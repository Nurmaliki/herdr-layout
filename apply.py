#!/usr/bin/env python3
"""Apply .herdr/layout.toml into a new Herdr workspace (idempotent, no shell).

  python3 apply.py [--dry-run] [--if-present] [--replace [--force]] [--cwd PATH] [--layout PATH]
  python3 apply.py --selftest
"""
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

HERDR = os.environ.get("HERDR_BIN_PATH", "herdr")
TEXT = re.compile(r"^[^\x00\r\n]{1,300}$")
NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
ENVKEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DIRS = ("right", "down")


def fail(msg):
    if os.environ.get("HERDR_ENV") == "1":
        subprocess.run([HERDR, "notification", "show", "herdr-layout", "--body", str(msg)[:180]],
                       capture_output=True)
    sys.exit(msg)


def herdr(*args):
    p = subprocess.run([HERDR, *args], capture_output=True, text=True)
    if p.returncode:
        fail(f"herdr {' '.join(args)} -> {p.returncode}: {(p.stderr or p.stdout).strip()[:400]}")
    return json.loads(p.stdout).get("result", {})


def caller_cwd():
    try:
        ctx = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON") or "{}")
        if isinstance(ctx.get("focused_pane_cwd"), str):
            return ctx["focused_pane_cwd"]
    except ValueError:
        pass
    pane = os.environ.get("HERDR_PANE_ID")
    if pane:
        try:
            return herdr("pane", "get", pane)["pane"]["cwd"]
        except (SystemExit, KeyError):
            pass
    return os.getcwd()


def record(cwd):
    state = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    if not state:
        return
    p = Path(state) / "recent.json"
    try:
        recent = json.loads(p.read_text())
    except (OSError, ValueError):
        recent = []
    recent = [cwd] + [r for r in recent if r != cwd]
    p.write_text(json.dumps(recent[:12], indent=1))


def find_layout(start):
    """Nearest .herdr/layout.toml, never above the enclosing git root."""
    for d in [start, *start.parents]:
        p = d / ".herdr" / "layout.toml"
        if p.is_file():
            return p
        if (d / ".git").exists():  # repo root (dir, or file inside a worktree)
            return None
    return None


