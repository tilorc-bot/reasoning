"""Assumption-driven refinement backed by the independent engine.

The vendored dispatcher and initial handlers live in
:mod:`reasoning.refine._upstream`; every additional handler is a module in
:mod:`reasoning.refine.handlers` that registers itself into
``handlers_dict`` when imported.  Importing this package loads all of them.
"""
from __future__ import annotations

import importlib
import pkgutil

from ._upstream import (
    ask,
    handlers_dict,
    refine,
    refine_Heaviside,
    refine_Pow,
    refine_abs,
    refine_arg,
    refine_atan2,
    refine_exp,
    refine_floor_ceiling,
    refine_im,
    refine_matrixelement,
    refine_re,
    refine_sign,
    refine_sin_cos,
)

__all__ = [
    "ask",
    "handlers_dict",
    "refine",
    "refine_Heaviside",
    "refine_Pow",
    "refine_abs",
    "refine_arg",
    "refine_atan2",
    "refine_exp",
    "refine_floor_ceiling",
    "refine_im",
    "refine_matrixelement",
    "refine_re",
    "refine_sign",
    "refine_sin_cos",
]


def _load_handlers() -> None:
    """Import every public module in :mod:`reasoning.refine.handlers`."""
    package = importlib.import_module(__name__ + ".handlers")
    path = getattr(package, "__path__", None)
    if path is None:
        return
    for info in pkgutil.iter_modules(path):
        if not info.name.startswith("_"):
            importlib.import_module(f"{package.__name__}.{info.name}")


_load_handlers()
