# Agent plan: independent refine-handler implementation and verification

- **Date:** 2026-09-21
- **Status:** plan only; no handler work started. Base is the existing branch
  `feature/refine` at `cf821f7` ("Add refine with handlers backed by the independent
  engine"), on top of `d993cf6` (the missing-handler report); the working tree holds
  only this untracked plan. `feature/refine` is both the base for the task branches
  and the integration branch they merge back into (§8)
- **Scope:** every missing handler catalogued in
  `agent-reports/2026-09-21-refine-missing-handlers.md`, plus the scaffolding needed
  to implement each one independently and verify it before merge
- **Read this if:** you are the orchestrator spawning one agent per handler, or a
  verifier checking one handler's work
- **Stale after:** the package scaffold lands, the handler task table changes, the
  SymPy pin moves, `agent/2a-add-mul-pow` / `agent/2b-elementary-functions` merge, or
  upstream lands one of the referenced PRs
- **TL;DR:** restructure `reasoning/refine.py` into a package whose handlers
  self-register from `reasoning/refine/handlers/*` (one file per registry key, so two
  tasks never touch the same file), add a reference-ask/numeric-oracle test harness,
  then run one implementer + one verifier per task on its own worktree/branch.
  Independence unit is the **registry key** (`handlers_dict` name), not the rule:
  every task owns exactly one key and may add new rules for it. Two tasks must never
  register the same key, and no task may edit `_upstream.py`; fixes are overrides.
  Tier A (matrix ports, log, conjugate-basic, tan/cot/sec/csc, hyperbolic, Min/Max,
  frac/Mod/Rem, factorial/binomial, gamma, deltas, Pow/Abs/sign/arg/sin-cos fixes) is
  ~30 parallel tasks; catalog/deferred items are listed so they are not rediscovered.

## 1. Ground rules

1. **One task = one registry key.** A task may add every rule for that key. Never
   register a key another task owns (`handlers_dict` is a flat dict; import-order
   nondeterminism makes duplicate keys silently wrong).
2. **No edits to `reasoning/refine/_upstream.py`.** The vendored dispatcher and the
   initial 14 handlers stay byte-diff-clean against pinned SymPy. Fixes to vendored
   handlers are new modules that override `handlers_dict[key]`, importing the vendored
   function for delegation where useful.
3. **New files only.** A task creates `reasoning/refine/handlers/<task>.py` and
   `reasoning/tests/test_refine_<task>.py`. No shared-file edits, so concurrent
   branches never conflict.
4. **Reference ask is the correctness oracle.** Handler logic is validated with
   `ask` bound to `sympy.assumptions.ask.ask` (harness fixture); the local
   `reasoning.satask` binding is the integration oracle and may xfail.
   A task is *implemented correctly* when it passes under reference ask; it is
   *integrated* when its local-ask tests flip from strict xfail to pass.
5. **Every rule needs a negative case and a `None`-safety case.** `ask` returning
   `None` must leave the expression unchanged, never raise (see `refine_Pow`'s
   `expr.exp` crash and `refine_sin_cos`'s `Integer` bug, report §3.1/§3.4).
6. **Merge gate:** `pytest reasoning/tests`, `mypy`, and the verifier's verdict.
   `validation/test_refine.py` failures are recorded, not gating.

## 2. Integration architecture (Phase 0 scaffold)

```
reasoning/refine/
  __init__.py        # public API + handler auto-discovery
  _upstream.py       # dumped from reasoning/refine.py: dispatcher, 14 handlers,
                     #   local ask, handlers_dict
  handlers/
    __init__.py      # empty
    _trig.py         # shared pi/2 parser (task SCAFFOLD-TRIGHELPER)
    <task>.py        # one file per task, registers its key
reasoning/tests/
  refine_harness.py  # fixtures/helpers (task SCAFFOLD-HARNESS)
  test_refine_<task>.py
```

`__init__.py`:

```python
from ._upstream import ask, handlers_dict, refine, refine_sin_cos  # public API

def _load_handlers() -> None:
    import importlib, pkgutil
    package = importlib.import_module(__name__ + ".handlers")
    for info in pkgutil.iter_modules(package.__path__):
        if not info.name.startswith("_"):
            importlib.import_module(f"{package.__name__}.{info.name}")

_load_handlers()
```

Handler registration idiom (in a task file):

```python
from .. import _upstream
from .._upstream import handlers_dict

def refine_tan(expr: Basic, assumptions: Boolean | bool) -> Basic | None:
    from .._trig import split_pi_half   # task-specific imports allowed
    if _upstream.ask(Q.zero(expr.args[0]), assumptions):
        return S.Zero
    ...

handlers_dict['tan'] = refine_tan
```

**Ask-call rule:** new handlers must call `_upstream.ask(...)` through the module
attribute, never `from .._upstream import ask`. A `from` import binds the original
function object, so the harness's monkeypatch would not reach the handler.

The harness provides:

- `reference_ask` fixture: monkeypatches `reasoning.refine._upstream.ask` (the
  module global that both vendored and new handlers call) to
  `sympy.assumptions.ask.ask`.
- `assert_refines_like_sympy(expr, assumptions)`: under `reference_ask`, compares
  `reasoning.refine.refine` with `sympy.assumptions.refine.refine`.
- `stub_ask(mapping)` / `recording_ask`: scripted True/False/None answers and a
  `(proposition, assumptions, result)` log, for `None`-safety and blocker lists.
- `assert_refinement_valid(expr, assumptions, refined, samples=25)`: draws numeric
  values satisfying the assumptions (integer/positive/even/real/imaginary symbols),
  substitutes into both expressions, and requires agreement (with explicit handling
  for `zoo`/`nan` and branch cuts; uses `sympy.simplify` of the difference as a
  fallback). This oracle is independent of `ask`.

## 3. Phase 0 tasks (serial, land before any handler)

The port is already committed on `feature/refine` as `cf821f7`, so the only
orchestrator-side base step is to record that sha (or tag it) and fork every task
branch from it. The pre-existing `agent/2a-add-mul-pow` and
`agent/2b-elementary-functions` branches are the sources for C-2A/C-2B in §5.

| ID | deliverable | verifier focus |
|---|---|---|
| SCAFFOLD-BASE | Record the base sha `cf821f7` (tag or orchestrator log); all task branches fork from it and `feature/refine` stays the integration target | branch/pointers consistent; no task branched from a moving ref |
| SCAFFOLD-PKG | Restructure to §2; public API unchanged; `reasoning/tests/test_refine.py` and `validation/test_refine.py` still collect and pass with the same counts | vendor diff of `_upstream.py` vs pinned shows only the known header/annotation/return-`None` changes; no behavior change; auto-discovery has no key collisions |
| SCAFFOLD-HARNESS | `reasoning/tests/refine_harness.py` + `reasoning/tests/conftest.py` fixtures per §2, with self-tests | fixtures restore patch state; oracle catches a deliberately wrong handler; harness itself is mypy-clean |
| SCAFFOLD-TRIGHELPER | `handlers/_trig.py`: extract the `pi/2` coefficient/parity parser from `refine_sin_cos` without editing `_upstream.py` | parser unit tests (parity known/unknown, non-Add args); `refine_sin_cos` behavior unchanged |

## 4. Phase 1 handler tasks

Every task: create `handlers/<id>.py` + `tests/test_refine_<id>.py`; rules as in the
report §3 for that class; reference-ask fidelity tests must pass; local-ask tests are
marked `@pytest.mark.xfail(strict=True, reason="needs <fact>")` when core-blocked.
"Blocked" column is the local-core status today (from the report).

### Tier A — high value

| ID | key | rules / references | deps | blocked |
|---|---|---|---|---|
| H-MATRIX-TRANSPOSE | `Transpose` | `Q.symmetric(A.T)->A`; port `transpose.py:85`, ask `expr.arg` (report §3.10) | — | closure for exact port; adjusted port works |
| H-MATRIX-INVERSE | `Inverse` | `Q.orthogonal(A**-1)->A.T`, `Q.unitary(A**-1)->A.conjugate()`; port `inverse.py:86`, ask `expr.arg`; upstream `Q.singular` path **raises** — guard | — | closure; adjusted port works |
| H-MATRIX-DET | `Determinant` | `Q.orthogonal->1`, `Q.singular->0`, `Q.unit_triangular->1`; port verbatim `determinant.py:133` | — | no |
| H-MATRIX-MATMUL | `MatMul` | cancel `A.T*A` under `Q.orthogonal`, `A.conjugate()*A` under `Q.unitary`; port `matmul.py:471` | — | no |
| H-LOG | `log` | `log(exp(x))->x` under `Q.real`; `log(x**y)->y*log(x)` under positive/real; `log(1/x)`; product split; branch guards; refs #29131/#29760 | — | no (all probes answer) |
| H-CONJ-BASIC | `conjugate` | real/imag/integer-power rules only; ref #29173 basic half; branch cuts are a separate deferred item | — | basic yes; Mul form needs 2a |
| H-TAN | `tan` | zero/period/pole rules; refs #29324/#29962 | SCAFFOLD-TRIGHELPER | mixed Add shifts need 2a |
| H-COT | `cot` | zero/pole/period rules; ref #29324 | SCAFFOLD-TRIGHELPER | as tan |
| H-SEC-CSC | `sec`, `csc` | `sec(n*pi)`, `csc(n*pi)`, `pi/2` shifts and poles; refs #29948/#29405 (one task, two keys owned together on purpose) | SCAFFOLD-TRIGHELPER | no |
| H-SINC | `sinc` | `sinc(x)/Q.zero(x)->1` | — | no |
| H-HYP-FWD | `sinh`..`csch` (6 keys) | zero values; `x+n*pi*I` periods; refs #30192/#30138 | — | no |
| H-HYP-INV | `asinh`..`acsch` (6 keys) | inverse compositions under direct range assumptions | — | mainly no |
| H-INVTRIG | `asin`, `acos`, `atan` | compositions with `Q.ge`/`Q.le` ranges given directly; no branch-cut guesses | — | range derivation partly blocked |
| H-MIN | `Min` | `Q.ge/Q.le`/`Q.positive`/`Q.zero` selection; refs #29406/#30487 | — | no |
| H-MAX | `Max` | mirror; refs #29406/#30487 | — | no |
| H-FRAC | `frac` | `Q.integer->0`, `frac(x+n)` period; refs #30368/#29744 | — | no |
| H-MOD | `Mod` | integer/positive cases, `Mod(p,1)`; refs #30376/#29743 | — | no |
| H-REM | `Rem` | mirror Mod integer cases | — | no |
| H-FACTORIAL | `factorial` | `Q.zero->1`, nonpositive-integer pole, infinities; ref #29203 | — | no |
| H-BINOMIAL | `binomial` | zero/one `k`, negative `k`, support cases; ref #29213 | — | no |
| H-RF-FF | `RisingFactorial`, `FallingFactorial` | zero/integer cases | — | no |
| H-GAMMA | `gamma` | nonpositive-integer pole only; ref #29203 | — | no |
| H-DIRACDELTA | `DiracDelta` | `Q.nonzero->0` | — | no |
| H-KRONECKERDELTA | `KroneckerDelta` | `Q.eq->1`, `Q.ne->0` (local `Q.ne` from given `Q.eq` is None; document) | — | partly |
| H-POW | `Pow` | **one task owns all Pow fixes:** #29800 nested `(x**a)**b` correctness + drop wrong `abs(base.base)**...`; `Abs(z)**2` under `Q.imaginary` (#30474/#30476); `Pow(E,x)` double-handling (#30248); `sqrt(1/x)` under positive x is the 2a integration case | — | nested/imaginary yes; `sqrt(1/x)` needs 2a |
| H-ABS | `Abs` | zero-arg fix; Add-sign path; refs #29183/#29796 | — | zero yes; Add needs 2a |
| H-SIGN | `sign` | pass `assumptions` through to its `Q.real`/`Q.imaginary` checks; ref #29605 | — | real cases yes; old-assumption symbol cases need 2d |
| H-ARG | `arg` | `Q.imaginary & Q.nonzero -> ±pi/2` (only when sign of `im` is known), zero edge; ref #29409 | — | yes/partly |
| H-SIN-COS | `sin`, `cos` | guard the `Integer` parity factor (PR #29450 `AttributeError`); Add-parity integration xfail for `test_sin_cos` | SCAFFOLD-TRIGHELPER | Add parity needs 2a |
| H-TRACE | `Trace` | `Q.zero(X)->0`; local PR draft `/tmp/opencode/pr-body-trace.md` | — | no |
| H-MATADD | `MatAdd` | drop `Q.zero` terms | — | no |
| H-HADAMARD | `HadamardProduct` | zero factors -> zero matrix | — | no |
| H-MATELEMENT-EXT | `MatrixElement` | override/extension: `Q.zero(X)` and `Q.diagonal(X)` with `i != j` -> 0 | — | direct assumptions yes; element-set closure no |

### Tier B — meaningful but smaller/deferred

| ID | key | note |
|---|---|---|
| H-CONJ-BRANCH | `conjugate` continuation | branch-aware `log`/inverse-trig rules; **research task**, requires external math verification (maintainer found wrong answers in #29173); do not land on reference-ask alone |
| H-ACOT-ASEC-ACSC | `acot`, `asec`, `acsc` | branch cuts are the hard part; defer until H-CONJ-BRANCH math is settled |
| H-ADJOINT | `adjoint` | needs matrix predicate closure (C-2C) |
| H-FACT2 | `factorial2` | low value |
| H-SUBFACT | `subfactorial` | low value |
| H-FIB | `fibonacci`, `lucas`, `harmonic` | low value |
| H-KRONECKER | `KroneckerProduct` | identity/zero-matrix identities; low value |
| H-LEVICIVITA | `LeviCivita` | repeated-index zero; low value |
| H-SINGULARITY | `SingularityFunction` | order/argument cases; low value |
| H-LAMBERTW | `LambertW` | report says not recommended (branch bookkeeping) |
| H-EXPPOLAR | `exp_polar`, `polar_lift`, `principal_branch` | internal multivalued objects; unrealistic |

### Explicit non-goals (do not schedule)

- `Piecewise`, `Relational`/inequalities: `Boolean._eval_refine` + SymPy `ask` route
  already reproduces upstream; fix belongs in `ask`/LRA (report §3.8/§3.11).
- Special functions at large (`erf`, `zeta`, Bessel, hyper, elliptic, ...), sets,
  `Derivative`/`Integral`/`Sum`, number-theory functions: no assumption-driven
  rewrite with plausible value (report §3.7/§3.12).
- Duplicating upstream `_eval_refine` behavior already reachable through SymPy hooks.

## 5. Phase 2 core tasks (run in parallel with Tier A; gate integration xpasses)

| ID | deliverable | note |
|---|---|---|
| C-2A | Land `agent/2a-add-mul-pow` facts (+ tests) on the integration branch | fixes `test_pow1`, `test_sin_cos`; prerequisite for H-POW/H-ABS/H-CONJ integration tests |
| C-2B | Land `agent/2b-elementary-functions` facts | supplies `Q.real(exp(x))` etc. used by H-LOG/H-CONJ |
| C-2C | Matrix predicate closure (`symmetric(A.T)`, `orthogonal(A**-1)`, `integer_elements -> integer(X[i,j])`, ...) | lets the verbatim matrix ports replace the adjusted versions; large |
| C-2D | Old-assumption symbol bridge (decision needed: repo policy vs last `test_sign` asserts) | conflicts with `tools/check_old_assumptions.py` intent; default skip |

## 6. Task-card template (orchestrator expands one per row)

```
TASK <ID>
Base: feature/refine @ cf821f7 (or the recorded scaffold sha)
Worktree: /home/tilo/reasoning-handlers/<ID>   Branch: refine/<ID>
Goal: implement <key(s)> rules from report §3.<n> (quote exact rules/examples).
Files you may create:
  reasoning/refine/handlers/<ID>.py
  reasoning/tests/test_refine_<ID>.py
Files you must not modify: everything else, especially _upstream.py and any other
  handlers/ or tests/ file.
Required tests:
  1. reference-ask fidelity: each rule positive case, compared to SymPy refine where
     an upstream handler exists, else to the quoted expected output
  2. negative case per rule (assumptions not met -> unchanged)
  3. None-safety: stub ask returning None per query -> unchanged, no exception
  4. numeric equivalence via assert_refinement_valid
  5. local-ask integration: expected today, or strict xfail naming the missing fact
Definition of done: mypy clean; `pytest reasoning/tests/test_refine_<ID>.py` green
  (xfails strict); `pytest reasoning/tests` green; commit on refine/<ID> only the two
  new files, message `Add refine handler for <key> (<refs>)`; report the exact
  commands run and their output.
Report back: branch, commit sha, files, test counts, local-ask xfail list with the
  exact missing ask queries.
```

## 7. Verifier rubric (one fresh-context verifier per task)

The verifier must not read the implementer's chat/notes; it receives the task card and
the branch, creates its own worktree, and checks:

1. **Scope:** diff contains exactly the two allowed files; no `_upstream.py` or other
   task edits; commit message matches; no duplicate registry key (grep
   `handlers_dict[`).
2. **Fidelity:** reruns the task's tests; additionally diffs handler behavior against
   the referenced upstream PR/output for at least the quoted examples, under
   reference ask. Divergence without a documented reason = FAIL.
3. **Soundness (adversarial):** writes its own cases, including boundary values
   (`0`, `±1`, `±pi/2`, `±pi`, `oo`, `-oo`, `zoo`, `nan`, non-real), branch cuts for
   trig/inverse/conjugate/log, and variables violating the assumptions. Numeric
   sampling per the harness oracle. Any wrong refinement on a satisfiable assumption
   set = FAIL, with the counterexample.
4. **Robustness:** stub `ask` with a scripted sequence mixing `None`, `True`,
   `False`; no exception and no change when unknown. Also verifies the handler cannot
   recurse forever (result dispatched again).
5. **Coverage discipline:** every rule has positive, negative, and None-safety tests;
   xfails are `strict=True` and name the prerequisite (`needs 2a: Q.real(x**-1)`).
6. **Integration:** `pytest reasoning/tests`, `mypy`, and
   `pytest validation/test_refine.py` before/after; reports the delta. Explains any
   xfail that unexpectedly passes (flipped prerequisite) or any new failure.
7. **Verdict:** PASS/FAIL + evidence (commands, outputs, counterexamples) + residual
   risks. On FAIL, the orchestrator returns the verdict to the implementer for one
   revision; a second FAIL marks the task blocked and the branch is not merged.

The verifier may keep adversarial tests it wrote if it commits them to the task
branch under `reasoning/tests/test_refine_<ID>_verifier.py` (a new file, consistent
with the independence rule) — the implementer's commit is not amended.

## 8. Orchestration protocol

1. **Phase 0** runs serially (one agent per task, verifier each). SCAFFOLD-BASE is
   the orchestrator's own step. `feature/refine` (currently `cf821f7`) stays checked
   out in `/home/tilo/reasoning-refine`; the scaffold tasks land there first.
2. **Phase 1:** spawn up to `N` implementers concurrently (start `N=4`; each task runs
   mypy/pytest, so higher N contends for CPU). Every task branches from the scaffold
   commit on `feature/refine`, so no task depends on another except the `deps` column
   (`SCAFFOLD-*`, and the trig-helper dependency).
3. **Verify → merge loop:** as each task clears its verifier, the orchestrator merges
   `refine/<ID>` back into `feature/refine` with `--no-ff`, then runs
   `pytest reasoning/tests` on the merged result. Because tasks only add files,
   merge conflicts are a protocol violation: reject the branch and re-run the task.
4. **Phase 2** (C-2A..C-2D) runs alongside; merge C-2A/C-2B early to flip the
   integration xfails; C-2C last (largest). When a fact lands, the orchestrator
   re-runs Tier A local-ask tests; newly passing xfails become regular tests (or, if
   an xfail unexpectedly passes while facts are absent, that is a verifier FAIL
   condition in step 7.6 — the handler is over-firing).
5. **Final integration verifier** (fresh context, whole branch): full
   `pytest reasoning/tests`, `mypy`, `pytest validation/test_refine.py`,
   `validation/compare_backends.py --suite validation/test_refine.py`, plus re-running
   every task's verifier file. Produces the final report: per-key status, validation
   before/after, remaining xfails with the missing `ask` queries, and the deferred
   list from §4.
6. **Failure policy:** one revision per verifier FAIL, then blocked; blocked tasks do
   not stall the merge train. Anything whose rules require external math
   verification (H-CONJ-BRANCH, H-ACOT-ASEC-ACSC) is gated on a human sign-off and
   must not be merged on test evidence alone.

## 9. Definition of done

- Every Tier A key in `handlers_dict` with a Task Card, verifier PASS, and tests in
  `reasoning/tests/`.
- `pytest reasoning/tests` green with strict xfails; `mypy` clean; `_upstream.py`
  diff vs pinned SymPy unchanged from the scaffold commit.
- `validation/test_refine.py` count recorded before/after; every remaining failure
  has a named missing fact and a corresponding Tier A xfail.
- Deferred/non-goal lists in §4 recorded in the final report so they are not
  re-attempted accidentally.
