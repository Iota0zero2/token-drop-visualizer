#!/usr/bin/env python3
"""Token Drop Visualizer.

Visualizes the odds of a token dropping from a chest (default 1 in 137,000)
for a party grinding games. Pure tkinter, no third-party dependencies.

Run:  python3 token_drop.py
"""

import json
import math
import random
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

APP_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = APP_DIR / "settings.json"

# ----------------------------------------------------------------- theme --

C = {
    "bg": "#0a0d13",
    "panel": "#121721",
    "panel2": "#1a2130",
    "border": "#252d3d",
    "grid": "#1c2331",
    "text": "#e8edf5",
    "muted": "#8d97a8",
    "dim": "#596377",
    "accent": "#4da3ff",
    "accent_fill": "#10213a",
    "accent2": "#b48cff",
    "gold": "#f5c451",
    "green": "#3fd68a",
    "red": "#ff6b81",
}

F = {}  # fonts, filled in once the Tk root exists

SLIDERS = [
    # key, label, unit suffix, color
    ("players", "Players per party", "", "accent"),
    ("chests", "Chests per player per game", "", "gold"),
    ("length", "Game length", " min", "green"),
    ("hours", "Hours played per day", " h", "accent2"),
]

DEFAULTS = {
    "odds": 137000,
    "sliders": {
        "players": {"min": 1, "max": 4, "step": 1, "value": 4},
        "chests": {"min": 1, "max": 50, "step": 1, "value": 30},
        "length": {"min": 5, "max": 120, "step": 1, "value": 30},
        "hours": {"min": 0.5, "max": 16, "step": 0.5, "value": 3},
    },
}


# --------------------------------------------------------------- helpers --

def load_settings():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        if float(data.get("odds", 0)) > 1:
            cfg["odds"] = float(data["odds"])
        for key, s in data.get("sliders", {}).items():
            if key in cfg["sliders"]:
                for field in ("min", "max", "step", "value"):
                    if field in s:
                        cfg["sliders"][key][field] = float(s[field])
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return cfg


