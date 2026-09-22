# Agent report: refine-handler implementation and verification

- **Date:** 2026-09-22
- **Status:** implementation complete. Phase 0 scaffold, the structural/elementary
  facts (C-2A/C-2B), and every Tier A handler from
  `agent-reports/2026-09-21-refine-handler-implementation-plan.md` are on
  `feature/refine`; one implementer + one adversarial verifier ran per package
  (grouped by handler family), and all verifier findings inside our code were fixed
- **Base:** scaffold `aaafa5b`; facts landed in `7b1743c`; handlers in `e196632`
  and `b2b8647`; verifier fixes in `7761cfa`
- **Read this if:** you are extending `reasoning/refine/handlers/`, reviewing the
  merge of the facts branches, or picking up a deferred item
- **Stale after:** the SymPy pin moves, `_upstream.py` changes, the
  old-assumption bridge lands, or any upstream refine PR in the deferred list lands

## 1. TL;DR

`handlers_dict` grew from 14 to **56 keys**: all Tier A keys from the plan plus
the auxiliary `Mul` key used by the conjugate-pair rule. Gates on `feature/refine`:

| check | before (cf821f7) | after |
|---|---|---|
| `pytest reasoning/tests -q` | 107 passed, 4 xfailed | **543 passed, 7 xfailed** |
| `pytest validation/test_refine.py -q` | 16 passed, 3 failed | **18 passed, 1 failed** |
| `mypy` (strict) | clean | **clean (111 files)** |
| `validation/compare_backends.py --suite validation/test_refine.py` | 3 outcome mismatches | **1 outcome mismatch** |
| `git diff aaafa5b..HEAD -- reasoning/refine/_upstream.py` | — | **0 lines** |

The only remaining validation failure is `test_sign`'s old-assumption path
(`Symbol('x', imaginary=True)`); the remaining xfails are listed in §6.

## 2. Architecture as landed

```
reasoning/refine/
  __init__.py        public API + handler auto-discovery (pkgutil)
  _upstream.py       vendored dispatcher, 14 initial handlers, local ask
  handlers/
    _trig.py         shared pi/2 coefficient/parity parser
    <task>.py        one module per registry key (or key family)
reasoning/tests/
  refine_harness.py  reference ask, stub/scripted/recording ask, numeric oracle
  conftest.py        reference_ask fixture
  test_refine_<task>.py
  test_refine_verifier_*.py   adversarial tests kept by the verifiers
```

New handlers call `_upstream.ask(...)` through the module attribute so the
harness can redirect `ask`; `test_refine_harness.py::test_no_duplicate_handler_keys`
scans the handler sources and fails on duplicate registrations.

## 3. Phase 0 and Phase 2

- **SCAFFOLD-PKG / HARNESS / TRIGHELPER** (`aaafa5b`): package split, harness with
  a numeric oracle independent of `ask`, and the shared `pi/2` parser.
- **C-2A / C-2B** (`7b1743c`): merged `agent/2a-add-mul-pow` and
  `agent/2b-elementary-functions`. The merge exposed an unsound interaction:
  2a's generic `b**imaginary -> real iff imaginary(log b)` equivalence contradicts
  the `base == E` special case that 2b relies on. Fixed by giving the `E` case
  SymPy's precedence and adding the sound negative rule; `test_pow1` and
  `test_sin_cos` flipped from xfail to regular tests.

## 4. Tier A handlers

Each row: handler module, registry key(s), test module, verifier verdict.

