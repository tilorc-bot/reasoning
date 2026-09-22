"""Warn before timing runs when CPUs are already busy.

ASV records benchmark timings without checking whether other work is using the
machine.  This module is loaded as an asv plugin (``plugins`` in
``asv.conf.json``), so its :func:`setup` hook runs in the asv process before
``asv run`` or ``asv continuous`` start their benchmarks, and its warning is
visible without ``--show-stderr``.

On Linux the check samples ``/proc/stat`` twice and counts the CPUs that were
busy for at least :data:`BUSY_FRACTION` of the interval.  One or two busy CPUs
produce a note that the load may not matter much; more than
:data:`MANY_BUSY_CPUS` produce a stronger warning.  Platforms without
``/proc/stat`` fall back to the aggregate 1-minute load average.  The check is
advisory: it never delays or fails the run.

The plugin must be importable from the working directory as
``asvbench.loadcheck``; run asv from the repository root, as ``asv.conf.json``
expects anyway.
"""
from __future__ import annotations

import os
import sys
import time

TIMING_COMMANDS = frozenset({"run", "continuous"})
SAMPLE_SECONDS = 0.2
BUSY_FRACTION = 0.5
MANY_BUSY_CPUS = 2
WARN_LOAD_PER_CPU = 0.5


def _cpu_count() -> int:
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:  # Not Linux.
        return os.cpu_count() or 1


def _read_proc_stat() -> list[tuple[int, int]] | None:
    """Per-CPU ``(total, idle)`` jiffy counters, or ``None`` off Linux."""
    try:
        with open("/proc/stat", "rb") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    samples = []
    for line in lines:
        if not line.startswith(b"cpu") or line.startswith(b"cpu "):
            continue
        fields = [int(value) for value in line.split()[1:]]
        if len(fields) < 5:
            continue
        total = sum(fields[:8])
        idle = fields[3] + fields[4]
        samples.append((total, idle))
    return samples or None


def _busy_fractions(interval: float) -> list[float] | None:
    """Busy fraction per CPU over ``interval`` seconds, or ``None``."""
    first = _read_proc_stat()
    if first is None:
        return None
    time.sleep(interval)
    second = _read_proc_stat()
    if second is None or len(second) != len(first):
        return None
    fractions = []
    for (total1, idle1), (total2, idle2) in zip(first, second):
        total = total2 - total1
        idle = idle2 - idle1
        fractions.append(0.0 if total <= 0 else 1.0 - idle / total)
    return fractions


def _load_averages() -> tuple[float, float, float] | None:
    try:
        return os.getloadavg()
    except (AttributeError, OSError):  # Not available on this platform.
        return None


def _timing_command() -> str | None:
    return next((arg for arg in sys.argv[1:] if arg in TIMING_COMMANDS), None)


def _report_busy_cpus(fractions: list[float]) -> bool:
    busy = sum(1 for fraction in fractions if fraction >= BUSY_FRACTION)
    if busy == 0:
        return False
    sample = (f"{busy} of {len(fractions)} CPUs were busy "
              f"(at least {BUSY_FRACTION:.0%} during a {SAMPLE_SECONDS:g} s sample)")
    if busy > MANY_BUSY_CPUS:
        print(f"asv load check: {sample}; timing results may be unreliable "
              f"while other work runs.", file=sys.stderr)
    else:
        print(f"asv load check: {sample}; this may not matter much if the "
              f"benchmarks do not contend for those CPUs.", file=sys.stderr)
    return True


def _report_load_average() -> bool:
    averages = _load_averages()
    if averages is None:
        return False
    cpus = _cpu_count()
    one, five, fifteen = averages
    if one < WARN_LOAD_PER_CPU * cpus:
        return False
    print(
        f"asv load check: system load (1/5/15 min) is "
        f"{one:.2f}/{five:.2f}/{fifteen:.2f} on {cpus} CPU(s), "
        f"{one / cpus:.2f} per CPU at 1 min; "
        f"timing results may be unreliable while other work runs.",
        file=sys.stderr,
    )
    return True


def check_load() -> bool:
    """Print a warning if CPUs look busy; return whether it did."""
    if _timing_command() is None:
        return False
    fractions = _busy_fractions(SAMPLE_SECONDS)
    if fractions is not None:
        return _report_busy_cpus(fractions)
    return _report_load_average()


def setup() -> None:
    """asv plugin hook, run when asv imports this module."""
    check_load()
