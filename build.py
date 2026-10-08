#!/usr/bin/env python3
"""Build Nord for Cider from one token table.

Outputs (next to this file):
  main.css            base: semantic tokens for Cider's dark AND light appearance + all component rules
  accent-<slug>.css   stackable accent overrides (enable one on top of the base)
  aurora.css          stackable "varied palette" layer (works with any accent, both appearances)
  theme.yml           ThemeKit manifest
  preview/*.css       same CSS with !important appended (what ThemeKit does), for live CDP previews

Component rules only reference semantic tokens; raw Nord colours live in the token table.
The build fails if any text/fill pair misses its WCAG contrast target.
"""
import pathlib
import re
import sys

VERSION = "1.1.0"
HERE = pathlib.Path(__file__).resolve().parent

NORD = {
    0: "#2e3440", 1: "#3b4252", 2: "#434c5e", 3: "#4c566a",
    4: "#d8dee9", 5: "#e5e9f0", 6: "#eceff4",
    7: "#8fbcbb", 8: "#88c0d0", 9: "#81a1c1", 10: "#5e81ac",
    11: "#bf616a", 12: "#d08770", 13: "#ebcb8b", 14: "#a3be8c", 15: "#b48ead",
}

# ---------------------------------------------------------------- colour maths
def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def hexc(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in c)

def mix(a, b, t):
    """t=0 -> a, t=1 -> b (sRGB)."""
    ra, rb = rgb(a), rgb(b)
    return hexc(tuple(ra[i] + (rb[i] - ra[i]) * t for i in range(3)))

def lum(h):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

def nudge(color, toward, bg, target):
    """Smallest mix of `color` toward `toward` that reaches `target` contrast on `bg`."""
    for i in range(0, 101):
        c = mix(color, toward, i / 100)
        if contrast(c, bg) >= target:
            return c
    raise SystemExit(f"cannot reach {target}:1 for {color} on {bg}")

def nudge_all(color, toward, bgs, target):
    """Like nudge, but the result must clear `target` on every background in `bgs`."""
    for i in range(0, 101):
        c = mix(color, toward, i / 100)
        if all(contrast(c, bg) >= target for bg in bgs):
            return c
    raise SystemExit(f"cannot reach {target}:1 for {color} on {bgs}")

def text_bgs(s):
    """Surfaces coloured text actually sits on."""
    return [s["bg-base"], s["bg-mantle"], s["surface-1"], s["bg-crust"]]

def fill_and_on(color, mode):
    """Accent fill + its text colour. Keep the hue as intact as possible: try Polar Night
    text (lightening the fill if needed) and Snow Storm text (darkening it), take the
    option that moves the fill least. Ties go to the mode's natural choice."""
    best = None
    for on, toward in ((NORD[0], NORD[6]), (NORD[6], NORD[0])):
        for i in range(0, 101):
            f = mix(color, toward, i / 100)
            if contrast(f, on) >= 4.5:
                pref = 0 if (on == NORD[0]) == (mode == "dark") else 0.5
                score = i + pref
                if best is None or score < best[0]:
                    best = (score, f, on)
                break
    return best[1], best[2]

# ---------------------------------------------------------------- token table
SURFACES = {
    "dark": {
        "bg-crust": "#242933",      # sidebar, window frame (a step below nord0, as in Nord's own UIs)
        "bg-base": NORD[0],         # pages
        "bg-mantle": "#2a303b",     # player, drawers, menus
        "surface-1": NORD[1],       # cards, tiles, alt rows
        "surface-2": NORD[2],       # hover, selected
        "surface-3": NORD[3],       # pressed, scrollbar thumb
        "border": NORD[2],
        "border-strong": NORD[3],
        "text": NORD[6],
        "text-2": NORD[4],
        "text-muted-seed": "#8892a4",
    },
    "light": {
        "bg-crust": NORD[4],        # sidebar
        "bg-base": NORD[6],         # pages
        "bg-mantle": NORD[5],       # player, drawers, menus
        "surface-1": "#f8f9fb",     # cards lift slightly above Snow Storm
        "surface-2": "#eef1f6",     # hover on white cards
        "surface-3": NORD[4],
        "border": "#d3d9e4",
        "border-strong": "#bcc5d3",
        "text": NORD[0],
        "text-2": NORD[2],
        "text-muted-seed": NORD[3],
    },
}

# accent seeds: slug, label, nord index
ACCENTS = [
    ("frost", "Frost", 8),
    ("glacier", "Glacier", 9),
    ("deep-frost", "Deep Frost", 10),
    ("arctic-teal", "Arctic Teal", 7),
    ("aurora-red", "Aurora Red", 11),
    ("aurora-orange", "Aurora Orange", 12),
    ("aurora-yellow", "Aurora Yellow", 13),
    ("aurora-green", "Aurora Green", 14),
    ("aurora-purple", "Aurora Purple", 15),
]

CHECKS = []  # (label, fg, bg, ratio, target)

def check(label, fg, bg, target):
    r = contrast(fg, bg)
    CHECKS.append((label, fg, bg, r, target))
    return r

def shrink_mix(base, toward, start, ok):
    """Largest mix (<= start) of `toward` into `base` that keeps `ok(colour)` true."""
    for i in range(int(start * 100), -1, -1):
        c = mix(base, toward, i / 100)
        if ok(c):
            return c
    return base

def base_text(mode):
    """Mode-level text colours that accent surfaces must respect."""
    s = SURFACES[mode]
    away = NORD[6] if mode == "dark" else NORD[0]
    return {
        "text-muted": nudge_all(s["text-muted-seed"], away, text_bgs(s), 4.5),
        "link": nudge_all(NORD[9] if mode == "dark" else NORD[10], away, text_bgs(s), 4.5),
    }

def accent_tokens(seed, mode, with_immersive=True):
    s = SURFACES[mode]
    bt = base_text(mode)
    fill, on = fill_and_on(seed, mode)
    away = NORD[6] if mode == "dark" else NORD[0]
    row_hover = row_hover_of(mode)
    # hovered rows (selection-bg) carry text, text-2, muted text and links: all must stay 4.5
    sel = shrink_mix(s["surface-1"], fill, 0.22,
                     lambda c: all(contrast(fg, c) >= 4.5 for fg in (s["text"], s["text-2"], bt["text-muted"], bt["link"])))
    # selected rows carry text and text-2
    selected = shrink_mix(s["bg-mantle"], fill, 0.18 if mode == "dark" else 0.26,
                          lambda c: all(contrast(fg, c) >= 4.5 for fg in (s["text"], s["text-2"])))
    surfaces = text_bgs(s) + [sel, row_hover]
    text = nudge_all(seed, away, surfaces, 4.5)                               # accent as small text
    icon = nudge_all(seed, away, text_bgs(s), 3.0)                            # accent as icon / large text
    ui = nudge_all(seed, away, text_bgs(s) + [s["surface-2"], selected, row_hover], 3.0)  # rings, fills, markers
    label = nudge_all(seed, away, [s["bg-crust"]], 4.5)
    special_marker = nudge_all(NORD[15], away, [selected, s["bg-mantle"], s["bg-crust"]], 3.0)
    for name, fg, bgs, tgt in (("on-accent", on, [fill], 4.5), ("accent-text", text, surfaces, 4.5),
                               ("accent-icon", icon, text_bgs(s), 3.0),
                               ("accent-ui", ui, text_bgs(s) + [s["surface-2"], selected, row_hover], 3.0),
                               ("accent-label", label, [s["bg-crust"]], 4.5),
                               ("special-marker/selected", special_marker, [selected], 3.0),
                               ("link/selection-bg", bt["link"], [sel], 4.5),
                               ("text-muted/selection-bg", bt["text-muted"], [sel], 4.5),
                               ("text-2/selected", s["text-2"], [selected], 4.5),
                               ("control-thumb/accent-ui", control_thumb(mode), [ui], 3.0)):
        for bg in bgs:
            check(f"{mode} {name}", fg, bg, tgt)
    r, g, b = rgb(fill)
    t = {
        "accent": fill,
        "accent-rgb": f"{r}, {g}, {b}",
        "on-accent": on,
        "accent-text": text,
        "accent-icon": icon,
        "accent-ui": ui,
        "accent-label": label,
        "selection-bg": sel,
        "selected-bg": selected,
        "special-marker": special_marker,
        "accent-soft": mix(s["bg-base"], fill, 0.16),
    }
    if with_immersive:
        # immersive is a fixed dark context: derive it from this accent's DARK set, in both modes
        d = accent_tokens(seed, "dark", with_immersive=False)
        db = base_text("dark")
        t.update({"imm-accent-text": d["accent-text"], "imm-accent-icon": d["accent-icon"],
                  "imm-accent-ui": d["accent-ui"], "imm-link": db["link"],
                  "imm-selection-bg": d["selection-bg"], "imm-selected-bg": d["selected-bg"],
                  "imm-current-card": NORD[2]})
    return t

