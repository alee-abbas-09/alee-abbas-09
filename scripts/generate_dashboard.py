#!/usr/bin/env python3
"""
generate_dashboard.py
----------------------
Builds a fully custom, hand-designed SVG "mission control" dashboard for a
GitHub profile, using REAL data pulled straight from the GitHub API.

Unlike third-party badge services (github-readme-stats, streak-stats, etc.)
that render the exact same template for every user on the planet, this
script and its visual design belong entirely to this repository — so the
result is unique to this profile.

Env vars (set automatically by the GitHub Actions workflow):
  GITHUB_TOKEN     - auth token (Actions provides this for free)
  GH_USERNAME       - the GitHub username to report on

Output:
  assets/dashboard.svg
"""

import os
import sys
import json
import datetime
import urllib.request

USERNAME = os.environ.get("GH_USERNAME", "alee-abbas-09")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "dashboard.svg")

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        primaryLanguage { name color }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { contributionCount date }
        }
      }
    }
  }
}
"""


def gh_graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "custom-dashboard-generator",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_streaks(days):
    """days: chronological list of {contributionCount, date}."""
    current = 0
    longest = 0
    running = 0
    n = len(days)
    for i, d in enumerate(days):
        if d["contributionCount"] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    # current streak: walk backwards, allow today to be 0 (day not finished yet)
    i = n - 1
    if i >= 0 and days[i]["contributionCount"] == 0:
        i -= 1
    while i >= 0 and days[i]["contributionCount"] > 0:
        current += 1
        i -= 1
    return current, longest


def fallback_data():
    """Used if the API call fails (e.g. missing token during local testing)."""
    return {
        "followers": 0,
        "repos": 0,
        "stars": 0,
        "contributions": 0,
        "current_streak": 0,
        "longest_streak": 0,
        "languages": [("Python", "#3776AB", 1.0)],
        "weekly": [0] * 12,
    }


def fetch_data():
    if not TOKEN:
        return fallback_data()
    try:
        result = gh_graphql(QUERY, {"login": USERNAME})
        user = result["data"]["user"]

        repos = user["repositories"]["nodes"]
        total_repos = user["repositories"]["totalCount"]
        stars = sum(r["stargazerCount"] for r in repos)

        lang_count = {}
        for r in repos:
            lang = r.get("primaryLanguage")
            if lang:
                key = lang["name"]
                lang_count.setdefault(key, {"color": lang["color"] or "#8b949e", "count": 0})
                lang_count[key]["count"] += 1
        total_lang = sum(v["count"] for v in lang_count.values()) or 1
        languages = sorted(
            [(name, v["color"], v["count"] / total_lang) for name, v in lang_count.items()],
            key=lambda x: -x[2],
        )[:5]

        cal = user["contributionsCollection"]["contributionCalendar"]
        all_days = []
        for w in cal["weeks"]:
            all_days.extend(w["contributionDays"])
        current_streak, longest_streak = compute_streaks(all_days)

        # last 12 weeks totals for the pulse strip
        weekly = []
        for w in cal["weeks"][-12:]:
            weekly.append(sum(d["contributionCount"] for d in w["contributionDays"]))

        return {
            "followers": user["followers"]["totalCount"],
            "repos": total_repos,
            "stars": stars,
            "contributions": cal["totalContributions"],
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "languages": languages or [("Python", "#3776AB", 1.0)],
            "weekly": weekly or [0] * 12,
        }
    except Exception as e:  # noqa: BLE001
        print(f"[generate_dashboard] API call failed, using fallback: {e}", file=sys.stderr)
        return fallback_data()


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_svg(data):
    W, H = 900, 500
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tiles = [
        ("STARS", data["stars"], "#f2cc60"),
        ("REPOS", data["repos"], "#48CAE4"),
        ("FOLLOWERS", data["followers"], "#7ee787"),
        ("CONTRIBUTIONS", data["contributions"], "#f97583"),
    ]
    tile_w, tile_h, gap = 190, 92, 20
    tiles_svg = ""
    for i, (label, value, color) in enumerate(tiles):
        x = 40 + i * (tile_w + gap)
        tiles_svg += f"""
        <g transform="translate({x},96)">
          <rect width="{tile_w}" height="{tile_h}" rx="12" fill="#121826" stroke="#233156" stroke-width="1.4"/>
          <rect x="0" y="0" width="5" height="{tile_h}" rx="2.5" fill="{color}"/>
          <text x="22" y="38" fill="#e8f7ff" font-family="Arial" font-size="30" font-weight="800">{value}</text>
          <text x="22" y="66" fill="#8b93ab" font-family="Arial" font-size="13" letter-spacing="1">{label}</text>
        </g>"""

    # streak gauge (circular progress out of a 30-day reference scale)
    radius = 54
    circumference = 2 * 3.14159265 * radius
    pct = min(data["current_streak"] / 30.0, 1.0)
    dash = circumference * pct

    # language bars
    lang_svg = ""
    for i, (name, color, frac) in enumerate(data["languages"]):
        y = i * 34
        bar_w = max(6, frac * 260)
        lang_svg += f"""
        <g transform="translate(0,{y})">
          <text x="0" y="14" fill="#c9d1d9" font-family="Arial" font-size="13">{esc(name)}</text>
          <rect x="0" y="20" width="260" height="8" rx="4" fill="#1b2233"/>
          <rect x="0" y="20" width="{bar_w:.1f}" height="8" rx="4" fill="{color}"/>
          <text x="270" y="28" fill="#8b93ab" font-family="Arial" font-size="12">{frac*100:.0f}%</text>
        </g>"""

    # 12-week contribution pulse
    weekly = data["weekly"]
    max_w = max(weekly) if max(weekly) > 0 else 1
    pulse_svg = ""
    bar_w2 = 22
    for i, v in enumerate(weekly):
        h = 6 + (v / max_w) * 64
        x = i * (bar_w2 + 6)
        pulse_svg += (
            f'<rect x="{x}" y="{78-h:.1f}" width="{bar_w2}" height="{h:.1f}" rx="3" '
            f'fill="#48CAE4" opacity="{0.35 + 0.65*(v/max_w):.2f}"/>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0b0f1f"/>
    <stop offset="1" stop-color="#0d1226"/>
  </linearGradient>
</defs>
<rect width="{W}" height="{H}" rx="18" fill="url(#bg)" stroke="#233156" stroke-width="1.4"/>

<text x="40" y="46" fill="#e8f7ff" font-family="Arial" font-size="22" font-weight="800">LIVE GITHUB DASHBOARD</text>
<text x="40" y="68" fill="#6b7690" font-family="Consolas,monospace" font-size="13">@{esc(USERNAME)} · auto-updated {now}</text>

{tiles_svg}

<!-- streak gauge -->
<g transform="translate(120,300)">
  <circle r="{radius}" fill="none" stroke="#1b2233" stroke-width="10"/>
  <circle r="{radius}" fill="none" stroke="#48CAE4" stroke-width="10"
    stroke-dasharray="{dash:.1f} {circumference:.1f}" stroke-linecap="round"
    transform="rotate(-90)"/>
  <text x="0" y="-4" text-anchor="middle" fill="#e8f7ff" font-family="Arial" font-size="26" font-weight="800">{data['current_streak']}</text>
  <text x="0" y="18" text-anchor="middle" fill="#8b93ab" font-family="Arial" font-size="12">DAY STREAK</text>
</g>
<text x="120" y="386" text-anchor="middle" fill="#6b7690" font-family="Arial" font-size="12">longest: {data['longest_streak']} days</text>

<!-- languages -->
<g transform="translate(280,222)">
  <text x="0" y="0" fill="#8b93ab" font-family="Arial" font-size="13" letter-spacing="1">TOP LANGUAGES</text>
  <g transform="translate(0,16)">
    {lang_svg}
  </g>
</g>

<!-- 12-week pulse -->
<g transform="translate(620,222)">
  <text x="0" y="0" fill="#8b93ab" font-family="Arial" font-size="13" letter-spacing="1">12-WEEK PULSE</text>
  <g transform="translate(0,20)">
    {pulse_svg}
  </g>
</g>
</svg>"""
    return svg


def main():
    data = fetch_data()
    svg = render_svg(data)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"[generate_dashboard] wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
