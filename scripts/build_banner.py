#!/usr/bin/env python3
"""Renders assets/banner.svg with live numbers from the GitHub API.

Run by the profile workflow once a day. Works offline too: without a token it
falls back to assets/stats.json from the previous run.

    GITHUB_TOKEN=... python scripts/build_banner.py
"""
import base64
import json
import math
import os
import random
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LOGIN = "quueli"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STATS_FILE = ASSETS / "stats.json"
AVATAR_FILE = ASSETS / "avatar.jpg"
OUT = ASSETS / "banner.svg"

STACK_LINE = "PYTHON  ·  AIOGRAM  ·  TELETHON  ·  FASTAPI  ·  TYPESCRIPT  ·  PHP  ·  DOCKER"


def graphql(query, variables, token):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": "bearer " + token, "Content-Type": "application/json",
                 "User-Agent": "profile-banner"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def fetch_stats(token):
    base = graphql(
        """
        query($login: String!) {
          user(login: $login) {
            createdAt
            contributionsCollection { contributionYears }
            repositories(first: 100, privacy: PUBLIC, ownerAffiliations: [OWNER], isFork: false) {
              totalCount
              nodes { primaryLanguage { name } }
            }
          }
        }
        """,
        {"login": LOGIN},
        token,
    )["user"]

    commits = 0
    for year in base["contributionsCollection"]["contributionYears"]:
        span = graphql(
            """
            query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  totalCommitContributions
                  restrictedContributionsCount
                }
              }
            }
            """,
            {"login": LOGIN, "from": f"{year}-01-01T00:00:00Z", "to": f"{year}-12-31T23:59:59Z"},
            token,
        )["user"]["contributionsCollection"]
        commits += span["totalCommitContributions"] + span["restrictedContributionsCount"]

    languages = {n["primaryLanguage"]["name"] for n in base["repositories"]["nodes"] if n["primaryLanguage"]}
    return {
        "commits": commits,
        "repos": base["repositories"]["totalCount"],
        "languages": len(languages),
        "since": datetime.fromisoformat(base["createdAt"].replace("Z", "+00:00")).year,
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def load_stats():
    token = os.environ.get("GITHUB_TOKEN")
    cached = json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {}
    if token:
        try:
            stats = fetch_stats(token)
            # the workflow token only sees public activity, and a commit count
            # never really goes down, so keep the higher number
            stats["commits"] = max(stats["commits"], cached.get("commits", 0))
            STATS_FILE.write_text(json.dumps(stats, indent=2) + "\n")
            return stats
        except Exception as e:  # noqa: BLE001 - keep the old numbers rather than fail the workflow
            print("api failed, using cached stats:", e, file=sys.stderr)
    if STATS_FILE.exists():
        return json.loads(STATS_FILE.read_text())
    return {"commits": 0, "repos": 0, "languages": 0, "since": 2025, "updated": "never"}


def fmt(n):
    return f"{n:,}".replace(",", " ")


def stars(rnd, n, w, h, rmin, rmax, twinkle_every=0):
    out = []
    for i in range(n):
        x, y = round(rnd.uniform(0, w), 1), round(rnd.uniform(0, h), 1)
        r, o = round(rnd.uniform(rmin, rmax), 2), round(rnd.uniform(0.25, 0.9), 2)
        if twinkle_every and i % twinkle_every == 0:
            dur, beg = round(rnd.uniform(2.6, 5.2), 1), round(rnd.uniform(0, 4), 1)
            out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#eae6ff" opacity="{o}">'
                       f'<animate attributeName="opacity" values="{o};{max(0.12, o - 0.55):.2f};{o}" '
                       f'dur="{dur}s" begin="{beg}s" repeatCount="indefinite"/></circle>')
        else:
            out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#cfc7ef" opacity="{o * 0.55:.2f}"/>')
    return "".join(out)


