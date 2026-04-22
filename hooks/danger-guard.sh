#!/usr/bin/env bash
# PreToolUse hook — inspects shell commands via agentboard_check_command_safety
# pattern library. Blocks hard-destructive patterns outright; asks for
# confirmation on warn-level patterns.
#
# Applies to matcher: "Bash"

set -eu

input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // ""')

[ -z "$command" ] && exit 0

# Hard-blocked patterns
if echo "$command" | grep -qE '(\brm\s+-rf?\s+/\s*$|\brm\s+-rf?\s+/\*|\brm\s+-rf?\s+~(/|$)|:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:|\bdd\s+.*of=/dev/|>\s*/dev/(sda|nvme|hda)|mkfs\.[a-z0-9]+\s+/dev/)'; then
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "DangerGuard blocked: irreversibly destructive command pattern detected"
  }
}
EOF
    exit 0
fi

# Warn-level patterns — prompt user
if echo "$command" | grep -qE '(\bgit\s+push\s+.*--force|\bgit\s+push\s+.*-f\b|\bgit\s+reset\s+--hard|\bgit\s+clean\s+-[a-z]*f|\bgit\s+branch\s+-D|\bchmod\s+(-R\s+)?0?777\b|\bsudo\s+rm|\bcurl\s+[^|]+\|\s*(sh|bash|zsh)|\bDROP\s+TABLE|\bTRUNCATE\s+TABLE|\beval\s*\(|\bexec\s*\()' ; then
    cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "ask",
    "permissionDecisionReason": "DangerGuard: potentially destructive command — please confirm"
  }
}
EOF
    exit 0
fi

exit 0
