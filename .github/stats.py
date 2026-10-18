"""Generate stats/langs/streak SVG cards (dark + light) that include private team repos.

Run:  GH_TOKEN=<token with repo + read:user> python .github/stats.py  -> writes assets/{stats,langs,streak}-*.svg
"""
import base64
import json
import os
import urllib.error
import urllib.request
from datetime import date
from html import escape
from pathlib import Path

USER = "Hesyitena"
OUT = Path(__file__).resolve().parents[1] / "assets"
HIDE = {"Jupyter Notebook"}
EXCLUDE = ["Hesyitena/github-activity"]  # backdated commits from an activity generator, not real work

THEMES = {
    "dark": dict(panel="#0d1117", frame="#30363d", panel_line="#21262d", text="#e6edf3",
                 muted="#7d8590", accent="#e3b341", live="#3fb950",
                 langs=["#e3b341", "#58a6ff", "#3fb950", "#db6d28", "#a371f7"]),
    "light": dict(panel="#ffffff", frame="#d0d7de", panel_line="#d8dee4", text="#1f2328",
                  muted="#656d76", accent="#9a6700", live="#1a7f37",
                  langs=["#9a6700", "#0969da", "#1a7f37", "#bc4c00", "#8250df"]),
}
FONTS = Path(__file__).resolve().parent / "fonts"
SERIF = "Chart, Georgia, serif"
MONO = "ChartMono, ui-monospace, Consolas, monospace"
FACES = {  # file -> @font-face descriptors
    "serif": "font-family:Chart;font-style:normal;font-weight:400",
    "serif-italic": "font-family:Chart;font-style:italic;font-weight:400",
    "serif-display": "font-family:Chart;font-style:italic;font-weight:600",
    "mono": "font-family:ChartMono",
}


def font_style(*names):
    """<style> embedding the given fonts; GitHub won't load external fonts inside SVG images."""
    css = "".join(
        f'@font-face{{{FACES[n]};src:url(data:font/woff;base64,'
        f'{base64.b64encode((FONTS / f"{n}.woff").read_bytes()).decode()}) format("woff")}}'
        for n in names
    )
    return f"<style>{css}</style>"

LANGS = "languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }"
# ponytail: first 100 repos each, paginate if either list ever outgrows that
QUERY = f"""{{ user(login: "{USER}") {{
  contributionsCollection {{
    contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }}
    totalCommitContributions totalPullRequestContributions totalPullRequestReviewContributions
  }}
  repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {{ nodes {{ nameWithOwner {LANGS} }} }}
  repositoriesContributedTo(first: 100, includeUserRepositories: false,
      contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW]) {{ nodes {{ nameWithOwner {LANGS} }} }}
}} }}"""


def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY}).encode(),
        headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}"},
    )
    body = json.load(urllib.request.urlopen(req))
    if "errors" in body:
        raise SystemExit(body["errors"])
    return body["data"]["user"]


def excluded_per_day():
    """{YYYY-MM-DD (UTC, authored): commits} across EXCLUDE; a deleted repo just counts as zero."""
    counts = {}
    for repo in EXCLUDE:
        url = f"https://api.github.com/repos/{repo}/commits?per_page=100"
        while url:
            req = urllib.request.Request(url, headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}"})
            try:
                resp = urllib.request.urlopen(req)
            except urllib.error.HTTPError as e:
                if e.code in (404, 409):  # gone, or empty repo
                    break
                raise
            for cm in json.load(resp):
                day = cm["commit"]["author"]["date"][:10]
                counts[day] = counts.get(day, 0) + 1
            nxt = [p for p in resp.headers.get("Link", "").split(",") if 'rel="next"' in p]
            url = nxt[0][nxt[0].index("<") + 1:nxt[0].index(">")] if nxt else None
    return counts


def lang_share(repos, top=5):
    """[(name, percent)] by bytes across unique repos; the tail is folded into 'Other'."""
    seen, sizes = set(), {}
    for r in repos:
        if r["nameWithOwner"] in seen:
            continue
        seen.add(r["nameWithOwner"])
        for e in r["languages"]["edges"]:
            if e["node"]["name"] not in HIDE:
                sizes[e["node"]["name"]] = sizes.get(e["node"]["name"], 0) + e["size"]
    total = sum(sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: -kv[1])
    out = [(n, 100 * s / total) for n, s in ranked[:top]]
    rest = sum(s for _, s in ranked[top:])
    if rest:
        out.append(("Other", 100 * rest / total))
    return out


