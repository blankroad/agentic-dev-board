"""FM2 guard — redirect $HOME to a per-session pytest tmpdir so the test
suite cannot silently pollute the developer's real ~/.agentboard/.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 challenge.md Failure Mode 2.

Function-scope `monkeypatch.setattr(Path, 'home', ...)` in individual tests
still takes precedence (direct classmethod replacement short-circuits the
env-var path) — this fixture is a *safety net*, not a replacement for
targeted monkeypatching.
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def home_tmpdir(tmp_path_factory):
    fake_home = tmp_path_factory.mktemp("agentboard_home")
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(fake_home)
    yield fake_home
    if old_home is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = old_home
