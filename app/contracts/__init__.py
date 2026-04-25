"""Contracts — typed payloads shared between modules.

Rules:
- Files in here contain Pydantic models / plain dataclasses / TypedDicts only.
- NO imports from app.modules.* — that would defeat the point.
- NO business logic — if you find yourself writing a function that does
  anything more than a `from_x()` / `to_x()` transform, it does not belong here.

When a module needs data owned by another module, it asks via a contract
defined here, not by importing the other module's service directly.
"""
