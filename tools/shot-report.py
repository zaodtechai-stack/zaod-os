#!/usr/bin/env python3
"""Describe a screenshot in text, so a layout can be reviewed without eyes.

Reviewing GUI work by reading code is how an "ugly" desktop gets shipped. This
turns a PNG into three things a reviewer can actually read:

* a coarse character map (luminance blocks) showing where panels, cards and
  empty areas sit;
* the dominant flat colours with the share of the window each one covers, which
  exposes a black content area, a border that is far too bright, or text that
  has the same colour as the surface under it;
* contrast ratios between the most common foreground and background colours.

Usage: shot-report.py image.png [--cols 110]
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from PIL import Image

RAMP = " .:-=+*#%@"


def luminance(rgb: tuple[int, int, int]) -> float:
    def channel(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hexed(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--cols", type=int, default=110)
    args = parser.parse_args()

    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    print(f"{Path(args.image).name}: {width}x{height}")

    cols = args.cols
    rows = max(8, round(cols * height / width * 0.48))
    small = image.resize((cols, rows), Image.BOX)
    print("-" * cols)
    for y in range(rows):
        line = []
        for x in range(cols):
            lum = luminance(small.getpixel((x, y)))
            line.append(RAMP[min(len(RAMP) - 1, int(lum ** 0.5 * len(RAMP)))])
        print("".join(line))
    print("-" * cols)

    counts = Counter(image.getdata())
    total = width * height
    print("dominant colours:")
    top = counts.most_common(8)
    for colour, count in top:
        print(f"  {hexed(colour)}  {count / total:6.1%}")

    if len(top) >= 2:
        background = top[0][0]
        print("contrast against the most common colour:")
        for colour, count in top[1:6]:
            print(f"  {hexed(colour)} on {hexed(background)}  {contrast(colour, background):5.2f}:1")

    # How many distinct "edges" there are: a clean layout has few strong lines.
    edges = 0
    for y in range(1, height - 1, 2):
        previous = image.getpixel((0, y))
        for x in range(1, width, 2):
            current = image.getpixel((x, y))
            if abs(sum(current) - sum(previous)) > 60:
                edges += 1
            previous = current
    print(f"strong horizontal edges: {edges} ({edges / max(1, total / 4):.2%} of sampled pixels)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
