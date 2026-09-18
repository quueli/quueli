#!/usr/bin/env python3
"""Renders assets/banner.svg: the last year of commits as a star map plus a weekly pulse line.

Run daily by the profile workflow. The contribution calendar is cached in
assets/calendar.json and merged per day (max), so a token that sees less
than the previous run never makes the picture emptier.

    GITHUB_TOKEN=... python scripts/build_banner.py
"""
import base64
import json
import math
import os
import random
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOGIN = "quueli"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CAL_FILE = ASSETS / "calendar.json"
AVATAR_FILE = ASSETS / "avatar.jpg"
OUT = ASSETS / "banner.svg"

W, H = 1280, 340
AX, AY, AR = 190, 170, 82      # avatar
X0, X1 = 380, 1236             # chart span


def fetch_calendar(token):
    to = datetime.now(timezone.utc).replace(microsecond=0)
    frm = to - timedelta(days=365)
    q = """query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){
      contributionsCollection(from:$from,to:$to){ contributionCalendar{
        weeks{ contributionDays{ date contributionCount } } } } } }"""
    body = json.dumps({"query": q, "variables": {"login": LOGIN, "from": frm.isoformat().replace("+00:00", "Z"),
                                                 "to": to.isoformat().replace("+00:00", "Z")}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body,
                                 headers={"Authorization": "bearer " + token, "Content-Type": "application/json",
                                          "User-Agent": "profile-banner"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {d["date"]: d["contributionCount"] for w in weeks for d in w["contributionDays"]}


def load_days():
    cached = json.loads(CAL_FILE.read_text()) if CAL_FILE.exists() else {}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        try:
            fresh = fetch_calendar(token)
            merged = {d: max(c, cached.get(d, 0)) for d, c in fresh.items()}
            CAL_FILE.write_text(json.dumps(merged, indent=0, sort_keys=True) + "\n")
            return merged
        except Exception as e:  # noqa: BLE001
            print("api failed, using cached calendar:", e, file=sys.stderr)
    return cached


def weeks_of(days):
    dates = sorted(days)
    if not dates:
        return []
    first = datetime.fromisoformat(dates[0]).date()
    first -= timedelta(days=(first.weekday() + 1) % 7)   # back to sunday
    weeks, cur = [], []
    d = first
    last = datetime.fromisoformat(dates[-1]).date()
    while d <= last:
        cur.append(days.get(d.isoformat(), 0))
        if len(cur) == 7:
            weeks.append(cur)
            cur = []
        d += timedelta(days=1)
    if cur:
        weeks.append(cur + [0] * (7 - len(cur)))
    return weeks


def bg_stars(rnd, n, rmin, rmax, twinkle_every=0):
    out = []
    for i in range(n):
        x, y = round(rnd.uniform(0, W), 1), round(rnd.uniform(0, H), 1)
        r, o = round(rnd.uniform(rmin, rmax), 2), round(rnd.uniform(0.2, 0.8), 2)
        if twinkle_every and i % twinkle_every == 0:
            out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#eae6ff" opacity="{o}">'
                       f'<animate attributeName="opacity" values="{o};{max(0.1, o - 0.5):.2f};{o}" '
                       f'dur="{rnd.uniform(2.6, 5.2):.1f}s" begin="{rnd.uniform(0, 4):.1f}s" repeatCount="indefinite"/></circle>')
        else:
            out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#cfc7ef" opacity="{o * 0.5:.2f}"/>')
    return "".join(out)


def burst(rnd, cx, cy):
    out = []
    for _ in range(40):
        a = rnd.uniform(0.55, 2.35)
        length, r0 = rnd.uniform(30, 120), rnd.uniform(96, 108)
        out.append(f'<line x1="{cx + math.cos(a) * r0:.1f}" y1="{cy - math.sin(a) * r0:.1f}" '
                   f'x2="{cx + math.cos(a) * (r0 + length):.1f}" y2="{cy - math.sin(a) * (r0 + length):.1f}" '
                   f'stroke="#b7a9ef" stroke-width="{rnd.uniform(0.5, 1.4):.2f}" opacity="{rnd.uniform(0.12, 0.5):.2f}" stroke-linecap="round"/>')
    for _ in range(70):
        a, d = rnd.uniform(0, 2 * math.pi), 95 + abs(rnd.gauss(0, 60))
        out.append(f'<circle cx="{cx + math.cos(a) * d:.1f}" cy="{cy - abs(math.sin(a)) * d * 0.9:.1f}" '
                   f'r="{rnd.uniform(0.4, 1.3):.2f}" fill="#efe9ff" opacity="{rnd.uniform(0.2, 0.8):.2f}"/>')
    return "".join(out)


def constellation(rnd, weeks, y0=62, rowh=19):
    n = len(weeks)
    step = (X1 - X0) / max(n - 1, 1)
    mx = max((c for w in weeks for c in w), default=1) or 1
    out, bright = [], []
    for wi, w in enumerate(weeks):
        for di, c in enumerate(w):
            x = X0 + wi * step + rnd.uniform(-3, 3)
            y = y0 + di * rowh + rnd.uniform(-4, 4)
            if c == 0:
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="0.7" fill="#8b84b8" opacity="0.3"/>')
                continue
            t = math.sqrt(c / mx)
            r = 1.7 + 5.5 * t
            o = 0.6 + 0.4 * t
            if t > 0.3:
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 3.4:.1f}" fill="url(#sg)" opacity="{0.4 + 0.45 * t:.2f}"/>')
            if t > 0.42:
                bright.append((x, y))
            tw = ""
            if t > 0.25 and rnd.random() < 0.5:
                tw = (f'<animate attributeName="opacity" values="{o};{max(0.35, o - 0.4):.2f};{o}" '
                      f'dur="{rnd.uniform(2.5, 5):.1f}s" begin="{rnd.uniform(0, 4):.1f}s" repeatCount="indefinite"/>')
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="#f6f3ff" opacity="{o:.2f}">{tw}</circle>')
    bright.sort()
    for (x1, y1), (x2, y2) in zip(bright, bright[1:]):
        if x2 - x1 < 130:
            out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#d3c8f5" stroke-width="0.9" opacity="0.32"/>')
    return "".join(out)


def pulse(rnd, weeks, base=296, height=96):
    totals = [sum(w) for w in weeks]
    if len(totals) > 1:
        totals = totals[:-1]        # the current week is not over yet
    mx = max(totals) or 1
    n = len(totals)
    step = (X1 - X0) / max(n - 1, 1)
    pts = [(X0 + i * step, base - math.log1p(t) / math.log1p(mx) * height) for i, t in enumerate(totals)]

    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    area = d + f" L{pts[-1][0]:.1f},{base} L{X0:.1f},{base} Z"
    top = sorted(totals)[-6] if len(totals) >= 6 else 0
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#f6f3ff">'
                   f'<animate attributeName="opacity" values="1;0.5;1" dur="{rnd.uniform(2, 4):.1f}s" repeatCount="indefinite"/></circle>'
                   for (x, y), t in zip(pts, totals) if t >= top and t > 0)
    return (f'<path d="{area}" fill="url(#area)"/>'
            f'<path d="{d}" fill="none" stroke="#b9a9f0" stroke-width="8" opacity="0.4" filter="url(#blur6)"/>'
            f'<path d="{d}" fill="none" stroke="url(#line)" stroke-width="2.4" stroke-linecap="round"/>'
            f'<line x1="{X0}" y1="{base}" x2="{X1}" y2="{base}" stroke="#8b7fd0" stroke-width="0.6" opacity="0.25"/>' + dots)


def render(weeks):
    rnd = random.Random(7)
    avatar = base64.b64encode(AVATAR_FILE.read_bytes()).decode()
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="a year of commits drawn as a star map">
  <defs>
    <radialGradient id="bg" cx="18%" cy="45%" r="95%"><stop offset="0%" stop-color="#1b1c3c"/><stop offset="42%" stop-color="#101127"/><stop offset="100%" stop-color="#080912"/></radialGradient>
    <radialGradient id="glow" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#efe9ff" stop-opacity="0.9"/><stop offset="30%" stop-color="#b9a9f0" stop-opacity="0.45"/><stop offset="65%" stop-color="#6f5fb2" stop-opacity="0.14"/><stop offset="100%" stop-color="#6f5fb2" stop-opacity="0"/></radialGradient>
    <radialGradient id="sg" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#f3efff" stop-opacity="1"/><stop offset="40%" stop-color="#c9bdf2" stop-opacity="0.55"/><stop offset="100%" stop-color="#8b7fd0" stop-opacity="0"/></radialGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#8f83d6"/><stop offset="55%" stop-color="#d8ccf6"/><stop offset="100%" stop-color="#e7b9cf"/></linearGradient>
    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#b9a9f0" stop-opacity="0.35"/><stop offset="100%" stop-color="#6f5fb2" stop-opacity="0"/></linearGradient>
    <linearGradient id="line" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#8f83d6"/><stop offset="60%" stop-color="#d8ccf6"/><stop offset="100%" stop-color="#f3efff"/></linearGradient>
    <clipPath id="avatar"><circle cx="{AX}" cy="{AY}" r="{AR}"/></clipPath>
    <filter id="soft" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="28"/></filter>
    <filter id="blur6" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  {bg_stars(rnd, 140, 0.3, 0.9)}
  <circle cx="{AX + 40}" cy="{AY - 50}" r="190" fill="url(#glow)" filter="url(#soft)"><animate attributeName="opacity" values="0.8;1;0.8" dur="6s" repeatCount="indefinite"/></circle>
  {burst(rnd, AX, AY)}
  {bg_stars(rnd, 55, 0.6, 1.6, 3)}
  <circle cx="{AX}" cy="{AY}" r="{AR + 9}" fill="none" stroke="#8f83d6" stroke-width="1" opacity="0.35"/>
  <image href="data:image/jpeg;base64,{avatar}" x="{AX - AR}" y="{AY - AR}" width="{AR * 2}" height="{AR * 2}" clip-path="url(#avatar)" preserveAspectRatio="xMidYMid slice"/>
  <circle cx="{AX}" cy="{AY}" r="{AR}" fill="none" stroke="url(#ring)" stroke-width="2.5"/>
  {pulse(random.Random(5), weeks)}
  {constellation(random.Random(3), weeks)}
</svg>
'''


def main():
    days = load_days()
    weeks = weeks_of(days)
    if not weeks:
        sys.exit("no calendar data")
    OUT.write_text(render(weeks), encoding="utf-8")
    print(f"banner: {len(weeks)} weeks, {sum(days.values())} contributions, {sum(1 for v in days.values() if v)} active days")


if __name__ == "__main__":
    main()
