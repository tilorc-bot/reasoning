"""Run SymPy's own ``test_refine.py`` against this checkout's ``refine``.

The suite is imported from the installed SymPy, which the ``sympy`` extra in
``pyproject.toml`` pins to a git commit.  ``refine`` and ``refine_sin_cos``
are rebound to ``reasoning.refine`` in the imported module, and the test
functions are re-exported so pytest collects them.
"""
from ._pinned_sympy import check_pinned_sympy

check_pinned_sympy()

from reasoning.refine import refine as _refine  # noqa: E402
from reasoning.refine import refine_sin_cos as _refine_sin_cos  # noqa: E402
from sympy.assumptions.tests import test_refine as _suite  # noqa: E402

_suite.refine = _refine
_suite.refine_sin_cos = _refine_sin_cos

from sympy.assumptions.tests.test_refine import *  # noqa: E402,F401,F403
