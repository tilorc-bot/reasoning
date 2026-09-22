# Agent report: SymPy theory-solver research (#27835, #30537, #30538 and surroundings)

- **Date:** 2026-09-21
- **Update (2026-09-22):** the suggested sequencing below was carried out as a
  prototype; the opt-in protocol + LRA work is merged into `main` at `5bf789e`.
  See `agent-reports/2026-09-21-lra-theory-prototype.md` and section 7a.
- **Status:** research only when written; the LRA follow-up now exists on `main`
- **Scope:** the three anchor PRs, their local branch equivalents under `/home/tilo`,
  the merged SAT/assumptions work they build on, and what it means for
  `/home/tilo/reasoning`
- **Read this if:** you are deciding whether to revive #27835, finish #30537/#30538,
  or add a theory layer to the `reasoning` core
- **Stale after:** any push to `TiloRC/sympy:{forward-theory,theory-registration,rf-from_encoded}`,
  changes to `sympy/logic/algorithms/dpll2.py`, `lra_theory.py`,
  `sympy/assumptions/reasoning_engine.py` on master, or changes to
  `reasoning/{theory,lra,lra_adapter,solver,satask}.py` in this repo
- **TL;DR:** #30538 is a green, self-contained refactor that enables the #30533 plan
  (move LRA input interpretation out of `logic/`); #30537 defines the right 4-method
  `TheorySolver` protocol and fixes a real theory-conflict bug, but **its head commit
  is a syntax error and CI is red**. #27835 (the unary-predicate forward-chaining
  theory) is a stale draft with debug leftovers (`if False:` disabling known facts)
  and has been overtaken by the merged incremental route (#30201/#30326/#30265/#30518).
  The `reasoning` core has no theory support at all; the clean insertion points are
  `solver.py:611` (`_assign_literal`), `solver.py:668/674` (`_create_level`/`_undo`),
  `solver.py:715` (`_simplify`), the model-yield at `solver.py:229`, and
  `ClauseDB.symbols` for literal→predicate decoding.

## 1. Anchor PRs at a glance

| PR | State | Head | Checks | What it is |
|---|---|---|---|---|
| [#27835](https://github.com/sympy/sympy/pull/27835) | open **draft**, last commit 2025-08-21 | `TiloRC/sympy:forward-theory` = `6197a018` | n/a (draft) | SMT theory solver for unary predicates; new `facts2.py`, `forward_chaining_theory.py`, `rules_engine.py`; ~2x `ask`, removes composite predicates |
| [#30537](https://github.com/sympy/sympy/pull/30537) | open, updated 2026-09-21 | `theory-registration` = `1834482b` | **failing**: Test groups 1-4 + Code Quality | Generic `TheorySolver` protocol; `SATSolver(theory_solvers=[...])` replaces hardcoded `lra_theory` |
| [#30538](https://github.com/sympy/sympy/pull/30538) | open, updated 2026-09-20 | `rf-from_encoded` = `63c3134a` | **all green** (45 runs) | Pure refactor of `LRASolver.from_encoded_cnf` into `_preprocess_lra_constraints` + `_build_lra_solver` + `_build_tableau` |

## 2. #27835 — forward-chaining theory for unary predicates

Design (branch tip verified byte-identical to the downloaded diff and to unreachable
objects in `/home/tilo/satask-lra-fallback/.git`):

- `sympy/assumptions/facts2.py` (232 lines) compiles `get_number_facts()` plus six
  extra rules and the composite-predicate definitions into implication dictionaries,
  takes the transitive closure, and encodes each predicate's direct implications as
  Python-int bitsets (`pred_id_to_bitvec`, `direct_dict_bitset`,
  `implication_counts_by_lit`, `fc_lit_to_direct_implications`).
- `sympy/logic/algorithms/forward_chaining_theory.py` (356 lines) defines `FCSolver`
  with `assert_lit(literal, state)` (returns `(False, 2-literal conflict clause)` on an
  immediate conflict), `check(initial_literals)` (only runs `RulesEngine.check` when an
  expression has more than two independent literals — `find_independent_subset`),
  `theory_prop` (implemented but disabled by default because it "makes everything a
  lot slower"), and `get_heuristic_multipliers` feeding theory information into VSIDS.
- `sympy/logic/algorithms/rules_engine.py` (237 lines) implements the actual chaining
  (`trigger_rules`, `trigger`, `_check_by_facts`, `_check_by_rules`) and returns
  explanation clauses.
- `dpll2.py` grows an `fc_theory` argument, `_theory_prop_queue`, `Level.fc_state`,
  and a `_theory_prop` loop; `inference.py` grows `_satisfiable(..., use_sympy_theory=True)`;
  `satask.check_satisfiability` uses it; `CNF.to_CNF` stops substituting composite
  predicates; `facts.py` gains `Equivalent(Q.noninteger(x), Q.real(x) & ~Q.integer(x))`.

Claimed results: `test_query` ~15 s → ~8 s; `ask(Q.negative(x), ~Q.positive(x) & Q.real(x))`
~1.4 ms → ~1 ms; `satask(...)` ~650 µs → ~400 µs; query time no longer exponential in
variable count (fixes #27467, though #27492 actually closed that issue).

Why it is stalled / not mergeable as-is:

- Still a **draft**, no commits since 2025-08-21, no formal review; asmeurer only
  commented on timing methodology.
- Debug leftovers on the tip: `satask.py` `if False:` disables `use_known_facts`
  entirely; `FCSolver.__init__` has `if True:` with a `# disable when finished`
  comment; `CNF.to_CNF` has the composite-predicate call commented out; commented-out
  test bodies in `test_fc_theory.py`/`test_inference.py`.
- #27467 was fixed independently by #27492 (merged 2025-09-22), removing urgency.
- The `find_independent_subset` idea survives in discussion (#30121) as the way to
  answer `None` queries without full solves.

## 3. #30537 — modular theory solvers (and a broken head)

Content of the current diff/raw head (`1834482b`):

- New protocol in `dpll2.py`:
  `assert_lit(int) -> (bool, list[int]) | None`, `check() -> (bool, Any) | None`,
  `push_level()`, `pop_level()`.
- `SATSolver.__init__(clauses, variables, symbols=None, ..., *, theory_solvers=None)`;
  `var_settings` is **removed** from the constructor and starts empty; `dpll_satisfiable`
  now appends `from_encoded_cnf` conflicts with `solver.clause(clause)` instead of
  concatenating them into the clause list; `reasoning_engine.py` drops its `set()` arg.
- `_assign_literal` calls every theory's `assert_lit` and returns the last conflict;
  `_create_level`/`_undo` call `push_level`/`pop_level`; the model-yield loop calls
  `check()` and breaks on the first conflict; `propagate()` will not report
  `SATISFIABLE` while any theory solver is registered; VSIDS gets no theory input.
- `_find_model` assumption handling is now conflict-aware (create level, `_assign_literal`,
  on conflict set `is_unsatisfied` and add the learned clause). tilorc-bot's review
  correctly identifies this as a **real master bug fix**: a theory conflict discovered
  while assigning an assumption literal was previously swallowed, so
  `Q.lt(x,0) & (Q.gt(x,1) | Q.lt(x,2))` + `assume(Q.gt(x,1))` reported SAT. No regression
  test for that path was added (the new test only covers a toy `ExcludeLiteral` theory).
- Review state: `register_theory_solver()` was removed in response to JosephMehdiyev;
  smichr suggested docstring wording; JosephMehdiyev asked for `class LRASolver(TheorySolver)`
  and `pop_level(n)`, both deferred by TiloRC to keep the PR small and avoid conflicts
  with #30538.

**Blocking defect (verified):** commit `1834482` ("Fix mypy") deleted the condition
line but left its body:

```python
self.theory_solvers = list(theory_solvers) if theory_solvers is not None else []
    raise ValueError("Duplicate theory solver")   # IndentationError
```

The raw file at the head SHA does not parse (`ast.parse` fails), and the GitHub checks
for that commit show Test groups 1-4 and Code Quality failing. The PR cannot be merged
until this is fixed (restore
`if len({id(theory) for theory in self.theory_solvers}) != len(self.theory_solvers):`).
Other open points: `_assign_literal` neither breaks after the first theory conflict nor
records which theory conflicted (last conflict wins, later theories still receive the
literal); a theory returning `(True, model)` is overwritten by later theories.

## 4. #30538 — `from_encoded_cnf` refactor (green)

- `LRASolver.from_encoded_cnf` becomes
  `_build_lra_solver(_preprocess_lra_constraints(encoded_cnf, testing_mode), testing_mode)`.
- New IR documented at module level: `_Clause = list[int]`,
  `_LinearTerms = tuple[tuple[Expr, Expr], ...]`, and
  `_LRAConstraint = tuple[_LinearTerms, Expr, bool, bool]` representing
  `sum(coeff*var) + constant <= | < | == 0`, with `>=`/`>` normalized by negation.
- `_evaluate_trivial_predicate` returns `True/False` for constant predicates (turned
  into unit conflict clauses) or `None`; it also carries the nan/imaginary/infinity
  validation and the `AppliedBinaryRelation` narrowing assert for mypy.
- `_split_constant(expr, Add|Mul)` consolidates the old `_sep_const_terms`/`_sep_const_coeff`.
- `_build_lra_solver` builds slack variables keyed by the canonical `terms` tuple,
  then calls `_build_tableau`, which fills the matrix directly from coefficients —
  `linear_eq_to_matrix` and sympy-expression rebuilding are gone from the logic layer.
- `s_subs` (expression→Dummy) is replaced by `slack_rows` `(terms, slack)` pairs;
  `test_lra_theory` reconstructs the old mapping via a `slack_map` helper.
- Reviewer benchmark: `time_from_encoded_cnf` 0.61-0.70x, `time_unknown` 0.81x,
  `time_zero_from_bounds` 0.79x, everything else within noise.
- Open review questions: duplicate asserts, why `Q.ne` is forbidden (TiloRC no longer
  remembers; "I think because it's a disjunction of inequalities"), whether negated
  equalities are handled correctly, and removal of the old bare-`Predicate` →
  `Predicate(Dummy)` conversion (now a `ValueError`). The nonlinearity check is
  equivalent but now keyed per variable term.

## 5. The merged incremental route (what actually landed)

The real progress is a chain of small PRs that #30537/#30538 build on:

- #29961 "lra_theory: Improve Preprocessing" — merged 2026-07-10.
- #30201 "logic: add IPASIR style interface to SATSolver (part 1)" — merged 2026-08-21
  (`propagate`, `fixed`, `solve`, `val`).
- #30326 "logic: add `assume()` to `dpll2`" — merged 2026-08-23.
- #30265 "assumptions: implement early return in `satask`" — merged 2026-09-01; closes
  #30121 and the #30155/#30206/#30314 sub-issues.
- #30518 "assumptions: Add interface for sat solver" (`ReasoningEngine`) — merged
  2026-09-17. `create_query(prop, _prop)` guards the query with a selector, calls
  `propagate()` and raises on UNSAT; `lookup`/`fixed`/`ask_query` drive incremental
  queries. This is the object all the local LRA branches extend.

Related open/draft work:

- [#30533](https://github.com/sympy/sympy/issues/30533) (LRASolver not modular enough):
  move preprocessing/validation out of `logic/` into assumptions; remove
  `Predicate/AppliedPredicate/Q/Dummy/Add/Mul` imports from `lra_theory.py`; minimal
  constraint object (`terms`, `constant`, `strict`); one entry point; fold
  `lra_satask` into `satask`.
- [#28147](https://github.com/sympy/sympy/issues/28147) (combine `lra_satask` and `satask`):
  asmeurer wants `satask` restructured like a theory solver; TiloRC's plan is an
  "inequalities theory" that only feeds LRA once realness of the sides is established,
  plus `real(x) <-> (x > 2 | x <= 2)` to bridge to other predicates. Open.
- [#30415](https://github.com/sympy/sympy/pull/30415) (more inequality queries, draft):
  handles expressions assumed real via `Q.real`/real-implying predicates using
  root-level inference; mixed perf (2-4x faster on chains, up to 1.86x slower on
  undecided queries; `from_encoded_cnf` is built twice). TiloRC paused it pending the
  #30533 refactor.
- EUF: #28160 closed (draft) and continued in #28311 ("please take over", dormant);
  #30010 and #30327 are open drafts. TiloRC's review guidance: implement `EUFSolver`
  with `assert_lit`/`check`, defer cross-predicate fact propagation until #27835 lands.
- Protocol debate: #30098 proposes a CaDiCaL/IPASIR-UP-style interface
  (`notify_assignment`, `notify_new_decision_level`, `notify_backtrack`, `check_model`,
  `decide`, `propagate`, `provide_reason`, `has_clause`, `add_clause`) vs the simpler
  `assert_lit`/`check` of #30537; #30119 (draft) would deprecate `use_lra_theory`.
  JosephMehdiyev's own conclusion: implement EUF first, then design the abstract class.
- tilorc-bot PRs: [#31](https://github.com/tilorc-bot/sympy/pull/31) is the big AI change
  #30537/#30538 were extracted from; [#32](https://github.com/tilorc-bot/sympy/pull/32)
  moves LRA preprocessing into assumptions with `LRASolver.register_constraint` and a
  lazily built tableau; [#39](https://github.com/tilorc-bot/sympy/pull/39) rewrites LRA
  literals before CNF encoding. All open; local equivalents exist under
  `/home/tilo/orion` and `/home/tilo/satask-lra-*` (see §6).

## 6. Local branches worth knowing (all clean unless noted)

- `forward-theory` itself has **no local ref**; its objects are unreachable in
  `/home/tilo/satask-lra-fallback/.git` at `6197a018`, byte-identical to the remote.
- `/home/tilo/lra_theory-rf` (`lra-review` = old `f0afaf8` + local commit) is behind
  the live #30537/#30538 heads.
- `/home/tilo/satask-lra-fallback` (detached at `9a90f3e`, the #30415 head) has the
  three design plans: `PLAN-fallback-and-real-propagation.md`,
  `PLAN-reasoning-engine-lra-and-refactor.md`, `PLAN-remove-lra-from-encoded-cnf.md`.
- `lra-registration`/`refactor-theory-registration` (`/home/tilo/lra_theory-rf`) are the
  local version of tilorc-bot #32: `preprocess_lra_constraints`/`create_lra_solver` in
  `lra_satask.py`, `LRASolver.register_constraint(literal, terms, constant, strict=,
  equality=)`, lazy `_initialize()`, `from_encoded_cnf` removed.
- `/home/tilo/orion/lra-preprocess-work` consolidates the atom interpretation into
  `sympy/assumptions/lra_preprocess.py` with a frozen `LRAConstraint` dataclass;
  `/home/tilo/orion/lra-constraint-pr` makes `LRAConstraint` an immutable tuple
  normalized to a single upper bound.
- `/home/tilo/satask-wt-*` implement the `ReasoningEngine(use_lra_theory=True)` mode and
  the SAT-first/LRA-fallback in `satask` (all expressions must be provably real via
  root-level `lookup(Q.real)` or `is_real`; `UnhandledInput -> None`), plus
  `Q.real`-implying facts for `nonnegative/nonpositive/nonzero/integer`.

## 7. What this means for `/home/tilo/reasoning`

The core is purely propositional: relations (`LocalQ.eq/ne/gt/lt/ge/le`) are opaque
atoms (`sympy_adapter.py:90-93`), no order/arithmetic axioms exist, and `solver.py` is
the extracted `dpll2` with an IPASIR API. It is therefore a near-perfect host for the
#30537 protocol, and the Rust work already added a `solver_class` hook on
`feature/rust-core` (not on `main`).

Concrete insertion points (from the current tree):

| Need | Location |
|---|---|
| Theory construction/DI | `engine.py:6,23` (`SATSolver(self._clauses, variables, set())`) |
| assert / immediate conflict | `solver.py:611` `_assign_literal` already returns `list[int] | None`; callers at `solver.py:249-252,752-755` |
| push/pop | `solver.py:668` `_create_level`, `solver.py:674` `_undo` |
| theory propagation | `solver.py:715` `_simplify`, stub `_pure_literal` at `solver.py:763` |
| full-assignment check | model-yield at `solver.py:229`, root check in `propagate()` at `solver.py:324` |
| literal → predicate | `clauses.py:29` `symbols`, `clauses.py:26-28` `encoding`; aux vars are `clauses.py:55-59` |

Suggested sequencing (mirrors upstream, cheapest first):

1. Port the #30537 4-method protocol (fixing the `break`-on-first-conflict and
   duplicate-detection issues), and add an LRA theory over `LocalQ.gt/lt/ge/le/eq`
   with an assumptions-side preprocessing layer modeled on `lra_preprocess.py`
   (`LRAConstraint` IR + conflict unit clauses for constant predicates). Keep the core
   SymPy-free by passing `(terms, constant, strict, equality)` records, not
   `AppliedPredicate`s.
2. Use the theory only when the validation harness shows the two remaining relational
   groups need it; per `2026-09-21-sathandlers-validation-triage.md` the bigger wins
   are still handler-side (matrix 18, Add/Mul/Pow 18).
3. If unary-predicate performance becomes the bottleneck, the #27835 bitset-rules
   approach (`find_independent_subset` + direct-implication bitsets + explanation
   clauses) is a good standalone theory design, but only after its debug state is
   cleaned; do not import `facts2.py` as-is.

### 7a. Follow-up (2026-09-22): the prototype exists

Sequencing item 1 above has been implemented on branch `investigate/lra-theory`
(merged into `main` at merge commit `5bf789e`, not pushed):

- `reasoning/theory.py` defines the #30537 four-method `TheorySolver` protocol
  with the review fixes: first-conflict-wins in `_assign_literal`, duplicate
  detection, and no swallowed conflict while assigning an assumption.
- `reasoning/lra.py` is a SymPy-free dual-simplex port over
  `(terms, constant, strict, equality)` records using `Fraction`; terms are
  opaque keys and a small exact `_rref` replaces the SymPy `Matrix`.
- `reasoning/lra_adapter.py` interprets `LocalQ.eq/gt/lt/ge/le`, folds constant
  relations into unit clauses, and skips unhandled atoms (nan, imaginary,
  infinity, non-rational, matrices). Upstream's global nonlinearity rejection
  was dropped: independent terms are a sound relaxation.
- `satask(..., use_lra_theory=True)` and
  `ReasoningEngine(factbase, theory_solvers=...)` are the only API changes; the
  default path is unchanged. `var_settings` seeds plus a theory raise.

Measured (`agent-reports/2026-09-21-lra-theory-prototype.md`): 135 unit tests
pass, mypy strict clean; pinned `test_query.py` +1 (`test_issue_28127`, 38→39
passed, no regressions); a 528-query randomized differential against SymPy
`ask` had zero disagreements and answered 146 queries `ask` returns `None` for;
overhead is within noise when off and 1.03–1.43x on relational queries.

Still open: theory propagation, `Q.ne`/negated equalities, relation-to-sign
bridging (`test_relational` needs the latter), and the decision whether to
auto-enable the theory in `satask`.

## 8. Open questions / risks

- #30537's head must be fixed before any merge; the tilorc-bot regression case
  (theory conflict during `assume`) deserves a test, since it is the PR's main
  correctness win.
- Whether `LRASolver` should accept preprocessed constraints (`register_constraint`,
  tilorc-bot #32 / local branches) or keep `from_encoded_cnf` with internal helpers
  (#30538 as merged-to-be) is still undecided; #30533 prefers the former, #30538 was
  deliberately scoped to make the move easy.
- `Q.ne` and negated equalities remain under-specified in LRA preprocessing
  (`ALLOWED_PRED` excludes `Q.ne`; TiloRC suspects an edge case bug).
- The `var_settings` removal in #30537 is an API break; it also means the
  `NotImplementedError` for non-empty base assignments with LRA disappears.
- The assumptions layer still has soundness problems that a theory solver will not fix
  (see #27662's `finite`/`zero` handler rule and the nan/contrapositive discussion);
  #27835's explanation clauses would make unsat cores easier.

## 9. Sources

- PRs: sympy/sympy#27835, #30537, #30538, #30201, #30326, #30265, #30518, #29961,
  #30415, #28160, #30098, #30119; tilorc-bot/sympy#31, #32, #39.
- Issues: sympy/sympy#30533, #28147, #30121, #30157, #30209, #27467, #27662, #30150.
- Local refs: `TiloRC/sympy:forward-theory` = `6197a018`, `theory-registration` =
  `1834482b`, `rf-from_encoded` = `63c3134a`; worktrees `/home/tilo/lra_theory-rf`,
  `/home/tilo/satask-lra-*`, `/home/tilo/orion/*`; plans in
  `/home/tilo/satask-lra-fallback/PLAN-*.md`.
- Downloaded diffs and verified head files: `/tmp/opencode/theory-research/`
  (`pr27835.diff`, `pr30537.diff`, `pr30538.diff`, `dpll2_30537.py`, `lra_30538.py`,
  `fix_mypy.diff`).
