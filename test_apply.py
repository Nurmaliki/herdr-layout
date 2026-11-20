#!/usr/bin/env python3
"""End-to-end checks for apply.py against a fake `herdr` (no server, no framework).

  python3 test_apply.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STUB = '''#!/bin/sh
echo "$*" >> "$LOG"
case "$1 $2" in
  "workspace list") cat "$WS" ;;
  "workspace create") echo '{"result":{"workspace":{"workspace_id":"w9"},"root_pane":{"pane_id":"p-root"}}}' ;;
  "tab create") echo '{"result":{"tab":{"tab_id":"tb1"},"root_pane":{"pane_id":"p-tab"}}}' ;;
  "pane list") cat "$PANES" ;;
  "pane split") n=$(cat "$CNT"); n=$((n+1)); echo $n > "$CNT"; echo "{\\"result\\":{\\"pane\\":{\\"pane_id\\":\\"p$n\\"}}}" ;;
  *) echo '{"result":{"pane":{"pane_id":"p-other"}}}' ;;
esac
'''
LAYOUT = '''[workspace]
label = "t"

[[pane]]
label = "editor"

[[pane]]
label = "dev"
tab = "run"

[[pane]]
label = "logs"
tab = "run"
from = "previous"
'''
BUSY = '{"result":{"panes":[{"pane_id":"p1","agent":{"status":"working"}}]}}'
IDLE = '{"result":{"panes":[{"pane_id":"p1","agent":{"status":"idle"}}]}}'


def run(panes="{\"result\":{\"panes\":[]}}", label=None, *args):
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        stub = d / "herdr"
        stub.write_text(STUB)
        stub.chmod(0o755)
        (d / "panes").write_text(panes)
        (d / "ws").write_text('{"result":{"workspaces":[]}}' if label is None else
                              '{"result":{"workspaces":[{"workspace_id":"w1","label":"%s"}]}}' % label)
        (d / "cnt").write_text("0")
        (d / "lay.toml").write_text(LAYOUT)
        env = dict(os.environ, HERDR_BIN_PATH=str(stub), LOG=str(d / "log"), WS=str(d / "ws"),
                   PANES=str(d / "panes"), CNT=str(d / "cnt"))
        env.pop("HERDR_ENV", None)
        p = subprocess.run([sys.executable, str(ROOT / "apply.py"), "--layout", str(d / "lay.toml"),
                            "--cwd", str(ROOT), *args], capture_output=True, text=True, env=env)
        log = (d / "log").read_text() if (d / "log").exists() else ""
    return p, log


p, log = run()
assert p.returncode == 0, p.stderr
assert "tab create --workspace w9 --label run --cwd" in log, log
splits = [l for l in log.splitlines() if l.startswith("pane split")]
assert [s.split()[3] for s in splits] == ["p-root", "p-tab", "p2"], splits

p, log = run(BUSY, "t", "--replace")
assert p.returncode != 0 and "workspace close" not in log and "p1" in (p.stderr + p.stdout), (p.stdout, p.stderr, log)

p, log = run(BUSY, "t", "--replace", "--force")
assert p.returncode == 0 and "workspace close w1" in log, (p.stdout, p.stderr, log)

p, log = run(IDLE, "t", "--replace")
assert p.returncode == 0 and log.index("workspace close w1") < log.index("workspace create"), log

# worktree without its own layout: use the main worktree's, never a parent dir's
with tempfile.TemporaryDirectory() as tmp:
    x = Path(tmp)
    (x / ".herdr").mkdir()
    (x / ".herdr" / "layout.toml").write_text('[workspace]\nlabel="outer"\n')
    repo = x / "repo"
    (repo / ".herdr").mkdir(parents=True)
    git = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
    git("init", "-q", ".")
    (repo / "README.md").write_text("hi\n")
    git("add", "README.md")
    git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "init")
    (repo / ".herdr" / "layout.toml").write_text('[workspace]\nlabel="inner"\n')
    git("worktree", "add", "-q", str(x / "wt"))
    p = subprocess.run([sys.executable, str(ROOT / "apply.py"), "--dry-run", "--cwd", str(x / "wt")],
                       capture_output=True, text=True)
    assert f"--label inner --cwd {(x / 'wt').resolve()}" in p.stdout, p.stdout + p.stderr

print("test_apply ok")
