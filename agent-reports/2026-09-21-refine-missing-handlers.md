# Agent report: every refine handler SymPy currently lacks (and what the independent core can support)

- **Date:** 2026-09-21
- **Status:** investigation complete; no implementation attempted. All findings reproduced
  against pinned SymPy `ddbb536d` (1.15.0.dev) and this worktree's
  `reasoning/refine.py`; the 4 upstream matrix handlers missing from our copy and
  the handler/core split for the 3 xfailed tests were newly identified here
- **Branch/worktree:** `feature/refine` in `/home/tilo/reasoning-refine` (report only;
  `reasoning/refine.py`, `reasoning/tests/test_refine.py`, `validation/test_refine.py`
  are uncommitted working-tree files and were not touched)
- **Scope:** `sympy/assumptions/refine.py`, `handlers_dict` registrations elsewhere in
  SymPy, `_eval_refine` implementations, `sympy.functions.*`, `sympy.matrices.expressions`,
  `sympy.special`, plus `reasoning/refine.py`, `reasoning/satask.py`, and the 2a/2b
  facts branches
- **Read this if:** you are picking a refine handler to implement upstream, importing
  upstream handlers into the independent core, or deciding whether a missing
  simplification is a handler gap or a `satask` gap
- **Stale after:** any change to `handlers_dict`, `_eval_refine`, the SymPy pin, the
  refine tests, `agent/2a-add-mul-pow` / `agent/2b-elementary-functions` landing, or
  the `assumptions.refine` PR queue
- **TL;DR:** SymPy's runtime `handlers_dict` has **18** entries (14 in `refine.py`
  plus 4 matrix handlers registered from `matrices/expressions/*.py`) and **5**
  `_eval_refine` hooks. Our copy has only the 14 literal entries, so
  `Transpose`/`Inverse`/`Determinant`/`MatMul` refinement is silently lost. Of 215
  `Function` subclasses and 30 `MatrixExpr` subclasses, only **21 classes** have any
  refine behavior. We inventory **~50 plausible class-level additions in 12 families**
  (~15 high-value: log, conjugate, tan/cot/sec/csc, Min/Max, frac/Mod, factorial,
  binomial, DiracDelta/KroneckerDelta, gamma poles, hyperbolic zero/period, inverse
  trig, matrix handler parity). On today's `feature/refine` core, 26 representative
  prototype checks (23 handlers) pass with no core change once `Transpose`/`Inverse`
  ask the base matrix instead of `A.T`/`A**-1`; `Determinant`/`MatMul` work verbatim.
  The remaining gaps are confined to Add/Mul/Pow closure, matrix predicate closure,
  relations, and old-assumption symbols (see the xfail tie-back below).
  The `agent/2a-add-mul-pow` facts silently fix **2 of our 3 xfails**
  (`test_pow1`, `test_sin_cos`, verified); `test_sign` is 2 asserts handler-layer
  (pass `assumptions` in `refine_sign`) and 2 core-blocked (old-assumption symbols).
  Upstream has 9 open + 10 closed labeled `assumptions.refine` PRs; only 6 ever
  merged, all before Feb-Apr 2026, and the main reviewer has publicly stepped back.
  Piecewise/relational work should stay out of refine (rejected PR #29364; belongs
  in `ask`/LRA).

## 1. Method

All inventory was produced from the pinned install and this worktree; scripts live in
`/tmp/opencode/refine_inventory/` (outside the repo) and are small enough to recreate.

1. **Literal handler extraction (AST).** Parse the `handlers_dict` assignment in both
   `sympy/assumptions/refine.py` and `reasoning/refine.py` with `ast`, including the
   `AnnAssign` form (upstream annotates the dict, which a naive `ast.Assign` walk
   misses):

   ```python
   for node in ast.walk(ast.parse(Path(path).read_text())):
       if isinstance(node, (ast.Assign, ast.AnnAssign)):
           ...
           out[ast.literal_eval(key)] = value.id
   ```

2. **Runtime handler extraction.** Import the pinned SymPy and print
   `sympy.assumptions.refine.handlers_dict`. This is essential: 4 handlers are
   registered by import side effects of `sympy.matrices.expressions.{transpose,inverse,
   determinant,matmul}`, so the static view undercounts (14 vs 18). Grep for all
   registration sites:

   ```bash
   grep -rn "handlers_dict" /home/tilo/reasoning/.venv/lib/python3.14/site-packages/sympy --include=*.py | grep -v assumptions/refine.py
   ```

3. **`_eval_refine` enumeration.** AST-scan every non-test `*.py` under the pinned
   `sympy/` for `_eval_refine` definitions and record the enclosing class and
   `file:line`:

   ```bash
   grep -rn "_eval_refine" /home/tilo/reasoning/.venv/lib/python3.14/site-packages/sympy --include=*.py | grep -v test
   ```

4. **Class-surface enumeration.** Walk `Basic.__subclasses__()` recursively and
   `Function`/`MatrixExpr` subclass trees, recording `__name__`, `__module__`, own
   `_eval_refine`, and handler membership. 436 `Basic` subclasses, of which **215 are
   `Function` subclasses** and **30 are `MatrixExpr` subclasses**. Script:
   `candidates.py`.

5. **Behavioral evidence.** A corpus of 85 `(family, expr, assumptions, expected,
   probe-queries)` cases (`evidence.py`) runs `sympy.refine` and `reasoning.refine`
   side by side and records answers; a separate probe list (`probes.py`, 68 queries)
   compares `reasoning.satask.satask` against `sympy.assumptions.ask` for exactly the
   `Q.*` queries candidate handlers need. The same probe script was run against the
   sibling branches' cores by setting `PYTHONPATH`
   (`/tmp/opencode/reasoning-2a`, `/tmp/opencode/reasoning-2b`,
   `/tmp/opencode/reasoning-combined`) with `reasoning/refine.py` copied in (temp
   overlay, other worktrees untouched).

6. **Prototype validation.** `prototypes.py` monkeypatches 22 candidate handlers into
   `reasoning.refine.handlers_dict` (no repo file changed) and checks 25 concrete
   simplifications against the real `reasoning.refine` dispatch.

7. **Xfail attribution.** `xfail_asserts.py` parses the three `@XFAIL` test bodies in
   `reasoning/tests/test_refine.py` with `ast`, executes each statement individually
   against a selected core, and reports which exact `assert`s fail.

8. **Upstream activity.** GitHub API searches (2026-09-21):

   ```bash
   curl -s "https://api.github.com/search/issues?q=repo:sympy/sympy+label:assumptions.refine+is:pr+is:open&per_page=100"
   curl -s "https://api.github.com/search/issues?q=repo:sympy/sympy+label:assumptions.refine+is:pr+is:closed&per_page=100"
   curl -s "https://api.github.com/search/issues?q=repo:sympy/sympy+refine+in:title+is:pr+created:%3E2025-01-01&per_page=100"
   curl -s "https://api.github.com/repos/sympy/sympy/issues/27888"
   curl -s "https://api.github.com/repos/sympy/sympy/pulls/29948"
   curl -s -H "Accept: application/vnd.github.v3.diff" "https://api.github.com/repos/sympy/sympy/pulls/<N>"
   ```

   Patches were extracted for all labeled PRs and the key unlabeled ones; comments
   were fetched for the open PRs to capture maintainer blockers.