def row_hover_of(mode):
    return NORD[1] if mode == "dark" else mix(NORD[6], NORD[4], 0.6)

def control_thumb(mode):
    return SURFACES[mode]["bg-base"] if mode == "dark" else "#ffffff"

def composite(rgba_alpha, over):
    """(hex, alpha) composited over a hex backdrop."""
    h, a = rgba_alpha
    return mix(over, h, a)

# immersive glass over artwork: alpha chosen so Snow Storm text keeps 4.5 even over pure white art
IMM_GLASS = NORD[0]
def imm_alpha():
    for i in range(50, 101):
        a = i / 100
        bg = composite((IMM_GLASS, a), "#ffffff")
        if contrast(NORD[6], bg) >= 4.5 and contrast("#c2c9d6", bg) >= 4.5:
            return max(a, 0.72)
    raise SystemExit("no immersive alpha")

def scrim_alpha():
    """Black scrim alpha under artwork captions: Snow Storm text at 90% opacity must reach 4.5:1
    over pure white artwork."""
    for i in range(30, 101):
        a = i / 100
        bg = mix("#ffffff", "#000000", a)
        if contrast(mix(bg, NORD[6], 0.9), bg) >= 4.5:
            return a
    raise SystemExit("no scrim alpha")

SCRIM = scrim_alpha()
check("art caption (90% Snow Storm) / scrim over white", mix(mix("#ffffff", "#000000", SCRIM), NORD[6], 0.9),
      mix("#ffffff", "#000000", SCRIM), 4.5)

def mode_tokens(mode):
    s = SURFACES[mode]
    away = NORD[6] if mode == "dark" else NORD[0]
    t = {k: v for k, v in s.items() if k != "text-muted-seed"}
    t.update(base_text(mode))
    check(f"{mode} text/base", s["text"], s["bg-base"], 7.0)
    check(f"{mode} text-2/mantle", s["text-2"], s["bg-mantle"], 4.5)
    for bg in text_bgs(s):
        check(f"{mode} text-muted", t["text-muted"], bg, 4.5)
        check(f"{mode} link", t["link"], bg, 4.5)
    t["success-label"] = nudge_all(NORD[14], away, [s["bg-crust"]], 4.5)
    check(f"{mode} success-label/sidebar", t["success-label"], s["bg-crust"], 4.5)
    # semantic Aurora colours: `name` for icons/large text (3:1), `name-text` for small text (4.5:1)
    for name, idx in (("danger", 11), ("warning", 12), ("highlight", 13), ("success", 14), ("special", 15)):
        t[name] = nudge_all(NORD[idx], away, text_bgs(s), 3.0)
        t[f"{name}-text"] = nudge_all(NORD[idx], away, text_bgs(s), 4.5)
        for bg in text_bgs(s):
            check(f"{mode} {name}", t[name], bg, 3.0)
            check(f"{mode} {name}-text", t[f"{name}-text"], bg, 4.5)
    # form controls (WCAG 1.4.11): input/checkbox boundary and switch off-track at 3:1
    ctl_bgs = [s["bg-base"], s["bg-mantle"], s["surface-1"]]
    t["control-border"] = nudge_all(s["border-strong"], away, ctl_bgs, 3.0)
    t["control-off"] = nudge_all(s["surface-3"], away, ctl_bgs + [s["bg-crust"]], 3.0)
    t["control-thumb"] = control_thumb(mode)
    for bg in ctl_bgs:
        check(f"{mode} control-border", t["control-border"], bg, 3.0)
        check(f"{mode} control-off", t["control-off"], bg, 3.0)
    check(f"{mode} control-thumb/off-track", t["control-thumb"], t["control-off"], 3.0)
    # scrollbar thumb: 3:1 against what it floats over
    t["scroll-thumb"] = nudge_all(NORD[3] if mode == "dark" else mix(NORD[4], NORD[3], 0.45), away,
                                  [s["bg-base"], s["bg-mantle"], s["bg-crust"]], 3.0)
    for bg in (s["bg-base"], s["bg-mantle"], s["bg-crust"]):
        check(f"{mode} scroll-thumb", t["scroll-thumb"], bg, 3.0)
    # selected sidebar item: deep frost fill with readable text, both modes
    nav_fill, nav_on = fill_and_on(NORD[10], mode)
    if contrast(nav_fill, s["bg-crust"]) < 3.0:
        for i in range(0, 101):
            f = mix(NORD[10], NORD[6], i / 100)
            if contrast(f, s["bg-crust"]) >= 3.0 and contrast(f, NORD[0]) >= 4.5:
                nav_fill, nav_on = f, NORD[0]
                break
    t["nav-fill"], t["on-nav-fill"] = nav_fill, nav_on
    t["danger-fill"], t["on-danger"] = fill_and_on(NORD[11], mode)
    t["success-fill"], t["on-success"] = fill_and_on(NORD[14], mode)
    check(f"{mode} on-danger glyph", t["on-danger"], t["danger-fill"], 4.5)
    check(f"{mode} on-success", t["on-success"], t["success-fill"], 4.5)
    check(f"{mode} nav-fill text", nav_on, nav_fill, 4.5)
    check(f"{mode} nav-fill/sidebar (state)", nav_fill, s["bg-crust"], 3.0)
    t.update(accent_tokens(NORD[8], mode))
    t["shadow"] = "rgba(0, 0, 0, 0.35)" if mode == "dark" else "rgba(46, 52, 64, 0.12)"
    t["nav-hover"] = mix(s["bg-crust"], NORD[2] if mode == "dark" else NORD[6], 0.55)
    t["current-card"] = NORD[2] if mode == "dark" else "#f8f9fb"
    t["row-hover"] = row_hover_of(mode)
    check(f"{mode} text/row-hover", s["text"], t["row-hover"], 7.0)
    check(f"{mode} text/current-card", s["text"], t["current-card"], 7.0)
    check(f"{mode} nav text/hover pill", s["text-2"], t["nav-hover"], 4.5)
    t["glow-strength"] = "0.10" if mode == "dark" else "0.14"
    # identical geometry in both modes; only colours differ
    t["pane-shadow"] = ("0 0 0 1px rgba(0, 0, 0, 0.28), 0 2px 8px rgba(0, 0, 0, 0.18)" if mode == "dark"
                        else "0 0 0 1px rgba(46, 52, 64, 0.10), 0 2px 8px rgba(46, 52, 64, 0.06)")
    t["row-bg"] = "transparent" if mode == "dark" else "rgba(248, 249, 251, 0.55)"
    t["row-alt-bg"] = "rgba(236, 239, 244, 0.035)" if mode == "dark" else "rgba(255, 255, 255, 0.05)"
    t["dim-base"] = s["bg-crust"]
    if mode == "dark":
        t["float-bg"] = "linear-gradient(to bottom, rgba(0, 0, 0, 0.12), rgba(0, 0, 0, 0.05)), color-mix(in srgb, " + s["bg-mantle"] + " 94%, transparent)"
        t["float-ring"] = "inset 0 0 0 1px rgba(236, 239, 244, 0.10), inset 0 1px 0 rgba(236, 239, 244, 0.08), 0 0 0 1px rgba(0, 0, 0, 0.22)"
    else:
        t["float-bg"] = "linear-gradient(to bottom, rgba(255, 255, 255, 0.58), rgba(255, 255, 255, 0.42)), color-mix(in srgb, " + s["bg-base"] + " 90%, transparent)"
        t["float-ring"] = "inset 0 0 0 1px rgba(255, 255, 255, 0.42), inset 0 1px 0 rgba(255, 255, 255, 0.48), 0 0 0 1px " + s["border"]
    t["float-blur"] = "blur(22px) saturate(140%)"
    a = imm_alpha()
    t["imm-glass"] = f"rgba(46, 52, 64, {a})"
    imm = composite((IMM_GLASS, a), "#ffffff")
    for fg, lab in ((NORD[6], "text"), ("#c2c9d6", "text-muted"), (t["imm-accent-icon"], "accent-icon")):
        check(f"{mode} immersive {lab}/glass over white art", fg, imm, 3.0 if lab == "accent-icon" else 4.5)
    return t

