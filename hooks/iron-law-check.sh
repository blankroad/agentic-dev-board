#!/usr/bin/env bash
# PostToolUse hook — emits a systemMessage warning if Write|Edit looks like
# production code written without a preceding test write.
#
# Heuristic (client-side): if file_path is NOT a test file (no "tests/" or "_test.py"
# or "test_" prefix) AND we're modifying Python/JS/TS, emit a gentle reminder.
#
# This is a LIGHT check — the real Iron Law detector (devboard_check_iron_law
# MCP tool) looks at sequences of tool calls within a single turn.

set -eu

# Read stdin JSON
input=$(cat)

# Extract file path (try tool_response first for Write, then tool_input)
file_path=$(echo "$input" | jq -r '.tool_response.filePath // .tool_input.file_path // ""')

[ -z "$file_path" ] && exit 0

# Is this a test file?
case "$file_path" in
    */tests/*|*_test.py|*_test.js|*_test.ts|*/test_*|*.test.js|*.test.ts|*.spec.js|*.spec.ts)
        exit 0  # test file — OK
        ;;
esac

# Is this production code we care about?
case "$file_path" in
    *.py|*.js|*.ts|*.tsx|*.jsx|*.go|*.rs)
        # Heuristic: is there a corresponding test file anywhere?
        base=$(basename "$file_path" | sed -E 's/\.[^.]+$//')
        ext=$(echo "$file_path" | sed -E 's/.*\.([^.]+)$/\1/')

        # Look for test file with same base name
        if find . -type f \( \
            -name "test_${base}.${ext}" \
            -o -name "${base}_test.${ext}" \
            -o -name "${base}.test.${ext}" \
            -o -name "${base}.spec.${ext}" \
        \) 2>/dev/null | head -1 | grep -q .; then
            exit 0  # test exists
        fi

        # Warn via systemMessage
        cat <<EOF
{
  "systemMessage": "⚠ devboard: wrote $file_path without a matching test file (Iron Law of TDD). Consider writing the test first — see skill devboard-tdd."
}
EOF
        exit 0
        ;;
esac

exit 0
