# Agent report: a soundness fuzzer for satask handlers

- **Date:** 2026-09-22
- **Status:** tool implemented on branch `agent/handler-fuzzer` (based on `main`
  `29cca2e`); no handler code touched
- **Scope:** `tools/check_soundness.py`, `reasoning/tests/test_check_soundness.py`,
  `pyproject.toml` (adds `hypothesis` to the dev extra), and the README
  validation section
- **Read this if:** you are adding or auditing handler facts and want to know
  whether a definite `satask` answer is true, not just whether it matches a
  validation expectation
- **Stale after:** changes to `reasoning/satask.py`'s answer semantics, the
  model value pools, or the curated regression list
- **TL;DR:** the validation suites measure how many queries get answered; this
  tool checks whether the answers are sound. It catches the T1 and T2
  unsoundness on `cde5c70` and found a new one on `agent/tail-audits`:
  `satask(Q.zero(x), ~Q.complex(1/x))` returns `False`, but `x = 0` satisfies
  the assumption and makes the proposition true.

## What it does

`tools/check_soundness.py` generates queries (a curated regression list plus
random queries) and checks each definite answer against two oracles:

1. **Concrete models.** Each symbol is assigned a value, the assumptions are
   evaluated with `sympy.ask` on the ground atoms, and only satisfying
   assignments are kept. A definite answer contradicted by any model is
   unsound.
2. **`sympy.ask`.** When `ask` returns a definite answer for the same query and
   `satask` returns the opposite, the result is reported.

It also reports assumptions that raise `Inconsistent assumptions` even though a
model exists, and propositions whose negation gets the same definite answer.
Missing deductions (`None` where `ask` is definite) are expected while handlers
are being added and are not findings.

Some handlers deliberately mirror SymPy rules that a concrete model can
contradict, such as the closed-group rule that a sum of imaginary arguments is
imaginary even when the sum cancels. A model counterexample is therefore only
reported when `sympy.ask` does not return the same definite answer; `--strict`
reports those upstream-shared counterexamples as well.

## Hypothesis engine

Random queries come from Hypothesis by default. The `hypothesis_cases`
strategy draws a model first and then builds assumptions that hold under it, so
every generated query has a satisfying assignment and nothing is rejected.
Findings are shrunk to a minimal example; the stub-driven smoke test shrinks an
always-wrong solver down to `Q.zero(x)` under `Q.zero(x)` with `x = 0`.
`--engine random` keeps the seedable stdlib generator, which reports every
finding in one run instead of one minimized example per run.

## Usage

The script imports `reasoning` from the environment, so point `PYTHONPATH` at a
checkout to audit its handlers:

```console
.venv/bin/python tools/check_soundness.py
PYTHONPATH=/path/to/worktree .venv/bin/python tools/check_soundness.py \
    --cases 200
.venv/bin/python tools/check_soundness.py --engine random --seed 7
```

Exit status is 1 when a finding is reported. `--early-return` also audits
`early_return=True` answers, `--no-oracle` drops the `ask` comparison,
`--derandomize` fixes the Hypothesis seed, and `--no-matrices` / `--no-relations`
narrow the generator.

## Results

| Checkout | Queries | Findings | Upstream-shared |
|---|---|---|---|
| `cde5c70` (pre T1/T2 fix), curated | 12 | 2 (T1, T2) | 1 |
| `cde5c70`, 200 Hypothesis examples | 212 | 3 (T1, T2, Pow complex) | 1 |
| `main` `29cca2e`, curated | 12 | 0 | 0 |
| `agent/tail-audits` `67fb3ed`, curated | 12 | 1 (Pow complex) | 2 |
| `agent/tail-audits`, seeds 2-5, 100 random each | 412 | 0 | 1 per run |
| `agent/tail-audits`, seed 21 with matrices | 70 | 0 | 1 |

The T1 and T2 findings on `cde5c70` are exactly the bugs fixed by
`agent/tail-hermitian` and `agent/tail-positive`: `satask` returned `False` for
`Q.hermitian(x + I)` under `Q.imaginary(x)` (witness `x = -I`) and for
`Q.positive(x**I)` under `Q.positive(x)` (witness `x = exp(2*pi)`). T3
(`algebraic(exp(x)) | algebraic(x)`) is not flagged because plain `satask`
already returns `None`; the bug only appears under the validation harness's
`_exp_is_pow(True)` mode, which the fuzzer does not set.

## New finding: `~Q.complex(1/x)` implies `~Q.zero(x)`

Reproduces on `agent/tail-audits` `67fb3ed` and, without the new Pow closure,
not on `main`:

```python
satask(Q.complex(1/x), Q.complex(x))      # True, but x = 0 gives zoo
satask(Q.zero(x), ~Q.complex(1/x))        # False, but x = 0 satisfies the assumption
sympy.ask(Q.zero(x), ~Q.complex(1/x))     # None
```

Chain: the Pow closure `allargs complex -> complex(expr)` has no nonzero-base
guard, so `complex(x) -> complex(1/x)`. Contraposition gives
`~complex(1/x) -> ~complex(x)`, and `~complex(x) -> ~real(x) -> ~zero(x)`, so
`Q.zero(x)` is answered `False`. `ask` also returns `True` for
`Q.complex(1/x)` under `Q.complex(x)`, so that over-inference alone is
upstream-shared and only shows under `--strict`; the `~zero(x)` consequence is
not shared and is reported. Both curated cases are in the regression list.

## Caveats

- Model coverage is finite. The value pools include the witnesses for the known
  bugs (`-I`, `exp(2*pi)`, `0`), but a new bug whose only witness is outside the
  pool will be missed.
- The Hypothesis engine reports one minimized example per run and stops there;
  the random engine is available when all findings in a run are wanted.
- Cases whose ground atoms are unknown to `ask` are skipped and counted in the
  summary. The random engine skips roughly half of its queries at the default
  `--model-tries 200`; the Hypothesis engine does not skip.
- Relation assumptions are restricted to real operands, so complex comparisons
  do not abort model search.

## Next steps

- Fix the Pow complex closure by guarding it with a nonzero base, then confirm
  the curated case flips to passing.
- Run the fuzzer against each tail/matrix worktree before merging handler
  changes; `--strict` gives the upstream-shared list for review.
- A fixed-seed Hypothesis run (`--cases 50 --derandomize`, about 10s) can gate
  CI once the Pow finding is fixed; wiring it before then would turn `main` red
  as soon as the tail-audit handlers merge.
