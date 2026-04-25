"""Modules — plugin-style feature packages.

Each subpackage exposes one function:

    def register(app: FastAPI) -> None: ...

which wires the module into the app (routers, startup hooks, celery beat,
anything else). `register_all` iterates over every known module.

Adding a module: create the subpackage with an __init__.py that exposes
`register`, then add it to `_MODULES` below. That's the only glue file that
ever changes.
"""
from __future__ import annotations

from fastapi import FastAPI

from app.modules import approvals as _approvals
from app.modules import memorycore as _memorycore
from app.modules import projects as _projects
from app.modules import router as _router

_MODULES = (_memorycore, _approvals, _projects, _router)


def register_all(app: FastAPI) -> None:
    for module in _MODULES:
        module.register(app)
