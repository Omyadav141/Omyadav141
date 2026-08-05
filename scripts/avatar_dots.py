#!/usr/bin/env python3
"""
avatar_dots.py — turn a GitHub profile picture into an animated
LED / dot-matrix display (SVG).

It downloads https://github.com/<user>.png, samples it down to a grid and
draws every cell as a glowing dot whose size and colour come from the pixel
underneath. The dots switch on in a diagonal wave, a light bar sweeps across
the glass, and then the panel breathes forever.

Change your profile picture on GitHub -> run this again (the included GitHub
Action does it for you) -> the display shows the new picture. Nothing else
to update.

Usage
  python scripts/avatar_dots.py --user Omyadav141 --out assets/avatar-dotmatrix.svg
  python scripts/avatar_dots.py --user Omyadav141 --mode mono --shape circle
  python scripts/avatar_dots.py --local me.png  --out assets/avatar-dotmatrix.svg
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

from PIL import Image, ImageEnhance

# ------------------------------------------------------------------ tuning --
CELL = 8             # svg units per dot cell
PAD_X = 34           # panel padding, left and right
PAD_TOP = 34
PAD_BOTTOM = 50      # extra room for the label strip
BANDS = 22           # how many diagonal waves sweep across the panel
MIN_R = 0.55         # radius of the dimmest visible dot
MAX_R = 3.45         # radius of the brightest dot (CELL/2 minus a hairline gap)
CUTOFF = 0.055       # below this luminance the LED stays off
REVEAL = 2.6         # seconds for the whole power-on wave

PALETTES = {
    "color": None,                 # keep the picture's own colours
    "mono": (126, 231, 135),       # green phosphor
    "amber": (255, 176, 86),       # amber CRT
    "ice": (121, 192, 255),        # blue terminal
}


def load_image(user: str | None, local: str | None, px: int) -> Image.Image:
    """Fetch the avatar (or a local file) and return a square RGB image."""
    if local:
        img = Image.open(local)
    else:
        url = "https://github.com/" + user + ".png?size=" + str(px)
        req = urllib.request.Request(url, headers={"User-Agent": "avatar-dots"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            img = Image.open(resp).copy()

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGBA", img.size, (10, 14, 22, 255))
        flat.alpha_composite(img)
        img = flat
    img = img.convert("RGB")

    # centre-crop to a square so the face is never stretched
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return ImageEnhance.Color(img).enhance(1.22)   # a little extra saturation


def dot_colour(rgb, v: float, tint) -> str:
    """Colour of a single LED: the real pixel colour, or one phosphor hue."""
    if tint is not None:
        k = 0.35 + 0.65 * v
        r, g, b = (int(c * k) for c in tint)
    else:
        k = 0.55 + 0.45 * v        # lift dark pixels so they still read on black
        r, g, b = (min(255, int(c * k) + 12) for c in rgb)
    return "#%02x%02x%02x" % (r, g, b)


def build_svg(img, grid: int, mode: str, shape: str, label: str, accent: str) -> str:
    tint = PALETTES[mode]
    small = img.resize((grid, grid), Image.LANCZOS)
    px = small.load()

    art = grid * CELL
    w = art + PAD_X * 2
    h = art + PAD_TOP + PAD_BOTTOM
    mid = (grid - 1) / 2
    radius = grid / 2 - 0.35

    bands: dict[int, list[str]] = {}
    for gy in range(grid):
        for gx in range(grid):
            if shape == "circle" and ((gx - mid) ** 2 + (gy - mid) ** 2) ** 0.5 > radius:
                continue
            r8, g8, b8 = px[gx, gy]
            v = (0.2126 * r8 + 0.7152 * g8 + 0.0722 * b8) / 255
            if v < CUTOFF:
                continue
            v = v ** 0.82                       # gamma: keep the midtones lively
            rr = round(MIN_R + (MAX_R - MIN_R) * v, 2)
            x = PAD_X + gx * CELL + CELL // 2
            y = PAD_TOP + gy * CELL + CELL // 2
            band = int((gx + gy) / (2 * grid - 1) * (BANDS - 1))
            bands.setdefault(band, []).append(
                '<circle cx="%d" cy="%d" r="%s" fill="%s"/>'
                % (x, y, rr, dot_colour((r8, g8, b8), v, tint))
            )

    # every wave is one group with two SMIL animations: switch on, then breathe
    groups = []
    for b in sorted(bands):
        start = 0.25 + b * 0.06
        end = start + 0.75
        on = ('<animate attributeName="opacity" values="0;0;1;1" keyTimes="0;%s;%s;1"'
              ' dur="%ss" fill="freeze"/>'
              % (round(start / REVEAL, 4), round(end / REVEAL, 4), REVEAL))
        breathe = ('<animate attributeName="opacity" values="1;.8;1" dur="%ss"'
                   ' begin="%ss" repeatCount="indefinite"/>'
                   % (round(3.4 + (b % 5) * 0.4, 2), round(REVEAL + 0.2 + b * 0.05, 2)))
        groups.append('<g opacity="1">' + on + breathe + "".join(bands[b]) + "</g>")
    dots = "\n".join(groups)

    lx, ly = PAD_X, h - 20
    half = CELL // 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{label}: profile picture rendered as an animated dot-matrix display">
<title>{label} — dot-matrix avatar</title>
<defs>
<linearGradient id="glass" x1="0" y1="0" x2="0.6" y2="1">
<stop offset="0" stop-color="#0b0f16"/><stop offset="1" stop-color="#05070b"/>
</linearGradient>
<linearGradient id="sweep" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{accent}" stop-opacity="0"/>
<stop offset="0.5" stop-color="{accent}" stop-opacity="0.14"/>
<stop offset="1" stop-color="{accent}" stop-opacity="0"/>
</linearGradient>
<pattern id="off" x="{PAD_X}" y="{PAD_TOP}" width="{CELL}" height="{CELL}" patternUnits="userSpaceOnUse">
<circle cx="{half}" cy="{half}" r="0.85" fill="#161d29"/>
</pattern>
<filter id="bloom" x="-10%" y="-10%" width="120%" height="120%">
<feGaussianBlur stdDeviation="1.9" result="b"/>
<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
</filter>
<clipPath id="screen"><rect x="{PAD_X - 8}" y="{PAD_TOP - 8}" width="{art + 16}" height="{art + 16}" rx="14"/></clipPath>
</defs>

<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="22" fill="url(#glass)" stroke="#1b2431" stroke-width="2"/>
<rect x="{PAD_X - 8}" y="{PAD_TOP - 8}" width="{art + 16}" height="{art + 16}" rx="14" fill="#070a10" stroke="#182130"/>
<rect x="{PAD_X}" y="{PAD_TOP}" width="{art}" height="{art}" fill="url(#off)"/>

<g clip-path="url(#screen)">
<g filter="url(#bloom)" shape-rendering="geometricPrecision">
{dots}
</g>
<rect x="{PAD_X - 8}" y="-92" width="{art + 16}" height="92" fill="url(#sweep)">
<animateTransform attributeName="transform" type="translate" values="0 0;0 {art + 200}" dur="5.5s" begin="1.4s" repeatCount="indefinite"/>
</rect>
</g>

<g stroke="{accent}" stroke-width="2" fill="none" opacity=".55" stroke-linecap="round">
<path d="M{PAD_X - 14} {PAD_TOP - 2} v-12 h12"/>
<path d="M{PAD_X + art + 14} {PAD_TOP - 2} v-12 h-12"/>
<path d="M{PAD_X - 14} {PAD_TOP + art + 2} v12 h12"/>
<path d="M{PAD_X + art + 14} {PAD_TOP + art + 2} v12 h-12"/>
</g>

<circle cx="{lx + 4}" cy="{ly - 4}" r="3.4" fill="#7ee787">
<animate attributeName="opacity" values="1;.25;1" dur="2.2s" repeatCount="indefinite"/>
</circle>
<text x="{lx + 16}" y="{ly}" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="11" letter-spacing="2.4" fill="#6e7681">{label.upper()}</text>
<text x="{w - PAD_X}" y="{ly}" text-anchor="end" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" font-size="11" letter-spacing="2.4" fill="{accent}" opacity=".8">ONLINE</text>
</svg>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a GitHub avatar as a dot-matrix SVG")
    ap.add_argument("--user", help="GitHub username")
    ap.add_argument("--local", help="use a local image instead of the GitHub avatar")
    ap.add_argument("--out", default="assets/avatar-dotmatrix.svg")
    ap.add_argument("--grid", type=int, default=42, help="dots per side (32-56 looks best)")
    ap.add_argument("--mode", choices=sorted(PALETTES), default="color")
    ap.add_argument("--shape", choices=("square", "circle"), default="square")
    ap.add_argument("--accent", default="#58a6ff")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    if not args.user and not args.local:
        ap.error("pass --user <github-name> or --local <file>")

    label = args.label or (args.user or "profile")
    img = load_image(args.user, args.local, max(320, args.grid * 8))
    svg = build_svg(img, args.grid, args.mode, args.shape, label, args.accent)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")
    print("wrote %s  (%.1f KB, %dx%d dots, mode=%s)"
          % (out, out.stat().st_size / 1024, args.grid, args.grid, args.mode))


if __name__ == "__main__":
    main()
