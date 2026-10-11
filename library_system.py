"""PDM Library Lending Books & Reservation System.

Single-file Tkinter application: catalog search, checkout/return, reservations,
overdue reminders with SDO escalation, and an admin dashboard.
"""

import os
import re
import sys
import random
import sqlite3
import hashlib
import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont

APP_NAME = "PDM Library"
SLOGAN = "Lending & Reservations"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "library.db")

MAROON_DARK = "#5A1220"
MAROON = "#7A122A"
MAROON_HOVER = "#8E1B33"
MAROON_SOFT = "#F3E7EA"
CREAM = "#F5F1EA"
CREAM_DEEP = "#EFE9DE"
WHITE = "#FFFFFF"
GOLD = "#C9A227"
GOLD_SOFT = "#FEF6E0"
INK = "#1F1B18"
MUTED = "#6B6259"
LINE = "#E5DDD1"
GREEN_BG, GREEN_FG = "#E7F5EC", "#1E7A45"
RED_BG, RED_FG = "#FDECEC", "#B3261E"
AMBER_BG, AMBER_FG = "#FEF6E0", "#B7791F"
BLUE_BG, BLUE_FG = "#E8F1FB", "#1D4ED8"
GREY_BG, GREY_FG = "#F0ECE5", "#5D564E"

HEAD = "Georgia"
BODY = "Segoe UI"

PILL_STYLES = {
    "available": (GREEN_BG, GREEN_FG),
    "good": (GREEN_BG, GREEN_FG),
    "completed": (GREEN_BG, GREEN_FG),
    "checked out": (RED_BG, RED_FG),
    "overdue": (RED_BG, RED_FG),
    "escalated": (RED_BG, RED_FG),
    "reserved": (AMBER_BG, AMBER_FG),
    "waiting": (AMBER_BG, AMBER_FG),
    "ready": (AMBER_BG, AMBER_FG),
    "due tomorrow": (RED_BG, RED_FG),
    "reminder": (AMBER_BG, AMBER_FG),
    "pending": (AMBER_BG, AMBER_FG),
    "sdo": (BLUE_BG, BLUE_FG),
    "acknowledged": (BLUE_BG, BLUE_FG),
    "returned": (GREY_BG, GREY_FG),
    "neutral": (GREY_BG, GREY_FG),
    "category": (MAROON_SOFT, MAROON),
}

COVER_COLORS = ["#33556E", "#6E2233", "#3F5B2E", "#7A6A2A", "#4A3B6B",
                "#1F5A57", "#7C4A2A", "#31507A", "#6B2E5A", "#4C5A22"]


# --- DATE / FORMAT HELPERS ---
# today() — current local date (no time); base for due dates, holds and scans.
def today():
    return dt.date.today()


# iso(d) — date → "YYYY-MM-DD" string for SQLite storage.
def iso(d):
    return d.isoformat() if isinstance(d, dt.date) else d


# parse(s) — "YYYY-MM-DD" → date; inverse of iso().
def parse(s):
    return dt.date.fromisoformat(s) if s else None


# days_until(due) — days from today to a due date; negative means overdue.
def days_until(due):
    return (parse(due) - today()).days


# fmt_date(d) — date → "Oct 05, 2026" for labels and notices.
def fmt_date(d):
    if isinstance(d, str):
        d = parse(d)
    return d.strftime("%b %d, %Y") if d else "-"


# fmt_long(d) — date → long readable label; used in the exported report header.
def fmt_long(d):
    if isinstance(d, str):
        d = parse(d)
    return d.strftime("%B %d, %Y") if d else "-"


# initials(title) — first letters of a title; drawn on reservation icon tiles.
def initials(title):
    words = [w for w in title.replace(":", " ").split() if w[0].isalpha()]
    return "".join(w[0].upper() for w in words[:2])


# cover_color(key) — deterministic tile colour per title.
def cover_color(key):
    return COVER_COLORS[sum(ord(c) for c in key) % len(COVER_COLORS)]


# hash_pw(value) — SHA-256 of a password; only the hash is stored.
def hash_pw(value):
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


# --- UI TOOLKIT (buttons, cards, tiles, tables) ---
# rounded_rect(...) — rounded rectangle on a canvas; backs pills and tiles.
def rounded_rect(cv, x1, y1, x2, y2, r, fill, outline=None, width=1):
    outline = fill if outline is None else outline
    cv.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=outline, width=width)
    cv.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=outline, width=width)
    cv.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill=fill, outline=outline, width=width)
    cv.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill=fill, outline=outline, width=width)
    cv.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill=fill, outline=outline, width=width)
    cv.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill=fill, outline=outline, width=width)


# widget_bg(widget) — nearest set background colour walking up the widget tree.
def widget_bg(widget):
    try:
        bg = widget.cget("bg")
        if bg in ("", "transparent"):
            raise ValueError
        return bg
    except Exception:
        return WHITE


# pill(...) — small status lozenge; kind picks the colour (status pills, counts).
def pill(parent, text, kind="neutral", anchor="center"):
    key = str(text).strip().lower()
    bg, fg = PILL_STYLES.get(key, PILL_STYLES.get(kind, PILL_STYLES["neutral"]))
    f = tkfont.Font(family=BODY, size=9, weight="bold")
    w = max(56, f.measure(text) + 26)
    h = 22
    cv = tk.Canvas(parent, width=w, height=h, bg=widget_bg(parent),
                   highlightthickness=0, bd=0)
    rounded_rect(cv, 1, 1, w - 1, h - 1, 7, bg, bg)
    cv.create_text(w / 2, h / 2, text=text, fill=fg, font=f)
    return cv


# button(...) — themed button (primary / ghost / danger); stays readable when disabled.
def button(parent, text, command=None, kind="primary", width=None, icon=None):
    if kind == "primary":
        bg, fg, active, border = MAROON, WHITE, MAROON_HOVER, MAROON
    elif kind == "ghost":
        bg, fg, active, border = WHITE, MAROON, MAROON_SOFT, LINE
    elif kind == "quiet":
        bg, fg, active, border = CREAM_DEEP, MUTED, LINE, CREAM_DEEP
    else:
        bg, fg, active, border = RED_BG, RED_FG, "#FBDDDD", RED_BG
    label = text if not icon else f"{icon}   {text}"
    b = tk.Button(parent, text=label, command=command, bg=bg, fg=fg,
                  activebackground=active, activeforeground=fg, relief="flat",
                  bd=0, highlightthickness=1, highlightbackground=border,
                  font=tkfont.Font(family=BODY, size=10, weight="bold"),
                  padx=18, pady=9, cursor="hand2")
    if width:
        b.configure(width=width)
    b.bind("<Enter>", lambda e: b.configure(bg=active))
    b.bind("<Leave>", lambda e: b.configure(bg=bg))
    return b


# check_row(...) — labelled checkbox row with optional count; filter panels.
def check_row(parent, text, var, command=None, count=None, pady=3, side=None):
    line = tk.Frame(parent, bg=widget_bg(parent))
    if side:
        line.pack(side=side, pady=pady)
    else:
        line.pack(fill="x", pady=pady)
    cb = tk.Checkbutton(line, text="", variable=var,
                        bg=widget_bg(line), fg=WHITE, selectcolor=MAROON,
                        activebackground=widget_bg(line),
                        activeforeground=MAROON, relief="sunken", bd=2,
                        highlightthickness=0, command=command)
    cb.pack(side="left")
    lab = tk.Label(line, text=text, bg=widget_bg(line), fg=INK,
                   font=(BODY, 10), cursor="hand2", anchor="w")
    lab.pack(side="left", fill="x", expand=True, padx=(7, 0))

    # flip(event) — toggles the row checkbox and runs its command.
    def flip(event=None):
        var.set(not var.get())
        if command:
            command()

    lab.bind("<Button-1>", flip)
    if count is not None:
        tk.Label(line, text=str(count), bg=widget_bg(line), fg=MUTED,
                 font=(BODY, 9)).pack(side="right")
    return line


# card(...) — white rounded panel; the basic content container.
def card(parent, pad=18):
    fr = tk.Frame(parent, bg=WHITE, highlightthickness=1,
                  highlightbackground=LINE)
    inner = tk.Frame(fr, bg=WHITE)
    inner.pack(fill="both", expand=True, padx=pad, pady=pad)
    fr.inner = inner
    return fr


# section_title(...) — panel heading with optional sub-line; returns the header frame.
def section_title(parent, text, sub=None):
    wrap = tk.Frame(parent, bg=WHITE)
    wrap.pack(fill="x")
    row = tk.Frame(wrap, bg=WHITE)
    row.pack(fill="x")
    left = tk.Frame(row, bg=WHITE)
    left.pack(side="left")
    tk.Label(left, text=text, bg=WHITE, fg=INK,
             font=tkfont.Font(family=HEAD, size=15, weight="bold")).pack(
        anchor="w")
    if sub:
        tk.Label(left, text=sub, bg=WHITE, fg=MUTED,
                 font=(BODY, 10)).pack(anchor="w")
    tk.Frame(wrap, bg=LINE, height=1).pack(fill="x", pady=(10, 0))
    return row


# stat_card(...) — KPI tile (label, big value, note, icon); dashboard + My loans.
def stat_card(parent, label, value, note, icon, note_color=MAROON):
    fr = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=LINE)
    fr.pack(side="left", fill="both", expand=True, padx=(0, 12))
    body = tk.Frame(fr, bg=WHITE)
    body.pack(fill="both", expand=True, padx=16, pady=14)
    top = tk.Frame(body, bg=WHITE)
    top.pack(fill="x")
    tk.Label(top, text=label, bg=WHITE, fg=MUTED,
             font=tkfont.Font(family=BODY, size=10, weight="bold")).pack(side="left")
    tk.Label(top, text=icon, bg=MAROON_SOFT, fg=MAROON,
             font=(BODY, 10, "bold"), width=3, pady=4).pack(side="right")
    row = tk.Frame(body, bg=WHITE)
    row.pack(fill="x", pady=(8, 0))
    tk.Label(row, text=str(value), bg=WHITE, fg=INK,
             font=tkfont.Font(family=HEAD, size=26, weight="bold")).pack(side="left")
    tk.Label(row, text=note, bg=WHITE, fg=note_color,
             font=tkfont.Font(family=BODY, size=10, weight="bold")).pack(
        side="left", padx=(10, 0), pady=(12, 0))
    return fr


# cover_tile(...) — small cover tile painted from the title; catalog + loan rows.
def cover_tile(parent, title, width=58, height=76):
    cv = tk.Canvas(parent, width=width, height=height,
                   bg=cover_color(title), highlightthickness=0, bd=0)
    cv.create_text(width / 2, 12, text="PDM LIBRARY", fill="#EADFC7",
                   font=tkfont.Font(family=BODY, size=5, weight="bold"))
    cv.create_text(width / 2, height / 2 - 4, text=initials(title), fill=WHITE,
                   font=tkfont.Font(family=HEAD, size=17, weight="bold"))
    cv.create_line(14, height / 2 + 14, width - 14, height / 2 + 14,
                   fill=GOLD, width=2)
    return cv


# =====================================================================
# CLASS: ScrollFrame(tk.Frame)
# Layer:   UI Toolkit   (grep: "# CLASS: ScrollFrame")
# Purpose: Scrollable container — hosts child widgets inside a Canvas so long
#          forms/lists stay reachable on short windows. Rebinds <MouseWheel>
#          on <Enter> and unbinds it on <Leave> (Windows-friendly scrolling).
# Objects: created 8x — signup form, catalog results, book details, my loans,
#          reservations, circulation, dashboard, add-book dialog.
#          Search: grep -n "ScrollFrame(" library_system.py
# =====================================================================
class ScrollFrame(tk.Frame):
    # ScrollFrame — scrollable container; the wheel handler scrolls on Windows.

    # METHOD: __init__(self, parent, bg=WHITE)
    # Sets up canvas + scrollbar + inner body frame, and keeps the scroll
    # region and window width in sync with <Configure> events.
    def __init__(self, parent, bg=WHITE):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self._win, width=e.width))
        self.bind("<Enter>", lambda e: self.canvas.bind_all(
            "<MouseWheel>", self._wheel))
        self.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    # METHOD: _wheel(self, event)
    # Mouse-wheel handler; scrolls the canvas by whole "units".
    # Bound to <MouseWheel> via bind_all() inside __init__.
    def _wheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


