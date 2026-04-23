#!/usr/bin/env bash
# PostToolUse hook — emits a systemMessage warning if Write|Edit looks like
# production code written without a preceding test write.
#
# Strategy:
# 1. If file IS a test file → silently OK.
# 2. If file is production code:
#    a. Look for matching test file (same base, common test suffixes)
#    b. Check session-local tool-call history (.agentboard/.iron-law-history.jsonl)
#       for a preceding test write in the same session
#    c. If neither → systemMessage reminder

set -eu

input=$(cat)

file_path=$(echo "$input" | jq -r '.tool_response.filePath // .tool_input.file_path // ""')
session_id=$(echo "$input" | jq -r '.session_id // "unknown"')

[ -z "$file_path" ] && exit 0

# Resolve project root (nearest .agentboard ancestor from file_path's dir)
resolve_root() {
    local dir
    if [ -d "$1" ]; then dir="$1"; else dir=$(dirname "$1"); fi
    while [ "$dir" != "/" ]; do
        [ -d "$dir/.agentboard" ] && { echo "$dir"; return 0; }
        dir=$(dirname "$dir")
    done
    echo "."
}

# Classify path
is_test_path() {
    case "$1" in
        */tests/*|*_test.py|*_test.js|*_test.ts|*_test.go|*/test_*|\
        *.test.js|*.test.ts|*.test.tsx|*.test.jsx|*.spec.js|*.spec.ts|\
        */test/*|*_spec.rb)
            return 0
            ;;
    esac
    return 1
}

is_prod_code() {
    case "$1" in
        *.py|*.js|*.ts|*.tsx|*.jsx|*.go|*.rs|*.rb|*.java|*.kt|*.swift|*.cs)
            return 0
            ;;
    esac
    return 1
}

# Record test writes in session history (so subsequent impl writes count them)
if is_test_path "$file_path"; then
    root=$(resolve_root "$file_path")
    hist="$root/.agentboard/.iron-law-history.jsonl"
    mkdir -p "$(dirname "$hist")"
    echo "{\"session_id\":\"$session_id\",\"kind\":\"test_write\",\"path\":\"$file_path\"}" >> "$hist"
    exit 0
fi

# Silently OK if not code we care about
if ! is_prod_code "$file_path"; then
    exit 0
fi

# 1. Check for matching test file in repo
base=$(basename "$file_path" | sed -E 's/\.[^.]+$//')
ext=$(echo "$file_path" | sed -E 's/.*\.([^.]+)$/\1/')

if find . -maxdepth 6 -type f \( \
    -name "test_${base}.${ext}" \
    -o -name "${base}_test.${ext}" \
    -o -name "${base}.test.${ext}" \
    -o -name "${base}.spec.${ext}" \
    -o -name "${base}_spec.${ext}" \
\) 2>/dev/null | head -1 | grep -q .; then
    exit 0  # test exists
fi

# 2. Check session history for a recent test write in same session
root=$(resolve_root "$file_path")
hist="$root/.agentboard/.iron-law-history.jsonl"

if [ -f "$hist" ]; then
    # Look for any test_write in the last 20 entries for this session
    if tail -20 "$hist" 2>/dev/null | jq -r --arg sid "$session_id" \
        'select(.session_id == $sid and .kind == "test_write") | .path' \
        2>/dev/null | head -1 | grep -q .; then
        # Session wrote a test recently — assume TDD discipline
        # (record the impl write for future reference)
        mkdir -p "$(dirname "$hist")"
        echo "{\"session_id\":\"$session_id\",\"kind\":\"impl_write\",\"path\":\"$file_path\"}" >> "$hist"
        exit 0
    fi
fi

# Record this impl write and warn
mkdir -p "$(dirname "$hist")"
echo "{\"session_id\":\"$session_id\",\"kind\":\"impl_write\",\"path\":\"$file_path\"}" >> "$hist"

cat <<EOF
{
  "systemMessage": "⚠ TDD Iron Law: wrote $file_path without any matching test file or prior test write in this session. See skill agentboard-tdd — write the failing test FIRST."
}
EOF
exit 0