**Limitations.** (a) The class list is exhaustive over `Basic` subclasses importable
from `sympy.functions`, `sympy.matrices.expressions`, `sympy.special`, and friends, but
"candidate simplification" judgement is mathematical, not mechanical — functions with
no assumption-driven rewrite (most special functions) are called out as such rather
than enumerated case by case. (b) `handlers_dict` is keyed on exact
`expr.__class__.__name__`, so subclass relationships do not matter at dispatch; the
inventory counts classes, not handler functions. (c) Built-in evaluators auto-simplify
many exact cases (`sin(0)`, `binomial(n, 0)`, `exp(log(x))`), so some table entries say
"already handled by construction, no handler needed".

## 2. Current coverage and dispatch

### 2.1 Dispatch order

`refine` (`sympy/assumptions/refine.py:21-78`, `reasoning/refine.py:37-94`):

1. Return non-`Basic` inputs unchanged.
2. If `expr` is not an atom, recursively refine every argument and rebuild
   `expr = expr.func(*refined_args)` (`refine.py:61-64`).
3. If `expr` has `_eval_refine`, call it and return any non-`None` result
   (`refine.py:65-68`). **These hooks are SymPy methods, so in `reasoning.refine` they
   still call SymPy's `ask`, not `satask`.**
4. Otherwise look up `handlers_dict[expr.__class__.__name__]` (`refine.py:69-72`);
   handlers in our copy call the local, satask-backed `ask`
   (`reasoning/refine.py:25-34`).
5. If the handler returned a different `Expr`, recurse into it
   (`refine.py:73-78`), which is how e.g. `refine_log` output is simplified further.

### 2.2 Handlers actually dispatched (runtime, pinned SymPy)

| # | class name | handler | source | in local `handlers_dict`? |
|---|---|---|---|---|
| 1 | `Abs` | `refine_abs` | `assumptions/refine.py:81` | yes |
| 2 | `Pow` | `refine_Pow` | `assumptions/refine.py:119` | yes |
| 3 | `exp` | `refine_exp` | `assumptions/refine.py:220` | yes |
| 4 | `atan2` | `refine_atan2` | `assumptions/refine.py:256` | yes |
| 5 | `re` | `refine_re` | `assumptions/refine.py:301` | yes |
| 6 | `im` | `refine_im` | `assumptions/refine.py:324` | yes |
| 7 | `arg` | `refine_arg` | `assumptions/refine.py:346` | yes |
| 8 | `sign` | `refine_sign` | `assumptions/refine.py:380` | yes |
| 9 | `MatrixElement` | `refine_matrixelement` | `assumptions/refine.py:421` | yes |
| 10 | `cos` | `refine_sin_cos` | `assumptions/refine.py:444` | yes |
| 11 | `sin` | `refine_sin_cos` | `assumptions/refine.py:444` | yes |
| 12 | `Heaviside` | `refine_Heaviside` | `assumptions/refine.py:537` | yes |
| 13 | `floor` | `refine_floor_ceiling` | `assumptions/refine.py:565` | yes |
| 14 | `ceiling` | `refine_floor_ceiling` | `assumptions/refine.py:565` | yes |
| 15 | `Transpose` | `refine_Transpose` | `matrices/expressions/transpose.py:85`, registered at `:100` | **no** |
| 16 | `Inverse` | `refine_Inverse` | `matrices/expressions/inverse.py:86`, registered at `:105` | **no** |
| 17 | `Determinant` | `refine_Determinant` | `matrices/expressions/determinant.py:133`, registered at `:153` | **no** |
| 18 | `MatMul` | `refine_MatMul` | `matrices/expressions/matmul.py:471`, registered at `:505` | **no** |

The 4 missing matrix handlers are the cheapest parity gap in this project: they exist
upstream, are small (10-35 lines), and are not produced by any import our copy performs
because `reasoning.refine` defines its own independent dict (`reasoning/refine.py:624`).
Note the handler keys are exact class names: `sec` is not `cos`, `sqrt` *is* `Pow`,
`1/x` is `Pow`, `x/y` is `Mul` (no `Mul` handler), and `frac`/`Mod` are their own classes.

### 2.3 `_eval_refine` hooks (all in SymPy core, reached by both copies)