# ---------------------------------------------------------------- CSS
def block(selector, tokens, indent="  "):
    lines = [f"{selector} {{"]
    lines += [f"{indent}--{k}: {v};" for k, v in tokens.items()]
    lines.append("}")
    return "\n".join(lines)

FONTS = HERE / "fonts"

def font_faces():
    """Rubik + Inter (OFL) shipped inside the CSS as data: URIs: no third-party request, works
    offline, and Cider's URL rewriting (rule-level only, so @font-face urls would break) is moot."""
    import base64, json
    ranges = json.loads((FONTS / "ranges.json").read_text())
    out = []
    for fam, file in (("Nord Rubik", "rubik"), ("Nord Inter", "inter")):
        for sub in ("latin", "latin-ext", "cyrillic"):
            key = f"{file}-{sub}-wght-normal"
            data = base64.b64encode((FONTS / f"{key}.woff2").read_bytes()).decode()
            out.append("@font-face {\n  font-family: '%s';\n  font-style: normal;\n  font-display: block;\n"
                       "  font-weight: %s;\n  src: url(data:font/woff2;base64,%s) format('woff2');\n  unicode-range: %s;\n}"
                       % (fam, ranges[key + "#w"], data, ranges[key]))
    return "\n".join(out) + "\n"

HEADER = """/* Nord for Cider {ver} :: {what}
   The Nord palette (https://www.nordtheme.com) for the Cider Apple Music client.
   Generated by build.py from one token table; edit the table, not this file.
   Credits: selector map in the lineage of Catppuccin for Cider (MIT,
   https://github.com/catppuccin/cider); Cider 4 variable layout first seen in
   "Omarchy Your Cider" by mattco (marketplace #92); background and progress-bar
   handling researched against CiderPunk Dark and Ciderify v2. License: MIT. */
"""

# Cider's own variables, mapped onto semantic tokens. Identical for both appearances.
CIDER_VARS = """
  --font-display: "Nord Rubik", "Rubik", "Nord Inter", system-ui, sans-serif;
  --font-body: "Nord Inter", "Inter", "Inter Variable", "Adwaita Sans", "Noto Sans", system-ui, sans-serif;
  --fontFamily: var(--font-body);
  --fontFamilyLyrics: var(--font-display);
  --glassFilter: none;
  --glassFilter2: none;
  --glassFallbackColor: var(--bg-mantle);
  --chrome-button-blur: 0px;

  --textDefault: var(--text);
  --textPrimary: var(--text);
  --textSecondary: var(--text-2);
  --textOpposite: var(--bg-crust);
  --systemPrimary: var(--text);
  --systemSecondary: var(--text-2);
  --systemTertiary: var(--surface-1);
  --systemQuaternary: var(--selection-bg);
  --systemQuinary: var(--selection-bg);
  /* "-onDark" = text Cider places on artwork/dark scrims: stays Snow Storm in BOTH appearances */
  --systemPrimary-onDark: #eceff4;
  --systemSecondary-onDark: #d8dee9;
  --systemTertiary-onDark: rgba(236, 239, 244, 0.6);
  --systemBlue: var(--link);
  --systemPink: var(--special);
  --systemRed: var(--danger);
  --systemGreen: var(--success);
  --systemPurple: var(--special);
  --systemYellow: var(--highlight);
  --systemCyan: var(--accent-text);
  --systemGray: var(--text-muted);

  --keyColor: var(--accent);
  --keyColor-rgb: var(--accent-rgb);
  --musicKeyColor: var(--accent);
  --primary: var(--accent);
  --primary-rgb: var(--accent-rgb);
  --q-primary: var(--accent);
  --q-primary-rgb: var(--accent-rgb);
  --q-accent: var(--special);
  --q-info: var(--link);
  --q-positive: var(--success);
  --q-negative: var(--danger);
  --q-warning: var(--warning);
  --nav-accent: var(--nav-fill);
  --eq-bars-bg-color: var(--accent-ui);

  --q-dark: var(--bg-base);
  --q-dark-page: var(--bg-base);
  --qDark: var(--bg-base);
  --qDarkPage: var(--bg-base);
  --qDarkHUD: var(--bg-mantle);
  --pageBG: var(--bg-base);
  --lightBackgroundColor: var(--bg-base);
  --opaqueShelfBG: var(--surface-1);
  --tracklistHoverColor: var(--surface-2);
  --vibrantDivider: var(--border);
  --reducedSurfaceColor: var(--surface-1);
  --playerBackground: var(--bg-mantle);
  --playerScrubberFill: var(--accent-ui);
  --progressColor: var(--accent-ui);

  /* Cider tints dialogs by mixing 10% key colour into near-black / near-white */
  --mats-darkBackgroundBase: var(--bg-crust);
  --mats-lightBackgroundBase: var(--bg-base);
  --mats-accentBackground: var(--bg-base);
  --mats-accentBackgroundDark: var(--bg-mantle);
  --mats-accentOutline: color-mix(in srgb, var(--accent), transparent 60%);

  background: var(--bg-crust);
  color: var(--text);
  font-family: var(--fontFamily);
"""