def streaks(days):
    """days: [(date, count)] oldest first -> ((len, start, end) current, (len, start, end) longest).

    A zero today doesn't break the current streak yet; the day isn't over.
    """
    runs, start = [], None
    for i, (day, n) in enumerate(days):
        if n and start is None:
            start = i
        if not n and start is not None:
            runs.append((i - start, start, i - 1)); start = None
    if start is not None:
        runs.append((len(days) - start, start, len(days) - 1))
    last = len(days) - 1 - (days[-1][1] == 0)
    cur = next(((n, a, b) for n, a, b in runs if b == last), (0, None, None))
    best = max(runs, default=(0, None, None))
    as_dates = lambda r: (r[0], *(days[i][0] if i is not None else None for i in r[1:]))
    return as_dates(cur), as_dates(best)


def frame(c, w, h, title, label, s, fonts):
    s.insert(0, f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(label)}">\n'
                f'{font_style(*fonts)}\n'
                f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="12" fill="{c["panel"]}" stroke="{c["frame"]}" stroke-width="2"/>\n'
                f'<text x="48" y="66" font-family="{SERIF}" font-style="italic" font-size="30" fill="{c["text"]}">{title}</text>\n'
                f'<line x1="48" y1="92" x2="{w-48}" y2="92" stroke="{c["panel_line"]}" stroke-width="2"/>')
    s.append("</svg>")
    return "\n".join(s)


def stats_card(t, d, n_team):
    c, W, H = THEMES[t], 800, 380
    cc = d["contributionsCollection"]
    rows = [
        ("contributions", cc["contributionCalendar"]["totalContributions"]),
        ("commits", cc["totalCommitContributions"]),
        ("pull requests", cc["totalPullRequestContributions"]),
        ("reviews", cc["totalPullRequestReviewContributions"]),
        ("team repositories", n_team),
    ]
    s, y = [], 150
    for k, v in rows:
        # dotted leader between label and figure, like a printed table
        s.append(f'<line x1="{48 + 13 * len(k) + 16}" y1="{y - 2}" x2="{W - 48 - 18 * len(f"{v:,}") - 16}" y2="{y - 2}" '
                 f'stroke="{c["frame"]}" stroke-width="2" stroke-dasharray="2 8" stroke-linecap="round"/>')
        s.append(f'<text x="48" y="{y}" font-family="{SERIF}" font-style="italic" font-size="26" fill="{c["muted"]}">{k}</text>')
        s.append(f'<text x="{W-48}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="28" fill="{c["text"]}">{v:,}</text>')
        y += 50
    label = "The last twelve months, private team repos included: " + ", ".join(f"{k} {v}" for k, v in rows)
    return frame(c, W, H, "the last twelve months", label, s, ["serif-italic", "mono"])