# style="PDM.SmallTreeview" drops rows to a size-9 font for the dense tx tables.
# tree(...) — themed Treeview with fixed columns; lists, registers, inventory.
def tree(parent, columns, widths, height=8, style="PDM.Treeview"):
    sty = ttk.Style()
    sty.theme_use("clam")
    sty.configure("PDM.Treeview", background=WHITE, fieldbackground=WHITE,
                  foreground=INK, rowheight=34, font=(BODY, 10),
                  borderwidth=0, relief="flat")
    sty.configure("PDM.Treeview.Heading", background=CREAM_DEEP, foreground=MUTED,
                  font=(BODY, 9, "bold"), relief="flat", padding=6)
    sty.configure("PDM.SmallTreeview", background=WHITE, fieldbackground=WHITE,
                  foreground=INK, rowheight=30, font=(BODY, 9),
                  borderwidth=0, relief="flat")
    sty.configure("PDM.SmallTreeview.Heading", background=CREAM_DEEP,
                  foreground=MUTED, font=(BODY, 9, "bold"), relief="flat",
                  padding=6)
    # PDM.Spot.SmallTreeview — audit-table variant whose SELECTED row paints
    # maroon in BOTH the focused and unfocused states. The clam default loses
    # its highlight when the widget loses focus, which makes a marked record
    # impossible to follow; this map keeps the bookmark visible either way.
    sty.configure("PDM.Spot.SmallTreeview", background=WHITE,
                  fieldbackground=WHITE, foreground=INK, rowheight=30,
                  font=(BODY, 9), borderwidth=0, relief="flat")
    sty.configure("PDM.Spot.SmallTreeview.Heading", background=CREAM_DEEP,
                  foreground=MUTED, font=(BODY, 9, "bold"), relief="flat",
                  padding=6)
    sty.map("PDM.Spot.SmallTreeview",
            background=[("selected", MAROON)],
            foreground=[("selected", WHITE)])
    sty.layout("PDM.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    sty.layout("PDM.SmallTreeview", [("Treeview.treearea", {"sticky": "nswe"})])
    sty.layout("PDM.Spot.SmallTreeview",
               [("Treeview.treearea", {"sticky": "nswe"})])
    tv = ttk.Treeview(parent, columns=columns, show="headings",
                      style=style, height=height)
    for col, w in zip(columns, widths):
        tv.heading(col, text=col.upper())
        tv.column(col, width=w, anchor="w")
    return tv


# attach_scroll(tv, parent) — vertical scrollbar wired to a tree.
def attach_scroll(tv, parent):
    sb = ttk.Scrollbar(parent, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=sb.set)
    return sb


# spotlight(tv) — click-to-highlight bookmark for the staff audit tables.
# PURELY VISUAL: it marks a row so staff can follow one record; it performs no
# action, opens nothing and writes nothing. Pair it with
# style="PDM.Spot.SmallTreeview" so the mark keeps the maroon fill after the
# table loses focus (a plain ttk selection greys out and is easy to lose).
def spotlight(tv):
    tv.configure(selectmode="browse")   # one marked record at a time
    tv.tag_configure("spot", background=MAROON_SOFT, foreground=MAROON)
    busy = False

    # _mark(row) — moves the "spot" tag + native selection onto one row.
    # Anything not currently marked loses its tag first. Guarded by `busy`
    # because selection_set() re-fires <<TreeviewSelect>>.
    def _mark(row):
        nonlocal busy
        if not row or busy:
            return
        busy = True
        try:
            for other in tv.tag_has("spot"):
                if other != row:
                    kept = [t for t in tv.item(other, "tags") if t != "spot"]
                    tv.item(other, tags=kept)
            if "spot" not in tv.item(row, "tags"):
                tv.item(row, tags=[*tv.item(row, "tags"), "spot"])
            if tv.selection() != (row,):
                tv.selection_set(row)
        finally:
            busy = False

    # _pick(event) — mouse: identify the clicked row. A click on empty space
    # below the rows resolves to "" and is ignored, so the mark stays put.
    def _pick(event):
        _mark(tv.identify_row(event.y))

    # keeps the mark in step with keyboard navigation.
    def _focus(event=None):
        _mark(tv.focus())

    tv.bind("<ButtonRelease-1>", _pick)
    tv.bind("<<TreeviewSelect>>", _focus)
    return tv


# =====================================================================
# CLASS: Toast(tk.Toplevel)
# Layer:   UI Toolkit   (grep: "# CLASS: Toast")
# Purpose: Small borderless auto-closing popup for confirmations and alerts.
#          "level" picks styling: info (maroon border) / warn|error (gold).
#          Positions itself bottom-right of the master window and self-destructs.
# Objects: created at many call sites — overdue-scan alerts, library-update
#          notice on login, reservation/renew/return/case results.
#          Search: grep -n "Toast(" library_system.py
# =====================================================================
class Toast(tk.Toplevel):
    # Toast — small auto-fading popup; level picks info / warn / error styling.

    # METHOD: __init__(self, master, title, message, level="info")
    # Builds the popup, aligns it to the master's bottom-right corner,
    # then schedules self.destroy() after 4200 ms.
    def __init__(self, master, title, message, level="info"):
        super().__init__(master)
        self.overrideredirect(True)
        self.configure(bg=WHITE, highlightthickness=1,
                       highlightbackground=MAROON if level == "info" else GOLD)
        tk.Label(self, text=title, bg=WHITE, fg=MAROON,
                 font=tkfont.Font(family=BODY, size=10, weight="bold"),
                 anchor="w", padx=14).pack(fill="x", pady=(12, 0))
        tk.Label(self, text=message, bg=WHITE, fg=MUTED, font=(BODY, 10),
                 wraplength=300, justify="left", padx=14).pack(fill="x",
                                                               pady=(4, 14))
        self.update_idletasks()
        x = master.winfo_rootx() + master.winfo_width() - self.winfo_width() - 28
        y = master.winfo_rooty() + master.winfo_height() - self.winfo_height() - 36
        self.geometry(f"+{max(x, 10)}+{max(y, 10)}")
        self.after(4200, self.destroy)


# =====================================================================
# CLASS: Database
# Layer:   DATABASE   (grep: "# CLASS: Database")
# Purpose: Thin OOP wrapper over one SQLite connection. Holds PRAGMA
#          foreign_keys=ON and sets row_factory so every row behaves like a
#          dict. This is the only class the Logic-layer functions depend on.
# Objects: the single long-lived instance lives as App.db
#          (self.db = Database() inside App.__init__).
#          Search: grep -n "Database(" library_system.py
# =====================================================================
class Database:
    # Database — one SQLite connection per run; rows behave like dicts.

    # METHOD: __init__(self, path=DB_PATH)
    # Opens the SQLite file, enables dict-like rows, turns on FK enforcement.
    def __init__(self, path=DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")

    # METHOD: all(self, sql, args=())  -> list[sqlite3.Row]
    # Every matching row; use for lists, feeds and tables.
    def all(self, sql, args=()):
        return self.conn.execute(sql, args).fetchall()

    # METHOD: one(self, sql, args=())  -> sqlite3.Row | None
    # First matching row or None; use for single-record lookups.
    def one(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()

    # METHOD: run(self, sql, args=())  -> int
    # INSERT / UPDATE / DELETE, commits immediately, returns the new row id.
    def run(self, sql, args=()):
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur.lastrowid

    # METHOD: scalar(self, sql, args=(), default=0)  -> Any
    # Single value (counts, settings); returns "default" when no row/NULL.
    def scalar(self, sql, args=(), default=0):
        row = self.conn.execute(sql, args).fetchone()
        if row is None or row[0] is None:
            return default
        return row[0]

    # METHOD: close(self)  -> None
    # Shuts the SQLite connection down.
    def close(self):
        self.conn.close()


# --- SEED DATA (catalog, people) ---
BOOKS = [
    ("Python Programming: An Introduction to Computer Science", "John M. Zelle",
     "Programming", "Computer Science", "Franklin, Beedle", "3rd edition", 2023,
     "978-1-59028-275-5", "QA76.73.P98 L88 2023", "Book", "QA-14", 5,
     "A clear, example-driven introduction to programming and computer science "
     "using Python. Covers object-oriented design, algorithms, graphics, and "
     "data processing for first-course learners."),
    ("Microsoft Office 365: In Practice", "Randy Nordell", "Office", "Business",
     "McGraw Hill", "1st edition", 2021, "978-1-260-40333-1",
     "HF5548.4.M523 O37 2021", "Book", "HF-04", 2,
     "Hands-on coverage of Word, Excel, PowerPoint, Access and Teams with "
     "workplace scenarios built around real projects."),
    ("Educational Technology and Learning", "Terry T. Kidd", "Education",
     "Education", "Information Age", "2nd edition", 2020, "978-1-64802-114-3",
     "LB1028.5.R63 2020", "Book", "LB-08", 3,
     "A practical guide to selecting, designing and evaluating technology "
     "supported learning environments in the classroom."),
    ("Fundamentals of Database Systems", "Ramez Elmasri & Shamkant Navathe",
     "Databases", "Computer Science", "Pearson", "7th edition", 2022,
     "978-0-13-494256-1", "QA76.9.D3 E46 2022", "Book", "QA-14", 4,
     "Comprehensive treatment of database design, SQL, transaction management "
     "and modern data models for undergraduate study."),
    ("Data Structures and Algorithms in Python", "Michael T. Goodrich",
     "Programming", "Computer Science", "Wiley", "1st edition", 2013,
     "978-1-118-29027-9", "QA76.9.D35 G66", "Book", "QA-14", 3,
     "Provides a practical introduction to data structures and algorithms with "
     "full Python implementations and design patterns."),
    ("The Philippine Constitution", "Hector S. De Leon", "Law", "Social Science",
     "Central Book Supply", "2021 edition", 2021, "978-621-432-019-1",
     "KPM2064 D45", "Reference", "JQ-03", 2,
     "Annotated discussion of the 1987 Philippine Constitution with commentaries "
     "on civil, political and social rights."),
    ("Research Methods in Education", "Louis Cohen", "Education", "Education",
     "Routledge", "7th edition", 2018, "978-1-138-23034-6", "LB1028 C63",
     "Book", "LB-08", 3,
     "The standard guide to planning, conducting and evaluating educational "
     "research, covering quantitative, qualitative and mixed methods."),
    ("Introduction to Information Systems", "Rainer & Prince",
     "Information Systems", "Computer Science", "Cengage", "9th edition", 2022,
     "978-0-357-67199-5", "QA76.9.I5 R35", "Book", "QA-12", 5,
     "Shows how business value is created through information systems, with "
     "coverage of cloud, security, data and emerging technologies."),
    ("Business Communication Today", "Bovee & Thill", "Communication",
     "Business", "Pearson", "14th edition", 2019, "978-0-13-473536-3",
     "HF5717.B66", "Book", "HF-04", 2,
     "Modern business writing, presentations and digital communication "
     "strategies for the contemporary workplace."),
    ("Principles of Marketing", "Philip Kotler", "Marketing", "Business",
     "Pearson", "18th edition", 2021, "978-0-13-519742-0", "HF5415.K64",
     "Book", "HF-04", 4,
     "Foundational marketing framework covering segmentation, branding, the "
     "digital customer journey and global marketing ethics."),
    ("Understanding the Philippine Government", "Isagani R. Cruz", "Government",
     "Social Science", "Central Book Supply", "2020 edition", 2020,
     "978-621-432-088-7", "JQ1417 C78", "Book", "JQ-03", 3,
     "A readable survey of Philippine political institutions, local governance "
     "and the structure of public administration."),
    ("General Psychology", "David G. Myers", "Psychology", "Social Science",
     "Worth Publishers", "13th edition", 2021, "978-1-319-34318-0",
     "BF121 M94", "Book", "BF-01", 4,
     "Survey of the science of behaviour and mental processes, from sensation "
     "and perception to personality and social influence."),
    ("Statistics for Business and Economics", "David R. Anderson", "Statistics",
     "Business", "Cengage", "13th edition", 2019, "978-1-305-18466-9",
     "HA297.A53", "Book", "HF-06", 3,
     "Emphasises statistical thinking with real business data, regression, "
     "forecasting and experimental design."),
    ("Calculus: Early Transcendentals", "James Stewart", "Mathematics",
     "Science", "Cengage", "9th edition", 2021, "978-0-357-02216-9",
     "QA303.2.S84", "Book", "QA-01", 4,
     "The classic single-variable calculus text covering limits, derivatives, "
     "integrals and series with extensive exercises."),
    ("Physics for Scientists and Engineers", "Raymond A. Serway", "Physics",
     "Science", "Cengage", "10th edition", 2019, "978-1-337-55327-1",
     "QC21.S47", "Book", "QC-02", 3,
     "Algebra-based physics covering mechanics, waves, thermodynamics, "
     "electricity and modern physics with worked examples."),
    ("Organic Chemistry", "Paula Yurkanis Bruice", "Chemistry", "Science",
     "Pearson", "9th edition", 2020, "978-0-13-404228-8", "QD251.3.B78",
     "Book", "QD-03", 3,
     "Mechanism-driven approach to organic chemistry with biological and "
     "medicinal applications throughout."),
    ("Anatomy and Physiology", "Marieb & Hoehn", "Biology", "Science",
     "Pearson", "10th edition", 2019, "978-0-13-458099-9", "QP34.5.M35",
     "Book", "QP-05", 4,
     "Integrated coverage of the eleven organ systems with clinical boxes and "
     "interactive study support."),
    ("Teaching in the 21st Century", "Bob Blecher", "Education", "Education",
     "Routledge", "3rd edition", 2022, "978-0-367-75431-2", "LB1025.3.B56",
     "Book", "LB-08", 3,
     "Contemporary pedagogy, classroom management and assessment strategies "
     "for future educators."),
    ("Sociology: The Core", "Hughes & Kroehler", "Sociology", "Social Science",
     "McGraw Hill", "11th edition", 2018, "978-1-259-92253-6", "HM586.H84",
     "Book", "HM-02", 2,
     "Concise introduction to social structure, culture, stratification and "
     "social change with global examples."),
    ("Financial Accounting: Tools for Business Decision Making",
     "Weygandt, Kimmel & Kieso", "Accounting", "Business", "Wiley",
     "9th edition", 2020, "978-1-119-69274-6", "HF5636.W49", "Book", "HF-06", 4,
     "Financial statement analysis, accrual accounting and decision making "
     "presented through a business lens."),
    ("Introduction to Electronics and Communication",
     "Robert L. Boylestad", "Engineering", "Science", "Pearson",
     "12th edition", 2018, "978-0-13-458869-9", "TK7871.15.B68", "Book",
     "TK-04", 2,
     "Circuit analysis through diodes, transistors, amplifiers and "
     "communication systems with laboratory guidance."),
    ("The Great Gatsby", "F. Scott Fitzgerald", "Literature", "Literature",
     "Scribner", "2004 edition", 2004, "978-0-7432-7356-5", "PS3511.I9 G6",
     "Book", "PS-07", 3,
     "The definitive American novel of the jazz age, edited with critical "
     "essays and historical notes."),
    ("Noli Me Tangere", "José P. Rizal", "Literature", "Literature",
     "Grafika Filipina", "2017 edition", 2017, "978-971-27-2803-7",
     "PL6745.R5", "Book", "PL-02", 5,
     "Rizal's foundational novel of Philippine society, with annotation and "
     "study guide for senior high learners."),
    ("Project Management: A Managerial Approach", "Jack R. Meredith",
     "Management", "Business", "Wiley", "10th edition", 2020,
     "978-1-119-66697-8", "HD69.P75", "Book", "HF-08", 3,
     "Project life cycle, scheduling, risk and team leadership framed for "
     "managerial decision making."),
]

STUDENTS = [
    ("2024-01842", "Alyssa M. Reyes", "BS Information Systems", "2nd Year",
     "B", "03152005"),
    ("2023-00615", "Joshua P. Lim", "BS Computer Science", "3rd Year",
     "C", "07222004"),
    ("2024-02481", "Denise R. Flores", "Bachelor of Elementary Education",
     "2nd Year", "A", "11092005"),
    ("2022-00988", "Carlo D. Ramos", "BS Business Administration", "4th Year",
     "D", "01042003"),
    ("2025-01177", "Maria C. Delos Santos", "BS Psychology", "1st Year",
     "A", "06182006"),
    ("2023-03390", "Kevin B. Aguilar", "BS Secondary Education", "3rd Year",
     "B", "09252004"),
]

STAFF = [
    ("staff", "Christopher Teope", "Library Staff", "pdmstaff"),
    ("a.soy", "Soy Delacruz", "Library Staff", "pdmstaff"),
    ("b.karen", "Karen Bautista", "Library Staff", "pdmstaff"),
    ("c.janine", "Janine Cruz", "Library Staff", "pdmstaff"),
]

ADMINS = [
    ("admin", "Mae Ann D.C Basa", "System Administrator", "pdmadmin"),
]

# --- POLICY TUNABLES (mirrored into settings on launch) ---
LOAN_DAYS = 3
BOOK_LIMIT = 5
MAX_RENEWALS = 3
HOLD_DAYS = 3
SDO_AFTER = 2
RENEW_WINDOW = 1
# --- DATABASE SCHEMA ---
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    password TEXT NOT NULL,
    program TEXT DEFAULT '',
    year_level TEXT DEFAULT '',
    section TEXT DEFAULT '',
    birthdate TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    joined TEXT
);
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    subject TEXT NOT NULL,
    category TEXT NOT NULL,
    publisher TEXT,
    edition TEXT,
    year INTEGER,
    isbn TEXT,
    call_no TEXT,
    material_type TEXT DEFAULT 'Book',
    description TEXT
);
CREATE TABLE IF NOT EXISTS copies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    accession TEXT UNIQUE NOT NULL,
    shelf TEXT,
    status TEXT DEFAULT 'available'
);
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    copy_id INTEGER NOT NULL REFERENCES copies(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    checkout_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    return_date TEXT,
    renewals INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    position INTEGER,
    status TEXT DEFAULT 'waiting',
    created_at TEXT,
    ready_at TEXT,
    UNIQUE(book_id, user_id)
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user_id INTEGER,
    copy_id INTEGER,
    type TEXT NOT NULL,
    staff_id INTEGER,
    status TEXT DEFAULT 'Completed',
    note TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    level TEXT DEFAULT 'info',
    kind TEXT,
    dedupe TEXT UNIQUE,
    ts TEXT,
    read INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sdo_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL REFERENCES loans(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    reason TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    resolved_at TEXT,
    closed_by TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


# --- DB SETUP + SEEDING ---
# init_db(db) — schema + seed on first launch; re-seeds the 3 policy settings every launch; see WORKFLOW.md section 2.
def init_db(db):
    db.conn.executescript(SCHEMA)
    db.conn.commit()
    # adds section to databases created before that column existed.
    if not any(row["name"] == "section"
               for row in db.conn.execute("PRAGMA table_info(users)")):
        db.run("ALTER TABLE users ADD COLUMN section TEXT DEFAULT ''")
    # adds closed_by to databases created before that column existed. It
    # records HOW a case closed — 'return' (the book came back) or 'sdo'
    # (staff acknowledged). Left NULL on purpose for rows that were already
    # acknowledged under the old schema: the true closer is not recoverable,
    # so the register shows them without a qualifier rather than guessing.
    if not any(row["name"] == "closed_by"
               for row in db.conn.execute("PRAGMA table_info(sdo_cases)")):
        db.run("ALTER TABLE sdo_cases ADD COLUMN closed_by TEXT")
    for key, value in (("renew_window", RENEW_WINDOW), ("loan_days", LOAN_DAYS),
                       ("sdo_after", SDO_AFTER)):
        db.run("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
               (key, str(value)))
    if db.one("SELECT id FROM users LIMIT 1"):
        return
    seed_db(db)


# seed_db(db) — catalog, people and default settings; fresh databases only.
def seed_db(db):
    now = iso(today())
    for username, name, program, year, section, bday in STUDENTS:
        db.run(
            "INSERT INTO users(username,name,role,password,program,year_level,"
            "section,birthdate,status,joined) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (username, name, "student", hash_pw(bday), program, year, section,
             bday, "active", now))
    for username, name, role, password in STAFF:
        db.run(
            "INSERT INTO users(username,name,role,password,program,year_level,"
            "birthdate,status,joined) VALUES(?,?,?,?,?,?,?,?,?)",
            (username, name, "staff", hash_pw(password), "Library", "", "",
             "active", now))
    for username, name, role, password in ADMINS:
        db.run(
            "INSERT INTO users(username,name,role,password,program,year_level,"
            "birthdate,status,joined) VALUES(?,?,?,?,?,?,?,?,?)",
            (username, name, "admin", hash_pw(password), "Administration", "",
             "", "active", now))
    for b in BOOKS:
        (title, author, subject, category, publisher, edition, year, isbn,
         call_no, material, shelf, copies, description) = b
        book_id = db.run(
            "INSERT INTO books(title,author,subject,category,publisher,edition,"
            "year,isbn,call_no,material_type,description) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (title, author, subject, category, publisher, edition, year, isbn,
             call_no, material, description))
        for i in range(copies):
            accession = f"PDM-{1000 + book_id * 40 + i:06d}"
            db.run("INSERT INTO copies(book_id,accession,shelf,status) "
                   "VALUES(?,?,?,?)", (book_id, accession, shelf, "available"))
    for key, value in (("loan_days", LOAN_DAYS), ("book_limit", BOOK_LIMIT),
                       ("max_renewals", MAX_RENEWALS), ("hold_days", HOLD_DAYS),
                       ("sdo_after", SDO_AFTER), ("renew_window", RENEW_WINDOW)):
        db.run("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                (key, str(value)))
    seed_activity(db)


# --- READ HELPERS (lookups, counts, queues) ---
# setting(db, key, default) — one policy value from settings, or the default.
def setting(db, key, default):
    row = db.one("SELECT value FROM settings WHERE key=?", (key,))
    return int(row[0]) if row else default


# user_by_id(db, uid) — account row by id.
def user_by_id(db, uid):
    return db.one("SELECT * FROM users WHERE id=?", (uid,))


# student(db, username) — student account row by student number.
def student(db, username):
    return db.one("SELECT * FROM users WHERE username=? AND role='student'",
                  (username,))


# copy_of(db, accession) — copy row with title, by barcode.
def copy_of(db, accession):
    return db.one(
        "SELECT c.*, b.title, b.author, b.call_no, b.subject, b.category, "
        "b.description, b.publisher, b.edition, b.year, b.isbn, b.material_type "
        "FROM copies c JOIN books b ON b.id=c.book_id WHERE c.accession=?",
        (accession.strip(),))


# available_count(db, book_id) — free copies of a title; drives availability pills.
def available_count(db, book_id):
    return db.scalar("SELECT COUNT(*) FROM copies WHERE book_id=? AND "
                     "status='available'", (book_id,))


# copies_of(db, book_id) — every copy row of a title.
def copies_of(db, book_id):
    return db.all(
        "SELECT c.*, l.due_date, l.status AS loan_status, u.name AS borrower "
        "FROM copies c "
        "LEFT JOIN loans l ON l.copy_id=c.id AND l.status IN ('active','overdue') "
        "LEFT JOIN users u ON u.id=l.user_id WHERE c.book_id=?", (book_id,))


# held_copy(db, book_id) — the reserved, unloaned copy a request or checkout consumes.
def held_copy(db, book_id):
    """A copy of this title sitting on the reserved shelf, free to be issued."""
    return db.one(
        "SELECT * FROM copies WHERE book_id=? AND status='reserved' AND NOT "
        "EXISTS (SELECT 1 FROM loans l WHERE l.copy_id=copies.id AND "
        "l.status IN ('active','overdue')) ORDER BY id LIMIT 1", (book_id,))


# active_loan(db, copy_id) — the live loan on a copy, if any.
def active_loan(db, copy_id):
    return db.one("SELECT * FROM loans WHERE copy_id=? AND status IN "
                  "('active','overdue')", (copy_id,))


# my_loans(db, user_id) — active + overdue loans with book info, soonest due first.
def my_loans(db, user_id):
    return db.all(
        "SELECT l.*, c.accession, c.shelf, b.title, b.author, b.call_no "
        "FROM loans l JOIN copies c ON c.id=l.copy_id "
        "JOIN books b ON b.id=c.book_id "
        "WHERE l.user_id=? AND l.status IN ('active','overdue') "
        "ORDER BY l.due_date", (user_id,))


# my_reservations(db, user_id) — requests, pickups and queue rows, actionable first.
def my_reservations(db, user_id):
    return db.all(
        "SELECT r.*, b.title, b.author, b.call_no, b.id AS bid FROM "
        "reservations r JOIN books b ON b.id=r.book_id WHERE r.user_id=? "
        "ORDER BY CASE r.status WHEN 'requested' THEN 0 WHEN 'ready' THEN 1 "
        "ELSE 2 END, r.position",
        (user_id,))


# reservation_for(db, book_id, user_id) — this student's row on a title, if any.
def reservation_for(db, book_id, user_id):
    return db.one("SELECT * FROM reservations WHERE book_id=? AND user_id=?",
                  (book_id, user_id))


# title_loan(db, user_id, book_id) — this student's live loan on a title; one title stays out at a time.
def title_loan(db, user_id, book_id):
    return db.one(
        "SELECT l.due_date FROM loans l JOIN copies c ON c.id=l.copy_id "
        "WHERE l.user_id=? AND c.book_id=? AND l.status IN ('active','overdue') "
        "ORDER BY l.due_date LIMIT 1", (user_id, book_id))


# queue_for(db, book_id) — waiting queue of a title in position order.
def queue_for(db, book_id):
    return db.all(
        "SELECT r.*, u.username, u.name FROM reservations r "
        "JOIN users u ON u.id=r.user_id WHERE r.book_id=? AND "
        "r.status='waiting' ORDER BY r.position", (book_id,))


# --- NOTIFICATIONS + AUDIT ---
# notify(...) — one message-centre row; user_id None = system-wide; repeats swallowed by the UNIQUE dedupe key; see D7.
def notify(db, user_id, title, body, level="info", dedupe=None, kind=None):
    try:
        db.run("INSERT INTO notifications(user_id,title,body,level,kind,dedupe,"
               "ts) VALUES(?,?,?,?,?,?,?)",
               (user_id, title, body, level, kind, dedupe,
                dt.datetime.now().isoformat(timespec="seconds")))
        return True
    except sqlite3.IntegrityError:
        return False


# announce_case_closed(db, case_id, how) — system-wide "SDO case acknowledged" notice; deduped per case; see §10 rows 10/10b.
def announce_case_closed(db, case_id, how):
    row = db.one(
        "SELECT s.id, u.name, u.username, b.title FROM sdo_cases s "
        "JOIN users u ON u.id=s.user_id JOIN loans l ON l.id=s.loan_id "
        "JOIN copies c ON c.id=l.copy_id JOIN books b ON b.id=c.book_id "
        "WHERE s.id=?", (case_id,))
    if not row:
        return False
    return notify(db, None, "SDO case acknowledged",
                  f"Case SDO-{row['id']:03d} for {row['name']} "
                  f"({row['username']}) - {row['title']} was closed {how}.",
                  "info", f"sdoack:{row['id']}")


# ack_guidance(db, case_id) — post-ack summary of what still restricts the student; empty if no such case; see C4.4.
def ack_guidance(db, case_id):
    row = db.one("SELECT s.id, s.user_id, u.name, u.username, u.status "
                 "FROM sdo_cases s JOIN users u ON u.id=s.user_id "
                 "WHERE s.id=?", (case_id,))
    if not row:
        return ""
    late = db.scalar("SELECT COUNT(*) FROM loans WHERE user_id=? AND "
                     "status='overdue'", (row["user_id"],))
    others = db.scalar("SELECT COUNT(*) FROM sdo_cases WHERE user_id=? AND "
                       "status='pending' AND id<>?", (row["user_id"], case_id))
    head = (f"SDO-{row['id']:03d} acknowledged for {row['name']} "
            f"({row['username']}). ")
    if late:
        body = (f"They still have {late} overdue book(s) out, so the account "
                f"stays blocked. Once the books are returned, reinstate the "
                f"account on Users (double-click the row).")
    elif row["status"] == "blocked":
        body = ("All books are back. Reinstate the account on Users "
                "(double-click the row) to restore borrowing.")
    else:
        body = "The account is active - borrowing is restored."
    if others:
        body += f" {others} other case(s) for this student remain pending."
    return head + body


# log_tx(...) — one audit row (Checkout / Return / Renewal); feeds charts and tables.
def log_tx(db, user_id, copy_id, tx_type, staff_id, status="Completed",
           note=""):
    db.run("INSERT INTO transactions(ts,user_id,copy_id,type,staff_id,status,"
           "note) VALUES(?,?,?,?,?,?,?)",
           (dt.datetime.now().isoformat(timespec="seconds"), user_id, copy_id,
            tx_type, staff_id, status, note))


# --- BORROWING RULES (gate, checkout, holds, returns, renewals) ---
# eligibility(db, user) — borrowing gate: account active, 0 overdue, under the limit; status re-read live; see §11 + B1.5.
def eligibility(db, user):
    if not user:
        return False, "Account not found"
    if db.scalar("SELECT status FROM users WHERE id=?", (user["id"],),
                 user["status"]) != "active":
        return False, "Account is blocked"
    loans = db.scalar("SELECT COUNT(*) FROM loans WHERE user_id=? AND status IN "
                      "('active','overdue')", (user["id"],))
    overdue = db.scalar("SELECT COUNT(*) FROM loans WHERE user_id=? AND "
                        "status='overdue'", (user["id"],))
    if overdue:
        return False, f"{overdue} overdue item(s) - resolve with the librarian"
    if loans >= setting(db, "book_limit", BOOK_LIMIT):
        return False, (f"Borrowing limit reached ({loans} of "
                       f"{setting(db, 'book_limit', BOOK_LIMIT)})")
    return True, f"{loans} of {setting(db, 'book_limit', BOOK_LIMIT)} books"


# checkout(db, user, accessions, staff) — issues copies (due = today + loan_days); consumes the holder's reservation; returns per-copy (accession, ok, msg); see P4 + B2.
def checkout(db, user, accessions, staff):
    results = []
    for accession in accessions:
        copy = copy_of(db, accession)
        if not copy:
            results.append((accession, False, "Accession not found"))
            continue
        if copy["status"] == "checked_out":
            results.append((accession, False, "Already checked out"))
            continue
        if copy["status"] == "reserved":
            mine = db.one("SELECT * FROM reservations WHERE book_id=? AND "
                          "user_id=? AND status IN ('ready','requested')",
                          (copy["book_id"], user["id"]))
            if not mine:
                results.append((accession, False, "Held for a reservation"))
                continue
        ok, reason = eligibility(db, user)
        if not ok:
            results.append((accession, False, reason))
            continue
        if title_loan(db, user["id"], copy["book_id"]):
            results.append((accession, False, "Already holds this title"))
            continue
        due = iso(today() + dt.timedelta(days=setting(db, "loan_days", LOAN_DAYS)))
        db.run("INSERT INTO loans(copy_id,user_id,checkout_date,due_date,status) "
               "VALUES(?,?,?,?,?)",
               (copy["id"], user["id"], iso(today()), due, "active"))
        db.run("UPDATE copies SET status='checked_out' WHERE id=?",
               (copy["id"],))
        log_tx(db, user["id"], copy["id"], "Checkout", staff["id"],
               note=f"Due {due}")
        res = db.one("SELECT * FROM reservations WHERE book_id=? AND user_id=? "
                     "AND status IN ('ready','requested')",
                     (copy["book_id"], user["id"]))
        if res:
            db.run("DELETE FROM reservations WHERE id=?", (res["id"],))
            release_hold(db, copy["book_id"])
        notify(db, user["id"], "Book checked out",
               f"{copy['title']} is due {fmt_date(due)}.", "info",
               f"checkout:{copy['id']}:{due}")
        results.append((accession, True, f"Due {fmt_date(due)}"))
    return results


# requeue(db, book_id) — renumbers a title's waiting queue 1..n after a change.
def requeue(db, book_id):
    waiting = queue_for(db, book_id)
    for i, row in enumerate(waiting, start=1):
        db.run("UPDATE reservations SET position=? WHERE id=?", (i, row["id"]))


# release_hold(db, book_id) — hands a freed copy to the next waiter (ready) or back to the shelf; see §10 row 8.
def release_hold(db, book_id):
    """Match reserved-but-unloaned copies of a title to its outstanding holds.

    Copies held for a 'ready' pickup or a 'requested' borrow stay reserved.
    Copies with no holder left are offered to the next waiting student or
    returned to the shelf. Copies currently on loan are never touched.
    """
    book = db.one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        return
    ready = db.scalar("SELECT COUNT(*) FROM reservations WHERE book_id=? AND "
                      "status IN ('ready','requested')", (book_id,))
    held = [c for c in db.all(
        "SELECT * FROM copies WHERE book_id=? AND status='reserved'",
        (book_id,)) if not active_loan(db, c["id"])]
    while len(held) > ready:
        copy = held.pop()
        waiting = queue_for(db, book_id)
        if waiting:
            first = waiting[0]
            hold = iso(today() + dt.timedelta(
                days=setting(db, "hold_days", HOLD_DAYS)))
            db.run("UPDATE reservations SET status='ready', position=NULL, "
                   "ready_at=? WHERE id=?", (hold, first["id"]))
            notify(db, first["user_id"], "Ready for pickup",
                   f"{book['title']} is held for you until {fmt_date(hold)}.",
                   "info", f"ready:{first['id']}")
            notify(db, None, "Hold available",
                   f"Shelf {copy['shelf']} - {book['title']} is ready for "
                   f"{first['name']}.", "info", f"hold:{first['id']}:{hold}")
            ready += 1
        else:
            db.run("UPDATE copies SET status='available' WHERE id=?",
                   (copy["id"],))
    requeue(db, book_id)


# release_expired_holds(db) — deletes past-deadline ready holds, notifies, promotes the next waiter; see §10 row 9.
def release_expired_holds(db):
    """Drop ready holds whose pickup window has passed."""
    alerts = []
    for res in db.all(
            "SELECT r.*, b.title FROM reservations r JOIN books b "
            "ON b.id=r.book_id WHERE r.status='ready' AND r.ready_at IS NOT "
            "NULL AND r.ready_at < ?", (iso(today()),)):
        db.run("DELETE FROM reservations WHERE id=?", (res["id"],))
        if notify(db, res["user_id"], "Hold expired",
                  f"{res['title']} was not picked up by "
                  f"{fmt_date(res['ready_at'])}. The copy has been returned "
                  "to the shelf.", "warn", f"expired:{res['id']}"):
            alerts.append(("Hold expired", res["title"]))
        release_hold(db, res["book_id"])
    return alerts


# return_book(db, accession, staff) — closes the loan, promotes the queue, auto-acknowledges SDO cases (block stays); returns (ok, msg); see §10 rows 7/10.
def return_book(db, accession, staff):
    copy = copy_of(db, accession.strip())
    if not copy:
        return False, "Accession not found"
    loan = active_loan(db, copy["id"])
    if not loan:
        if copy["status"] == "reserved":
            return False, "Copy is held for pickup, not on loan"
        return False, "No active loan for this copy"
    overdue_days = -days_until(loan["due_date"])
    status = "Overdue noted" if overdue_days > 0 else "Completed"
    db.run("UPDATE loans SET status='returned', return_date=? WHERE id=?",
           (iso(today()), loan["id"]))
    waiting = queue_for(db, copy["book_id"])
    if waiting:
        first = waiting[0]
        ready = iso(today() + dt.timedelta(days=setting(db, "hold_days", HOLD_DAYS)))
        db.run("UPDATE reservations SET status='ready', position=NULL, "
               "ready_at=? WHERE id=?", (ready, first["id"]))
        db.run("UPDATE copies SET status='reserved' WHERE id=?", (copy["id"],))
        notify(db, first["user_id"], "Ready for pickup",
               f"{copy['title']} is held for you until {fmt_date(ready)}.",
               "info", f"ready:{first['id']}")
        notify(db, None, "Hold available",
               f"Shelf {copy['shelf']} - {copy['title']} is ready for "
               f"{first['name']}.", "info", f"hold:{first['id']}:{ready}")
        requeue(db, copy["book_id"])
        note = f"Reserved for {first['name']}"
    else:
        db.run("UPDATE copies SET status='available' WHERE id=?",
               (copy["id"],))
        requeue(db, copy["book_id"])
        note = ""
    log_tx(db, loan["user_id"], copy["id"], "Return", staff["id"], status, note)
    pending = [r["id"] for r in db.all(
        "SELECT id FROM sdo_cases WHERE loan_id=? AND status='pending'",
        (loan["id"],))]
    db.run("UPDATE sdo_cases SET status='acknowledged', resolved_at=?, "
           "closed_by='return' WHERE loan_id=? AND status='pending'",
           (iso(today()), loan["id"]))
    for cid in pending:
        announce_case_closed(db, cid, "on return of the book")
    message = "Returned"
    if overdue_days > 0:
        message = f"Returned {overdue_days} day(s) late"
    return True, message


# renew_loan(db, loan_id, staff) — extends due to today + loan_days inside the window unless capped, overdue or awaited; returns (ok, msg); see A4.4 / B3.3.
def renew_loan(db, loan_id, staff):
    loan = db.one("SELECT * FROM loans WHERE id=?", (loan_id,))
    if not loan:
        return False, "Loan not found"
    max_r = setting(db, "max_renewals", MAX_RENEWALS)
    if loan["renewals"] >= max_r:
        return False, f"Renewal limit reached ({max_r})"
    if days_until(loan["due_date"]) < 0:
        return False, "Overdue items cannot be renewed"
    left = days_until(loan["due_date"])
    window = setting(db, "renew_window", RENEW_WINDOW)
    if left > window:
        return False, (f"Too early to renew - due in {left} days "
                       f"(renewals open {window} "
                       f"{'day' if window == 1 else 'days'} "
                       f"before the due date)")
    waiting = db.scalar("SELECT COUNT(*) FROM reservations r JOIN copies c ON "
                        "c.book_id=r.book_id WHERE c.id=? AND r.status IN "
                        "('waiting','ready')", (loan["copy_id"],))
    if waiting:
        return False, "Another student is waiting for this title"
    due = iso(today() + dt.timedelta(days=setting(db, "loan_days", LOAN_DAYS)))
    db.run("UPDATE loans SET due_date=?, renewals=renewals+1, status='active' "
           "WHERE id=?", (due, loan_id))
    log_tx(db, loan["user_id"], loan["copy_id"], "Renewal", staff["id"],
           note=f"New due date {due}")
    notify(db, loan["user_id"], "Loan renewed",
           f"New due date is {fmt_date(due)}.", "info",
           f"renew:{loan_id}:{due}")
    return True, f"Extended to {fmt_date(due)}"


# reserve(db, book_id, user) — instant ready hold when a copy is free, else a queue slot; returns (ok, msg); see A-catalog.
def reserve(db, book_id, user):
    book = db.one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        return False, "Title not found"
    if reservation_for(db, book_id, user["id"]):
        return False, "You already hold a reservation for this title"
    held = title_loan(db, user["id"], book_id)
    if held:
        return False, f"You already have this title out - due {fmt_date(held['due_date'])}"
    ok, reason = eligibility(db, user)
    if not ok:
        return False, reason
    if available_count(db, book_id) > 0:
        ready = iso(today() + dt.timedelta(days=setting(db, "hold_days", HOLD_DAYS)))
        copy = db.one("SELECT * FROM copies WHERE book_id=? AND "
                      "status='available' LIMIT 1", (book_id,))
        db.run("UPDATE copies SET status='reserved' WHERE id=?", (copy["id"],))
        db.run("INSERT INTO reservations(book_id,user_id,status,created_at,"
               "ready_at) VALUES(?,?,?,?,?)",
               (book_id, user["id"], "ready", iso(today()), ready))
        notify(db, user["id"], "Ready for pickup",
               f"{book['title']} is held until {fmt_date(ready)}.", "info",
               f"ready:{book_id}:{user['id']}")
        notify(db, None, "Hold available",
               f"{book['title']} held at shelf {copy['shelf']} for {user['name']}.",
               "info", f"hold:{user['id']}:{ready}")
        return True, f"Ready for pickup by {fmt_date(ready)}"
    next_pos = (db.scalar("SELECT MAX(position) FROM reservations WHERE book_id=? "
                          "AND status='waiting'", (book_id,), 0) or 0) + 1
    db.run("INSERT INTO reservations(book_id,user_id,position,status,created_at) "
           "VALUES(?,?,?,?,?)",
           (book_id, user["id"], next_pos, "waiting", iso(today())))
    notify(db, None, "Waitlist joined",
           f"{user['name']} joined the queue for {book['title']}.", "info",
           f"wait:{book_id}:{user['id']}")
    total = db.scalar("SELECT COUNT(*) FROM copies WHERE book_id=?", (book_id,))
    return True, f"Position #{next_pos} of {total} in the queue"


# request_borrow(db, book_id, user) — "Borrow today": holds a free copy with no expiry for the desk; returns (ok, msg); see A3.3b.
def request_borrow(db, book_id, user):
    """Student asks for a copy to be issued today; the desk processes it."""
    book = db.one("SELECT * FROM books WHERE id=?", (book_id,))
    if not book:
        return False, "Title not found"
    if reservation_for(db, book_id, user["id"]):
        return False, "You already hold a request for this title"
    held = title_loan(db, user["id"], book_id)
    if held:
        return False, f"You already have this title out - due {fmt_date(held['due_date'])}"
    ok, reason = eligibility(db, user)
    if not ok:
        return False, reason
    if available_count(db, book_id) < 1:
        return False, "All copies are out - join the waitlist instead"
    copy = db.one("SELECT * FROM copies WHERE book_id=? AND "
                  "status='available' LIMIT 1", (book_id,))
    db.run("UPDATE copies SET status='reserved' WHERE id=?", (copy["id"],))
    db.run("INSERT INTO reservations(book_id,user_id,status,created_at) "
           "VALUES(?,?,?,?)",
           (book_id, user["id"], "requested", iso(today())))
    notify(db, user["id"], "Borrow request sent",
           f"{book['title']} is set aside for you - collect it at the desk "
           "today.", "info", f"req:{book_id}:{user['id']}")
    notify(db, None, "Borrow request",
           f"{user['name']} asked to borrow {book['title']} today - shelf "
           f"{copy['shelf']}.", "info", f"reqdesk:{book_id}:{user['id']}")
    return True, "Sent to the library desk - collect your book today"


# cancel_reservation(db, res_id, user) — deletes one reservation and re-matches the copy; see A.5.
def cancel_reservation(db, res_id, user):
    res = db.one("SELECT * FROM reservations WHERE id=? AND user_id=?",
                 (res_id, user["id"]))
    if not res:
        return False, "Reservation not found"
    db.run("DELETE FROM reservations WHERE id=?", (res_id,))
    release_hold(db, res["book_id"])
    return True, "Reservation cancelled"


# --- OVERDUE SCAN + REPORTING ---
# run_overdue_scan(db, silent) — reminders, overdue flags, final warnings, SDO cases + blocks; runs on launch, login and every 60 s; see §10 / P5.
def run_overdue_scan(db, silent=True):
    new_alerts = []
    new_alerts.extend(release_expired_holds(db))
    limit = setting(db, "book_limit", BOOK_LIMIT)
    for loan in db.all("SELECT l.*, u.name, u.username, b.title, c.accession "
                       "FROM loans l JOIN users u ON u.id=l.user_id "
                       "JOIN copies c ON c.id=l.copy_id "
                       "JOIN books b ON b.id=c.book_id "
                       "WHERE l.status IN ('active','overdue')"):
        left = days_until(loan["due_date"])
        if loan["status"] == "active" and left < 0:
            db.run("UPDATE loans SET status='overdue' WHERE id=?", (loan["id"],))
        threshold = setting(db, "sdo_after", SDO_AFTER)
        if left == 1:
            if notify(db, loan["user_id"], "Return reminder",
                      f"{loan['title']} is due tomorrow, "
                      f"{fmt_date(loan['due_date'])}.",
                      "warn", f"due-tomorrow:{loan['id']}"):
                new_alerts.append(("Return reminder", loan["title"]))
        if left == 0:
            if notify(db, loan["user_id"], "Due today",
                      f"{loan['title']} is due today - return it by "
                      f"5:00 PM to stay in good standing.",
                      "warn", f"due-today:{loan['id']}"):
                new_alerts.append(("Due today", loan["title"]))
        if left < 0:
            late = -left
            if notify(db, loan["user_id"], "Item overdue",
                      f"{loan['title']} is {late} day(s) past the due date. "
                      f"Return it immediately to clear your account.",
                      "warn", f"late:{loan['id']}:{late}"):
                new_alerts.append(("Item overdue", loan["title"]))
            if notify(db, None, "Overdue alert",
                      f"{loan['name']} ({loan['username']}) - "
                      f"{loan['title']} is {late} day(s) overdue.", "warn",
                      f"syslate:{loan['id']}:{late}"):
                new_alerts.append(("Overdue alert", loan["username"]))
            if late == threshold - 1 and notify(
                    db, loan["user_id"], "Final warning",
                    f"{loan['title']} is {late} day(s) overdue. Return it "
                    f"today - tomorrow your account is restricted and this "
                    f"record is forwarded to the Student Disciplinary "
                    f"Office.", "error", f"finalwarn:{loan['id']}"):
                new_alerts.append(("Final warning", loan["title"]))
            if late >= threshold:
                if not db.one("SELECT id FROM sdo_cases WHERE loan_id=?",
                              (loan["id"],)):
                    case = db.run(
                        "INSERT INTO sdo_cases(loan_id,user_id,reason,"
                        "status,created_at) VALUES(?,?,?,?,?)",
                        (loan["id"], loan["user_id"],
                         f"{loan['title']} overdue by {late} days",
                         "pending", iso(today())))
                    notify(db, None, "SDO escalation",
                           f"Case SDO-{case:03d} opened for {loan['name']} - "
                           f"{loan['title']} ({late} days overdue).", "error",
                           f"sdo:{loan['id']}")
                    notify(db, loan["user_id"], "Referred to the SDO",
                           "Your overdue record was forwarded to the Student "
                           "Disciplinary Office.", "error",
                           f"sdocase:{loan['id']}")
                    new_alerts.append(("SDO escalation", loan["name"]))
                db.run("UPDATE users SET status='blocked' WHERE id=? AND "
                       "status='active'", (loan["user_id"],))
                if notify(db, loan["user_id"], "Account restricted",
                          f"{loan['title']} is {late} day(s) overdue, so "
                          f"borrowing is suspended. Return the book, comply "
                          f"with the Student Disciplinary Office, then see "
                          f"the administrator to be reinstated.", "error",
                          f"restricted:{loan['id']}"):
                    new_alerts.append(("Account restricted", loan["name"]))
    if not silent:
        return new_alerts
    return new_alerts


# renewals_remaining(db, user_id) — renewals left on the least-renewed active loan.
def renewals_remaining(db, user_id):
    loans = my_loans(db, user_id)
    return max(0, setting(db, "max_renewals", MAX_RENEWALS) -
               max([l["renewals"] for l in loans], default=0))


# dashboard_stats(db) — KPI counts for the admin dashboard; see C.1.
def dashboard_stats(db):
    total = db.scalar("SELECT COUNT(*) FROM copies")
    available = db.scalar("SELECT COUNT(*) FROM copies WHERE status='available'")
    active = db.scalar("SELECT COUNT(*) FROM loans WHERE status IN "
                       "('active','overdue')")
    reservations = db.scalar("SELECT COUNT(*) FROM reservations")
    ready = db.scalar("SELECT COUNT(*) FROM reservations WHERE status='ready'")
    overdue = db.scalar("SELECT COUNT(*) FROM loans WHERE status='overdue'")
    escalated = db.scalar("SELECT COUNT(*) FROM sdo_cases WHERE status='pending'")
    titles = db.scalar("SELECT COUNT(*) FROM books")
    return dict(total=total, available=available, active=active,
                reservations=reservations, ready=ready, overdue=overdue,
                escalated=escalated, titles=titles)


# escalation_buckets(db) — overdue loans split into warn / escalated / pending / acknowledged; see C1.4 / C4.2.
def escalation_buckets(db):
    rows = db.all("SELECT l.due_date, s.status AS sdo FROM loans l "
                  "LEFT JOIN sdo_cases s ON s.loan_id=l.id "
                  "WHERE l.status='overdue'")
    b = {"warn": 0, "escalated": 0, "pending": 0, "acknowledged": 0}
    threshold = setting(db, "sdo_after", SDO_AFTER)
    for r in rows:
        late = -days_until(r["due_date"])
        if late >= threshold:
            b["escalated"] += 1
        elif late >= 1:
            b["warn"] += 1
        if r["sdo"] == "pending":
            b["pending"] += 1
        elif r["sdo"] == "acknowledged":
            b["acknowledged"] += 1
    return b


# weekly_activity(db) — last-7-days transaction counts for the circulation chart.
def weekly_activity(db):
    labels = []
    counts = []
    for i in range(6, -1, -1):
        day = today() - dt.timedelta(days=i)
        n = db.scalar("SELECT COUNT(*) FROM transactions WHERE ts LIKE ?",
                      (day.isoformat() + "%",), 0)
        labels.append(day.strftime("%a"))
        counts.append(n)
    return labels, counts


# recent_transactions(db, limit) — newest audit rows with borrower program / section, book title and staff names.
def recent_transactions(db, limit=8):
    return db.all(
        "SELECT t.*, u.username, u.name, u.program, u.section, c.accession, "
        "b.title AS title, s.name AS staff "
        "FROM transactions t LEFT JOIN users u ON u.id=t.user_id "
        "LEFT JOIN copies c ON c.id=t.copy_id "
        "LEFT JOIN books b ON b.id=c.book_id "
        "LEFT JOIN users s ON s.id=t.staff_id "
        "ORDER BY t.ts DESC LIMIT ?", (limit,))


# tx_time(iso_ts) — transaction timestamp → short display time.
def tx_time(iso_ts):
    try:
        return dt.datetime.fromisoformat(iso_ts).strftime("%I:%M %p").lstrip("0")
    except Exception:
        return iso_ts
# acc(book_id, i) — builds the PDM-xxxxxx accession for copy i of a title.
def acc(book_id, i=0):
    return f"PDM-{1000 + book_id * 40 + i:06d}"


# --- DEMO LOANS, HOLDS + NOTICES (seed only) ---
# seed_activity(db) — demo loans, holds, cases + notices; seed only.
def seed_activity(db):
    # borrow(...) — plants one demo loan: checkout back_days ago, due late_days out.
    def borrow(username, book_id, copy_index, back_days, late_days,
               status="active", renewals=0):
        u = db.one("SELECT id FROM users WHERE username=?", (username,))
        c = db.one("SELECT id FROM copies WHERE accession=?",
                   (acc(book_id, copy_index),))
        if not u or not c:
            return None
        checkout = today() - dt.timedelta(days=back_days)
        due = today() + dt.timedelta(days=late_days)
        loan_id = db.run(
            "INSERT INTO loans(copy_id,user_id,checkout_date,due_date,"
            "renewals,status) VALUES(?,?,?,?,?,?)",
            (c["id"], u["id"], iso(checkout), iso(due), renewals, status))
        db.run("UPDATE copies SET status='checked_out' WHERE id=?", (c["id"],))
        db.run("INSERT INTO transactions(ts,user_id,copy_id,type,staff_id,"
               "status,note) VALUES(?,?,?,?,?,?,?)",
               (dt.datetime.combine(checkout, dt.time(9, 30)).isoformat(
                   timespec="seconds"), u["id"], c["id"], "Checkout", 7,
                "Completed", f"Due {iso(due)}"))
        return loan_id

    # reserve_slot(...) — plants one demo reservation in the given state.
    def reserve_slot(username, book_id, position, status, ahead_days=0):
        u = db.one("SELECT id FROM users WHERE username=?", (username,))
        created = today() - dt.timedelta(days=max(ahead_days, 1))
        ready = iso(today() + dt.timedelta(days=HOLD_DAYS)) if status == "ready" else None
        db.run("INSERT INTO reservations(book_id,user_id,position,status,"
               "created_at,ready_at) VALUES(?,?,?,?,?,?)",
               (book_id, u["id"], position, status, iso(created), ready))

    borrow("2024-01842", 5, 0, 10, 4)
    borrow("2024-01842", 7, 0, 13, 1)
    borrow("2024-01842", 6, 0, 5, 9)
    overdue_loan = borrow("2022-00988", 1, 0, 32, -18, status="overdue")
    borrow("2022-00988", 12, 0, 8, 6)
    borrow("2023-00615", 8, 0, 16, -2, status="overdue")
    borrow("2023-00615", 9, 0, 7, 7)
    borrow("2023-00615", 1, 2, 4, 10)
    borrow("2024-02481", 3, 0, 3, 11)
    borrow("2024-02481", 1, 3, 11, 3)
    borrow("2025-01177", 4, 0, 9, 5)
    borrow("2025-01177", 1, 1, 8, 6)
    borrow("2023-03390", 13, 0, 6, 8)
    borrow("2023-03390", 1, 4, 2, 12)

    reserve_slot("2023-03390", 1, 1, "waiting", 6)
    reserve_slot("2025-01177", 1, 2, "waiting", 4)
    reserve_slot("2024-01842", 1, 3, "waiting", 3)
    reserve_slot("2024-01842", 10, None, "ready", 1)
    db.run("UPDATE copies SET status='reserved' WHERE accession=?",
           (acc(10, 0),))

    if overdue_loan:
        carlo = db.one("SELECT id FROM users WHERE username='2022-00988'")
        db.run("INSERT INTO sdo_cases(loan_id,user_id,reason,status,created_at) "
               "VALUES(?,?,?,?,?)",
               (overdue_loan, carlo["id"],
                "Python Programming: An Introduction to Computer Science "
                "overdue by 18 days", "pending",
                iso(today() - dt.timedelta(days=4))))

    for user_id, title, body, kind, back in (
            (None, "Nightly backup completed",
             "library.db snapshot stored at 2:05 AM.", "system", 0),
            (None, "3 returned books need shelving",
             "Circulation desk has items ready for the stacks.", "system", 0),
            (None, "Inventory sync finished",
             "Shelf locations verified against the catalog.", "system", 1)):
        ts = dt.datetime.combine(today() - dt.timedelta(days=back),
                                 dt.time(8, 0)).isoformat(timespec="seconds")
        db.run("INSERT INTO notifications(user_id,title,body,level,kind,dedupe,"
               "ts,read) VALUES(?,?,?,?,?,?,?,0)",
               (user_id, title, body, "info", kind, f"sys:{kind}:{title}:{back}",
                ts))
    db.run("INSERT INTO transactions(ts,user_id,copy_id,type,staff_id,status,"
           "note) VALUES(?,?,?,?,?,?,?)",
           (dt.datetime.combine(today(), dt.time(10, 18)).isoformat(
               timespec="seconds"), 4, db.scalar(
                   "SELECT id FROM copies WHERE accession=?", (acc(8, 1),)),
            "Return", 8, "Overdue noted", "Returned 1 day late"))
    db.run("INSERT INTO transactions(ts,user_id,copy_id,type,staff_id,status,"
           "note) VALUES(?,?,?,?,?,?,?)",
           (dt.datetime.combine(today(), dt.time(10, 37)).isoformat(
               timespec="seconds"), 5, db.scalar(
                   "SELECT id FROM copies WHERE accession=?", (acc(4, 0),)),
            "Renewal", 7, "Completed", f"Extended by {LOAN_DAYS} days"))
    db.conn.commit()
ROLE_LABEL = {"student": "Student", "staff": "Staff",
              "admin": "Administrator"}


# --- FORM WIDGETS (auth + dialogs) ---
# entry(...) — themed text input for auth forms and dialogs.
def entry(parent, show=None, width=None):
    e = tk.Entry(parent, bg=WHITE, fg=INK, insertbackground=INK, relief="flat",
                 highlightthickness=1, highlightbackground=LINE,
                 highlightcolor=MAROON, font=(BODY, 11), bd=8, show=show)
    if width:
        e.configure(width=width)
    return e


# placeholder(e, text) — grey hint text, cleared on focus.
def placeholder(e, text):
    e.insert(0, text)
    e.configure(fg="#A79C8E")

    # clears the hint text on focus.
    def on_focus_in(evt):
        if e.get() == text:
            e.delete(0, "end")
            e.configure(fg=INK)

    # restores the hint text when left empty.
    def on_focus_out(evt):
        if not e.get().strip():
            e.delete(0, "end")
            e.insert(0, text)
            e.configure(fg="#A79C8E")

    e.bind("<FocusIn>", on_focus_in)
    e.bind("<FocusOut>", on_focus_out)
    return e


# field(...) — labelled entry with optional hint; auth forms.
def field(parent, label, show=None, hint=None):
    wrap = tk.Frame(parent, bg=WHITE)
    wrap.pack(fill="x", pady=(0, 14))
    tk.Label(wrap, text=label, bg=WHITE, fg=INK, font=(BODY, 10, "bold"),
             anchor="w").pack(fill="x", pady=(0, 6))
    box = tk.Frame(wrap, bg=WHITE)
    box.pack(fill="x")
    if hint:
        tk.Label(box, text=hint, bg=WHITE, fg="#A79C8E", font=(BODY, 11),
                 width=3).pack(side="left", padx=(10, 0))
    e = entry(box, show=show)
    e.pack(side="left", fill="x", expand=True, padx=(0 if hint else 0, 0),
           ipady=4)
    box.configure(highlightthickness=1, highlightbackground=LINE)
    return e


# =====================================================================
# CLASS: App(tk.Tk)
# Layer:   PRESENTATION / root window   (grep: "# CLASS: App")
# Inherits: tk.Tk  — the OS-level root window of the whole application.
# Purpose: Owns the database handle, builds the auth screens (login/signup),
#          opens/closes the Shell, and runs the 60-second overdue-scan timer.
# Startup: App() -> Database() -> init_db() -> run_overdue_scan()
#                      -> build_login() -> after(2000, tick)
# Objects: self.db (Database), self.shell (Shell), Tk widgets, Toast popups.
#          Search: grep -n "App()\|Shell(\|Toast(" library_system.py
# =====================================================================
class App(tk.Tk):
    # App — root window; builds auth, starts the scan tick; see WORKFLOW.md section 2.

    # METHOD: __init__(self)
    # Constructor / STARTUP CHAIN. Sizes the window, opens the DB, creates the
    # schema + seed, runs the first overdue scan, draws the login screen and
    # schedules the first heartbeat tick after 2 s.
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} - Lending & Reservation System")
        self.configure(bg=CREAM)
        w = min(1440, self.winfo_screenwidth() - 60)
        h = min(900, self.winfo_screenheight() - 90)
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(1150, 720)
        self.db = Database()          # <== OBJECT Database (the app's only DB handle)
        init_db(self.db)
        run_overdue_scan(self.db)
        self.user = None
        self.shell = None
        self.login_role = tk.StringVar(value="student")
        self.build_login()
        self.after(2000, self.tick)

    # METHOD: clear_root(self)
    # Destroys every child widget of the root — used before drawing the next
    # screen so login/signup/shell never overlap.
    def clear_root(self):
        for child in self.winfo_children():
            child.destroy()

    # METHOD: tick(self)
    # BACKGROUND HEARTBEAT (every 60 000 ms). Runs run_overdue_scan(); if new
    # alerts were raised, shows a warn Toast and refreshes the bell badge.
    # Errors are swallowed so a bad scan can never kill the timer, then it
    # reschedules itself with after(60000, ...).
    def tick(self):
        try:
            new = run_overdue_scan(self.db)
            if new:
                title, detail = new[0]
                Toast(self, title, detail, "warn")   # <== OBJECT Toast
                if self.shell:
                    self.shell.refresh_bell()
        except Exception:
            pass
        self.after(60000, self.tick)

    # METHOD: build_auth_left(self, left)
    # Draws the shared maroon branding panel (logo, slogan, hero headline,
    # "N catalogued books" counter, Data Privacy Act footer) reused by both
    # the sign-in and sign-up screens.
    def build_auth_left(self, left):
        brand = tk.Frame(left, bg=MAROON_DARK)
        brand.pack(anchor="nw", padx=54, pady=(50, 0))
        badge = tk.Canvas(brand, width=54, height=54, bg=MAROON_DARK,
                          highlightthickness=0)
        badge.pack(side="left", padx=(0, 16))
        badge.create_oval(2, 2, 52, 52, fill=GOLD, outline="#F0D57A", width=2)
        badge.create_oval(9, 9, 45, 45, fill=MAROON_DARK, outline=GOLD, width=1)
        badge.create_text(27, 27, text="PDM", fill=GOLD,
                          font=tkfont.Font(family=HEAD, size=11, weight="bold"))
        tk.Label(brand, text="Pambayang Dalubhasan ng Marilao", bg=MAROON_DARK,
                 fg=WHITE, font=tkfont.Font(family=HEAD, size=17, weight="bold"),
                 anchor="w").pack(anchor="w")
        tk.Label(brand, text="SERVING LEARNERS SINCE 2010", bg=MAROON_DARK,
                 fg=GOLD, font=tkfont.Font(family=BODY, size=9, weight="bold"),
                 anchor="w").pack(anchor="w")

        hero = tk.Frame(left, bg=MAROON_DARK)
        hero.pack(anchor="w", padx=54, pady=(110, 0))
        tk.Label(hero, text="LIBRARY OPERATIONS PORTAL", bg=MAROON_DARK,
                 fg=GOLD, font=tkfont.Font(family=BODY, size=10, weight="bold"))
        tk.Label(hero, text="Knowledge, ready when\nour community needs it.",
                 bg=MAROON_DARK, fg=WHITE, justify="left",
                 font=tkfont.Font(family=HEAD, size=34, weight="bold"),
                 pady=10).pack(anchor="w")
        tk.Label(hero, text="Search the collection, reserve titles, manage "
                 "loans, and keep circulation\nmoving from one trusted "
                 "workspace.", bg=MAROON_DARK, fg="#D8C7C0", justify="left",
                 font=(BODY, 12), pady=14).pack(anchor="w")
        stats = tk.Frame(hero, bg=MAROON_DARK)
        stats.pack(anchor="w", pady=(6, 0))
        total = self.db.scalar("SELECT COUNT(*) FROM copies")
        for text in (f"{total:,} catalogued books", "Open until 5:00 PM"):
            item = tk.Frame(stats, bg=MAROON_DARK)
            item.pack(side="left", padx=(0, 28))
            tk.Label(item, text="✓", bg=GOLD, fg=MAROON_DARK,
                     font=(BODY, 9, "bold"), width=2, pady=2).pack(
                side="left", padx=(0, 8))
            tk.Label(item, text=text, bg=MAROON_DARK, fg="#EFE3DC",
                     font=(BODY, 11)).pack(side="left")

        tk.Label(left, text="Authorized PDM users only  •  Activity is logged "
                 "in accordance with campus library policy and the Data "
                 "Privacy Act.", bg=MAROON_DARK, fg="#A98F87",
                 font=(BODY, 9), wraplength=460, justify="left").pack(
            side="bottom", anchor="w", padx=54, pady=40)

    # METHOD: build_login(self)
    # Builds the SIGN-IN screen: maroon hero + white form with Student /
    # Staff / Administrator role tabs, ID + password fields, the
    # "Create an account" link (student tab only) and the credential hint box.
    def build_login(self):
        self.clear_root()
        self.user = None
        self.shell = None
        self.login_role = tk.StringVar(value="student")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=5)
        self.columnconfigure(1, weight=6)

        left = tk.Frame(self, bg=MAROON_DARK)
        left.grid(row=0, column=0, sticky="nsew")
        right = tk.Frame(self, bg=CREAM)
        right.grid(row=0, column=1, sticky="nsew")

        self.build_auth_left(left)

        holder = tk.Frame(right, bg=CREAM)
        holder.pack(expand=True)
        panel = tk.Frame(holder, bg=WHITE, highlightthickness=1,
                         highlightbackground="#E3DACB")
        panel.pack(padx=60, pady=40)
        form = tk.Frame(panel, bg=WHITE)
        form.pack(padx=48, pady=(44, 40))
        tk.Frame(form, bg=WHITE, width=470, height=1).pack(fill="x")

        tk.Label(form, text="Welcome back", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=28, weight="bold"),
                 anchor="w").pack(fill="x")
        tk.Label(form, text="Choose your role, then sign in with your PDM "
                 "credentials.", bg=WHITE, fg=MUTED, font=(BODY, 11),
                 anchor="w").pack(fill="x", pady=(6, 22))

        tabs = tk.Frame(form, bg="#F1ECE3", highlightthickness=1,
                        highlightbackground=LINE)
        tabs.pack(fill="x", pady=(0, 22))
        tab_refs = {}

        # highlights the active role tab.
        def select_role(role):
            self.login_role.set(role)
            for key, ref in tab_refs.items():
                active = key == role
                ref.configure(bg=WHITE if active else "#F1ECE3",
                              highlightbackground=MAROON if active else LINE,
                              fg=MAROON if active else MUTED)
            sign.configure(text=f"→   Sign in as {ROLE_LABEL[role]}")
            id_label.configure(text={"student": "Student number",
                                     "staff": "Staff ID",
                                     "admin": "Administrator ID"}[role])
            id_hint.configure(text={"student": "e.g. 2024-018423",
                                    "staff": "e.g. staff",
                                    "admin": "e.g. admin"}[role])
            if role == "student":
                su_link.pack_forget()
                su_note.pack_forget()
                su_row.pack(fill="x", pady=(0, 16))
                su_link.pack(side="left")
            else:
                su_row.pack_forget()
                su_note.pack(fill="x", pady=(0, 16))

        for role, icon in (("student", "◈"), ("staff", "◎"),
                           ("admin", "◉")):
            ref = tk.Button(tabs, text=f"{icon}   {ROLE_LABEL[role]}",
                            command=lambda r=role: select_role(r),
                            bg=WHITE, fg=MAROON, activebackground=WHITE,
                            relief="flat", bd=0, highlightthickness=2,
                            highlightbackground=MAROON, cursor="hand2",
                            font=tkfont.Font(family=BODY, size=10,
                                             weight="bold"), pady=11)
            ref.pack(side="left", fill="x", expand=True, padx=4, pady=4)
            tab_refs[role] = ref

        id_label = tk.Label(form, text="Student number", bg=WHITE, fg=INK,
                            font=(BODY, 10, "bold"), anchor="w")
        id_label.pack(fill="x", pady=(0, 6))
        id_row = tk.Frame(form, bg=WHITE, highlightthickness=1,
                          highlightbackground=LINE)
        id_row.pack(fill="x", pady=(0, 16))
        id_hint = tk.Label(id_row, text="e.g. 2024-018423", bg=WHITE,
                           fg="#A79C8E", font=(BODY, 11), width=14)
        id_hint.pack(side="left", padx=(10, 0))
        self.id_entry = entry(id_row)
        self.id_entry.pack(side="left", fill="x", expand=True, ipady=5)

        pw = field(form, "Password", show="•")
        pw.configure(highlightbackground=LINE)
        self.pw_entry = pw

        opts = tk.Frame(form, bg=WHITE)
        opts.pack(fill="x", pady=(0, 20))
        self.remember = tk.BooleanVar(value=True)
        check_row(opts, "Remember this device", self.remember, pady=0,
                  side="left")
        tk.Label(opts, text="Forgot password?", bg=WHITE, fg=MAROON,
                 font=(BODY, 10, "bold"), cursor="hand2").pack(side="right")

        self.login_error = tk.Label(form, text="", bg=WHITE, fg=RED_FG,
                                    font=(BODY, 10, "bold"), anchor="w")
        self.login_error.pack(fill="x")

        sign = tk.Button(form, text="→   Sign in as Student",
                         command=self.attempt_login, bg=MAROON, fg=WHITE,
                         activebackground=MAROON_HOVER, activeforeground=WHITE,
                         relief="flat", bd=0, font=tkfont.Font(
                             family=BODY, size=12, weight="bold"),
                         pady=13, cursor="hand2")
        sign.pack(fill="x", pady=(8, 10))

        su_row = tk.Frame(form, bg=WHITE)
        su_link = tk.Label(su_row, text="Create an account", bg=WHITE,
                           fg=MAROON, font=(BODY, 10, "bold"), cursor="hand2",
                           padx=0)
        su_link.bind("<Button-1>", lambda e: self.build_signup())
        tk.Label(su_row, text="New student?", bg=WHITE, fg=MUTED,
                 font=(BODY, 10)).pack(side="left", padx=(0, 6))
        su_note = tk.Label(form, text="Staff and administrator accounts are "
                           "issued by the library.", bg=WHITE, fg=MUTED,
                           font=(BODY, 10), anchor="w")

        hint = tk.Frame(form, bg=GOLD_SOFT, highlightthickness=1,
                        highlightbackground="#F0E0AE")
        hint.pack(fill="x")
        tk.Label(hint, text="ℹ", bg=GOLD_SOFT, fg=AMBER_FG,
                 font=(BODY, 11, "bold")).pack(side="left", padx=(12, 6),
                                               pady=10)
        tk.Label(hint, text="First-time students: your password is your birth "
                 "date in MMDDYYYY format.\nStaff: pdmstaff  •  Administrator: "
                 "pdmadmin", bg=GOLD_SOFT, fg="#8A6A15", font=(BODY, 10),
                 justify="left", wraplength=360).pack(
            side="left", padx=(0, 12), pady=10)

        links = tk.Frame(form, bg=WHITE)
        links.pack(fill="x", pady=(24, 0))
        for text in ("Library policy", "Help desk", "Privacy notice"):
            tk.Label(links, text=text, bg=WHITE, fg=MUTED, font=(BODY, 9),
                     padx=14).pack(side="left")

        self.id_entry.bind("<Return>", lambda e: self.attempt_login())
        self.pw_entry.bind("<Return>", lambda e: self.attempt_login())
        select_role("student")
        self.id_entry.focus_set()

    # METHOD: attempt_login(self)
    # AUTHENTICATION (Logic P1). Looks up the username in `users`, compares the
    # SHA-256 hash, then verifies the selected role tab matches users.role.
    # Failure -> red inline message; success -> open_shell(user).
    def attempt_login(self):
        role = self.login_role.get()
        username = self.id_entry.get().strip()
        password = self.pw_entry.get()
        user = self.db.one("SELECT * FROM users WHERE username=?",
                           (username,))
        if not user or user["password"] != hash_pw(password):
            self.login_error.configure(
                text="We could not match those credentials. Check your ID and "
                     "password, then try again.")
            return
        if user["role"] != role:
            self.login_error.configure(
                text=f"This account is registered as "
                     f"{ROLE_LABEL[user['role']]} - "
                     f"select the matching role tab.")
            return
        self.login_error.configure(text="")
        self.open_shell(user)

    # METHOD: build_signup(self)
    # Builds the SELF-SERVICE REGISTRATION screen inside a ScrollFrame so all
    # fields stay reachable on short windows. Only the Signup button submits.
    def build_signup(self):
        self.clear_root()
        self.user = None
        self.shell = None
        self.login_role = tk.StringVar(value="student")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=5)
        self.columnconfigure(1, weight=6)

        left = tk.Frame(self, bg=MAROON_DARK)
        left.grid(row=0, column=0, sticky="nsew")
        right = tk.Frame(self, bg=CREAM)
        right.grid(row=0, column=1, sticky="nsew")
        self.build_auth_left(left)

        # OBJECT ScrollFrame — keeps the signup card scrollable (was clipping
        # the Confirm password field and the Signup button on short windows).
        scroll = ScrollFrame(right, bg=CREAM)
        scroll.pack(fill="both", expand=True)
        card_pad = 60
        panel = tk.Frame(scroll.body, bg=WHITE, highlightthickness=1,
                         highlightbackground="#E3DACB")
        panel.pack(padx=card_pad, pady=40)
        form = tk.Frame(panel, bg=WHITE)
        form.pack(padx=48, pady=(44, 40))
        tk.Frame(form, bg=WHITE, width=470, height=1).pack(fill="x")

        top_back = tk.Label(form, text="←   Back", bg=WHITE, fg=MAROON,
                            font=(BODY, 11, "bold"), cursor="hand2",
                            anchor="w")
        top_back.pack(fill="x")
        top_back.bind("<Button-1>", lambda e: self.build_login())
        tk.Label(form, text="Create your account", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=28, weight="bold"),
                 anchor="w").pack(fill="x")
        tk.Label(form, text="Register with your PDM student number to start "
                 "borrowing and reserving titles.", bg=WHITE, fg=MUTED,
                 font=(BODY, 11), anchor="w", wraplength=380,
                 justify="left").pack(fill="x", pady=(6, 20))

        # labelled readonly dropdown for the signup form.
        def combo_field(label, values, state, width=16):
            wrap = tk.Frame(form, bg=WHITE)
            wrap.pack(fill="x", pady=(0, 14))
            tk.Label(wrap, text=label, bg=WHITE, fg=INK, font=(BODY, 10,
                     "bold"), anchor="w").pack(fill="x", pady=(0, 6))
            box = tk.Frame(wrap, bg=WHITE, highlightthickness=1,
                           highlightbackground=LINE)
            box.pack(fill="x")
            var = tk.StringVar()
            cb = ttk.Combobox(box, textvariable=var, values=values,
                              state=state, width=width, font=(BODY, 11))
            cb.pack(side="left", fill="x", expand=True, padx=8, pady=6)
            return var

        id_label = tk.Label(form, text="Student number", bg=WHITE, fg=INK,
                            font=(BODY, 10, "bold"), anchor="w")
        id_label.pack(fill="x", pady=(0, 6))
        id_row = tk.Frame(form, bg=WHITE, highlightthickness=1,
                          highlightbackground=LINE)
        id_row.pack(fill="x", pady=(0, 14))
        tk.Label(id_row, text="e.g. 2024-018423", bg=WHITE, fg="#A79C8E",
                 font=(BODY, 11), width=14).pack(side="left", padx=(10, 0))
        self.su_id = entry(id_row)
        self.su_id.pack(side="left", fill="x", expand=True, ipady=5)

        self.su_name = field(form, "Full name")
        placeholder(self.su_name, "e.g. Juan D. Cruz")
        programs = ["BS Information Technology", "BS Tourism",
                    "BS Hospitality Management", "BS Computer Science",
                    "BS Early Childhood Education", "BTLED",
                    "BS Entrepreneurship"]
        self.su_program = combo_field("Program", programs, "readonly")
        self.su_year = combo_field("Year level",
                                   ["1st Year", "2nd Year", "3rd Year",
                                    "4th Year"], "readonly")
        self.su_section = combo_field("Section", ["A", "B", "C", "D"],
                                      "readonly", width=6)
        self.su_pw = field(form, "Password", show="•")
        self.su_pw.configure(highlightbackground=LINE)
        self.su_pw2 = field(form, "Confirm password", show="•")
        self.su_pw2.configure(highlightbackground=LINE)

        self.su_error = tk.Label(form, text="", bg=WHITE, fg=RED_FG,
                                 font=(BODY, 10, "bold"), anchor="w")
        self.su_error.pack(fill="x")

        self.su_btn = tk.Button(form, text="→   Signup",
                                command=self.attempt_signup, bg=MAROON,
                                fg=WHITE, activebackground=MAROON_HOVER,
                                activeforeground=WHITE, relief="flat", bd=0,
                                font=tkfont.Font(family=BODY, size=12,
                                                  weight="bold"),
                                pady=13, cursor="hand2")
        self.su_btn.pack(fill="x", pady=(8, 12))

        back = tk.Label(form, text="←   Back to sign in", bg=WHITE,
                        fg=MAROON, font=(BODY, 10, "bold"), cursor="hand2",
                        anchor="w")
        back.pack(fill="x")
        back.bind("<Button-1>", lambda e: self.build_login())

        hint = tk.Frame(form, bg=GOLD_SOFT, highlightthickness=1,
                        highlightbackground="#F0E0AE")
        hint.pack(fill="x", pady=(18, 0))
        tk.Label(hint, text="ℹ", bg=GOLD_SOFT, fg=AMBER_FG,
                 font=(BODY, 11, "bold")).pack(side="left", padx=(12, 6),
                                               pady=10)
        tk.Label(hint, text="Your account is active as soon as you register. "
                 "Borrowing starts at the circulation desk.",
                 bg=GOLD_SOFT, fg="#8A6A15", font=(BODY, 10),
                 justify="left", wraplength=360).pack(
            side="left", padx=(0, 12), pady=10)

        # The card canvas must request the card's full width (its content
        # plus the side padding), or the grid starves this column and the
        # card title clips; the idle pass makes winfo_reqwidth() current.
        self.update_idletasks()
        scroll.canvas.configure(width=panel.winfo_reqwidth() + 2 * card_pad)

        self.su_program.set(programs[0])
        self.su_year.set("1st Year")
        self.su_id.focus_set()

    # METHOD: attempt_signup(self)
    # REGISTRATION (Logic P1). Validates student number \d{4}-\d{6}, uniqueness,
    # full name, program + year, section A-D, password >= 6 chars and match.
    # Inserts the `users` row (role='student', status='active'), shows the
    # success dialog and then signs the new student straight in.
    def attempt_signup(self):
        username = self.su_id.get().strip()
        name = self.su_name.get().strip()
        program = self.su_program.get().strip()
        year = self.su_year.get().strip()
        section = self.su_section.get().strip()
        password = self.su_pw.get()
        confirm = self.su_pw2.get()

        # shows a red signup error and stops.
        def fail(msg):
            self.su_error.configure(text=msg)

        if not re.fullmatch(r"\d{4}-\d{6}", username):
            fail("Student number should look like 2024-018423.")
            return
        if self.db.one("SELECT id FROM users WHERE username=?", (username,)):
            fail("That student number is already registered - sign in "
                 "instead.")
            return
        if len(name) < 3 or " " not in name or name.startswith("e.g."):
            fail("Enter your complete name (first and last).")
            return
        if not program or not year:
            fail("Select your program and year level.")
            return
        if section not in ("A", "B", "C", "D"):
            fail("Select your section (A, B, C or D).")
            return
        if len(password) < 6:
            fail("Password must be at least 6 characters.")
            return
        if password != confirm:
            fail("Passwords do not match.")
            return

        self.su_error.configure(text="")
        self.db.run(
            "INSERT INTO users(username,name,role,password,program,year_level,"
            "section,birthdate,status,joined) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (username, name, "student", hash_pw(password), program, year,
             section, "", "active", iso(today())))
        user = self.db.one("SELECT * FROM users WHERE username=?",
                           (username,))
        messagebox.showinfo(
            "Account created",
            f"Your account has been created, {name.split()[0]}!\n"
            "Click OK to open your student dashboard.",
            parent=self)
        self.open_shell(user)

    # METHOD: open_shell(self, user)
    # SESSION START. Creates the Shell for the authenticated user, packs it in,
    # runs a fresh overdue scan, and toasts the unread-notification count.
    def open_shell(self, user):
        self.clear_root()
        self.user = user
        self.shell = Shell(self, user)   # <== OBJECT Shell (post-login workspace)
        self.shell.pack(fill="both", expand=True)
        self.shell.start()
        run_overdue_scan(self.db)
        if self.shell.unread():
            Toast(self, "Library update",      # <== OBJECT Toast
                  f"{self.shell.unread()} new notification(s) for your "
                  f"account.", "info")
