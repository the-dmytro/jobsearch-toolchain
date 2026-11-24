"""Hermetic environment for tests that touch the default config and environment.

The toolchain resolves ``config/jobsearch.toml`` and ``.env`` against the current
directory (CLI default root) or the checkout (library default root), and reads
connector settings from ``JOBTRACKER_*`` / ``SUPABASE_*`` variables. A developer
or CI machine with a real config would change what such tests see. Test modules that rely on those defaults install this fixture::

    from hermetic import set_up_module, tear_down_module  # noqa: F401

    setUpModule, tearDownModule = set_up_module, tear_down_module

It moves the working directory and the library's default project root to an empty
temporary directory and removes every project-related environment variable for the
duration of the module.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

from jobtracker.sources import registry as sources_registry

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ENV_PREFIXES = ("JOBTRACKER_", "SUPABASE_", "NEXT_PUBLIC_", "CRM_")
# The local PostgreSQL integration tests are opted into through this variable (they never use
# the real project's database), so it stays visible.
KEEP_ENV = frozenset({"SUPABASE_TEST_DB_URL"})

_state: dict[str, Any] = {}


def clean_environ(source: dict[str, str] | None = None) -> dict[str, str]:
    """A copy of the environment without project-related variables."""
    source = os.environ if source is None else source
    return {
        key: value
        for key, value in source.items()
        if key in KEEP_ENV or not key.startswith(PROJECT_ENV_PREFIXES)
    }


def set_up_module() -> None:
    temp = tempfile.TemporaryDirectory()
    patchers = [
        mock.patch.dict(os.environ, clean_environ(), clear=True),
        mock.patch.object(sources_registry, "_REPO_ROOT", Path(temp.name)),
    ]
    for patcher in patchers:
        patcher.start()
    _state.update(temp=temp, patchers=patchers, cwd=os.getcwd())
    os.chdir(temp.name)


def tear_down_module() -> None:
    os.chdir(_state.pop("cwd"))
    for patcher in reversed(_state.pop("patchers")):
        patcher.stop()
    _state.pop("temp").cleanup()


def subprocess_kwargs(cwd: str | Path | None = None) -> dict[str, Any]:
    """``subprocess.run`` keyword arguments for ``python -m jobtracker`` without ambient config.

    The child imports a copy of the package from an empty directory, so neither its
    working directory nor its checkout-relative default root contains a real config.
    """
    if "package_copy" not in _state:
        copy = tempfile.TemporaryDirectory()
        shutil.copytree(
            REPO_ROOT / "jobtracker",
            Path(copy.name) / "jobtracker",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        _state["package_copy"] = copy
        atexit.register(copy.cleanup)
    copy_root = Path(_state["package_copy"].name)
    env = clean_environ()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(copy_root), env.get("PYTHONPATH")]))
    return {"cwd": str(cwd or copy_root), "env": env}
