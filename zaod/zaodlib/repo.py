"""Store repositories: signed index handling, cache, search and downloads."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import keys, schema, util
from .errors import RepoError

INDEX_FORMAT = 1
REPOS_FORMAT = 1
USER_AGENT = "zaod/0.7 (+https://zaod.os)"


@dataclass
class Repo:
    name: str
    url: str
    key_ids: list[str] = field(default_factory=list)
    enabled: bool = True
    last_sync: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "key_ids": list(self.key_ids),
            "enabled": self.enabled,
            "last_sync": self.last_sync,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Repo:
        return cls(
            name=data["name"],
            url=data["url"],
            key_ids=list(data.get("key_ids", [])),
            enabled=bool(data.get("enabled", True)),
            last_sync=data.get("last_sync"),
        )


class RepoSet:
    """The configured store repositories (``/var/lib/zaod/repos.json``)."""

    def __init__(self, paths):
        self.paths = paths
        self.path = paths.repos_file
        self.repos: list[Repo] = []
        self.load()

    def load(self) -> list[Repo]:
        if not self.path.is_file():
            self.repos = []
            return self.repos
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RepoError(f"{self.path} is corrupt: {exc}") from exc
        if data.get("format") != REPOS_FORMAT:
            raise RepoError(f"{self.path} has an unsupported format")
        self.repos = [Repo.from_dict(item) for item in data.get("repos", [])]
        return self.repos

    def save(self) -> None:
        payload = {"format": REPOS_FORMAT, "repos": [repo.to_dict() for repo in self.repos]}
        util.atomic_write_bytes(self.path, json.dumps(payload, indent=2).encode() + b"\n")

    def get(self, name: str) -> Repo:
        for repo in self.repos:
            if repo.name == name:
                return repo
        raise RepoError(f"no store repository named {name!r}")

    def add(self, repo: Repo, *, replace: bool = False) -> Repo:
        for index, existing in enumerate(self.repos):
            if existing.name == repo.name:
                if not replace:
                    raise RepoError(f"repository {repo.name!r} already exists")
                self.repos[index] = repo
                self.save()
                return repo
        self.repos.append(repo)
        self.save()
        return repo

    def remove(self, name: str) -> None:
        self.get(name)
        self.repos = [repo for repo in self.repos if repo.name != name]
        self.save()


def fetch(url: str, *, timeout: int = 30) -> bytes:
    """Fetch an index or package from https, http or file URLs."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("", "file"):
        path = Path(urllib.request.url2pathname(parsed.path)) if parsed.scheme == "file" else Path(url)
        if not path.is_file():
            raise RepoError(f"{path} does not exist")
        return path.read_bytes()
    if parsed.scheme not in ("https", "http"):
        raise RepoError(f"unsupported URL scheme {parsed.scheme!r} in {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RepoError(f"{url} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RepoError(f"cannot reach {url}: {exc.reason}") from exc


def index_url(url: str) -> str:
    return url.rstrip("/") + "/index.json"


def signature_url(url: str) -> str:
    return url.rstrip("/") + "/index.json.sig"


def load_schema() -> dict:
    from .manifest import SPEC_DIRS

    for directory in SPEC_DIRS:
        candidate = directory / "store-index.schema.json"
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise RepoError("store index schema not found")


def verify_index(raw_index: bytes, raw_signature: bytes, keyring: dict[str, bytes], allowed: list[str] | None) -> dict:
    """Verify the detached index signature, then validate the index body."""
    try:
        document = json.loads(raw_signature.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepoError(f"index signature is not valid JSON: {exc}") from exc
    key, signature = keys.parse_signature(document)
    if allowed and key not in allowed:
        raise RepoError(f"index is signed by {key}, which this repository does not trust")
    keys.verify_with_keyring(keyring, key, raw_index, signature)
    try:
        index = json.loads(raw_index.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepoError(f"index is not valid JSON: {exc}") from exc
    errors = schema.validate(index, load_schema(), "index")
    if errors:
        raise RepoError("invalid store index: " + "; ".join(errors))
    for package in index["packages"]:
        util.ensure_safe_relative(package["filename"], "index.filename")
    return index


def sync_repo(repo: Repo, paths, keyring: dict[str, bytes]) -> dict:
    """Download ``repo``'s index, verify it, and cache it locally."""
    raw_index = fetch(index_url(repo.url))
    raw_signature = fetch(signature_url(repo.url))
    index = verify_index(raw_index, raw_signature, keyring, repo.key_ids or None)
    if index["name"] != repo.name:
        raise RepoError(f"repository {repo.name!r} served an index named {index['name']!r}")
    cache = paths.index_cache_dir / repo.name
    util.atomic_write_bytes(cache / "index.json", raw_index)
    util.atomic_write_bytes(cache / "index.json.sig", raw_signature)
    repo.last_sync = util.utc_now()
    return index


def cached_index(paths, name: str) -> dict:
    path = paths.index_cache_dir / name / "index.json"
    if not path.is_file():
        raise RepoError(f"repository {name!r} has no cached index; run 'zaod repo sync'")
    raw = path.read_bytes()
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RepoError(f"cached index for {name!r} is corrupt: {exc}") from exc


def all_packages(indexes: dict[str, dict]) -> list[dict]:
    packages: list[dict] = []
    for name, index in indexes.items():
        for package in index.get("packages", []):
            entry = dict(package)
            entry["repo"] = name
            packages.append(entry)
    return packages


def search(indexes: dict[str, dict], query: str) -> list[dict]:
    needle = query.strip().lower()
    results = []
    for package in all_packages(indexes):
        haystack = " ".join(
            str(package.get(field, "")) for field in ("id", "name", "summary", "description")
        ).lower()
        if needle in haystack:
            results.append(package)
    results.sort(key=lambda item: (item.get("name", "").lower(), item["id"]))
    return results


def find_package(indexes: dict[str, dict], app_id: str, version: str | None = None) -> dict:
    matches = [
        package
        for package in all_packages(indexes)
        if package["id"] == app_id and (version is None or package["version"] == version)
    ]
    if not matches:
        raise RepoError(f"{app_id}{'' if version is None else ' ' + version} was not found in any repository")
    matches.sort(key=lambda item: util.parse_semver(item["version"]), reverse=True)
    return matches[0]


def package_url(package: dict, repo_url: str | None = None) -> str:
    """Absolute URL for a package, resolving bare file names against ``repo_url``."""
    url = str(package.get("url") or package["filename"])
    if "://" in url or repo_url is None:
        return url
    return repo_url.rstrip("/") + "/" + url.lstrip("./")


def download_package(package: dict, paths, repo_url: str | None = None) -> Path:
    """Download (or reuse) a package archive, verifying its index hash."""
    paths.package_cache_dir.mkdir(parents=True, exist_ok=True)
    target = paths.package_cache_dir / f"{package['sha256']}.zaod"
    if target.is_file():
        if util.sha256_file(target) == package["sha256"]:
            return target
        target.unlink()
    data = fetch(package_url(package, repo_url))
    actual = util.sha256_bytes(data)
    if actual != package["sha256"]:
        raise RepoError(
            f"{package['id']} {package['version']}: downloaded archive hash {actual} "
            f"does not match the signed index ({package['sha256']})"
        )
    util.atomic_write_bytes(target, data, mode=0o644)
    return target


def build_index(directory: Path, name: str, key: keys.KeyPair) -> tuple[Path, Path]:
    """Create a signed ``index.json`` for every ``*.zaod`` file in ``directory``."""
    from .archive import extract_tree
    from .manifest import load_manifest

    directory = Path(directory)
    packages = []
    for package_path in sorted(directory.glob("*.zaod")):
        staging = directory / f".index-{package_path.stem}"
        util.remove_tree(staging)
        extract_tree(package_path, staging)
        try:
            manifest = load_manifest(staging / "MANIFEST.json")
        finally:
            util.remove_tree(staging)
        packages.append(
            {
                "id": manifest.id,
                "name": manifest.name,
                "version": manifest.version,
                "kind": manifest.kind,
                "arch": manifest.arch,
                "min_os": manifest.min_os,
                "summary": manifest.summary,
                "description": manifest.description,
                "categories": manifest.categories,
                "license": manifest.license,
                "author": manifest.author,
                "permissions": manifest.permissions,
                "runtimes": manifest.runtimes,
                "size": package_path.stat().st_size,
                "sha256": util.sha256_file(package_path),
                "filename": package_path.name,
                "url": package_path.name,
            }
        )
    packages.sort(key=lambda item: (item["id"], util.parse_semver(item["version"])))
    index = {"format": INDEX_FORMAT, "name": name, "generated": util.utc_now(), "packages": packages}
    errors = schema.validate(index, load_schema(), "index")
    if errors:
        raise RepoError("refusing to write an invalid index: " + "; ".join(errors))
    raw = json.dumps(index, indent=2, sort_keys=True).encode() + b"\n"
    index_path = directory / "index.json"
    index_path.write_bytes(raw)
    signature = {"format": keys.SIGNATURE_FORMAT, "key_id": key.key_id,
                 "sig": base64.b64encode(key.sign(raw)).decode(), "signed": "index"}
    signature_path = directory / "index.json.sig"
    signature_path.write_text(json.dumps(signature, indent=2) + "\n", encoding="utf-8")
    return index_path, signature_path
