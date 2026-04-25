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
# and the install dir + venv. User data in ~/.agentboard/ is PRESERVED unless
# --purge-data is passed.
#
# Flags:
#   --purge-data        Also delete ~/.agentboard/ user data (learnings, sessions)
#   --keep-install      Skip removal of ~/.local/share/agentic-dev-board/
#   --keep-alias        Skip shell rc alias removal
#   --yes               Skip confirmation prompts
#
# Env vars:
#   AGENTIC_DEV_BOARD_DIR   — install location (default ~/.local/share/agentic-dev-board)

set -euo pipefail

INSTALL_DIR="${AGENTIC_DEV_BOARD_DIR:-$HOME/.local/share/agentic-dev-board}"
PURGE_DATA=0
KEEP_INSTALL=0
KEEP_ALIAS=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --purge-data)   PURGE_DATA=1 ;;
        --keep-install) KEEP_INSTALL=1 ;;
        --keep-alias)   KEEP_ALIAS=1 ;;
        --yes|-y)       ASSUME_YES=1 ;;
        -h|--help)
            sed -n '2,25p' "$0"
            exit 0 ;;
        *) printf "unknown flag: %s\n" "$1" >&2; exit 1 ;;
    esac
    shift
done

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
echo "    user data:    ~/.agentboard/  (remove: $([ "$PURGE_DATA" -eq 1 ] && echo yes || echo no))"
echo "    shell alias:  remove: $([ "$KEEP_ALIAS" -eq 1 ] && echo no || echo yes)"
echo "    global skills + tagged user hooks: always removed"
echo

if [ "$PURGE_DATA" -eq 1 ]; then
    warn "--purge-data will delete ~/.agentboard/ (learnings, session history)"
fi

confirm "Proceed with uninstall?" || { say "aborted"; exit 0; }

# ── Run agentboard uninstall (global scope) via the venv binary ───────────────

BIN="$INSTALL_DIR/.venv/bin/agentboard"
if [ -x "$BIN" ]; then
    say "removing global skills + agentboard-tagged user hooks"
    PURGE_FLAG=""
    [ "$PURGE_DATA" -eq 1 ] && PURGE_FLAG="--purge-data"
    "$BIN" uninstall --scope global --target both --yes $PURGE_FLAG || \
        warn "agentboard uninstall reported errors — continuing"
else
    warn "agentboard binary not found at $BIN — skipping skills/hooks cleanup"
    warn "(skills/hooks may need manual removal from ~/.claude/skills/, ~/.config/opencode/skills/, ~/.claude/settings.json)"
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

   Per-project artifacts are NOT touched by this script. To clean a project:
       cd <project>
       agentboard uninstall --scope project        # if binary still on PATH
   or remove these manually:
       <project>/.claude/skills/agentboard-*
       <project>/.opencode/skills/agentboard-*
       <project>/.claude/hooks/{danger-guard.sh,iron-law-check.sh,activity-log.py}
       agentboard entries in <project>/.mcp.json and <project>/opencode.json
       <project>/.agentboard/   (user data — only if you no longer need it)

EOF
