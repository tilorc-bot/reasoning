# Agent report: profiling and safe local optimizations of the pure-Python core

- **Date:** 2026-09-21
- **Status:** analysis complete; every prototype was measured and then reverted.
  The branch adds this report only; no source file differs from `b624573`.
- **Branch/worktree:** `perf/profiling` in `/home/tilo/reasoning-perf`,
  based on `b624573` (`Update agent report with number-facts results and scoped
  next steps`)
- **Scope:** the pure-Python pipeline only - `reasoning/clauses.py`,
  `engine.py`, `solver.py`, `discovery.py`, `registry.py`, `predicates.py`,
  `sympy_adapter.py`, `sathandlers.py`. No new dependencies, no Rust/CaDiCaL,
  no API or semantics changes, no broad rewrites.
- **Read this if:** you want to know where `satask` time goes at `b624573`,
  which low-risk edits are worth landing, or why the obvious solver-heuristic
  and known-facts ideas do not pay off.
- **Stale after:** changes to `clauses.py`, `engine.py`, `solver.py`,
  `sympy_adapter.py`, the fact volumes, or the pinned SymPy.
- **TL;DR:** at `b624573` the synthetic benchmark breaks down into
  discovery+encoding (34-44% of total), engine construction+search (42-64%),
  and a nearly free query-encoding slice (0.1-0.4%). On a 214-case broad
  workload the full pipeline is roughly a quarter each: discovery/class-fact
  processing 25%, known-fact encoding 24%, engine 25%, assumption/query
  encoding 24%. Microbenchmarks show `ClauseDB.add_clause` +
  `literal()` consume ~42% of `sum10` discovery+encoding, and `SATSolver`
  construction alone is ~68% of `ReasoningEngine` construction. Six low-risk,
  API-preserving prototypes (clause-DB validation fast path, engine container
  reuse + one-pass construction, `_base_model` from `var_settings`, deferred
  sentinel moves, predicate/registry caching, `Counter` occurrence counts)
  measured a combined **-16.1% on the `sum10` total** (7.295 -> 6.123 ms),
  **-13.3% on the broad-workload median** (3.32 -> 2.88 ms) and **-12.6% on
  engine-only**. All 74 reasoning tests, mypy, the broad-workload outcome
  counts, and the validation backend comparison are unchanged. Two tempting
  ideas were measured and rejected: a VSIDS heap dedupe (+8-9% `ask`,
  i.e. slower) and inert known-fact filtering (breaks 11 reasoning tests).
  The validation suite is 99.3% SymPy/handler-bound and out of scope.

## What was run

All timings below were taken on this machine, pinned to CPU 0 with `taskset`
(CPUs 2-3 measure ~8x slower, so pinning matters), in the prepared
`.venv` (Python 3.14, pinned SymPy `ddbb536d`):

```
# phase baselines (50 repeats per case, medians of 3-5 process runs)
taskset -c 0 .venv/bin/python -m benchmarks.satask --repeat 50

# engine-only on prebuilt databases, 50-100 repeats
PYTHONPATH=/home/tilo/reasoning-perf taskset -c 0 .venv/bin/python \
    /tmp/opencode/engine_only.py --repeat 50        # scratch, not committed

# broad discovery workload: benchmarks.compare_satask.cases(62819, 200), x5
PYTHONPATH=/home/tilo/reasoning-perf taskset -c 0 .venv/bin/python \
    /tmp/opencode/broad_discovery.py --seed 62819 --cases 200 --repeat 5

# cProfile attribution (workload-only profiling, imports warm)
PYTHONPATH=/home/tilo/reasoning-perf taskset -c 0 .venv/bin/python \
    /tmp/opencode/profile_runner.py satask  --repeat 30 --out /tmp/opencode/p_satask.prof
PYTHONPATH=/home/tilo/reasoning-perf taskset -c 0 .venv/bin/python \
    /tmp/opencode/profile_runner.py broad_nosat --repeat 3  --out /tmp/opencode/p_broad_nosat.prof
PYTHONPATH=/home/tilo/reasoning-perf taskset -c 0 .venv/bin/python \
    /tmp/opencode/profile_runner.py engine --repeat 30 --out /tmp/opencode/p_engine.prof

# validation attribution (scratch pytest plugin wraps ReasoningEngine)
PYTHONPATH=/tmp/opencode .venv/bin/python -m pytest validation -q --tb=no -p engine_timing -s

# correctness gates after each prototype
.venv/bin/python -m pytest reasoning/tests -q --tb=no
.venv/bin/python -m mypy
.venv/bin/python validation/compare_backends.py --timings 0
```

