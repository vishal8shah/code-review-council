from __future__ import annotations

import asyncio
import importlib.util
import inspect


def pytest_pyfunc_call(pyfuncitem):
    """Minimal async test runner fallback when pytest-asyncio is unavailable."""
    if importlib.util.find_spec("pytest_asyncio") is not None:
        return None

    testfunction = pyfuncitem.obj
    if inspect.iscoroutinefunction(testfunction):
        asyncio.run(testfunction(**pyfuncitem.funcargs))
        return True
    return None
