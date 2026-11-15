#!/usr/bin/env python3
"""Render the original Zaod OS boot splash artwork.

The artwork is generated from code instead of being committed as binaries, so
the repository stays free of opaque blobs and every pixel is auditable.  Only
the Python standard library is used: the PNG encoder, the vector rasteriser and
the small bitmap font below are all part of this file.

Everything drawn here is original Zaod OS geometry and Zaod OS lettering.  No
third-party logo, font, sound or trademark is copied, and no Microsoft/Windows
asset is reproduced in any form.

Output (into --outdir):
    background-<W>x<H>.png   dark vertical gradient + soft accent bloom
    zaod-mark.png            ring + geometric Z mark
    zaod-wordmark.png        "ZAOD OS" wordmark
    zaod-tagline.png         "LIVE MEDIA" caption
    spinner-0..7.png         eight frames of a rotating arc
    progress-dim.png         unlit progress pill
    progress-lit.png         lit progress pill
    assets.txt               manifest: name, size, sha256 (idempotency check)

Re-running with an up-to-date manifest is a no-op unless --force is given.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import struct
import sys
import zlib
from collections.abc import Callable, Iterable
from pathlib import Path

# ---------------------------------------------------------------- palette ---
INK = (0x0B, 0x0F, 0x16)  # deepest background
DEEP = (0x12, 0x1A, 0x26)  # upper background
SURFACE = (0x1B, 0x25, 0x33)
TEXT = (0xE9, 0xF1, 0xF7)
MUTED = (0x8F, 0xA2, 0xB7)
ACCENT = (0x2F, 0xD3, 0xC0)  # Zaod teal
ACCENT2 = (0x5B, 0x8C, 0xFF)  # Zaod azure
DIM_PILL = (0x24, 0x30, 0x40)

BACKGROUND_SIZES: tuple[tuple[int, int], ...] = (
    (1920, 1080),
    (1600, 900),
    (1366, 768),
    (1280, 1024),
    (1024, 768),
    (800, 600),
)

SPINNER_FRAMES = 8
SPINNER_SIZE = 128

# 5x7 bitmap font.  Original glyph shapes, drawn for Zaod OS.
FONT: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
}


# ------------------------------------------------------------------- png ----
def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png(width: int, height: int, pixels: bytearray) -> bytes:
    """Encode an 8-bit RGB buffer (bytearray of width*height*3) as PNG."""
    stride = width * 3
    expected = stride * height
    if len(pixels) != expected:
        raise ValueError(f"buffer is {len(pixels)} bytes, expected {expected}")
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter type 0 (None) keeps output deterministic
        raw += pixels[y * stride : (y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


class Canvas:
    """Tiny RGB canvas with alpha compositing and anti-aliased shape masks."""

    def __init__(self, width: int, height: int, background: tuple[int, int, int]) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(background) * (width * height))

    def blend(self, x: int, y: int, color: tuple[int, int, int], alpha: float) -> None:
        if alpha <= 0.0 or not (0 <= x < self.width and 0 <= y < self.height):
            return
        alpha = min(alpha, 1.0)
        offset = (y * self.width + x) * 3
        px = self.pixels
        if alpha >= 0.999:
            px[offset : offset + 3] = bytes(color)
            return
        inv = 1.0 - alpha
        px[offset] = int(px[offset] * inv + color[0] * alpha + 0.5)
        px[offset + 1] = int(px[offset + 1] * inv + color[1] * alpha + 0.5)
        px[offset + 2] = int(px[offset + 2] * inv + color[2] * alpha + 0.5)

    def draw_mask(
        self,
        inside: Callable[[float, float], bool],
        bounds: tuple[float, float, float, float],
        color: tuple[int, int, int],
        alpha: float = 1.0,
        samples: int = 3,
    ) -> None:
        """Fill where inside(x, y) is true, supersampled for smooth edges."""
        x0 = max(0, math.floor(bounds[0]))
        y0 = max(0, math.floor(bounds[1]))
        x1 = min(self.width, math.ceil(bounds[2]))
        y1 = min(self.height, math.ceil(bounds[3]))
        total = samples * samples
        step = 1.0 / samples
        offset = step / 2.0
        for y in range(y0, y1):
            for x in range(x0, x1):
                hits = 0
                for sy in range(samples):
                    fy = y + offset + sy * step
                    for sx in range(samples):
                        if inside(x + offset + sx * step, fy):
                            hits += 1
                if hits:
                    self.blend(x, y, color, alpha * hits / total)

    def draw_gradient_mask(
        self,
        inside: Callable[[float, float], bool],
        bounds: tuple[float, float, float, float],
        color_from: tuple[int, int, int],
        color_to: tuple[int, int, int],
        samples: int = 3,
    ) -> None:
        """Like draw_mask but with a vertical colour ramp across bounds."""
        x0 = max(0, math.floor(bounds[0]))
        y0 = max(0, math.floor(bounds[1]))
        x1 = min(self.width, math.ceil(bounds[2]))
        y1 = min(self.height, math.ceil(bounds[3]))
        total = samples * samples
        step = 1.0 / samples
        offset = step / 2.0
        span = max(1.0, bounds[3] - bounds[1])
        for y in range(y0, y1):
            t = min(1.0, max(0.0, (y - bounds[1]) / span))
            color = (
                int(color_from[0] + (color_to[0] - color_from[0]) * t),
                int(color_from[1] + (color_to[1] - color_from[1]) * t),
                int(color_from[2] + (color_to[2] - color_from[2]) * t),
            )
            for x in range(x0, x1):
                hits = 0
                for sy in range(samples):
                    fy = y + offset + sy * step
                    for sx in range(samples):
                        if inside(x + offset + sx * step, fy):
                            hits += 1
                if hits:
                    self.blend(x, y, color, hits / total)

    def to_png(self) -> bytes:
        return encode_png(self.width, self.height, self.pixels)


# ------------------------------------------------------------------ text ----
def text_size(text: str, scale: int, tracking: int = 1) -> tuple[int, int]:
    cell = 5 * scale
    gap = tracking * scale
    width = len(text) * (cell + gap) - gap if text else 0
    return width, 7 * scale


def draw_text(
    canvas: Canvas,
    text: str,
    origin_x: int,
    origin_y: int,
    scale: int,
    color: tuple[int, int, int],
    tracking: int = 1,
) -> None:
    cell = 5 * scale
    gap = tracking * scale
    cursor = origin_x
    for char in text.upper():
        glyph = FONT.get(char)
        if glyph is None:
            glyph = FONT[" "]
        lit = [
            (col, row)
            for row, line in enumerate(glyph)
            for col, value in enumerate(line)
            if value == "1"
        ]

        def inside(x: float, y: float, _lit=lit, _cursor=cursor) -> bool:
            gx = (x - _cursor) / scale
            gy = (y - origin_y) / scale
            if gx < 0 or gy < 0 or gx >= 5 or gy >= 7:
                return False
            return (int(gx), int(gy)) in _lit

        canvas.draw_mask(
            inside,
            (cursor, origin_y, cursor + cell, origin_y + 7 * scale),
            color,
            samples=2,
        )
        cursor += cell + gap


# --------------------------------------------------------------- objects ----
def ring_mask(cx: float, cy: float, radius: float, thickness: float) -> Callable[[float, float], bool]:
    inner = radius - thickness
    outer = radius

    def inside(x: float, y: float) -> bool:
        d = math.hypot(x - cx, y - cy)
        return inner <= d <= outer

    return inside


def arc_mask(
    cx: float,
    cy: float,
    radius: float,
    thickness: float,
    start: float,
    end: float,
) -> Callable[[float, float], bool]:
    inner = radius - thickness
    outer = radius

    def inside(x: float, y: float) -> bool:
        dx = x - cx
        dy = y - cy
        d = math.hypot(dx, dy)
        if not (inner <= d <= outer):
            return False
        angle = math.atan2(dy, dx) % (2 * math.pi)
        a0 = start % (2 * math.pi)
        a1 = end % (2 * math.pi)
        if a0 <= a1:
            return a0 <= angle <= a1
        return angle >= a0 or angle <= a1

    return inside


def polygon_mask(points: list[tuple[float, float]]) -> Callable[[float, float], bool]:
    def inside(x: float, y: float) -> bool:
        result = False
        count = len(points)
        j = count - 1
        for i in range(count):
            xi, yi = points[i]
            xj, yj = points[j]
            if (yi > y) != (yj > y):
                x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
                if x < x_cross:
                    result = not result
            j = i
        return result

    return inside


def rounded_rect_mask(
    x0: float, y0: float, x1: float, y1: float, radius: float
) -> Callable[[float, float], bool]:
    """Axis-aligned rectangle whose four corners are cut to `radius`."""

    def inside(x: float, y: float) -> bool:
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            return False
        left = x < x0 + radius
        right = x > x1 - radius
        top = y < y0 + radius
        bottom = y > y1 - radius
        if left and top:
            return math.hypot(x - (x0 + radius), y - (y0 + radius)) <= radius
        if right and top:
            return math.hypot(x - (x1 - radius), y - (y0 + radius)) <= radius
        if left and bottom:
            return math.hypot(x - (x0 + radius), y - (y1 - radius)) <= radius
        if right and bottom:
            return math.hypot(x - (x1 - radius), y - (y1 - radius)) <= radius
        return True

    return inside


# --------------------------------------------------------------- artwork ----
def render_background(width: int, height: int) -> Canvas:
    """Dark vertical gradient plus a soft accent bloom behind the logo."""
    canvas = Canvas(width, height, INK)
    pixels = canvas.pixels

    # Soft bloom, evaluated at quarter resolution and bilinearly upsampled.
    scale = 4
    low_w = max(2, width // scale)
    low_h = max(2, height // scale)
    centre_x = low_w / 2.0
    centre_y = low_h * 0.40
    radius = max(low_w, low_h) * 0.62
    bloom = bytearray(low_w * low_h * 3)
    for y in range(low_h):
        for x in range(low_w):
            d = math.hypot(x - centre_x, y - centre_y) / radius
            strength = 0.0 if d >= 1.0 else (1.0 - d) ** 2 * 0.22
            offset = (y * low_w + x) * 3
            bloom[offset] = int(ACCENT[0] * strength)
            bloom[offset + 1] = int(ACCENT[1] * strength)
            bloom[offset + 2] = int(ACCENT2[2] * strength)

    for y in range(height):
        t = y / (height - 1) if height > 1 else 0.0
        # ease towards the deep ink at the bottom
        base = (
            int(DEEP[0] + (INK[0] - DEEP[0]) * (t ** 0.85)),
            int(DEEP[1] + (INK[1] - DEEP[1]) * (t ** 0.85)),
            int(DEEP[2] + (INK[2] - DEEP[2]) * (t ** 0.85)),
        )
        row = bytearray(bytes(base) * width)
        # nearest-neighbour upsample of the quarter-resolution bloom
        y_low = min(low_h - 1, y * low_h // height)
        for x in range(width):
            x_low = min(low_w - 1, x * low_w // width)
            offset = (y_low * low_w + x_low) * 3
            r = bloom[offset]
            g = bloom[offset + 1]
            b = bloom[offset + 2]
            if r or g or b:
                pos = x * 3
                row[pos] = min(255, row[pos] + r)
                row[pos + 1] = min(255, row[pos + 1] + g)
                row[pos + 2] = min(255, row[pos + 2] + b)
        pixels[y * width * 3 : (y + 1) * width * 3] = row

    # Thin accent rule that grounds the logo block.
    rule_y = int(height * 0.68)
    canvas.draw_mask(
        lambda x, y: 0 <= y - rule_y < max(1, height // 540),
        (width * 0.34, rule_y, width * 0.66, rule_y + max(1, height // 540)),
        SURFACE,
    )
    return canvas


def render_mark(size: int = 256) -> Canvas:
    """Ring + geometric Z.  Original Zaod OS mark."""
    canvas = Canvas(size, size, INK)
    canvas.pixels = bytearray(bytes((0, 0, 0)) * (size * size))
    cx = cy = size / 2.0
    radius = size * 0.46
    thickness = size * 0.045

    # Outer ring, split into two arcs so the mark reads as an open orbit.
    canvas.draw_gradient_mask(
        arc_mask(cx, cy, radius, thickness, math.radians(200), math.radians(20)),
        (0, 0, size, size),
        ACCENT,
        ACCENT2,
    )
    canvas.draw_mask(
        arc_mask(cx, cy, radius, thickness, math.radians(30), math.radians(190)),
        (0, 0, size, size),
        SURFACE,
        alpha=0.55,
    )

    # Inner Z: two bars and a diagonal, all polygons.
    bar_h = size * 0.075
    bar_w = size * 0.30
    left = cx - bar_w / 2.0
    top = cy - size * 0.18
    bottom = cy + size * 0.18
    canvas.draw_mask(
        polygon_mask(
            [
                (left, top),
                (left + bar_w, top),
                (left + bar_w, top + bar_h),
                (left, top + bar_h),
            ]
        ),
        (left, top, left + bar_w, top + bar_h),
        TEXT,
    )
    canvas.draw_mask(
        polygon_mask(
            [
                (left, bottom - bar_h),
                (left + bar_w, bottom - bar_h),
                (left + bar_w, bottom),
                (left, bottom),
            ]
        ),
        (left, bottom - bar_h, left + bar_w, bottom),
        TEXT,
    )
    canvas.draw_mask(
        polygon_mask(
            [
                (left + bar_w * 0.80, top + bar_h),
                (left + bar_w, top + bar_h),
                (left + bar_w * 0.24, bottom - bar_h),
                (left + bar_w * 0.04, bottom - bar_h),
            ]
        ),
        (left, top, left + bar_w, bottom),
        ACCENT,
    )
    return canvas


def render_wordmark(text: str, scale: int, color: tuple[int, int, int]) -> Canvas:
    width, height = text_size(text, scale, tracking=1)
    pad = scale * 2
    canvas = Canvas(width + pad * 2, height + pad * 2, INK)
    canvas.pixels = bytearray(bytes((0, 0, 0)) * (canvas.width * canvas.height))
    draw_text(canvas, text, pad, pad, scale, color)
    return canvas


def render_spinner(frame: int, frames: int, size: int) -> Canvas:
    canvas = Canvas(size, size, INK)
    canvas.pixels = bytearray(bytes((0, 0, 0)) * (size * size))
    cx = cy = size / 2.0
    radius = size * 0.42
    thickness = size * 0.075
    sweep = math.radians(110)
    start = (2 * math.pi / frames) * frame
    # Three trailing arc segments of decreasing opacity.
    for index, alpha in enumerate((1.0, 0.55, 0.25)):
        offset = index * sweep * 0.75
        colour = ACCENT if index == 0 else SURFACE
        canvas.draw_mask(
            arc_mask(cx, cy, radius, thickness, start + offset, start + offset + sweep),
            (0, 0, size, size),
            colour,
            alpha=alpha if index else 1.0,
            samples=2,
        )
    return canvas


def render_pill(width: int, height: int, color: tuple[int, int, int]) -> Canvas:
    canvas = Canvas(width, height, INK)
    canvas.pixels = bytearray(bytes((0, 0, 0)) * (width * height))
    radius = height / 2.0
    canvas.draw_mask(
        rounded_rect_mask(0.5, 0.5, width - 1.5, height - 1.5, radius),
        (0, 0, width, height),
        color,
        samples=3,
    )
    return canvas


# ------------------------------------------------------------------ main ----
def build_outputs() -> Iterable[tuple[str, bytes]]:
    for width, height in BACKGROUND_SIZES:
        yield f"background-{width}x{height}.png", render_background(width, height).to_png()
    yield "zaod-mark.png", render_mark().to_png()
    yield "zaod-wordmark.png", render_wordmark("ZAOD OS", 5, TEXT).to_png()
    yield "zaod-tagline.png", render_wordmark("LIVE MEDIA", 2, MUTED).to_png()
    for frame in range(SPINNER_FRAMES):
        yield (
            f"spinner-{frame}.png",
            render_spinner(frame, SPINNER_FRAMES, SPINNER_SIZE).to_png(),
        )
    yield "progress-dim.png", render_pill(28, 6, DIM_PILL).to_png()
    yield "progress-lit.png", render_pill(28, 6, ACCENT).to_png()


def manifest_text(entries: list[tuple[str, bytes]]) -> str:
    lines = []
    for name, data in sorted(entries, key=lambda item: item[0]):
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}  {len(data)}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the Zaod OS splash artwork.")
    parser.add_argument("--outdir", required=True, type=Path, help="destination directory")
    parser.add_argument("--force", action="store_true", help="regenerate even if up to date")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify existing output instead of writing it",
    )
    args = parser.parse_args(argv)

    entries = list(build_outputs())
    manifest = manifest_text(entries)
    outdir: Path = args.outdir
    manifest_path = outdir / "assets.txt"

    if args.check:
        if not manifest_path.is_file() or manifest_path.read_text(encoding="utf-8") != manifest:
            print(f"{outdir}: artwork is missing or out of date", file=sys.stderr)
            return 1
        print(f"{outdir}: artwork up to date ({len(entries)} files)")
        return 0

    if (
        not args.force
        and manifest_path.is_file()
        and manifest_path.read_text(encoding="utf-8") == manifest
    ):
        print(f"{outdir}: artwork up to date ({len(entries)} files), nothing to do")
        return 0

    outdir.mkdir(parents=True, exist_ok=True)
    for name, data in entries:
        (outdir / name).write_bytes(data)
    manifest_path.write_text(manifest, encoding="utf-8")
    total = sum(len(data) for _, data in entries)
    print(f"{outdir}: wrote {len(entries)} PNG files ({total} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
