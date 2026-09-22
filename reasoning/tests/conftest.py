"""Shared fixtures for the refine-handler tests."""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from reasoning.tests.refine_harness import reference_ask as _reference_ask


@pytest.fixture
def reference_ask() -> Iterator[None]:
    """Run the local dispatcher with SymPy's ``ask`` bound."""
    with _reference_ask():
        yield