| class | file:line | behavior | note |
|---|---|---|---|
| `Boolean` (all `Relational`s, `AppliedPredicate`) | `sympy/logic/boolalg.py:224` | `ask(self, assumptions)`; returns `true`/`false`/`None` | **the reason relational/Piecewise refinement already works** and why a `refine_Relational` handler (PR #29579) is mostly dead code |
| `Pow` | `sympy/core/power.py:245` | negative numeric base + integer exponent: `(-b)**even -> b**even`, `(-b)**odd -> -b**odd` | already exercised by `test_pow1` |
| `Symbol` | `sympy/core/symbol.py:436` | returns `self` | bare symbols can never reach a handler |
| `exp` | `sympy/functions/elementary/exponential.py:258` | old-assumption path for `exp(pi*I*coeff)` | **ignores its `assumptions` argument** (this is issue behind PR #29199); the `exp` handler covers the Q-assumption path |
| `Predicate` | `sympy/assumptions/assume.py:351` | returns `self` | only applies to `Predicate` instances, not `AppliedPredicate` (which inherits `Boolean`) |

### 2.4 Current test status

```
/home/tilo/reasoning/.venv/bin/python -m pytest reasoning/tests/test_refine.py -q   # 16 passed, 3 xfailed
/home/tilo/reasoning/.venv/bin/python -m pytest validation/test_refine.py -q        # 16 passed, 3 failed
# failures: test_pow1, test_sign, test_sin_cos (same three as the xfails)
```

`sympy.assumptions.tests.test_refine` itself passes 19/19 under pinned SymPy.

## 3. Missing handlers, by family

Status legend: **none** = no handler/hook, `refine` returns the input; **partial** =
handler exists but does not cover the listed cases; **parity** = upstream has a handler
that our copy does not register. "Core" is the current `feature/refine` satask; where a
sibling branch changes the picture it is noted.

### 3.1 Trigonometric functions

`refine_sin_cos` (`refine.py:444-534`) and `refine_atan2` (`:256`) exist; everything
else is **none**. The reciprocal/inverse functions are distinct classes, so none of
them inherit `sin`/`cos` handling.

| class | current | candidate rules (exact input / assumptions / output) | source | core |
|---|---|---|---|---|
| `tan` | none | `tan(x)/Q.zero(x)->0`; `tan(n*pi)/Q.integer(n)->0`; `tan(x+n*pi)/Q.integer(n)->tan(x)`; `tan(n*pi/2)/Q.odd(n)->zoo`; `tan(x+n*pi/2)/Q.odd(n)->-cot(x)` | PRs #29324, #29962, #30073, #29941, #29317, #29302 | all parity/zero queries answered today (parity of integer multiples works; mixed Add shifts need 2a) |
| `cot` | none | `cot(x)/Q.zero(x)->zoo`; `cot(n*pi/2)/Q.odd(n)->0`; `cot(x+n*pi)/Q.integer(n)->cot(x)`; odd `pi/2` shift -> `-tan(x)` | #29324, #29941 | as above |
| `sec` | none | `sec(n*pi)/Q.integer(n)->(-1)**n`; `sec(x+n*pi/2)/Q.odd(n)->(-1)**((n+1)/2)*csc(x)`; `sec(n*pi/2)/Q.odd(n)->zoo` | #29948, #29942, #29405 | yes via `refine_sin_cos` parity machinery |
| `csc` | none | `csc(n*pi)/Q.integer(n)->zoo`; `csc(n*pi/2)/Q.odd(n)->0` when `(n-1)/2` even, `-1` when odd; odd `pi/2` shift -> sec | #29948, #29942 | yes |
| `sinc` | none | `sinc(x)/Q.zero(x)->1` (construction leaves `sinc(x)` symbolic) | none filed | yes |
| `asin` | none | `asin(sin(x))` with `Q.real(x) & Q.ge(x,-pi/2) & Q.le(x,pi/2)` -> `x`; outside the branch, piecewise | no dedicated PR; conjugate PR touched asin/acos branch cuts | range queries work when given directly; range *derivation* (`Q.le` from `Q.ge` swapped) fails |
| `acos` | none | `acos(cos(x))` with `Q.real(x) & Q.ge(x,0) & Q.le(x,pi)` -> `x` | as above | as above |
| `atan` | none | `atan(tan(x))` with `Q.real(x) & Q.ge(x,-pi/2) & Q.le(x,pi/2)` -> `x` | as above | as above; note `atan(tan(x))` is not auto-evaluated |
| `acot`, `asec`, `acsc` | none | compositions under range assumptions; branch cuts are the hard part | #29173 added them then reverted some as wrong | math feasibility risk > core risk |

The `sin`/`cos` handler itself is **partial**: it is the only place `sum_of_parity_*`
lives, and it fails when parity requires Add simplification
(`cos(x+(2*n+1)*pi+m*pi/2)` under `Q.integer(n)&Q.integer(m)`); that is the single
failing assert in `test_sin_cos` and is fixed by the 2a facts. PR #29450 also patches a
latent `AttributeError` there when the parity factor `(-1)**(k/2)` evaluates to an
`Integer` (`refine.py:527-534` calls `refine_Pow` on a non-`Pow`).

### 3.2 Hyperbolic functions and inverse hyperbolic functions

All **none**. `exp` exists but nothing else in `sympy.functions.elementary.hyperbolic`.
The forward functions are structurally close to `sin`/`cos` (imaginary period
`pi*I`) and inverse compositions are close to inverse trig.

| class | candidate rules | source | core |
|---|---|---|---|
| `sinh` | `sinh(x)/Q.zero(x)->0`; `sinh(x+n*pi*I)/Q.integer(n)->(-1)**n*sinh(x)` | #30192, #30138 | zero: yes; periodic: parity queries yes |
| `cosh` | `cosh(x)/Q.zero(x)->1`; `cosh(n*pi*I)/Q.integer(n)->(-1)**n`; `cosh(x+n*pi*I)->(-1)**n*cosh(x)` | #30192, #30138 | yes |
| `tanh` | `tanh(x)/Q.zero(x)->0`; `tanh(x+n*pi*I)->tanh(x)`; poles at odd `(n+1/2)*pi*I` | #30192, #30138 | yes |
| `coth` | `coth(x)/Q.zero(x)->zoo`; period `pi*I`; `coth(x+n*pi*I)->coth(x)` | none filed | yes |
| `sech` | `sech(x)/Q.zero(x)->1`; `sech(x+n*pi*I)->(-1)**n*sech(x)` | none filed | yes |
| `csch` | `csch(x)/Q.zero(x)->zoo`; `csch(x+n*pi*I)->(-1)**n*csch(x)` | none filed | yes |
| `asinh` | `asinh(sinh(x))/Q.real(x)->x` | none filed | yes |
| `acosh` | `acosh(cosh(x))/Q.nonnegative(x)->x` | none filed | yes |
| `atanh` | `atanh(tanh(x))/Q.real(x)->x`; poles on real axis | none filed | yes |
| `acoth`, `asech`, `acsch` | inverse compositions with range restrictions | none filed | yes for direct range assumptions |

Evidence: `refine(sinh(x), Q.zero(x))`, `refine(cosh(x), Q.zero(x))`,
`refine(coth(x), Q.zero(x))` are all unchanged in master; `sinh(n*pi*I)` and
`cosh(n*pi*I)` auto-simplify at construction, `sinh(x+n*pi*I)` does not.

### 3.3 Exponential / logarithmic

`exp` exists (`refine_exp`, plus the assumption-ignoring hook). `log` is **none**;
`LambertW` is **none**; `exp_polar`/`ExpBase` are **none**.

| class | candidate rules | source | core |
|---|---|---|---|
| `log` | `log(exp(x))/Q.real(x)->x`; `log(x**y)/Q.positive(x)&Q.real(y)->y*log(x)`; `log(1/x)/Q.positive(x)->-log(x)`; product split under positive factors; branch-cut guards (`log(exp(x))` only for real `x`, `log(x**2)` only for positive `x`) | #29131, #29760 | **all needed probes answer today** (`Q.positive(x)`, `Q.real(y)`, `Q.real(x)`, `Q.nonzero(x)`), so fully handler-layer |
| `LambertW` | `W(x*exp(x))/Q.real(x)->x` only on the principal branch with sign bookkeeping; `W(0)=0` already evaluates | none filed | risky math, not core-limited; **not recommended** |
| `exp_polar` | branch-aware products/lifts; `exp_polar` is an internal multivalued object | none filed | unrealistic |

`exp` is **partial**: `refine(exp(pi*I*2*x), Q.integer(x))` works through the handler,
but `exp` of a real sum cannot be split by `refine` (not its job); the hook at
`exponential.py:258` ignores passed assumptions (PR #29199 was closed and superseded by
#29592).

### 3.4 Powers and roots

`Pow` exists but is **partial/buggy**; `Rem` is **none**; `sqrt` is `Pow`.

| case | current | candidate | source | core |
|---|---|---|---|---|
| `(x**3)**(1/2)` with `Q.real(x)` | pinned and local both return `Abs(x)**(3/2)`, which is **wrong** at `x=-2` (`2*sqrt(2)*I` vs `2*sqrt(2)`) | split `(z1**z2)**z3` casework: integer outer exponent -> `z1**(z2*z3)`; positive base + real inner -> `z1**(z2*z3)`; real base + even inner -> `Abs(z1)**(z2*z3)`; drop the unconditional `abs(base.base)**(base.exp*exp)` at `refine.py:160-162` | issue #29684, PR #29800 | queries (`Q.integer`, `Q.positive`, `Q.real`, `Q.even`) all answer today; fully handler-layer |
| `(x**a)**b` general | no change | as above | #29800 | yes |
| `sqrt(1/x)` with `Q.positive(x)` | pinned `1/sqrt(x)`, local `sqrt(1/x)` | Pow real closure `Q.real(x**-1)` | — | **core-blocked today**; fixed by 2a (`Q.real(1/x)` -> True) |
| `Abs(z)**2` with `Q.imaginary(z)` | `Abs(z)**2` | `-z**2` (and `Abs(z)**4 -> z**4`) | issue #30473, PRs #30474/#30476 | `Q.imaginary`, `Q.even` answer today; handler-layer |
| `Pow(S.Exp1, x)` | no special handling | avoid double-handling between `refine_Pow` and `refine_exp` | PR #30248 | handler-layer |
| `Rem(p, q)` | none | analogous to `Mod` below | none filed | yes for integer cases |

### 3.5 Complex functions

`re`, `im`, `arg`, `sign`, `Abs` exist but several are **partial/incorrect**;
`conjugate`, `adjoint`, `polar_lift`, `exp_polar`, `principal_branch` are **none**.

| class | current | candidate rules | source | core |
|---|---|---|---|---|
| `conjugate` | none | `conjugate(x)/Q.real(x)->x`; `conjugate(x)/Q.imaginary(x)->-x`; `conjugate(x**n)/Q.imaginary(x)&Q.integer(n)->(-x)**n`; branch-aware `log`/`asin`/`acos`/`atan`/`acot`/`asec`/`acsc` rules; `z*conjugate(z)->Abs(z)**2` | #29173 (largest), #29994, #29954, #29945, #30489, #30488 | basic real/imag/pow cases answer today; branch-cut rules are subtle (maintainer found concrete wrong answers in #29173); Mul form is core-blocked (`Q.negative(x*y)` fails today, 2a fixes) |
| `Abs` | **partial** | `Abs(x)/Q.zero(x)` should be `0` but returns `x` (`refine_abs` has no zero check); `Abs(x+y)` for Add args under per-term signs; the Add-sign path needs `Q.negative(x-y)` closure | #29183, #29796 | zero/positive/negative direct: yes; Add sign derivation: fails today, 2a fixes; Mul path already works |
| `sign` | **partial + bug** | `refine_sign` drops `assumptions` on its `Q.real`/`Q.imaginary` checks (`refine.py:407,412`), so `refine(sign(x), Q.positive(x))` fails for a plain real symbol and `sign(Abs(x))` only works because satask separately knows `Q.real(Abs(x))`; pass assumptions through | #29605, #29407, #29604 | real cases fixable in handler; imaginary-symbol cases need the old-assumption bridge |
| `arg` | **partial** | `arg(x)/Q.imaginary(x)&Q.nonzero(x)->±pi/2`; `arg(x)/Q.zero(x)` edge (nan) | #29409 | `Q.imaginary`/`Q.nonzero` answer; ±requires sign of `im(x)` |
| `adjoint` | none | `Adjoint(X)` under real-elements/self-adjoint predicates | none filed | needs matrix predicate closure |
| `polar_lift`, `exp_polar`, `principal_branch` | none | multivalued branch bookkeeping | none filed | **unrealistic** (internal, no test/use demand) |

### 3.6 Integer-valued functions

`floor`/`ceiling` exist (partial); `frac`, `Mod`, `Rem` are **none**; combinatorial
functions are **none** (many exact values auto-evaluate).

| class | candidate rules | source | core |
|---|---|---|---|
| `frac` | `frac(x)/Q.integer(x)->0`; `frac(x+n)/Q.integer(n)->frac(x)` | #30368, #29744, #30496 (all closed) | `Q.integer` answers today; handler-layer |
| `Mod` | `Mod(p,1)/Q.integer(p)->0`; `Mod(p,q)` with `Q.integer(p)&Q.integer(q)` -> `p - q*floor(p/q)`; sign variants | #30376, #29743 (closed) | yes |
| `factorial` | `factorial(n)/Q.zero(n)->1`; `Q.integer(n)&Q.negative(n)->zoo` (gamma pole); `Q.positive_infinite(n)->oo`; `Q.negative_infinite(n)` edge | #29203 (draft; maintainer: only constants, wanted more) | all probes answer today |
| `RisingFactorial`/`FallingFactorial` | `rf(x,0)=1`, `ff(x,0)=1` (some auto-evaluate); integer/zero cases | none filed | yes |
| `binomial` | zero/one k cases (`binomial(n,0)`, `binomial(n,1)` auto-evaluate for literal `k`; under `Q.zero(k)` they need the handler), negative `k` -> 0, `Q.integer(n)&Q.nonnegative(n)&Q.negative(n-k)->0` | #29213 (draft) | all probes answer today |
| `factorial2`, `subfactorial`, `MultiFactorial` | exact/zero/infinite constants | none filed | yes but low value |
| `fibonacci`, `lucas`, `harmonic` | `fibonacci(0)`, `harmonic(0)` auto; negative-index identities | none filed | low value |

`floor`/`ceiling` are **partial**: they handle integer/infinite args and integer Add
terms, but not `frac` terms or `Mod`; the `floor(x+frac(y))` family is absent.

### 3.7 Special functions

**Mostly unrealistic for `refine`.** At exact numeric arguments these functions already
evaluate (`erf(0)`, `zeta(0)`, `besselj(0,0)`, `gamma(-1)`); assumption-driven symbolic
rewrites mostly need `rewrite`/`simplify`, not `refine`, and branch behavior is hard.

| class | realistic part | source | core |
|---|---|---|---|
| `gamma` (+ `loggamma`, `digamma`, ...) | only poles: `gamma(n)/Q.integer(n)&Q.nonpositive(n)->zoo`; maybe `gamma(1)->1` etc. already auto | #29203 included it; maintainer lukewarm | queries answer today |
| `beta`, `betainc` | poles at nonpositive integers; otherwise no | none filed | not recommended |
| `erf`, `erfc`, `erfi`, `fresnel*` | exact/odd-even values auto; no useful assumption rules | none filed | unrealistic |
| `Ei`, `Si`, `Ci`, `li`, `Chi`, `Shi` | exact values at 0 auto; no | none filed | unrealistic |
| `zeta`, `dirichlet_eta`, `polylog`, `lerchphi` | exact arguments auto (`zeta(2)` etc.); no assumption rules | none filed | unrealistic |
| Bessel/Airy/Hankel, `hyper`, `meijerg`, elliptic, Mathieu, orthogonal polynomials | no plausible refine rules | none filed | **unrealistic** |
| `LambertW` | see 3.3 | none filed | hard, not core-limited |

### 3.8 `Piecewise`

**none**, and deliberately so. PR #29364 ("Add `_eval_refine` for Piecewise") was
rejected: *"this is not the right approach … This is really an issue with `ask` and not
`refine`"*, and the follow-up diagnosis pointed at `lra_satask`/the `Or` handler, not
refine. Today `refine(Piecewise((1, x>0),(3,True)), Q.positive(x)) -> 1` and the
`~(x>0)`/`Eq`/`Ne` cases already work through recursive arg refinement plus
`Boolean._eval_refine`. In `reasoning.refine` that hook still calls **SymPy's** `ask`,
so Piecewise/relational behavior is *identical to upstream and not satask-limited*;
adding a handler that used the local `ask` would risk regressions. Recommendation:
leave Piecewise/relational out (matches issue #27888's guidance).

### 3.9 `Min` / `Max`

**none**. No `_eval_refine`, no handler; `Max(x, y)` stays symbolic under any
assumption today.

| class | candidate rules | source | core |
|---|---|---|---|
| `Max` | `Max(x,y)/Q.ge(x,y)->x`; `Max(x,y)/Q.le(x,y)->y`; `Max(x,0)/Q.positive(x)->x`; `Max(x,0)/Q.zero(x)->0`; infinite args | #29406, #30487, #29565, #29302, #27697 | `Q.ge`/`Q.le`/`Q.positive` direct answers work today; fully handler-layer |
| `Min` | mirror image | as above | yes |

### 3.10 Matrix expressions

Four upstream handlers are **parity-missing in `reasoning.refine`**; the rest are
**none** (except `MatrixElement`, which is partial). The base matrix predicates exist
in `Q` (`symmetric`, `orthogonal`, `unitary`, `singular`, `unit_triangular`, `diagonal`,
`triangular`, `invertible`, `integer_elements`, …), but satask only answers them when
they are *directly assumed on the same expression*.

| class | upstream handler | local status | local feasibility |
|---|---|---|---|
| `Transpose` | `Q.symmetric(A.T)->A` (`transpose.py:85`) | absent; local returns `X.T`, pinned returns `X` | exact port needs `Q.symmetric(X.T)` from `Q.symmetric(X)` (**blocked today and on combined**); asking `expr.arg` instead makes it pass (prototype 26/26) |
| `Inverse` | `Q.orthogonal(A**-1)->A.T`; `Q.unitary(A**-1)->A.conjugate()` (`inverse.py:86`) | absent | same closure gap; adjusted `expr.arg` port passes |
| `Determinant` | `Q.orthogonal(A)->1`; `Q.singular(A)->0`; `Q.unit_triangular(A)->1` (`determinant.py:133`) | absent; local leaves `Determinant(X)` where pinned gives `1`/`0` | asks the *base* matrix, so **works today** (prototype passes) |
| `MatMul` | cancels `A.T*A` under `Q.orthogonal`, `A.conjugate()*A` under `Q.unitary` (`matmul.py:471`) | absent; `X.T*X` stays `X.T*X` vs pinned `I` | asks the factor directly -> works |
| `MatrixElement` | symmetric index swap only (`refine.py:421`) | present | extensions below |
| `Trace` | none upstream; a local PR draft exists (`/tmp/opencode/pr-body-trace.md`) | none | `Trace(X)/Q.zero(X)->0` feasible today (`Q.zero(X)` direct); trace-class variants harder |
| `MatAdd` | none | `MatAdd(X, 0)` stays `X + 0` | `Q.zero(Y)` -> drop term; feasible |
| `HadamardProduct` | none | stays under any assumption | `Q.zero(X)` -> zero matrix; feasible |
| `KroneckerProduct` | none | stays | identities with `Identity`/`ZeroMatrix`; low value |
| element-set predicates | none | `X[i,j]` stays | `Q.zero(X)` / `Q.diagonal(X)` with `i != j` -> 0 (direct assumption works today); `Q.upper_triangular` etc. need closure; `Q.integer_elements(X) -> Q.integer(X[i,j])` **blocked** (`satask` answers neither today nor on combined, pinned `ask` does) |

For this project the 4 upstream matrix handlers are the highest-value low-risk item:
porting `Determinant`/`MatMul` verbatim works on the current core, and a one-line
adjustment (`ask(..., expr.arg)`) makes `Transpose`/`Inverse` work too (all four pass
in the prototype).

### 3.11 Boolean / relational

**Out of scope by maintainer guidance.** `Boolean._eval_refine` (`boolalg.py:224`)
already asks, so `refine(x >= 0, Q.nonnegative(x)) -> True`, `refine(Eq(x,0), Q.zero(x))`
and `refine(Ne(x,0), Q.zero(x))` already work in both copies (verified). The genuine
gap is `ask` for cases such as `refine(sqrt(x) >= 0, Q.real(sqrt(x)))` (still
unrefined), where the fix belongs in the predicate handlers (`NonNegativePredicate` for
`Pow`) and LRA, not in `refine`. PR #29579 added both a (dead) `refine_Relational`
handler and the `ask` fix; the contributor agreed to split, and TiloRC noted some
relational cases already pass in master. The ask-side work is active outside the
refine label: PR #30415 ("ask: Handle more inequality related queries", open
2026-09-18, touches `lra_satask.py`/`satask.py`/`ask.py`, fixes issues #30324/#27834).
Our core should not add a relational handler.

### 3.12 Everything else the enumeration found

| class | current | note |
|---|---|---|
| `DiracDelta` | none; `DiracDelta(x)` under `Q.nonzero(x)` stays | `->0` is a clean, useful handler; `Q.nonzero` answers today |
| `KroneckerDelta` | none; unchanged under `Q.eq`/`Q.ne` | `->1/0`; satask answers `Q.eq` when given directly, and `Q.ne(x,y)` given `Q.eq(x,y)` is `None` (SymPy says `False`), but the `Q.eq` branch alone gives a useful handler |
| `LeviCivita` | none | repeated-index zero rules; low value |
| `SingularityFunction` | none | order/argument cases; low value |
| `Derivative`, `Integral`, `Sum`, `Product`, transforms | none (`refine` has an explicit TODO about `Integral` at `refine.py:63`) | unrealistic; assumption-based integrand refinement is not well-defined |
| sets (`Intersection`, `Union`, `Interval`, `ImageSet`, `ConditionSet`), `Contains` | none | `Contains` is Boolean -> ask route; set algebra is out of scope |
| number-theory functions (`primepi`, `totient`, `divisor_sigma`, `mobius`, `primeomega`, …) | none | no assumption-driven simplifications; unrealistic |
| `AccumBounds` (returned by `refine_sin_cos` for infinite args) | not dispatched | already covered indirectly |

### 3.13 Summary of counts

| family | classes with behavior today | missing/incomplete candidates | high-value now |
|---|---|---|---|
| trig | `sin`, `cos`, `atan2` | tan, cot, sec, csc, sinc, asin, acos, atan, acot, asec, acsc (11); `sin/cos` partial | tan/cot/sec/csc |
| hyperbolic | — | 12 forward+inverse | zero/periodic |
| exp/log | `exp` | log, LambertW, `exp_polar` (2 practical) | log |
| powers/roots | `Pow` (partial/buggy) | `Rem` + 4 Pow gaps | `(x**a)**b` fix |
| complex | `Abs`(partial), `re`, `im`, `arg`(partial), `sign`(buggy) | conjugate, adjoint, polar trio (4 practical) | conjugate |
| integer | `floor`, `ceiling` (partial) | frac, Mod, Rem, factorial, rf, ff, binomial, factorial2, subfactorial, fibonacci (9+) | frac/Mod/factorial/binomial |
| special | — | gamma only (rest ~60 unrealistic) | gamma poles |
| Piecewise | via `Boolean` hook | 1 (do not add) | — |
| Min/Max | — | 2 | both |
| matrices | `MatrixElement` (partial), 4 upstream ports absent | 4 ports + Trace, MatAdd, Hadamard, Kronecker + element extensions (8) | all 4 ports |
| Boolean/relational | via `Boolean` hook | out of scope | — |
| deltas | — | DiracDelta, KroneckerDelta, LeviCivita, SingularityFunction (4) | first two |

Roughly **50 class-level candidates across 12 families**, ~15 high-value. Only 21 of
436 `Basic` subclasses (18 handler keys + `Symbol` + `Boolean` + `Predicate`) have any
refine behavior today.

## 4. Verification and evidence

### 4.1 Representative behavior (pinned SymPy vs `reasoning.refine`)

From `evidence.py` (85 cases). "same" means both agree; "local gap" means SymPy
simplifies and we do not (or produce a different form).

| family | expression, assumptions | `sympy.refine` | `reasoning.refine` | needed `ask` query -> satask today | verdict |
|---|---|---|---|---|---|
| trig | `tan(x), Q.zero(x)` | `tan(x)` | `tan(x)` | `Q.zero(x)` -> True | both missing handler |
| trig | `tan(n*pi), Q.integer(n)` | `tan(pi*n)` | `tan(pi*n)` | `Q.integer(n)` -> True | both missing |
| trig | `sec(n*pi), Q.integer(n)` | `sec(pi*n)` | `sec(pi*n)` | `Q.integer(n)` -> True | both missing |
| trig | `asin(sin(x)), Q.real(x)&Q.ge(x,-pi/2)&Q.le(x,pi/2)` | `asin(sin(x))` | `asin(sin(x))` | range queries direct -> True | both missing |
| hyperbolic | `sinh(x), Q.zero(x)` | `sinh(x)` | `sinh(x)` | `Q.zero(x)` -> True | both missing |
| hyperbolic | `coth(x), Q.zero(x)` | `coth(x)` | `coth(x)` | `Q.zero(x)` -> True | both missing |
| hyperbolic | `sinh(x+n*pi*I), Q.integer(n)` | `sinh(I*pi*n+x)` | `sinh(I*pi*n+x)` | `Q.integer(n)` -> True | both missing |
| hyperbolic | `asinh(sinh(x)), Q.real(x)` | `asinh(sinh(x))` | `asinh(sinh(x))` | `Q.real(x)` -> True | both missing |
| exp/log | `log(exp(x)), Q.real(x)` | `log(exp(x))` | `log(exp(x))` | `Q.real(x)` -> True | both missing |
| exp/log | `log(x**2), Q.positive(x)` | `log(x**2)` | `log(x**2)` | `Q.positive(x)` -> True | both missing |
| exp/log | `log(1/x), Q.positive(x)` | `log(1/x)` | `log(1/x)` | `Q.positive(x)` -> True | both missing |
| pow | `(x**3)**(1/2), Q.real(x)` | `Abs(x)**(3/2)` | `Abs(x)**(3/2)` | — | **both wrong** (#29684) |
| pow | `sqrt(1/x), Q.positive(x)` | `1/sqrt(x)` | `sqrt(1/x)` | `Q.real(1/x)` -> **None** | core-blocked (2a fixes) |
| pow | `(-2)**x, Q.even(x)` | `2**x` | `2**x` | `Q.even(x)` -> True | works |
| complex | `conjugate(x), Q.real(x)` | `conjugate(x)` | `conjugate(x)` | `Q.real(x)` -> True | both missing |
| complex | `sign(x*y), Q.positive(x)&Q.negative(y)` | `sign(x*y)` | `sign(x*y)` | `Q.negative(x*y)` -> **None** | core-blocked (2a fixes) |
| complex | `Abs(x+y), Q.positive(x)&Q.positive(y)` | `x+y` | `x+y` | `Q.positive(x+y)` -> True | works |
| complex | `Abs(x), Q.zero(x)` | `x` | `x` | `Q.zero(x)` -> True | **both wrong** (should be 0) |
| integer | `frac(x), Q.integer(x)` | `frac(x)` | `frac(x)` | `Q.integer(x)` -> True | both missing |
| integer | `Mod(x,1), Q.integer(x)` | `Mod(x,1)` | `Mod(x,1)` | `Q.integer(x)` -> True | both missing |
| integer | `factorial(n), Q.zero(n)` | `factorial(n)` | `factorial(n)` | `Q.zero(n)` -> True | both missing |
| integer | `factorial(n), Q.integer(n)&Q.negative(n)` | `factorial(n)` | `factorial(n)` | both True | both missing |
| integer | `binomial(n, n-k), Q.integer(n)&Q.negative(n-k)` | unchanged | unchanged | `Q.negative(n-k)` -> True | both missing |
| special | `gamma(n), Q.integer(n)&Q.nonpositive(n)` | `gamma(n)` | `gamma(n)` | both True | both missing |
| delta | `DiracDelta(x), Q.nonzero(x)` | `DiracDelta(x)` | `DiracDelta(x)` | `Q.nonzero(x)` -> True | both missing |
| delta | `KroneckerDelta(x,y), Q.eq(x,y)` | `KroneckerDelta(x,y)` | `KroneckerDelta(x,y)` | `Q.eq` -> True | both missing |
| Min/Max | `Max(x,y), Q.ge(x,y)` | `Max(x,y)` | `Max(x,y)` | `Q.ge(x,y)` -> True | both missing |
| Piecewise | `Piecewise((1,x>0),(3,True)), Q.negative(x)` | `3` | `3` | via SymPy `ask` in `Boolean` hook | works |
| matrices | `Transpose(X), Q.symmetric(X)` | `X` | `X.T` | `Q.symmetric(X.T)` -> None | **parity gap** |
| matrices | `Inverse(X), Q.orthogonal(X)` | `X.T` | `X**-1` | `Q.orthogonal(X**-1)` -> None | **parity gap** |
| matrices | `Determinant(X), Q.orthogonal(X)` | `1` | `Determinant(X)` | `Q.orthogonal(X)` -> True | **parity gap** |
| matrices | `X.T*X, Q.orthogonal(X)` | `I` | `X.T*X` | `Q.orthogonal(X)` -> True | **parity gap** |
| matrices | `X[0,1], Q.diagonal(X)` | `X[0,1]` | `X[0,1]` | `Q.zero` of element -> None (sympy too) | both missing, feasible via `Q.diagonal(X)` |
| relational | `x>=0, Q.nonnegative(x)` | `True` | `True` | via SymPy `ask` | works (out of scope) |

### 4.2 `satask` answerability for handler prerequisites

All 68 probes were run on four cores: `feature/refine`, `agent/2a-add-mul-pow`,
`agent/2b-elementary-functions`, and `agent/combined-2a-2b` (temp overlays). Gaps
relative to `sympy.ask`:

| query / assumptions | base satask | 2a | 2b | combined | sympy ask |
|---|---|---|---|---|---|
| `Q.odd(2*n+1) / Q.integer(n)` | None | **True** | None | **True** | True |
| `Q.real(1/x) / Q.positive(x)` | None | **True** | None | **True** | True |
| `Q.imaginary(1/x) / Q.imaginary(x)` | None | **True** | None | **True** | True |
| `Q.real(exp(x)) / Q.real(x)` | None | None | **True** | **True** | True |
| `Q.negative(x*y) / Q.positive(x)&Q.negative(y)` | None | **True** | None | **True** | True |
| `Q.negative(x-y) / Q.negative(x)&Q.positive(y)` | None | **True** | None | **True** | True |
| `Q.symmetric(X.T) / Q.symmetric(X)` | None | None | None | None | True |
| `Q.orthogonal(X**-1) / Q.orthogonal(X)` | None | None | None | None | True |
| `Q.orthogonal(X*Y) / Q.orthogonal(X)&Q.orthogonal(Y)` | None | None | None | None | True |
| `Q.integer(X[i,j]) / Q.integer_elements(X)` | None | None | None | None | True |
| `Q.le(y,x) / Q.ge(x,y)` | None | None | None | None | True |
| `Q.real(Abs(x))` (no assumptions) | **True** (class fact) | True | True | True | True |
| `Q.zero(x) / Q.zero(x)`, `Q.eq(x,y) / Q.eq(x,y)`, `Q.ge(x,y) / Q.ge(x,y)`, `Q.integer(n) / Q.integer(n)`, `Q.positive_infinite(n) / Q.positive_infinite(n)` | True | True | True | True | True |

Takeaway: the 2a facts close **7 of the 15** handler-prerequisite gaps (all Add/Mul/Pow
closure and parity cases), 2b adds elementary-function closure (`Q.real(exp(x))`) for
**8 of 15** together, and only **matrix predicates and reversed-order relations**
remain after both. That is remarkably good news for porting the non-matrix handler
backlog to this core.

### 4.3 Prototype handlers on the current core

`prototypes.py` monkeypatches 23 handlers and checks 26 simplifications. Result:
**26/26 pass on `feature/refine` without any core change**, once the two matrix ports
that ask the transposed/inverted matrix (`Transpose`, `Inverse`) are adjusted to ask
`expr.arg`; the verbatim upstream forms fail exactly those 2 checks
(`Q.symmetric(X.T)`, `Q.orthogonal(X**-1)`), and `Determinant`/`MatMul` work verbatim.
Verified passing on base:
`tan` zero/period/odd-half-shift, `cot`, `sinh`/`cosh`/`coth` zero, `log(exp(x))`,
`log(x**2)`, `conjugate(x)` real/imag, `frac(integer)`, `Mod(x,1)`, `factorial` zero and
negative-integer pole, `binomial(n,0)`, `Max`/`Min`, `DiracDelta` nonzero,
`KroneckerDelta` eq, `gamma` nonpositive-integer pole,
`Transpose`/`Inverse`/`Determinant`/`MatMul`.

### 4.4 The three xfailed tests

Statement-level execution (`xfail_asserts.py`) on each core:

| test | base `feature/refine` | 2a | 2b | combined |
|---|---|---|---|---|
| `test_pow1` | 19 assertions pass; **1 fail**: `refine(sqrt(1/x), Q.positive(x)) == 1/sqrt(x)` (line 19) | **20/20 pass** | fails same assert | **20/20 pass** |
| `test_sin_cos` | 44 pass; **1 fail**: `cos(x+(2*n+1)*pi+m*pi/2)` under `Q.integer(n)&Q.integer(m)` (line 43) | **45/45 pass** | fails same assert | **45/45 pass** |
| `test_sign` | 5 pass; **4 fail**: lines 5-6 (`Symbol('x', real=True)`) and 12-13 (`Symbol('x', imaginary=True)`) | same 4 fail | same 4 fail | same 4 fail |

`test_sign` attribution: lines 5-6 fail because `refine_sign` calls `ask(Q.real(arg))`
**without the assumptions** (upstream bug, `refine.py:407`), and satask cannot see the
symbol's old `real=True`. Patching the handler to pass `assumptions` fixes lines 5-6 on
every core (verified: returns `1`/`-1`); lines 12-13 then need the symbol's old
`imaginary=True`, i.e. the project's known old-assumption bridge (gap 2d in
`agent-reports/2026-09-21-sathandlers-validation-triage.md`), or a test change to pass
`Q.imaginary(x)` explicitly.

### 4.5 Reproduction commands

```bash
PY=/home/tilo/reasoning/.venv/bin/python
cd /home/tilo/reasoning-refine
$PY -m pytest reasoning/tests/test_refine.py -q          # 16 passed, 3 xfailed
$PY -m pytest validation/test_refine.py -q               # 16 passed, 3 failed
PYTHONPATH=/home/tilo/reasoning-refine $PY /tmp/opencode/refine_inventory/enumerate.py
PYTHONPATH=/home/tilo/reasoning-refine $PY /tmp/opencode/refine_inventory/evidence.py
PYTHONPATH=/home/tilo/reasoning-refine $PY /tmp/opencode/refine_inventory/probes.py
PYTHONPATH=/home/tilo/reasoning-refine $PY /tmp/opencode/refine_inventory/prototypes.py
PYTHONPATH=/home/tilo/reasoning-refine $PY /tmp/opencode/refine_inventory/xfail_asserts.py
# sibling-core comparisons (temp overlays; no other worktree modified):
PYTHONPATH=/tmp/opencode/refine_inventory/core_2a       $PY /tmp/opencode/refine_inventory/xfail_asserts.py
PYTHONPATH=/tmp/opencode/refine_inventory/core_combined $PY /tmp/opencode/refine_inventory/probes.py
```

## 5. Upstream activity

Issue #27888 ("Refine is not able to make many simplifications", open since 2025-04-03,
updated 2026-09-09) is the umbrella. Its guidance, verbatim: *"Anything related to
inequalities is not an easy or good choice (e.g. piecewise is not a good choice). The
fix for such issues has to do with `ask` and not refine."* Successful examples cited:
#28873, #29276, #29174, #29325; the explicitly unsuccessful one is #29364 (Piecewise).

### 5.1 PRs labeled `assumptions.refine` (+ #29948)

Open (9):

| PR | title | handler | state | landed? | revive? |
|---|---|---|---|---|---|
| #29131 | Add refine_log handler for logarithm simplifications | log | open (35 comments) | no | maybe — all satask prerequisites answer; needs rebase, `logcombine` study, split functions, more tests/maintainer bandwidth |
| #29173 | Assumptions: add refine handler for conjugate | conjugate | open (46 comments) | no | maybe — basic cases good; branch-cut rules had concrete wrong results and the reviewer now wants Lean-assisted verification; split basic rules only |
| #29183 | improve refine_abs to handle Add expressions | Abs | open (10) | no | maybe — some Add cases already work in master; needs a clear explanation of interaction with the generic path |
| #29203 | add refine handler for factorial | factorial | open draft (11) | no | low value per maintainer (constants only); could add negative-integer pole safely |
| #29213 | Adds a function to refine basic cases of binomial | binomial | open draft (2) | no | medium — small and answerable; revive with non-constant cases |
| #29324 | add refine handler for tan and cot | tan/cot | open (4) | no | yes — reviewer explicitly asked to share the `pi/2` parsing with `refine_sin_cos` instead of duplicating it; rebase needed |
| #29450 | fix AttributeError regression in refine_sin_cos | sin/cos fix | open (8) | no | yes — two-line `isinstance(pow_expr, Pow)` guard + tests; touches already-merged code |
| #29579 | add refine handler for Relational and support non-negative Pow | relational/ask | open (4) | no | no — relational part is dead code; the `NonNegativePredicate(Pow)` ask part should be split out and reviewed by the `ask` owners |
| #29800 | Fix/refine pow nested 29684 | Pow fix | open (3) | no | yes — fixes a real correctness bug (issue #29684); patch is focused and its own tests cover counterexamples |
| #29948 | add refine handler for sec and csc | sec/csc | open (3) | no | yes but duplicate of #29405; needs a trig-parsing refactor with #29324 |

Closed (10):

| PR | title | handler | merged? | landed in pinned? | note |
|---|---|---|---|---|---|
| #28873 | add `refine_sin_cos` | sin/cos | merged 2026-02-03 | **yes** (`refine.py:444-534`) | first success; 61 comments |
| #29276 | refine sin/cos with further simplification | sin/cos | merged 2026-03-09 | **yes** | parity aggregation |
| #29174 | refine handlers for floor and ceiling | floor/ceiling | merged 2026-02-25 | **yes** (`:565-602`) | 29 comments |
| #29325 | refine handler for Heaviside | Heaviside | merged 2026-03-06 | **yes** (`:537-562`) | |
| #29533 | Update `refine_sin_cos` to handle more simplifications | sin/cos | merged 2026-04-03 | **yes** | current pinned form |
| #29592 | add refine_exp handler for exp | exp | merged 2026-04-17 | **yes** (`:220-253`) | supersedes #29199 |
| #29199 | Fix refine(exp(...)) ignoring passed assumptions | exp | closed unmerged | no | superseded by #29592 |
| #29364 | Add `_eval_refine` for Piecewise | Piecewise | closed unmerged | no | **rejected**: right issue, wrong layer (`ask`/`lra_satask`) |
| #29132 | refine sqrt inequalities under real assumptions | inequalities | closed unmerged | no | out of scope; `ask` work |
| #27619 | Fix refine for expressions with Infinity in Add | Add | closed unmerged (2025) | no | stale: predates the current file layout (`handlers_dict` grew after it) |

### 5.2 Unlabeled and duplicate refine PRs (search: `refine in:title`, 66 results since 2025)

These do not carry the `assumptions.refine` label but cover the same handlers; most
are duplicates or one-day PRs. Grouped, most recent first:

| handler | open | closed unmerged | merged | notes |
|---|---|---|---|---|
| tan/cot | #29962, #29324 | #30073, #29941, #29317, #29302 | — | #29324 is the only reviewed attempt; #29941 predates it |
| sec/csc | #29948, #29405 | #29942 | — | two open duplicates |
| conjugate | #29994, #29173 | #30489, #30488, #29992, #29954, #29945 | — | five closed duplicates in 2026-06/09; #29173 is the substantive one |
| sinh/cosh/tanh | #30192, #30138 | — | — | both opened 2026-07/08, no reviews |
| Min/Max | #29406 | #30487, #29565, #29302, #27697 | — | #27697 is a 2025 test-only PR |
| frac | — | #30496, #30368, #29744 | — | three attempts, all closed |
| Mod | — | #30376, #29743, #29565 | — | |
| log | #29760, #29131 | — | — | #29760 is a newer duplicate of #29131 |
| factorial / binomial | #29203, #29213 | — | — | both drafts |
| refine_abs | #29183 | #29796 | — | |
| refine_sign (assumption bug) | #29605 | #29604, #29407 | — | same one-line fix attempted three times |
| refine_arg | #29409 | — | — | |
| sin/cos fixes | #29450, #29410 | #29486, #29399, #29397, #29395, #29103 | #28873, #29276, #29533 | merged lineage plus cleanup attempts |
| Pow | #29800 | #30248, #30474, #30476 | — | #30473 issue + two fixes for `Abs(z)**k` under `Q.imaginary` |
| relational/inequalities | #30325, #29579 | #29841, #29708 | — | all out of scope (`ask`) |
| exp | — | #29565, #29302 | #29592 | |
| Piecewise | — | #29364 | — | rejected |
| floor/ceiling | — | #29362 | #29174 | |
| Heaviside | — | — | #29325 | |
| grab bags | — | #29565, #29302, #29561 | — | multi-handler PRs rejected/superseded |

### 5.3 Maintainer signals

- Issue #27888 header: *"It's unlikely that I will review future PRs related to this
  issue atm. Do not ping people or email people to review your PRs."*
- TiloRC, 2026-06-24 on #29173: *"I think for now I'm not going to be reviewing PRs
  related to refine. I'm not sure if refine is even a good idea to begin with."*
  (He is exploring Lean-verified rewrite rules with the #29173 author instead.)
- oscarbenjamin, 2026-07-01 on #29948: *"I'm not going to review it."*
- #29174/#29325/#29592 landed quickly when a reviewer engaged; the bottleneck is review
  bandwidth and approach quality (branch-cut correctness, duplicated parsing), not the
  mechanics of adding a handler.
- Consequence for this project: a vendored copy is not "behind" in any active
  development flow; the upstream queue is effectively frozen for merge purposes. Our
  parity work should prioritize what upstream already has (the 4 matrix handlers) and
  what `satask` already supports.

## 6. Prioritized recommendations

### 6.1 For upstream SymPy

1. **Correctness first:** revive #29800 (`(x**a)**b` bug, issue #29684) and #29450
   (`refine_sin_cos` `AttributeError`). These are bugs in merged code, not new features.
2. **Smallest complete handlers:** Min/Max (#29406), frac (#30368), Mod (#30376),
   `KroneckerDelta`/`DiracDelta` (no PRs yet) — each is a handful of `ask` calls.
3. **Trig consolidation:** one shared `pi/2`-parsing helper used by `refine_sin_cos`,
   `refine_tan_cot` and `refine_sec_csc` (reviewer's explicit request on #29324); then
   rebase #29324/#29405/#29948 onto it.
4. **log:** revive #29131/#29760, but split rules into separate functions, study
   `logcombine`, and add negative tests for every omitted assumption (reviewer's asks).
5. **conjugate:** land the basic real/imag/integer-power rules separately from branch
   cuts; treat branch-cut rules as research (the Lean verification effort may subsume
   them).
6. **refine_sign assumption bug (#29605):** one-line fix plus tests; fails today for
   plain symbols because `assumptions` is dropped.
7. **Do not add** Piecewise/relational/inequality handlers (#29364/#29132/#29579
   direction); fix `ask`/LRA instead.
8. **Fold duplicates:** close #29760, #29962, #29994, #30138/#30192, #29405 in favor of
   one canonical PR per handler; the queue has 5 conjugate, 4 tan/cot, 3 sec/csc and
   4 frac attempts.

### 6.2 For this project's independent core

Ordered by value/effort:

1. **Port the 4 upstream matrix handlers** (`Transpose`, `Inverse`, `Determinant`,
   `MatMul`) into `handlers_dict`. `Determinant`/`MatMul` work verbatim; adapting
   `Transpose`/`Inverse` to ask the base matrix (`expr.arg`) makes all four work today
   (26/26 prototype checks). This is pure parity and the only upstream code our copy
   silently lacks. Watch the `Q.singular` path in `refine_Inverse`, which *raises* in
   upstream.
2. **Add handlers whose prerequisites satask already answers on `feature/refine`:**
   `log` (real inverse + power rule), `conjugate` (real/imag), `frac`, `Mod`,
   `factorial` (zero/pole/infinity), `binomial`, `Min`/`Max`, `DiracDelta`,
   `KroneckerDelta`, `gamma` (nonpositive-integer pole), `tan`/`cot` (zero/period),
   `sec`/`csc` (via `refine_sin_cos`), hyperbolic zero values and inverse compositions.
   These need no core work and lift the validation suite's handler surface.
3. **Fix/extend existing handlers:** `refine_sign` must pass `assumptions`
   (`reasoning/refine.py:425,430`); `refine_abs` zero case (`:116-121`) and Add args
   (needs 2a for the sign derivation); `refine_arg` imaginary/zero cases;
   `refine_Pow` nested-power bug and `Abs`-under-imaginary case.
4. **Land the 2a structural facts** (`agent/2a-add-mul-pow`, 82e4186) — they fix 2 of
   our 3 xfails with no handler changes (verified: `test_pow1`, `test_sin_cos`) and
   close 7/15 handler-prerequisite gaps. 2b (`fc0e6c6`, `3b34d49`) additionally supplies
   `Q.real(exp(x))`, needed by conjugate/log-like rules and the `test_sign` real path.
5. **Core work that would extend the handler ceiling:** matrix predicate closure
   (`symmetric(A.T)`/`orthogonal(A**-1)`/products, `integer_elements -> integer(X[i,j])`)
   to allow verbatim upstream ports and element-set refinements; reversed-order
   relations (`Q.le` from `Q.ge`) for inverse-trig ranges; old-assumption symbol bridge
   for the last two `test_sign` asserts.
6. **Explicitly skip:** Piecewise/relational handlers (the `Boolean._eval_refine` hook
   already reproduces upstream via SymPy `ask`), sets/calculus/number theory, and
   branch-cut-heavy conjugate/inverse-trig rules until the math is verified.

### 6.3 Tie-back to the 3 xfailed tests

| test | root cause | fix | verified |
|---|---|---|---|
| `test_pow1` (1 failing assert, `sqrt(1/x)`) | `ask(Q.real(x**-1), Q.positive(x))` missing | land 2a facts; no handler change | 20/20 on `agent/2a-add-mul-pow` and combined |
| `test_sin_cos` (1 failing assert, `cos(x+(2n+1)*pi+...)`) | Add parity `Q.odd(2*n+1)` / `Q.even(2*n+1)` missing | land 2a facts | 45/45 on `agent/2a-add-mul-pow` and combined |
| `test_sign` (4 failing asserts) | `refine_sign` drops `assumptions` (lines 5-6); old `imaginary=True` symbol (12-13) | handler fix for 5-6; 2d old-assumption bridge (or explicit `Q.imaginary(x)` in the test) for 12-13 | patched handler returns 1/-1 on all cores; 12-13 remain `sign(y)` |
