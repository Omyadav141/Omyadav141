#!/usr/bin/env python3
"""
stats_cards.py — build your GitHub stat cards yourself, as animated SVGs.

The usual cards (github-readme-stats, github-profile-trophy) live on free
shared servers that regularly answer 503 / 402, and then your profile shows
broken images. This script asks the GitHub API directly — from inside your
own GitHub Action, with your own token — and writes three SVG files into
assets/. GitHub then serves them from your repo, so they can never rate-limit
or go down.

Writes:
  assets/stats-card.svg     stars / commits / PRs / issues / repos + rank ring
  assets/langs-card.svg     most used languages, real GitHub language colours
  assets/achievements.svg   wide six-tile row (replaces the trophy strip)

Usage:
  GH_TOKEN=xxx python scripts/stats_cards.py --user Omyadav141
  python scripts/stats_cards.py --demo          # sample data, no network
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

API = "https://api.github.com/graphql"
BG = "#0d1117"
EDGE = "#1b2431"
TEXT = "#c9d1d9"
MUTED = "#6e7681"
ACCENT = "#58a6ff"
GOOD = "#7ee787"

QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestReviewContributions
    }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        forkCount
        languages(first: 12, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

DEMO = {
    "name": "Om Yadav",
    "stars": 128,
    "commits": 253,
    "prs": 34,
    "issues": 17,
    "repos": 21,
    "followers": 46,
    "reviews": 9,
    "forks": 12,
    "langs": [
        ("Python", 612000, "#3572A5"),
        ("Jupyter Notebook", 240000, "#DA5B0B"),
        ("JavaScript", 132000, "#f1e05a"),
        ("Java", 96000, "#b07219"),
        ("HTML", 61000, "#e34c26"),
        ("CSS", 38000, "#563d7c"),
        ("R", 22000, "#198CE7"),
    ],
}


# ------------------------------------------------------------------- data --
def call_api(token: str, login: str, after: str | None) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": login, "after": after}})
    req = urllib.request.Request(
        API,
        data=body.encode(),
        headers={
            "Authorization": "bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "stats-cards",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    if "errors" in payload:
        raise SystemExit("GitHub API error: " + json.dumps(payload["errors"]))
    return payload["data"]["user"]


def fetch(token: str, login: str) -> dict:
    """Pull every owned repo (paginated) and roll it up into plain numbers."""
    stars = forks = 0
    sizes: dict[str, int] = {}
    colours: dict[str, str] = {}
    after = None
    user = None

    while True:
        user = call_api(token, login, after)
        repos = user["repositories"]
        for node in repos["nodes"]:
            stars += node["stargazerCount"]
            forks += node["forkCount"]
            for edge in node["languages"]["edges"]:
                name = edge["node"]["name"]
                sizes[name] = sizes.get(name, 0) + edge["size"]
                colours[name] = edge["node"]["color"] or MUTED
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]

    contrib = user["contributionsCollection"]
    ranked = sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "name": user["name"] or user["login"],
        "stars": stars,
        "forks": forks,
        "commits": contrib["totalCommitContributions"] + contrib["restrictedContributionsCount"],
        "reviews": contrib["totalPullRequestReviewContributions"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "langs": [(n, s, colours[n]) for n, s in ranked],
    }


# ------------------------------------------------------------------ utils --
def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt(n: int) -> str:
    if n >= 1000000:
        return "%.1fM" % (n / 1000000.0)
    if n >= 10000:
        return "%.1fk" % (n / 1000.0)
    if n >= 1000:
        return "%d,%03d" % (n // 1000, n % 1000)
    return str(n)


def rank(d: dict) -> tuple[str, float]:
    """Cheap, readable score -> letter grade + how full the ring should be."""
    score = (
        d["commits"] * 1.0
        + d["stars"] * 2.0
        + d["prs"] * 3.0
        + d["issues"] * 1.5
        + d["followers"] * 2.0
        + d["reviews"] * 2.0
    )
    table = [(2600, "S"), (1500, "A+"), (900, "A"), (500, "B+"), (250, "B"), (90, "C+")]
    for need, letter in table:
        if score >= need:
            pct = min(1.0, 0.55 + 0.45 * (score - need) / max(need, 1))
            return letter, pct
    return "C", max(0.12, score / 90.0 * 0.5)


def icon(kind: str, x: int, y: int, colour: str) -> str:
    """Tiny 14px line icons, drawn so no icon font is needed."""
    s = 'fill="none" stroke="%s" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"' % colour
    if kind == "star":
        return '<path transform="translate(%d %d)" d="M7 1.2l1.8 3.7 4 .6-2.9 2.8.7 4L7 10.4 3.4 12.3l.7-4L1.2 5.5l4-.6z" fill="%s" stroke="none"/>' % (x, y, colour)
    if kind == "commit":
        return '<g transform="translate(%d %d)" %s><circle cx="7" cy="7" r="3"/><path d="M0 7h4M10 7h4"/></g>' % (x, y, s)
    if kind == "pr":
        return '<g transform="translate(%d %d)" %s><circle cx="3" cy="3" r="2"/><circle cx="3" cy="11" r="2"/><path d="M3 5v4"/><circle cx="11" cy="11" r="2"/><path d="M11 9V4H8l2-2M8 4l2 2"/></g>' % (x, y, s)
    if kind == "issue":
        return '<g transform="translate(%d %d)" %s><circle cx="7" cy="7" r="5.6"/><circle cx="7" cy="7" r="1.4" fill="%s" stroke="none"/></g>' % (x, y, s, colour)
    if kind == "repo":
        return '<g transform="translate(%d %d)" %s><path d="M2 2.4h8.6a1.4 1.4 0 011.4 1.4v8.8H3.4A1.4 1.4 0 012 11.2z"/><path d="M2 10.2h10"/></g>' % (x, y, s)
    return '<g transform="translate(%d %d)" %s><circle cx="7" cy="4.6" r="2.8"/><path d="M1.6 12.6c.7-2.6 2.8-3.8 5.4-3.8s4.7 1.2 5.4 3.8"/></g>' % (x, y, s)


def shell(w: int, h: int, title: str, label: str) -> str:
    """Card background + title, shared by every card."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'role="img" aria-label="%s">\n'
        '<title>%s</title>\n'
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>\n'
        '<text x="25" y="36" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
        'font-size="16" font-weight="600" fill="%s">%s</text>\n'
        % (w, h, w, h, esc(label), esc(label), w - 1, h - 1, BG, EDGE, ACCENT, esc(title))
    )