NAV = {
    "student": [("catalog", "Catalog", "☰"),
                ("loans", "My loans", "▤"),
                ("reservations", "Reservations", "⚑")],
    "staff": [("circulation", "Circulation", "⇄"),
              ("catalog", "Catalog", "☰"),
              ("transactions", "Transactions", "≣")],
    "admin": [("dashboard", "Dashboard", "▦"),
              ("inventory", "Inventory", "▥"),
              ("users", "Users", "◉"),
              ("cases", "SDO cases", "⚑")],
}

TITLES = {
    "catalog": ("Library catalog", "Search the collection across the PDM shelves"),
    "details": ("Book details", "Catalog record, copies and availability"),
    "loans": ("My loans & reservations", "Track due dates, renewals, holds and "
                                         "your borrowing status"),
    "reservations": ("Reservations", "Queue positions update automatically "
                                     "after each return"),
    "circulation": ("Circulation workspace", "Process checkouts, returns and "
                                             "renewals at the library desk"),
    "transactions": ("Transaction log", "Every circulation event recorded at "
                                        "the desk"),
    "dashboard": ("Library administration", "Operational overview of the "
                                            "PDM collection"),
    "inventory": ("Inventory overview", "Live copy availability and shelf "
                                        "location"),
    "users": ("Users", "Students, library staff and borrowing status"),
    "cases": ("Overdue & SDO escalation", "Cases requiring disciplinary "
                                          "follow-up"),
}


