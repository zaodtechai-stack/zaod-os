"""Desktop integration: ``.desktop`` entries and default MIME associations."""

from __future__ import annotations

from pathlib import Path

from .manifest import Manifest

MIMEAPPS_HEADER = "[Default Applications]"


def desktop_exec(paths, manifest: Manifest) -> str:
    entry = manifest.entry.get("exec")
    if not entry:
        return ""
    current = paths.app_current(manifest.id)
    command = [str(current / entry), *manifest.entry.get("args", [])]
    return " ".join(_quote(part) for part in command)


def _quote(value: str) -> str:
    if value and all(character.isalnum() or character in "/._-+:" for character in value):
        return value
    return '"' + value.replace('"', '\\"') + '"'


def build_desktop_entry(paths, manifest: Manifest) -> str:
    current = paths.app_current(manifest.id)
    icon = current / manifest.icon
    categories = ";".join(manifest.categories) if manifest.categories else ""
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={manifest.name}",
        f"Comment={manifest.summary}",
        f"Exec={desktop_exec(paths, manifest)}",
        f"Icon={icon}",
        "Terminal=true" if manifest.entry.get("terminal") else "Terminal=false",
    ]
    if categories:
        lines.append(f"Categories={categories};" if not categories.endswith(";") else f"Categories={categories}")
    if manifest.associations:
        lines.append("MimeType=" + ";".join(manifest.associations) + ";")
    lines.extend(
        [
            "StartupNotify=true",
            f"X-Zaod-AppId={manifest.id}",
            f"X-Zaod-Version={manifest.version}",
            "",
        ]
    )
    return "\n".join(lines)


def install_desktop_entry(paths, manifest: Manifest) -> Path | None:
    if manifest.kind not in ("app", "project") or not manifest.entry.get("exec"):
        return None
    target = paths.desktop_file(manifest.id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_desktop_entry(paths, manifest), encoding="utf-8")
    target.chmod(0o644)
    if manifest.associations:
        set_default_associations(paths, manifest.id, manifest.associations)
    return target


def remove_desktop_entry(paths, app_id: str) -> bool:
    target = paths.desktop_file(app_id)
    if target.exists():
        target.unlink()
        return True
    return False


def mimeapps_path(paths) -> Path:
    return paths.path("/etc/xdg/mimeapps.list")


def set_default_associations(paths, app_id: str, mime_types: list[str]) -> Path:
    """Register ``app_id`` as the default handler for ``mime_types``."""
    path = mimeapps_path(paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines: list[str] = []
    in_section = False
    written: set[str] = set()
    for line in existing:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped == MIMEAPPS_HEADER
            lines.append(line)
            continue
        if in_section and "=" in stripped:
            mime = stripped.split("=", 1)[0].strip()
            if mime in mime_types:
                lines.append(f"{mime}={app_id}.desktop")
                written.add(mime)
                continue
        lines.append(line)
    if MIMEAPPS_HEADER not in [line.strip() for line in lines]:
        lines.insert(0, MIMEAPPS_HEADER)
        offset = 1
    else:
        offset = [line.strip() for line in lines].index(MIMEAPPS_HEADER) + 1
    for mime in mime_types:
        if mime not in written:
            lines.insert(offset, f"{mime}={app_id}.desktop")
            offset += 1
    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return path
