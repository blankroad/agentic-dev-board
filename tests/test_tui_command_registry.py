from __future__ import annotations

import pytest

from devboard.tui.command_registry import (
    CommandRegistry,
    MissingArgError,
    UnknownCommandError,
)


def test_dispatch_calls_registered_handler() -> None:
    calls: list[tuple] = []
    reg = CommandRegistry()
    reg.register("goals", [], lambda *args: calls.append(("goals", args)))

    reg.dispatch(":goals")

    assert calls == [("goals", ())]


def test_unknown_command_raises() -> None:
    reg = CommandRegistry()
    with pytest.raises(UnknownCommandError) as exc:
        reg.dispatch(":nope")
    assert "nope" in str(exc.value)


def test_missing_arg_raises() -> None:
    reg = CommandRegistry()
    reg.register("diff", ["task_id"], lambda task_id: None)
    with pytest.raises(MissingArgError) as exc:
        reg.dispatch(":diff")
    assert "task_id" in str(exc.value)


def test_extra_args_do_not_crash_handler() -> None:
    """Red-team A1: ':goals foo bar' must not crash a zero-arg handler with
    TypeError. Extra args are silently dropped; the dispatch is still a
    hit for the registered command."""
    calls: list[tuple] = []
    reg = CommandRegistry()
    reg.register("goals", [], lambda: calls.append(("goals", ())))
    reg.dispatch(":goals foo bar")
    assert calls == [("goals", ())]


def test_variadic_command_receives_all_tokens() -> None:
    """Commands that declare a single required arg but accept more (e.g.
    ':learn one two three' → full query) must receive every token after
    the name, not just the first."""
    received: list[tuple] = []
    reg = CommandRegistry()
    reg.register("learn", ["query"], lambda *q: received.append(q))
    reg.dispatch(":learn one two three")
    assert received == [("one", "two", "three")]
