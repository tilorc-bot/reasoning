# Agent report: LRA theory-solver prototype for the reasoning core

- **Date:** 2026-09-21
- **Status:** prototype implemented and measured on branch `investigate/lra-theory`
  (not pushed); no behavior change unless `satask(..., use_lra_theory=True)` is
  passed
- **Scope:** the #30537 four-method theory protocol and an opt-in linear real
  arithmetic theory over `LocalQ.eq/gt/lt/ge/le`, the preprocessing layer that
  models `lra_preprocess.py`, and what the validation harness shows
- **Read this if:** you are deciding whether to land a theory layer in
  `reasoning/`, extend the LRA fragment, or wire relation bridging into
  `satask`
- **Stale after:** changes to `reasoning/solver.py`, `reasoning/lra.py`,
  `reasoning/lra_adapter.py`, `reasoning/satask.py`, or the pinned SymPy
- **TL;DR:** the #30537 protocol ports cleanly: 135 unit tests pass (up from
  74), mypy strict is clean, and `test_query.py` gains exactly one test
  (`test_issue_28127`, 38→39 passed, no regressions). A 528-query randomized
  differential against SymPy's `ask` found zero wrong answers; the opt-in mode
  answers 146 queries `ask` leaves as `None`. Overhead is within noise when
  LRA is off and 1.03–1.43x on relational queries that previously returned
  `None`. `test_relational` (the other remaining relational failure) needs
  `Q.eq(x, 0) <=> Q.zero(x)`-style bridging, not LRA.

## 1. What was built

Four new modules plus wiring:

| File | Contents |
|---|---|
| `reasoning/theory.py` | `TheorySolver` protocol: `assert_lit`, `check`, `push_level`, `pop_level` |
| `reasoning/lra.py` | SymPy-free dual-simplex LRA solver (Port of `lra_theory.py`) over `(terms, constant, strict, equality)` records with `Fraction` arithmetic, terms are opaque hashable keys |
| `reasoning/lra_adapter.py` | Interprets `LocalQ.eq/gt/lt/ge/le` atoms: constant folding, rational validation, nan/imaginary/infinity rejection, Add/Mul splitting, slack terms |
| `reasoning/tests/{test_lra,test_theory,test_lra_adapter}.py` | 61 new tests |

Wiring is deliberately small (`git diff --stat` on tracked files: 118 lines in
three files):

- `solver.py`: keyword-only `theory_solvers=()`, `assert_lit` in
  `_assign_literal`, `push/pop_level` in `_create_level`/`_undo`, `check()` at
  the model-yield, `propagate()` no longer claims `SATISFIABLE` with theories
  attached, and the assumption loop uses `_create_level` instead of a bare
  `levels.append` so theories see assumption levels.
- `engine.py`: `ReasoningEngine(factbase, theory_solvers=())`.
- `satask.py`: `use_lra_theory: bool = False`; builds the theory after the
  query literal exists, adds the adapter's unit conflicts (e.g. `Q.gt(2, 1)`),
  and passes the solver to the engine.

The fixed `#30537` head issues are respected: `assert_lit` breaks on the first
theory conflict, duplicate theories are rejected, and the swallowed-conflict
path is handled (see §4).

## 2. Why the core stays SymPy-free

The dual-simplex tableau only ever combines *coefficients*; term keys are
never evaluated. Passing `(expression, Fraction)` pairs with the expression as
an opaque key therefore keeps `lra.py` free of SymPy, and the same solver
would serve any other linear domain. `lra_adapter.py` is the only new
SymPy-importing module.

Two deliberate differences from `sympy.logic.algorithms.lra_theory`:

- **No global nonlinearity rejection.** Upstream raises `UnhandledInput` if
  two distinct term keys share free symbols (e.g. `x + y` and `x`). Treating
  distinct terms as independent variables is a relaxation: any real
  assignment still evaluates every term, so a conflict over the relaxed terms
  is a valid real conflict, and the engine can only return `True`/`False` from
  theory-UNSAT. The cost is incompleteness, not soundness, and mixed formulas
  keep working. `lra_adapter` skips atoms it cannot parse instead of disabling
  the theory.
- **No matrix code.** `_rref` is a 30-line exact-`Fraction` Gauss-Jordan; the
  testing-mode invariants are reimplemented without `Matrix`.

## 3. Soundness argument for the protocol

- `check()` conflicts become learned clauses; the clause is the negation of
  asserted literals, so adding it can only remove assignments the theory
  rejects.
- A relaxation (independent terms, skipped atoms, unhandled negated
  equalities) can only add models. `ReasoningEngine.ask` proves `True` by
  UNSAT of *assumptions + negation of the query* and `False` by UNSAT of
  *assumptions + query*; UNSAT under a relaxation implies UNSAT under the real
  theory. Base models may be relaxed, but they only choose the polarity to
  test.
- `push_level`/`pop_level` bracket every decision and assumption level, so no
  bound outlives its level.

The randomized differential (§5) is the empirical check on this argument.

## 4. Integration findings

- **Assumption conflicts were not swallowed here only because
  `_assign_literal` always returned `None`.** Making the return value live
  exposed that `_find_model`'s assumption loop ignored it and used a bare
  `levels.append`. Both are fixed and covered by
  `test_theory_conflict_while_asserting_an_assumption_is_not_swallowed`, the
  regression case tilorc-bot identified on #30537.
