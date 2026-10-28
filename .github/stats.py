"""Generate the numbers strip (dark + light), private team repos included.

Run:  GH_TOKEN=<token with repo + read:user> python .github/stats.py  -> writes assets/numbers-*.svg
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
          ".up{animation:up .7s cubic-bezier(.2,.7,.2,1) both}"
          ".grow{transform-box:fill-box;transform-origin:left center;animation:grow .9s cubic-bezier(.2,.7,.2,1) both}"
          "@media (prefers-reduced-motion:reduce){.up,.grow{animation:none}}")


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
    d["days"] = sorted(days.items())
    return d


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


def numbers(t, totals, share):
    """Three figures on the left, a thin language bar on the right."""
    c, W, H = THEMES[t], 1600, 210
    rows = [("contributions", totals["contributions"]), ("commits", totals["totalCommitContributions"]),
            ("pull requests", totals["totalPullRequestContributions"])]
    s = []
    for i, (x, (k, v)) in enumerate(zip((0, 250, 470), rows)):
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
    s.append(f'<text class="up"{delay(0.9)} x="0" y="190" font-family="{MONO}" font-size="20" fill="{c["muted"]}">All time, team repos included.</text>')
    label = ("All time, private team repos included: " + ", ".join(f"{v} {k}" for k, v in rows)
             + ". Languages: " + ", ".join(f"{n} {p:.1f}%" for n, p in share))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{escape(label)}">\n'
            f'{font_style("grotesk-heavy", "mono")}\n' + "\n".join(s) + "\n</svg>")


if __name__ == "__main__":
    d = fetch()
    gen = excluded_per_day()
    # ponytail: assumes every excluded commit counted on the calendar (default branch, own email)
    removed = sum(min(n, gen.get(day, 0)) for day, n in d["days"])
    d["totals"]["contributions"] -= removed
    d["totals"]["totalCommitContributions"] -= removed
    print("excluded:", removed)
    share = lang_share(d["repositories"]["nodes"] + d["repositoriesContributedTo"]["nodes"])
    assert not share or abs(sum(p for _, p in share) - 100) < 0.01, share
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"numbers-{theme}.svg").write_text(numbers(theme, d["totals"], share), encoding="utf-8", newline="\n")
    print("ok:", share)
