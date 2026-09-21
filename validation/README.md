# validation

This directory is an unbiased way to evaluate progress in the project. The test
suite comes from the SymPy commit pinned by the `sympy` extra in
`pyproject.toml`, so it should not be edited here.

`test_query.py` re-exports SymPy's `assumptions/tests/test_query.py` with `ask`
and `_ask_recursive` bound to `reasoning.satask.satask`, and refuses to run
against a different SymPy install. Install the pinned version with
`pip install -e '.[sympy,dev]'`.

`test_refine.py` re-exports SymPy's `assumptions/tests/test_refine.py` with
`refine` and `refine_sin_cos` bound to `reasoning.refine`. Its three current
failures are known core gaps: Pow real closure, old-assumption symbols, and
parity facts for sums.

`compare_backends.py` runs the suites against this checkout's implementations
and against SymPy's unmodified ones, then compares per-test outcomes. The
refine suite is opt-in because it reports expected failures:
`python validation/compare_backends.py --suite validation/test_refine.py`.