- **Root-level theory conflicts at model time need care.** A theory conflict
  whose explanation consists only of root/assumption literals cannot be
  resolved by flipping; the first version of the backtrack loop could reach
  the base level and try to flip decision `0`. The loop now returns UNSAT as
  soon as the blamed literals are all at or below `assumption_level`
  (`test_root_theory_conflict_found_at_the_model_check`,
  `test_root_theory_conflict_with_an_assumption_level`).
- **No theory propagation.** `check()` runs only once all variables are
  assigned. Conflicts that only appear through a slack variable surface at
  `check()`, not `assert_lit` (e.g. `x >= 1 & y >= 1 & x + y <= 0`); that is
  handled, but relational queries still search more than a propagating theory
  would. `_simplify`/`_pure_literal` is the hook for a future
  `theory_prop`.
- **Matrix relations must be rejected, not interpreted.** `MatrixExpr` is an
  `Expr`, so the scalar checks pass, but `A - A` is a `ZeroMatrix` and
  `Eq(ZeroMatrix, 0)` is `False`, which silently turned the true
  `Q.eq(A, A)` into a false answer. The adapter now skips any relation with a
  matrix argument (`test_matrix_relations_are_skipped`); upstream rejects
  these too.
- **`var_settings` seeds would bypass the theory**, so non-empty seeds with a
  theory raise `NotImplementedError` rather than run unsound.

## 5. Measurements

Unit and correctness gates:

- `python -m pytest reasoning/tests`: **135 passed, 1 xfailed** (was 74 + 1).
- `python -m mypy reasoning`: clean, strict.
- `python -m benchmarks.satask --repeat 25` against the pre-change worktree:
  all five cases within 0.99–1.01x.
- Random differential: 600 generated queries over `x`, `y`, `x + y`,
  `2*x - y`; 528 had consistent assumptions and were comparable — **0
  disagreements with SymPy `ask`**, while the LRA mode answered 146 queries
  `ask` returned `None` for; the other 72 assumption sets are LRA-inconsistent
  and raise as `satask` documents.

Overhead (median of 50 runs, one process):

| Case | plain | LRA | ratio |
|---|---:|---:|---:|
| `Q.real(x)` under `Q.positive(x)` | 0.395 ms | 0.395 ms | 1.00x |
| nested `x*(x+y)` | 2.881 ms | 2.898 ms | 1.01x |
| `Q.gt(x, 0)` under `Q.gt(x, 1)` | 1.675 ms → `None` | 1.867 ms → `True` | 1.11x |
| `Q.gt(y, x)` under `Q.lt(x, y)` | 0.966 ms → `None` | 1.117 ms → `True` | 1.16x |
| `Q.le(x, y)` under `Q.gt(x, y)` | 0.973 ms → `None` | 1.393 ms → `False` | 1.43x |
| inconsistent relations | 1.727 ms → `None` | 1.441 ms → raises | 0.83x |

Validation (`validation/test_query.py` + `test_matrices.py`, pinned SymPy),
with `use_lra_theory=True` forced only for the query suite:

- Baseline and current with LRA off: **40 passed / 54 failed / 8 xfailed / 2
  xpassed** both — no regressions from the solver changes.
- LRA on: **41 passed / 53 failed**; the single flip is
  `test_issue_28127` (orientation/negation of `Q.lt/le/gt/ge`), and no test
  regressed. `test_relational` still fails: it needs `Q.eq(x,0) <=> Q.zero(x)`
  and `Q.ne`/`Q.nonzero` bridging, which is handler/fact work, not LRA.

## 6. Limitations

- `Q.ne` and negated equalities are not constraints (disjunctions); the
  adapter skips them, so `x != y` contributes nothing.
- No bridging between relations and sign predicates
  (`Q.positive <-> Q.gt(x, 0)`, `Q.zero <-> Q.eq(x, 0)`). `ask` gets some of
  this from handlers; `satask` does not, and LRA does not either.
- Non-rational constants (`Float`, `pi`, ...), nan, imaginary and infinite
  arguments cause the atom to be skipped.
- Strict inequalities use the delta-rational encoding from upstream; there is
  no check that a returned assignment is "human" (assignments can carry a
  negative delta, which is the intended semantics).

## 7. Recommendation

1. **Land the protocol and the opt-in LRA mode.** They are self-contained, add
   no default-path cost, and the randomized differential found no wrong
   answers. Keeping `use_lra_theory=False` by default avoids behavior changes
   while the fragment grows.
2. **Auto-enable only after deciding the validation policy.** Forcing the
   theory on for the pinned suite is +1 test with no regressions *today*, but
   it changes answers on relation-bearing queries and deserves an explicit
   decision. The `ReasoningEngine` hook is the natural place for an
   `use_lra_theory`-style option on the SymPy side.
3. **Add theory propagation next** if relational search cost matters: consult
  the theory in `_simplify` and skip models earlier. The current bottleneck is
  that all theory pruning happens at full assignments.
4. **Bridging facts are the bigger validation win.** `test_relational` (and
   the `Q.positive`-style directions `ask` answers) need relation/sign
   equivalences in `sympy_adapter`/`numberfacts`; that is independent of the
   theory layer and helps the non-LRA path too.
5. **Do not port `facts2.py`/forward chaining**; the report's earlier
   sequencing still holds.

## 8. Sources

- `TiloRC/sympy` #30537 (`theory-registration`), #30538 (`rf-from_encoded`),
  #30533; local references under `/home/tilo/satask-lra-fallback` and
  `/home/tilo/orion` cited by
  `agent-reports/2026-09-21-theory-solver-research.md`.
- Implementation: `reasoning/theory.py`, `reasoning/lra.py`,
  `reasoning/lra_adapter.py`, tests under `reasoning/tests/`.