def reveal(delay: float, shift: int = -10) -> str:
    """Fade + slide in. Base state stays visible if SMIL never runs."""
    total = 1.8
    k0 = round(delay / total, 4)
    k1 = round(min(delay + 0.45, total) / total, 4)
    return (
        '<animate attributeName="opacity" values="0;0;1;1" keyTimes="0;%s;%s;1" dur="%ss" fill="freeze"/>'
        '<animateTransform attributeName="transform" type="translate" values="%d 0;0 0" '
        'dur="0.5s" begin="%ss" fill="freeze" calcMode="spline" keySplines="0.16 0.8 0.24 1"/>'
        % (k0, k1, total, shift, round(delay, 2))
    )


# ------------------------------------------------------------------ cards --
def stats_card(d: dict) -> str:
    w, h = 480, 200
    rows = [
        ("star", "Total stars earned", d["stars"]),
        ("commit", "Commits (past year)", d["commits"]),
        ("pr", "Pull requests", d["prs"]),
        ("issue", "Issues opened", d["issues"]),
        ("repo", "Public repositories", d["repos"]),
        ("user", "Followers", d["followers"]),
    ]
    out = [shell(w, h, d["name"] + "'s GitHub stats", d["name"] + " GitHub statistics")]

    y = 62
    for i, (kind, label, value) in enumerate(rows):
        out.append('<g opacity="1">%s' % reveal(0.15 + i * 0.09))
        out.append(icon(kind, 26, y - 11, ACCENT))
        out.append(
            '<text x="50" y="%d" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
            'font-size="13" fill="%s">%s</text>' % (y, TEXT, esc(label))
        )
        out.append(
            '<text x="330" y="%d" text-anchor="end" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
            'font-size="13" font-weight="600" fill="%s">%s</text>' % (y, GOOD, fmt(value))
        )
        out.append("</g>")
        y += 22

    letter, pct = rank(d)
    cx, cy, r = 400, 108, 42
    circ = round(2 * 3.14159265 * r, 2)
    out.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="#21262d" stroke-width="7"/>' % (cx, cy, r))
    out.append(
        '<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="7" stroke-linecap="round" '
        'transform="rotate(-90 %d %d)" stroke-dasharray="%s" stroke-dashoffset="%s">'
        '<animate attributeName="stroke-dashoffset" values="%s;%s" dur="1.5s" begin="0.35s" fill="freeze" '
        'calcMode="spline" keySplines="0.2 0.7 0.2 1"/></circle>'
        % (cx, cy, r, ACCENT, cx, cy, circ, round(circ * (1 - pct), 2), circ, round(circ * (1 - pct), 2))
    )
    out.append(
        '<text x="%d" y="%d" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
        'font-size="30" font-weight="700" fill="%s" opacity="1">'
        '<animate attributeName="opacity" values="0;0;1" keyTimes="0;0.45;1" dur="1.6s" fill="freeze"/>%s</text>'
        % (cx, cy + 11, TEXT, letter)
    )
    out.append("</svg>")
    return "\n".join(out)


