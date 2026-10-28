"""Generate the numbers strip (dark + light), private team repos included.

Run:  GH_TOKEN=<token with repo + read:user> python .github/stats.py  -> writes assets/numbers-*.svg
"""
import base64
import json
import os
import urllib.error
import urllib.request
from datetime import date, timedelta
from html import escape
from pathlib import Path

USER = "Hesyitena"
OUT = Path(__file__).resolve().parents[1] / "assets"
HIDE = {"Jupyter Notebook"}
EXCLUDE = ["Hesyitena/github-activity"]  # backdated commits from an activity generator, not real work

# SVGs have no background, so they sit on GitHub's own page colour in either theme
THEMES = {
    "dark": dict(text="#f0f3f6", muted="#8b939d", line="#252c35", accent="#ff5a4e"),
    "light": dict(text="#111214", muted="#6b7078", line="#e3e5e8", accent="#e5372b"),
}
FONTS = Path(__file__).resolve().parent / "fonts"
SANS = "Grot, 'Helvetica Neue', Arial, sans-serif"
MONO = "GrotMono, ui-monospace, Consolas, monospace"
FACES = {  # file -> @font-face descriptors
    "grotesk": "font-family:Grot;font-weight:400",
    "grotesk-medium": "font-family:Grot;font-weight:500",
    "grotesk-heavy": "font-family:Grot;font-weight:800",
    "mono": "font-family:GrotMono",
}


def font_style(*names):
    """<style> embedding the given fonts; GitHub won't load external fonts inside SVG images."""
    css = "".join(
        f'@font-face{{{FACES[n]};src:url(data:font/woff;base64,'
        f'{base64.b64encode((FONTS / f"{n}.woff").read_bytes()).decode()}) format("woff")}}'
        for n in names
    )
    return f"<style>{css}{MOTION}</style>"


# entry animations; GitHub plays them once per page load. Off for people who ask for reduced motion.
MOTION = ("@keyframes up{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:none}}"
          "@keyframes grow{from{transform:scaleX(0)}to{transform:none}}"
          "@keyframes rise{from{transform:scaleY(0)}to{transform:none}}"
          ".up{animation:up .7s cubic-bezier(.2,.7,.2,1) both}"
          ".grow{transform-box:fill-box;transform-origin:left center;animation:grow .9s cubic-bezier(.2,.7,.2,1) both}"
          ".rise{transform-box:fill-box;transform-origin:center bottom;animation:rise .6s cubic-bezier(.2,.7,.2,1) both}"
          "@media (prefers-reduced-motion:reduce){.up,.grow,.rise{animation:none}}")


def delay(s):
    return f' style="animation-delay:{s:.2f}s"'

LANGS = "languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }"
# ponytail: first 100 repos each, paginate if either list ever outgrows that
QUERY = f"""{{ user(login: "{USER}") {{
  contributionsCollection {{ contributionYears }}
  repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {{ nodes {{ nameWithOwner {LANGS} }} }}
  repositoriesContributedTo(first: 100, includeUserRepositories: false,
      contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW]) {{ nodes {{ nameWithOwner {LANGS} }} }}
}} }}"""
# the API caps one contributionsCollection at a year, so all-time = one aliased collection per year
YEAR = """y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") {{
    contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }}
    totalCommitContributions totalPullRequestContributions totalPullRequestReviewContributions
    commitContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner }} contributions {{ totalCount }} }}
  }}"""


def gql(query):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}"},
    )
    body = json.load(urllib.request.urlopen(req))
    if "errors" in body:
        raise SystemExit(body["errors"])
    return body["data"]["user"]


def fetch():
    """Repos plus all-time totals and a merged day-by-day calendar (oldest first)."""
    d = gql(QUERY)
    years = d["contributionsCollection"]["contributionYears"]
    ys = gql(f'{{ user(login: "{USER}") {{ {" ".join(YEAR.format(y=y) for y in years)} }} }}').values()
    keys = ["totalCommitContributions", "totalPullRequestContributions", "totalPullRequestReviewContributions"]
    d["totals"] = {k: sum(y[k] for y in ys) for k in keys}
    d["totals"]["contributions"] = sum(y["contributionCalendar"]["totalContributions"] for y in ys)
    # calendar weeks can spill over year boundaries and past today; keep the max per date, drop the future
    days, today = {}, date.today().isoformat()
    for y in ys:
        for w in y["contributionCalendar"]["weeks"]:
            for x in w["contributionDays"]:
                if x["date"] <= today:
                    days[x["date"]] = max(days.get(x["date"], 0), x["contributionCount"])
    d["days"] = days
    # repos whose commits GitHub already put on the calendar, so we neither add nor subtract them twice
    d["counted"] = {}
    for y in ys:
        for r in y["commitContributionsByRepository"]:
            name = r["repository"]["nameWithOwner"]
            d["counted"][name] = d["counted"].get(name, 0) + r["contributions"]["totalCount"]
    return d


