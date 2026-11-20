#!/usr/bin/env python3
"""Popup picker: choose a project with .herdr/layout.toml, then apply it.

  python3 pick.py          # TUI (plugin pane entrypoint)
  python3 pick.py --list   # print candidates, non-interactive
"""
import curses
import io
import json
import os
import sys
import tomllib
from contextlib import redirect_stdout
from pathlib import Path

import apply as A


def candidates(start):
    dirs = [d for d in [start, *start.parents] if (d / ".herdr" / "layout.toml").is_file()]
    state = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if state:
        try:
            dirs += [Path(p) for p in json.loads((Path(state) / "recent.json").read_text())]
        except (OSError, ValueError):
            pass
    try:
        dirs += sorted(c for c in start.iterdir() if (c / ".herdr" / "layout.toml").is_file())
    except OSError:
        pass
    out, seen = [], set()
    for d in dirs:
        try:
            d = d.expanduser().resolve()
        except OSError:
            continue
        if d not in seen and (d / ".herdr" / "layout.toml").is_file():
            seen.add(d)
            out.append(d)
    return out


def load(start):
    """[dir, already-applied?] for each candidate; a bad layout counts as not applied."""
    try:
        have = {w.get("label") for w in A.herdr("workspace", "list").get("workspaces", [])}
    except SystemExit:
        have = set()
    out = []
    for d in candidates(start):
        try:  # plain parse: A.read would notify the desktop once per bad file
            label = tomllib.loads((d / ".herdr" / "layout.toml").read_text()).get("workspace", {}).get("label")
        except (OSError, tomllib.TOMLDecodeError):
            label = None
        out.append([d, label in have])
    return out


def draw(scr, items, sel, msg):
    scr.erase()
    h, w = scr.getmaxyx()
    scr.addnstr(0, 0, " herdr-layout · ⏎ apply · R rebuild · r reload · q quit", w - 1, curses.A_BOLD)
    scr.addnstr(1, 0, " " + msg, w - 1)
    rows = max(h - 4, 1)
    top = max(0, min(sel - rows + 1, len(items) - rows))
    for i, (d, on) in enumerate(items[top:top + rows]):
        scr.addnstr(3 + i, 0, f" {'•' if on else ' '} {d} ", w - 1,
                    curses.A_REVERSE if top + i == sel else curses.A_NORMAL)
    if not items:
        scr.addnstr(3, 0, " no .herdr/layout.toml found here or in recent projects", w - 1)
    scr.refresh()


def run(scr, start):
    items, sel, msg = load(start), 0, ""
    while True:
        draw(scr, items, sel, msg)
        key = scr.getch()
        if key in (ord("q"), 27):
            return 0
        if key in (ord("j"), curses.KEY_DOWN):
            sel = min(sel + 1, max(len(items) - 1, 0))
        elif key in (ord("k"), curses.KEY_UP):
            sel = max(sel - 1, 0)
        elif key == ord("r"):
            items, sel, msg = load(start), 0, ""
        elif key in (10, 13, curses.KEY_ENTER, ord("R")) and items:
            d = items[sel][0]
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    A.apply(A.read(d / ".herdr" / "layout.toml"), d, False, key == ord("R"))
            except SystemExit as exc:
                buf.write(str(exc.code))
            msg = buf.getvalue().replace("\n", " | ").strip()[-140:]
            draw(scr, items, sel, msg)
            scr.getch()
            return 0


def main(argv):
    start = Path(A.caller_cwd()).resolve()
    if "--list" in argv:
        for d in candidates(start):
            print(d)
        return 0
    return curses.wrapper(run, start)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
