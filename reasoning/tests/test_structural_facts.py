from __future__ import annotations

from sympy import I, Q, oo, pi, sqrt, symbols
from sympy.core.numbers import Rational

from reasoning.satask import satask

x, y, z = symbols('x y z')


def test_add_closure_facts() -> None:
    assert satask(Q.real(x + y), Q.real(x) & Q.real(y)) is True
    assert satask(Q.real(x + I), Q.real(x)) is False
    assert satask(Q.real(x + y), Q.imaginary(x) & Q.real(y)) is False

    assert satask(Q.complex(x + y), Q.complex(x) & Q.complex(y)) is True
    assert satask(Q.complex(x + I), Q.imaginary(x)) is True

    assert satask(Q.rational(x + y), Q.rational(x) & Q.rational(y)) is True
    assert satask(Q.rational(x + pi), Q.rational(x)) is False
    assert satask(Q.integer(x + y), Q.integer(x) & Q.integer(y)) is True
    assert satask(Q.integer(x + Rational(1, 2)), Q.integer(x)) is False
    assert satask(Q.algebraic(x + pi), Q.algebraic(x)) is False

    assert satask(Q.hermitian(x + 1), Q.imaginary(x)) is False
    assert satask(Q.antihermitian(x + I), Q.imaginary(x)) is True


def test_add_sign_parity_and_imaginary_facts() -> None:
    assert satask(Q.positive(x + 1), Q.positive(x)) is True
    assert satask(Q.negative(x + y), Q.negative(x) & Q.nonpositive(y)) is True
    assert satask(Q.nonzero(x + y), Q.positive(x) & Q.positive(y)) is True

    assert satask(Q.odd(x + 1), Q.even(x)) is True
    assert satask(Q.even(x + 1), Q.odd(x)) is True
    assert satask(Q.odd(x + y), Q.odd(x) & Q.odd(y)) is False
    assert satask(Q.odd(x + y + z), Q.odd(x) & Q.odd(y) & Q.even(z)) is False

    assert satask(Q.imaginary(x + I), Q.real(x)) is False
    assert satask(Q.imaginary(x + I), Q.imaginary(x)) is True
    assert satask(Q.imaginary(x + y), Q.imaginary(x) & Q.real(y)) is False
    assert satask(Q.imaginary(x + y + z),
                  Q.real(x) & Q.imaginary(y) & Q.imaginary(z)) is False


def test_mul_sign_and_parity_facts() -> None:
    assert satask(Q.negative(-x), Q.positive(x)) is True
    assert satask(Q.negative(-x), ~Q.positive(x)) is None
    assert satask(Q.positive(2*x), Q.positive(x)) is True
    assert satask(Q.negative(x*y), Q.positive(x) & Q.negative(y)) is True
    assert satask(Q.negative(x*y), Q.positive(x) & Q.positive(y)) is False

    assert satask(Q.even(x*y), Q.even(x) & Q.odd(y)) is True
    assert satask(Q.odd(x*y), Q.odd(x) & Q.odd(y)) is True
    assert satask(Q.odd(x*y), Q.even(x) & Q.odd(y)) is False
    assert satask(Q.odd(x*(x + y)), Q.integer(x) & Q.odd(y)) is False
    assert satask(Q.odd(x*(x + y)), Q.integer(x) & Q.even(y)) is None


def test_mul_closure_and_imaginary_facts() -> None:
    assert satask(Q.rational(2*x), Q.rational(x)) is True
    assert satask(Q.rational(2*x), Q.irrational(x)) is False
    assert satask(Q.algebraic(2*pi)) is False
    assert satask(Q.complex(x*y), Q.complex(x) & Q.complex(y)) is True

    assert satask(Q.imaginary(I*x), Q.imaginary(x)) is False
    assert satask(Q.imaginary(x*y), Q.imaginary(x) & Q.real(y)) is None
    assert satask(Q.imaginary(x*y), Q.imaginary(x) & Q.imaginary(y)) is False
    assert satask(Q.hermitian(I*x), Q.imaginary(x)) is True


def test_pow_real_and_rational_facts() -> None:
    assert satask(Q.real(x**2), Q.real(x)) is True
    assert satask(Q.real(sqrt(x)), Q.negative(x)) is False
    assert satask(Q.real(x**y), Q.positive(x) & Q.real(y)) is True
    assert satask(Q.real(x**y), Q.imaginary(x) & Q.odd(y)) is False
    assert satask(Q.real(x**y), Q.imaginary(x) & Q.even(y)) is True

    assert satask(Q.rational(1/x), Q.rational(x) & Q.nonzero(x)) is True
    assert satask(Q.rational(1/x), Q.irrational(x)) is False
    assert satask(Q.rational(1/x), Q.integer(x) & Q.nonzero(x)) is True


def test_pow_algebraic_parity_and_imaginary_facts() -> None:
    assert satask(Q.algebraic(sqrt(2))) is True
    assert satask(Q.algebraic(pi**2)) is False
    assert satask(Q.transcendental(pi**2)) is True

    assert satask(Q.odd(x**2), Q.even(x)) is False
    assert satask(Q.odd(x**2), Q.odd(x)) is True
    assert satask(Q.odd((-1)**x), Q.integer(x)) is True

    assert satask(Q.imaginary(x**y), Q.imaginary(x) & Q.odd(y)) is True
    assert satask(Q.imaginary(x**y), Q.imaginary(x) & Q.even(y)) is False


def test_commutative_facts() -> None:
    assert satask(Q.commutative(x)) is True
    assert satask(Q.commutative(x), ~Q.commutative(x)) is False
    assert satask(Q.commutative(2*x)) is True
    assert satask(Q.commutative(2*x), ~Q.commutative(x)) is False
    assert satask(Q.commutative(x + 1)) is True
    assert satask(Q.commutative(x + 1), ~Q.commutative(x)) is False
    assert satask(Q.commutative(x**2)) is True
    assert satask(Q.commutative(x**2), ~Q.commutative(x)) is False


def test_extra_predicate_facts() -> None:
    assert satask(Q.hermitian(x), Q.imaginary(x)) is False
    assert satask(Q.antihermitian(x), Q.real(x) & Q.nonzero(x)) is False
    assert satask(Q.extended_real(x), Q.imaginary(x)) is False
    assert satask(Q.odd(x), Q.even(x)) is False
    assert satask(Q.zero(x), Q.nonzero(x)) is False
    assert satask(Q.positive(x), Q.nonpositive(x)) is False
    assert satask(Q.negative(x), Q.nonnegative(x)) is False


def test_extended_real_and_infinite_facts() -> None:
    assert satask(Q.extended_real(x + oo), Q.real(x)) is True
    assert satask(Q.infinite(I*oo)) is True
    assert satask(Q.infinite(1 + I*oo)) is True
    assert satask(Q.infinite(1/x), Q.finite(x) & ~Q.zero(x)) is False
    assert satask(Q.positive_infinite(x + I), Q.real(x)) is False
    assert satask(Q.positive_infinite(x*I), Q.real(x)) is False