COMPONENTS = """
  /* Quasar colour fills carry their own text (e.g. the "name cannot be empty" banner) */
  .bg-green { background-color: var(--success-fill); color: var(--on-success); }
  .bg-red { background-color: var(--danger-fill); color: var(--on-danger); }
  .text-default { color: var(--text); }
  .text-red { color: var(--danger-text); }
  .bg-primary.text-white, .bg-primary .text-white { color: var(--on-accent); }

  /* ---- Backgrounds: Cider runs with window transparency (mica/acrylic). Any layer it
     leaves transparent shows what is behind the window (black where there is no blur),
     so every layer is painted explicitly. */
  #app, #app-viewport, #app-bounds, .app-root { background: var(--bg-crust); }
  .cider-sidebar { background-color: var(--bg-crust); }
  /* page header wash: Cider fades the key colour into black/white */
  .q-page.q-py-lg.q-px-xl,
  .q-page.q-pa-lg.q-px-xl {
    background-image: linear-gradient(rgba(var(--accent-rgb), 0.14) 0%, var(--bg-base) 9%);
  }

  .win-titlebar { background: var(--bg-crust); color: var(--text); }
  .window-controls .window-button,
  .window-controls .window-control { color: var(--text-2); }

  .q-card, .q-menu, .q-tooltip, .q-dialog, .q-field__control, .search-box,
  .dropdown-menu, .chrome-top, .player, [role='dialog'] [sfc-name='QCard'] {
    box-shadow: none;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }

  [sfc-name='MojavePlayer'] {
    [sfc-name='AMProgressBar'] .overlay-progress-bar { --progressColor: var(--accent-ui); }
    .volumeBar input.volume-range { --progressColor: var(--accent-ui); }
  }
  /* newer progress bar component (fill defaults to --textDefault) */
  .cider-progress-bar .progress-current,
  .cider-progress-bar .progress-cursor { background-color: var(--accent-ui); }
  .cider-progress-bar .progress-bar-content,
  .cider-progress-bar .progress-background { background-color: var(--surface-2); }

  ::selection { background-color: var(--selection-bg); color: var(--text); }
  /* scrollbars float: 13px gutter, a 6px rounded thumb (3:1) inset by a transparent border,
     transparent track; same language for sidebar, pages and drawers */
  ::-webkit-scrollbar { width: 13px; height: 13px; background: transparent; }
  ::-webkit-scrollbar-track, ::-webkit-scrollbar-track-piece, ::-webkit-scrollbar-corner { background: transparent; }
  /* Cider paints its thumb with an inset box-shadow; replace it with a clipped fill:
     3px left + 4px right transparent border = a 6px pill floating 4px off the edge */
  ::-webkit-scrollbar-thumb {
    background-color: var(--scroll-thumb);
    box-shadow: none;
    border-style: solid;
    border-color: transparent;
    border-width: 3px 4px 3px 3px;
    background-clip: padding-box;
    border-radius: 999px;
    min-height: 32px;
  }
  ::-webkit-scrollbar-thumb:hover { background-color: var(--text-muted); box-shadow: none; border-width: 3px 4px 3px 3px; }

  input, textarea, select, button, .q-item, .nav-text { font-family: var(--fontFamily); }
  input[type=checkbox][switch] { background: var(--control-off); }
  input[type=checkbox][switch]:checked { background: var(--accent-ui); }
  input[type=checkbox][switch]:before { background: var(--control-thumb); }
  .c-switch__track { background: var(--control-off); }
  .c-switch.is-on .c-switch__track { background: var(--accent-ui); }
  .c-switch__thumb { background: var(--control-thumb); }

  .q-tooltip {
    background-color: var(--bg-mantle);
    color: var(--text);
    border: 1px solid var(--border-strong);
  }

  [sfc-name='HeaderSearch'] {
    .search-box { background: var(--bg-mantle); border: 1px solid var(--control-border); color: var(--text); }
    .dropdown-menu { background-color: var(--bg-base); border: 1px solid var(--border-strong); }
  }
  .command-center .content-area,
  .content-area .results-container { background: var(--bg-base); }
  .content-area .details-container { background: var(--surface-1); }

  [sfc-name='QueueButton'].active,
  [title='Lyrics'].active { color: var(--accent-icon); }
  .see-all { color: var(--accent-text); }

  [sfc-name='Explicit'] svg { fill: var(--text-muted); }

  [sfc-name='RouterView'] {
    background: var(--bg-base);
    color: var(--text);
    .artist-chip { --keyColor: var(--chip-color, var(--accent-text)); }
    [sfc-name='Playlist'] .tracks-container .track-list,
    [sfc-name='Album'] .tracks-container .track-list {
      color: var(--text);
      .ri-list-item:hover:not(.selected) { background-color: var(--selection-bg); }
      .ri-list-item.selected,
      [sfc-name='PlaylistTrack'].selected,
      [sfc-name='AlbumTrack'].selected {
        background-color: var(--selected-bg);
        box-shadow: inset 0 0 0 1.5px var(--selected-marker, var(--accent-ui));
      }
      [sfc-name='PlaylistTrack']:not(.selected),
      [sfc-name='AlbumTrack']:not(.selected) {
        .artist-link, .artist-section, .album-section, button.menu-btn { color: var(--link); }
      }
    }
  }

  /* ---- Sidebar */
  [sfc-name='Sidebar'] {
    background: var(--bg-crust);
    color: var(--text-2);
    --selection-bg: var(--surface-2);
    --systemQuaternary: var(--surface-1);
    --systemQuinary: var(--surface-1);
    --textSecondary: var(--text-2);
    --systemSecondary: var(--text-2);
    .nav-icon { color: var(--nav-icon, var(--accent-icon)); }
    /* selected and hover share Cider's inset pill (.nav-button-content::before) */
    .sidebar_nav-btn:hover .nav-button-content:not(.active)::before {
      background: var(--nav-hover);
      opacity: 1;
      transform: scale(1);
    }
    .nav-button-content.active {
      .nav-icon, .nav-text { color: var(--on-nav-fill); }
    }
    .search-box { background: var(--bg-mantle); color: var(--text); border: 1px solid var(--control-border); }
  }
  /* selected sidebar item is painted by .nav-button-content::before = --nav-accent */
  /* ---- Profile footer: chip + "..." read as one unit on one inset surface */
  .profile-tab {
    padding: 0;
    margin: 0 8px 8px;
    align-items: center;
  }
  .profile-tab .profile-btn { background: transparent; border: none; box-shadow: none; border-radius: 14px; }
  .profile-tab .profile-btn::before, .profile-tab .profile-btn::after { opacity: 0; }
  .profile-tab .profile-artwork { box-shadow: 0 0 0 1.5px var(--border-strong); }
  .profile-tab .profile-name { color: var(--text); font-weight: 600; }
  .profile-tab .profile-handle { color: var(--text-muted); opacity: 1; }
  .profile-tab .profile-mainmenu .chrome-button { background: transparent; border-radius: 10px; color: var(--text-2); }
  .profile-tab .profile-mainmenu .chrome-button:hover { background: var(--surface-2); color: var(--text); }

  /* ---- Right drawer: lyrics + queue */
  /* right column mirrors the left sidebar: one crust gutter, the page pane floats between them */
  .ns-sidebar--right { background: var(--bg-crust); }
  [sfc-name='RightDrawerContent'] {
    background: transparent;
    border-left: none;
    .lyric-view {
      font-family: var(--fontFamilyLyrics);
      .lyric-word {
        --defaultColor: var(--text-muted);
        --gradientColor: var(--lyric-sweep, var(--accent-text));
      }
      .lyric-word.finished-word { --defaultColor: var(--lyric-sung, var(--text)); }
      .active .lyric-text { color: var(--lyric-active, var(--text)); }
      .finished .lyric-text { color: var(--lyric-sung, var(--text)); }
    }
    .queue-item.is-current {
      background: var(--current-card);
      box-shadow: none;
      .qmd-artist_album { color: var(--text-2); }
    }
    [sfc-name='AMQueueItem'] {
      .qmd-title-text { color: var(--text); }
      .qmd-artist_album { color: var(--text-muted); }
      .fa-solid:not(.remove-item-button *) { color: var(--accent-icon); }
    }
  }

  /* ---- Menus, dialogs, settings */
  /* ---- Popovers and menus: the shared float material. The .q-menu wrapper is the ONE element
     that owns surface, ring, radius and shadow; Cider's inner panels go transparent. */
  .q-menu {
    background: var(--float-bg);
    box-shadow: var(--float-ring), 0 8px 28px var(--shadow);
    backdrop-filter: var(--float-blur);
    -webkit-backdrop-filter: var(--float-blur);
    border: none;
    border-radius: var(--floatingRadius, 13px);
    color: var(--text);
    .q-hoverable:hover, .q-item:hover { background-color: var(--row-hover); }
    .q-separator { background: var(--border); }
    [sfc-name='ContextMenuIcon'],
    [sfc-name='QItem']:hover [sfc-name='QIcon'] { color: var(--accent-icon); }
    [sfc-name='AMVolumeSlider'] .volumeBar .volume-range { --progressColor: var(--accent-ui); }
  }
  .q-menu > .notification-center {
    background: transparent;
    border: none;
    box-shadow: none;
    border-radius: inherit;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
  .notification-center {
    color: var(--text);
    .notification-center__heading { color: var(--text); font-family: var(--font-display); }
    .notification-center__section { color: var(--text-muted); letter-spacing: .04em; }
    .notification-center__row { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; }
    .notification-center__title { color: var(--text); }
    .notification-center__subtitle { color: var(--text-2); }
    .notification-center__meta { color: var(--text-muted); }
    .notification-center__glyph { color: var(--text-muted); }
    .notification-center__glyph.is-success { color: var(--success); }
    .notification-center__glyph.is-error { color: var(--danger); }
    .notification-center__glyph.is-warning { color: var(--warning); }
    .c-spinner { color: var(--accent-ui); }
    .c-btn { color: var(--text-2); border-radius: 10px; }
    .c-btn:hover { background: var(--surface-2); color: var(--text); }
  }
  .q-menu:has(> .notification-center) { animation: nord-pop var(--motion-slow) var(--ease-out); }

  [role='dialog'] [sfc-name='QCard'] {
    background-color: var(--bg-base);
    color: var(--text);
    border: 1px solid var(--border-strong);
  }
  .cider-dialog-window--generic,
  .dialog-box,
  dialog.plugin-base-modal {
    --backgroundColor: var(--bg-base);
    --backgroundColorFallback: var(--bg-base);
    background: var(--bg-base);
    color: var(--text);
    border: 1px solid var(--border-strong);
  }
  .settings-category-tile { background: var(--surface-1); border-color: var(--border); }
  .settings-category-tile:hover { background: var(--surface-2); border-color: var(--accent-ui); }
  .settings-category-tile .tile-icon-wrap { color: var(--accent-icon); }
  .settings-updates-widget,
  .profile-hero-card {
    background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.16) 0%, transparent 60%), var(--surface-1);
  }

  /* ---- Marketplace and installed-theme cards: painted like the page, square -> lift them */
  .gallery-item-card {
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 14px;
    transition: background-color .15s ease, border-color .15s ease;
  }
  .gallery-item-card:hover { background: var(--surface-2); border-color: var(--accent-ui); }
  .themes-grid > * {
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 12px;
  }

  /* "Remove from queue" (shown on queue-row hover): a clear red minus, ringed off the artwork */
  .remove-item-button {
    width: 18px;
    height: 18px;
    background: var(--danger-fill);
    color: var(--on-danger);
    box-shadow: 0 0 0 2px var(--bg-crust);
    animation: nord-fade var(--motion-fast) var(--ease-out);
    transition: filter var(--motion-fast) var(--ease-out), transform var(--motion-fast) var(--ease-out);
    .fa-solid { color: var(--on-danger); font-size: 10px; }
  }
  .remove-item-button:hover { background: var(--danger-fill); filter: brightness(1.08); transform: scale(1.05); }
  @keyframes nord-fade { from { opacity: 0; } to { opacity: 1; } }

  /* ---- Floating material: the player pill (.blur-surface), the queue info bar and the profile
     pill are one family. Cider builds the player glass differently per mode; this is one rule. */
  .blur-surface, .queue-info-bar, .profile-tab, .library-toolbar {
    background: var(--float-bg);
    box-shadow: var(--float-ring), 0 6px 24px var(--shadow);
    backdrop-filter: var(--float-blur);
    -webkit-backdrop-filter: var(--float-blur);
    border: none;
  }
  .queue-info-bar, .profile-tab, .library-toolbar { border-radius: var(--floatingRadius, 13px); }
  /* the floating list toolbar (Songs etc.): float material + quiet icons, accent on hover */
  .library-toolbar .chrome-button { color: var(--text-2); }
  .library-toolbar .chrome-button:hover { color: var(--accent-icon); }
  .library-toolbar .chrome-button-fill { background: var(--surface-2); }
  /* sticky column header: opaque so rows never ghost through it */
  .header-container { background-color: var(--bg-mantle); }

  [sfc-name='MiniPlayerLayout'] {
    background: var(--bg-mantle);
    border: 1px solid var(--border-strong);
    [sfc-name='MiniPlayerControls'] .overlay-progress-bar { --progressColor: var(--accent-ui); }
  }
  .immersive-player {
    [sfc-name='AMPMetadataMojave'] {
      .song-name { color: var(--text); }
      .release-info { color: var(--text-2); }
    }
    [sfc-name='AMProgressBar'] .overlay-progress-bar { --progressColor: var(--accent-ui); }
  }

  /* favourites in Apple Music are stars: favourited button, rating star, favourite badges */
  .added .favorite-icon, .rating-icon.text-primary, .favorite-icon.text-primary,
  .favorite-star { color: var(--star, var(--accent-icon)); }

  /* Album/playlist Play + Shuffle: Cider tints them from the cover art, which can put
     light text on a light fill. Pin them to the accent so on-accent contrast holds. */
  [sfc-name='AlbumPlaybackActions'] .c-btn .c-btn--surface { background: var(--accent); }


  /* ---- Icons that Cider colours with the key colour: use the text-safe accent, keep fills as fills */
  .text-primary { color: var(--accent-text); }
  ._svg-icon { --keyColor: var(--accent-icon); }
  .chrome-button-accent { color: var(--text-2); }   /* holds text labels too (plugin badges): 4.5:1 tier */
  .queue-header-row .q-btn { color: var(--text-2); }

  /* ---- Top chrome pills (nav flipper, button groups, round buttons): Nord surfaces, so the
     accent icons on them keep 3:1 (Cider's light pills are #d9dbdd) */
  .chrome-top .nav-flipper,
  .chrome-top .chrome-button-group,
  .chrome-top .chrome-button:not(:where(.chrome-button-group *)) {
    background-color: var(--surface-1);
    border-color: var(--border);
  }
  .chrome-top .chrome-button:hover { background-color: var(--surface-2); }

  /* ---- Text on artwork cards (PowerSwoosh): always Snow Storm, with a soft lift for busy covers */
  [sfc-name='PowerSwoosh'] {
    .powerswoosh-chin, .title-text, .powerswoosh-lockup-reason, .powerswoosh-lockup-detail-subtitle-links {
      text-shadow: 0 1px 3px rgba(0, 0, 0, 0.55);
    }
    [sfc-name='Explicit'] svg { fill: var(--systemSecondary-onDark); }
    /* Apple-style soft scrim under the chin so the caption holds AA on any cover;
       the opacity-.75 subtitles go fully opaque (scrim carries the hierarchy instead) */
    .powerswoosh-chin { background: rgba(0, 0, 0, %(scrim)s); box-shadow: 0 -30px 30px -4px rgba(0, 0, 0, 0.5); }
    .powerswoosh-lockup-reason, .powerswoosh-lockup-detail-subtitle { opacity: .9; }
  }


  /* ---- Cider hard-codes some surfaces per appearance; neutralise them identically for both */
  .am-tabs { background: var(--surface-1); }
  .bg-active { background: var(--surface-1); border-color: var(--border); }
  .c-input-wrapper, .c-input { background: var(--surface-1); color: var(--text); border-color: var(--control-border); }
  .c-checkbox__box { background: var(--surface-1); border-color: var(--control-border); }
  .category-tabs { background: var(--bg-mantle); border-bottom-color: var(--border); }
  .action-footer { background: var(--bg-mantle); border-top-color: var(--border); }
  .cider-dialog-container { --dimBaseColor: var(--dim-base); }
  #app-bounds, .new-shell-page-container { box-shadow: var(--pane-shadow); }

  /* ---- List rows (zebra approved): same rule in both modes, only the tokens differ */
  --tracklistAltRowColor: var(--row-bg);
  --trackBackgroundEven: var(--row-alt-bg);
  .frow.library-song-item { background-color: var(--row-bg); }
  .frow.library-song-item.alt-row { background-color: var(--row-alt-bg); }

  /* ---- Hover fills: one quiet palette step, same language everywhere */
  .frow.library-song-item:hover,
  .listitem-scaffold .c-listitem:hover,
  [sfc-name='RightDrawerContent'] .queue-item:not(.is-current):hover { background-color: var(--row-hover); }
  /* sticky list header must be opaque or scrolled rows show through it */
  .frow.header-frow { background-color: var(--bg-mantle); }
  /* round icon buttons on pages (artist/album headers): text-safe icon on a quiet pill */
  .more-btn { color: var(--accent-icon); background: var(--surface-1); border: 1px solid var(--border); border-radius: 999px; }
  .more-btn:hover { background: var(--surface-2); }

  /* ---- Motion: tokens + cheap properties only (colour, opacity, transform, shadow) */
  --motion-fast: 120ms;
  --motion-base: 180ms;
  --motion-slow: 260ms;
  --ease-out: cubic-bezier(.2, .8, .2, 1);
  --ease-in-out: cubic-bezier(.4, 0, .2, 1);
  .frow, .ri-list-item, .queue-item, .q-item, .profile-tab, .listitem-scaffold .c-listitem {
    transition: background-color var(--motion-base) var(--ease-out), color var(--motion-base) var(--ease-out);
  }
  /* Cider animates transform (hover lift, press scale) on these: keep it in the list */
  .chrome-button, .c-btn, .more-btn, .q-btn, .notification-center .c-btn {
    transition: transform var(--motion-duration-hover) var(--motion-ease-spring, var(--ease-out)),
                background-color var(--motion-fast) var(--ease-out), color var(--motion-fast) var(--ease-out),
                border-color var(--motion-fast) var(--ease-out), box-shadow var(--motion-fast) var(--ease-out);
  }
  /* Cider's own motion presets (html.cards-in-motion etc.): calm them, don't stack on them */
  --motion-card-hover-scale: 1.01;
  --motion-card-press-scale: .99;
  --motion-lift-sm: -1px;
  --motion-lift-md: -1px;
  --motion-icon-scale: 1.03;
  --motion-ease-overshoot: cubic-bezier(.2, .8, .2, 1);
  --motion-icon-ease: cubic-bezier(.2, .8, .2, 1);
  --motion-duration-hover: 240ms;
  .artwork:hover, .item-artwork:hover > .artwork, .qnp-artwork:hover { filter: brightness(.94); }
  .mediaitem-card:hover, .powerswoosh:hover { filter: brightness(1.03); }

  /* the only lift we add: cards you choose from (marketplace, settings tiles) */
  .gallery-item-card, .settings-category-tile {
    transition: transform var(--motion-slow) var(--ease-out), box-shadow var(--motion-slow) var(--ease-out),
                background-color var(--motion-slow) var(--ease-out), border-color var(--motion-slow) var(--ease-out);
  }
  .gallery-item-card:hover, .settings-category-tile:hover { transform: translateY(-1px); box-shadow: 0 6px 18px var(--shadow); }
  @keyframes nord-pop { from { opacity: 0; transform: translateY(-4px) scale(.98); } to { opacity: 1; transform: none; } }

  /* ---- Player action toggles (shuffle/repeat on): icon in the UI-safe accent (3:1) */
  [sfc-name='AMShuffleAction'], [sfc-name='AMRepeatAction'],
  [sfc-name='NowPlayingLibraryButton'], .item-actions, .queue-section-header {
    --keyColor: var(--accent-ui);
    --musicKeyColor: var(--accent-ui);
  }

  /* ---- Lyrics drawer: provider list, empty state, provider pill */
  .no-lyrics-container .no-lyrics-text { color: var(--text-muted); }
  .provider-check-item { color: var(--text-2); }
  .provider-check-item .check-icon, .provider-check-item .q-icon { color: var(--text-muted); }
  .provider-check-item.status-pending { opacity: .7; }
  .provider-check-item.status-pending .check-icon,
  .provider-check-item.status-checking .check-icon { color: var(--text-muted); }
  .provider-check-item.status-found .check-icon { color: var(--success); }
  .provider-select {
    --pill-bg: var(--surface-1);
    --pill-bg-hover: var(--surface-2);
    --pill-border: inset 0 0 0 1px var(--border);
    --pill-color: var(--text);
  }
  .provider-select .c-select--indicator svg { fill: var(--text-muted); }
  .provider-select option { color: var(--text); }
  svg.c-spinner, .c-spinner, .c-spinner__dot, .q-spinner { color: var(--text-muted); fill: var(--text-muted); }

  /* ---- Quasar "--dark" components: Cider renders lists, items, cards and checkboxes with the
     dark variants in BOTH appearances, which forces #fff text. Route them through tokens. */
  .q-list--dark, .q-item--dark, .q-card--dark { color: var(--text); border-color: var(--border); }
  .q-list--dark .q-item__section--side:not(.q-item__section--avatar),
  .q-item--dark .q-item__section--side:not(.q-item__section--avatar) { color: var(--text-2); }
  .q-list--dark .q-item__label--header, .q-item--dark .q-item__label--header,
  .q-list--dark .q-item__label--caption, .q-item--dark .q-item__label--caption,
  .q-list--dark .q-item__label--overline, .q-item--dark .q-item__label--overline { color: var(--text-muted); }
  .q-list--dark.q-list--separator > .q-item-type + .q-item-type { border-top-color: var(--border); }
  .q-checkbox--dark .q-checkbox__inner { color: var(--text-muted); }
  .q-menu .q-item ._svg-icon:not([class*='text-']), .q-menu .q-item .q-icon:not([class*='text-']),
  .q-list--dark .q-item ._svg-icon:not([class*='text-']), .q-list--dark .q-item .q-icon:not([class*='text-']) { color: var(--text-2); }
  .q-item--clickable:hover { background-color: var(--row-hover); }
  .q-item:focus-visible, .q-item.q-manual-focusable--focused { outline-color: var(--accent-ui); }
  .q-list, .cider-dialog-window--generic, [sfc-name='CSwitch'] { --keyColor: var(--accent-ui); --musicKeyColor: var(--accent-ui); }
  /* small tooltips Cider hard-codes near-black: one Nord tooltip in both modes */
  .c-slider__tooltip, .custom-tooltip { background: var(--bg-mantle); color: var(--text); box-shadow: var(--float-ring), 0 4px 14px var(--shadow); }
  .c-slider__tooltip::after { border-top-color: var(--bg-mantle); }

  /* ---- Immersive: always artwork + dark glass, so it is a fixed dark CONTEXT in both appearances
     (context tokens, not mode tokens: identical in light and dark) */
  /* the now-playing view only: in immersive app mode Cider also renders normal pages inside
     .immersive-layer, and those must keep the mode tokens */
  [class*='immersive-player'] {
    --text: #eceff4;
    --text-2: #d8dee9;
    --text-muted: #c2c9d6;
    --textDefault: #eceff4;
    --systemPrimary: #eceff4;
    --systemSecondary: #d8dee9;
    --accent-text: var(--imm-accent-text);
    --accent-icon: var(--imm-accent-icon);
    --accent-ui: var(--imm-accent-ui);
    --link: var(--imm-link);
    --selection-bg: var(--imm-selection-bg);
    --selected-bg: var(--imm-selected-bg);
    --current-card: var(--imm-current-card);
    --keyColor: var(--imm-accent-ui);
    --musicKeyColor: var(--imm-accent-ui);
    --row-hover: var(--imm-glass);
    --surface-1: var(--imm-glass);
    --surface-2: var(--imm-glass);
    --border: rgba(236, 239, 244, 0.12);
    --border-strong: rgba(236, 239, 244, 0.18);
    --bg-mantle: #2a303b;
    --float-bg: linear-gradient(to bottom, rgba(0, 0, 0, 0.12), rgba(0, 0, 0, 0.05)), var(--imm-glass);
    --float-ring: inset 0 0 0 1px rgba(236, 239, 244, 0.10), inset 0 1px 0 rgba(236, 239, 244, 0.08), 0 0 0 1px rgba(0, 0, 0, 0.22);
    /* Cider colours immersive text, badges and the glass controls from the artwork; pin them */
    --nowPlaying-textColor1: #eceff4;
    --nowPlaying-textColor2: #d8dee9;
    --artwork-key-color: var(--imm-accent-ui);
    color: #eceff4;
  }
  /* the floating glass controls in immersive layouts: dark Nord glass, whatever the artwork */
  .immersive-player-tab-controls { background: var(--imm-glass); }
  [class*='immersive-player'] .lgs-fallback { background: var(--imm-glass); }
  [class*='immersive-player'] [sfc-name='AMPLCDGlass'] { background: rgba(236, 239, 244, 0.06); box-shadow: inset 0 0 0 1px rgba(236, 239, 244, 0.10); }
  [class*='immersive-player'] .lgs-inner { background: var(--imm-glass); box-shadow: inset 0 0 0 1px rgba(236, 239, 244, 0.12); }

  /* ---- Typography: Nord's own pairing. Rubik (display) for titles and lyrics, Inter for UI. */
  h1, h2, h3, .shelf-title, .title-text, .song-name, .gi-title,
  [sfc-name='RightDrawerContent'] .lyric-view {
    font-family: var(--font-display);
    letter-spacing: -0.01em;
  }

  /* ---- Atmosphere: a faint Frost aurora at the top of every page, then flat Polar Night / Snow Storm */
  .new-shell-page-container,
  .new-shell-page-container[data-corner-cut=true]::before,
  [sugar-color-scheme=artwork] .new-shell-page-container,
  [sugar-color-scheme=keyColor] .new-shell-page-container {
    background:
      radial-gradient(1100px 380px at 18% -12%, rgba(var(--accent-rgb), var(--glow-strength)), transparent 62%),
      var(--bg-base);
  }
  .new-shell-page-container[data-corner-cut=true] { background: transparent; }

  /* ---- Keyboard focus: always visible, always the accent */
  :focus-visible {
    outline: 2px solid var(--accent-ui);
    outline-offset: 2px;
  }

  /* reduced motion: the OS setting AND Cider's own toggle; [no-reduced-motion] (spinners) stays alive */
  @media (prefers-reduced-motion: reduce) {
    *:not([no-reduced-motion]), *:not([no-reduced-motion])::before, *:not([no-reduced-motion])::after { transition: none; animation: none; }
    .gallery-item-card:hover, .settings-category-tile:hover { transform: none; }
  }
  html[reduced-motion=true] & {
    *:not([no-reduced-motion]), *:not([no-reduced-motion])::before, *:not([no-reduced-motion])::after { transition: none; animation: none; }
    .gallery-item-card:hover, .settings-category-tile:hover { transform: none; }
  }

  /* ---- Text on accent fills: computed per accent for 4.5:1 */
  [sfc-name='AlbumPlaybackActions'] .c-btn,
  [sfc-name='AlbumPlaybackActions'] .c-btn .c-btn--content,
  .c-btn--primary-text,
  .plugin-base .c-btn.primary,
  button.bg-primary,
  .q-btn.bg-primary,
  .q-btn.bg-primary [sfc-name='QIcon'],
  .category-tab.active {
    color: var(--on-accent);
  }
"""