def burst(rnd, cx, cy):
    out = []
    for _ in range(40):
        a = rnd.uniform(0.55, 2.35)
        length, r0 = rnd.uniform(30, 120), rnd.uniform(96, 108)
        x1, y1 = cx + math.cos(a) * r0, cy - math.sin(a) * r0
        x2, y2 = cx + math.cos(a) * (r0 + length), cy - math.sin(a) * (r0 + length)
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#b7a9ef" '
                   f'stroke-width="{rnd.uniform(0.5, 1.4):.2f}" opacity="{rnd.uniform(0.12, 0.5):.2f}" stroke-linecap="round"/>')
    for _ in range(70):
        a, d = rnd.uniform(0, 2 * math.pi), 95 + abs(rnd.gauss(0, 60))
        x, y = cx + math.cos(a) * d, cy - abs(math.sin(a)) * d * 0.9
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rnd.uniform(0.4, 1.3):.2f}" fill="#efe9ff" opacity="{rnd.uniform(0.2, 0.8):.2f}"/>')
    return "".join(out)


def render(stats):
    w, h = 1280, 340
    rnd = random.Random(7)
    avatar = base64.b64encode(AVATAR_FILE.read_bytes()).decode()
    ax, ay, ar = 190, 170, 82

    blocks = [
        (fmt(stats["commits"]), "COMMITS"),
        (fmt(stats["repos"]), "PUBLIC REPOS"),
        (str(stats["languages"]), "LANGUAGES"),
        (str(stats["since"]), "ACTIVE SINCE"),
    ]
    x0, step = 400, 200
    stat_svg = ""
    for i, (value, label) in enumerate(blocks):
        x = x0 + i * step
        stat_svg += (f'<text x="{x}" y="176" font-size="46" font-weight="700" fill="#f3efff">{value}</text>'
                     f'<text x="{x + 1}" y="204" font-size="12" font-weight="600" fill="#8981b4" letter-spacing="2.4">{label}</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="GitHub activity: {stats["commits"]} commits, {stats["repos"]} public repositories">
  <defs>
    <radialGradient id="bg" cx="18%" cy="45%" r="95%">
      <stop offset="0%" stop-color="#1b1c3c"/>
      <stop offset="42%" stop-color="#101127"/>
      <stop offset="100%" stop-color="#080912"/>
    </radialGradient>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#efe9ff" stop-opacity="0.9"/>
      <stop offset="30%" stop-color="#b9a9f0" stop-opacity="0.45"/>
      <stop offset="65%" stop-color="#6f5fb2" stop-opacity="0.14"/>
      <stop offset="100%" stop-color="#6f5fb2" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#8f83d6"/>
      <stop offset="55%" stop-color="#d8ccf6"/>
      <stop offset="100%" stop-color="#e7b9cf"/>
    </linearGradient>
    <linearGradient id="divider" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#8b7fd0" stop-opacity="0"/>
      <stop offset="50%" stop-color="#8b7fd0" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="#8b7fd0" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="avatar"><circle cx="{ax}" cy="{ay}" r="{ar}"/></clipPath>
    <filter id="soft" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="28"/></filter>
  </defs>

  <rect width="{w}" height="{h}" fill="url(#bg)"/>
  {stars(rnd, 140, w, h, 0.3, 0.9)}
  <circle cx="{ax + 40}" cy="{ay - 50}" r="190" fill="url(#glow)" filter="url(#soft)">
    <animate attributeName="opacity" values="0.8;1;0.8" dur="6s" repeatCount="indefinite"/>
  </circle>
  {burst(rnd, ax, ay)}
  {stars(rnd, 55, w, h, 0.6, 1.6, twinkle_every=3)}

  <circle cx="{ax}" cy="{ay}" r="{ar + 9}" fill="none" stroke="#8f83d6" stroke-width="1" opacity="0.35"/>
  <image href="data:image/jpeg;base64,{avatar}" x="{ax - ar}" y="{ay - ar}" width="{ar * 2}" height="{ar * 2}" clip-path="url(#avatar)" preserveAspectRatio="xMidYMid slice"/>
  <circle cx="{ax}" cy="{ay}" r="{ar}" fill="none" stroke="url(#ring)" stroke-width="2.5"/>

  <rect x="336" y="96" width="1.5" height="150" fill="url(#divider)"/>

  <g font-family="'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
    {stat_svg}
    <text x="{x0 + 1}" y="262" font-size="14" font-weight="500" fill="#a89ed0" letter-spacing="2.6">{STACK_LINE}</text>
  </g>
</svg>
'''


def main():
    stats = load_stats()
    OUT.write_text(render(stats), encoding="utf-8")
    print("banner:", stats)


if __name__ == "__main__":
    main()
