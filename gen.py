"""Generate the static dark/light SVGs for the profile README (header, work index).

Run:  python gen.py   -> writes assets/{header,work}-*.svg
The numbers strip comes from .github/stats.py, run nightly by the workflow.
"""
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".github"))
from stats import MONO, SANS, THEMES, font_style  # noqa: E402  shared fonts and colours

OUT = Path(__file__).parent / "assets"

META = [("ROLE", "Computer engineering student"), ("SCHOOL", "PENS, Surabaya"),
        ("TEAM", "PENSHIP, programming division"), ("TIME", "UTC+7")]
WORK = [  # (project, stack) - most of these live in private team repos
    ("Autonomous vehicle software", "ROS 2, computer vision"),
    ("Web ground control station", "React, TypeScript"),
    ("IoT monitoring system", "Embedded, web dashboard"),
    ("PENSHIP team website", "React"),
    ("GerakPulih, physiotherapy app", "Flutter"),
]


def svg(w, h, label, fonts, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(label)}">\n'
            f'{font_style(*fonts)}\n' + "\n".join(body) + "\n</svg>")


def header(t):
    c = THEMES[t]
    s = [f'<rect width="1600" height="6" fill="{c["text"]}"/>',
         f'<text x="-6" y="236" font-family="{SANS}" font-weight="800" font-size="210" letter-spacing="-9" fill="{c["text"]}">Alek</text>',
         # x measured from the font's advances for "Alek" at this size; re-measure if the name changes
         f'<rect x="456" y="196" width="28" height="28" fill="{c["accent"]}"/>']
    for i, (k, v) in enumerate(META):
        y = 90 + 60 * i
        s.append(f'<text x="880" y="{y}" font-family="{MONO}" font-size="21" letter-spacing="1.5" fill="{c["muted"]}">{k}</text>')
        s.append(f'<text x="1040" y="{y + 1}" font-family="{SANS}" font-weight="500" font-size="29" fill="{c["text"]}">{escape(v)}</text>')
        s.append(f'<line x1="880" y1="{y + 22}" x2="1600" y2="{y + 22}" stroke="{c["line"]}" stroke-width="2"/>')
    s.append(f'<text x="0" y="354" font-family="{SANS}" font-size="36" fill="{c["text"]}">I build robotics software, web dashboards and mobile apps.</text>')
    s.append(f'<text x="0" y="402" font-family="{SANS}" font-size="36" fill="{c["muted"]}">Most of it lives in private team repositories.</text>')
    label = "Alek. " + "; ".join(f"{k.lower()}: {v}" for k, v in META) + \
            ". I build robotics software, web dashboards and mobile apps. Most of it lives in private team repositories."
    return svg(1600, 440, label, ["grotesk", "grotesk-medium", "grotesk-heavy", "mono"], s)


def work(t):
    c = THEMES[t]
    s = [f'<text x="{x}" y="34" font-family="{MONO}" font-size="20" letter-spacing="1.5" fill="{c["muted"]}"{a}>{k}</text>'
         for k, x, a in [("NO.", 0, ""), ("PROJECT", 110, ""), ("STACK", 900, ""), ("REPO", 1600, ' text-anchor="end"')]]
    s.append(f'<line x1="0" y1="54" x2="1600" y2="54" stroke="{c["text"]}" stroke-width="2.5"/>')
    for k, (name, stack) in enumerate(WORK):
        y = 54 + 68 * k
        s.append(f'<text x="0" y="{y + 46}" font-family="{MONO}" font-size="22" fill="{c["muted"]}">{k + 1:02d}</text>')
        s.append(f'<text x="110" y="{y + 46}" font-family="{SANS}" font-weight="500" font-size="31" fill="{c["text"]}">{escape(name)}</text>')
        s.append(f'<text x="900" y="{y + 46}" font-family="{SANS}" font-size="28" fill="{c["muted"]}">{escape(stack)}</text>')
        s.append(f'<text x="1600" y="{y + 46}" text-anchor="end" font-family="{MONO}" font-size="21" fill="{c["muted"]}">private</text>')
        s.append(f'<line x1="0" y1="{y + 68}" x2="1600" y2="{y + 68}" stroke="{c["line"]}" stroke-width="2"/>')
    label = "Work, private team repos: " + "; ".join(f"{n} ({st})" for n, st in WORK)
    return svg(1600, 54 + 68 * len(WORK) + 6, label, ["grotesk", "grotesk-medium", "mono"], s)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"header-{theme}.svg").write_text(header(theme), encoding="utf-8", newline="\n")
        (OUT / f"work-{theme}.svg").write_text(work(theme), encoding="utf-8", newline="\n")
    print("ok:", sorted(p.name for p in OUT.iterdir()))