SCOPE = "body.body--dark, body.body--light"

HC = {
    "dark":  {"text": "#ffffff", "text-2": NORD[6], "text-muted": NORD[4], "link": "#a3c2e0",
              "border": NORD[3], "border-strong": "#8892a4", "control-border": NORD[4], "control-off": NORD[4],
              "textDefault": "#ffffff", "systemPrimary": "#ffffff", "systemSecondary": NORD[6]},
    "light": {"text": "#000000", "text-2": NORD[0], "text-muted": NORD[1], "link": "#2f4a6b",
              "border": "#8892a4", "border-strong": NORD[3], "control-border": NORD[2], "control-off": NORD[2],
              "textDefault": "#000000", "systemPrimary": "#000000", "systemSecondary": NORD[0]},
}

def base_css(tokens):
    out = [HEADER.format(ver=VERSION, what="base (follows Cider's Light/Dark appearance)") + font_faces()]
    out.append(block("body.body--dark", tokens["dark"]))
    out.append(block("body.body--light", tokens["light"]))
    out.append("/* Cider's High Contrast mode (html.a11y-high-contrast): maximum-contrast Nord tokens */")
    out.append(block("html.a11y-high-contrast body.body--dark", HC["dark"]))
    out.append(block("html.a11y-high-contrast body.body--light", HC["light"]))
    out.append(f"{SCOPE} {{{CIDER_VARS}{COMPONENTS.replace('%(scrim)s', f'{SCRIM:.2f}')}}}")
    return "\n\n".join(out) + "\n"