Scratch scripts live in `/tmp/opencode/`; nothing outside the report was added
to the repository. `cProfile` distorts absolute times, so it is used only for
relative call attribution; every before/after claim below is a `perf_counter`
median.

## Phase baselines (`b624573`, medians of 5 x 50 repeats, ms)

| Case | Clauses | Conversion | Discovery+encoding | Query encoding | Solve | Total |
| ---- | ---: | ---: | ---: | ---: | ---: | ---: |
| simple | 82 | 0.0098 | 0.1485 | 0.0056 | 0.2110 | 0.3811 |
| nested | 456 | 0.0268 | 1.1534 | 0.0082 | 1.1652 | 2.7478 |
| sum10 | 1161 | 0.0265 | 2.5073 | 0.0074 | 4.6357 | 7.2950 |
| matrix | 26 | 0.0167 | 0.0771 | 0.0073 | 0.1065 | 0.2088 |
| contradiction | 83 | 0.0214 | 0.1419 | 0.0081 | 0.1498 | 0.3251 |

`Solve` covers `ReasoningEngine(db)` construction, root propagation, the base
solve and the query solve. Engine-only over a prebuilt database splits as:

| Case | Clauses | ctor | ask | total |
| ---- | ---: | ---: | ---: | ---: |
| simple | 82 | 0.1444 | 0.0564 | 0.1997 |
| nested | 456 | 0.8629 | 0.3384 | 1.2144 |
| sum10 | 1161 | 1.9972 | 2.4698 | 4.4659 |
| matrix | 26 | 0.0507 | 0.0459 | 0.0966 |
| contradiction | 83 | 0.1332 | 0.0000 | 0.1334 |

Construction is 44% (sum10) to 72% (simple, nested) of engine-only time
(matrix 53%, and the contradiction case pays only construction before the
inconsistency is detected).

Broad workload (`compare_satask.cases(62819, 200)`: 12 fixed + 200 random + 2
matrix cases, x5 = 1070 `satask` calls; outcomes True 215 / False 160 / None
670, 25 `ValueError` "Inconsistent assumptions"):

```
sum_s=3.916  median_ms=3.3165  mean_ms=3.6594  p95_ms=7.296  max_ms=45.048
```

Clause sources over the 214 cases (scratch counter script):

| Source | Clauses | Share | Per case |
| ---- | ---: | ---: | ---: |
| discovery (`discover_facts`) | 24373 | 22.8% | 113.9 |
| known facts (`add_known_facts`) | 81129 | 75.9% | 379.1 |
| assumption assertion | 732 | 0.7% | 3.4 |
| query compilation | 691 | 0.6% | 3.2 |
| **total** | **106925** | | **499.6** |

The known-fact template is 81 clauses over 31 predicates (numbers),
24 clauses over 17 predicates (matrices), or 105 clauses over 48 predicates
when both occur; it is added for every discovered subject. For `sum10`:
269 discovery + 891 known + 1 assumption = 1161 clauses.

Microbenchmarks of the core primitives (medians of 200, pristine revision, ms):

| Operation | simple | nested | sum10 | matrix | contradiction |
| ---- | ---: | ---: | ---: | ---: | ---: |
| `ClauseDB.literal` over all atoms | 0.0339 | 0.1351 | 0.3789 | 0.0193 | 0.0347 |
| `ClauseDB.add_clause` over all clauses | 0.0490 | 0.2808 | 0.7732 | 0.0149 | 0.0499 |
| `get_all_relevant_facts` | 0.1283 | 1.1046 | 2.7797 | 0.0667 | 0.1269 |
| `assert_formula(assumption)` fresh db | 0.0029 | 0.0053 | 0.0029 | 0.0056 | 0.0050 |
| `compile_formula(query)` | 0.0013 | 0.0013 | 0.0013 | 0.0013 | 0.0013 |
| `SATSolver` ctor only | 0.0790 | 0.4576 | 1.3480 | 0.0344 | 0.0827 |
| `SATSolver` ctor + `solve` | 0.1440 | 0.9184 | 2.6692 | 0.0671 | 0.1048 |
| `ReasoningEngine` ctor + `ask` | 0.1888 | 1.1884 | 4.5001 | 0.0938 | 0.1346 |

