"""Generate the static dark/light SVGs for the profile README (header, work index).

Run:  python gen.py   -> writes assets/{header,work}-*.svg
The numbers strip comes from .github/stats.py, run nightly by the workflow.
"""
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".github"))
from stats import MONO, SANS, THEMES, delay, font_style  # noqa: E402  shared fonts, colours, motion

OUT = Path(__file__).parent / "assets"

META = [("ROLE", "Computer engineering student"), ("SCHOOL", "PENS, Surabaya"),
        ("TEAM", "PENSHIP, programming division"), ("TIME", "UTC+7")]
WORK = [  # (project, stack)
    ("Autonomous vehicle software", "ROS 2, computer vision"),
    ("Web ground control station", "React, TypeScript"),
    ("IoT monitoring system", "Embedded, web dashboard"),
    ("PENSHIP team website", "React"),
    ("GerakPulih, physiotherapy app", "Flutter"),
    ("Shiftwheel, radial file converter", "Rust, Tauri"),
]
PREFIX = "I build "
PHRASES = ["robotics software for autonomous vehicles", "web ground control stations",
           "IoT monitoring dashboards", "mobile apps in Flutter"]
WINDOW = 4.0  # seconds each phrase owns: type, hold, erase


def svg(w, h, label, fonts, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{escape(label)}">\n'
            f'{font_style(*fonts)}\n' + "\n".join(body) + "\n</svg>")


def frames(k, n, cw):
    """[(seconds, revealed width)] for phrase k: type it out, hold, erase."""
    s, dt, de = k * WINDOW, min(0.06, 2.4 / n), 0.45 / n
    erase = s + WINDOW - 0.7
    return [(s + i * dt, i * cw) for i in range(n + 1)] + [(erase + j * de, (n - j) * cw) for j in range(n + 1)]


def discrete(attr, fr, total):
    """SMIL step animation; SMIL rather than CSS because it animates clip paths in every browser."""
    fr = [(0.0, fr[0][1] if fr[0][0] == 0 else 0)] + fr + [(total, fr[-1][1])]
    keys = {}
    for t, v in fr:  # same rounded time -> later value wins
        keys[round(t / total, 4)] = v
    kt, vals = zip(*sorted(keys.items()))
    return (f'<animate attributeName="{attr}" dur="{total:g}s" repeatCount="indefinite" calcMode="discrete" '
            f'keyTimes="{";".join(f"{t:g}" for t in kt)}" values="{";".join(f"{v:.1f}" for v in vals)}"/>')


def typer(c, x0, y, size):
    cw, total = size * 0.6, WINDOW * len(PHRASES)  # mono advance is 600/1000 em
    px = x0 + len(PREFIX) * cw
    s = [f'<text x="{x0}" y="{y}" xml:space="preserve" font-family="{MONO}" font-size="{size}" fill="{c["muted"]}">{PREFIX}</text>']
    cursor = []
    for k, p in enumerate(PHRASES):
        fr = frames(k, len(p), cw)
        cursor += fr
        s.append(f'<clipPath id="p{k}"><rect x="{px:.1f}" y="{y - size}" width="0" height="{size * 1.4:.0f}">'
                 f'{discrete("width", fr, total)}</rect></clipPath>')
        s.append(f'<text clip-path="url(#p{k})" x="{px:.1f}" y="{y}" font-family="{MONO}" font-size="{size}" fill="{c["text"]}">{escape(p)}</text>')
    s.append(f'<rect x="{px:.1f}" y="{y - size * 0.82:.1f}" width="4" height="{size:.0f}" fill="{c["accent"]}">'
             f'{discrete("x", [(t, px + w) for t, w in cursor], total)}'
             '<animate attributeName="opacity" values="1;0" dur="1s" calcMode="discrete" repeatCount="indefinite"/></rect>')
    return s


def header(t):
    c = THEMES[t]
    s = [f'<rect class="grow" width="1600" height="6" fill="{c["text"]}"/>',
         f'<text class="up"{delay(0.1)} x="-6" y="236" font-family="{SANS}" font-weight="800" font-size="210" letter-spacing="-9" fill="{c["text"]}">Alek</text>',
         # x measured from the font's advances for "Alek" at this size; re-measure if the name changes
         f'<rect class="up"{delay(0.45)} x="456" y="196" width="28" height="28" fill="{c["accent"]}"/>']
    for i, (k, v) in enumerate(META):
        y = 90 + 60 * i
        s.append(f'<g class="up"{delay(0.25 + 0.08 * i)}>'
                 f'<text x="880" y="{y}" font-family="{MONO}" font-size="21" letter-spacing="1.5" fill="{c["muted"]}">{k}</text>'
                 f'<text x="1040" y="{y + 1}" font-family="{SANS}" font-weight="500" font-size="29" fill="{c["text"]}">{escape(v)}</text>'
                 f'<line x1="880" y1="{y + 22}" x2="1600" y2="{y + 22}" stroke="{c["line"]}" stroke-width="2"/></g>')
    s.append(f'<g class="up"{delay(0.7)}>')
    s += typer(c, 0, 354, 34)
    s.append("</g>")
    label = "Alek. " + "; ".join(f"{k.lower()}: {v}" for k, v in META) + ". I build " + ", ".join(PHRASES) + "."
    return svg(1600, 390, label, ["grotesk-medium", "grotesk-heavy", "mono"], s)


def work(t):
    c = THEMES[t]
    s = [f'<text x="{x}" y="34" font-family="{MONO}" font-size="20" letter-spacing="1.5" fill="{c["muted"]}"{a}>{k}</text>'
         for k, x, a in [("NO.", 0, ""), ("PROJECT", 110, ""), ("STACK", 1600, ' text-anchor="end"')]]
    s.append(f'<rect class="grow" x="0" y="53" width="1600" height="2.5" fill="{c["text"]}"/>')
    for k, (name, stack) in enumerate(WORK):
        y = 54 + 68 * k
        s.append(f'<g class="up"{delay(0.15 + 0.09 * k)}>'
                 f'<text x="0" y="{y + 46}" font-family="{MONO}" font-size="22" fill="{c["muted"]}">{k + 1:02d}</text>'
                 f'<text x="110" y="{y + 46}" font-family="{SANS}" font-weight="500" font-size="31" fill="{c["text"]}">{escape(name)}</text>'
                 f'<text x="1600" y="{y + 46}" text-anchor="end" font-family="{SANS}" font-size="28" fill="{c["muted"]}">{escape(stack)}</text>'
                 f'<line x1="0" y1="{y + 68}" x2="1600" y2="{y + 68}" stroke="{c["line"]}" stroke-width="2"/></g>')
    label = "Work: " + "; ".join(f"{n} ({st})" for n, st in WORK)
    return svg(1600, 54 + 68 * len(WORK) + 6, label, ["grotesk", "grotesk-medium", "mono"], s)


if __name__ == "__main__":
    assert frames(0, 4, 10)[0] == (0, 0) and frames(0, 4, 10)[4][1] == 40 and frames(1, 4, 10)[-1][1] == 0
    assert max(t for t, _ in frames(len(PHRASES) - 1, max(map(len, PHRASES)), 1)) < WINDOW * len(PHRASES)
    OUT.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT / f"header-{theme}.svg").write_text(header(theme), encoding="utf-8", newline="\n")
        (OUT / f"work-{theme}.svg").write_text(work(theme), encoding="utf-8", newline="\n")
    print("ok:", sorted(p.name for p in OUT.iterdir()))