def commits_per_day(repo, author=None):
    """{YYYY-MM-DD (UTC, authored): commits} on the default branch; a deleted or empty repo is {}."""
    counts = {}
    url = f"https://api.github.com/repos/{repo}/commits?per_page=100" + (f"&author={author}" if author else "")
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


def merge(days, counted, team, per_day):
    """Fold team commits GitHub left off the calendar into it, and take generator commits out.

    days: {date: n} from the calendar. counted: {repo: commits GitHub counted}. team: repos contributed to.
    per_day(repo, author) -> {date: n}. Returns (days oldest first with no gaps, commits added).
    """
    days, added = dict(days), 0
    for repo in EXCLUDE:  # only what GitHub actually counted can be taken back out
        if counted.get(repo):
            for day, n in per_day(repo, USER).items():
                if day in days:
                    days[day] = max(days[day] - n, 0)
            added -= counted[repo]
    for repo in team:
        if repo in counted or repo in EXCLUDE:
            continue
        for day, n in per_day(repo, USER).items():
            days[day] = days.get(day, 0) + n
            added += n
    # ponytail: commit days are UTC while the calendar uses your timezone, so a late-night commit can land a day off
    today = date.today()
    first = date.fromisoformat(min(days)) if days else today
    full = [(first + timedelta(i)).isoformat() for i in range((today - first).days + 1)]
    return [(d, days.get(d, 0)) for d in full], added


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
    for i, (_, n) in enumerate(days):
        if n and start is None:
            start = i
        if not n and start is not None:
            runs.append((i - start, start, i - 1))
            start = None
    if start is not None:
        runs.append((len(days) - start, start, len(days) - 1))
    last = len(days) - 1 - (days[-1][1] == 0)
    cur = next(((n, a, b) for n, a, b in runs if b == last), (0, None, None))
    best = max(runs, default=(0, None, None))
    as_dates = lambda r: (r[0], *(days[i][0] if i is not None else None for i in r[1:]))
    return as_dates(cur), as_dates(best)


def span(r):
    if not r[0]:
        return "none yet"
    a, b = (date.fromisoformat(x) for x in r[1:])
    fmt = lambda d: f"{d:%b} {d.day}"
    return fmt(a) if a == b else f"{fmt(a)} – {fmt(b)}"


