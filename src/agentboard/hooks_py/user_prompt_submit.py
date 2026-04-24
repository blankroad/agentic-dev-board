"""UserPromptSubmit hook — R3 auto-inject.

Searches the global learnings index for entries matching the current prompt
text, formats the top-K as a <system-reminder> block, returns the formatted
string (the hook runner prints it to stdout; Claude Code injects stdout into
model context per A1 verification).
"""

from agentboard.storage.global_index import GlobalIndex


HEADER = "<system-reminder>"
FOOTER = "</system-reminder>"
MAX_BYTES = 2048


def _format_entry(learning: dict) -> str:
    return f"- {learning.get('name', '?')}: {learning.get('content', '')}"


def _size(lines: list[str]) -> int:
    return len("\n".join(lines).encode("utf-8"))


def main(payload: dict, top_k: int = 5) -> str:
    # `or ""` handles explicit None (Claude Code runtime may null-serialize
    # missing prompts) as well as the default for absent keys.
    prompt = payload.get("prompt") or ""
    if not prompt.strip():
        # Empty / whitespace-only prompt must NOT inject top-K noise.
        # The token matcher treats empty kw_tokens as "all entries pass";
        # guard here keeps that from leaking into model context.
        return ""
    learnings = GlobalIndex().search_learnings(keyword=prompt)[:top_k]
    if not learnings:
        return ""
    lines: list[str] = [HEADER]
    included = 0
    for learning in learnings:
        entry = _format_entry(learning)
        prospective = lines + [entry, FOOTER]
        if _size(prospective) > MAX_BYTES and included > 0:
            remaining = len(learnings) - included
            marker = f"...({remaining} more via agentboard_search_learnings)"
            lines.append(marker)
            break
        lines.append(entry)
        included += 1
    else:
        # Consumed every learning without triggering truncation.
        pass
    lines.append(FOOTER)
    return "\n".join(lines)
