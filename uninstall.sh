#!/usr/bin/env bash
#
# agentic-dev-board — one-line uninstaller
#
#   curl -fsSL https://raw.githubusercontent.com/blankroad/agentic-dev-board/main/uninstall.sh | bash
#
# Or, if already cloned:
#
#   ~/.local/share/agentic-dev-board/uninstall.sh
#
# Safe by default: removes alias, global skills, agentboard-tagged user hooks,
# the install dir + venv, AND the agentboard MCP / hook wiring of the CWD
# project (.mcp.json, opencode.json, .claude/skills/agentboard-*, .claude/
# hooks). User data in ~/.agentboard/ and <cwd>/.agentboard/ is PRESERVED
# unless --purge-data is passed.
#
# Flags:
#   --purge-data        Also delete ~/.agentboard/ + <cwd>/.agentboard/ user data
#   --global-only       Skip CWD project cleanup (only touch global state)
#   --keep-install      Skip removal of ~/.local/share/agentic-dev-board/
#   --keep-alias        Skip shell rc alias removal
#   --yes               Skip confirmation prompts
#
# Env vars:
#   AGENTIC_DEV_BOARD_DIR   — install location (default ~/.local/share/agentic-dev-board)

set -euo pipefail

INSTALL_DIR="${AGENTIC_DEV_BOARD_DIR:-$HOME/.local/share/agentic-dev-board}"
PURGE_DATA=0
GLOBAL_ONLY=0
KEEP_INSTALL=0
KEEP_ALIAS=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --purge-data)   PURGE_DATA=1 ;;
        --global-only)  GLOBAL_ONLY=1 ;;
        --keep-install) KEEP_INSTALL=1 ;;
        --keep-alias)   KEEP_ALIAS=1 ;;
        --yes|-y)       ASSUME_YES=1 ;;
        -h|--help)
            sed -n '2,28p' "$0"
            exit 0 ;;
        *) printf "unknown flag: %s\n" "$1" >&2; exit 1 ;;
    esac
    shift
done

[ "$GLOBAL_ONLY" -eq 1 ] && SCOPE="global" || SCOPE="all"

say()  { printf "\033[1;36m→\033[0m %s\n" "$1"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$1"; }
warn() { printf "\033[1;33m!\033[0m %s\n" "$1"; }
err()  { printf "\033[1;31m✗\033[0m %s\n" "$1" >&2; }

confirm() {
    [ "$ASSUME_YES" -eq 1 ] && return 0
    printf "%s [y/N] " "$1"
    read -r reply
    case "$reply" in y|Y|yes|YES) return 0 ;; *) return 1 ;; esac
}

# ── Pre-flight summary ────────────────────────────────────────────────────────

say "agentic-dev-board uninstall"
echo "    install dir:  $INSTALL_DIR  (remove: $([ "$KEEP_INSTALL" -eq 1 ] && echo no || echo yes))"
echo "    scope:        $SCOPE  (global: skills + tagged user hooks always removed$([ "$SCOPE" = "all" ] && echo "; project: cleans CWD .mcp.json + opencode.json + .claude/skills + hooks"))"
echo "    cwd:          $PWD"
echo "    user data:    ~/.agentboard/ + <cwd>/.agentboard/  (remove: $([ "$PURGE_DATA" -eq 1 ] && echo yes || echo no))"
echo "    shell alias:  remove: $([ "$KEEP_ALIAS" -eq 1 ] && echo no || echo yes)"
echo

if [ "$PURGE_DATA" -eq 1 ]; then
    warn "--purge-data will delete ~/.agentboard/ AND <cwd>/.agentboard/ (learnings, goal history)"
fi

confirm "Proceed with uninstall?" || { say "aborted"; exit 0; }

# ── Run agentboard uninstall (global scope) via the venv binary ───────────────

BIN="$INSTALL_DIR/.venv/bin/agentboard"
if [ -x "$BIN" ]; then
    say "removing scope=$SCOPE artifacts (skills + hooks + MCP wiring)"
    PURGE_FLAG=""
    [ "$PURGE_DATA" -eq 1 ] && PURGE_FLAG="--purge-data"
    "$BIN" uninstall --scope "$SCOPE" --target both --yes $PURGE_FLAG || \
        warn "agentboard uninstall reported errors — continuing"
else
    warn "agentboard binary not found at $BIN — falling back to inline python cleanup"
    SCOPE="$SCOPE" PURGE_DATA="$PURGE_DATA" CWD="$PWD" python3 - <<'PY' || warn "inline cleanup encountered errors — continuing"
import json, os, shutil
from pathlib import Path

scope = os.environ["SCOPE"]
purge = os.environ["PURGE_DATA"] == "1"
home = Path.home()
cwd = Path(os.environ["CWD"])

def rm_agentboard_skills(dir_):
    if not dir_.exists(): return 0
    n = 0
    for c in dir_.iterdir():
        if c.is_dir() and c.name.startswith("agentboard-"):
            shutil.rmtree(c); n += 1
    return n

