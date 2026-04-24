"""FM2 manifest — full suite leaves developer real ~/.agentboard untouched.

Ref: .agentboard/goals/g_20260424_035650_6ecdd2 challenge.md Failure Mode 2.

The conftest home_tmpdir session fixture redirects ``$HOME`` to a per-session
pytest tmpdir. On POSIX, ``Path.home()`` routes through ``$HOME``, so any code
under test that calls Path.home() or ``os.path.expanduser('~')`` lands in the
tmpdir — making it structurally impossible for the suite to pollute the real
developer HOME.
"""

from pathlib import Path


def test_pytest_home_equals_session_tmpdir(home_tmpdir: Path) -> None:
    # If this fails, the FM2 guard is broken and some test could silently
    # write to the developer's real ~/.agentboard/ during a full suite run.
    assert Path.home() == home_tmpdir