def langs_card(d: dict) -> str:
    w, h = 480, 200
    langs = d["langs"][:7]
    total = sum(size for _, size, _ in langs) or 1
    out = [shell(w, h, "Most used languages", "Most used languages")]

    bx, by, bw, bh = 25, 58, w - 50, 11
    out.append('<clipPath id="bar"><rect x="%d" y="%d" width="%d" height="%d" rx="5.5"/></clipPath>' % (bx, by, bw, bh))
    out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="5.5" fill="#161b22"/>' % (bx, by, bw, bh))
    out.append('<g clip-path="url(#bar)">')
    x = bx
    for i, (name, size, colour) in enumerate(langs):
        seg = bw * size / total
        out.append(
            '<rect x="%s" y="%d" width="%s" height="%d" fill="%s">'
            '<animate attributeName="width" values="0;%s" dur="0.9s" begin="%ss" fill="freeze" '
            'calcMode="spline" keySplines="0.16 0.8 0.24 1"/></rect>'
            % (round(x, 2), by, round(seg, 2), bh, colour, round(seg, 2), round(0.2 + i * 0.07, 2))
        )
        x += seg
    out.append("</g>")

    for i, (name, size, colour) in enumerate(langs):
        col, row = i % 2, i // 2
        lx = 25 + col * 220
        ly = 100 + row * 24
        pct = 100.0 * size / total
        out.append('<g opacity="1">%s' % reveal(0.35 + i * 0.07))
        out.append('<circle cx="%d" cy="%d" r="5" fill="%s"/>' % (lx + 5, ly - 4, colour))
        out.append(
            '<text x="%d" y="%d" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
            'font-size="12.5" fill="%s">%s</text>' % (lx + 18, ly, TEXT, esc(name))
        )
        out.append(
            '<text x="%d" y="%d" text-anchor="end" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
            'font-size="12" fill="%s">%.1f%%</text>' % (lx + 200, ly, MUTED, pct)
        )
        out.append("</g>")

    out.append("</svg>")
    return "\n".join(out)


def achievements_card(d: dict) -> str:
    w, h = 900, 118
    tiles = [
        ("Commits", d["commits"], "#58a6ff"),
        ("Stars", d["stars"], "#f0883e"),
        ("Pull requests", d["prs"], "#d2a8ff"),
        ("Issues", d["issues"], "#7ee787"),
        ("Repositories", d["repos"], "#79c0ff"),
        ("Followers", d["followers"], "#ff7b72"),
    ]
    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-label="GitHub highlights">' % (w, h, w, h),
        "<title>GitHub highlights</title>",
        '<defs><linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#ffffff" stop-opacity="0"/>'
        '<stop offset="0.5" stop-color="#ffffff" stop-opacity="0.06"/>'
        '<stop offset="1" stop-color="#ffffff" stop-opacity="0"/></linearGradient>'
        '<clipPath id="card"><rect x="0" y="0" width="%d" height="%d" rx="12"/></clipPath></defs>' % (w, h),
        '<rect x="0.5" y="0.5" width="%d" height="%d" rx="12" fill="%s" stroke="%s"/>' % (w - 1, h - 1, BG, EDGE),
    ]

    tw, gap = 134, 12
    x0 = (w - (tw * len(tiles) + gap * (len(tiles) - 1))) / 2
    for i, (label, value, colour) in enumerate(tiles):
        tx = x0 + i * (tw + gap)
        out.append('<g opacity="1">%s' % reveal(0.12 + i * 0.08, -6))
        out.append('<rect x="%s" y="22" width="%d" height="74" rx="10" fill="#111823" stroke="#1f2836"/>' % (round(tx, 2), tw))
        out.append('<rect x="%s" y="22" width="%d" height="3" rx="1.5" fill="%s"/>' % (round(tx + 18, 2), tw - 36, colour))
        out.append(
            '<text x="%s" y="62" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
            'font-size="21" font-weight="700" fill="%s">%s</text>' % (round(tx + tw / 2, 2), TEXT, fmt(value))
        )
        out.append(
            '<text x="%s" y="81" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
            'font-size="10.5" letter-spacing="1.1" fill="%s">%s</text>' % (round(tx + tw / 2, 2), MUTED, esc(label.upper()))
        )
        out.append("</g>")

    out.append(
        '<g clip-path="url(#card)"><rect x="-320" y="0" width="320" height="%d" fill="url(#shine)">'
        '<animateTransform attributeName="transform" type="translate" values="0 0;%d 0" dur="6s" '
        'begin="1.2s" repeatCount="indefinite"/></rect></g>' % (h, w + 640)
    )
    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------- main --
def main() -> None:
    ap = argparse.ArgumentParser(description="Render self-hosted GitHub stat cards")
    ap.add_argument("--user", help="GitHub username")
    ap.add_argument("--out-dir", default="assets")
    ap.add_argument("--demo", action="store_true", help="use sample numbers, no network")
    args = ap.parse_args()

    if args.demo:
        data = DEMO
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("set GH_TOKEN (or pass --demo)")
        if not args.user:
            raise SystemExit("pass --user <github-name>")
        data = fetch(token, args.user)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "stats-card.svg": stats_card(data),
        "langs-card.svg": langs_card(data),
        "achievements.svg": achievements_card(data),
    }
    for name, svg in files.items():
        (out / name).write_text(svg, encoding="utf-8")
        print("wrote %s (%.1f KB)" % (out / name, (out / name).stat().st_size / 1024))


if __name__ == "__main__":
    main()
