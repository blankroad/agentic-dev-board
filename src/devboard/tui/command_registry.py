from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class CommandError(Exception):
    """Base class for command dispatch errors."""


class UnknownCommandError(CommandError):
    pass


class MissingArgError(CommandError):
    pass


@dataclass(frozen=True)
class _Entry:
    name: str
    required_args: tuple[str, ...]
    handler: Callable[..., None]
    variadic: bool


class CommandRegistry:
    """Parse and dispatch bottom-command-line input.

    Arity rules (red-team A1):
    - Handler with zero positional params → extras dropped silently.
    - Handler with *args → every token after the name forwarded.
    - Otherwise → first len(required_args) tokens forwarded; extras dropped.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, _Entry] = {}

    def register(
        self, name: str, required_args: list[str], handler: Callable[..., None]
    ) -> None:
        import inspect

        try:
            sig = inspect.signature(handler)
            variadic = any(
                p.kind is inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
            )
        except (TypeError, ValueError):
            variadic = False
        self._by_name[name] = _Entry(
            name=name,
            required_args=tuple(required_args),
            handler=handler,
            variadic=variadic,
        )

    def dispatch(self, raw: str) -> None:
        text = raw.lstrip().lstrip(":").strip()
        if not text:
            raise UnknownCommandError("empty command")
        parts = text.split()
        name, args = parts[0], parts[1:]

        entry = self._by_name.get(name)
        if entry is None:
            raise UnknownCommandError(f"Unknown command: {name} (try ?)")

        if len(args) < len(entry.required_args):
            missing = entry.required_args[len(args)]
            raise MissingArgError(f"{name} missing required arg: {missing}")

        if entry.variadic:
            entry.handler(*args)
        else:
            entry.handler(*args[: len(entry.required_args)])