def accent_css(slug, label, idx):
    d, l = accent_tokens(NORD[idx], "dark"), accent_tokens(NORD[idx], "light")
    out = [HEADER.format(ver=VERSION, what=f"accent: {label} (nord{idx})")]
    out.append("/* Enable on top of the base, one accent at a time. Only redefines accent tokens. */")
    # higher specificity than the base token blocks, so stacking never depends on load order
    out.append(block("html body.body--dark", d))
    out.append(block("html body.body--light", l))
    return "\n\n".join(out) + "\n"

# Aurora: Nord's own split of roles across the UI. Frost stays primary (accent),
# Aurora colours carry emphasis and meaning.
def aurora_css(tokens):
    """Aurora assigns colour by meaning, never as a rainbow:
       yellow = the line being sung / starred items, red = loved / explicit, purple = your selection,
       green = library (yours) + good news, orange = live (radio, concerts), Frost stays the accent."""
    out = [HEADER.format(ver=VERSION, what="Aurora layer (colour by meaning; stack on any base/accent)")]
    rules = """
  --lyric-sweep: var(--highlight);
  --lyric-sung: var(--accent-text);
  --lyric-active: var(--text);
  --selected-marker: var(--special-marker);
  --star: var(--highlight);
  --eq-bars-bg-color: var(--success);

  [sfc-name='Explicit'] svg { fill: var(--warning); }
  [sfc-name='RouterView'] { --chip-color: var(--success-text); }
  .see-all { color: var(--link); }
  [sfc-name='RightDrawerContent'] [sfc-name='AMQueueItem'] .fa-solid:not(.remove-item-button *) { color: var(--special); }
  .settings-updates-widget {
    background: linear-gradient(135deg, color-mix(in srgb, var(--success) 22%, transparent) 0%, transparent 60%), var(--surface-1);
  }
  .profile-hero-card {
    background: linear-gradient(135deg, color-mix(in srgb, var(--special) 22%, transparent) 0%, transparent 60%), var(--surface-1);
  }

  /* the one memorable moment: what is playing now wears Aurora purple */
  [sfc-name='RightDrawerContent'] .queue-item.is-current {
    background: var(--current-card);
    box-shadow: inset 0 0 0 1.5px var(--special-marker);
  }

  /* sidebar sections by route (stable across layouts; Cider can insert extra wrapper divs) */
  [sfc-name='Sidebar'] [data-nav-path^='/am/'] { --nav-icon: var(--accent-icon); }
  [sfc-name='Sidebar'] [data-nav-path='/am/radio'],
  [sfc-name='Sidebar'] [data-nav-path='/am/concerts'] { --nav-icon: var(--warning); }
  [sfc-name='Sidebar'] [data-nav-path^='/am/library/'] { --nav-icon: var(--success); }
  [sfc-name='Sidebar'] .am-expansion-item:has(+ .expansion-content [data-nav-path='/am/listen-now']) .sidebar-label { color: var(--accent-label); }
  [sfc-name='Sidebar'] .am-expansion-item:has(+ .expansion-content [data-nav-path^='/am/library/']) .sidebar-label { color: var(--success-label); }
"""
    out.append(f"{SCOPE} {{{rules}}}")
    return "\n\n".join(out) + "\n"



