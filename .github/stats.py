"""Generate stats/langs SVG cards (dark + light) that include private team repos.

Run:  GH_TOKEN=<token with repo + read:user> python .github/stats.py  -> writes assets/{stats,langs}-*.svg
"""
import json
import os
import urllib.request
from html import escape
from pathlib import Path

USER = "Hesyitena"
OUT = Path(__file__).resolve().parents[1] / "assets"
HIDE = {"Jupyter Notebook"}

THEMES = {
    "dark": dict(panel="#0d1117", frame="#30363d", panel_line="#21262d", text="#e6edf3",
                 muted="#7d8590", accent="#e3b341", live="#3fb950",
                 langs=["#e3b341", "#58a6ff", "#3fb950", "#db6d28", "#a371f7"]),
    "light": dict(panel="#ffffff", frame="#d0d7de", panel_line="#d8dee4", text="#1f2328",
                  muted="#656d76", accent="#9a6700", live="#1a7f37",
                  langs=["#9a6700", "#0969da", "#1a7f37", "#bc4c00", "#8250df"]),
}
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

LANGS = "languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }"
# ponytail: first 100 repos each, paginate if either list ever outgrows that
QUERY = f"""{{ user(login: "{USER}") {{
  contributionsCollection {{
    contributionCalendar {{ totalContributions }}
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


def frame(c, w, h, title, label, s):
    s.insert(0, f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(label)}">\n'
                f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="12" fill="{c["panel"]}" stroke="{c["frame"]}" stroke-width="2"/>\n'
                f'<text x="48" y="64" font-family="{MONO}" font-size="20" letter-spacing="4" fill="{c["muted"]}">{title}</text>\n'
                f'<line x1="48" y1="92" x2="{w-48}" y2="92" stroke="{c["panel_line"]}" stroke-width="2"/>')
    s.append("</svg>")
    return "\n".join(s)


def stats_card(t, d, n_team):
    c, W, H = THEMES[t], 800, 380
    cc = d["contributionsCollection"]
    rows = [
        ("CONTRIB", cc["contributionCalendar"]["totalContributions"]),
        ("COMMITS", cc["totalCommitContributions"]),
        ("PULLS", cc["totalPullRequestContributions"]),
        ("REVIEWS", cc["totalPullRequestReviewContributions"]),
        ("TEAM REPOS", n_team),
    ]
    s, y = [], 148
    for k, v in rows:
        s.append(f'<text x="48" y="{y}" font-family="{MONO}" font-size="21" letter-spacing="3" fill="{c["accent"]}">{k}</text>')
        s.append(f'<text x="{W-48}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="26" fill="{c["text"]}">{v:,}</text>')
        y += 50
    label = "Last 12 months, private team repos included: " + ", ".join(f"{k.lower()} {v}" for k, v in rows)
    return frame(c, W, H, "LOG / LAST 12 MONTHS", label, s)


def langs_card(t, share):
    c, W, H = THEMES[t], 800, 380
    colors = c["langs"] + [c["muted"]]
    s = [f'<defs><clipPath id="bar"><rect x="48" y="128" width="{W-96}" height="16" rx="8"/></clipPath></defs>',
         '<g clip-path="url(#bar)">']
    x = 48.0
    for i, (_, p) in enumerate(share):
        w = (W - 96) * p / 100
        s.append(f'<rect x="{x:.1f}" y="128" width="{w + 0.5:.1f}" height="16" fill="{colors[i]}"/>')
        x += w
    s.append("</g>")
    for i, (name, p) in enumerate(share):
        cx, y = 48 + (i // 3) * 368, 214 + (i % 3) * 56
        s.append(f'<circle cx="{cx + 8}" cy="{y - 9}" r="8" fill="{colors[i]}"/>')
        s.append(f'<text x="{cx + 30}" y="{y}" font-family="{MONO}" font-size="24" fill="{c["text"]}">{escape(name)}</text>')
        s.append(f'<text x="{cx + 336}" y="{y}" text-anchor="end" font-family="{MONO}" font-size="22" fill="{c["muted"]}">{p:.1f}%</text>')
    label = "Languages across own and team repos: " + ", ".join(f"{n} {p:.1f}%" for n, p in share)
    return frame(c, W, H, "LANGS / OWN + TEAM REPOS", label, s)


if __name__ == "__main__":
    d = fetch()
    team = d["repositoriesContributedTo"]["nodes"]
    share = lang_share(d["repositories"]["nodes"] + team)
    assert not share or abs(sum(p for _, p in share) - 100) < 0.01, share
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"stats-{theme}.svg").write_text(stats_card(theme, d, len(team)), encoding="utf-8")
        (OUT / f"langs-{theme}.svg").write_text(langs_card(theme, share), encoding="utf-8")
    print("ok:", share)