# =====================================================================
# CLASS: Shell(tk.Frame)
# Layer:   PRESENTATION / navigation   (grep: "# CLASS: Shell")
# Inherits: tk.Frame
# Purpose: The post-login workspace. Builds the role-coloured sidebar, the
#          header (screen title + bell + per-screen actions), the screen host
#          frame `self.body`, and ROUTES between screens via navigate(key),
#          which dispatches through the SCREENS dict at the end of the file.
# Roles:   NAV[role] decides the sidebar items — student / staff / admin.
# Objects: held as App.shell; creates every *Screen instance on navigate().
# =====================================================================
class Shell(tk.Frame):
    # Shell — role-coloured frame: sidebar, header, bell and the active screen.

    # METHOD: __init__(self, app, user)
    # Builds sidebar (brand, portal box, nav rows, help, user avatar/sign-out),
    # header (title, subtitle, action slot, bell) and the empty screen host.
    def __init__(self, app, user):
        super().__init__(app, bg=CREAM)
        self.app = app
        self.db = app.db
        self.user = user
        self.current = None
        self.nav = NAV[user["role"]]
        self.bell_panel = None

        side = tk.Frame(self, bg=MAROON_DARK, width=250)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        brand = tk.Frame(side, bg=MAROON_DARK)
        brand.pack(anchor="nw", padx=22, pady=(26, 0))
        logo = tk.Canvas(brand, width=42, height=42, bg=MAROON_DARK,
                         highlightthickness=0)
        logo.pack(side="left", padx=(0, 11))
        logo.create_oval(1, 1, 41, 41, fill=GOLD, outline="#F0D57A", width=2)
        logo.create_oval(7, 7, 35, 35, fill=MAROON_DARK, outline=GOLD)
        logo.create_text(21, 21, text="PDM", fill=GOLD,
                         font=tkfont.Font(family=HEAD, size=8, weight="bold"))
        tk.Label(brand, text=APP_NAME, bg=MAROON_DARK, fg=WHITE, anchor="w",
                 font=tkfont.Font(family=HEAD, size=15, weight="bold")).pack(
            anchor="w")
        tk.Label(brand, text=SLOGAN, bg=MAROON_DARK, fg="#C9AFA8",
                 anchor="w", font=(BODY, 9)).pack(anchor="w")

        portal = tk.Frame(side, bg="#6B1B2B", highlightthickness=1,
                          highlightbackground="#7E2436")
        portal.pack(fill="x", padx=18, pady=(26, 18))
        tk.Label(portal, text=f"{ROLE_LABEL[user['role']]} portal",
                 bg="#6B1B2B",
                 fg="#F0D8DC", font=(BODY, 10, "bold"), pady=10).pack(
            padx=12, anchor="w")

        self.nav_refs = {}
        for key, label, icon in self.nav:
            row = tk.Frame(side, bg=MAROON_DARK, cursor="hand2")
            row.pack(fill="x", padx=12, pady=2)
            lab = tk.Label(row, text=f"{icon}      {label}", bg=MAROON_DARK,
                           fg="#E7D6D1", font=(BODY, 11), anchor="w", pady=11)
            lab.pack(fill="x", padx=14)
            self.nav_refs[key] = (row, lab)
            for wdg in (row, lab):
                wdg.bind("<Button-1>", lambda e, k=key: self.navigate(k))
                wdg.bind("<Enter>", lambda e, r=row, l=lab: l.configure(
                    fg=WHITE) if self.current != self._key_of(r) else None)
                wdg.bind("<Leave>", lambda e, r=row, l=lab, k=key: l.configure(
                    fg="#FFFFFF" if self.current == k else "#E7D6D1"))

        tk.Frame(side, bg=MAROON_DARK).pack(fill="both", expand=True)

        help_box = tk.Frame(side, bg="#4C0F1B", highlightthickness=1,
                            highlightbackground="#6B1B2B")
        help_box.pack(fill="x", padx=16, pady=(0, 14))
        tk.Label(help_box, text="Need help? Visit the library desk\nor call "
                 "local 114.", bg="#4C0F1B", fg="#CBB0AA", font=(BODY, 9),
                 justify="left", padx=12, pady=10).pack()

        foot = tk.Frame(side, bg=MAROON_DARK)
        foot.pack(fill="x", padx=16, pady=(0, 18))
        avatar = tk.Canvas(foot, width=36, height=36, bg=MAROON_DARK,
                           highlightthickness=0)
        avatar.pack(side="left")
        avatar.create_oval(1, 1, 35, 35, fill="#F3E3C8", outline=GOLD)
        avatar.create_text(18, 18, text=initials(user["name"]), fill=MAROON,
                           font=tkfont.Font(family=BODY, size=10,
                                            weight="bold"))
        who = tk.Frame(foot, bg=MAROON_DARK)
        who.pack(side="left", padx=10)
        tk.Label(who, text=user["name"], bg=MAROON_DARK, fg=WHITE,
                 font=(BODY, 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(who, text=user["username"], bg=MAROON_DARK, fg="#C9AFA8",
                 font=(BODY, 9), anchor="w").pack(anchor="w")
        out = tk.Label(foot, text="↪", bg=MAROON_DARK, fg="#E7D6D1",
                       font=(BODY, 14), cursor="hand2")
        out.pack(side="right")
        out.bind("<Button-1>", lambda e: self.logout())

        main = tk.Frame(self, bg=CREAM)
        main.pack(side="left", fill="both", expand=True)

        head = tk.Frame(main, bg=CREAM)
        head.pack(fill="x", padx=34, pady=(26, 6))
        self.head_left = tk.Frame(head, bg=CREAM)
        self.head_left.pack(side="left")
        self.title_lbl = tk.Label(self.head_left, text="", bg=CREAM, fg=INK,
                                  font=tkfont.Font(family=HEAD, size=25,
                                                   weight="bold"), anchor="w")
        self.title_lbl.pack(anchor="w")
        self.sub_lbl = tk.Label(self.head_left, text="", bg=CREAM, fg=MUTED,
                                font=(BODY, 10), anchor="w")
        self.sub_lbl.pack(anchor="w")
        self.head_actions = tk.Frame(head, bg=CREAM)
        self.head_actions.pack(side="right")
        self.bell = self.make_bell(self.head_actions)
        self.bell.pack(side="right")

        self.body = tk.Frame(main, bg=CREAM)
        self.body.pack(fill="both", expand=True, padx=34, pady=(8, 24))
        self.screens = {}

    # METHOD: _key_of(self, row)
    # Reverse lookup: given a sidebar row widget, return its nav key
    # (used by the hover handlers to skip the active item).
    def _key_of(self, row):
        for key, (r, _) in self.nav_refs.items():
            if r is row:
                return key
        return None

    # METHOD: make_bell(self, parent)
    # Draws the notification bell on a Canvas plus the red unread badge, and
    # wires a click on the badge to show_notifications(). Returns the frame.
    def make_bell(self, parent):
        wrap = tk.Frame(parent, bg=CREAM, width=42, height=42)
        wrap.pack_propagate(False)
        cv = tk.Canvas(wrap, width=42, height=42, bg=WHITE,
                       highlightthickness=1, highlightbackground=LINE,
                       cursor="hand2")
        cv.pack()
        cv.create_rectangle(6, 15, 26, 27, fill=MAROON, outline=MAROON)
        cv.create_arc(6, 7, 26, 27, start=180, extent=180, fill=MAROON,
                      outline=MAROON)
        cv.create_rectangle(4, 26, 28, 29, fill=MAROON, outline=MAROON)
        cv.create_oval(14, 30, 20, 36, fill=MAROON, outline=MAROON)
        self.badge = cv.create_oval(26, 4, 40, 18, fill=RED_FG, outline=WHITE,
                                    width=2)
        self.badge_txt = cv.create_text(33, 11, text="0", fill=WHITE,
                                        font=tkfont.Font(family=BODY, size=7,
                                                         weight="bold"))
        cv.tag_bind(self.badge, "<Button-1>", lambda e: self.show_notifications())
        cv.tag_bind(self.badge_txt, "<Button-1>",
                    lambda e: self.show_notifications())
        self.bell_cv = cv
        return wrap

    # METHOD: my_notifications(self)  -> list[sqlite3.Row]
    # Newest 30 notifications for me PLUS system-wide ones (user_id IS NULL).
    def my_notifications(self):
        return self.db.all(
            "SELECT * FROM notifications WHERE user_id IS NULL OR user_id=? "
            "ORDER BY ts DESC LIMIT 30", (self.user["id"],))

    # METHOD: unread(self)  -> int
    # My unread count (own + system-wide) where read=0; drives the badge.
    def unread(self):
        return self.db.scalar(
            "SELECT COUNT(*) FROM notifications WHERE (user_id IS NULL OR "
            "user_id=?) AND read=0", (self.user["id"],))

    # METHOD: refresh_bell(self)
    # Redraws the unread badge from unread(); hides it entirely at zero.
    def refresh_bell(self):
        n = self.unread()
        if n <= 0:
            self.bell_cv.itemconfigure(self.badge, state="hidden")
            self.bell_cv.itemconfigure(self.badge_txt, state="hidden")
        else:
            self.bell_cv.itemconfigure(self.badge, state="normal")
            self.bell_cv.itemconfigure(self.badge_txt, state="normal",
                                       text=str(min(n, 99)))

    # METHOD: show_notifications(self)
    # Bell dropdown: toggles the popup panel, lists up to 12 notifications with
    # colour-coded level dots, then marks everything shown as read=1.
    # Also closes itself on <Escape> and when navigating.
    def show_notifications(self):
        if self.bell_panel and self.bell_panel.winfo_exists():
            self.bell_panel.destroy()
            return
        panel = tk.Toplevel(self)
        panel.overrideredirect(True)
        panel.configure(bg=WHITE, highlightthickness=1,
                        highlightbackground=MAROON)
        panel.lift()
        top = tk.Frame(panel, bg=WHITE)
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(top, text="Notifications", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=14, weight="bold")).pack(
            side="left")
        tk.Label(top, text="Mark all read", bg=WHITE, fg=MAROON,
                 font=(BODY, 9, "bold"), cursor="hand2").pack(side="right")
        tk.Frame(top, bg=WHITE, height=1).pack(fill="x")

        body = tk.Frame(panel, bg=WHITE)
        body.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        rows = self.my_notifications()
        if not rows:
            tk.Label(body, text="Nothing new for your account.", bg=WHITE,
                     fg=MUTED, font=(BODY, 10)).pack(pady=20)
        for row in rows[:12]:
            colour = {"warn": AMBER_FG, "error": RED_FG}.get(row["level"],
                                                            GREEN_FG)
            line = tk.Frame(body, bg=WHITE)
            line.pack(fill="x", pady=6)
            tk.Label(line, text="●", bg=WHITE, fg=colour,
                     font=(BODY, 9)).pack(side="left", padx=(4, 8))
            txt = tk.Frame(line, bg=WHITE)
            txt.pack(side="left", fill="x", expand=True)
            tk.Label(txt, text=row["title"], bg=WHITE, fg=INK,
                     font=(BODY, 10, "bold"), anchor="w").pack(anchor="w")
            tk.Label(txt, text=row["body"], bg=WHITE, fg=MUTED, font=(BODY, 9),
                     wraplength=280, justify="left", anchor="w").pack(anchor="w")
        panel.update_idletasks()
        x = self.bell.winfo_rootx() - 320
        y = self.bell.winfo_rooty() + 46
        panel.geometry(f"340x440+{max(x, 10)}+{max(y, 10)}")
        self.bell_panel = panel
        self.db.run("UPDATE notifications SET read=1 WHERE user_id IS NULL OR "
                    "user_id=?", (self.user["id"],))
        panel.bind("<Escape>", lambda e: panel.destroy())

    # METHOD: start(self)
    # Entry point after login: opens the role's home screen and paints the bell.
    def start(self):
        self.navigate(self.nav[0][0])
        self.refresh_bell()

    # METHOD: navigate(self, key, **ctx)
    # SCREEN ROUTER. Highlights the sidebar item (details maps back to catalog),
    # closes the bell panel, clears the body + header-action slot, rebuilds the
    # bell, sets the title/subtitle from TITLES, then instantiates the screen:
    #     builder = SCREENS[key];  builder(self)
    # `ctx` is handed to the screen (e.g. {"book_id": id} for DetailsScreen).
    def navigate(self, key, **ctx):
        self.current = key
        self.ctx = ctx
        highlight = "catalog" if key == "details" else key
        for k, (row, lab) in self.nav_refs.items():
            active = k == highlight
            row.configure(bg=MAROON if active else MAROON_DARK)
            lab.configure(bg=MAROON if active else MAROON_DARK,
                          fg=WHITE if active else "#E7D6D1")
        if self.bell_panel and self.bell_panel.winfo_exists():
            self.bell_panel.destroy()
        for child in self.body.winfo_children():
            child.destroy()
        for child in list(self.head_actions.winfo_children()):
            child.destroy()
        self.bell = self.make_bell(self.head_actions)
        self.bell.pack(side="right")
        title, sub = TITLES.get(key, (APP_NAME, SLOGAN))
        self.title_lbl.configure(text=title)
        self.sub_lbl.configure(text=sub)
        builder = SCREENS.get(key)
        if builder:
            builder(self)
        self.refresh_bell()

    # METHOD: set_header_actions(self, widget)
    # Lets a screen drop its own buttons into the header (e.g. Export report).
    def set_header_actions(self, widget):
        widget.pack(side="right", padx=10)

    # METHOD: logout(self)
    # Confirms "End this session?", then tears the Shell down and redraws login.
    def logout(self):
        if messagebox.askyesno("Sign out", "End this session?"):
            self.app.build_login()
SELECT_BOOK = """
SELECT b.*,
 (SELECT COUNT(*) FROM copies c WHERE c.book_id=b.id) AS total,
 (SELECT COUNT(*) FROM copies c WHERE c.book_id=b.id AND c.status='available') AS avail,
 (SELECT COUNT(*) FROM copies c WHERE c.book_id=b.id AND c.status='checked_out') AS out,
 (SELECT COUNT(*) FROM copies c WHERE c.book_id=b.id AND c.status='reserved') AS held,
 (SELECT COUNT(*) FROM reservations r WHERE r.book_id=b.id AND r.status IN
  ('waiting','ready','requested')) AS queued,
 (SELECT MIN(l.due_date) FROM loans l JOIN copies c2 ON c2.id=l.copy_id
  WHERE c2.book_id=b.id AND l.status IN ('active','overdue')) AS next_due
FROM books b
"""

YEAR_RANGES = (("All years", None), ("2020 - 2026", (2020, 2026)),
               ("2010 - 2019", (2010, 2019)), ("Before 2010", (0, 2009)))


# book_status(row) — availability pill text (Available / n left / Checked out …) from counts.
def book_status(row):
    if row["avail"] > 0:
        return "Available"
    if row["held"] > 0:
        return "Reserved"
    return "Checked out"


# --- STUDENT SCREENS (catalog, details, loans, reservations) ---
# =====================================================================
# CLASS: CatalogScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "catalog"   (SCREENS router, see below)
# Inherits: tk.Frame
# Purpose: Searchable catalog grid — search bar, availability / material /
#          subject / year filters, sort, and result rows. Read-only for staff
#          and admin; students also get Borrow today / Reserve / Join waitlist.
# Logic:   open() -> navigate("details"); do_reserve() -> reserve();
    #          do_borrow() -> request_borrow(); refresh() re-queries the catalog.
# Objects: built by Shell.navigate("catalog"); contains a ScrollFrame (results)
#          and Toast popups on reserve/borrow results.
# =====================================================================
class CatalogScreen(tk.Frame):
    # METHOD: __init__(self, shell, readonly=False)
    # Logic: Constructor — grabs shell.db, marks itself read-only for non-students,
    # then calls build() to lay out the whole catalog page.
    def __init__(self, shell, readonly=False):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.readonly = readonly or shell.user["role"] != "student"
        self.pack(fill="both", expand=True)
        self.query = tk.StringVar()
        self.search_in = tk.StringVar(value="All fields")
        self.sort_by = tk.StringVar(value="Relevance")
        self.year_range = tk.StringVar(value="All years")
        self.avail = {s: tk.BooleanVar(value=True)
                      for s in ("Available", "Checked out", "Reserved")}
        self.materials = {m: tk.BooleanVar(value=True)
                          for m in ("Book", "Reference", "Thesis")}
        self.subjects = {}
        self.build()
        self.refresh()

    # METHOD: build(self)
    # Logic: lays out the search bar, filters, sort and results table.
    def build(self):
        head = tk.Frame(self, bg=WHITE, highlightthickness=1,
                        highlightbackground=LINE)
        head.pack(fill="x")
        inner = tk.Frame(head, bg=WHITE)
        inner.pack(fill="x", padx=20, pady=16)
        tk.Label(inner, text="Title, author, subject, or ISBN", bg=WHITE,
                 fg=INK, font=(BODY, 10, "bold"), anchor="w").pack(fill="x")
        row = tk.Frame(inner, bg=WHITE)
        row.pack(fill="x", pady=(6, 0))
        box = tk.Frame(row, bg=WHITE, highlightthickness=1,
                       highlightbackground=LINE)
        box.pack(side="left", fill="x", expand=True)
        tk.Label(box, text="⌕", bg=WHITE, fg=MUTED, font=(BODY, 12)).pack(
            side="left", padx=(10, 4))
        self.entry = entry(box)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.after(1, self.refresh))

        sbox = tk.Frame(row, bg=WHITE, highlightthickness=1,
                        highlightbackground=LINE)
        sbox.pack(side="left", padx=(12, 0))
        tk.Label(sbox, text="Search in", bg=WHITE, fg=MUTED,
                 font=(BODY, 9)).pack(side="left", padx=(10, 4))
        combo = ttk.Combobox(sbox, textvariable=self.search_in, width=13,
                             state="readonly",
                             values=["All fields", "Title", "Author",
                                     "Subject", "ISBN"])
        combo.pack(side="left", padx=(0, 8), pady=4)
        combo.bind("<<ComboboxSelected>>", lambda e: self.after(1, self.refresh))

        button(row, "Search catalog", self.refresh, "primary").pack(
            side="left", padx=(12, 0))
        tk.Label(inner, text="Clear search", bg=WHITE, fg=MAROON,
                 font=(BODY, 10, "bold"), cursor="hand2").pack(
            anchor="e", pady=(8, 0))
        tk.Label(inner, text="", bg=WHITE, fg=MUTED, font=(BODY, 10),
                 anchor="w").pack(fill="x")
        self.count_lbl = tk.Label(inner, text="", bg=WHITE, fg=MUTED,
                                  font=(BODY, 10), anchor="w")
        self.count_lbl.pack(fill="x")

        body = tk.Frame(self, bg=CREAM)
        body.pack(fill="both", expand=True, pady=(16, 0))
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        side = tk.Frame(body, bg=WHITE, width=236, highlightthickness=1,
                        highlightbackground=LINE)
        side.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        side.pack_propagate(False)
        pane = tk.Frame(side, bg=WHITE)
        pane.pack(fill="both", expand=True, padx=16, pady=16)
        top = tk.Frame(pane, bg=WHITE)
        top.pack(fill="x")
        tk.Label(top, text="Filter results", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=14, weight="bold")).pack(
            side="left")
        tk.Label(top, text="Reset", bg=WHITE, fg=MAROON,
                 font=(BODY, 9, "bold"), cursor="hand2").pack(side="right")
        top.winfo_children()[-1].bind(
            "<Button-1>", lambda e: self.reset_filters())
        self.filter_pane = pane

        self.results = ScrollFrame(body, bg=WHITE)
        self.results.grid(row=0, column=1, sticky="nsew")
        self.results.configure(highlightthickness=1,
                               highlightbackground=LINE)

        sort_bar = tk.Frame(body, bg=CREAM)
        sort_bar.grid(row=1, column=1, sticky="ew", pady=(10, 0))
        tk.Label(sort_bar, text="Sort by", bg=CREAM, fg=MUTED,
                 font=(BODY, 10)).pack(side="left")
        cb = ttk.Combobox(sort_bar, textvariable=self.sort_by, width=14,
                          state="readonly",
                          values=["Relevance", "Title A-Z", "Newest",
                                  "Oldest"])
        cb.pack(side="left", padx=8)
        cb.bind("<<ComboboxSelected>>", lambda e: self.after(1, self.refresh))

    # METHOD: reset_filters(self)
    # Logic: restores the default search, filters and sort.
    def reset_filters(self):
        for var in list(self.avail.values()) + list(self.materials.values()):
            var.set(True)
        for var in self.subjects.values():
            var.set(True)
        self.year_range.set("All years")
        self.entry.delete(0, "end")
        self.query.set("")
        self.refresh()

    # METHOD: where(self)
    # Logic: SQL filters for the current search text, field and dropdowns.
    def where(self):
        clauses, args = [], []
        q = self.query.get().strip() or self.entry.get().strip()
        field = self.search_in.get()
        if q and q != "":
            target = {"Title": "b.title", "Author": "b.author",
                      "Subject": "b.subject", "ISBN": "b.isbn"}.get(field)
            if target:
                clauses.append(f"LOWER({target}) LIKE ?")
                args.append(f"%{q.lower()}%")
            else:
                clauses.append("(LOWER(b.title) LIKE ? OR LOWER(b.author) LIKE ?"
                               " OR LOWER(b.subject) LIKE ? OR LOWER(b.isbn) "
                               "LIKE ?)")
                args.extend([f"%{q.lower()}%"] * 4)
        return " AND ".join(clauses) if clauses else "1=1", args, q

    # METHOD: all_rows(self)
    # Logic: every catalog row with availability counts for filtering.
    def all_rows(self):
        where, args, _ = self.where()
        return self.db.all(SELECT_BOOK + " WHERE " + where, args)

    # METHOD: filtered(self, rows)
    # Logic: applies the in-memory filters and sort to catalog rows.
    def filtered(self, rows):
        chosen_status = {k for k, v in self.avail.items() if v.get()}
        chosen_mat = {k for k, v in self.materials.items() if v.get()}
        rng = dict(YEAR_RANGES)[self.year_range.get()]
        out = []
        for row in rows:
            if book_status(row) not in chosen_status:
                continue
            if row["material_type"] not in chosen_mat:
                continue
            box = self.subjects.get(row["subject"])
            if box is not None and not box.get():
                continue
            if rng and not (rng[0] <= (row["year"] or 0) <= rng[1]):
                continue
            out.append(row)
        order = self.sort_by.get()
        if order == "Title A-Z":
            out.sort(key=lambda r: r["title"].lower())
        elif order == "Newest":
            out.sort(key=lambda r: -(r["year"] or 0))
        elif order == "Oldest":
            out.sort(key=lambda r: (r["year"] or 0))
        else:
            q = (self.query.get().strip() or "").lower()
            out.sort(key=lambda r: (0 if q in r["title"].lower() else 1,
                                    r["title"].lower()))
        return out

    # METHOD: build_filters(self, rows)
    # Logic: availability / material / subject / year checkboxes from the rows.
    def build_filters(self, rows):
        pane = self.filter_pane
        for child in pane.winfo_children()[1:]:
            child.destroy()

        # one titled checkbox group inside the filter panel.
        def group(title, pairs):
            tk.Label(pane, text=title, bg=WHITE, fg=MUTED,
                     font=(BODY, 9, "bold")).pack(anchor="w", pady=(14, 6))
            for text, var, count in pairs:
                check_row(pane, text, var, count=count, pady=3,
                          command=lambda: self.after(1, self.refresh))

        group("AVAILABILITY", [
            (k, self.avail[k], sum(1 for r in rows if book_status(r) == k))
            for k in ("Available", "Checked out", "Reserved")])
        group("MATERIAL TYPE", [
            (k, self.materials[k],
             sum(1 for r in rows if r["material_type"] == k))
            for k in ("Book", "Reference", "Thesis")])

        tally = {}
        for r in rows:
            tally[r["subject"]] = tally.get(r["subject"], 0) + 1
        top_subjects = sorted(tally, key=lambda s: -tally[s])[:6]
        new_vars = {s: self.subjects.get(s, tk.BooleanVar(value=True))
                    for s in top_subjects}
        self.subjects = new_vars
        group("SUBJECT", [(s, new_vars[s], tally[s]) for s in top_subjects])

        tk.Label(pane, text="Publication year", bg=WHITE, fg=MUTED,
                 font=(BODY, 9, "bold")).pack(anchor="w", pady=(16, 6))
        cb = ttk.Combobox(pane, textvariable=self.year_range, state="readonly",
                          values=[y[0] for y in YEAR_RANGES])
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda e: self.after(1, self.refresh))

    # METHOD: refresh(self)
    # Logic: re-queries and redraws the results for the current filters.
    def refresh(self):
        self.query.set(self.entry.get())
        self.mine = {}
        self.held = {}
        if not self.readonly:
            for res in my_reservations(self.db, self.shell.user["id"]):
                self.mine[res["bid"]] = res
            for loan in self.db.all(
                    "SELECT c.book_id AS bid, l.due_date FROM loans l "
                    "JOIN copies c ON c.id=l.copy_id WHERE l.user_id=? AND "
                    "l.status IN ('active','overdue')", (self.shell.user["id"],)):
                self.held[loan["bid"]] = loan
        rows = self.all_rows()
        self.build_filters(rows)
        rows = self.filtered(rows)
        q = (self.query.get() or "").strip()
        self.count_lbl.configure(
            text=f"{len(rows)} result(s) for “{q or 'all records'}”  •  "
                 f"Updated just now")
        for child in self.results.body.winfo_children():
            child.destroy()
        if not rows:
            empty = tk.Frame(self.results.body, bg=WHITE)
            empty.pack(fill="x", pady=60)
            tk.Label(empty, text="No matches", bg=WHITE, fg=AMBER_FG,
                     font=tkfont.Font(family=HEAD, size=16, weight="bold"),
                     anchor="w").pack(anchor="w")
            tk.Label(empty, text="Try clearing filters or searching a different "
                     "title, author or subject.", bg=WHITE, fg=MUTED,
                     font=(BODY, 10), anchor="w").pack(anchor="w", pady=(4, 14))
            button(empty, "Clear search", self.reset_filters, "ghost").pack(
                anchor="w")
            return
        for i, row in enumerate(rows):
            self.book_row(row, i == len(rows) - 1)

    # METHOD: book_row(self, row, last)
    # Logic: one catalog row: cover, meta, availability, Borrow today / Reserve buttons.
    def book_row(self, row, last):
        status = book_status(row)
        mine = self.mine.get(row["id"])
        held = self.held.get(row["id"])
        wrap = tk.Frame(self.results.body, bg=WHITE)
        wrap.pack(fill="x", padx=18)
        inner = tk.Frame(wrap, bg=WHITE, highlightthickness=1,
                         highlightbackground=LINE)
        inner.pack(fill="x", pady=(12, 0) if not last else (12, 14))
        body = tk.Frame(inner, bg=WHITE)
        body.pack(fill="x", padx=16, pady=14)
        cover_tile(body, row["title"]).pack(side="left", padx=(0, 16))

        info = tk.Frame(body, bg=WHITE)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=row["call_no"], bg=WHITE, fg=MAROON,
                 font=(BODY, 9, "bold"), anchor="w").pack(anchor="w")
        title_lbl = tk.Label(info, text=row["title"], bg=WHITE, fg=INK,
                             font=tkfont.Font(family=HEAD, size=13,
                                              weight="bold"),
                             anchor="w", cursor="hand2", wraplength=520,
                             justify="left")
        title_lbl.pack(anchor="w", pady=(2, 0))
        tk.Label(info, text=f"by {row['author']}", bg=WHITE, fg=MUTED,
                 font=(BODY, 10), anchor="w").pack(anchor="w")
        meta = "  •  ".join(str(x) for x in (row["edition"], row["publisher"],
                                             row["year"]) if x)
        tk.Label(info, text=meta, bg=WHITE, fg="#9A9084", font=(BODY, 9),
                 anchor="w").pack(anchor="w", pady=(2, 0))

        right = tk.Frame(body, bg=WHITE)
        right.pack(side="right")
        pill(right, status).pack(anchor="e")
        note = {"Available": f"{row['avail']} of {row['total']} copies",
                "Checked out": (f"Due {fmt_date(row['next_due'])}  •  "
                                f"{row['avail']} of {row['total']}")
                if row["next_due"] else f"{row['total']} copies",
                "Reserved": f"Held for pickup  •  {row['queued']} in queue"}[status]
        tk.Label(right, text=note, bg=WHITE, fg=MUTED, font=(BODY, 9),
                 anchor="e").pack(anchor="e", pady=(4, 8))

        if self.readonly:
            button(right, "View record", lambda r=row: self.open(r),
                   "ghost").pack(anchor="e")
        elif held:
            button(right, f"Borrowed - due {fmt_date(held['due_date'])}",
                   lambda r=row: self.open(r), "ghost").pack(anchor="e")
        elif mine:
            label = {"requested": "Borrow requested",
                     "ready": "Ready - pick up"}.get(
                         mine["status"], f"In queue #{mine['position']}")
            button(right, label, lambda r=row: self.open(r),
                   "ghost").pack(anchor="e")
        elif status == "Available":
            button(right, "Borrow today", lambda r=row: self.do_borrow(r),
                   "primary").pack(anchor="e")
            button(right, "Reserve", lambda r=row: self.do_reserve(r),
                   "ghost").pack(anchor="e", pady=(6, 0))
        else:
            button(right, "Join waitlist", lambda r=row: self.do_reserve(r),
                   "ghost").pack(anchor="e")

        for wdg in (title_lbl, info):
            wdg.bind("<Button-1>", lambda e, r=row: self.open(r))

    # METHOD: open(self, row)
    # Logic: jumps to the details screen for a catalog row.
    def open(self, row):
        self.shell.navigate("details", book_id=row["id"])

    # METHOD: do_reserve(self, row)
    # Logic: reserves the row's title via reserve(); refreshes on success.
    def do_reserve(self, row):
        ok, msg = reserve(self.db, row["id"], self.shell.user)
        if ok:
            Toast(self.shell.app, "Reservation placed", msg, "info")
        else:
            messagebox.showinfo("Reservation", msg, parent=self)
        self.refresh()

    # METHOD: do_borrow(self, row)
    # Logic: sends a Borrow-today request via request_borrow(); refreshes on success.
    def do_borrow(self, row):
        ok, msg = request_borrow(self.db, row["id"], self.shell.user)
        if ok:
            Toast(self.shell.app, "Borrow today", msg, "info")
        else:
            messagebox.showinfo("Borrow today", msg, parent=self)
        self.refresh()