def numbers(t, totals, share, days):
    """Figures and a language bar on top; streaks and a year of weekly contributions below."""
    c, W, H = THEMES[t], 1600, 380
    rows = [("contributions", totals["contributions"]), ("commits", totals["totalCommitContributions"]),
            ("pull requests", totals["totalPullRequestContributions"])]
    s = []
    for i, (x, (k, v)) in enumerate(zip((0, 290, 580), rows)):
        s.append(f'<g class="up"{delay(0.1 * i)}>'
                 f'<text x="{x}" y="70" font-family="{SANS}" font-weight="800" font-size="64" fill="{c["text"]}">{v:,}</text>'
                 f'<text x="{x}" y="108" font-family="{MONO}" font-size="20" letter-spacing="1.5" fill="{c["muted"]}">{k.upper()}</text></g>')
    x = 800.0
    for i, (_, p) in enumerate(share):
        w = 800 * p / 100
        fill, op = (c["accent"], 1) if i == 0 else (c["text"], max(0.18, 1 - i * 0.16))
        s.append(f'<rect class="grow"{delay(0.3 + 0.12 * i)} x="{x:.1f}" y="44" width="{max(w - 4, 1):.1f}" height="10" fill="{fill}" opacity="{op:.2f}"/>')
        x += w
    names = "   ".join(f"{'JS' if n == 'JavaScript' else escape(n)} {p:.1f}" for n, p in share if n != "Other")
    s.append(f'<text class="up"{delay(0.8)} x="800" y="96" xml:space="preserve" font-family="{MONO}" font-size="22" fill="{c["muted"]}">{names}</text>')
    s.append(f'<rect class="grow"{delay(0.5)} x="0" y="149" width="1600" height="2" fill="{c["line"]}"/>')

    cur, best = streaks(days)
    unit = lambda n: "day" if n == 1 else "days"
    for i, (x, (k, r)) in enumerate(zip((0, 290), (("current streak", cur), ("longest streak", best)))):
        s.append(f'<g class="up"{delay(0.7 + 0.1 * i)}>'
                 f'<text x="{x}" y="232" font-family="{SANS}" font-weight="800" font-size="64" fill="{c["text"]}">{r[0]}'
                 f'<tspan dx="10" font-family="{MONO}" font-weight="400" font-size="22" fill="{c["muted"]}">{unit(r[0])}</tspan></text>'
                 f'<text x="{x}" y="270" font-family="{MONO}" font-size="20" letter-spacing="1.5" fill="{c["muted"]}">{k.upper()}</text>'
                 f'<text x="{x}" y="302" font-family="{MONO}" font-size="18" fill="{c["muted"]}">{span(r)}</text></g>')

    recent = [n for _, n in days[-364:]]
    weekly = [sum(recent[i:i + 7]) for i in range(0, len(recent), 7)]
    x0, top, base = 800, 176, 290
    bw, peak = 800 / max(len(weekly), 1), max(weekly, default=0) or 1
    for i, v in enumerate(weekly):
        if not v:
            continue
        h = max((base - top) * v / peak, 3)
        fill = c["accent"] if i == len(weekly) - 1 else c["text"]
        s.append(f'<rect class="rise"{delay(0.8 + 0.012 * i)} x="{x0 + i * bw + bw * 0.2:.1f}" y="{base - h:.1f}" '
                 f'width="{bw * 0.6:.1f}" height="{h:.1f}" fill="{fill}"/>')
    s.append(f'<rect x="{x0}" y="{base + 1}" width="800" height="2" fill="{c["line"]}"/>')
    s.append(f'<text class="up"{delay(1.2)} x="{x0}" y="322" font-family="{MONO}" font-size="18" fill="{c["muted"]}">CONTRIBUTIONS PER WEEK, PAST YEAR</text>')
    s.append(f'<text class="up"{delay(1.2)} x="1600" y="322" text-anchor="end" font-family="{MONO}" font-size="18" fill="{c["muted"]}">PEAK {max(weekly, default=0):,}</text>')
    s.append(f'<text class="up"{delay(1.3)} x="0" y="370" font-family="{MONO}" font-size="20" fill="{c["muted"]}">All time, team repos included.</text>')
    label = ("All time, team repos included: " + ", ".join(f"{v} {k}" for k, v in rows)
             + ". Languages: " + ", ".join(f"{n} {p:.1f}%" for n, p in share)
             + f". Current streak {cur[0]} {unit(cur[0])} ({span(cur)}); longest {best[0]} {unit(best[0])} ({span(best)}).")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{escape(label)}">\n'
            f'{font_style("grotesk-heavy", "mono")}\n' + "\n".join(s) + "\n</svg>")


if __name__ == "__main__":
    assert streaks([("a", 1), ("b", 0), ("c", 2), ("d", 3), ("e", 0)]) == ((2, "c", "d"), (2, "c", "d"))
    assert streaks([("a", 0), ("b", 0)]) == ((0, None, None), (0, None, None))
    fake = {"team/a": {"2026-01-02": 3}, EXCLUDE[0]: {"2026-01-01": 5}}
    m, n = merge({"2026-01-01": 2}, {"own/x": 2}, ["team/a", "own/x"], lambda r, a: fake.get(r, {}))
    assert n == 3 and m[:3] == [("2026-01-01", 2), ("2026-01-02", 3), ("2026-01-03", 0)], (n, m[:3])  # uncounted generator: no cut
    m, n = merge({"2026-01-01": 6}, {EXCLUDE[0]: 5}, [], lambda r, a: fake.get(r, {}))
    assert n == -5 and m[0] == ("2026-01-01", 1)

    d = fetch()
    team = d["repositoriesContributedTo"]["nodes"]
    days, added = merge(d["days"], d["counted"], [r["nameWithOwner"] for r in team], commits_per_day)
    d["totals"]["contributions"] += added
    d["totals"]["totalCommitContributions"] += added
    print("commits added from team repos, net of excluded:", added)
    share = lang_share(d["repositories"]["nodes"] + team)
    assert not share or abs(sum(p for _, p in share) - 100) < 0.01, share
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"numbers-{theme}.svg").write_text(numbers(theme, d["totals"], share, days), encoding="utf-8", newline="\n")
    print("ok:", share)