For `sum10`, `add_clause` + `literal` (1.15 ms) are 41% of the 2.78 ms
discovery+encoding pass, and `SATSolver` construction (1.35 ms) is 68% of the
2.00 ms engine construction cost.

## Hot functions (cProfile, workload-only, `b624573`)

Full pipeline, 30 repetitions of each benchmark case (`strip`ped path omitted):

```
   ncalls   tottime   cumtime    tt%    ct%  function
    54240    0.1688    0.2432  11.47  16.54  reasoning/clauses.py:66(add_clause)
      150    0.1131    0.1398   7.69   9.51  reasoning/solver.py:132(_initialize_clauses)
    28350    0.1055    0.1726   7.17  11.74  reasoning/solver.py:611(_assign_literal)
      150    0.0659    0.3684   4.48  25.04  reasoning/sympy_adapter.py:148(add_known_facts)
      150    0.0494    0.2883   3.36  19.60  reasoning/engine.py:12(__init__)
     4440    0.0381    0.0860   2.59   5.85  reasoning/solver.py:805(_vsids_calculate)
    27900    0.0380    0.1226   2.59   8.33  reasoning/clauses.py:43(literal)
    62400    0.0235    0.0265   1.60   1.80  reasoning/clauses.py:195(iter_atoms)
      150    0.0218    0.0303   1.48   2.06  reasoning/solver.py:770(_vsids_init)
    59310    0.0206    0.0206   1.40   1.40  reasoning/solver.py:569(_clause_sat)
    55140    0.0203    0.0850   1.38   5.78  reasoning/predicates.py:58(__hash__)
    55140    0.0197    0.0305   1.34   2.07  reasoning/predicates.py:31(__hash__)
   129840    0.0193    0.0193   1.32   1.32  reasoning/engine.py:21(<genexpr>)
     7860    0.0182    0.1513   1.24  10.29  reasoning/solver.py:744(_unit_prop)
      390    0.0145    0.2806   0.98  19.08  reasoning/solver.py:155(_find_model)
```

Broad discovery+encoding, 3 x 214 cases (no engine):

```
   ncalls   tottime   cumtime    tt%    ct%  function
   335736    0.7740    1.2024  17.19  26.70  reasoning/clauses.py:66(add_clause)
      642    0.3630    1.8897   8.06  41.97  reasoning/sympy_adapter.py:148(add_known_facts)
   158799    0.2386    0.7650   5.30  16.99  reasoning/clauses.py:43(literal)
   303426    0.1646    0.1831   3.65   4.07  reasoning/clauses.py:195(iter_atoms)
   313305    0.1172    0.5129   2.60  11.39  reasoning/predicates.py:58(__hash__)
   324441    0.1165    0.1792   2.59   3.98  reasoning/predicates.py:31(__hash__)
    24876    0.1055    1.0920   2.34  24.25  reasoning/clauses.py:341(assert_formula)
   146640    0.0973    0.1198   2.16   2.66  reasoning/predicates.py:22(__call__)
      642    0.0748    2.1238   1.66  47.17  reasoning/discovery.py:48(discover_facts)
   113268    0.0677    0.3832   1.50   8.51  reasoning/clauses.py:206(_as_literal)
    40059    0.0637    0.5701   1.42  12.66  reasoning/clauses.py:227(compile_)
    77961    0.0496    0.0957   1.10   2.13  reasoning/predicates.py:53(__eq__)
    13260    0.0482    0.1062   1.07   2.36  reasoning/clauses.py:117(AND)
     6246    0.0471    0.1528   1.05   3.39  reasoning/sathandlers.py:42(_allargs)
    16848    0.0446    0.0833   0.99   1.85  reasoning/clauses.py:161(EQUIVALENT)
```

Engine-only on prebuilt databases, 30 repetitions:

```
   ncalls   tottime   cumtime    tt%    ct%  function
    28350    0.1048    0.1681  16.52  26.52  reasoning/solver.py:611(_assign_literal)
      150    0.1009    0.1272  15.91  20.06  reasoning/solver.py:132(_initialize_clauses)
      150    0.0465    0.2696   7.33  42.51  reasoning/engine.py:12(__init__)
     4380    0.0375    0.0844   5.92  13.32  reasoning/solver.py:805(_vsids_calculate)
      150    0.0207    0.0289   3.26   4.56  reasoning/solver.py:770(_vsids_init)
   129840    0.0191    0.0191   3.01   3.01  reasoning/engine.py:21(<genexpr>)
    58530    0.0188    0.0188   2.97   2.97  reasoning/solver.py:569(_clause_sat)
     7770    0.0178    0.1544   2.80  24.35  reasoning/solver.py:744(_unit_prop)
      390    0.0139    0.2720   2.19  42.89  reasoning/solver.py:155(_find_model)
      2340    0.0122    0.0377   1.92   5.95  reasoning/solver.py:674(_undo)
     12840    0.0116    0.0201   1.83   3.17  reasoning/solver.py:841(_vsids_lit_unset)
     47100    0.0109    0.0109   1.72   1.72  reasoning/solver.py:592(_is_sentinel)
     17220    0.0104    0.0153   1.65   2.41  reasoning/solver.py:378(val)
      54390    0.0069    0.0069   1.08   1.08  reasoning/engine.py:19(<genexpr>)
      120    0.0056    0.1844   0.88  29.09  reasoning/engine.py:28(_base_model)
```

Notable readings:

- `engine.py:19/21` are the two validation generator scans (`any(not clause
  ...)`, `any(literal == 0 ...)`); across 150 engine constructions that is
  54k empty-clause iterations plus 130k zero-literal iterations, even though a
  single pass suffices.
- `val()` is called once per variable in `_base_model`; `engine.py` builds the
  model dict twice per SAT solve (`_find_model`'s generator yield is discarded
  by `solve()`).
- `_assign_literal` copies `list(self.sentinels[-lit])` before every watched
  scan even when no sentinel moves.
- `_initialize_clauses` materializes every clause twice (`engine` tuples, then
  solver lists) and updates `defaultdict`s with a Python-level loop.
- `predicates.__hash__` builds a fresh tuple on every call; 637k calls in the
  broad workload.

## Validation-suite attribution (engine vs SymPy)

A scratch plugin (`/tmp/opencode/engine_timing.py`) wraps
`ReasoningEngine.__init__` and `ReasoningEngine.ask` during a full
`pytest validation -q` run (104 tests: 54 failed, 40 passed, 8 xfailed,
2 xpassed at both revisions):

| Revision | Wall | ctor calls/ms | ask calls/ms | Engine share | ask median | ask p99 | ask max |
| ---- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline `b624573` | 48.91 s | 660 / 231.5 | 658 / 100.5 | 0.68% | 0.062 ms | 0.887 ms | 1.707 ms |
| best prototype set | 49.09 s | 660 / 242.4 | 658 / 88.7 | 0.67% | 0.056 ms | 0.808 ms | 1.910 ms |

**The validation suite is ~99.3% SymPy/handler/discovery-bound, so it is
explicitly out of scope for this report.** The small ctor/ask changes are
inside the engine's own bookkeeping, not in SymPy; total wall time is
unchanged within noise (48.9 vs 48.8 s baseline noise band).

Behaviour parity on the suite was also checked with the committed comparison
script: `validation/compare_backends.py --timings 0` exits 1 both before and
after, with an **identical** list of 16 outcome mismatches (all
`reasoning=PASSED, sympy=FAILED`) and the same 3 "same outcome, different
failure" tests. Exit 1 is the committed policy at this revision (it counts
"reasoning passes where SymPy fails" as a mismatch); the updated
improvement-aware policy mentioned in
`agent-reports/2026-09-21-sathandlers-validation-triage.md` is not in this
commit.

## Ranked optimization opportunities

Each numbered item was prototyped in the worktree, measured, and reverted.
"Measured" figures are incremental deltas against the configuration one step
earlier (configurations were cumulative), on the same pinned CPU and harness;
"estimated" marks extrapolations that were not prototyped. Prototype diff:
6 files, +105/-50 lines, no public signature changes.

### O1. Engine construction: reuse clause containers, one validation pass, model from assignments (measured)

- **Location:** `reasoning/engine.py:16` (`[tuple(clause) ...]`), `:19`/`:21`
  (two full scans), `:23` (`SATSolver` copy), `:38-41` (`val()` per variable).