# tagged_tree(...) — tree with per-row colour tags for hold / overdue states.
def tagged_tree(parent, columns, widths, rows, tags=None, height=6):
    tv = tree(parent, columns, widths, height=height)
    tv.tag_configure("available", background=WHITE)
    tv.tag_configure("checked", background="#FDF8F6")
    tv.tag_configure("reserved", background="#FEFAF0")
    tv.tag_configure("overdue", background="#FDECEC")
    for r in rows:
        tv.insert("", "end", values=r[0], tags=(r[1],))
    return tv


# =====================================================================
# CLASS: DetailsScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "details"   (opened from CatalogScreen.open)
# Inherits: tk.Frame
# Purpose: One title in full — cover, category pill, bibliographic record,
#          description, subject tags, "Copies & availability" (plus a
#          RESERVED BY column for staff) and related-title tiles.
# Logic:   join() -> reserve(); do_borrow() -> request_borrow();
    #          eligibility() decides whether the action buttons are enabled.
# Objects: built by Shell.navigate("details", book_id=...); Toast on results.
# =====================================================================
class DetailsScreen(tk.Frame):
    # METHOD: __init__(self, shell, book_id)
    # Logic: Constructor — receives the book id from Shell.navigate(**ctx) and
    # builds the single-title record inside a ScrollFrame.
    def __init__(self, shell, book_id):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.book_id = book_id
        self.pack(fill="both", expand=True)

        back = button(shell.head_actions, "Back to results",
                      lambda: shell.navigate("catalog"), "ghost",
                      icon="↩")
        shell.set_header_actions(back)

        book = self.db.one("SELECT * FROM books WHERE id=?", (book_id,))
        if not book:
            tk.Label(self, text="Record not found", bg=CREAM).pack()
            return
        copies = copies_of(self.db, book_id)
        avail = sum(1 for c in copies if c["status"] == "available")
        queue = queue_for(self.db, book_id)
        mine = (reservation_for(self.db, book_id, shell.user["id"])
                if shell.user["role"] == "student" else None)
        on_loan = (title_loan(self.db, shell.user["id"], book_id)
                   if shell.user["role"] == "student" else None)
        is_staff = shell.user["role"] != "student"
        holders = (self.db.all(
            "SELECT u.name FROM reservations r JOIN users u ON u.id=r.user_id "
            "WHERE r.book_id=? AND r.status IN ('ready','requested') "
            "ORDER BY COALESCE(r.ready_at, r.created_at)", (book_id,))
            if is_staff else [])

        scroll = ScrollFrame(self, bg=CREAM)
        scroll.pack(fill="both", expand=True)
        host = scroll.body

        main = tk.Frame(host, bg=CREAM)
        main.pack(side="left", fill="both", expand=True, padx=(0, 18))
        rail = tk.Frame(host, bg=CREAM, width=320)
        rail.pack(side="right", fill="y")

        top = card(main, pad=0)
        top.pack(fill="x")
        inner = tk.Frame(top.inner, bg=WHITE)
        inner.pack(fill="x")
        big = tk.Frame(inner, bg=WHITE)
        big.pack(side="left", padx=(0, 26))
        cv = cover_tile(big, book["title"], width=150, height=200)
        cv.pack()
        tk.Label(big, text=book["edition"], bg=WHITE, fg=MUTED,
                 font=(BODY, 9)).pack(pady=(8, 0))

        info = tk.Frame(inner, bg=WHITE)
        info.pack(side="left", fill="both", expand=True)
        tags = tk.Frame(info, bg=WHITE)
        tags.pack(anchor="w")
        pill(tags, book["category"], "reserved").pack(side="left")
        tk.Label(tags, text=book["call_no"], bg=WHITE, fg=MUTED,
                 font=(BODY, 10, "bold")).pack(side="left", padx=12)
        tk.Label(info, text=book["title"], bg=WHITE, fg=INK, wraplength=500,
                 justify="left", anchor="w",
                 font=tkfont.Font(family=HEAD, size=24, weight="bold")).pack(
            anchor="w", pady=(10, 0))
        tk.Label(info, text=book["author"], bg=WHITE, fg=MUTED,
                 font=(BODY, 11), anchor="w").pack(anchor="w", pady=(2, 14))
        meta = tk.Frame(info, bg=WHITE)
        meta.pack(fill="x")
        for label, value in (("PUBLISHER", book["publisher"]),
                             ("EDITION", book["edition"]),
                             ("PUBLISHED", book["year"]),
                             ("ISBN", book["isbn"])):
            cell = tk.Frame(meta, bg=WHITE)
            cell.pack(side="left", padx=(0, 34))
            tk.Label(cell, text=label, bg=WHITE, fg="#9A9084",
                     font=tkfont.Font(family=BODY, size=8, weight="bold"),
                     anchor="w").pack(anchor="w")
            tk.Label(cell, text=str(value or "-"), bg=WHITE, fg=INK,
                     font=(BODY, 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(info, text=book["description"], bg=WHITE, fg=MUTED,
                 font=(BODY, 10), wraplength=470, justify="left",
                 anchor="w").pack(anchor="w", pady=(16, 0))
        subj = tk.Frame(info, bg=WHITE)
        subj.pack(anchor="w", pady=(14, 0))
        for text in (book["subject"], book["material_type"],
                     book["category"]):
            tag = tk.Label(subj, text=text, bg=CREAM, fg=MUTED,
                           font=(BODY, 9), padx=10, pady=4,
                           highlightthickness=1, highlightbackground=LINE)
            tag.pack(side="left", padx=(0, 8))

        copies_card = card(main, pad=0)
        copies_card.pack(fill="x", pady=(18, 0))
        copies_hdr = section_title(copies_card.inner, "Copies & availability")
        tk.Label(copies_hdr, text=f"{len(copies)} copies  •  "
                 f"{avail} available now", bg=WHITE, fg=MUTED,
                 font=(BODY, 10)).pack(side="right", pady=4)
        rows = []
        hold_i = 0
        for c in copies:
            if c["status"] == "available":
                state, tag, due = "●  Available", "available", "-"
            elif c["status"] == "reserved":
                state, tag, due = "●  Reserved", "reserved", "Pickup hold"
            else:
                state, tag = "●  Checked out", "checked"
                due = fmt_date(c["due_date"]) if c["due_date"] else "-"
            cells = (c["accession"], f"Main Stacks  •  Shelf {c['shelf']}",
                     state, due)
            if is_staff:
                name = "-"
                if c["status"] == "reserved":
                    if hold_i < len(holders):
                        name = holders[hold_i]["name"]
                    hold_i += 1
                cells = (cells[0], name) + cells[1:]
            rows.append((cells, tag))
        holder = tk.Frame(copies_card.inner, bg=WHITE)
        holder.pack(fill="x", pady=(12, 0))
        if is_staff:
            tv = tagged_tree(holder, ["ACCESSION NO.", "RESERVED BY",
                                      "LOCATION", "STATUS", "DUE / HOLD"],
                             [130, 170, 240, 160, 150], rows, height=len(rows))
        else:
            tv = tagged_tree(holder, ["ACCESSION NO.", "LOCATION", "STATUS",
                                      "DUE / HOLD"],
                             [130, 240, 160, 150], rows, height=len(rows))
        tv.pack(fill="x")
        tv.tag_configure("checked", foreground=INK)

        if book["category"]:
            related = self.db.all(
                SELECT_BOOK + " WHERE b.category=? AND b.id<>? LIMIT 3",
                (book["category"], book_id))
            if related:
                rel = card(main, pad=0)
                rel.pack(fill="x", pady=(18, 0))
                section_title(rel.inner, "Related titles",
                              sub=f"Other books in {book['category']}")
                strip = tk.Frame(rel.inner, bg=WHITE)
                strip.pack(fill="x", pady=(14, 0))
                for b in related:
                    self.related_card(strip, b).pack(side="left", fill="x",
                                                     expand=True, padx=(0, 14))

        reserve_card = card(rail, pad=0)
        reserve_card.pack(fill="x")
        pane = reserve_card.inner
        status_text = ("Available now" if avail else "All copies in use")
        pill(pane, status_text, "available" if avail else "reserved").pack(
            anchor="w")
        tk.Label(pane, text=("Borrow it today" if avail else
                             "Reserve your place"), bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=17, weight="bold"),
                 anchor="w").pack(anchor="w", pady=(10, 0))
        if avail:
            body_text = ("Copies are on the shelf. Borrow one today and the "
                         "desk issues it straight away, or reserve one and "
                         "collect it within %d school days." % HOLD_DAYS)
        else:
            body_text = ("You will be notified when a copy is returned. "
                         "Pickup holds last %d school days." % HOLD_DAYS)
        tk.Label(pane, text=body_text, bg=WHITE, fg=MUTED, font=(BODY, 10),
                 wraplength=290, justify="left", anchor="w").pack(
            anchor="w", pady=(6, 14))
        if not avail:
            box = tk.Frame(pane, bg=GOLD_SOFT, highlightthickness=1,
                           highlightbackground="#F0E0AE")
            box.pack(fill="x", pady=(0, 14))
            tk.Label(box, text="CURRENT WAITLIST", bg=GOLD_SOFT, fg=AMBER_FG,
                     font=tkfont.Font(family=BODY, size=8, weight="bold"),
                     anchor="w").pack(fill="x", padx=12, pady=(10, 0))
            pos = ("#%d" % mine["position"]) if mine and mine["position"] \
                else "#%d" % (len(queue) + 1)
            line = tk.Frame(box, bg=GOLD_SOFT)
            line.pack(fill="x", padx=12, pady=(2, 12))
            tk.Label(line, text=f"{len(queue)} waiting  •  Estimated "
                     f"availability: {fmt_date(today() + dt.timedelta(days=21))}",
                     bg=GOLD_SOFT, fg="#8A6A15", font=(BODY, 9),
                     wraplength=190, justify="left", anchor="w").pack(
                side="left")
            tk.Label(line, text=pos, bg=GOLD_SOFT, fg=AMBER_FG,
                     font=tkfont.Font(family=HEAD, size=22,
                                      weight="bold")).pack(side="right")

        if self.shell.user["role"] == "student":
            if on_loan:
                button(pane, f"Borrowed - due {fmt_date(on_loan['due_date'])}",
                       lambda: shell.navigate("reservations"), "ghost",
                       icon="⚑").pack(fill="x")
            elif mine:
                label = {"requested": "Borrow requested",
                         "ready": "Pick up by " + fmt_date(mine["ready_at"])
                         }.get(mine["status"], f"In queue #{mine['position']}")
                b = button(pane, label, lambda: shell.navigate(
                    "reservations"), "ghost", icon="⚑")
                b.pack(fill="x")
            elif avail:
                ok, reason = eligibility(self.db, shell.user)
                b1 = button(pane, "Borrow today", lambda: self.do_borrow(),
                            "primary")
                b1.pack(fill="x")
                b2 = button(pane, "Reserve this title", lambda: self.join(),
                            "ghost", icon="⚑")
                b2.pack(fill="x", pady=(6, 0))
                if not ok:
                    for b in (b1, b2):
                        b.configure(state="disabled", bg=GREY_BG, fg=GREY_FG)
            else:
                ok, reason = eligibility(self.db, shell.user)
                b = button(pane, "Join reservation waitlist",
                           lambda: self.join(), "primary", icon="⚑")
                b.pack(fill="x")
                if not ok:
                    b.configure(state="disabled", bg=GREY_BG, fg=GREY_FG)
            tk.Label(pane, text="Notify me by PDM email and app  ›", bg=WHITE,
                     fg=MUTED, font=(BODY, 9), anchor="w").pack(
                fill="x", pady=(12, 0))
        else:
            button(pane, "Open in circulation", lambda: shell.navigate(
                "circulation"), "ghost").pack(fill="x")

        info_box = tk.Frame(rail, bg=BLUE_BG, highlightthickness=1,
                            highlightbackground="#CFE0F5")
        info_box.pack(fill="x", pady=(16, 0))
        tk.Label(info_box, text="ℹ", bg=BLUE_BG, fg=BLUE_FG,
                 font=(BODY, 11, "bold")).pack(side="left", padx=(12, 6),
                                               pady=12)
        tk.Label(info_box, text="Reservations are unavailable while your "
                 "account has overdue items or an active borrowing "
                 "restriction.", bg=BLUE_BG, fg="#1E4C8F", font=(BODY, 9),
                 wraplength=250, justify="left").pack(
            side="left", padx=(0, 12), pady=12)

    # METHOD: related_card(self, parent, b)
    # Logic: clickable tile that opens a related title.
    def related_card(self, parent, b):
        frame = tk.Frame(parent, bg=WHITE, highlightthickness=1,
                         highlightbackground=LINE, cursor="hand2")
        body = tk.Frame(frame, bg=WHITE)
        body.pack(padx=10, pady=10)
        cover_tile(body, b["title"], width=34, height=46).pack(side="left",
                                                               padx=(0, 8))
        txt = tk.Frame(body, bg=WHITE)
        txt.pack(side="left")
        tk.Label(txt, text=b["title"], bg=WHITE, fg=INK, font=(BODY, 9, "bold"),
                 wraplength=150, justify="left", anchor="w").pack(anchor="w")
        tk.Label(txt, text=b["author"], bg=WHITE, fg=MUTED, font=(BODY, 8),
                 anchor="w").pack(anchor="w")
        status = book_status(b)
        pill(txt, status, "available" if status == "Available"
             else "checked out").pack(anchor="w", pady=(4, 0))
        frame.bind("<Button-1>", lambda e: self.shell.navigate(
            "details", book_id=b["id"]))
        return frame

    # METHOD: join(self)
    # Logic: reserves this title via reserve(); used by the details Reserve button.
    def join(self):
        ok, msg = reserve(self.db, self.book_id, self.shell.user)
        if ok:
            Toast(self.shell.app, "Reservation placed", msg, "info")
        else:
            messagebox.showinfo("Reservation", msg, parent=self)
        self.shell.navigate("details", book_id=self.book_id)

    # METHOD: do_borrow(self)
    # Logic: sends a Borrow-today request via request_borrow(); used by the details button.
    def do_borrow(self):
        ok, msg = request_borrow(self.db, self.book_id, self.shell.user)
        if ok:
            Toast(self.shell.app, "Borrow today", msg, "info")
        else:
            messagebox.showinfo("Borrow today", msg, parent=self)
        self.shell.navigate("details", book_id=self.book_id)
# switch_row(parent, title, note, value) — labelled on/off toggle row (reminder settings).
def switch_row(parent, title, note, value=True):
    line = tk.Frame(parent, bg=WHITE)
    line.pack(fill="x", pady=7)
    tk.Label(line, text=title, bg=WHITE, fg=INK, font=(BODY, 10, "bold"),
             anchor="w").pack(side="left")
    tk.Label(line, text=note, bg=WHITE, fg=MUTED, font=(BODY, 9)).pack(
        side="left", padx=(8, 0))
    state = tk.BooleanVar(value=value)
    cv = tk.Canvas(line, width=34, height=18, bg=WHITE, highlightthickness=0,
                   bd=0, cursor="hand2")
    cv.pack(side="right")

    # repaints the toggle knob for the current on/off state.
    def draw():
        cv.delete("all")
        on = state.get()
        rounded_rect(cv, 1, 1, 33, 17, 8,
                     GREEN_FG if on else "#D6CEC2", GREEN_FG if on else "#D6CEC2")
        cv.create_oval(17 if on else 3, 3, 31 if on else 17, 17,
                       fill=WHITE, outline=WHITE)

    cv.bind("<Button-1>", lambda e: (state.set(not state.get()), draw()))
    draw()
    return line


# loan_status_row(loan) — (pill text, kind) for a loan: overdue / due today / tomorrow / in n days / on time.
def loan_status_row(loan):
    left = days_until(loan["due_date"])
    if left < 0:
        return f"Overdue {-left} days", "overdue"
    if left == 0:
        return "Due today", "due tomorrow"
    if left == 1:
        return "Due tomorrow", "due tomorrow"
    if left <= 3:
        return f"Due in {left} days", "reminder"
    return "On time", "available"


# LoansScreen — My loans: stats, due banner, loan rows with Renew, reservations, status; see A.3.
# =====================================================================
# CLASS: LoansScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "loans"   (student role)
# Inherits: tk.Frame
# Purpose: "My loans & reservations" — four KPI stat cards, the gold due-soon
#          banner, per-loan rows with a Renew button, a Borrowing status card,
#          reminder toggles, fine history and the reservations list.
# Logic:   renew() / renew_all() -> renew_loan();  cancel() -> cancel_reservation();
    #          renewals_remaining() feeds the "renewals left" figure.
# Objects: built by Shell.navigate("loans"); Toast on renew / cancel results.
# =====================================================================
class LoansScreen(tk.Frame):
    screen_key = "loans"

    # METHOD: __init__(self, shell)
    # Logic: Constructor — KPI cards, due-soon banner, loan rows, status card,
    # reminder toggles and fine history for shell.user.
    def __init__(self, shell):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.user = shell.user
        self.pack(fill="both", expand=True)

        scroll = ScrollFrame(self, bg=CREAM)
        scroll.pack(fill="both", expand=True)
        host = scroll.body

        loans = my_loans(self.db, self.user["id"])
        res = my_reservations(self.db, self.user["id"])
        limit = setting(self.db, "book_limit", BOOK_LIMIT)
        due_week = [l for l in loans if days_until(l["due_date"]) <= 1]
        ready = [r for r in res if r["status"] == "ready"]
        ok, reason = eligibility(self.db, self.user)

        stats = tk.Frame(host, bg=CREAM)
        stats.pack(fill="x")
        stat_card(stats, "Active loans", len(loans),
                  f"{limit} book limit", "▤")
        stat_card(stats, "Due soon", len(due_week),
                  "Action needed" if due_week else "All clear",
                  "▦", RED_FG if due_week else GREEN_FG)
        stat_card(stats, "Reservations", len(res),
                  f"{len(ready)} ready" if ready else "Nothing waiting",
                  "⚑", AMBER_FG if ready else MUTED)
        stat_card(stats, "Account status", "Good" if ok else "Restricted",
                  "No restrictions" if ok else reason[:26], "✓",
                  GREEN_FG if ok else RED_FG)

        upcoming = sorted(loans, key=lambda l: l["due_date"])
        upcoming = [l for l in upcoming if days_until(l["due_date"]) <= 1]
        if upcoming:
            first = upcoming[0]
            left = days_until(first["due_date"])
            banner = tk.Frame(host, bg=GOLD_SOFT, highlightthickness=1,
                              highlightbackground="#F0E0AE")
            banner.pack(fill="x", pady=(16, 0))
            tk.Label(banner, text="!", bg=GOLD_SOFT, fg=AMBER_FG,
                     font=tkfont.Font(family=HEAD, size=16, weight="bold"),
                     padx=16, pady=12).pack(side="left")
            txt = tk.Frame(banner, bg=GOLD_SOFT)
            txt.pack(side="left", fill="both", expand=True, pady=10)
            when = ("today" if left <= 0 else "tomorrow" if left == 1
                    else f"in {left} days")
            tk.Label(txt, text=f"{first['title']} is due {when}",
                     bg=GOLD_SOFT, fg="#6E5410",
                     font=tkfont.Font(family=BODY, size=11, weight="bold"),
                     anchor="w").pack(anchor="w")
            tk.Label(txt, text="Return it by 5:00 PM or renew now if no one is "
                     "waiting.", bg=GOLD_SOFT, fg="#8A6A15", font=(BODY, 9),
                     anchor="w").pack(anchor="w")
            button(banner, "Renew book", lambda: self.renew(first["id"]),
                   "ghost").pack(side="right", padx=14, pady=10)

        columns = tk.Frame(host, bg=CREAM)
        columns.pack(fill="both", expand=True, pady=(16, 0))
        left = tk.Frame(columns, bg=CREAM)
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))
        right = tk.Frame(columns, bg=CREAM, width=310)
        right.pack(side="right", fill="y")

        panel = card(left, pad=0)
        panel.pack(fill="both", expand=True)
        loans_hdr = section_title(panel.inner, f"Current loans ({len(loans)})")
        button(loans_hdr, "Renew eligible books", self.renew_all, "ghost",
               icon="↻").pack(side="right", pady=4)
        if loans:
            for loan in loans:
                self.loan_row(panel.inner, loan)
            rw = setting(self.db, "renew_window", RENEW_WINDOW)
            tk.Label(panel.inner, text="Books may be renewed up to "
                     f"{setting(self.db, 'max_renewals', MAX_RENEWALS)} times "
                     "when no reservation exists, from "
                     f"{rw} {'day' if rw == 1 else 'days'} before "
                     "the due date.", bg=WHITE, fg=MUTED,
                     font=(BODY, 9)).pack(anchor="w", pady=(4, 0))
        else:
            empty = tk.Label(panel.inner, text="No active loans. Browse the "
                             "catalog to borrow a title.", bg=WHITE, fg=MUTED,
                             font=(BODY, 10))
            empty.pack(anchor="w", pady=20)

        res_panel = card(left, pad=0)
        res_panel.pack(fill="x", pady=(18, 0))
        section_title(res_panel.inner, "Reservations",
                      sub="Queue positions update automatically after each "
                          "return")
        if res:
            for r in res:
                self.reservation_row(res_panel.inner, r)
        else:
            tk.Label(res_panel.inner, text="No reservations yet.", bg=WHITE,
                     fg=MUTED, font=(BODY, 10)).pack(anchor="w", pady=16)

        status = card(right, pad=0)
        status.pack(fill="x")
        tk.Label(status.inner, text="Borrowing status", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=16, weight="bold"),
                 anchor="w").pack(anchor="w", pady=(0, 12))
        box = tk.Frame(status.inner, bg=GREEN_BG if ok else RED_BG,
                       highlightthickness=1,
                       highlightbackground="#CFE7D7" if ok else "#F5C9C9")
        box.pack(fill="x", pady=(0, 14))
        tk.Label(box, text=("✓  Account in good standing" if ok else
                            "!  Borrowing restricted"), bg=GREEN_BG if ok
                 else RED_BG, fg=GREEN_FG if ok else RED_FG,
                 font=(BODY, 10, "bold"), anchor="w", padx=12,
                 pady=10).pack(fill="x")
        renewals = setting(self.db, "max_renewals", MAX_RENEWALS)
        for label, value in (
                ("Borrowing limit", f"{len(loans)} of {limit} books"),
                ("Outstanding fines", "₱0.00"),
                ("Renewals remaining",
                 f"{max([renewals - l['renewals'] for l in loans], default=renewals)}"
                 " available"),
                ("Library card", "Valid to " + fmt_date(
                    parse(self.user["joined"]).replace(
                        year=parse(self.user["joined"]).year + 4)))):
            line = tk.Frame(status.inner, bg=WHITE)
            line.pack(fill="x", pady=5)
            tk.Label(line, text=label, bg=WHITE, fg=MUTED, font=(BODY, 9)).pack(
                side="left")
            tk.Label(line, text=value, bg=WHITE, fg=INK,
                     font=(BODY, 9, "bold")).pack(side="right")

        remind = card(right, pad=0)
        remind.pack(fill="x", pady=(16, 0))
        tk.Label(remind.inner, text="Reminder settings", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=16, weight="bold"),
                 anchor="w").pack(anchor="w", pady=(0, 8))
        switch_row(remind.inner, "Email reminders", "1 day before due")
        switch_row(remind.inner, "In-app reminders", "On")
        switch_row(remind.inner, "Reservation updates", "Email + in-app")

        fines = card(right, pad=0)
        fines.pack(fill="x", pady=(16, 0))
        tk.Label(fines.inner, text="◷", bg=WHITE, fg=MUTED,
                 font=(BODY, 18)).pack(pady=(0, 6))
        tk.Label(fines.inner, text="No fine history", bg=WHITE, fg=INK,
                 font=(BODY, 11, "bold")).pack()
        tk.Label(fines.inner, text="Adjustments and resolved fines will "
                 "appear here.", bg=WHITE, fg=MUTED, font=(BODY, 9),
                 wraplength=240, justify="center").pack(pady=(4, 0))

    # METHOD: loan_row(self, parent, loan)
    # Logic: one loan row: cover, meta, dates, pill, Renew button.
    def loan_row(self, parent, loan):
        left, tag = loan_status_row(loan)
        line = tk.Frame(parent, bg=WHITE, highlightthickness=1,
                        highlightbackground=LINE)
        line.pack(fill="x", pady=(10, 0))
        body = tk.Frame(line, bg=WHITE)
        body.pack(fill="x", padx=14, pady=12)
        cover_tile(body, loan["title"], width=44, height=58).pack(
            side="left", padx=(0, 14))
        info = tk.Frame(body, bg=WHITE)
        info.pack(side="left")
        tk.Label(info, text=loan["title"], bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=12, weight="bold"),
                 anchor="w", wraplength=300, justify="left").pack(anchor="w")
        tk.Label(info, text=loan["author"], bg=WHITE, fg=MUTED,
                 font=(BODY, 9), anchor="w").pack(anchor="w")
        tk.Label(info, text=loan["call_no"], bg=WHITE, fg=MAROON,
                 font=(BODY, 9, "bold"), anchor="w").pack(anchor="w")

        button(body, "Renew", lambda: self.renew(loan["id"]), "ghost").pack(
            side="right", padx=(16, 0))

        due = tk.Frame(body, bg=WHITE)
        due.pack(side="right", padx=(0, 24))
        tk.Label(due, text="DUE DATE", bg=WHITE, fg="#9A9084",
                 font=tkfont.Font(family=BODY, size=8, weight="bold")).pack(
            anchor="e")
        tk.Label(due, text=fmt_date(loan["due_date"]), bg=WHITE, fg=INK,
                 font=tkfont.Font(family=BODY, size=10, weight="bold")).pack(
            anchor="e", pady=(2, 4))
        pill(due, left, tag).pack(anchor="e")

        checked = tk.Frame(body, bg=WHITE)
        checked.pack(side="right", padx=(0, 20))
        tk.Label(checked, text="CHECKED OUT", bg=WHITE, fg="#9A9084",
                 font=tkfont.Font(family=BODY, size=8, weight="bold")).pack(
            anchor="e")
        tk.Label(checked, text=fmt_date(loan["checkout_date"]), bg=WHITE,
                 fg=MUTED, font=(BODY, 9), anchor="e").pack(anchor="e")

    # METHOD: reservation_row(self, parent, res)
    # Logic: one reservation row with its state label and Cancel button.
    def reservation_row(self, parent, res):
        line = tk.Frame(parent, bg=WHITE, highlightthickness=1,
                        highlightbackground=LINE)
        line.pack(fill="x", pady=(10, 0))
        body = tk.Frame(line, bg=WHITE)
        body.pack(fill="x", padx=14, pady=12)
        icon = tk.Canvas(body, width=38, height=48, bg=MAROON_SOFT,
                         highlightthickness=0)
        icon.pack(side="left", padx=(0, 14))
        icon.create_text(19, 24, text=initials(res["title"]), fill=MAROON,
                         font=tkfont.Font(family=HEAD, size=13,
                                          weight="bold"))
        info = tk.Frame(body, bg=WHITE)
        info.pack(side="left")
        tk.Label(info, text=res["title"], bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=12, weight="bold"),
                 anchor="w", wraplength=330, justify="left").pack(anchor="w")
        tk.Label(info, text=f"by {res['author']}  •  placed "
                 f"{fmt_date(res['created_at'])}", bg=WHITE, fg=MUTED,
                 font=(BODY, 9), anchor="w").pack(anchor="w")

        if res["status"] == "requested":
            right_text, right_note = "Today", "Waiting for the desk"
            tag, label = "pending", "Borrow requested"
        elif res["status"] == "ready":
            right_text, right_note = "Ready", f"Pick up by {fmt_date(res['ready_at'])}"
            tag, label = "ready", "Ready for pickup"
        else:
            right_text = f"#{res['position']}"
            right_note = "Waiting in queue"
            tag, label = "waiting", "Waiting"
        end = tk.Frame(body, bg=WHITE)
        end.pack(side="right", padx=(16, 0))
        pill(end, label, tag).pack(anchor="e", pady=(0, 8))
        button(end, "Cancel", lambda: self.cancel(res["id"]), "ghost").pack(
            anchor="e")

        meta = tk.Frame(body, bg=WHITE)
        meta.pack(side="right", padx=(20, 0))
        tk.Label(meta, text=right_text, bg=WHITE, fg=INK,
                 font=tkfont.Font(family=BODY, size=11, weight="bold")).pack(
            anchor="e")
        tk.Label(meta, text=right_note, bg=WHITE, fg=MUTED, font=(BODY, 9)).pack(
            anchor="e")

    # METHOD: renew(self, loan_id)
    # Logic: renews one loan via renew_loan(); toasts or shows the refusal; see A4.4.
    def renew(self, loan_id):
        ok, msg = renew_loan(self.db, loan_id, self.user)
        if ok:
            Toast(self.shell.app, "Loan renewed", msg, "info")
        else:
            messagebox.showinfo("Renew", msg, parent=self)
        self.shell.navigate(self.screen_key)

    # METHOD: renew_all(self)
    # Logic: renews every eligible loan; toasts the count, lists skipped titles; see A4.5.
    def renew_all(self):
        done, skipped = 0, []
        for loan in my_loans(self.db, self.user["id"]):
            ok, msg = renew_loan(self.db, loan["id"], self.user)
            if ok:
                done += 1
            else:
                skipped.append(f"{loan['title']}: {msg}")
        if done:
            Toast(self.shell.app, "Renewals processed",
                  f"{done} loan(s) extended.", "info")
        if skipped:
            messagebox.showinfo("Renew", "\n".join(skipped[:6]), parent=self)
        self.shell.navigate(self.screen_key)

    # METHOD: cancel(self, res_id)
    # Logic: confirms, then cancels one reservation via cancel_reservation(); see A.5.
    def cancel(self, res_id):
        if not messagebox.askyesno("Cancel reservation",
                                   "Remove this reservation from the queue?",
                                   parent=self):
            return
        ok, msg = cancel_reservation(self.db, res_id, self.user)
        Toast(self.shell.app, "Reservation", msg, "info")
        self.shell.navigate(self.screen_key)


