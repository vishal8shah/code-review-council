from __future__ import annotations

import asyncio
import importlib.util
import inspect
from typing import Any


def pytest_pyfunc_call(pyfuncitem: Any) -> bool | None:
    """Minimal async test runner fallback when pytest-asyncio is unavailable."""
    if importlib.util.find_spec("pytest_asyncio") is not None:
        return None

    testfunction = pyfuncitem.obj
    if inspect.iscoroutinefunction(testfunction):
        parameters = inspect.signature(testfunction).parameters
        kwargs = {name: pyfuncitem.funcargs[name] for name in parameters if name in pyfuncitem.funcargs}
        asyncio.run(testfunction(**kwargs))
        return True
    return None