- **Measured cost/share:** engine construction is 42.5% of engine-only time;
  the `engine.py:19/21` validation scans are ~4.1% of engine-only tottime and
  `val()` plus the model-dict build another ~2.5%.
- **Proposed change:** build `_clauses` from the factbase's own containers
  (converting only non-standard clause iterables), validate emptiness and
  zero-literal membership in one pass, and build `_model_values` as
  `{abs(lit): lit for lit in solver.var_settings}` instead of calling `val()`
  for every variable index.
- **Measured end-to-end gain:** within the P2 bundle, engine-only -12.8% and
  `sum10` total -5.5% (see prototype accounting).
- **Risk:** low. The model identity holds because `_find_model` yields only
  when every variable is assigned; unassigned variables read back as 0 either
  way. Container reuse is safe because `SATSolver` copies clauses into lists.
- **Effort/scope:** ~15 lines in one file.
- **Verification:** `pytest reasoning/tests`, broad-workload outcome counts,
  `compare_backends.py`.

### O2. Solver construction: single clause materialization and C-level occurrence counts (measured)

- **Location:** `reasoning/solver.py:69` (`clauses = list(clauses)` then
  `:140` copies again), `:132-152` (`_initialize_clauses` Python increment
  loop over every literal).
- **Measured cost/share:** `_initialize_clauses` is 15.9-18.5% of engine-only
  tottime and the single largest remaining engine-construction cost;
  `SATSolver` ctor is 1.35 ms of the 4.50 ms `sum10` engine-only baseline.
- **Proposed change:** materialize the outer clause list only when `variables
  is None`, bind `sentinels`/`_unit_prop_queue` locally, and compute
  occurrence counts with `Counter().update(chain.from_iterable(non_units))`
  (units are excluded exactly as before, so VSIDS scores are unchanged).
- **Measured gain:** dedicated 300-sample A/B of `SATSolver(clauses, vars)`:
  nested 0.441 -> 0.413 ms (-6.4%), sum10 1.266 -> 1.188 ms (-6.2%); the
  full-pipeline contribution is inside the P2/P7 deltas.
- **Risk:** low. `Counter` supports the same `[lit] += 1` and missing-key
  reads as `defaultdict(int)`; only the (class-level) attribute type changes.
- **Effort/scope:** ~15 lines in one file.
- **Verification:** same as O1 plus `mypy` (annotation update needed).

### O3. `_assign_literal`: defer sentinel moves instead of copying the watch set (measured)

- **Location:** `reasoning/solver.py:647` (`list(self.sentinels[-lit])`),
  `:649-664` (remove/add during iteration).
- **Measured cost/share:** `_assign_literal` is 14-17% of engine-only tottime;
  its `_clause_sat`/`_is_sentinel` helpers add another ~4.7%.
- **Proposed change:** iterate the live watch set, collect `(newlit, cls)`
  moves, and apply them after the loop (one pass, no per-assignment set copy).
  Inline the `_clause_sat`/`_is_sentinel` checks and bind hot attributes
  locally.
- **Measured gain:** engine-only total improved ~2-3% over the identical
  configuration with the original method (nested 1.072 vs 1.103 ms on
  repeated 100-repeat runs).
- **Risk:** medium-low. Watch invariants are subtle; the deferred moves must
  not alter which clause moves where. Reasoning tests and the broad-workload
  outcome counts pass, but `solver.py` has no unit-test file, so this edit
  deserves a dedicated watch-invariant/parity test before landing.
- **Effort/scope:** ~25 lines in one method.
- **Verification:** `pytest reasoning/tests`, a scripted parity sweep over
  `compare_satask.cases` in both `early_return` modes, `compare_backends.py`.

### O4. `ClauseDB.add_clause` validation fast path (measured)

- **Location:** `reasoning/clauses.py:66`.
- **Measured cost/share:** 11.5% tottime / 16.5% cumtime of the full satask
  profile, 17.2%/26.7% of broad discovery; 41% of `sum10`
  discovery+encoding in the microbenchmark.
- **Proposed change:** handle `type(literal) is int` directly (zero check,
  tautology check, `set.add`), keeping the original `isinstance` chain as the
  fallback for `bool` and int subclasses.
- **Measured gain (isolated, cumulative P1):** `sum10` discovery -7.3%, total
  -3.1% (7.295 -> 7.068 ms), broad median -2.1%. Micro: add_clause for all
  `sum10` clauses 0.773 -> 0.638 ms (-17%).
