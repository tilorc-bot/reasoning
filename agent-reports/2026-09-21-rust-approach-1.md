# Agent report: Approach 1 - Rust reasoning core over CaDiCaL

- **Date:** 2026-09-21
- **Status:** implemented, all mandatory gates pass; optional ClauseDB/Tseitin
  stretch not attempted
- **Branch/worktree:** `feature/rust-core` in `/home/tilo/reasoning-rust`
  (kept off `main`; nothing outside the worktree touched)
- **Scope:** `rust/` crate (`reasoning_core`, cdylib), `reasoning/rust_solver.py`,
  the `ReasoningEngine` solver hook, new benchmark/parity scripts and tests
- **Read this if:** you want the measured state of the Rust core, the remaining
  Python-side overhead, or the comparison against the Python CaDiCaL adapter
- **Stale after:** changes to `engine.py`'s construction path, the satask
  factbase sizes, or a ClauseDB move into Rust
- **TL;DR:** the Rust core is a drop-in `SATSolver` with exact parity (314 cases
  x 2 modes, 0 mismatches; validation outcome counts unchanged) and cuts
  `sum10` engine-only from **4.52 ms to 1.90 ms (2.38x)** and the full pipeline
  from **7.60 ms to 4.48 ms (1.70x)** in the benchmark harness. That is ~1.5-1.6x
  faster than the investigated Python CaDiCaL adapter on the same machine
  (`sum10` engine-only 3.15 ms), but it misses the aspirational
  `<=1.2 ms` engine-only / `<=3.5 ms` total targets. The remaining cost is
  Python-side buffer building and engine copies, not CaDiCaL: ~0.46 ms to
  flatten clauses, ~0.28 ms to cross the ABI, ~0.16 ms for the engine's clause
  copy, ~0.12 ms to build the model dict. Removing those needs the optional
  ClauseDB-in-Rust step.

## Acceptance gates

| # | Gate | Result |
| - | ---- | ------ |
| 1 | `cargo build --release` in `rust/` | **pass** - clean rebuild 5.30 s, `libreasoning_core.so` 1.9 MB; early smoke test printed `cadical-3.0.1-c607304` |
| 2 | `pytest reasoning/tests -q --tb=no` | **pass** - baseline (pre-change) 61 passed, 1 xfailed; after adding 8 Rust tests: default **69 passed, 1 xfailed** (0.99 s) and `REASONING_SOLVER=rust` **69 passed, 1 xfailed** (0.86 s) |
| 3 | `python -m benchmarks.rust_parity --random-cases 300` | **pass** - full SAT: 314 cases, **0 mismatches**; early_return: 314 cases, **0 mismatches** |
| 4 | `REASONING_SOLVER=rust pytest validation -q --tb=no` | **pass** - **68 failed, 26 passed, 8 xfailed, 2 xpassed**, WALL **47.18 s**; default run of the same command after the change: same counts, WALL **47.65 s** (pre-change baseline: 48.84 s). SymPy-bound, so the difference is noise |
| 5 | `python -m benchmarks.rust_compare --repeat 50 --solver-only` | **measured, targets missed** - see table; sum10 engine-only 1.90 ms (target ~1.2 ms), total 4.48 ms (target ~3.5 ms) |
| 6 | Default path unchanged without the Rust library | **pass** - with `rust/target` moved aside: `reasoning/tests` 61 passed, 1 skipped, 1 xfailed; `benchmarks.satask --repeat 25` runs (sum10 solve 4.66 ms / total 7.39 ms) |
| 7 | `python -m mypy` | **pass** - "Success: no issues found in 32 source files" |
| 8 | Missing-library behavior | **pass** - Rust tests skip (`1 skipped in 0.01 s`); `ReasoningEngine` under `REASONING_SOLVER=rust` raises a clear `ImportError` naming the build command and every path tried |

Gate 2's count is 69 rather than the 61 in the brief because the new
`reasoning/tests/test_rust_solver.py` adds 8 tests; the pre-change baseline was
re-measured at 61 passed / 1 xfailed before any edit.

## Measured comparison (this machine, same harness, `--repeat 50 --solver-only`)

### Full pipeline medians (ms)

| Case | Clauses | DPLL solve | Rust solve | DPLL total | Rust total | Total speedup | Solve speedup |
| ---- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| simple | 82 | 0.227 | 0.186 | 0.400 | 0.352 | 1.14x | 1.22x |
| nested | 456 | 1.605 | 0.778 | 2.807 | 1.975 | 1.42x | 2.06x |
| sum10 | 1161 | 4.517 | 1.893 | 7.599 | 4.483 | **1.70x** | **2.39x** |
| matrix | 26 | 0.119 | 0.120 | 0.229 | 0.226 | 1.01x | 1.00x |
| contradiction | 83 | 0.159 | 0.147 | 0.342 | 0.321 | 1.06x | 1.08x |

### Engine-only medians over a prebuilt database (ms)

