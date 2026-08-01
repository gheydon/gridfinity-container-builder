"""Typed errors for invalid build inputs.

The geometry/config layer raises `SpecError` (a `ValueError`) for bad
user input — unknown printer, unknown colour, bad box-label width, an
out-of-range tool. The CLI catches it and exits cleanly; a web API can
catch the same exception and return a 4xx instead of the process dying.
Previously these were `raise SystemExit`, which killed a worker process.
"""

from __future__ import annotations


class SpecError(ValueError):
    """Invalid build/config input supplied by the user."""