# ReservationsScreen — Active reservations page; reuses LoansScreen rows, list only; see A.4.
# =====================================================================
# CLASS: ReservationsScreen(LoansScreen)
# Layer:   PRESENTATION — screen key "reservations"   (student role)
# Inherits: LoansScreen   <-- INHERITANCE EXAMPLE: it reuses the parent
#           reservation_row() and cancel() machinery and only overrides the
#           body it draws (queue-first ordering + the waitlist explainer).
# Purpose: The student's hold queue — Borrow requested / Ready for pickup /
#          Waiting rows with positions, pickup deadlines and Cancel buttons.
# Logic:   cancel() (inherited) -> cancel_reservation(); my_reservations() rows.
    # =====================================================================
class ReservationsScreen(LoansScreen):
    screen_key = "reservations"

    # METHOD: __init__(self, shell)
    # Logic: Constructor — overrides the parent to draw the waitlist view
    # (active reservations + how-the-waitlist-works rail).
    def __init__(self, shell):
        tk.Frame.__init__(self, shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.user = shell.user
        self.pack(fill="both", expand=True)
        scroll = ScrollFrame(self, bg=CREAM)
        scroll.pack(fill="both", expand=True)
        res = my_reservations(self.db, self.user["id"])

        columns = tk.Frame(scroll.body, bg=CREAM)
        columns.pack(fill="both", expand=True)
        left = tk.Frame(columns, bg=CREAM)
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))
        right = tk.Frame(columns, bg=CREAM, width=320)
        right.pack(side="right", fill="y")

        panel = card(left, pad=0)
        panel.pack(fill="both", expand=True)
        section_title(panel.inner, f"Active reservations ({len(res)})",
                      sub="One active reservation per title")
        if res:
            for r in res:
                self.reservation_row(panel.inner, r)
        else:
            tk.Label(panel.inner, text="You are not waiting on any title. "
                     "Open the catalog and join a waitlist.", bg=WHITE,
                     fg=MUTED, font=(BODY, 10)).pack(anchor="w", pady=20)

        how = card(right, pad=0)
        how.pack(fill="x")
        tk.Label(how.inner, text="How the waitlist works", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=16, weight="bold"),
                 anchor="w").pack(anchor="w", pady=(0, 12))
        steps = (("1", "Join the queue", "One active reservation per title."),
                 ("2", "Watch your position",
                  "Returns automatically advance the queue."),
                 ("3", "Pick up promptly",
                  f"You have {HOLD_DAYS} days once notified."))
        for number, title, note in steps:
            line = tk.Frame(how.inner, bg=WHITE)
            line.pack(fill="x", pady=7)
            tk.Label(line, text=number, bg=MAROON_SOFT, fg=MAROON,
                     font=(BODY, 9, "bold"), width=2, pady=5).pack(
                side="left", padx=(0, 10))
            txt = tk.Frame(line, bg=WHITE)
            txt.pack(side="left")
            tk.Label(txt, text=title, bg=WHITE, fg=INK,
                     font=(BODY, 10, "bold"), anchor="w").pack(anchor="w")
            tk.Label(txt, text=note, bg=WHITE, fg=MUTED, font=(BODY, 9),
                     anchor="w").pack(anchor="w")
