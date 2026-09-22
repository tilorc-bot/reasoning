# reasoning

A propositional reasoning core with an optional SymPy integration.

Install the core with `pip install -e .`, or the SymPy integration and test
dependencies with `pip install -e '.[sympy,dev]'`.

```python
from reasoning.satask import satask
from sympy import Q, symbols

x = symbols('x')
assert satask(Q.real(x), Q.positive(x)) is True
```

The independent API uses opaque hashable atoms and integer clauses:

```python
from reasoning.clauses import ClauseDB, IMPLIES, assert_formula, compile_formula
from reasoning.engine import ReasoningEngine

db = ClauseDB()
assert_formula('a', db)
assert_formula(IMPLIES('a', 'b'), db)
query = compile_formula('b', db)
assert ReasoningEngine(db).ask(query) is True
```

## Implementation

- `clauses.py` owns the atom table, auxiliary variables, lightweight Boolean
  formulas, and direct/Tseitin clause compilation. Query literals are equivalent
  to their formulas, so either polarity can be queried. An empty clause is false;
  an empty clause list is true. Zero is not a literal.
- `discovery.py` computes relevance and discovers facts in rounds, visiting each
  subject once. Its adapter supplies expression knowledge.
- `solver.py` contains the propositional DPLL2 solver extracted from SymPy;
  `engine.py` manages consistency checking and entailment queries.
- `predicates.py` owns a SymPy-independent `Q` vocabulary. Predicates apply to
  opaque arguments to form hashable applied predicates, so only the argument
  expressions of `Q` applications need to be SymPy objects.
- `sympy_adapter.py` translates Boolean expressions, relations, and `Q`
  applications into local formulas, inspects predicates and symbols, and
  instantiates cached number/matrix fact templates.
- `sathandlers.py` inspects SymPy expressions but emits lightweight formulas
  over local predicates. `registry.py` is independent of SymPy.
- `refine.py` adapts SymPy's assumption-driven refinement. Its handlers ask
  the independent engine; `refine` keeps SymPy's `_eval_refine` hooks.

The core does not import SymPy. SymPy expressions can be opaque atoms without
requiring the core to understand them, and `satask` normalizes its inputs so
SymPy `Q` applications become local applied predicates carrying the original
expression arguments. Every normalized atom must be an applied predicate;
other leaves raise `TypeError`. Handler facts and query formulas are compiled
directly to integer clauses; there is no symbolic CNF intermediate.
`ClauseDB.format_clauses()` provides readable diagnostics.

`satask` retains its three-valued results and inconsistency errors.
`early_return=True` permits propagation-only answers while trusting consistency;
root propagation conflicts still raise. Relevance limits fact discovery, while
all explicit assumptions enter the solver. Existing number/matrix fact selection
is preserved, including its combined rule selection for mixed subjects.

`iterations=None` means unlimited discovery rounds; the former `sympy.oo` value
is also accepted. Zero now means zero discovery rounds (the old loop always ran
at least once). Known predicate facts remain independently controlled by
`use_known_facts`. `get_relevant_clsfacts` and `get_all_relevant_facts` now return
`ClauseDB` objects instead of SymPy CNF objects. Registered handlers now return
lightweight formulas. Legacy substitution helpers remain available for callers.

## Validation and performance

Run `python -m pytest reasoning/tests` and
`python -m benchmarks.satask --repeat 25`.

To compare answers against saved original modules, run
`python -m benchmarks.compare_satask --baseline-satask /path/to/satask.py
--baseline-handlers /path/to/sathandlers.py --include-early-return`.

SymPy's refine suite is re-exported with `refine` bound to `reasoning.refine`:
run `python -m pytest validation/test_refine.py`, or compare it against SymPy's
refine with `python validation/compare_backends.py --suite
validation/test_refine.py`. The only remaining failure is the old-assumption
path in `test_sign` (`Symbol('x', imaginary=True)`); the `Q.real(1/x)` and
sum-parity gaps have landed with the structural and elementary-function facts.
Handler modules live in `reasoning/refine/handlers/` and self-register into
`handlers_dict`; see `agent-reports/2026-09-22-refine-handler-report.md` for
the per-key status and the deliberately deferred list.

The benchmark reports warm median conversion, discovery/encoding, query
encoding, and solving times, plus clause and variable counts. Discovery and fact
encoding are measured together because facts are encoded as they are produced.

A local Python 3.14 comparison against the original implementation, alternating
25 runs of each implementation in one process, produced these medians:

| Case | Before (ms) | After (ms) | Speedup |
| --- | ---: | ---: | ---: |
| Simple predicate | 0.624 | 0.449 | 1.39× |
| Nested arithmetic | 4.996 | 3.223 | 1.55× |
| Ten-term sum | 14.084 | 8.155 | 1.73× |
| Matrix predicate | 0.355 | 0.259 | 1.37× |
| Contradictory assumptions | 0.568 | 0.403 | 1.41× |

These are illustrative measurements, not performance guarantees. Auxiliary
variables can change propagation strength and search cost for other formulas.
The tests cover query equivalence, constants, inconsistencies, cyclic discovery,
iteration limits, existing SymPy behavior, and operation without SymPy imports.

Code derived from SymPy is covered by `reasoning/LICENSE.sympy`.