def theme_yml():
    lines = [
        "name: Nord",
        "author: ondrish",
        "description: An arctic, north-bluish theme for Cider. Follows Cider's Light/Dark appearance, with Frost and Aurora accents and an optional varied Aurora layer.",
        f"version: {VERSION}",
        "marketplaceID: 107",
        "repo: https://github.com/ondrish/cider-nord",
        "stylesheets:",
        "  - file: main.css",
        "    name: Nord (base)",
        "    description: Required. Polar Night in Dark appearance, Snow Storm in Light appearance, Frost accent. Enable one accent and/or Aurora below.",
        "  - file: aurora.css",
        "    name: Aurora layer (varied colours)",
        "    description: Optional, stacks with any accent. Spreads Aurora colours across lyrics, ratings, selection and sidebar icons.",
    ]
    for slug, label, idx in ACCENTS[1:]:
        lines += [f"  - file: accent-{slug}.css",
                  f"    name: \"Accent: {label}\"",
                  f"    description: Enable on top of the base, one accent at a time (nord{idx})."]
    return "\n".join(lines) + "\n"

def importantize(css):
    """What ThemeKit does at load: every declaration becomes !important, except inside
    @keyframes and @font-face (ThemeKit only touches style rules; !important there voids them)."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    keep = []
    out, i = [], 0
    for m in re.finditer(r"@(?:keyframes|font-face)[^{]*\{", css):
        if m.start() < i: continue
        j = m.end(); depth = 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0); j += 1
        out.append(css[i:m.start()]); keep.append(css[m.start():j]); out.append(f"__KF{len(keep)-1}__"); i = j
    out.append(css[i:])
    body = "".join(out)
    def fix(m):
        decl = m.group(0)
        return decl if "!important" in decl else decl[:-1] + " !important;"
    body = re.sub(r"(?<=[{;\s])(?:--)?[A-Za-z][\w-]*\s*:[^;{}]+;", fix, body)
    for n, kf in enumerate(keep):
        body = body.replace(f"__KF{n}__", kf)
    return body


def assert_token_only_modes(css, name):
    """Light and dark must share every rule: outside the two token blocks nothing may be
    scoped to an appearance, and the token blocks may hold only custom properties."""
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    body = re.sub(r"@font-face\s*\{[^}]*\}", "", body)
    for m in re.finditer(r"([^{}]*)\{", body):
        sel = m.group(1).strip()
        if "body--dark" in sel or "body--light" in sel:
            if sel in ("body.body--dark", "body.body--light", "html body.body--dark", "html body.body--light",
                       "html.a11y-high-contrast body.body--dark", "html.a11y-high-contrast body.body--light"):
                start = m.end(); depth = 1; i = start
                while depth:
                    depth += {"{": 1, "}": -1}.get(body[i], 0); i += 1
                inner = body[start:i - 1]
                if "{" in inner or re.search(r"(?<![-\w])(?!--)[a-z-]+\s*:", inner):
                    raise SystemExit(f"{name}: appearance block holds more than custom properties")
            elif sel != "body.body--dark, body.body--light":
                raise SystemExit(f"{name}: mode-scoped selector outside token blocks: {sel[:80]}")


# ---------------------------------------------------------------- structural parity (F19)
COLOR_RE = re.compile(r"color-mix\([^()]*(?:\([^()]*\)[^()]*)*\)|rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}\b|\btransparent\b")

def assert_mode_geometry(tokens):
    """Token values may differ in colour only: shadows, gradients and stacks need the same
    layer count and geometry in both modes."""
    for k in tokens["dark"]:
        d, l = str(tokens["dark"][k]), str(tokens["light"].get(k, ""))
        if re.fullmatch(r"[\d.]+", d) and re.fullmatch(r"[\d.]+", l):
            continue                                   # pure alpha/strength numbers
        if COLOR_RE.sub("C", d) != COLOR_RE.sub("C", l):
            raise SystemExit(f"token --{k}: dark/light differ in structure, not just colour:\n  {d}\n  {l}")

# ---------------------------------------------------------------- role map (F6)
# Every colour a rule paints with must be a known role; each role lists the surfaces it may sit
# on and its WCAG target. The build checks every role x surface x mode x accent.
TEXT_SURF = ["bg-base", "bg-mantle", "surface-1", "bg-crust"]
ROLES = {
    "text":            (TEXT_SURF + ["selection-bg", "selected-bg", "row-hover", "current-card", "nav-hover"], 4.5),
    "text-2":          (TEXT_SURF + ["selection-bg", "selected-bg", "row-hover", "current-card", "nav-hover"], 4.5),
    "text-muted":      (TEXT_SURF + ["selection-bg", "row-hover"], 4.5),
    "link":            (TEXT_SURF + ["selection-bg", "row-hover"], 4.5),
    "accent-text":     (TEXT_SURF + ["selection-bg", "row-hover"], 4.5),
    "accent-icon":     (TEXT_SURF, 3.0),
    "accent-ui":       (TEXT_SURF + ["surface-2", "selected-bg", "row-hover"], 3.0),
    "accent-label":    (["bg-crust"], 4.5),
    "success-label":   (["bg-crust"], 4.5),
    "special-marker":  (["selected-bg", "bg-mantle", "bg-crust"], 3.0),
    "on-accent":       (["accent"], 4.5),
    "on-nav-fill":     (["nav-fill"], 4.5),
    "on-danger":       (["danger-fill"], 4.5),
    "on-success":      (["success-fill"], 4.5),
    "danger":          (TEXT_SURF, 3.0), "warning": (TEXT_SURF, 3.0), "success": (TEXT_SURF, 3.0),
    "special":         (TEXT_SURF, 3.0), "highlight": (TEXT_SURF, 3.0),
    "danger-text":     (TEXT_SURF, 4.5), "success-text": (TEXT_SURF, 4.5), "warning-text": (TEXT_SURF, 4.5),
    "control-border":  (["bg-base", "bg-mantle", "surface-1"], 3.0),
    "control-off":     (["bg-base", "bg-mantle", "surface-1"], 3.0),
    "scroll-thumb":    (["bg-base", "bg-mantle", "bg-crust"], 3.0),
}
# roles that resolve to other roles (Aurora / Cider indirections)
ALIASES = {"nav-icon": "accent-icon", "loved": "danger", "star": "highlight", "chip-color": "accent-text",
           "lyric-sweep": "highlight", "lyric-sung": "accent-text", "lyric-active": "text",
           "selected-marker": "special-marker", "pill-color": "text"}
# Snow Storm on artwork/scrims and the fixed dark immersive context are checked separately
EXEMPT = {"systemSecondary-onDark", "text-on-art"}
DECL_RE = re.compile(r"(?<![-\w])(color|fill|outline-color|--defaultColor|--gradientColor|--pill-color)\s*:\s*([^;}]+)")

def check_roles(css, name, mode_toks):
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    body = re.sub(r"@font-face\s*\{[^}]*\}", "", body)
    # immersive overrides its own tokens (fixed dark context, checked in mode_tokens)
    body = re.sub(r"\[class\*='immersive-player'\] \{[^}]*\}", "", body)
    for prop, val in DECL_RE.findall(body):
        for tok in re.findall(r"var\(--([\w-]+)", val):
            tok = ALIASES.get(tok, tok)
            if tok in EXEMPT or tok in ("keyColor", "musicKeyColor"):
                continue
            if tok not in ROLES:
                raise SystemExit(f"{name}: '{prop}: {val.strip()[:50]}' uses --{tok}, which has no role (fg/bg pair) in ROLES")
    for mode, t in mode_toks.items():
        for role, (bgs, tgt) in ROLES.items():
            for bg in bgs:
                check(f"{mode} role {role}/{bg}", t[role], t[bg], tgt)

# ---------------------------------------------------------------- live selector check (F13)
LIVE_IDS = HERE / "tools" / "cider-live-identifiers.txt.gz"
OWN = {"nord-pop", "nord-fade"}

def check_live_selectors(files):
    import gzip
    if not LIVE_IDS.exists():
        # The snapshot is extracted from Cider's own (closed-source) bundle, so it is
        # kept out of the public repo; maintainers keep it locally in tools/.
        print("note: tools/cider-live-identifiers.txt.gz not present, live selector check skipped")
        return
    ids = set(gzip.open(LIVE_IDS, "rt").read().split())
    dead = []
    for name, css in files.items():
        if not name.endswith(".css"):
            continue
        body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        body = re.sub(r"@font-face\s*\{[^}]*\}", "", body)
        sels = " ".join(re.findall(r"([^{};]+)\{", body))
        for c in set(re.findall(r"\.([A-Za-z_][\w-]*)", sels)) | set(re.findall(r"sfc-name='([^']+)'", sels)):
            if c not in ids and c not in OWN and not re.fullmatch(r"\d+\w*", c):
                dead.append(f"{name}: {c}")
    if dead:
        raise SystemExit("selectors not present in the pinned live Cider snapshot:\n  " + "\n  ".join(sorted(dead)))


# ---------------------------------------------------------------- context scopes
# Rules outside the token blocks may redefine surface/text tokens only for these self-contained
# contexts. A wrapper that can contain normal pages (e.g. Cider's .immersive-layer, which holds the
# whole app in immersive mode) must never get them: that made light-mode text Snow Storm on Snow Storm.
CONTEXT_SCOPES = {"[class*='immersive-player']", "[sfc-name='Sidebar']"}
CONTEXT_TOKENS = {"text", "text-2", "text-muted", "bg-base", "bg-mantle", "surface-1", "surface-2", "textDefault", "systemPrimary"}

def check_context_scopes(css, name):
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    body = re.sub(r"@font-face\s*\{[^}]*\}", "", body)
    for m in re.finditer(r"([^{};]+)\{([^{}]*)\}", body):
        sel = m.group(1).strip()
        if "body--" in sel:
            continue
        toks = set(re.findall(r"--([\w-]+)\s*:", m.group(2))) & CONTEXT_TOKENS
        if toks and sel not in CONTEXT_SCOPES:
            raise SystemExit(f"{name}: '{sel[:70]}' redefines {sorted(toks)} outside an allowed context scope")

REQUIRED_SELECTORS = ["[class*='immersive-player'] {", ".notification-center", ".q-menu > .notification-center", ".remove-item-button",
    ".queue-info-bar", ".profile-tab", ".blur-surface", ".new-shell-page-container", ".frow.library-song-item.alt-row",
    ".nav-button-content", "::-webkit-scrollbar-thumb", ".gallery-item-card", "[sfc-name='AlbumPlaybackActions'] .c-btn"]

def main():
    tokens = {m: mode_tokens(m) for m in ("dark", "light")}
    files = {"main.css": base_css(tokens), "aurora.css": aurora_css(tokens)}
    for slug, label, idx in ACCENTS[1:]:
        files[f"accent-{slug}.css"] = accent_css(slug, label, idx)
    files["theme.yml"] = theme_yml()

    for name, text in files.items():
        if name.endswith(".css"):
            assert_token_only_modes(text, name)
    assert_mode_geometry(tokens)
    for name, text in files.items():
        if name.endswith('.css'):
            check_context_scopes(text, name)
    check_live_selectors(files)
    accent_sets = {"frost": tokens}
    for slug, label, idx in ACCENTS[1:]:
        accent_sets[slug] = {m: {**tokens[m], **accent_tokens(NORD[idx], m)} for m in ("dark", "light")}
    accent_sets["high-contrast"] = {m: {**tokens[m], **HC[m]} for m in ("dark", "light")}
    for slug, toks in accent_sets.items():
        for name in ("main.css", "aurora.css"):
            check_roles(files[name], f"{name}+{slug}", toks)
    missing = [sel for sel in REQUIRED_SELECTORS if sel not in files["main.css"]]
    if missing:
        raise SystemExit(f"main.css lost required component rules: {missing}")
    bad = [c for c in CHECKS if c[3] < c[4] - 1e-9]
    worst = {}
    for label, fg, bg, r, tgt in CHECKS:
        key = label.split(" ", 1)[1]
        if key not in worst or r < worst[key][0]:
            worst[key] = (r, label, fg, bg, tgt)
    if "--report" in sys.argv:
        for key, (r, label, fg, bg, tgt) in sorted(worst.items()):
            print(f"  min {key:28s} {r:5.2f}:1 (target {tgt}) worst={label} {fg} on {bg}")
    if bad:
        for b in bad:
            print("FAIL", b)
        raise SystemExit(1)

    (HERE / "preview").mkdir(exist_ok=True)
    for name, text in files.items():
        (HERE / name).write_text(text)
        if name.endswith(".css"):
            (HERE / "preview" / name).write_text(importantize(text))
    print(f"built {len(files)} files, {len(CHECKS)} contrast checks passed")

if __name__ == "__main__":
    main()