# --- STAFF + ADMIN SCREENS (circulation, reports, users, cases) ---
# CirculationScreen — staff desk: Requests list, Returns, Renew lookup, recent activity; see section B.
# =====================================================================
# CLASS: CirculationScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "circulation"   (staff role) — Logic P4
# Inherits: tk.Frame
# Purpose: The library-desk workspace with three tabs:
#            1. Requests — borrow-today + ready-for-pickup rows, Process each
#            2. Return   — accession scan + Process return
#            3. Renew    — find borrower by student number, Renew per loan
#          plus a "Recent transactions" panel and a hold-queue rail.
# Logic:   process_request() and do_return() both ASK FIRST — a
#          messagebox.askyesno showing the title, student, accession and shelf
#          ("No" writes nothing), then run checkout() / return_book().
#          do_renew() -> renew_loan(); requests_view() = reservations with
#          status IN ('requested','ready').
# Objects: built by Shell.navigate("circulation"); Toast per processed row.
# =====================================================================
class CirculationScreen(tk.Frame):
    # METHOD: __init__(self, shell)
    # Logic: Constructor — builds the tab bar and opens on the Requests tab via render().
    def __init__(self, shell):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.staff = shell.user
        self.borrower = None
        self.mode = tk.StringVar(value="Requests")
        self.pack(fill="both", expand=True)

        bar = tk.Frame(self, bg=WHITE, highlightthickness=1,
                       highlightbackground=LINE)
        bar.pack(fill="x")
        inner = tk.Frame(bar, bg=WHITE)
        inner.pack(fill="x", padx=6, pady=6)
        self.tabs = {}
        for mode, icon in (("Requests", "↗"), ("Return", "↙"),
                           ("Renew", "↻")):
            ref = tk.Button(inner, text=f"{icon}   {mode}",
                            command=lambda m=mode: self.set_mode(m),
                            bg=MAROON if mode == "Requests" else WHITE,
                            fg=WHITE if mode == "Requests" else MUTED,
                            relief="flat", bd=0, font=tkfont.Font(
                                family=BODY, size=11, weight="bold"),
                            pady=11, cursor="hand2")
            ref.pack(side="left", fill="x", expand=True, padx=4)
            self.tabs[mode] = ref

        scroll = ScrollFrame(self, bg=CREAM)
        scroll.pack(fill="both", expand=True, pady=(16, 0))
        self.host = scroll.body
        self.render()

    # METHOD: set_mode(self, mode)
    # Logic: switches the desk tab (Requests / Return / Renew) and redraws.
    def set_mode(self, mode):
        self.mode.set(mode)
        for key, ref in self.tabs.items():
            active = key == mode
            ref.configure(bg=MAROON if active else WHITE,
                          fg=WHITE if active else MUTED)
        self.render()

    # METHOD: render(self)
    # Logic: draws the active desk tab.
    def render(self):
        for child in self.host.winfo_children():
            child.destroy()
        columns = tk.Frame(self.host, bg=CREAM)
        columns.pack(fill="both", expand=True)
        main = tk.Frame(columns, bg=CREAM)
        main.pack(side="left", fill="both", expand=True, padx=(0, 16))
        side = tk.Frame(columns, bg=CREAM, width=330)
        side.pack(side="right", fill="y")
        if self.mode.get() == "Requests":
            self.requests_view(main, side)
        elif self.mode.get() == "Return":
            self.return_view(main, side)
        else:
            self.renew_view(main, side)
        self.recent(main)

    # METHOD: borrower_panel(self, parent)
    # Logic: student-number lookup shared by the Return / Renew tabs.
    def borrower_panel(self, parent):
        pane = parent
        if not self.borrower:
            tk.Label(pane, text="No borrower selected", bg=WHITE, fg=MUTED,
                     font=(BODY, 10)).pack(anchor="w")
            return
        u = self.borrower
        ok, reason = eligibility(self.db, u)
        head = tk.Frame(pane, bg=WHITE)
        head.pack(fill="x")
        tk.Label(head, text="Borrower found", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=16, weight="bold")).pack(
            side="left")
        pill(head, "Eligible" if ok else "Restricted",
             "available" if ok else "checked out").pack(side="right")
        who = tk.Frame(pane, bg=WHITE)
        who.pack(fill="x", pady=(14, 0))
        av = tk.Canvas(who, width=46, height=46, bg=WHITE,
                       highlightthickness=0)
        av.pack(side="left", padx=(0, 12))
        av.create_oval(1, 1, 45, 45, fill=MAROON_SOFT, outline=MAROON)
        av.create_text(23, 23, text=initials(u["name"]), fill=MAROON,
                       font=tkfont.Font(family=BODY, size=13, weight="bold"))
        txt = tk.Frame(who, bg=WHITE)
        txt.pack(side="left")
        tk.Label(txt, text=u["name"], bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=14, weight="bold")).pack(
            anchor="w")
        tk.Label(txt, text=f"{u['program']}  •  {u['year_level'] or 'Student'}",
                 bg=WHITE, fg=MUTED, font=(BODY, 9)).pack(anchor="w")
        tk.Label(txt, text=u["username"], bg=WHITE, fg=MAROON,
                 font=(BODY, 10, "bold")).pack(anchor="w")
        loans = my_loans(self.db, u["id"])
        overdue = [l for l in loans if l["status"] == "overdue"]
        for label, value in (
                ("Current loans",
                 f"{len(loans)} of {setting(self.db, 'book_limit', BOOK_LIMIT)}"),
                ("Overdue items", str(len(overdue))),
                ("Outstanding balance", "₱0.00"),
                ("Account valid until", fmt_date(
                    parse(u["joined"]).replace(year=parse(u["joined"]).year + 4))
                 if u["joined"] else "-")):
            line = tk.Frame(pane, bg=WHITE)
            line.pack(fill="x", pady=5)
            tk.Label(line, text=label, bg=WHITE, fg=MUTED, font=(BODY, 9)).pack(
                side="left")
            tk.Label(line, text=value, bg=WHITE, fg=INK,
                     font=(BODY, 9, "bold")).pack(side="right")
        if not ok:
            tk.Label(pane, text=reason, bg=RED_BG, fg=RED_FG, font=(BODY, 9),
                     wraplength=280, justify="left", anchor="w").pack(
                fill="x", pady=(10, 0), padx=0)

    # METHOD: requests_view(self, main, side)
    # Logic: Borrow-today + pickup rows with a Process button each; see B2.
    def requests_view(self, main, side):
        wanted = self.db.all(
            "SELECT r.*, u.username, u.name, b.title, b.call_no FROM "
            "reservations r JOIN users u ON u.id=r.user_id "
            "JOIN books b ON b.id=r.book_id "
            "WHERE r.status IN ('requested','ready') "
            "ORDER BY CASE r.status WHEN 'requested' THEN 0 ELSE 1 END, "
            "COALESCE(r.ready_at, r.created_at)")
        borrow = [r for r in wanted if r["status"] == "requested"]
        pickup = [r for r in wanted if r["status"] == "ready"]

        card1 = card(main, pad=0)
        card1.pack(fill="x")
        section_title(card1.inner, f"Borrow today ({len(borrow)})",
                      sub="Students waiting for the desk to issue their books")
        if not borrow:
            tk.Label(card1.inner, text="No borrow requests waiting.",
                     bg=WHITE, fg=MUTED, font=(BODY, 10)).pack(anchor="w",
                                                               pady=14)
        for res in borrow:
            self.request_row(card1.inner, res, "requested")

        card2 = card(main, pad=0)
        card2.pack(fill="x", pady=(16, 0))
        section_title(card2.inner, f"Reservations awaiting pickup ({len(pickup)})",
                      sub=f"Held at the desk - the pickup window lasts "
                          f"{setting(self.db, 'hold_days', HOLD_DAYS)} days")
        if not pickup:
            tk.Label(card2.inner, text="Nothing waiting for pickup.",
                     bg=WHITE, fg=MUTED, font=(BODY, 10)).pack(anchor="w",
                                                               pady=14)
        for res in pickup:
            self.request_row(card2.inner, res, "ready")

        side1 = card(side, pad=0)
        side1.pack(fill="x")
        pane = side1.inner
        tk.Label(pane, text="How processing works", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=16, weight="bold")).pack(
            anchor="w")
        steps = ("1  A student sends Borrow today or Reserve from the "
                 "catalog.",
                 "2  The title and the held copy appear in the lists here.",
                 "3  Press Process to issue the loan - the student is "
                 "notified with the due date.")
        for step in steps:
            tk.Label(pane, text=step, bg=WHITE, fg=MUTED, font=(BODY, 9),
                     wraplength=270, justify="left", anchor="w").pack(
                anchor="w", pady=(10, 0))
        box = tk.Frame(pane, bg=GOLD_SOFT, highlightthickness=1,
                       highlightbackground="#F0E0AE")
        box.pack(fill="x", pady=(16, 0))
        tk.Label(box, text="WAITING AT THIS DESK", bg=GOLD_SOFT, fg=AMBER_FG,
                 font=tkfont.Font(family=BODY, size=8, weight="bold"),
                 anchor="w").pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(box, text=f"{len(borrow)} borrow  •  {len(pickup)} pickup",
                 bg=GOLD_SOFT, fg="#6E5410",
                 font=tkfont.Font(family=HEAD, size=15, weight="bold"),
                 anchor="w").pack(fill="x", padx=14, pady=(2, 12))

    # METHOD: request_row(self, parent, res, kind)
    # Logic: one request row (borrow-today or pickup) with its Process button.
    def request_row(self, parent, res, kind):
        copy = held_copy(self.db, res["book_id"])
        line = tk.Frame(parent, bg=WHITE, highlightthickness=1,
                        highlightbackground=LINE)
        line.pack(fill="x", pady=(10, 0))
        body = tk.Frame(line, bg=WHITE)
        body.pack(fill="x", padx=14, pady=12)

        info = tk.Frame(body, bg=WHITE)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=res["title"], bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=12, weight="bold"),
                 anchor="w", wraplength=330, justify="left").pack(anchor="w")
        tk.Label(info, text=f"{res['name']}  •  {res['username']}", bg=WHITE,
                 fg=MUTED, font=(BODY, 9), anchor="w").pack(anchor="w")
        where = (f"{copy['accession']}  •  shelf {copy['shelf']}"
                 if copy else "held copy unavailable")
        tk.Label(info, text=where, bg=WHITE, fg=MAROON, font=(BODY, 9),
                 anchor="w").pack(anchor="w", pady=(2, 0))

        if kind == "ready":
            pill_text, pill_tag = "Ready for pickup", "ready"
            right_text, right_note = "Pick up by", fmt_date(res["ready_at"])
        else:
            pill_text, pill_tag = "Borrow today", "pending"
            right_text, right_note = "Requested", fmt_date(res["created_at"])

        meta = tk.Frame(body, bg=WHITE)
        meta.pack(side="right", padx=(20, 0))
        tk.Label(meta, text=right_text, bg=WHITE, fg=INK,
                 font=(BODY, 11, "bold")).pack(anchor="e")
        tk.Label(meta, text=right_note, bg=WHITE, fg=MUTED,
                 font=(BODY, 9)).pack(anchor="e")

        end = tk.Frame(body, bg=WHITE)
        end.pack(side="right", padx=(16, 0))
        pill(end, pill_text, pill_tag).pack(anchor="e", pady=(0, 8))
        button(end, "Process",
               lambda i=res["id"]: self.process_request(i), "primary").pack(
            anchor="e")

    # METHOD: process_request(self, res_id)
    # Logic: confirms the issue first, then hands the held copy to checkout();
    #        the row disappears; declining leaves everything untouched; see B2.
    def process_request(self, res_id):
        res = self.db.one("SELECT r.*, b.title FROM reservations r "
                          "JOIN books b ON b.id=r.book_id WHERE r.id=?",
                          (res_id,))
        if not res:
            self.render()
            return
        user = self.db.one("SELECT * FROM users WHERE id=?", (res["user_id"],))
        copy = held_copy(self.db, res["book_id"])
        if not copy:
            messagebox.showwarning(
                "Requests",
                "No held copy is left for this title. Ask the student to "
                "send the request again.", parent=self)
            self.render()
            return
        if res["status"] == "ready":
            what = "Hand over this pickup hold"
        else:
            what = "Issue this borrow-today request"
        if not messagebox.askyesno(
                "Process request",
                f"{what}?\n\n"
                f"{res['title']}\n"
                f"{user['name']} ({user['username']})\n"
                f"{copy['accession']}  •  shelf {copy['shelf']}",
                parent=self):
            return
        results = checkout(self.db, user, [copy["accession"]], self.staff)
        if results and results[0][1]:
            Toast(self.shell.app, "Request processed",
                  f"{user['name']} - {results[0][2]}", "info")
        else:
            messagebox.showwarning(
                "Requests", results[0][2] if results else "Unable to process.",
                parent=self)
        self.render()

    # METHOD: find_student(self)
    # Logic: looks up the typed student number for the Return / Renew tabs.
    def find_student(self):
        username = self.id_entry.get().strip()
        user = self.db.one("SELECT * FROM users WHERE username=? AND role="
                           "'student'", (username,))
        if not user:
            messagebox.showwarning("Circulation",
                                   "No student record matches that number.",
                                   parent=self)
            self.borrower = None
        else:
            self.borrower = user
        self.render()

    # METHOD: return_view(self, main, side)
    # Logic: accession entry + the selected borrower's active loans.
    def return_view(self, main, side):
        step = card(main, pad=0)
        step.pack(fill="x")
        section_title(step.inner, "1. Scan the accession",
                      sub="Enter the barcode of the book being returned")
        row = tk.Frame(step.inner, bg=WHITE)
        row.pack(fill="x", pady=(14, 0))
        self.ret_entry = entry(row)
        self.ret_entry.pack(side="left", fill="x", expand=True, ipady=4)
        placeholder(self.ret_entry, "PDM-")
        button(row, "Process return", self.do_return, "primary").pack(
            side="left", padx=(12, 0))
        self.ret_entry.bind("<Return>", lambda e: self.do_return())

        result = card(main, pad=0)
        result.pack(fill="x", pady=(16, 0))
        section_title(result.inner, "Return status",
                      sub="Reservations are advanced automatically on return")
        if getattr(self, "last_return", None):
            ok, msg = self.last_return
            pill(result.inner, "Completed" if ok else "Check again",
                 "completed" if ok else "checked out").pack(anchor="w",
                                                            pady=(12, 6))
            tk.Label(result.inner, text=msg, bg=WHITE, fg=INK, font=(BODY, 10),
                     anchor="w").pack(anchor="w")
        else:
            tk.Label(result.inner, text="No return processed in this session.",
                     bg=WHITE, fg=MUTED, font=(BODY, 10), anchor="w").pack(
                anchor="w", pady=(12, 0))

        panel = card(main, pad=0)
        panel.pack(fill="x", pady=(16, 0))
        section_title(panel.inner, "Today's returns")
        rows = self.db.all(
            "SELECT t.ts, c.accession, b.title, t.status FROM transactions t "
            "JOIN copies c ON c.id=t.copy_id JOIN books b ON b.id=c.book_id "
            "WHERE t.type='Return' ORDER BY t.ts DESC LIMIT 6")
        if rows:
            tv = tree(panel.inner, ["TIME", "ACCESSION", "BOOK", "STATUS"],
                      [80, 120, 300, 130], height=len(rows))
            for r in rows:
                tv.insert("", "end", values=(tx_time(r["ts"]), r["accession"],
                                             r["title"], r["status"]))
            tv.pack(fill="x", pady=(12, 0))
        else:
            tk.Label(panel.inner, text="No returns yet today.", bg=WHITE,
                     fg=MUTED, font=(BODY, 9)).pack(anchor="w", pady=14)

        side1 = card(side, pad=0)
        side1.pack(fill="x")
        tk.Label(side1.inner, text="Hold queue", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=16, weight="bold")).pack(
            anchor="w", pady=(0, 10))
        holds = self.db.all(
            "SELECT r.*, b.title, u.name FROM reservations r "
            "JOIN books b ON b.id=r.book_id JOIN users u ON u.id=r.user_id "
            "WHERE r.status='waiting' ORDER BY r.position LIMIT 6")
        if not holds:
            tk.Label(side1.inner, text="No one is waiting right now.", bg=WHITE,
                     fg=MUTED, font=(BODY, 9)).pack(anchor="w")
        for h in holds:
            line = tk.Frame(side1.inner, bg=CREAM)
            line.pack(fill="x", pady=4)
            tk.Label(line, text=f"#{h['position']}", bg=MAROON_SOFT, fg=MAROON,
                     font=(BODY, 9, "bold"), padx=8, pady=6).pack(side="left",
                                                                  padx=(0, 8))
            txt = tk.Frame(line, bg=CREAM)
            txt.pack(side="left", fill="x", expand=True, pady=6)
            tk.Label(txt, text=h["title"], bg=CREAM, fg=INK, font=(BODY, 9,
                     "bold"), anchor="w", wraplength=220, justify="left").pack(
                anchor="w")
            tk.Label(txt, text=h["name"], bg=CREAM, fg=MUTED,
                     font=(BODY, 8), anchor="w").pack(anchor="w")

    # METHOD: do_return(self)
    # Logic: confirms the return with the book and borrower details first,
    #        then returns the typed accession via return_book(), which advances
    #        the queue; declining writes nothing and keeps the typed accession.
    def do_return(self):
        accession = self.ret_entry.get().strip()
        if not accession or accession == "PDM-":
            return
        copy = copy_of(self.db, accession)
        lines = [copy["title"], accession] if copy else [accession]
        loan = active_loan(self.db, copy["id"]) if copy else None
        if loan:
            borrower = user_by_id(self.db, loan["user_id"])
            if borrower:
                lines.append(f"Borrowed by {borrower['name']} "
                             f"({borrower['username']})")
        if not messagebox.askyesno(
                "Process return",
                "Return this book?\n\n" + "\n".join(lines),
                parent=self):
            return
        ok, msg = return_book(self.db, accession, self.staff)
        self.last_return = (ok, msg)
        detail = f"{copy['title']} - {msg}" if copy else msg
        if ok:
            Toast(self.shell.app, "Return processed", detail, "info")
        else:
            messagebox.showwarning("Return", detail, parent=self)
        self.render()

    # METHOD: renew_view(self, main, side)
    # Logic: the selected borrower's active loans with a Renew button each; see B3.
    def renew_view(self, main, side):
        step = card(main, pad=0)
        step.pack(fill="x")
        section_title(step.inner, "1. Identify borrower",
                      sub="Enter a student number to list active loans")
        row = tk.Frame(step.inner, bg=WHITE)
        row.pack(fill="x", pady=(14, 0))
        self.id_entry = entry(row)
        self.id_entry.pack(side="left", fill="x", expand=True, ipady=4)
        if self.borrower:
            self.id_entry.insert(0, self.borrower["username"])
        button(row, "Find student", self.find_student, "primary").pack(
            side="left", padx=(12, 0))
        self.id_entry.bind("<Return>", lambda e: self.find_student())

        panel = card(main, pad=0)
        panel.pack(fill="x", pady=(16, 0))
        if not self.borrower:
            section_title(panel.inner, "Active loans",
                          sub="No borrower selected yet")
            tk.Label(panel.inner, text="Find a student to see their loans.",
                     bg=WHITE, fg=MUTED, font=(BODY, 10)).pack(anchor="w",
                                                               pady=16)
        else:
            loans = my_loans(self.db, self.borrower["id"])
            section_title(panel.inner,
                          f"Active loans for {self.borrower['name']}",
                          sub=f"{len(loans)} item(s) on loan")
            if not loans:
                tk.Label(panel.inner, text="Nothing on loan.", bg=WHITE,
                         fg=MUTED, font=(BODY, 10)).pack(anchor="w", pady=16)
            for loan in loans:
                line = tk.Frame(panel.inner, bg=WHITE, highlightthickness=1,
                                highlightbackground=LINE)
                line.pack(fill="x", pady=(10, 0))
                body = tk.Frame(line, bg=WHITE)
                body.pack(fill="x", padx=14, pady=10)
                tk.Label(body, text=loan["title"], bg=WHITE, fg=INK,
                         font=(BODY, 10, "bold"), anchor="w").pack(side="left")
                status, tag = loan_status_row(loan)
                pill(body, status, tag).pack(side="right")
                tk.Label(body, text=f"Due {fmt_date(loan['due_date'])}",
                         bg=WHITE, fg=MUTED, font=(BODY, 9)).pack(
                    side="right", padx=14)
                button(body, "Renew",
                       lambda i=loan["id"]: self.do_renew(i), "ghost").pack(
                    side="right")
        side1 = card(side, pad=0)
        side1.pack(fill="x")
        self.borrower_panel(side1.inner)

    # METHOD: do_renew(self, loan_id)
    # Logic: renews one loan via renew_loan() as the desk; see B3.3.
    def do_renew(self, loan_id):
        ok, msg = renew_loan(self.db, loan_id, self.staff)
        if ok:
            Toast(self.shell.app, "Loan renewed", msg, "info")
        else:
            messagebox.showinfo("Renew", msg, parent=self)
        self.render()

    # Small type plus h-scroll keeps long names and programs readable.
    # METHOD: recent(self, main)
    # Logic: newest circulation events; spotlight() makes each row click-to-
    # highlight so staff can track one record. Rebuilt on every render(), so
    # the mark starts fresh each time the desk switches tab.
    def recent(self, main):
        panel = card(main, pad=0)
        panel.pack(fill="x", pady=(16, 0))
        section_title(panel.inner, "Recent transactions",
                      sub="Latest circulation events at this desk")
        rows = recent_transactions(self.db, 8)
        holder = tk.Frame(panel.inner, bg=WHITE)
        holder.pack(fill="x", pady=(12, 0))
        tv = tree(holder, ["TIME", "STUDENT", "NAME", "PROGRAM", "SECTION",
                           "ITEM", "TYPE", "PROCESSED BY", "STATUS"],
                  [60, 70, 126, 188, 66, 78, 62, 110, 90],
                  height=len(rows) or 1, style="PDM.Spot.SmallTreeview")
        for r in rows:
            tv.insert("", "end", values=(
                tx_time(r["ts"]), r["username"] or "-", r["name"] or "-",
                r["program"] or "-", r["section"] or "-",
                r["accession"] or "-", r["type"], r["staff"] or "-",
                r["status"]))
        spotlight(tv)   # click a row to highlight it — visual bookmark only
        hsb = ttk.Scrollbar(holder, orient="horizontal", command=tv.xview)
        hsb.pack(side="bottom", fill="x")
        tv.configure(xscrollcommand=hsb.set)
        tv.pack(fill="x")
        tk.Label(holder, text="Every event is written to the transaction log "
                 "and drives the admin dashboard.", bg=WHITE, fg=MUTED,
                 font=(BODY, 9)).pack(anchor="w", pady=(10, 0))


# TransactionsScreen — filterable audit log (checkout / return / renewal); see B.4.
# =====================================================================
# CLASS: TransactionsScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "transactions"   (staff role)
# Inherits: tk.Frame
# Purpose: Read-only audit log of every circulation event with a type filter
#          (All / Checkout / Return / Renewal) and a Refresh button.
# Logic:   load() -> recent_transactions() (reads D6 `transactions`, up to 300
    #          rows); uses the compact PDM.Spot.SmallTreeview style + h-scrollbar.
#          spotlight() makes each row click-to-highlight (visual bookmark only —
#          it runs no action and writes nothing; a Refresh clears the mark).
# =====================================================================
class TransactionsScreen(tk.Frame):
    # METHOD: __init__(self, shell)
    # Logic: Constructor — builds the type filter and the log Treeview, then load().
    def __init__(self, shell):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.kind = tk.StringVar(value="All")
        self.pack(fill="both", expand=True)
        bar = tk.Frame(self, bg=WHITE, highlightthickness=1,
                       highlightbackground=LINE)
        bar.pack(fill="x")
        inner = tk.Frame(bar, bg=WHITE)
        inner.pack(fill="x", padx=18, pady=14)
        tk.Label(inner, text="Show", bg=WHITE, fg=MUTED, font=(BODY, 10)).pack(
            side="left")
        cb = ttk.Combobox(inner, textvariable=self.kind, width=14,
                          state="readonly",
                          values=["All", "Checkout", "Return", "Renewal"])
        cb.pack(side="left", padx=10)
        cb.bind("<<ComboboxSelected>>", lambda e: self.after(1, self.load))
        button(inner, "Refresh", self.load, "ghost").pack(side="right")

        panel = card(self, pad=0)
        panel.pack(fill="both", expand=True, pady=(16, 0))
        section_title(panel.inner, "Transaction log",
                      sub="Checkout, return and renewal events with the "
                          "processing librarian")
        holder = tk.Frame(panel.inner, bg=WHITE)
        holder.pack(fill="both", expand=True, pady=(14, 0))
        body = tk.Frame(holder, bg=WHITE)
        self.tv = tree(body, ["TIME", "STUDENT", "NAME", "PROGRAM",
                               "SECTION", "ITEM", "BOOK NAME", "TYPE",
                               "PROCESSED BY", "STATUS", "NOTE"],
                        [60, 70, 126, 188, 66, 78, 330, 62, 110, 90, 170],
                        height=14, style="PDM.Spot.SmallTreeview")
        spotlight(self.tv)   # click a row to highlight it — visual bookmark only
        hsb = ttk.Scrollbar(holder, orient="horizontal",
                            command=self.tv.xview)
        hsb.pack(side="bottom", fill="x")
        self.tv.configure(xscrollcommand=hsb.set)
        sb = attach_scroll(self.tv, body)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        body.pack(side="left", fill="both", expand=True)
        self.load()

    # METHOD: load(self)
    # Logic: redraws the log for the chosen type filter.
    def load(self):
        self.tv.delete(*self.tv.get_children())
        rows = recent_transactions(self.db, 300)
        kind = self.kind.get()
        for r in rows:
            if kind != "All" and r["type"] != kind:
                continue
            self.tv.insert("", "end", values=(
                tx_time(r["ts"]), r["username"] or "-", r["name"] or "-",
                r["program"] or "-", r["section"] or "-",
                r["accession"] or "-", r["title"] or "-", r["type"],
                r["staff"] or "-", r["status"], r["note"] or ""))
# DashboardScreen — KPIs, circulation chart, escalation buckets, system feed, report export; see C.1.
# =====================================================================
# CLASS: DashboardScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "dashboard"   (admin role) — Logic P6
# Inherits: tk.Frame
# Purpose: Library administration overview — five KPI stat cards, the weekly
#          circulation bar chart, the overdue & SDO escalation buckets, the
#          latest system-wide Notifications feed, and the Export report button.
# Logic:   dashboard_stats() for KPIs, weekly_activity() for the chart,
    #          escalation_buckets() for the escalation card, export() writes
