#!/usr/bin/env python3
"""Make the dev tab in the Herdr desktop app from the same .herdr/layout.toml.

  python3 app-space.py [--folder DIR] [--name NAME] [--agent PATH] [--dry-run]

The first pane becomes the tab's initial terminal; the rest are splits. `ratio` is
ignored (the app has none), `tab` is flattened into the dev tab, and `agent`
resolves a binary from PATH. `wait`/`env` are not supported by the app. Without
a layout: editor | shell (/ agent).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import apply as A


def do(*args, dry=False):
    cmd = ["herdr-app", "do", *args]
    if dry:
        print(" ".join(cmd))
        return {}
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = p.stdout.strip()
    if p.returncode or '"error"' in out:
        sys.exit(f"{' '.join(cmd)} -> {out or p.stderr.strip()}")
    return json.loads(out)


def tab_panes(tab_id):
    p = subprocess.run(["herdr-app", "ls"], capture_output=True, text=True, check=True)
    for space in json.loads(p.stdout)["spaces"]:
        for tab in space["tabs"]:
            if tab["id"] == tab_id:
                return [t["pane"] for t in tab["terminals"]]
    sys.exit(f"tab {tab_id} not found in herdr-app ls")


def split(tab_id, direction, pane, argv_):
    """Split and return the new pane id (diff, so terminal order doesn't matter)."""
    before = set(tab_panes(tab_id))
    do("pane.split", "--direction", direction, "--pane", pane, "--argv", json.dumps(argv_))
    new = set(tab_panes(tab_id)) - before
    return new.pop() if new else pane


def argv_for(pane, shell):
    if pane.get("command"):
        return [shell, "-lc", pane["command"]]
    if pane.get("agent"):
        return [shutil.which(pane["agent"]) or sys.exit(f"agent {pane['agent']} not found in PATH")]
    return [shell, "-l"]


def main(argv):
    opt = lambda name: argv[argv.index(name) + 1] if name in argv else None
    dry = "--dry-run" in argv
    folder = str(Path(opt("--folder") or os.getcwd()).expanduser().resolve())
    shell = os.environ.get("SHELL") or "/bin/zsh"
    path = A.find_layout(Path(folder))
    if path:
        cfg = A.read(path)
        folder = str((path.parent.parent / cfg["cwd"]).resolve())
        first, *rest = cfg["panes"]
    else:
        first, rest = {"label": "editor", "command": "vim ."}, [{"label": "shell"}]
        if opt("--agent"):
            rest.append({"label": "agent", "from": "previous", "direction": "down", "command": opt("--agent")})
    name = opt("--name") or Path(folder).name

    res = do("space.new", "--name", name, "--folder", folder, "--tab", "dev",
             "--argv", json.dumps(argv_for(first, shell)), "--focus", "false", dry=dry)
    if dry:
        for p in rest:
            print(f"# pane.split {p.get('direction', 'right')} {p.get('label', '')}")
        return 0
    ids = {"": tab_panes(res["tab"])[0]}
    ids["previous"] = ids[""]
    for p in rest:
        target = ids["previous"] if p.get("from", "root") == "previous" else ids[""]
        ids["previous"] = split(res["tab"], p.get("direction", "right"), target, argv_for(p, shell))
        print(f"pane {p.get('label') or '?'} {ids['previous']}")
    print(f"space {res['space']} tab dev: {len(rest) + 1} panes in {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