| handler | keys | tests | verifier |
|---|---|---|---|
| `matrix_transpose.py` | `Transpose` | `test_refine_matrix_transpose.py` | PASS (asks `expr.arg`; exact-port closure missing) |
| `matrix_inverse.py` | `Inverse` | `test_refine_matrix_inverse.py` | PASS (singular path raises, as upstream) |
| `matrix_det.py` | `Determinant` | `test_refine_matrix_det.py` | PASS |
| `matrix_matmul.py` | `MatMul` | `test_refine_matrix_matmul.py` | PASS (`X.T*X` cancels; `X*X.T` needs closure) |
| `matrix_trace.py` | `Trace` | `test_refine_matrix_trace.py` | PASS |
| `matrix_matadd.py` | `MatAdd` | `test_refine_matrix_matadd.py` | PASS |
| `matrix_hadamard.py` | `HadamardProduct` | `test_refine_matrix_hadamard.py` | PASS |
| `matrix_element.py` | `MatrixElement` (override) | `test_refine_matrix_element.py` | PASS after fix (see §5) |
| `trig_tan.py` | `tan` | `test_refine_trig_tan.py` | PASS |
| `trig_cot.py` | `cot` | `test_refine_trig_cot.py` | PASS |
| `trig_sec_csc.py` | `sec`, `csc` | `test_refine_trig_sec_csc.py` | PASS |
| `trig_sinc.py` | `sinc` | `test_refine_trig_sinc.py` | PASS |
| `trig_sin_cos.py` | `sin`, `cos` (override) | `test_refine_trig_sin_cos.py` | PASS (PR #29450 crash guarded) |
| `hyperbolic_forward.py` | `sinh`, `cosh`, `tanh`, `coth`, `sech`, `csch` | `test_refine_hyperbolic_forward.py` | PASS after fix (`(-1)**n` shifts) |
| `hyperbolic_inverse.py` | `asinh`, `acosh`, `atanh`, `acoth`, `asech`, `acsch` | `test_refine_hyperbolic_inverse.py` | PASS |
| `inverse_trig.py` | `asin`, `acos`, `atan` | `test_refine_inverse_trig.py` | PASS after fix (strict `atan` bounds) |
| `log.py` | `log` | `test_refine_log.py` | PASS |
| `conjugate.py` | `conjugate`, `Mul` | `test_refine_conjugate.py` | PASS after fix (commutativity guard) |
| `pow.py` | `Pow` (override) | `test_refine_pow.py` | PASS (nested-power bug fixed) |
| `abs.py` | `Abs` (override) | `test_refine_abs.py` | PASS (zero case fixed) |
| `sign.py` | `sign` (override) | `test_refine_sign.py` | PASS (assumptions now passed through) |
| `arg.py` | `arg` (override) | `test_refine_arg.py` | PASS |
| `frac.py` | `frac` | `test_refine_frac.py` | PASS |
| `mod.py` | `Mod` | `test_refine_mod.py` | PASS |
| `rem.py` | `Rem` | `test_refine_rem.py` | PASS (floor identity restricted to sign cases) |
| `factorial.py` | `factorial` | `test_refine_factorial.py` | PASS |
| `binomial.py` | `binomial` | `test_refine_binomial.py` | PASS |
| `rf_ff.py` | `RisingFactorial`, `FallingFactorial` | `test_refine_rf_ff.py` | PASS |
| `special_gamma.py` | `gamma` | `test_refine_gamma.py` | PASS |
| `minmax_min.py` | `Min` | `test_refine_min.py` | PASS |
| `minmax_max.py` | `Max` | `test_refine_max.py` | PASS |
| `dirac_delta.py` | `DiracDelta` | `test_refine_dirac_delta.py` | PASS |
| `kronecker_delta.py` | `KroneckerDelta` | `test_refine_kronecker_delta.py` | PASS |

## 5. Verifier findings fixed

1. **MatrixElement off-diagonal zero was unsound.** Independent symbols are not
   provably distinct (`i == j` is satisfiable), and `could_extract_minus_sign`
   is not a distinctness proof. Now only structurally nonzero differences
   (`i`, `i + 1`, unequal literals) or an assumption-proven `Q.ne(i, j)` yield
   zero; regression tests updated.
2. **`Mul` conjugate-pair rule fired on noncommutative products.** Guarded with
   `expr.is_commutative`.
3. **`atan(tan(x)) -> x` was unsound at `x = ±pi/2`** (the closed rectangle
   includes the poles). The rule now requires the open interval via `Q.gt`/`Q.lt`.
4. **Hyperbolic integer shifts were left unchanged** despite the quoted
   `(-1)**n` rule; now emitted and reduced when parity is known.
5. **Harness oracles fixed:** `_odd` treated non-integers as odd, and the
   `nonzero` check accepted non-real values; both now match the predicates.

## 6. Remaining xfails (7)

| test | reason |
|---|---|
| `test_refine.py::test_sign` | old-assumption symbols (`Symbol('x', real=True)`), 2 asserts |
| `test_refine_sign.py::test_sign_old_assumption_imaginary_symbol` | needs old-assumption bridge: `ask(Q.imaginary(y))` is `None` for `Symbol('y', imaginary=True)` |
| `test_refine_verifier_matrix.py::test_transpose_reference_ask_parity_on_transpose_assumption` | `satask` cannot derive `Q.symmetric(X)` from `Q.symmetric(X.T)`; local port asks `expr.arg` |
| `test_refine_verifier_matrix.py::test_inverse_reference_ask_parity_on_inverse_assumption` | same closure gap for `Q.orthogonal(X**-1)` |
| `test_refine_verifier_matrix.py::test_inverse_unitary_soundness_counterexample` | inherited upstream bug: `U**-1 -> U.conjugate()` for unitary `U` |
| `test_refine_verifier_matrix.py::test_matmul_unitary_soundness_counterexample` | inherited upstream bug: `conjugate(U)*U -> I` for unitary `U` |
| `test_satask.py::test_invertible` | pre-existing on the facts branches, unrelated to refine |

The two inherited upstream unitary bugs are ported verbatim per the plan's
fidelity rule; fixing them would diverge from pinned SymPy and should be done
upstream first. The reference-ask parity xfails are the C-2C closure gap.

## 7. Deferred and non-goals (do not reschedule accidentally)

- **Tier B, deferred:** branch-aware `conjugate` continuation (needs external
  math verification), `acot`/`asec`/`acsc`, `adjoint` (needs C-2C),
  `factorial2`/`subfactorial`, `fibonacci`/`lucas`/`harmonic`,
  `KroneckerProduct`, `LeviCivita`, `SingularityFunction`, `LambertW`,
  `exp_polar`/`polar_lift`/`principal_branch`.
- **Explicit non-goals:** `Piecewise`, `Relational`/inequalities (the
  `Boolean._eval_refine` + SymPy `ask` route already reproduces upstream),
  special functions at large, sets, calculus, number theory, and duplicating
  upstream `_eval_refine` behavior.
- **Core follow-ups:** C-2C matrix predicate closure, C-2D old-assumption bridge
  (policy decision), and upstream fixes for the two unitary bugs.

## 8. Reproduce

```bash
cd /home/tilo/reasoning-refine
/home/tilo/reasoning/.venv/bin/python -m pytest reasoning/tests -q
/home/tilo/reasoning/.venv/bin/python -m mypy
/home/tilo/reasoning/.venv/bin/python -m pytest validation/test_refine.py -q
/home/tilo/reasoning/.venv/bin/python validation/compare_backends.py --suite validation/test_refine.py
```