def langs_card(t, share):
    c, W, H = THEMES[t], 800, 380
    colors = c["langs"] + [c["muted"]]
    s = [f'<defs><clipPath id="bar"><rect x="48" y="128" width="{W-96}" height="12" rx="6"/></clipPath></defs>',
         '<g clip-path="url(#bar)">']
    x = 48.0
    for i, (_, p) in enumerate(share):
        w = (W - 96) * p / 100
        s.append(f'<rect x="{x:.1f}" y="128" width="{w + 0.5:.1f}" height="12" fill="{colors[i]}"/>')
        x += w
    s.append("</g>")
    for i, (name, p) in enumerate(share):
        cx, y = 48 + (i // 3) * 368, 214 + (i % 3) * 56
        s.append(f'<circle cx="{cx + 7}" cy="{y - 8}" r="7" fill="{colors[i]}"/>')
        s.append(f'<text x="{cx + 28}" y="{y}" font-family="{SERIF}" font-size="26" fill="{c["text"]}">{escape(name)}</text>')
        s.append(f'<text x="{cx + 336}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="22" fill="{c["muted"]}">{p:.1f}%</text>')
    label = "Languages across own and team repos: " + ", ".join(f"{n} {p:.1f}%" for n, p in share)
    return frame(c, W, H, "languages, own and team repos", label, s, ["serif", "serif-italic", "mono"])


def streak_card(t, days, weekly):
    c, W, H = THEMES[t], 1600, 300
    cur, best = streaks(days)

    def span(r):
        if not r[0]:
            return "none yet"
        a, b = (date.fromisoformat(x) for x in r[1:])
        fmt = lambda d: f"{d:%b} {d.day}"
        return fmt(a) if a == b else f"{fmt(a)} – {fmt(b)}"

    days_word = lambda n: "day" if n == 1 else "days"
    s = []
    for x, (k, r) in ((48, ("current streak", cur)), (400, ("longest, past year", best))):
        s.append(f'<text x="{x}" y="148" font-family="{SERIF}" font-style="italic" font-size="26" fill="{c["muted"]}">{k}</text>')
        s.append(f'<text x="{x}" y="222" font-family="{MONO}" font-size="68" fill="{c["text"]}">{r[0]}'
                 f'<tspan dx="14" font-family="{SERIF}" font-style="italic" font-size="28" fill="{c["muted"]}">'
                 f'{days_word(r[0])}</tspan></text>')
        s.append(f'<text x="{x}" y="260" font-family="{MONO}" font-size="20" fill="{c["muted"]}">{span(r)}</text>')
    # weekly totals as a tide-gauge strip; this week in accent
    x0, x1, top, base = 780, W - 48, 120, 236
    bw, peak = (x1 - x0) / len(weekly), max(weekly) or 1
    for i, v in enumerate(weekly):
        h = max((base - top) * v / peak, 2 if v else 0)
        fill = c["accent"] if i == len(weekly) - 1 else c["muted"]
        s.append(f'<rect x="{x0 + i * bw + bw * 0.2:.1f}" y="{base - h:.1f}" width="{bw * 0.6:.1f}" height="{h:.1f}" fill="{fill}"'
                 f'{"" if i == len(weekly) - 1 else " fill-opacity=\"0.55\""}/>')
    s.append(f'<line x1="{x0}" y1="{base + 1}" x2="{x1}" y2="{base + 1}" stroke="{c["frame"]}" stroke-width="2"/>')
    s.append(f'<text x="{x0}" y="268" font-family="{SERIF}" font-style="italic" font-size="22" fill="{c["muted"]}">contributions per week</text>')
    s.append(f'<text x="{x1}" y="268" text-anchor="end" font-family="{MONO}" font-size="18" fill="{c["muted"]}">peak {peak:,}</text>')
    label = (f"Current streak {cur[0]} {days_word(cur[0])} ({span(cur)}); "
             f"longest in the past year {best[0]} {days_word(best[0])} ({span(best)}).")
    return frame(c, W, H, "streaks", label, s, ["serif-italic", "mono"])


if __name__ == "__main__":
    assert streaks([("a", 1), ("b", 0), ("c", 2), ("d", 3), ("e", 0)]) == ((2, "c", "d"), (2, "c", "d"))
    assert streaks([("a", 0), ("b", 0)]) == ((0, None, None), (0, None, None))
    d = fetch()
    cc = d["contributionsCollection"]
    gen = excluded_per_day()
    weeks = [[(x["date"], max(x["contributionCount"] - gen.get(x["date"], 0), 0)) for x in w["contributionDays"]]
             for w in cc["contributionCalendar"]["weeks"]]
    days = [x for w in weeks for x in w]
    weekly = [sum(n for _, n in w) for w in weeks]
    # ponytail: assumes every excluded commit counted on the calendar (default branch, own email)
    removed = cc["contributionCalendar"]["totalContributions"] - sum(n for _, n in days)
    cc["contributionCalendar"]["totalContributions"] -= removed
    cc["totalCommitContributions"] -= removed
    print("excluded:", removed)
    team = d["repositoriesContributedTo"]["nodes"]
    share = lang_share(d["repositories"]["nodes"] + team)
    assert not share or abs(sum(p for _, p in share) - 100) < 0.01, share
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"stats-{theme}.svg").write_text(stats_card(theme, d, len(team)), encoding="utf-8", newline="\n")
        (OUT / f"langs-{theme}.svg").write_text(langs_card(theme, share), encoding="utf-8", newline="\n")
        (OUT / f"streak-{theme}.svg").write_text(streak_card(theme, days, weekly), encoding="utf-8", newline="\n")
    print("ok:", share)