def save_settings(cfg):
    try:
        SETTINGS_FILE.write_text(json.dumps(cfg, indent=2))
    except OSError:
        pass


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(a, b, t):
    """Mix color a toward b by t (0..1)."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = hex_rgb(a)
    rb, gb, bb = hex_rgb(b)
    return "#%02x%02x%02x" % (round(ra + (rb - ra) * t),
                              round(ga + (gb - ga) * t),
                              round(ba + (bb - ba) * t))


def heat(p):
    """Color for a probability: blue -> purple -> gold."""
    if p < 0.5:
        return blend(C["accent"], C["accent2"], p / 0.5)
    return blend(C["accent2"], C["gold"], (p - 0.5) / 0.5)


def fmt_num(v):
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def fmt_plain(v):
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def fmt_pct(x):
    v = x * 100
    if v >= 99.995:
        return ">99.99%"
    if v >= 10:
        return f"{v:.1f}%"
    if v >= 1:
        return f"{v:.2f}%"
    if v >= 0.01:
        return f"{v:.3f}%"
    if v <= 0:
        return "0%"
    s = f"{v:.7f}".rstrip("0").rstrip(".")
    return "<0.0000001%" if s == "0" else s + "%"


def one_in(x):
    if x <= 0:
        return "never"
    n = 1 / x
    if n < 1.005:
        return "≈ certain"
    return f"1 in {n:,.0f}" if n >= 10 else f"1 in {n:.2f}"


def fmt_duration(days, hours_per_day):
    """Human readable duration where one 'day' = one day of playing."""
    if days == math.inf:
        return "never"
    if days < 1:
        h = days * hours_per_day
        return f"{h * 60:.0f} min played" if h < 1 else f"{h:.1f} h played"
    if days < 90:
        return f"{days:,.1f} days"
    if days < 730:
        return f"{days / 30.44:,.1f} months"
    return f"{days / 365.25:,.1f} years"


def nice_step(span, target=6):
    if span <= 0:
        return 1
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= raw:
            return m * mag
    return 10 * mag


def pick_unit(max_days, hours_per_day):
    if max_days < 1.5:
        return "hours played", hours_per_day
    if max_days <= 400:
        return "days", 1
    if max_days <= 1500:
        return "months", 1 / 30.44
    return "years", 1 / 365.25


# ------------------------------------------------------------- widgets --

class FlatButton(tk.Label):
    def __init__(self, master, text, command, color=None, **kw):
        self.base = kw.pop("bg", C["panel2"])
        self.hover = blend(self.base, color or C["accent"], 0.25)
        super().__init__(master, text=text, bg=self.base,
                         fg=color or C["text"], font=F["btn"],
                         padx=14, pady=9, cursor="hand2", **kw)
        self.command = command
        self.bind("<Enter>", lambda e: self.config(bg=self.hover))
        self.bind("<Leave>", lambda e: self.config(bg=self.base))
        self.bind("<Button-1>", lambda e: self.command())


class Slider(tk.Canvas):
    """Smooth canvas slider: drag, click, or scroll. Fires on every change."""

    H = 78
    PAD = 16

    def __init__(self, master, label, unit, color, cfg, on_change):
        super().__init__(master, height=self.H, bg=C["panel"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.label, self.unit, self.color = label, unit, color
        self.min, self.max, self.step = cfg["min"], cfg["max"], cfg["step"]
        self.value = self.snap(cfg["value"])
        self.on_change = on_change
        self.active = False
        self.hovering = False
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", lambda e: self._from_x(e.x))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda e: self.set(self.value + self.step))
        self.bind("<Button-5>", lambda e: self.set(self.value - self.step))

    def snap(self, v):
        v = min(max(v, self.min), self.max)
        if self.step > 0:
            v = self.min + round((v - self.min) / self.step) * self.step
        return round(min(v, self.max), 9)

    def set_range(self, mn, mx, step):
        self.min, self.max, self.step = mn, mx, step
        self.value = self.snap(self.value)
        self.redraw()

    def set(self, v):
        v = self.snap(v)
        if v != self.value:
            self.value = v
            self.redraw()
            self.on_change()

    def _track(self):
        return self.PAD + 8, self.winfo_width() - self.PAD - 8

    def _from_x(self, x):
        x0, x1 = self._track()
        frac = (x - x0) / max(1, x1 - x0)
        self.set(self.min + max(0, min(1, frac)) * (self.max - self.min))

    def _press(self, e):
        self.active = True
        self._from_x(e.x)
        self.redraw()

    def _release(self, e):
        self.active = False
        self.redraw()

    def _hover(self, on):
        self.hovering = on
        self.redraw()

    def _wheel(self, e):
        if e.delta:
            self.set(self.value + (self.step if e.delta > 0 else -self.step))

    def redraw(self):
        self.delete("all")
        w = self.winfo_width()
        if w < 40:
            return
        col = C[self.color]
        p = self.PAD
        self.create_oval(p, 14, p + 8, 22, fill=col, outline="")
        self.create_text(p + 16, 18, text=self.label, anchor="w",
                         fill=C["muted"], font=F["label"])
        self.create_text(w - p, 18, text=fmt_num(self.value) + self.unit,
                         anchor="e", fill=C["text"], font=F["value"])
        x0, x1 = self._track()
        y = 48
        span = self.max - self.min
        frac = (self.value - self.min) / span if span > 0 else 0
        x = x0 + frac * (x1 - x0)
        self.create_line(x0, y, x1, y, width=6, fill=C["border"],
                         capstyle="round")
        # glowing gradient fill
        segs = 24
        for i in range(segs):
            a = x0 + (x - x0) * i / segs
            b = x0 + (x - x0) * (i + 1) / segs
            self.create_line(a, y, b, y, width=6, capstyle="round",
                             fill=blend(blend(col, C["panel"], 0.55), col,
                                        (i + 1) / segs))
        if self.active or self.hovering:
            r = 13 if self.active else 11
            self.create_oval(x - r, y - r, x + r, y + r, outline="",
                             fill=blend(col, C["panel"], 0.75))
        self.create_oval(x - 8, y - 8, x + 8, y + 8, fill=C["text"],
                         outline=col, width=3)
        self.create_text(x0, 68, text=fmt_num(self.min), anchor="w",
                         fill=C["dim"], font=F["tiny"])
        self.create_text(x1, 68, text=fmt_num(self.max), anchor="e",
                         fill=C["dim"], font=F["tiny"])


class Card(tk.Frame):
    def __init__(self, master, title, color):
        super().__init__(master, bg=C["panel"], highlightthickness=1,
                         highlightbackground=C["border"])
        tk.Frame(self, bg=C[color], height=3).pack(fill="x")
        inner = tk.Frame(self, bg=C["panel"], padx=16, pady=12)
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text=title.upper(), bg=C["panel"], fg=C["muted"],
                 font=F["tiny_b"], anchor="w").pack(fill="x")
        self.value = tk.Label(inner, text="–", bg=C["panel"], fg=C["text"],
                              font=F["card"], anchor="w")
        self.value.pack(fill="x", pady=(4, 0))
        self.sub = tk.Label(inner, text="", bg=C["panel"], fg=C["dim"],
                            font=F["small"], anchor="w")
        self.sub.pack(fill="x")

    def set(self, value, sub):
        self.value.config(text=value)
        self.sub.config(text=sub)


class ChartBase(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, bg=C["panel"], highlightthickness=1,
                         highlightbackground=C["border"], bd=0)
        self.app = app
        self.bind("<Configure>", lambda e: self.redraw())

    def title(self, text, sub):
        self.create_text(20, 24, text=text, anchor="w", fill=C["text"],
                         font=F["h2"])
        self.create_text(20, 44, text=sub, anchor="w", fill=C["muted"],
                         font=F["small"])


class CdfChart(ChartBase):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.mouse = None
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", self._leave)

    def _motion(self, e):
        self.mouse = (e.x, e.y)
        self.redraw()

    def _leave(self, e):
        self.mouse = None
        self.redraw()

    def redraw(self):
        self.delete("all")
        m = self.app.model
        w, h = self.winfo_width(), self.winfo_height()
        if m is None or w < 120 or h < 120:
            return
        self.title("Chance of at least one token",
                   "cumulative probability vs. time spent grinding"
                   " — hover to inspect")

        # legend
        lx = w - 24
        items = [("Whole party", C["accent"])]
        for name, col in items:
            tid = self.create_text(lx, 26, text=name, anchor="e",
                                   fill=C["muted"], font=F["small"])
            x0 = self.bbox(tid)[0]
            self.create_line(x0 - 28, 26, x0 - 8, 26, fill=col, width=3,
                             capstyle="round")
            lx = x0 - 44

        rate, lp = m["rate"], m["lp"]
        if rate <= 0:
            self.create_text(w / 2, h / 2, fill=C["muted"], font=F["h2"],
                             text="No chests opened → no token. Ever.")
            return

        L, R, T, B = 66, 30, 72, 46
        pw, ph = w - L - R, h - T - B
        xmax = m["days_for"](0.99, rate)
        if m["sim_days"] is not None:
            xmax = max(xmax, m["sim_days"] * 1.08)
        unit, factor = pick_unit(xmax, m["hours"])

        def X(d):
            return L + pw * d / xmax

        def Y(p):
            return T + ph * (1 - p)

        # grid
        for q in (0, 0.25, 0.5, 0.75, 1):
            y = Y(q)
            self.create_line(L, y, L + pw, y, fill=C["grid"])
            self.create_text(L - 10, y, text=f"{int(q * 100)}%", anchor="e",
                             fill=C["dim"], font=F["tiny"])
        step = nice_step(xmax * factor)
        t = 0.0
        while t <= xmax * factor * 1.0001:
            x = X(t / factor)
            self.create_line(x, T, x, T + ph, fill=C["grid"])
            self.create_text(x, T + ph + 14, text=fmt_num(round(t, 6)),
                             fill=C["dim"], font=F["tiny"])
            t += step
        self.create_text(L + pw, T + ph + 32, text=unit, anchor="e",
                         fill=C["muted"], font=F["small"])
        self.create_line(L, T + ph, L + pw, T + ph, fill=C["border"], width=2)

        # curves
        N = 240

        def curve(r):
            pts = []
            for i in range(N + 1):
                d = xmax * i / N
                pts += [X(d), Y(-math.expm1(r * d * lp))]
            return pts

        party = curve(rate)
        # layered fill for a soft gradient look
        self.create_polygon(party + [X(xmax), Y(0), X(0), Y(0)],
                            fill=C["accent_fill"], outline="")
        self.create_line(party, fill=blend(C["accent"], C["panel"], 0.6),
                         width=7, smooth=True)
        self.create_line(party, fill=C["accent"], width=3, smooth=True)

        # milestones
        for q, col in ((0.5, C["green"]), (0.9, C["gold"]), (0.99, C["red"])):
            d = m["days_for"](q, rate)
            x, y = X(d), Y(q)
            self.create_line(x, Y(0), x, y, fill=col, dash=(3, 4))
            self.create_line(L, y, x, y, fill=blend(col, C["panel"], 0.6),
                             dash=(3, 4))
            self.create_oval(x - 5, y - 5, x + 5, y + 5, fill=col,
                             outline=C["panel"], width=2)
            right = x > L + pw * 0.8
            self.create_text(x + (-10 if right else 10), y + 14,
                             anchor="ne" if right else "nw",
                             text=f"{int(q * 100)}% · "
                                  f"{fmt_duration(d, m['hours'])}",
                             fill=col, font=F["small_b"])

        # simulated roll
        if m["sim_days"] is not None:
            sd = m["sim_days"]
            sp = -math.expm1(m["sim_chests"] * lp)
            x, y = X(sd), Y(sp)
            self.create_line(x, T - 6, x, T + ph, fill=C["gold"], width=2)
            self.create_polygon(x, y - 9, x + 9, y, x, y + 9, x - 9, y,
                                fill=C["gold"], outline=C["panel"], width=2)
            right = x > L + pw * 0.75
            self.create_text(x + (-8 if right else 8), T - 2,
                             anchor="ne" if right else "nw",
                             text=f"★ simulated drop: "
                                  f"{fmt_duration(sd, m['hours'])}",
                             fill=C["gold"], font=F["small_b"])

        # hover crosshair + tooltip
        if self.mouse and L <= self.mouse[0] <= L + pw and \
                T - 20 <= self.mouse[1] <= T + ph + 10:
            mx = self.mouse[0]
            d = (mx - L) / pw * xmax
            pp = -math.expm1(rate * d * lp)
            self.create_line(mx, T, mx, T + ph, fill=C["muted"], dash=(2, 3))
            self.create_oval(mx - 6, Y(pp) - 6, mx + 6, Y(pp) + 6,
                             fill=C["accent"], outline=C["text"], width=2)
            lines = [f"{fmt_duration(d, m['hours'])}"
                     f"  ({d * m['hours']:,.0f} h played)",
                     f"Party   {fmt_pct(pp)}"]
            lines.append(f"Chests  {rate * d:,.0f}")
            right = mx > L + pw * 0.6
            tx = mx - 16 if right else mx + 16
            ty = max(T + 4, min(Y(pp) - 30, T + ph - 90))
            tid = self.create_text(tx, ty, text="\n".join(lines),
                                   anchor="ne" if right else "nw",
                                   fill=C["text"], font=F["mono"])
            x0, y0, x1, y1 = self.bbox(tid)
            rid = self.create_rectangle(x0 - 10, y0 - 8, x1 + 10, y1 + 8,
                                        fill=C["panel2"],
                                        outline=C["border"])
            self.tag_lower(rid, tid)


class BarsChart(ChartBase):
    def redraw(self):
        self.delete("all")
        m = self.app.model
        w, h = self.winfo_width(), self.winfo_height()
        if m is None or w < 120 or h < 100:
            return
        self.title("Party odds by time frame",
                   "probability the party gets a token")
        rows = [
            ("1 chest", 1),
            ("1 game", m["chests_game"]),
            ("1 hour", m["chests_hour"]),
            ("1 day", m["rate"]),
            ("1 week", m["rate"] * 7),
            ("30 days", m["rate"] * 30),
            ("1 year", m["rate"] * 365),
        ]
        top, bottom = 68, h - 16
        rh = (bottom - top) / len(rows)
        lx, bx0, bx1 = 20, 96, w - 20
        bar_h = max(8, min(22, rh * 0.55))
        for i, (name, n) in enumerate(rows):
            p = -math.expm1(n * m["lp"]) if n > 0 else 0
            yc = top + rh * (i + 0.5)
            self.create_text(lx, yc, text=name, anchor="w", fill=C["muted"],
                             font=F["small"])
            self.create_rectangle(bx0, yc - bar_h / 2, bx1, yc + bar_h / 2,
                                  fill=C["panel2"], outline="")
            bw = (bx1 - bx0) * p
            if bw > 0.5:
                col = heat(p)
                self.create_rectangle(bx0, yc - bar_h / 2, bx0 + bw,
                                      yc + bar_h / 2, fill=col, outline="")
                self.create_rectangle(bx0 + bw - 2, yc - bar_h / 2, bx0 + bw,
                                      yc + bar_h / 2, fill=C["text"],
                                      outline="")
            label = f"{fmt_pct(p)}   {one_in(p)}"
            inside = bw > (bx1 - bx0) * 0.55
            self.create_text(bx0 + bw - 8 if inside else max(bx0 + bw + 8,
                                                              bx0 + 8),
                             yc, text=label, anchor="e" if inside else "w",
                             fill=C["bg"] if inside else C["text"],
                             font=F["small_b"])


class Gauge(ChartBase):
    PERIODS = [("1 day", 1), ("1 week", 7), ("30 days", 30),
               ("90 days", 90), ("1 year", 365)]

    def __init__(self, master, app):
        super().__init__(master, app)
        self.idx = 2
        self.config(cursor="hand2")
        self.bind("<Button-1>", self._next)

    def _next(self, e):
        self.idx = (self.idx + 1) % len(self.PERIODS)
        self.redraw()

    def redraw(self):
        self.delete("all")
        m = self.app.model
        w, h = self.winfo_width(), self.winfo_height()
        if m is None or w < 120 or h < 140:
            return
        name, days = self.PERIODS[self.idx]
        self.title("Luck meter", "click to change time frame")
        p = -math.expm1(m["rate"] * days * m["lp"])
        cx, cy = w / 2, 60 + (h - 60) / 2 - 10
        r = max(30, min(w / 2 - 30, (h - 60) / 2 - 30))
        thick = max(10, r * 0.16)
        box = (cx - r, cy - r, cx + r, cy + r)
        self.create_oval(*box, outline=C["panel2"], width=thick)
        # tick marks
        for k in range(40):
            a = math.radians(90 - k * 9)
            r1, r2 = r + thick / 2 + 4, r + thick / 2 + (9 if k % 10 == 0 else 6)
            self.create_line(cx + r1 * math.cos(a), cy - r1 * math.sin(a),
                             cx + r2 * math.cos(a), cy - r2 * math.sin(a),
                             fill=C["border"] if k % 10 else C["dim"])
        if p > 0:
            # draw in segments so the arc shifts color along its length
            segs = max(1, int(60 * p))
            for s in range(segs):
                a0 = 90 - 359.99 * p * s / segs
                ext = -359.99 * p / segs - (0.6 if s < segs - 1 else 0)
                self.create_arc(*box, start=a0, extent=ext, style="arc",
                                outline=heat(p * (s + 1) / segs), width=thick)
        self.create_text(cx, cy - r * 0.12, text=fmt_pct(p), fill=heat(p),
                         font=(F["big"][0], int(max(14, min(34, r * 0.32))),
                               "bold"))
        self.create_text(cx, cy + r * 0.22, text=f"within {name}",
                         fill=C["muted"], font=F["small"])
        self.create_text(cx, h - 18, text=one_in(p), fill=C["dim"],
                         font=F["small"])


# --------------------------------------------------------------- settings --

class SettingsDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Settings")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.transient(app.root)

        body = tk.Frame(self, bg=C["bg"], padx=28, pady=24)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Settings", font=F["h1"], fg=C["text"],
                 bg=C["bg"]).grid(row=0, column=0, columnspan=4, sticky="w")
        tk.Label(body, text="Slider ranges", font=F["small_b"], fg=C["muted"],
                 bg=C["bg"]).grid(row=1, column=0, columnspan=4, sticky="w",
                                  pady=(14, 6))
        for c, head in enumerate(("Min", "Max", "Step"), start=1):
            tk.Label(body, text=head, font=F["tiny_b"], fg=C["dim"],
                     bg=C["bg"]).grid(row=2, column=c, sticky="e", padx=4)

        self.entries = {}
        for i, (key, label, unit, color) in enumerate(SLIDERS):
            s = app.cfg["sliders"][key]
            row = 3 + i
            lf = tk.Frame(body, bg=C["bg"])
            lf.grid(row=row, column=0, sticky="w", pady=5, padx=(0, 16))
            tk.Frame(lf, bg=C[color], width=8, height=8).pack(side="left",
                                                              padx=(0, 8))
            tk.Label(lf, text=label + (f" ({unit.strip()})" if unit else ""),
                     font=F["label"], fg=C["text"], bg=C["bg"]).pack(
                side="left")
            self.entries[key] = []
            for c, field in enumerate(("min", "max", "step"), start=1):
                e = self._entry(body, s[field])
                e.grid(row=row, column=c, padx=4, pady=5)
                self.entries[key].append(e)

        tk.Label(body, text="Drop rate", font=F["small_b"], fg=C["muted"],
                 bg=C["bg"]).grid(row=8, column=0, columnspan=4, sticky="w",
                                  pady=(18, 6))
        tk.Label(body, text="Chance per chest:  1 in", font=F["label"],
                 fg=C["text"], bg=C["bg"]).grid(row=9, column=0, sticky="w")
        self.odds = self._entry(body, app.cfg["odds"], width=12)
        self.odds.grid(row=9, column=1, columnspan=2, sticky="w", padx=4)

        self.error = tk.Label(body, text="", font=F["small"], fg=C["red"],
                              bg=C["bg"])
        self.error.grid(row=10, column=0, columnspan=4, sticky="w",
                        pady=(12, 0))

        btns = tk.Frame(body, bg=C["bg"])
        btns.grid(row=11, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        FlatButton(btns, "Reset defaults", self.reset,
                   color=C["muted"]).pack(side="left")
        FlatButton(btns, "Save", self.save,
                   color=C["accent"]).pack(side="right")
        FlatButton(btns, "Cancel", self.destroy,
                   color=C["muted"]).pack(side="right", padx=8)

        self.bind("<Return>", lambda e: self.save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _entry(self, master, value, width=8):
        e = tk.Entry(master, width=width, bg=C["panel2"], fg=C["text"],
                     insertbackground=C["text"], relief="flat",
                     highlightthickness=1, highlightbackground=C["border"],
                     highlightcolor=C["accent"], font=F["mono"],
                     justify="right")
        e.insert(0, fmt_plain(value))
        return e

    @staticmethod
    def _set(entry, value):
        entry.delete(0, "end")
        entry.insert(0, fmt_plain(value))

    def reset(self):
        for key, (emin, emax, estep) in self.entries.items():
            d = DEFAULTS["sliders"][key]
            self._set(emin, d["min"])
            self._set(emax, d["max"])
            self._set(estep, d["step"])
        self._set(self.odds, DEFAULTS["odds"])
        self.error.config(text="")

    def save(self):
        def num(entry, what):
            raw = entry.get().replace(",", "").replace("_", "").strip()
            try:
                v = float(raw)
            except ValueError:
                raise ValueError(f"{what}: '{entry.get()}' is not a number")
            if not math.isfinite(v):
                raise ValueError(f"{what}: must be a finite number")
            return v

        try:
            new = {}
            for key, label, unit, color in SLIDERS:
                emin, emax, estep = self.entries[key]
                mn = num(emin, f"{label} min")
                mx = num(emax, f"{label} max")
                st = num(estep, f"{label} step")
                if mn < 0:
                    raise ValueError(f"{label}: min can't be negative")
                if key == "length" and mn <= 0:
                    raise ValueError("Game length: min must be above 0")
                if mx <= mn:
                    raise ValueError(f"{label}: max must be greater than min")
                if st <= 0:
                    raise ValueError(f"{label}: step must be above 0")
                if st > mx - mn:
                    raise ValueError(f"{label}: step is larger than the range")
                new[key] = (mn, mx, st)
            odds = num(self.odds, "Drop rate")
            if odds <= 1:
                raise ValueError("Drop rate: must be greater than 1")
        except ValueError as exc:
            self.error.config(text=str(exc))
            return
        self.app.apply_settings(new, odds)
        self.destroy()


# -------------------------------------------------------------------- app --

class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_settings()
        self.model = None
        self.sim = None  # party chests needed until the drop
        self._pending = False
        self._init_fonts()

        root.title("Token Drop Visualizer")
        root.configure(bg=C["bg"])
        root.geometry("1380x880")
        root.minsize(1100, 720)
        self._build_menu()

        # sidebar
        side = tk.Frame(root, bg=C["panel"], width=340,
                        highlightthickness=1, highlightbackground=C["border"])
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        head = tk.Frame(side, bg=C["panel"], padx=16, pady=18)
        head.pack(fill="x")
        tk.Label(head, text="◆ Token Drop", font=F["h1"], fg=C["text"],
                 bg=C["panel"]).pack(anchor="w")
        self.odds_label = tk.Label(head, text="", font=F["small"],
                                   fg=C["gold"], bg=C["panel"])
        self.odds_label.pack(anchor="w", pady=(2, 0))

        self.sliders = {}
        for key, label, unit, color in SLIDERS:
            s = Slider(side, label, unit, color, self.cfg["sliders"][key],
                       self.request_update)
            s.pack(fill="x", pady=2)
            self.sliders[key] = s

        tk.Frame(side, bg=C["border"], height=1).pack(fill="x", padx=16,
                                                       pady=12)
        tk.Label(side, text="PARTY THROUGHPUT", font=F["tiny_b"],
                 fg=C["muted"], bg=C["panel"]).pack(anchor="w", padx=16)
        stats = tk.Frame(side, bg=C["panel"], padx=16, pady=6)
        stats.pack(fill="x")
        self.stat_labels = {}
        for i, (key, name) in enumerate((("game", "Chests / game"),
                                         ("gpd", "Games / day"),
                                         ("hour", "Chests / hour"),
                                         ("day", "Chests / day"))):
            tk.Label(stats, text=name, font=F["small"], fg=C["muted"],
                     bg=C["panel"]).grid(row=i, column=0, sticky="w", pady=2)
            lbl = tk.Label(stats, text="", font=F["mono"], fg=C["text"],
                           bg=C["panel"])
            lbl.grid(row=i, column=1, sticky="e", pady=2)
            self.stat_labels[key] = lbl
        stats.columnconfigure(1, weight=1)

        btns = tk.Frame(side, bg=C["panel"], padx=16, pady=10)
        btns.pack(fill="x")
        FlatButton(btns, "🎲  Simulate a grind", self.simulate,
                   color=C["gold"]).pack(fill="x")
        row = tk.Frame(btns, bg=C["panel"])
        row.pack(fill="x", pady=(8, 0))
        FlatButton(row, "Clear", self.clear_sim,
                   color=C["muted"]).pack(side="left", fill="x", expand=True)
        FlatButton(row, "⚙  Settings", self.open_settings,
                   color=C["accent"]).pack(side="left", fill="x",
                                           expand=True, padx=(8, 0))
        self.sim_label = tk.Label(side, text="", font=F["small"],
                                  fg=C["muted"], bg=C["panel"],
                                  justify="left", wraplength=300, anchor="w")
        self.sim_label.pack(fill="x", padx=16, pady=(6, 0))

        # main area
        main = tk.Frame(root, bg=C["bg"], padx=18, pady=18)
        main.pack(side="left", fill="both", expand=True)

        cards = tk.Frame(main, bg=C["bg"])
        cards.pack(fill="x")
        self.cards = {}
        for i, (key, title, color) in enumerate((
                ("game", "Per game", "accent"),
                ("day", "Per day", "accent2"),
                ("half", "50% chance after", "green"),
                ("ninety", "90% chance after", "gold"),
                ("mean", "Average wait", "red"))):
            card = Card(cards, title, color)
            card.grid(row=0, column=i, sticky="nsew",
                      padx=(0 if i == 0 else 10, 0))
            cards.columnconfigure(i, weight=1, uniform="cards")
            self.cards[key] = card

        self.cdf = CdfChart(main, self)
        self.cdf.pack(fill="both", expand=True, pady=(16, 16))

        bottom = tk.Frame(main, bg=C["bg"], height=290)
        bottom.pack(fill="x")
        bottom.pack_propagate(False)
        self.bars = BarsChart(bottom, self)
        self.bars.pack(side="left", fill="both", expand=True)
        self.gauge = Gauge(bottom, self)
        self.gauge.config(width=300)
        self.gauge.pack(side="left", fill="y", padx=(16, 0))

        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.update_all()

    # ---------------------------------------------------------- setup --

    def _init_fonts(self):
        fams = set(tkfont.families(self.root))

        def pick(*names):
            for n in names:
                if n in fams:
                    return n
            return "TkDefaultFont"

        sans = pick("SF Pro Display", "SF Pro Text", "Helvetica Neue",
                    "Segoe UI", "Inter", "Helvetica", "Arial")
        mono = pick("SF Mono", "Menlo", "JetBrains Mono", "Consolas",
                    "DejaVu Sans Mono", "Courier")
        F.update({
            "h1": (sans, 22, "bold"),
            "h2": (sans, 15, "bold"),
            "label": (sans, 12),
            "value": (mono, 14, "bold"),
            "small": (sans, 11),
            "small_b": (sans, 11, "bold"),
            "tiny": (sans, 10),
            "tiny_b": (sans, 10, "bold"),
            "card": (sans, 21, "bold"),
            "big": (sans, 30, "bold"),
            "mono": (mono, 12),
            "btn": (sans, 13, "bold"),
        })

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        mod = "Command" if sys.platform == "darwin" else "Control"
        acc = "Cmd" if sys.platform == "darwin" else "Ctrl"
        app_menu = tk.Menu(menubar, tearoff=False)
        app_menu.add_command(label="Settings…", accelerator=f"{acc}+,",
                             command=self.open_settings)
        app_menu.add_command(label="Simulate a grind", accelerator=f"{acc}+R",
                             command=self.simulate)
        app_menu.add_separator()
        app_menu.add_command(label="Quit", accelerator=f"{acc}+Q",
                             command=self.quit)
        menubar.add_cascade(label="Token", menu=app_menu)
        self.root.config(menu=menubar)
        self.root.bind(f"<{mod}-comma>", lambda e: self.open_settings())
        self.root.bind(f"<{mod}-r>", lambda e: self.simulate())
        self.root.bind(f"<{mod}-q>", lambda e: self.quit())
        if sys.platform == "darwin":
            try:  # hooks the native "Settings…" item in the macOS app menu
                self.root.createcommand("tk::mac::ShowPreferences",
                                        self.open_settings)
            except tk.TclError:
                pass

    # -------------------------------------------------------- actions --

    def open_settings(self):
        SettingsDialog(self)

    def apply_settings(self, ranges, odds):
        self.cfg["odds"] = odds
        for key, (mn, mx, st) in ranges.items():
            self.sliders[key].set_range(mn, mx, st)
            self.cfg["sliders"][key].update(min=mn, max=mx, step=st)
        self._persist()
        self.update_all()

    def simulate(self):
        p = 1 / self.cfg["odds"]
        u = 1 - random.random()  # (0, 1]
        chests = max(1, math.ceil(math.log(u) / math.log1p(-p)))
        self.sim = chests
        self.update_all()

    def clear_sim(self):
        self.sim = None
        self.update_all()

    def _persist(self):
        for key, s in self.sliders.items():
            self.cfg["sliders"][key]["value"] = s.value
        save_settings(self.cfg)

    def quit(self):
        self._persist()
        self.root.destroy()

    # --------------------------------------------------------- update --

    def request_update(self):
        if not self._pending:
            self._pending = True
            self.root.after_idle(self.update_all)

    def update_all(self):
        self._pending = False
        v = {k: s.value for k, s in self.sliders.items()}
        odds = self.cfg["odds"]
        p = 1 / odds
        lp = math.log1p(-p)
        players, chests, length, hours = (v["players"], v["chests"],
                                          v["length"], v["hours"])
        chests_game = players * chests
        games_day = hours * 60 / length
        rate = chests_game * games_day

        def days_for(q, r):
            return math.log1p(-q) / lp / r if r > 0 else math.inf

        sim_days = None
        if self.sim and rate > 0:
            sim_days = self.sim / rate
        self.model = dict(players=players, chests=chests, length=length,
                          hours=hours, p=p, lp=lp, odds=odds,
                          chests_game=chests_game,
                          chests_hour=chests_game * 60 / length,
                          rate=rate, days_for=days_for,
                          sim_days=sim_days,
                          sim_chests=self.sim or 0)

        # header + sidebar stats
        self.odds_label.config(text=f"Drop chance per chest: 1 in {odds:,.0f}"
                                    f"  ({fmt_pct(p)})")
        self.stat_labels["game"].config(text=fmt_num(chests_game))
        self.stat_labels["gpd"].config(text=f"{games_day:,.2f}")
        self.stat_labels["hour"].config(text=f"{chests_game * 60 / length:,.1f}")
        self.stat_labels["day"].config(text=f"{rate:,.0f}")

        # cards
        pg = -math.expm1(chests_game * lp)
        pd = -math.expm1(rate * lp)
        self.cards["game"].set(fmt_pct(pg), one_in(pg))
        self.cards["day"].set(fmt_pct(pd), one_in(pd))
        for key, q in (("half", 0.5), ("ninety", 0.9)):
            d = days_for(q, rate)
            sub = (f"{d * hours:,.0f} h · {d * games_day:,.0f} games"
                   if d != math.inf else "")
            self.cards[key].set(fmt_duration(d, hours), sub)
        mean = odds / rate if rate > 0 else math.inf
        self.cards["mean"].set(fmt_duration(mean, hours),
                               f"{odds:,.0f} chests on average")

        # simulation text
        if self.sim:
            n = self.sim
            luck = -math.expm1(n * lp)
            if rate > 0:
                self.sim_label.config(
                    fg=C["gold"],
                    text=f"★ Token dropped after {n:,} party chests — "
                         f"{fmt_duration(n / rate, hours)} "
                         f"({n / rate * hours:,.0f} h played). "
                         f"Luckier than {(1 - luck) * 100:.0f}% of parties.")
            else:
                self.sim_label.config(fg=C["muted"],
                                      text="Open some chests first!")
        else:
            self.sim_label.config(text="")

        for chart in (self.cdf, self.bars, self.gauge):
            chart.redraw()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
