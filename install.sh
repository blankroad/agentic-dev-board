#!/usr/bin/env bash
#
# agentic-dev-board — one-line installer
#
#   curl -fsSL https://raw.githubusercontent.com/blankroad/agentic-dev-board/main/install.sh | bash
#
# Idempotent: re-running updates to latest + refreshes skills.
# Customizable via env vars:
#   AGENTIC_DEV_BOARD_DIR    — install location (default ~/.local/share/agentic-dev-board)
#   AGENTIC_DEV_BOARD_BRANCH — git branch (default main)
#   AGENTIC_DEV_BOARD_NO_ALIAS=1 — skip shell rc modification

set -euo pipefail

INSTALL_DIR="${AGENTIC_DEV_BOARD_DIR:-$HOME/.local/share/agentic-dev-board}"
REPO_URL="${AGENTIC_DEV_BOARD_REPO:-https://github.com/blankroad/agentic-dev-board.git}"
BRANCH="${AGENTIC_DEV_BOARD_BRANCH:-main}"

say()  { printf "\033[1;36m→\033[0m %s\n" "$1"; }
ok()   { printf "\033[1;32m✓\033[0m %s\n" "$1"; }
warn() { printf "\033[1;33m!\033[0m %s\n" "$1"; }
err()  { printf "\033[1;31m✗\033[0m %s\n" "$1" >&2; }

# ── Prereq checks ─────────────────────────────────────────────────────────────

command -v git >/dev/null || { err "git required"; exit 1; }
command -v python3 >/dev/null || { err "python3 required"; exit 1; }

py_major=$(python3 -c "import sys; print(sys.version_info.major)")
py_minor=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 11 ]; }; then
    err "python 3.11+ required (found ${py_major}.${py_minor})"
    exit 1
fi

# ── Clone or update ───────────────────────────────────────────────────────────

if [ -d "$INSTALL_DIR/.git" ]; then
    say "updating $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch --quiet origin "$BRANCH"
    git -C "$INSTALL_DIR" checkout --quiet "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only --quiet
else
    say "cloning to $INSTALL_DIR (branch: $BRANCH)"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

# ── venv + pip install ────────────────────────────────────────────────────────

if [ ! -d "$INSTALL_DIR/.venv" ]; then
    say "creating venv"
    python3 -m venv "$INSTALL_DIR/.venv"
fi

say "installing dependencies"
"$INSTALL_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install --quiet -e "$INSTALL_DIR"

BIN="$INSTALL_DIR/.venv/bin/devboard"
if [ ! -x "$BIN" ]; then
    err "install failed — $BIN missing"
    exit 1
fi

# ── Install global skills ─────────────────────────────────────────────────────

say "installing skills to ~/.claude/skills/"
"$BIN" install --scope global --overwrite >/dev/null

# ── Shell alias ───────────────────────────────────────────────────────────────

if [ "${AGENTIC_DEV_BOARD_NO_ALIAS:-0}" != "1" ]; then
    ALIAS_LINE="alias devboard=\"$BIN\""
    MARKER="# agentic-dev-board (auto-installed)"

    shell_name=$(basename "${SHELL:-/bin/bash}")
    case "$shell_name" in
        zsh)  RC="$HOME/.zshrc"  ;;
        bash) RC="$HOME/.bashrc" ;;
        fish) RC="$HOME/.config/fish/config.fish"
              ALIAS_LINE="alias devboard='$BIN'" ;;
        *)    RC="" ;;
    esac

    if [ -n "$RC" ]; then
        mkdir -p "$(dirname "$RC")"
        touch "$RC"
        if grep -Fq "$MARKER" "$RC" 2>/dev/null; then
            # Update existing line in place
            ok "alias already registered in $RC (updated if path changed)"
            # Replace line after marker — pass values via env to avoid quoting bugs
            RC="$RC" MARKER="$MARKER" ALIAS_LINE="$ALIAS_LINE" python3 - <<'PY'
import os, pathlib, re
rc = pathlib.Path(os.environ["RC"])
marker = os.environ["MARKER"]
alias_line = os.environ["ALIAS_LINE"]
txt = rc.read_text()
pattern = re.escape(marker) + r"\n[^\n]*"
new = f"{marker}\n{alias_line}"
txt = re.sub(pattern, new, txt)
rc.write_text(txt)
PY
        else
            printf "\n%s\n%s\n" "$MARKER" "$ALIAS_LINE" >> "$RC"
            ok "added alias to $RC"
        fi
    else
        warn "unknown shell ($shell_name) — add this line to your shell rc manually:"
        echo "    $ALIAS_LINE"
    fi
fi

# ── Verify ────────────────────────────────────────────────────────────────────

VERSION=$("$BIN" --help 2>/dev/null | head -3 | tail -1 || echo "(ok)")

# ── Summary ───────────────────────────────────────────────────────────────────

cat <<EOF

$(ok "agentic-dev-board installed")

   location: $INSTALL_DIR
   binary:   $BIN
   skills:   ~/.claude/skills/devboard-* (9 skills)

$(say "next steps")

   # reload shell
   source ${RC:-~/.zshrc}     # or open a new terminal

   # use in any project
   cd ~/my-project
   devboard init
   devboard install           # writes .mcp.json + hooks (Python auto-detected)

   # open Claude Code — skills and MCP tools auto-load
   claude

$(say "update later")

   curl -fsSL https://raw.githubusercontent.com/blankroad/agentic-dev-board/$BRANCH/install.sh | bash

EOF