def main_repo(start):
    """Main worktree of the repo containing start (a new worktree has no untracked layout)."""
    p = subprocess.run(["git", "-C", str(start), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                       capture_output=True, text=True)
    return Path(p.stdout.strip()).parent if p.returncode == 0 and p.stdout.strip() else None


def bad_env(env):
    return not isinstance(env, dict) or any(not ENVKEY.match(str(k)) for k in env)


def read(path):
    try:
        doc = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        fail(f"{path}: {exc}")
    ws = doc.get("workspace", {})
    cfg = {"label": str(ws.get("label", "layout")), "cwd": str(ws.get("cwd", ".")),
           "focus": bool(ws.get("focus", False)), "env": ws.get("env", {}), "panes": doc.get("pane", [])}
    if not TEXT.match(cfg["label"]):
        fail("workspace.label is invalid")
    if bad_env(cfg["env"]):
        fail('workspace.env must be a table of NAME = "value"')
    tabs = set()
    for i, pane in enumerate(cfg["panes"], 1):
        tag = f"pane #{i}"
        if not isinstance(pane, dict):
            fail(f"{tag}: must be a table")
        if pane.get("direction", "right") not in DIRS:
            fail(f"{tag}: direction must be right|down")
        first = pane.get("tab") not in tabs
        tabs.add(pane.get("tab"))
        if first and pane.get("from", "root") == "previous":
            fail(f"{tag}: from=previous needs a pane above it")
        if pane.get("from", "root") not in ("root", "previous"):
            fail(f"{tag}: from must be root|previous")
        try:
            ratio = None if pane.get("ratio") is None else float(pane["ratio"])
        except (TypeError, ValueError):
            fail(f"{tag}: ratio must be a number")
        if ratio is not None and not 0.1 <= ratio <= 0.9:
            fail(f"{tag}: ratio must be 0.1-0.9")
        try:
            wait = float(pane.get("wait") or 0)
        except (TypeError, ValueError):
            fail(f"{tag}: wait must be seconds")
        if not 0 <= wait <= 30:
            fail(f"{tag}: wait must be 0-30s")
        if pane.get("command") and pane.get("agent"):
            fail(f"{tag}: use command or agent, not both")
        for key in ("label", "command", "prompt", "agent"):
            if key in pane and not TEXT.match(str(pane[key])):
                fail(f"{tag}: {key} is invalid")
        for key in ("label", "tab"):
            if pane.get(key) and not NAME.match(str(pane[key])):
                fail(f"{tag}: {key} must match [a-z][a-z0-9_-]{{0,31}}")
        if bad_env(pane.get("env", {})):
            fail(f'{tag}: env must be a table of NAME = "value"')
    return cfg


def plan(cfg, cwd):
    """Pure: (kind, argv, tab) with {ws}/{root}/{pane} resolved at apply time.

    {root} is the root pane of the step's tab, {pane} the last pane split in it.
    """
    root = ["workspace", "create", "--label", cfg["label"], "--cwd", cwd,
            "--focus" if cfg.get("focus") else "--no-focus"]
    for k, v in sorted(cfg.get("env", {}).items()):
        root += ["--env", f"{k}={v}"]
    steps = [("workspace", root, None)]
    tabs = set()
    for i, pane in enumerate(cfg["panes"], 1):
        tab = pane.get("tab")
        if tab and tab not in tabs:
            tabs.add(tab)
            steps.append(("tab", ["tab", "create", "--workspace", "{ws}", "--label", tab,
                                  "--cwd", cwd, "--no-focus"], tab))
        target = "{pane}" if pane.get("from", "root") == "previous" else "{root}"
        argv = ["pane", "split", "--pane", target, "--direction", pane.get("direction", "right"),
                "--cwd", cwd, "--no-focus"]
        if pane.get("ratio") is not None:
            argv += ["--ratio", str(float(pane["ratio"]))]
        for k, v in sorted(pane.get("env", {}).items()):
            argv += ["--env", f"{k}={v}"]
        steps.append(("split", argv, tab))
        if pane.get("wait"):
            steps.append(("wait", [str(pane["wait"])], tab))
        if pane.get("label"):
            steps.append(("rename", ["pane", "rename", "{pane}", pane["label"]], tab))
        if pane.get("command"):
            steps.append(("run", ["pane", "run", "{pane}", pane["command"]], tab))
        if pane.get("agent"):
            name = pane["label"] if pane.get("label") else f"pane{i}"
            steps.append(("agent", ["agent", "start", name, "--kind", pane["agent"], "--pane", "{pane}"], tab))
            if pane.get("prompt"):
                steps.append(("prompt", ["agent", "prompt", name, pane["prompt"]], tab))
    return steps


def fill(argv, ctx):
    """Substitute placeholder args only; commands may legitimately contain braces."""
    return [ctx.get(a, a) for a in argv]


def busy_agents(wsid):
    """Panes in this workspace whose agent is working/blocked (unknown payload -> none)."""
    try:
        panes = herdr("pane", "list", "--workspace", wsid).get("panes") or []
    except (SystemExit, KeyError):
        return []
    return [p.get("pane_id", "?") for p in panes
            if isinstance(p.get("agent"), dict) and p["agent"].get("status") in ("working", "blocked")]


def apply(cfg, base, dry, replace=False, force=False):
    cwd = str((Path(base).expanduser() / cfg["cwd"]).resolve())
    steps = plan(cfg, cwd)
    if dry:
        print(f"# {cwd}")
        for kind, argv, tab in steps:
            print(f"{tab + ': ' if tab else ''}" + (f"sleep {argv[0]}" if kind == "wait" else " ".join(argv)))
        return 0
    for w in herdr("workspace", "list").get("workspaces", []):
        if cfg["label"] == w.get("label"):
            if not replace:
                print(f"already applied: {w['workspace_id']} {w['label']}")
                return 0
            busy = busy_agents(w["workspace_id"])
            if busy and not force:
                fail(f"agents still working in {w['label']}: {', '.join(busy)} (--force to close anyway)")
            herdr("workspace", "close", w["workspace_id"])
    wsid = root = ""
    last, tabroot = {"": ""}, {"": ""}
    try:
        for kind, argv, tab in steps:
            key = tab or ""
            if kind == "wait":
                time.sleep(float(argv[0]))
                continue
            ctx = {"{ws}": wsid, "{root}": tabroot.get(key) or root, "{pane}": last.get(key, "")}
            res = herdr(*fill(argv, ctx))
            if kind == "workspace":
                wsid = res["workspace"]["workspace_id"]
                root = tabroot[""] = last[""] = res["root_pane"]["pane_id"]
                print(f"workspace {wsid} root {root}")
            elif kind == "tab":
                tabroot[key] = last[key] = res["root_pane"]["pane_id"]
                print(f"tab {res['tab']['tab_id']} root {tabroot[key]}")
            elif kind == "split":
                last[key] = res["pane"]["pane_id"]
                print(f"pane {key or '-'} {last[key]}")
    except SystemExit:
        if wsid:  # no half-built workspace: a retry would be skipped by label
            subprocess.run([HERDR, "workspace", "close", wsid], capture_output=True)
        raise
    record(str(base))
    return 0


def selftest():
    cfg = {"label": "t", "cwd": ".", "focus": False, "env": {"A": "1"}, "panes": [
        {"label": "edit", "direction": "right", "ratio": 0.6, "env": {"PORT": "3000"}},
        {"label": "sh", "from": "previous", "direction": "down", "wait": 0.2},
        {"label": "dev", "tab": "run", "direction": "down", "command": "npm run dev"},
        {"label": "bot", "direction": "right", "agent": "claude", "prompt": "hi"},
    ]}
    steps = plan(cfg, "/tmp")
    kinds = [k for k, _, _ in steps]
    splits = [a for k, a, _ in steps if k == "split"]
    assert steps[0][1][:3] == ["workspace", "create", "--label"], steps[0]
    assert steps[0][1][-2:] == ["--env", "A=1"], steps[0]
    assert kinds.count("tab") == 1 and steps[kinds.index("tab") + 1][2] == "run", steps
    assert len(splits) == 4, splits
    assert splits[0][2:4] == ["--pane", "{root}"] and splits[1][2:4] == ["--pane", "{pane}"], splits
    assert splits[0][-4:] == ["--ratio", "0.6", "--env", "PORT=3000"], splits[0]
    assert kinds.index("wait") < kinds.index("run"), kinds
    assert "--focus" in plan({**cfg, "focus": True}, "/tmp")[0][1]
    assert fill(["{pane}", "echo {pane}"], {"{pane}": "p"}) == ["p", "echo {pane}"]
    assert [a for k, a, _ in steps if k == "agent"][0][3] == "--kind", steps
    assert [a for k, a, _ in steps if k == "rename"][-1][3] == "bot", steps
    print("selftest ok")


def main(argv):
    if "--selftest" in argv:
        return selftest()
    opt = lambda name: argv[argv.index(name) + 1] if name in argv else None
    cwd = Path(opt("--cwd") or caller_cwd()).expanduser().resolve()
    path = Path(opt("--layout")) if opt("--layout") else find_layout(cwd)
    base = path.parent.parent if path and path.parent.name == ".herdr" else Path.cwd()
    if path is None:  # new worktree: its own .herdr/layout.toml may be untracked
        repo = main_repo(cwd)
        path = repo / ".herdr" / "layout.toml" if repo else None
        if path is None or not path.is_file():
            return 0 if "--if-present" in argv else fail(f"no .herdr/layout.toml above {cwd}")
        base = cwd
    return apply(read(path), base, "--dry-run" in argv, "--replace" in argv, "--force" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