| Case | DPLL | Rust core | Python CaDiCaL adapter | Rust vs DPLL | CaDiCaL vs DPLL | Rust vs CaDiCaL |
| ---- | ---: | ---: | ---: | ---: | ---: | ---: |
| simple | 0.227 | 0.189 | 0.246 | 1.20x | 0.97x | 1.30x |
| nested | 1.650 | 0.770 | 1.048 | 2.14x | 1.61x | 1.36x |
| sum10 | 4.518 | 1.899 | 3.146 | **2.38x** | 1.50x | **1.66x** |
| matrix | 0.122 | 0.126 | 0.139 | 0.97x | 0.91x | 1.10x |
| contradiction | 0.153 | 0.150 | 0.184 | 1.02x | 0.88x | 1.23x |

The Python CaDiCaL column was re-measured for this report with
`benchmarks.cadical_compare --repeat 50 --solver-only` in
`/home/tilo/reasoning-cadical` (read-only). The investigation's original
numbers were sum10 solve 4.659 / total 7.095 for DPLL and 5.598 total for
CaDiCaL; today's harness reproduces those within noise.

### Engine-only overhead breakdown (sum10, GC suppressed, medians)

| Step | Cost |
| ---- | ---: |
| Engine's clause copy (`[tuple(clause) ...]`) | ~0.16 ms |
| RustSolver: `list(clauses)` | 0.004 ms |
| RustSolver: maxvar from `variables` | 0.020 ms |
| RustSolver: flatten to `array('i')` | **0.458 ms** |
| RustSolver: ctypes buffer view | 0.004 ms |
| `rcore_new` (declare 367 vars) | 0.042 ms |
| `rcore_add_clauses` (normalize + 3.5k CaDiCaL adds) | 0.283 ms |
| `rcore_propagate` | 0.002 ms |
| base solve + bulk model + model dict | ~0.29 ms (ask) |
| query assume/solve | ~0.10 ms (ask) |

With GC enabled (the benchmark harness) the same sum10 engine-only segment
measures 1.9-2.2 ms; the spread is gen-0 collections triggered by the untimed
factbase rebuilds between samples.

## Architecture as implemented

- `rust/Cargo.toml` - package `reasoning_core`, `crate-type = ["cdylib"]`,
  `cc` build dependency.
- `rust/build.rs` - compiles `vendor/cadical_shim.cpp` as C++ with
  `-I vendor/cadical/src`, links `static=cadical` from
  `vendor/cadical/build` plus `dylib=stdc++`; paths derived from
  `CARGO_MANIFEST_DIR`, with `rerun-if-changed` on the shim and archive.
- `rust/src/lib.rs` - C ABI: `rcore_signature`, `rcore_new`, `rcore_free`,
  `rcore_add_clauses`, `rcore_add`, `rcore_propagate`, `rcore_fixed`,
  `rcore_assume`, `rcore_solve`, `rcore_val`, `rcore_model`. Rust owns clause
  normalization (literal dedupe, tautology drop), variable declaration
  (`ensure_variable` grows CaDiCaL when a literal exceeds `max_var`), session
  state, and all CaDiCaL calls. Clauses cross once per formula as one flat
  zero-terminated buffer; the model crosses once per SAT solve.
- `reasoning/rust_solver.py` - `RustSolver` with `variable_set`, `propagate`,
  `fixed`, `solve`, `val`, `assume`, `add`, `clause`, `copy`, returning
  `IpasirStatus`. The first `val()` after SAT fetches the whole model with one
  `rcore_model` call and caches it. Lazy library discovery:
  `$REASONING_CORE_LIB`, else `rust/target/release`, else `rust/target/debug`;
  a missing library raises a descriptive `ImportError`.
- `reasoning/engine.py` - added `default_solver_class()` (`$REASONING_SOLVER`
  unset/`dpll` -> `SATSolver`, `rust` -> `RustSolver`) and the optional
  `solver_class` argument. Default path is unchanged.
- `benchmarks/rust_compare.py`, `benchmarks/rust_parity.py`,
  `benchmarks/__init__.py` (needed so mypy resolves `benchmarks.satask` once),
  `reasoning/tests/test_rust_solver.py`.

## Optional stretch: not attempted

Moving `ClauseDB` + Tseitin compilation into Rust was left out. The existing
`test_clauses.py` asserts on Python objects (`db.encoding`, `db.symbols`,
`db.auxiliaries`, `db.data` as a list of sets), so a compatible class would
still materialize those per-atom structures in Python; without also teaching
`ReasoningEngine`/`RustSolver` to accept a prebuilt flat buffer, the measured
flatten cost would not drop. Doing it properly is a larger protocol change than
the remaining budget justified, and partial work would have risked the passing
mandatory gates.

## Blockers

None. The `<=1.2 ms` engine-only target is not met with the mandatory
architecture; the gap is understood and quantified above.

## Suggested next milestones

1. Rust-owned `ClauseDB` with a coarse flat compile protocol, plus an engine
   fast path that hands `RustSolver` a prebuilt clause buffer - eliminates the
   0.46 ms flatten and 0.16 ms engine copy, which should reach the original
   targets.
2. A `reasoning[rust]` packaging story (build the cdylib on demand) so the
   default install stays pure Python.
3. `benchmarks/rust_scaling.py` for hard instances, where the shared CaDiCaL
   search advantage over bundled DPLL is 20-150x (per the investigation).
4. Wire `RustSolver` into the validation outliers to confirm the 35x worst-ask
   improvement the Python adapter showed.