- **Risk:** low; exact same validation/exception behavior, just reordered.
- **Effort/scope:** ~12 lines.
- **Verification:** `pytest reasoning/tests` (error cases included),
  `test_satask.py` outcome tests.

### O5. `ClauseDB.literal` inline allocation and a validated known-fact emit (measured)

- **Location:** `reasoning/clauses.py:43` (dict lookup + `_allocate()` call),
  `reasoning/sympy_adapter.py:148-161` (`add_known_facts` calls
  `add_clause` for 76% of all clauses in the broad workload).
- **Measured cost/share:** `literal` is 2.6-5.9% tottime; `add_known_facts`
  is 25% cumtime of the full pipeline and 42% of broad discovery+encoding.
- **Proposed change:** inline the variable bump in `literal`; in
  `add_known_facts`, append `set(literals)` directly once `_known_template`
  guarantees nonzero, duplicate-free, tautology-free clauses. The current
  pinned templates were checked: numbers 81 clauses, matrices 24, combined
  105; all have zero tautologies, duplicates and zeros.
- **Measured gain (isolated, cumulative P5):** `sum10` discovery -12.3%
  (2.067 -> 1.812 ms), total -3.9%, broad median -3.8%. Micro: `literal` over
  all `sum10` atoms 0.379 -> 0.376 ms (noise; the win is the emit path).
- **Risk:** low if the template invariant is enforced where `_known_template`
  is built (or asserted once); otherwise a future SymPy pin could introduce a
  tautology and silently change `db.data`. Recommend asserting the invariant
  in `_known_template` rather than trusting it.
- **Effort/scope:** ~10 lines across two files.
- **Verification:** template-invariant assertion plus the usual gates.

### O6. Predicate hashing, namespace lookup, registry type cache (measured)

- **Location:** `reasoning/predicates.py:31` (`Predicate.__hash__` builds a
  tuple per call), `:58` (`AppliedPredicate.__hash__`), `:83`
  (`PredicateNamespace.__getattr__` on every `Q.x`), `reasoning/registry.py:43`
  (issubclass scan per `facts_for`).
- **Measured cost/share:** six predicate methods together are ~10% of broad
  discovery+encoding tottime (`__hash__` 5.2%, `__call__` 2.2%, `__eq__`
  1.1%, `__getattr__` 0.6%); `registry.__getitem__` is ~1%.
- **Proposed change:** precompute `Predicate._hash` at construction; cache
  `AppliedPredicate._hash` lazily in a third `__slots__` entry; copy predicate
  names into the namespace instance dict so plain attribute access is used;
  memoize `ClassFactRegistry.__getitem__` per type, clearing on register.
- **Measured gain (isolated, cumulative P4):** `sum10` total -5.2%, broad
  median -5.4% (3.110 -> 2.942 ms), broad sum -8%.
- **Risk:** low. `AppliedPredicate` is conceptually immutable; the registry
  cache is invalidated on every registration, so dynamically registered
  handlers still apply.
- **Effort/scope:** ~25 lines across two files.
- **Verification:** `test_predicates.py`, `test_sathandlers.py`, full suite.

### O7. Micro-optimizations that did not measure (not proposed)

- `SATSolver._initialize_variables` dense-set elision: neutral within noise.
- `assert_formula` op-dispatch restructuring: neutral (broad discovery+encoding
  247.0 vs 248.0 ms across interleaved runs).
- `engine.fixed()` allocating a three-entry dict per call: real but only on the
  `early_return` path, which is not used by the benchmark or validation;
  not worth the churn.

## Prototype accounting (cumulative, medians; all reverted)

| Config | `sum10` discovery | `sum10` total | engine-only `sum10` | broad median | broad sum_s | Broad outcomes |
| ---- | ---: | ---: | ---: | ---: | ---: | --- |
| baseline `b624573` | 2.507 | 7.295 | 4.466 | 3.317 | 3.916 | 215/160/670, 25 err |
| +O4 add_clause (P1) | 2.325 | 7.068 | 4.505 | 3.247 | 3.833 | identical |
| +O1/O2/O3 (P2b) | 2.395 | 6.680 | 3.927 | 3.110 | 3.782 | identical |
| +O6 predicates/registry (P4) | 2.067 | 6.334 | 3.900 | 2.942 | 3.479 | identical |
| +O5 literal/known emit (P5) | 1.812 | 6.089 | 3.920 | 2.831 | 3.410 | identical |
| +O2 Counter (P7) | 1.826 | 6.020 | 3.954 | 2.835 | 3.391 | identical |
| **final config, fresh 5-run batch** | **1.862** | **6.123** | **3.905** | **2.875** | **3.500** | **identical** |
| **gain vs baseline** | **-25.7%** | **-16.1%** | **-12.6%** | **-13.3%** | **-10.6%** | unchanged |