def strip_settings(p):
    if not p.exists(): return 0
    try: data = json.loads(p.read_text())
    except json.JSONDecodeError: return 0
    hooks = data.get("hooks")
    if not isinstance(hooks, dict): return 0
    legacy = ("danger-guard.sh", "iron-law-check.sh", "activity-log.py")
    n = 0; empty = []
    for ev, entries in list(hooks.items()):
        if not isinstance(entries, list): continue
        kept = []
        for e in entries:
            if not isinstance(e, dict): kept.append(e); continue
            tagged = e.get("_source") == "agentboard"
            legacy_match = any(
                isinstance(h.get("command"), str) and h["command"].endswith(legacy)
                for h in e.get("hooks", [])
            )
            if tagged or legacy_match: n += 1
            else: kept.append(e)
        if kept: hooks[ev] = kept
        else: empty.append(ev)
    for ev in empty: del hooks[ev]
    if not hooks: del data["hooks"]
    if n: p.write_text(json.dumps(data, indent=2) + "\n")
    return n

def strip_mcp(p):
    if not p.exists(): return False
    try: data = json.loads(p.read_text())
    except json.JSONDecodeError: return False
    servers = data.get("mcpServers")
    if not isinstance(servers, dict): return False
    changed = False
    for k in ("agentboard", "devboard"):
        if k in servers: del servers[k]; changed = True
    if not changed: return False
    if not servers: del data["mcpServers"]
    if data: p.write_text(json.dumps(data, indent=2) + "\n")
    else: p.unlink()
    return True

def strip_opencode(p):
    if not p.exists(): return False
    try: data = json.loads(p.read_text())
    except json.JSONDecodeError: return False
    mcp = data.get("mcp")
    if not isinstance(mcp, dict) or "agentboard" not in mcp: return False
    del mcp["agentboard"]
    if not mcp: del data["mcp"]
    if list(data.keys()) == ["$schema"]: p.unlink()
    else: p.write_text(json.dumps(data, indent=2) + "\n")
    return True

# global
g_skills = rm_agentboard_skills(home / ".claude" / "skills")
g_skills += rm_agentboard_skills(home / ".config" / "opencode" / "skills")
g_hooks = strip_settings(home / ".claude" / "settings.json")
print(f"  global skills removed: {g_skills}, user hooks pruned: {g_hooks}")
if purge and (home / ".agentboard").exists():
    shutil.rmtree(home / ".agentboard")
    print(f"  global data removed: {home/'.agentboard'}")

# project (CWD)
if scope == "all":
    p_skills = rm_agentboard_skills(cwd / ".claude" / "skills")
    p_skills += rm_agentboard_skills(cwd / ".opencode" / "skills")
    p_hooks = strip_settings(cwd / ".claude" / "settings.json")
    p_mcp = strip_mcp(cwd / ".mcp.json")
    p_oc = strip_opencode(cwd / "opencode.json")
    # legacy hook scripts
    hd = cwd / ".claude" / "hooks"
    p_scripts = 0
    if hd.exists():
        for name in ("danger-guard.sh", "iron-law-check.sh", "activity-log.py"):
            f = hd / name
            if f.exists(): f.unlink(); p_scripts += 1
    print(f"  project (CWD) skills: {p_skills}, hook scripts: {p_scripts}, settings hooks: {p_hooks}, .mcp.json: {p_mcp}, opencode.json: {p_oc}")
    if purge and (cwd / ".agentboard").exists():
        shutil.rmtree(cwd / ".agentboard")
        print(f"  project data removed: {cwd/'.agentboard'}")
PY
fi

# ── Shell rc alias ────────────────────────────────────────────────────────────

if [ "$KEEP_ALIAS" -eq 0 ]; then
    MARKER="# agentic-dev-board (auto-installed)"
    shell_name=$(basename "${SHELL:-/bin/bash}")
    case "$shell_name" in
        zsh)  RC="$HOME/.zshrc"  ;;
        bash) RC="$HOME/.bashrc" ;;
        fish) RC="$HOME/.config/fish/config.fish" ;;
        *)    RC="" ;;
    esac

    if [ -n "$RC" ] && [ -f "$RC" ] && grep -Fq "$MARKER" "$RC" 2>/dev/null; then
        RC="$RC" MARKER="$MARKER" python3 - <<'PY'
import os, pathlib, re
rc = pathlib.Path(os.environ["RC"])
marker = os.environ["MARKER"]
txt = rc.read_text()
pattern = r"\n?" + re.escape(marker) + r"\n[^\n]*\n?"
new_txt, n = re.subn(pattern, "", txt, count=1)
if n:
    rc.write_text(new_txt)
PY
        ok "removed alias from $RC"
    else
        say "no alias marker found in shell rc — skipping"
    fi
fi

# ── Remove install dir ────────────────────────────────────────────────────────

if [ "$KEEP_INSTALL" -eq 0 ]; then
    if [ -d "$INSTALL_DIR" ]; then
        # Sanity check: refuse to delete anything that doesn't look like our install.
        if [ ! -d "$INSTALL_DIR/.venv" ] && [ ! -f "$INSTALL_DIR/install.sh" ]; then
            err "$INSTALL_DIR does not look like an agentic-dev-board install (no .venv or install.sh) — refusing to delete"
        else
            say "removing $INSTALL_DIR"
            rm -rf "$INSTALL_DIR"
            ok "removed install dir"
        fi
    else
        say "install dir already gone: $INSTALL_DIR"
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────

cat <<EOF

$(ok "agentic-dev-board uninstalled")

   Shell may still have the old alias cached — open a new terminal or run:
       unalias agentboard 2>/dev/null || true

   This run cleaned scope=$SCOPE. Other agentboard-using projects on this
   machine are NOT touched — re-run uninstall.sh from inside each one
   (or remove their .mcp.json / opencode.json / .claude/skills/agentboard-*
   manually).

EOF
