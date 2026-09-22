"""Adversarial verification tests for the matrix refine handlers.

Independent verifier tests for ``reasoning/refine/handlers/matrix_*.py``.
They are deliberately hostile: scope/registration checks, wrong-assumption
negatives, ``None``-safety, scripted-ask robustness, fixed-point re-dispatch
and mathematical counterexamples.

Known defects are recorded as strict ``xfail`` markers with minimal repros in
the reason strings; they fail today and turn into errors if the defect is
fixed, forcing the marker to be revisited.  The MatrixElement off-diagonal
counterexamples found by this file were fixed; they are now regular
regression tests.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any

import pytest
from sympy import Matrix, Q, S, eye, simplify, sqrt
from sympy.abc import i, j, n, x
from sympy.assumptions.refine import refine as sympy_refine
from sympy.core.basic import Basic
from sympy.matrices.expressions import (
    HadamardProduct,
    Identity,
    MatAdd,
    MatMul,
    MatrixSymbol,
    Trace,
    ZeroMatrix,
)
from sympy.matrices.expressions.determinant import Determinant

from reasoning.refine import handlers as handlers_package
from reasoning.refine import handlers_dict, refine
from reasoning.tests.refine_harness import (
    assert_refines_like_sympy,
    recording_ask,
    scripted_ask,
    stub_ask,
    use_ask,
)

X = MatrixSymbol('X', 2, 2)
Y = MatrixSymbol('Y', 2, 2)
Z = MatrixSymbol('Z', 2, 2)
A = MatrixSymbol('A', 3, 3)
R = MatrixSymbol('R', 2, 3)
S3 = MatrixSymbol('S', 2, 3)

I2 = Identity(2)

ROT90 = Matrix([[0, -1], [1, 0]])
COMPLEX_UNITARY = (
    Matrix([[1, S.ImaginaryUnit], [S.ImaginaryUnit, 1]])
    / sqrt(2)
    * Matrix([[1, 0], [0, S.ImaginaryUnit]])
)

_EXPECTED_MODULES = {
    'Transpose': 'matrix_transpose',
    'Inverse': 'matrix_inverse',
    'Determinant': 'matrix_det',
    'MatMul': 'matrix_matmul',
    'Trace': 'matrix_trace',
    'MatAdd': 'matrix_matadd',
    'HadamardProduct': 'matrix_hadamard',
    'MatrixElement': 'matrix_element',
}

_ALL_HANDLER_CASES: list[tuple[Any, Any]] = [
    (X.T, Q.symmetric(X)),
    (X.I, Q.orthogonal(X)),
    (Determinant(X), Q.orthogonal(X)),
    (X.T * X, Q.orthogonal(X)),
    (X.conjugate() * X, Q.unitary(X)),
    (Trace(X), Q.zero(X)),
    (MatAdd(X, Y), Q.zero(Y)),
    (HadamardProduct(X, Y), Q.zero(X)),
    (A[0, 1], Q.diagonal(A)),
    (A[i, j], Q.diagonal(A)),
    (X[1, 0], Q.symmetric(X)),
]


# ---------------------------------------------------------------------------
# Scope and registration
# ---------------------------------------------------------------------------

def test_matrix_handler_keys_owned_by_their_modules() -> None:
    for key, module in _EXPECTED_MODULES.items():
        handler = handlers_dict[key]
        assert handler.__module__ == f'reasoning.refine.handlers.{module}', (
            key, handler.__module__
        )


def test_no_handler_key_is_registered_twice() -> None:
    package_file = handlers_package.__file__
    assert package_file is not None
    root = pathlib.Path(package_file).parent
    seen: dict[str, str] = {}
    for path in sorted(root.glob('*.py')):
        text = path.read_text(encoding='utf-8')
        for match in re.finditer(r"handlers_dict\[['\"](\w+)['\"]\]\s*=", text):
            key = match.group(1)
            assert key not in seen, (
                f'{key} registered in both {seen[key]} and {path.name}'
            )
            seen[key] = path.name
    for key in _EXPECTED_MODULES:
        assert key in seen


def test_handlers_consult_patchable_upstream_ask() -> None:
    fake, log = recording_ask({str(Q.symmetric(X)): True})
    with use_ask(fake):
        assert refine(X.T, Q.symmetric(X)) == X
    assert log and log[0][0] == Q.symmetric(X)


# ---------------------------------------------------------------------------
# Transpose
# ---------------------------------------------------------------------------

def test_transpose_positive() -> None:
    assert refine(X.T, Q.symmetric(X)) == X
    assert refine(A.T, Q.symmetric(A)) == A


def test_transpose_negative_wrong_assumptions() -> None:
    assert refine(X.T, Q.orthogonal(X)) == X.T
    assert refine(X.T, Q.unitary(X)) == X.T
    assert refine(X.T, Q.symmetric(Y)) == X.T
    assert refine(X.T, Q.real(x)) == X.T
    assert refine(X.T, True) == X.T


def test_transpose_diagonal_implies_symmetric() -> None:
    assert refine(X.T, Q.diagonal(X)) == X


def test_transpose_rectangular_symbols() -> None:
    assert refine(R.T, True) == R.T
    assert refine(R.T, Q.real(x)) == R.T
    assert refine(R.T, Q.symmetric(R)) == R
    assert sympy_refine(R.T, Q.symmetric(R)) == R


def test_transpose_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(X.T, Q.symmetric(X)) == X.T


def test_transpose_scripted_mixed_answers() -> None:
    for sequence in ([None], [False], [None, True], [True, False, None]):
        fake, _ = scripted_ask(sequence)
        with use_ask(fake):
            result = refine(X.T, Q.symmetric(X))
        assert result in (X, X.T)


def test_transpose_reference_ask_parity() -> None:
    assert_refines_like_sympy(X.T, Q.symmetric(X))
    assert_refines_like_sympy(X.T, Q.orthogonal(X))
    assert_refines_like_sympy(X.T, Q.symmetric(Y))
    assert_refines_like_sympy(X.T, True)


@pytest.mark.xfail(
    strict=True,
    reason=(
        'docstring claims the reference comparison holds because SymPy derives '
        'both directions; it does not: sympy_ask(Q.symmetric(X), Q.symmetric(X.T)) '
        'is None, so the port leaves X.T while pinned SymPy returns X'
    ),
)
def test_transpose_reference_ask_parity_on_transpose_assumption() -> None:
    assert_refines_like_sympy(X.T, Q.symmetric(X.T))


# ---------------------------------------------------------------------------
# Inverse
# ---------------------------------------------------------------------------

def test_inverse_positive() -> None:
    assert refine(X.I, Q.orthogonal(X)) == X.T
    assert refine(X.I, Q.unitary(X)) == X.conjugate()


def test_inverse_negative_wrong_assumptions() -> None:
    assert refine(X.I, Q.symmetric(X)) == X.I
    assert refine(X.I, Q.orthogonal(Y)) == X.I
    assert refine(X.I, Q.diagonal(X)) == X.I
    assert refine(X.I, Q.real(x)) == X.I
    assert refine(X.I, True) == X.I


def test_inverse_singular_raises() -> None:
    with pytest.raises(ValueError, match='Inverse of singular matrix'):
        refine(X.I, Q.singular(X))


def test_inverse_singular_raises_under_scripted_ask() -> None:
    fake, log = scripted_ask([False, False, True])
    with use_ask(fake):
        with pytest.raises(ValueError, match='Inverse of singular matrix'):
            refine(X.I, Q.singular(X))
    assert [entry[0] for entry in log] == [
        Q.orthogonal(X), Q.unitary(X), Q.singular(X),
    ]


def test_inverse_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(X.I, Q.orthogonal(X)) == X.I
        assert refine(X.I, Q.unitary(X)) == X.I
        assert refine(X.I, Q.singular(X)) == X.I


def test_inverse_reference_ask_parity() -> None:
    assert_refines_like_sympy(X.I, Q.orthogonal(X))
    assert_refines_like_sympy(X.I, Q.unitary(X))
    assert_refines_like_sympy(X.I, Q.symmetric(X))
    assert_refines_like_sympy(X.I, True)


def test_inverse_singular_divergence_from_upstream() -> None:
    # Documented: the port asks the base, so Q.singular(X) raises here while
    # upstream's undecidable Q.singular(X**-1) query leaves X**-1 unchanged.
    with pytest.raises(ValueError, match='Inverse of singular matrix'):
        refine(X.I, Q.singular(X))
    assert sympy_refine(X.I, Q.singular(X)) == X.I


@pytest.mark.xfail(
    strict=True,
    reason=(
        'documented arg-adjustment is incomplete: SymPy ask derives '
        'Q.orthogonal(X)/Q.unitary(X) from assumptions on X**-1, satask does '
        'not, so local leaves X**-1 while pinned SymPy refines it'
    ),
)
def test_inverse_reference_ask_parity_on_inverse_assumption() -> None:
    assert_refines_like_sympy(X.I, Q.orthogonal(X.I))
    assert_refines_like_sympy(X.I, Q.unitary(X.I))


@pytest.mark.xfail(
    strict=True,
    reason=(
        'inherited upstream bug: Q.unitary(U) -> U**-1 = U.conjugate() '
        '(elementwise conjugate) is false; minimal repro U = ROT90 gives '
        'conj(U) = ROT90 != ROT90.T, and COMPLEX_UNITARY gives conj(U) != U**-1'
    ),
)
def test_inverse_unitary_soundness_counterexample() -> None:
    refined = refine(X.I, Q.unitary(X))
    for sample in (ROT90, COMPLEX_UNITARY):
        assert _matrix_value(refined, sample) == _matrix_value(X.I, sample)


# ---------------------------------------------------------------------------
# Determinant
# ---------------------------------------------------------------------------

def test_determinant_positive() -> None:
    assert refine(Determinant(X), Q.orthogonal(X)) == S.One
    assert refine(Determinant(X), Q.singular(X)) == S.Zero
    assert refine(Determinant(X), Q.unit_triangular(X)) == S.One


def test_determinant_negative_wrong_assumptions() -> None:
    assert refine(Determinant(X), Q.symmetric(X)) == Determinant(X)
    assert refine(Determinant(X), Q.diagonal(X)) == Determinant(X)
    assert refine(Determinant(X), Q.triangular(X)) == Determinant(X)
    assert refine(Determinant(X), Q.invertible(X)) == Determinant(X)
    assert refine(Determinant(X), Q.real(x)) == Determinant(X)
    assert refine(Determinant(X), True) == Determinant(X)


def test_determinant_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        for assumption in (Q.orthogonal(X), Q.singular(X),
                           Q.unit_triangular(X)):
            assert refine(Determinant(X), assumption) == Determinant(X)


def test_determinant_ask_order() -> None:
    fake, log = recording_ask({str(Q.unit_triangular(X)): True})
    with use_ask(fake):
        assert refine(Determinant(X), Q.unit_triangular(X)) == S.One
    assert [entry[0] for entry in log] == [
        Q.orthogonal(X), Q.singular(X), Q.unit_triangular(X),
    ]


def test_determinant_reference_ask_parity() -> None:
    assert_refines_like_sympy(Determinant(X), Q.orthogonal(X))
    assert_refines_like_sympy(Determinant(X), Q.singular(X))
    assert_refines_like_sympy(Determinant(X), Q.unit_triangular(X))
    assert_refines_like_sympy(Determinant(X), Q.diagonal(X))
    assert_refines_like_sympy(Determinant(X), True)


# ---------------------------------------------------------------------------
# MatMul
# ---------------------------------------------------------------------------

def test_matmul_orthogonal_positive() -> None:
    assert refine(X.T * X, Q.orthogonal(X)).doit() == I2
    assert refine(2 * X.T * X, Q.orthogonal(X)) == 2 * I2


def _matrix_value(expr: Any, sample: Any) -> Any:
    value = expr.subs(X, sample).doit()
    if hasattr(value, 'as_explicit'):
        value = value.as_explicit()
    return simplify(value)


def test_matmul_multifactor_orthogonal_cancellation() -> None:
    assumptions = Q.orthogonal(X) & Q.orthogonal(Y)
    cases: list[tuple[Any, Any]] = [
        (X.T * X * Y, Y),
        (Y * X.T * X, Y),
        (X.T * Y.T * Y * X, X.T * X),
    ]
    for expr, expected in cases:
        refined = refine(expr, assumptions)
        assert refined.doit() == expected
        assert refine(refined, assumptions) == refined


def test_matmul_orthogonal_numeric_soundness() -> None:
    expr = X.T * X
    refined = refine(expr, Q.orthogonal(X))
    assert _matrix_value(refined, ROT90) == eye(2)
    assert _matrix_value(expr, ROT90) == eye(2)


def test_matmul_orthogonal_orientation_gap_is_documented() -> None:
    # satask cannot derive Q.orthogonal(X.T) from Q.orthogonal(X), so the
    # pinned docstring example X*X.T does not cancel locally even though the
    # handler is a verbatim port; pinned SymPy returns I.
    assert refine(X * X.T, Q.orthogonal(X)) == X * X.T
    assert sympy_refine(X * X.T, Q.orthogonal(X)).doit() == I2


def test_matmul_negative_wrong_assumptions() -> None:
    assert refine(X.T * X, Q.unitary(X)) == X.T * X
    assert refine(X.T * Y, Q.orthogonal(X) & Q.orthogonal(Y)) == X.T * Y
    assert refine(X.T * X, Q.real(x)) == X.T * X
    assert refine(X.T * X, True) == X.T * X


def test_matmul_symmetric_refines_factor_first() -> None:
    # The Transpose handler rewrites X.T -> X under Q.symmetric(X); the
    # resulting one-argument-product-free MatMul(X, X) is sound and is the
    # fixed point (MatMul(X, X).doit() == X**2).
    result = refine(X.T * X, Q.symmetric(X))
    assert result == MatMul(X, X)
    assert result.doit() == X**2
    assert refine(result, Q.symmetric(X)) == result


def test_matmul_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(X.T * X, Q.orthogonal(X)) == X.T * X
        assert refine(X.conjugate() * X, Q.unitary(X)) == X.conjugate() * X


def test_matmul_scripted_mixed_answers() -> None:
    for sequence in ([None, None], [False, True], [True, False, None],
                     [None, False]):
        for expr in (X.T * X, X.conjugate() * X):
            fake, _ = scripted_ask(sequence)
            with use_ask(fake):
                result = refine(expr, Q.orthogonal(X) & Q.unitary(X))
            assert isinstance(result, Basic)


def test_matmul_scalar_interleaving_preserves_value() -> None:
    expr = MatMul(X.T, 2, X)
    refined = refine(expr, Q.orthogonal(X))
    assert simplify(refined.subs(X, ROT90).doit()) == 2 * I2
    plain = MatMul(X, 2, Y)
    assert refine(plain, True) == sympy_refine(plain, True) == 2 * X * Y


def test_matmul_rectangular_unchanged_under_satisfiable_assumptions() -> None:
    assert refine(R * R.T, True) == R * R.T
    assert refine(R * R.T, Q.orthogonal(Y)) == R * R.T
    assert refine(R.T * R, Q.real(x)) == R.T * R


@pytest.mark.xfail(
    strict=True,
    reason=(
        'inherited upstream bug: Q.unitary(U) -> conj(U)*U = I is false; '
        'minimal repro U = ROT90 gives conj(U)*U = -I, COMPLEX_UNITARY gives '
        'a non-identity product'
    ),
)
def test_matmul_unitary_soundness_counterexample() -> None:
    expr = X.conjugate() * X
    refined = refine(expr, Q.unitary(X))
    for sample in (ROT90, COMPLEX_UNITARY):
        assert _matrix_value(refined, sample) == _matrix_value(expr, sample)


# ---------------------------------------------------------------------------
# Trace
# ---------------------------------------------------------------------------

def test_trace_positive() -> None:
    assert refine(Trace(X), Q.zero(X)) == S.Zero
    assert refine(Trace(X), Q.zero(X) & Q.diagonal(X)) == S.Zero


def test_trace_mixed_zero_and_unknown_terms() -> None:
    assert refine(Trace(MatAdd(X, Y)), Q.zero(X)) == Trace(Y)
    assert refine(Trace(MatAdd(X, Y)), Q.zero(Y)) == Trace(X)
    # The MatAdd rule collapses the sum to ZeroMatrix; satask does not know
    # ZeroMatrix is zero, so the Trace handler leaves Trace(0), which is the
    # mathematically correct value once evaluated.
    assert refine(Trace(MatAdd(X, Y)), Q.zero(X) & Q.zero(Y)).doit() == S.Zero


def test_trace_negative_wrong_assumptions() -> None:
    assert refine(Trace(X), Q.diagonal(X)) == Trace(X)
    assert refine(Trace(X), Q.singular(X)) == Trace(X)
    assert refine(Trace(X), Q.orthogonal(X)) == Trace(X)
    assert refine(Trace(X), Q.zero(Y)) == Trace(X)
    assert refine(Trace(X), True) == Trace(X)


def test_trace_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(Trace(X), Q.zero(X)) == Trace(X)


def test_trace_scripted_mixed_answers() -> None:
    for sequence in ([None], [False], [None, True], [True, False, None]):
        fake, _ = scripted_ask(sequence)
        with use_ask(fake):
            result = refine(Trace(X), Q.zero(X))
        assert result in (Trace(X), S.Zero)


# ---------------------------------------------------------------------------
# MatAdd
# ---------------------------------------------------------------------------

def test_matadd_positive_and_shape() -> None:
    assert refine(MatAdd(X, Y), Q.zero(Y)) == X
    assert refine(MatAdd(X, Y, Z), Q.zero(Y)) == X + Z
    assert refine(MatAdd(X, Y), Q.zero(X) & Q.zero(Y)) == ZeroMatrix(2, 2)
    assert refine(MatAdd(R, S3), Q.zero(R) & Q.zero(S3)) == ZeroMatrix(2, 3)


def test_matadd_unknown_terms_preserved() -> None:
    result = refine(MatAdd(X, Y, Z), Q.zero(Y))
    assert result == X + Z
    assert X in result.args
    assert Z in result.args
    assert Y not in result.args


def test_matadd_single_term() -> None:
    assert refine(MatAdd(X), True) == MatAdd(X)
    assert refine(MatAdd(X), Q.zero(X)) == ZeroMatrix(2, 2)


def test_matadd_negative_wrong_assumptions() -> None:
    assert refine(MatAdd(X, Y), Q.diagonal(Y)) == MatAdd(X, Y)
    assert refine(MatAdd(X, Y), Q.zero(Z)) == MatAdd(X, Y)
    assert refine(MatAdd(X, Y), Q.singular(Y)) == MatAdd(X, Y)
    assert refine(MatAdd(X, Y), True) == MatAdd(X, Y)


def test_matadd_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(MatAdd(X, Y), Q.zero(Y)) == MatAdd(X, Y)
        assert refine(MatAdd(X, Y, Z), Q.zero(Y)) == MatAdd(X, Y, Z)


def test_matadd_scripted_mixed_answers() -> None:
    for sequence in ([None, None], [True, None], [None, True, False]):
        fake, _ = scripted_ask(sequence)
        with use_ask(fake):
            result = refine(MatAdd(X, Y), Q.zero(Y))
        assert isinstance(result, Basic)


# ---------------------------------------------------------------------------
# HadamardProduct
# ---------------------------------------------------------------------------

def test_hadamard_positive() -> None:
    assert refine(HadamardProduct(X, Y), Q.zero(Y)) == ZeroMatrix(2, 2)
    assert refine(HadamardProduct(X, Y, Z), Q.zero(Z)) == ZeroMatrix(2, 2)
    assert refine(HadamardProduct(R, S3), Q.zero(S3)) == ZeroMatrix(2, 3)
    assert (refine(HadamardProduct(X, Y), Q.zero(X) & Q.zero(Y))
            == ZeroMatrix(2, 2))


def test_hadamard_negative_wrong_assumptions() -> None:
    assert (refine(HadamardProduct(X, Y), Q.diagonal(Y))
            == HadamardProduct(X, Y))
    assert (refine(HadamardProduct(X, Y), Q.zero(Z))
            == HadamardProduct(X, Y))
    assert (refine(HadamardProduct(X, Y), Q.singular(Y))
            == HadamardProduct(X, Y))
    assert refine(HadamardProduct(X, Y), True) == HadamardProduct(X, Y)


def test_hadamard_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert (refine(HadamardProduct(X, Y), Q.zero(X))
                == HadamardProduct(X, Y))


def test_hadamard_scripted_mixed_answers() -> None:
    for sequence in ([None, None], [False, True], [None, False, True]):
        fake, _ = scripted_ask(sequence)
        with use_ask(fake):
            result = refine(HadamardProduct(X, Y), Q.zero(X))
        assert isinstance(result, Basic)


# ---------------------------------------------------------------------------
# MatrixElement
# ---------------------------------------------------------------------------

def test_matrixelement_zero_matrix_positive() -> None:
    assert refine(X[0, 1], Q.zero(X)) == S.Zero
    assert refine(X[0, 0], Q.zero(X)) == S.Zero
    assert refine(A[i, j], Q.zero(A)) == S.Zero
    assert refine(A[n, 2 * n], Q.zero(A)) == S.Zero
    assert refine(R[0, 1], Q.zero(R)) == S.Zero


def test_matrixelement_diagonal_literal_indices() -> None:
    assert refine(A[0, 1], Q.diagonal(A)) == S.Zero
    assert refine(A[1, 0], Q.diagonal(A)) == S.Zero
    assert refine(A[0, 2], Q.diagonal(A)) == S.Zero
    assert refine(A[2, 0], Q.diagonal(A)) == S.Zero


def test_matrixelement_diagonal_same_index_unchanged() -> None:
    assert refine(A[0, 0], Q.diagonal(A)) == A[0, 0]
    assert refine(A[1, 1], Q.diagonal(A)) == A[1, 1]
    assert refine(A[i, i], Q.diagonal(A)) == A[i, i]
    assert refine(A[i, i], Q.symmetric(A)) == A[i, i]


def test_matrixelement_diagonal_provably_distinct_offset_symbol() -> None:
    assert refine(A[i, i + 1], Q.diagonal(A)) == S.Zero
    assert refine(A[i + 1, i], Q.diagonal(A)) == S.Zero


def test_matrixelement_mixed_literal_symbol_not_distinct() -> None:
    assert refine(A[0, i], Q.diagonal(A)) == A[0, i]
    assert refine(A[1, i], Q.diagonal(A)) == A[1, i]
    assert refine(A[i, 0], Q.diagonal(A)) == A[0, i]


def test_matrixelement_out_of_range_like_literals() -> None:
    assert refine(X[-1, 0], Q.diagonal(X)) == S.Zero
    assert refine(X[-1, -1], Q.diagonal(X)) == X[-1, -1]


def test_matrixelement_symmetric_swap_kept() -> None:
    assert refine(X[1, 0], Q.symmetric(X)) == X[0, 1]
    assert refine(X[0, 1], Q.symmetric(X)) == X[0, 1]
    assert_refines_like_sympy(X[1, 0], Q.symmetric(X))
    assert_refines_like_sympy(X[0, 1], Q.symmetric(X))
    assert_refines_like_sympy(A[i, i], Q.diagonal(A))


def test_matrixelement_diagonal_rule_is_an_extension() -> None:
    assert sympy_refine(A[0, 1], Q.diagonal(A)) == A[0, 1]
    assert refine(A[0, 1], Q.diagonal(A)) == S.Zero


def test_matrixelement_none_answers_unchanged() -> None:
    with use_ask(stub_ask({})):
        assert refine(A[0, 1], Q.diagonal(A)) == A[0, 1]
        assert refine(A[i, j], Q.diagonal(A)) == A[i, j]
        assert refine(X[0, 1], Q.zero(X)) == X[0, 1]
        assert refine(X[1, 0], Q.symmetric(X)) == X[1, 0]


def test_matrixelement_scripted_mixed_answers() -> None:
    for sequence in ([None, None, None], [None, None, True],
                     [True, None, None], [False, True, None]):
        fake, _ = scripted_ask(sequence)
        with use_ask(fake):
            result = refine(A[1, 0], Q.diagonal(A))
        assert isinstance(result, Basic)


def test_matrixelement_symbolic_indices_not_zero() -> None:
    # Independent symbols are not provably distinct: at i = j = 0 with A = I3
    # the true element is 1, so no off-diagonal zero may be emitted.
    for expr in (A[i, j], A[j, i]):
        refined = refine(expr, Q.diagonal(A))
        assert refined.subs({i: 0, j: 0}).subs(A, Identity(3)).doit() == 1


def test_matrixelement_vanishing_symbolic_indices_not_zero() -> None:
    # n and 2*n can coincide at n = 0, so the index pair is not distinct.
    refined = refine(A[n, 2 * n], Q.diagonal(A))
    assert refined.subs(n, 0).subs(A, Identity(3)).doit() == 1


# ---------------------------------------------------------------------------
# Robustness: fixed points, None-safety, no spurious raises
# ---------------------------------------------------------------------------

def test_redispatch_is_a_fixed_point() -> None:
    for expr, assumption in _ALL_HANDLER_CASES:
        once = refine(expr, assumption)
        assert refine(once, assumption) == once, (expr, assumption, once)


def test_all_none_answers_leave_matrix_handlers_unchanged() -> None:
    with use_ask(stub_ask({})):
        for expr, assumption in _ALL_HANDLER_CASES:
            assert refine(expr, assumption) == expr, (expr, assumption)


def test_scripted_mixed_answers_never_raise() -> None:
    sequences: list[list[bool | None]] = [
        [None, True, False],
        [False, None, True],
        [True, False, None, True],
        [None, None, None, None],
    ]
    for expr, assumption in _ALL_HANDLER_CASES:
        for sequence in sequences:
            fake, _ = scripted_ask(sequence)
            with use_ask(fake):
                try:
                    result = refine(expr, assumption)
                except ValueError:
                    # The singular-Inverse path is the one documented raise.
                    assert expr == X.I
                    continue
            assert isinstance(result, Basic)


def test_no_matrix_handler_raises_on_normal_inputs() -> None:
    cases: list[tuple[Any, Any]] = [
        (X.T, Q.symmetric(X)),
        (X.T, Q.orthogonal(X)),
        (X.I, Q.orthogonal(X)),
        (X.I, Q.unitary(X)),
        (X.I, Q.symmetric(X)),
        (X.I, True),
        (Determinant(X), Q.orthogonal(X)),
        (Determinant(X), Q.singular(X)),
        (Determinant(X), Q.unit_triangular(X)),
        (X.T * X, Q.orthogonal(X)),
        (X.T * Y, Q.orthogonal(X)),
        (Trace(X), Q.zero(X)),
        (MatAdd(X, Y), Q.zero(Y)),
        (HadamardProduct(X, Y), Q.zero(X)),
        (A[0, 1], Q.diagonal(A)),
        (A[i, j], Q.zero(A)),
        (X[1, 0], Q.symmetric(X)),
    ]
    for expr, assumption in cases:
        result = refine(expr, assumption)
        assert isinstance(result, Basic)


def test_singular_inverse_is_the_only_raising_path() -> None:
    raising: list[tuple[Any, Any, Exception]] = []
    for expr, assumption in _ALL_HANDLER_CASES:
        try:
            refine(expr, assumption)
        except Exception as exc:  # noqa: BLE001 - record, do not hide
            raising.append((expr, assumption, exc))
    assert raising == []
    with pytest.raises(ValueError, match='Inverse of singular matrix'):
        refine(X.I, Q.singular(X))


def test_complex_unitary_sample_is_actually_unitary() -> None:
    assert simplify(COMPLEX_UNITARY.H * COMPLEX_UNITARY) == eye(2)
    assert simplify(ROT90.T * ROT90) == eye(2)