Final vs baseline by case (total ms): simple 0.381 -> 0.295 (-22.7%), nested
2.748 -> 2.335 (-15.0%), sum10 7.295 -> 6.123 (-16.1%), matrix 0.209 -> 0.178
(-14.7%), contradiction 0.325 -> 0.248 (-23.9%). Engine-only: simple 0.200 ->
0.174, nested 1.214 -> 1.056, sum10 4.466 -> 3.905, matrix 0.097 -> 0.086,
contradiction 0.133 -> 0.109. Run-to-run drift on this machine is ~2%, which
is why the last two cumulative rows differ from the fresh final batch.

Correctness gates for the final prototype configuration:

```
.venv/bin/python -m pytest reasoning/tests -q --tb=no   # 74 passed, 1 xfailed
.venv/bin/python -m mypy                                # Success: no issues found
broad workload outcomes                                 # identical counts
validation/compare_backends.py --timings 0              # identical comparison output
```

## Considered and rejected

- **Inert known-fact filtering.** At the point known facts are added,
  `db.encoding` only contains predicates from discovered class facts; the
  proposition/assumption atoms are not encoded until after `add_known_facts`.
  A naive "drop clauses with no already-present predicate" filter is
  implementable but fails **11** `reasoning/tests/test_satask.py` tests
  (`test_satask`, `test_zero`, `test_integer`, `test_imaginary`,
  `test_pos_neg`, `test_pow_pos_neg`, `test_prime_composite`,
  `test_composite_proposition`, `test_matrix_predicates`,
  `test_satask_early_return`, `test_python_boolean_constants_and_zero_iterations`).
  The theoretically safe version needs the query/assumption atoms first, i.e.
  reordering `get_all_relevant_facts`/`satask` - a semantics-affecting change
  out of scope. Potential upside if ever done carefully: ~36% of known-fact
  clauses and ~27% of all broad-workload clauses are inert components.
- **VSIDS `lit_heap` duplicate dedupe.** Bound the heap to one entry per
  literal via a pending set. Measured **slower**: `ask` +8-9% on `sum10`
  (2.34 -> 2.55 ms engine-only), because per-pop set bookkeeping costs more
  than the saved `heappop`s for these formulas. Reverted; not recommended
  without hard-instance evidence.
- **`_simplify` extra `_unit_prop`/`_pure_literal` pass** after a non-empty
  queue: touched for analysis only; `_pure_literal` is a documented extension
  point (`_pure_literal` returns False today), so restructuring the loop would
  change that contract for negligible gain.
- **SymPy-bound work.** Handlers, `facts_for`, `to_formula` over SymPy
  expressions, and SymPy sorting/equality are ~99.3% of validation wall time
  and 5-7% of the broad workload. Only avoid-duplicate-work changes were in
  scope; no handler rewrite was attempted.
- **Rust/CaDiCaL.** Already explored in
  `/home/tilo/reasoning-rust` and `/home/tilo/reasoning-cadical`; both are
  explicitly out of scope here and add dependencies/build steps the project
  does not want.
- **API/semantics changes** (e.g. moving `ClauseDB.data` to tuples, removing
  `val()` from the engine model path) were not attempted; `test_clauses.py`
  pins `db.data` as a list of sets.

## Reproduction and committed state

The committed branch contains this report only. The six prototype source
files were restored byte-for-byte from copies of `b624573`; `git diff` for
`reasoning/`, `benchmarks/`, `validation/` and `tools/` is empty. The
worktree's pre-existing unstaged `sympy/` deletion (part of the prepared
environment) is untouched and is not part of the commit.

```
git -C /home/tilo/reasoning-perf status --short   # only " D sympy/..." plus the report
git -C /home/tilo/reasoning-perf show --stat HEAD
```