#          library_report.txt to the app folder.
# Objects: built by Shell.navigate("dashboard"); Toast after export.
# =====================================================================
class DashboardScreen(tk.Frame):
    # METHOD: __init__(self, shell)
    # Logic: Constructor — KPI row, weekly chart canvas, escalation buckets and
    # the Notifications feed; also registers Export report in the header.
    def __init__(self, shell):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.pack(fill="both", expand=True)

        export = button(shell.head_actions, "Export report", self.export,
                        "ghost", icon="⇩")
        shell.set_header_actions(export)

        scroll = ScrollFrame(self, bg=CREAM)
        scroll.pack(fill="both", expand=True)
        host = scroll.body

        stats = dashboard_stats(self.db)
        cards = tk.Frame(host, bg=CREAM)
        cards.pack(fill="x")
        stat_card(cards, "Total books", f"{stats['total']:,}",
                  f"+{stats['titles']} titles", "▤")
        stat_card(cards, "Available", f"{stats['available']:,}",
                  f"{stats['available'] * 100 // max(stats['total'], 1)}%",
                  "✓", GREEN_FG)
        stat_card(cards, "Active borrows", f"{stats['active']:,}",
                  "on loan", "▥", MAROON)
        stat_card(cards, "Reservations", f"{stats['reservations']:,}",
                  f"{stats['ready']} ready", "⚑", AMBER_FG)
        stat_card(cards, "Overdue alerts", f"{stats['overdue']:,}",
                  f"{stats['escalated']} escalated", "!", RED_FG)

        row = tk.Frame(host, bg=CREAM)
        row.pack(fill="x", pady=(16, 0))
        left = tk.Frame(row, bg=CREAM)
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))
        right = tk.Frame(row, bg=CREAM)
        right.pack(side="right", fill="both", expand=True)

        chart_card = card(left, pad=0)
        chart_card.pack(fill="both", expand=True)
        tk.Label(chart_card.inner, text="Weekly circulation", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=17, weight="bold"),
                 anchor="w").pack(anchor="w")
        tk.Label(chart_card.inner, text="Loans and returns for the last 7 days",
                 bg=WHITE, fg=MUTED, font=(BODY, 10), anchor="w").pack(
            anchor="w", pady=(2, 12))
        labels, counts = weekly_activity(self.db)
        cv = tk.Canvas(chart_card.inner, height=210, bg=WHITE,
                       highlightthickness=0, bd=0)
        cv.pack(fill="x")
        cv.bind("<Configure>", lambda e: self.draw_chart(cv, labels, counts))
        total_tx = sum(counts)
        tk.Label(chart_card.inner, text=f"{total_tx} transactions recorded",
                 bg=WHITE, fg=INK, font=(BODY, 10, "bold"), anchor="w").pack(
            anchor="w", pady=(6, 0))

        esc = escalation_buckets(self.db)
        esc_card = card(left, pad=0)
        esc_card.pack(fill="x", pady=(16, 0))
        tk.Label(esc_card.inner, text="Overdue & SDO escalation", bg=WHITE,
                 fg=INK, font=tkfont.Font(family=HEAD, size=17, weight="bold"),
                 anchor="w").pack(anchor="w")
        tk.Label(esc_card.inner, text="Cases requiring follow-up", bg=WHITE,
                 fg=MUTED, font=(BODY, 10), anchor="w").pack(anchor="w",
                                                             pady=(2, 12))
        buckets = (
            ("1 day overdue", "Final warning", esc["warn"], AMBER_BG,
             AMBER_FG),
            ("2+ days overdue", "Restricted + SDO", esc["escalated"], RED_BG,
             RED_FG),
            ("SDO pending review", "Awaiting acknowledgment", esc["pending"],
             RED_BG, RED_FG),
            ("SDO acknowledged", "Under student affairs", esc["acknowledged"],
             BLUE_BG, BLUE_FG))
        for title, note, value, bg, fg in buckets:
            line = tk.Frame(esc_card.inner, bg=bg, highlightthickness=1,
                            highlightbackground=bg)
            line.pack(fill="x", pady=5)
            tk.Label(line, text="✉", bg=bg, fg=fg, font=(BODY, 11),
                     padx=12, pady=10).pack(side="left")
            txt = tk.Frame(line, bg=bg)
            txt.pack(side="left", fill="both", expand=True, pady=8)
            tk.Label(txt, text=title, bg=bg, fg=fg, font=(BODY, 10, "bold"),
                     anchor="w").pack(anchor="w")
            tk.Label(txt, text=note, bg=bg, fg=fg, font=(BODY, 8)).pack(
                anchor="w")
            tk.Label(line, text=str(value), bg=bg, fg=fg,
                     font=tkfont.Font(family=HEAD, size=20, weight="bold"),
                     padx=18).pack(side="right")

        notes = card(right, pad=0)
        notes.pack(fill="both", expand=True)
        tk.Label(notes.inner, text="Notifications", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=17, weight="bold"),
                 anchor="w").pack(anchor="w")
        tk.Label(notes.inner, text="System and operations", bg=WHITE, fg=MUTED,
                 font=(BODY, 10), anchor="w").pack(anchor="w", pady=(2, 12))
        for n in self.db.all("SELECT * FROM notifications WHERE user_id IS "
                             "NULL ORDER BY ts DESC LIMIT 7"):
            line = tk.Frame(notes.inner, bg=WHITE)
            line.pack(fill="x", pady=7)
            colour = {"warn": AMBER_FG, "error": RED_FG}.get(n["level"],
                                                             GREEN_FG)
            tk.Label(line, text="●", bg=WHITE, fg=colour, font=(BODY, 9)).pack(
                side="left", padx=(0, 8), pady=2)
            txt = tk.Frame(line, bg=WHITE)
            txt.pack(side="left", fill="x", expand=True)
            tk.Label(txt, text=n["title"], bg=WHITE, fg=INK,
                     font=(BODY, 10, "bold"), anchor="w").pack(anchor="w")
            tk.Label(txt, text=n["body"], bg=WHITE, fg=MUTED, font=(BODY, 9),
                     wraplength=330, justify="left", anchor="w").pack(anchor="w")
        tk.Label(notes.inner, text=f"●  All services operational    "
                 f"{dt.datetime.now().strftime('%I:%M %p').lstrip('0')}",
                 bg=WHITE, fg=GREEN_FG, font=(BODY, 9, "bold"), anchor="w").pack(
            anchor="w", pady=(14, 0))

        inv = card(host, pad=0)
        inv.pack(fill="x", pady=(16, 0))
        inv_hdr = section_title(inv.inner, "Inventory overview",
                                sub="Live copy availability and shelf location")
        actions = tk.Frame(inv_hdr, bg=WHITE)
        actions.pack(side="right", pady=4)
        button(actions, "Full inventory",
               lambda: shell.navigate("inventory"), "ghost").pack(side="left")
        holder = tk.Frame(inv.inner, bg=WHITE)
        holder.pack(fill="x", pady=(14, 0))
        tv = tree(holder, ["ACCESSION", "TITLE", "CATEGORY", "SHELF",
                           "COPIES", "STATUS"],
                  [120, 330, 150, 80, 90, 130], height=6)
        for row in self.db.all(SELECT_BOOK + " ORDER BY b.id LIMIT 6"):
            tv.insert("", "end", values=(
                acc(row["id"], 0), row["title"], row["category"],
                self.shelf_of(row["id"]),
                f"{row['avail']} / {row['total']}",
                "●  " + book_status(row)))
        tv.pack(fill="x")
        tk.Label(holder, text=f"Showing 6 of {stats['titles']} catalog records",
                 bg=WHITE, fg=MUTED, font=(BODY, 9)).pack(anchor="w",
                                                          pady=(10, 0))

    # METHOD: shelf_of(self, book_id)
    # Logic: first shelf code found for a title, "-" when unknown.
    def shelf_of(self, book_id):
        row = self.db.one("SELECT shelf FROM copies WHERE book_id=? LIMIT 1",
                          (book_id,))
        return row[0] if row else "-"

    # METHOD: draw_chart(self, cv, labels, counts)
    # Logic: paints the weekly circulation bars.
    def draw_chart(self, cv, labels, counts):
        cv.delete("all")
        w = cv.winfo_width() or 600
        h = cv.winfo_height() or 210
        base = h - 28
        peak = max(counts + [1])
        slot = w / len(counts)
        for i, (label, count) in enumerate(zip(labels, counts)):
            bar_h = max(10, (base - 40) * count / peak)
            x1 = i * slot + slot * 0.30
            x2 = i * slot + slot * 0.70
            colour = GOLD if count == peak else MAROON
            radius = max(2, min(7, (x2 - x1) / 2, bar_h / 2))
            rounded_rect(cv, x1, base - bar_h, x2, base, radius, colour,
                         colour)
            cv.create_text((x1 + x2) / 2, base - bar_h - 12, text=str(count),
                           fill=MUTED, font=tkfont.Font(family=BODY, size=9,
                                                        weight="bold"))
            cv.create_text((x1 + x2) / 2, base + 16, text=label, fill=MUTED,
                           font=(BODY, 9))

    # METHOD: export(self)
    # Logic: writes library_report.txt (stats + inventory) and confirms the path.
    def export(self):
        path = os.path.join(BASE_DIR, "library_report.txt")
        stats = dashboard_stats(self.db)
        lines = [f"{APP_NAME} - Operational report",
                 f"Generated: {fmt_long(today())}", "",
                 f"Total copies: {stats['total']}",
                 f"Available: {stats['available']}",
                 f"Active borrows: {stats['active']}",
                 f"Reservations: {stats['reservations']}",
                 f"Overdue alerts: {stats['overdue']}",
                 f"SDO pending: {stats['escalated']}", "", "Inventory:"]
        for row in self.db.all(SELECT_BOOK + " ORDER BY b.id"):
            lines.append(f"  {acc(row['id'], 0)}  {row['title']}  "
                         f"{row['avail']}/{row['total']}  {book_status(row)}")
        # SDO escalation register — the paper trail for the Student
        # Disciplinary Office, including how each case was closed.
        lines += ["", "SDO cases:"]
        cases = self.db.all(
            "SELECT s.*, u.username, u.name, b.title, l.due_date "
            "FROM sdo_cases s JOIN users u ON u.id=s.user_id "
            "JOIN loans l ON l.id=s.loan_id JOIN copies c ON c.id=l.copy_id "
            "JOIN books b ON b.id=c.book_id "
            "ORDER BY CASE s.status WHEN 'pending' THEN 0 ELSE 1 END, s.id DESC")
        if not cases:
            lines.append("  (none on record)")
        for s in cases:
            late = max(-days_until(s["due_date"]), 0)
            if s["status"] == "pending":
                state = "Pending"
            else:
                state = (f"Acknowledged {fmt_date(s['resolved_at'])}")
                if s["closed_by"] == "return":
                    state += " on return"
                elif s["closed_by"] == "sdo":
                    state += " after SDO compliance"
            lines.append(f"  SDO-{s['id']:03d}  {s['name']} ({s['username']})"
                         f"  {s['title']}  due {fmt_date(s['due_date'])}"
                         f"  {late} day(s) overdue  {state}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        messagebox.showinfo("Export report", f"Report saved to:\n{path}",
                            parent=self)


# InventoryScreen — searchable catalog table with shelf, copies and the add-book form; see C.2.
# =====================================================================
# CLASS: InventoryScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "inventory"   (admin role) — Logic P6
# Inherits: tk.Frame
# Purpose: Live copy-level inventory — ACCESSION / TITLE / AUTHOR / CATEGORY /
#          SHELF / COPIES / STATUS with a search box, category filter and a
#          "+ Add book" dialog that writes a books row + n copies rows.
# Logic:   load() for the filtered table; add_book() validates the form,
    #          generates PDM-xxxxxx accessions and notifies the desk.
# Objects: built by Shell.navigate("inventory"); ScrollFrame inside the dialog;
#          Toast after a successful save.
# =====================================================================
class InventoryScreen(tk.Frame):
    # METHOD: __init__(self, shell)
    # Logic: Constructor — search box, category dropdown, counter line and table.
    def __init__(self, shell):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.query = tk.StringVar()
        self.category = tk.StringVar(value="All categories")
        self.pack(fill="both", expand=True)

        bar = tk.Frame(self, bg=WHITE, highlightthickness=1,
                       highlightbackground=LINE)
        bar.pack(fill="x")
        inner = tk.Frame(bar, bg=WHITE)
        inner.pack(fill="x", padx=18, pady=14)
        search = tk.Frame(inner, bg=WHITE, highlightthickness=1,
                          highlightbackground=LINE)
        search.pack(side="left", fill="x", expand=True)
        tk.Label(search, text="⌕", bg=WHITE, fg=MUTED, font=(BODY, 11)).pack(
            side="left", padx=(10, 4))
        e = entry(search)
        e.pack(side="left", fill="x", expand=True, ipady=3)
        e.bind("<KeyRelease>", lambda ev: self.after(1, self.load))
        cats = ["All categories"] + sorted({
            r["category"] for r in self.db.all("SELECT DISTINCT category FROM "
                                               "books")})
        cb = ttk.Combobox(inner, textvariable=self.category, width=18,
                          state="readonly", values=cats)
        cb.pack(side="left", padx=12)
        cb.bind("<<ComboboxSelected>>", lambda ev: self.after(1, self.load))
        button(inner, "Add book", self.add_book, "primary", icon="+").pack(
            side="left")

        panel = card(self, pad=0)
        panel.pack(fill="both", expand=True, pady=(16, 0))
        section_title(panel.inner, "All catalog records",
                      sub="Search by accession, title or category")
        holder = tk.Frame(panel.inner, bg=WHITE)
        holder.pack(fill="both", expand=True, pady=(14, 0))
        self.tv = tree(holder, ["ACCESSION", "TITLE", "AUTHOR", "CATEGORY",
                                "SHELF", "COPIES", "STATUS"],
                       [115, 270, 180, 135, 75, 75, 125], height=16)
        sb = attach_scroll(self.tv, holder)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.count_lbl = tk.Label(panel.inner, text="", bg=WHITE, fg=MUTED,
                                  font=(BODY, 9))
        self.count_lbl.pack(anchor="w", pady=(10, 0))
        self.load()

    # METHOD: load(self)
    # Logic: redraws the table for the current search text and category.
    def load(self):
        self.tv.delete(*self.tv.get_children())
        q = self.query.get().lower().strip()
        cat = self.category.get()
        rows = self.db.all(SELECT_BOOK + " ORDER BY b.id")
        shown = 0
        for row in rows:
            hay = f"{acc(row['id'], 0)} {row['title']} {row['author']}".lower()
            if q and q not in hay:
                continue
            if cat != "All categories" and row["category"] != cat:
                continue
            self.tv.insert("", "end", values=(
                acc(row["id"], 0), row["title"], row["author"],
                row["category"], self.shelf_of(row["id"]),
                f"{row['avail']} / {row['total']}",
                "●  " + book_status(row)))
            shown += 1
        self.count_lbl.configure(
            text=f"Showing {shown} of {len(rows)} catalog records  •  "
                 f"Last inventory sync {dt.datetime.now().strftime('%I:%M %p')}"
                 .lstrip("0"))

    # METHOD: shelf_of(self, book_id)
    # Logic: first shelf code found for a title, "-" when unknown.
    def shelf_of(self, book_id):
        row = self.db.one("SELECT shelf FROM copies WHERE book_id=? LIMIT 1",
                          (book_id,))
        return row[0] if row else "-"

    # METHOD: add_book(self)
    # Logic: opens the add-to-catalog dialog; see C2.3–C2.5.
    def add_book(self):
        win = tk.Toplevel(self)
        win.title("Add book")
        win.configure(bg=WHITE)
        win.geometry("480x680")
        win.minsize(420, 480)
        win.transient(self.winfo_toplevel())

        # ScrollFrame keeps all ten fields, the copies box and Save reachable on
        # short screens; a plain pack pushed Save to catalog off the bottom.
        scroll = ScrollFrame(win, bg=WHITE)
        scroll.pack(fill="both", expand=True)
        form = tk.Frame(scroll.body, bg=WHITE)
        form.pack(fill="x", padx=26, pady=22)
        tk.Label(form, text="Add to the catalog", bg=WHITE, fg=INK,
                 font=tkfont.Font(family=HEAD, size=18, weight="bold")).pack(
            anchor="w", pady=(0, 16))
        entries = {}
        for key, label in (("title", "Title"), ("author", "Author"),
                           ("subject", "Subject"), ("category", "Category"),
                           ("publisher", "Publisher"), ("edition", "Edition"),
                           ("year", "Publication year"), ("isbn", "ISBN"),
                           ("call_no", "Call number"),
                           ("shelf", "Shelf (e.g. QA-14)")):
            tk.Label(form, text=label, bg=WHITE, fg=INK, font=(BODY, 9,
                     "bold")).pack(anchor="w")
            box = tk.Frame(form, bg=WHITE, highlightthickness=1,
                           highlightbackground=LINE)
            box.pack(fill="x", pady=(4, 10))
            ent = entry(box)
            ent.pack(fill="x", ipady=3)
            entries[key] = ent
        copies_var = tk.StringVar(value="1")
        tk.Label(form, text="Number of copies", bg=WHITE, fg=INK,
                 font=(BODY, 9, "bold")).pack(anchor="w")
        tk.Entry(form, textvariable=copies_var, bg=WHITE, fg=INK,
                 relief="flat", highlightthickness=1, highlightbackground=LINE,
                 font=(BODY, 11), bd=6).pack(fill="x", pady=(4, 16))

        # the canvas must request the form's full width or the fields squeeze;
        # the idle pass makes winfo_reqwidth() current
        win.update_idletasks()
        scroll.canvas.configure(width=form.winfo_reqwidth() + 52)

        # validates the dialog and inserts the book row plus its copies.
        def save():
            title = entries["title"].get().strip()
            if not title:
                messagebox.showwarning("Add book", "A title is required.",
                                       parent=win)
                return
            year = entries["year"].get().strip()
            book_id = self.db.run(
                "INSERT INTO books(title,author,subject,category,publisher,"
                "edition,year,isbn,call_no,material_type,description) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (title, entries["author"].get().strip() or "Unknown",
                 entries["subject"].get().strip() or "General",
                 entries["category"].get().strip() or "General",
                 entries["publisher"].get().strip(),
                 entries["edition"].get().strip(),
                 int(year) if year.isdigit() else None,
                 entries["isbn"].get().strip(),
                 entries["call_no"].get().strip() or "-",
                 "Book", "Added through the administration inventory."))
            count = max(1, int(copies_var.get() or "1")
                        if copies_var.get().strip().isdigit() else 1)
            shelf = entries["shelf"].get().strip() or "STK-01"
            for i in range(count):
                self.db.run("INSERT INTO copies(book_id,accession,shelf,status) "
                            "VALUES(?,?,?,?)",
                            (book_id, f"PDM-{1000 + book_id * 40 + i:06d}",
                             shelf, "available"))
            Toast(self.shell.app, "Catalog updated",
                  f"{title} added with {count} copy(s).", "info")
            win.destroy()
            self.load()

        button(form, "Save to catalog", save, "primary").pack(fill="x")


# UsersScreen — account table with double-click block / reinstate; see C.3.
# =====================================================================
# CLASS: UsersScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "users"   (admin role) — Logic P6
# Inherits: tk.Frame
# Purpose: All accounts (students / staff / admins) with ON LOAN, OVERDUE and
#          Active / Blocked status. Double-clicking a row BLOCKS or REINSTATES
#          the account — the only way to lift an escalation block.
# Logic:   toggle_status() flips users.status; refuses on administrators;
    #          eligibility() re-reads this status, so a block stops borrowing.
# Objects: built by Shell.navigate("users").
# =====================================================================
class UsersScreen(tk.Frame):
    # METHOD: __init__(self, shell)
    # Logic: Constructor — builds the users Treeview with the double-click binding.
    def __init__(self, shell):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.pack(fill="both", expand=True)
        panel = card(self, pad=0)
        panel.pack(fill="both", expand=True)
        section_title(panel.inner, "Library users",
                      sub="Students and staff with their current borrowing "
                          "standing")
        holder = tk.Frame(panel.inner, bg=WHITE)
        holder.pack(fill="both", expand=True, pady=(14, 0))
        self.tv = tree(holder, ["ID", "NAME", "ROLE", "PROGRAM", "SECTION",
                                "ON LOAN", "OVERDUE", "STATUS"],
                       [115, 200, 105, 215, 80, 90, 90, 120], height=16)
        sb = attach_scroll(self.tv, holder)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tv.bind("<Double-1>", self.toggle_status)
        hint = tk.Label(panel.inner, text="Double-click a row to block or "
                         "reinstate a student account.", bg=WHITE, fg=MUTED,
                         font=(BODY, 9))
        hint.pack(anchor="w", pady=(10, 0))
        self.load()

    # METHOD: load(self)
    # Logic: redraws the table with per-user loan / overdue counts and status pills.
    def load(self):
        self.tv.delete(*self.tv.get_children())
        for u in self.db.all("SELECT * FROM users ORDER BY role, username"):
            loans = self.db.scalar(
                "SELECT COUNT(*) FROM loans WHERE user_id=? AND status IN "
                "('active','overdue')", (u["id"],))
            overdue = self.db.scalar(
                "SELECT COUNT(*) FROM loans WHERE user_id=? AND status="
                "'overdue'", (u["id"],))
            self.tv.insert("", "end", iid=str(u["id"]), values=(
                u["username"], u["name"], u["role"].title(),
                u["program"] or "-", u["section"] or "-", loans, overdue,
                "●  " + ("Active" if u["status"] == "active" else "Blocked")))

    # METHOD: toggle_status(self, event)
    # Logic: flips the double-clicked account active ↔ blocked (admins exempt);
    #        reinstating warns when books are still sdo_after+ days overdue,
    #        because run_overdue_scan() would re-block on its next 60 s pass;
    #        see C3.2–C3.4 and §11 "Reinstate warning".
    def toggle_status(self, event):
        sel = self.tv.selection()
        if not sel:
            return
        uid = int(sel[0])
        user = user_by_id(self.db, uid)
        if user["role"] == "admin":
            messagebox.showinfo("Users", "Administrators cannot be blocked.",
                                parent=self)
            return
        new = "blocked" if user["status"] == "active" else "active"
        warn = ""
        if new == "active":
            # still escalated? the scan re-applies 'blocked' within a minute
            threshold = setting(self.db, "sdo_after", SDO_AFTER)
            deep = sum(1 for r in self.db.all(
                "SELECT due_date FROM loans WHERE user_id=? AND status IN "
                "('active','overdue')", (uid,))
                if -days_until(r["due_date"]) >= threshold)
            if deep:
                warn = (f"\n\nWarning: {deep} book(s) are still {threshold}+ "
                        f"day(s) overdue.\nThe account will be blocked again at "
                        f"the next automatic scan. Reinstate anyway?")
        if not messagebox.askyesno("Users",
                                   f"{new.title()} the account of "
                                   f"{user['name']}?{warn}", parent=self):
            return
        self.db.run("UPDATE users SET status=? WHERE id=?", (new, uid))
        self.load()


# CasesScreen — escalation counters plus the SDO register with Mark-acknowledged; see C.4.
# =====================================================================
# CLASS: CasesScreen(tk.Frame)
# Layer:   PRESENTATION — screen key "cases"   (admin role) — SDO escalation
# Inherits: tk.Frame
# Purpose: "Overdue & SDO escalation" — four counters and the escalation
#          register (student, program, title, due date, days overdue, status).
#          Pending rows carry a "Mark acknowledged" button.
# Logic:   ack() -> sdo_cases.status='acknowledged' + resolved_at=today,
    #          then announce_case_closed() writes the system-wide notice and
    #          ack_guidance() explains what still restricts the student.
# Objects: built by Shell.navigate("cases"); Toast + messagebox on ack.
#          The whole screen sits in a ScrollFrame (see __init__) so a long
#          register scrolls instead of clipping past the window bottom.
# =====================================================================
class CasesScreen(tk.Frame):
    # METHOD: __init__(self, shell)
    # Logic: Constructor — four escalation counters + the register table.
    #        Everything is built inside a ScrollFrame so a long register stays
    #        reachable on short windows instead of clipping off-screen.
    def __init__(self, shell):
        super().__init__(shell.body, bg=CREAM)
        self.shell = shell
        self.db = shell.db
        self.pack(fill="both", expand=True)

        # OBJECT ScrollFrame — scrollable host; the register can grow past the
        # window height, so the counters, rows and gold note all live in
        # scroll.body and scroll together.
        scroll = ScrollFrame(self, bg=CREAM)
        scroll.pack(fill="both", expand=True)
        host = scroll.body

        esc = escalation_buckets(self.db)
        cards = tk.Frame(host, bg=CREAM)
        cards.pack(fill="x")
        stat_card(cards, "1 day overdue", esc["warn"], "Final warning",
                  "✉", AMBER_FG)
        stat_card(cards, "2+ days overdue", esc["escalated"],
                  "Restricted + SDO", "!", RED_FG)
        stat_card(cards, "SDO pending", esc["pending"], "Awaiting review",
                  "!", RED_FG)
        stat_card(cards, "SDO acknowledged", esc["acknowledged"],
                  "Under student affairs", "✓", BLUE_FG)

        panel = card(host, pad=0)
        panel.pack(fill="both", expand=True, pady=(16, 0))
        section_title(panel.inner, "Escalation register",
                      sub="Overdue records forwarded to the Student "
                          "Disciplinary Office")
        rows = self.db.all(
            "SELECT s.*, u.username, u.name, u.program, "
            "u.status AS user_status, b.title, l.due_date, l.status, "
            "(SELECT COUNT(*) FROM loans lo WHERE lo.user_id=u.id AND "
            " lo.status='overdue') AS late_count "
            "FROM sdo_cases s JOIN users u ON u.id=s.user_id "
            "JOIN loans l ON l.id=s.loan_id JOIN copies c ON c.id=l.copy_id "
            "JOIN books b ON b.id=c.book_id ORDER BY s.status, s.id DESC")
        holder = tk.Frame(panel.inner, bg=WHITE)
        holder.pack(fill="x", pady=(14, 0))
        if not rows:
            tk.Label(holder, text="No SDO cases on record.", bg=WHITE,
                     fg=MUTED, font=(BODY, 10)).pack(anchor="w", pady=14)
            return
        for r in rows:
            late = -days_until(r["due_date"])
            bg = RED_BG if r["status"] == "pending" else BLUE_BG
            fg = RED_FG if r["status"] == "pending" else BLUE_FG
            line = tk.Frame(holder, bg=bg, highlightthickness=1,
                            highlightbackground=bg)
            line.pack(fill="x", pady=6)
            tk.Label(line, text=f"SDO-{r['id']:03d}", bg=bg, fg=fg,
                     font=tkfont.Font(family=BODY, size=10, weight="bold"),
                     padx=14, pady=12).pack(side="left")
            txt = tk.Frame(line, bg=bg)
            txt.pack(side="left", fill="both", expand=True, pady=10)
            tk.Label(txt, text=f"{r['name']}  ({r['username']})  -  "
                     f"{r['program']}", bg=bg, fg=fg, font=(BODY, 10,
                                                            "bold"),
                     anchor="w").pack(anchor="w")
            tk.Label(txt, text=f"{r['title']}  •  due {fmt_date(r['due_date'])}"
                     f"  •  {max(late, 0)} days overdue", bg=bg, fg=fg,
                     font=(BODY, 9), anchor="w").pack(anchor="w")
            right = tk.Frame(line, bg=bg)
            right.pack(side="right", padx=14)
            pill(right, "Pending" if r["status"] == "pending"
                 else "Acknowledged").pack(anchor="e", pady=(0, 6))
            if r["status"] == "pending":
                button(right, "Mark acknowledged",
                       lambda i=r["id"]: self.ack(i), "ghost").pack(anchor="e")
            else:
                # Closed on return vs. closed after SDO compliance; a NULL
                # closed_by means the row predates the column, so no qualifier.
                closed = f"Closed {fmt_date(r['resolved_at'])}"
                if r["closed_by"] == "return":
                    closed += " on return"
                elif r["closed_by"] == "sdo":
                    closed += " after SDO compliance"
                tk.Label(right, text=closed,
                         bg=bg, fg=fg, font=(BODY, 8)).pack(anchor="e")
                hint = None
                if r["late_count"]:
                    hint = (f"Still has {r['late_count']} overdue book(s) out "
                            f"- stays blocked until returned, then reinstate "
                            f"on Users.")
                elif r["user_status"] == "blocked":
                    hint = "Account still blocked - reinstate on Users."
                if hint:
                    tk.Label(txt, text=hint, bg=bg, fg=fg, font=(BODY, 9),
                             anchor="w").pack(anchor="w")

        note = tk.Frame(panel.inner, bg=GOLD_SOFT, highlightthickness=1,
                        highlightbackground="#F0E0AE")
        note.pack(fill="x", pady=(16, 0))
        tk.Label(note, text="Overdue records are escalated automatically after "
                 f"{setting(self.db, 'sdo_after', SDO_AFTER)} day(s) past the "
                 f"due date, when the account is also restricted, in place of "
                 f"financial penalties.",
                 bg=GOLD_SOFT, fg="#8A6A15", font=(BODY, 10), padx=14,
                 pady=12, anchor="w").pack(fill="x")

    # METHOD: ack(self, case_id)
    # Logic: manual close — refuses a case that is missing or already closed,
    #        otherwise sets status='acknowledged', resolved_at=today and
    #        closed_by='sdo', announces it, refreshes the bell and dialogues
    #        what still restricts; see C4.4.
    def ack(self, case_id):
        case = self.db.one("SELECT * FROM sdo_cases WHERE id=?", (case_id,))
        if not case or case["status"] != "pending":
            Toast(self.shell.app, "Case updated",
                  "That case is already acknowledged.", "info")
            self.shell.navigate("cases")
            return
        self.db.run("UPDATE sdo_cases SET status='acknowledged', resolved_at=?, "
                    "closed_by='sdo' WHERE id=? AND status='pending'",
                    (iso(today()), case_id))
        announce_case_closed(self.db, case_id, "after SDO compliance")
        self.shell.refresh_bell()
        Toast(self.shell.app, "Case updated",
              "The record is now with the Student Disciplinary Office.",
              "info")
        self.shell.navigate("cases")
        messagebox.showinfo("Case acknowledged",
                            ack_guidance(self.db, case_id), parent=self)


# =====================================================================
# OBJECT: SCREENS — the ROUTER TABLE (screen key -> screen CLASS)
# Layer:   PRESENTATION routing. Consumed by Shell.navigate(key, **ctx):
#              builder = SCREENS.get(key);  builder(self)
#          Each lambda is an OBJECT FACTORY: it CREATES a *Screen instance
#          and each one packs itself into shell.body. Adding a screen means
#          adding one entry here + its class + a NAV/TITLES entry above.
# Objects created here: CatalogScreen, DetailsScreen, LoansScreen,
#          ReservationsScreen, CirculationScreen, TransactionsScreen,
#          DashboardScreen, InventoryScreen, UsersScreen, CasesScreen
#          Search: grep -n "Screen(" library_system.py
# =====================================================================
SCREENS = {
    "catalog": lambda s: CatalogScreen(s),
    "details": lambda s: DetailsScreen(s, s.ctx["book_id"]),
    "loans": lambda s: LoansScreen(s),
    "reservations": lambda s: ReservationsScreen(s),
    "circulation": lambda s: CirculationScreen(s),
    "transactions": lambda s: TransactionsScreen(s),
    "dashboard": lambda s: DashboardScreen(s),
    "inventory": lambda s: InventoryScreen(s),
    "users": lambda s: UsersScreen(s),
    "cases": lambda s: CasesScreen(s),
}


# main() — creates the database, builds the App and enters the Tk event loop.
# PROGRAM ENTRY POINT. One App OBJECT is created; mainloop() hands control to
# Tk, which then drives every button <-> METHOD callback in this file.
def main():
    app = App()          # <== OBJECT App (the root tk.Tk window)
    app.mainloop()


if __name__ == "__main__":
    main()
# === ADMIN-END ===
