"""A small, dependency-free Boolean formula and integer-CNF layer.

Atoms are opaque hashable Python objects.  Formula construction is deliberately
separate from any expression system: an adapter can use this module for SymPy
predicates, or an unrelated domain can use strings, tuples, or application
objects as atoms.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable, Iterator, Sequence, TypeAlias, cast


Literal: TypeAlias = int | bool


class ClauseDB:
    """A mutable collection of integer clauses with a shared atom encoding.

    Variable zero is never allocated.  ``True`` is represented by no clauses
    and ``False`` by an empty clause.  Tautological clauses are discarded.
    """

    def __init__(self) -> None:
        self.data: list[set[int]] = []
        self.encoding: dict[Hashable, int] = {}
        # ``atom_to_id`` is a descriptive alias useful to non-SymPy callers.
        self.atom_to_id = self.encoding
        self.symbols: dict[int, Hashable] = {}
        self.auxiliaries: set[int] = set()
        self._next_variable = 1

    @property
    def clauses(self) -> list[set[int]]:
        """Alias retained for callers which name the storage ``clauses``."""
        return self.data

    @property
    def variables(self) -> set[int]:
        """All variables allocated by this database, including auxiliaries."""
        return set(range(1, self._next_variable))

    def literal(self, atom: Hashable) -> int:
        """Return the positive literal for an opaque, hashable atom."""
        if isinstance(atom, bool):
            raise TypeError("Boolean constants are not atoms; use True or False directly")
        try:
            return self.encoding[atom]
        except KeyError:
            variable = self._allocate()
            self.encoding[atom] = variable
            self.symbols[variable] = atom
            return variable

    def new_auxiliary_variable(self) -> int:
        """Allocate an unnamed variable for Tseitin encoding."""
        variable = self._allocate()
        self.auxiliaries.add(variable)
        return variable

    def _allocate(self) -> int:
        variable = self._next_variable
        self._next_variable += 1
        return variable

    def add_clause(self, literals: Iterable[Literal]) -> None:
        """Add one normalized clause.

        ``True`` literals make a clause redundant; ``False`` literals are
        removed.  This accepts booleans only to make formula compilation's
        constant cases explicit at this one boundary.
        """
        clause: set[int] = set()
        for literal in literals:
            if literal is True:
                return
            if literal is False:
                continue
            if not isinstance(literal, int) or isinstance(literal, bool) or literal == 0:
                raise ValueError("clauses contain nonzero integer literals only")
            if -literal in clause:
                return
            clause.add(literal)
        self.data.append(clause)

    def format_clause(self, clause: Iterable[int]) -> str:
        """Return a readable clause using atoms where they are available."""
        terms = []
        for literal in sorted(clause, key=lambda item: (abs(item), item < 0)):
            name = repr(self.symbols.get(abs(literal), f"@{abs(literal)}"))
            terms.append(name if literal > 0 else f"~{name}")
        return "(" + " | ".join(terms) + ")" if terms else "False"

    def format_clauses(self) -> str:
        """Return all clauses in a form intended for debugging and tests."""
        return " & ".join(self.format_clause(clause) for clause in self.data) or "True"


class SharedClauses:
    """A pre-translated, immutable block of integer clauses.

    Some clause theories are *fixed*: the same clauses are needed in every
    query, with only the atom bindings varying.  Such a theory is translated
    into integer clauses once and replayed into each query's database, so
    per-query work is one ``ClauseDB.literal`` call per bound atom plus a
    clause replay instead of a full re-emission.  Sharing stops at
    construction time: every receiving database gets its own copies of the
    clauses and stays independently mutable, and no solver ever observes
    shared state between queries.

    The block stores clauses over *template positions* — positive integers
    from 1 to :attr:`width`.  :meth:`replay` binds each position to a
    variable id of the receiving database.  Auxiliary variables of the
    compiled theory must occupy the topmost positions of the block; callers
    that compile theories containing none (the known-facts template) use
    the default ``auxiliary_count=0``.
    """

    __slots__ = ("clauses", "width", "auxiliary_count")

    def __init__(self, clauses: Iterable[Iterable[int]], width: int,
                 auxiliary_count: int = 0) -> None:
        self.clauses: tuple[tuple[int, ...], ...] = tuple(
            tuple(clause) for clause in clauses)
        self.width = width
        self.auxiliary_count = auxiliary_count
        if any(abs(literal) > width
               for clause in self.clauses for literal in clause):
            raise ValueError("clause literal exceeds the block width")
        if not 0 <= auxiliary_count <= width:
            raise ValueError("auxiliary count outside the block width")

    def replay(self, db: ClauseDB, binding: Sequence[int]) -> None:
        """Add the block to *db*, binding position *i* to ``binding[i]``.

        The binding must map template positions to distinct positive
        variable ids of *db*; known-facts bindings map the template's
        predicate positions through ``ClauseDB.literal``, which does.  When
        the binding is consecutive from *db*'s next free variable — every
        atom freshly minted — the stored clauses are appended verbatim;
        otherwise they are re-based through the binding.  Re-based clauses
        skip ``add_clause`` normalization legitimately: template clauses
        contain no duplicate or tautological literals by construction, and
        distinct positions cannot collapse onto one id or onto negations of
        one another (ids are positive and ``literal`` never reuses an id for
        a different atom), so every re-based clause is already a normalized
        duplicate-free integer set.
        """
        if len(binding) != self.width:
            raise ValueError("binding does not cover the block width")
        base = db._next_variable
        for position, variable in enumerate(binding):
            if variable != base + position:
                self._rebase(db, binding)
                return
        db.data.extend(map(set, self.clauses))
        db._next_variable = base + self.width

    def _rebase(self, db: ClauseDB, binding: Sequence[int]) -> None:
        data = db.data
        for clause in self.clauses:
            data.append({
                binding[literal - 1] if literal > 0 else -binding[-literal - 1]
                for literal in clause})
        # Keep the next free id above every bound position so a later
        # ``literal`` call cannot mint an id a binding already names.
        if db._next_variable <= max(binding):
            db._next_variable = max(binding) + 1


@dataclass(frozen=True)
class Formula:
    """An internal Boolean connective.  Anything else is an opaque atom."""

    op: str
    args: tuple[object, ...]


def _flatten(op: str, args: tuple[object, ...]) -> tuple[object, ...]:
    flattened: list[object] = []
    for arg in args:
        if isinstance(arg, Formula) and arg.op == op:
            flattened.extend(arg.args)
        else:
            flattened.append(arg)
    return tuple(flattened)


def AND(*args: object) -> object:
    args = _flatten("and", args)
    if any(arg is False for arg in args):
        return False
    args = tuple(arg for arg in args if arg is not True)
    if not args:
        return True
    if len(args) == 1:
        return args[0]
    return Formula("and", args)


def OR(*args: object) -> object:
    args = _flatten("or", args)
    if any(arg is True for arg in args):
        return True
    args = tuple(arg for arg in args if arg is not False)
    if not args:
        return False
    if len(args) == 1:
        return args[0]
    return Formula("or", args)


def NOT(arg: object) -> object:
    if arg is True:
        return False
    if arg is False:
        return True
    if isinstance(arg, Formula) and arg.op == "not":
        return arg.args[0]
    return Formula("not", (arg,))


def IMPLIES(left: object, right: object) -> object:
    if left is False or right is True:
        return True
    if left is True:
        return right
    if right is False:
        return NOT(left)
    return Formula("implies", (left, right))


def EQUIVALENT(*args: object) -> object:
    if len(args) < 2:
        return True
    if all(arg == args[0] for arg in args[1:]):
        return True
    return Formula("equivalent", args)


def XOR(*args: object) -> object:
    parity = False
    remaining: list[object] = []
    for arg in args:
        if arg is True:
            parity = not parity
        elif arg is not False:
            remaining.append(arg)
    if not remaining:
        return parity
    result: object = remaining[0]
    for arg in remaining[1:]:
        result = Formula("xor", (result, arg))
    return NOT(result) if parity else result


def ITE(condition: object, if_true: object, if_false: object) -> object:
    if condition is True:
        return if_true
    if condition is False:
        return if_false
    if if_true == if_false:
        return if_true
    return Formula("ite", (condition, if_true, if_false))


def iter_atoms(formula: object) -> Iterator[object]:
    """Yield opaque atomic leaves of *formula*, excluding Boolean constants."""
    if formula is True or formula is False:
        return
    if isinstance(formula, Formula):
        for arg in formula.args:
            yield from iter_atoms(arg)
        return
    yield formula


def _as_literal(formula: object, db: ClauseDB) -> Literal | None:
    """Return a literal only when no connective encoding is necessary."""
    if formula is True or formula is False:
        return formula
    if isinstance(formula, Formula):
        if formula.op == "not":
            arg = _as_literal(formula.args[0], db)
            if arg is True:
                return False
            if arg is False:
                return True
            if isinstance(arg, int):
                return -arg
        return None
    return db.literal(formula)


def compile_formula(formula: object, db: ClauseDB) -> Literal:
    """Compile *formula* and return a literal equivalent to its truth value."""
    cache: dict[Formula, Literal] = {}

    def compile_(item: object) -> Literal:
        literal = _as_literal(item, db)
        if literal is not None:
            return literal
        assert isinstance(item, Formula)
        try:
            return cache[item]
        except KeyError:
            pass

        op = item.op
        args = item.args
        if op == "and":
            result = _compile_and([compile_(arg) for arg in args], db)
        elif op == "or":
            result = _compile_or([compile_(arg) for arg in args], db)
        elif op == "not":  # normally handled by _as_literal
            result = _negate(compile_(args[0]))
        elif op == "implies":
            result = _compile_or([_negate(compile_(args[0])), compile_(args[1])], db)
        elif op == "equivalent":
            first = compile_(args[0])
            comparisons = [_compile_equivalence(first, compile_(arg), db) for arg in args[1:]]
            result = _compile_and(comparisons, db)
        elif op == "xor":
            result = _compile_xor(compile_(args[0]), compile_(args[1]), db)
        elif op == "ite":
            result = _compile_ite(compile_(args[0]), compile_(args[1]), compile_(args[2]), db)
        else:
            raise ValueError(f"unknown formula operation {op!r}")
        cache[item] = result
        return result

    return compile_(formula)


def _negate(literal: Literal) -> Literal:
    return (not literal) if isinstance(literal, bool) else -literal


def _compile_and(args: list[Literal], db: ClauseDB) -> Literal:
    if any(arg is False for arg in args):
        return False
    args = [arg for arg in args if arg is not True]
    if not args:
        return True
    if len(args) == 1:
        return args[0]
    result = db.new_auxiliary_variable()
    for arg in args:
        db.add_clause((-result, arg))
    db.add_clause((result, *(_negate(arg) for arg in args)))
    return result


def _compile_or(args: list[Literal], db: ClauseDB) -> Literal:
    if any(arg is True for arg in args):
        return True
    args = [arg for arg in args if arg is not False]
    if not args:
        return False
    if len(args) == 1:
        return args[0]
    result = db.new_auxiliary_variable()
    for arg in args:
        db.add_clause((result, _negate(arg)))
    db.add_clause((-result, *args))
    return result


def _compile_equivalence(left: Literal, right: Literal, db: ClauseDB) -> Literal:
    # v <=> (left <=> right)
    if isinstance(left, bool):
        return right if left else _negate(right)
    if isinstance(right, bool):
        return left if right else _negate(left)
    result = db.new_auxiliary_variable()
    db.add_clause((-result, -left, right))
    db.add_clause((-result, left, -right))
    db.add_clause((result, left, right))
    db.add_clause((result, -left, -right))
    return result


def _compile_xor(left: Literal, right: Literal, db: ClauseDB) -> Literal:
    # v <=> left xor right
    if isinstance(left, bool):
        return _negate(right) if left else right
    if isinstance(right, bool):
        return _negate(left) if right else left
    result = db.new_auxiliary_variable()
    db.add_clause((-result, -left, -right))
    db.add_clause((-result, left, right))
    db.add_clause((result, -left, right))
    db.add_clause((result, left, -right))
    return result


def _compile_ite(condition: Literal, if_true: Literal, if_false: Literal, db: ClauseDB) -> Literal:
    if condition is True:
        return if_true
    if condition is False:
        return if_false
    if if_true == if_false:
        return if_true
    result = db.new_auxiliary_variable()
    # With condition true, result == if_true; otherwise result == if_false.
    db.add_clause((-condition, _negate(if_true), result))
    db.add_clause((-condition, if_true, -result))
    db.add_clause((condition, _negate(if_false), result))
    db.add_clause((condition, if_false, -result))
    return result


def assert_formula(formula: object, db: ClauseDB) -> None:
    """Assert *formula* while directly emitting common top-level clauses."""
    if formula is True:
        return
    if formula is False:
        db.add_clause(())
        return
    if isinstance(formula, Formula) and formula.op == "and":
        for arg in formula.args:
            assert_formula(arg, db)
        return

    # Clauses and simple implications/equivalences are common handler facts.
    if isinstance(formula, Formula) and formula.op == "or":
        literals = [_as_literal(arg, db) for arg in formula.args]
        if all(arg is not None for arg in literals):
            db.add_clause(cast("list[Literal]", literals))
            return
    if isinstance(formula, Formula) and formula.op == "implies":
        antecedent = _conjunction_literals(formula.args[0], db)
        consequent = _disjunction_literals(formula.args[1], db)
        if antecedent is not None and consequent is not None:
            db.add_clause((*(_negate(literal) for literal in antecedent), *consequent))
            return
        # A -> (Or_j(And_j) -> C) flattens to (A & Or_j(And_j)) -> C, one
        # clause per disjunct.  Distribution is confined to this negative
        # polarity: the same shapes in consequent position would expand
        # exponentially and must keep falling through to Tseitin compilation.
        # The shape checks below never allocate variables, so every shape
        # that is not fast-pathed reaches Tseitin with the database exactly
        # as before.
        if antecedent is not None and isinstance(formula.args[1], Formula) \
                and formula.args[1].op == "implies":
            nested = formula.args[1]
            disjuncts = _cnf_disjunct_formulas(nested.args[0])
            if disjuncts is not None and _flat_disjunction(nested.args[1]):
                nested_consequent = _disjunction_literals(nested.args[1], db)
                for disjunct in disjuncts:
                    db.add_clause((*(_negate(literal) for literal in antecedent),
                                   *(_negate(_as_literal(term, db))
                                     for term in disjunct),
                                   *nested_consequent))
                return
        # (Or_j(And_j)) -> C is one clause per disjunct, no auxiliaries.
        disjuncts = _cnf_disjunct_formulas(formula.args[0])
        if disjuncts is not None and consequent is not None:
            for disjunct in disjuncts:
                db.add_clause((*(_negate(_as_literal(term, db))
                                 for term in disjunct),
                               *consequent))
            return
    if isinstance(formula, Formula) and formula.op == "equivalent":
        literals = [_as_literal(arg, db) for arg in formula.args]
        if all(arg is not None for arg in literals):
            checked = cast("list[Literal]", literals)
            first = checked[0]
            for other in checked[1:]:
                db.add_clause((_negate(first), other))
                db.add_clause((first, _negate(other)))
            return

    literal = compile_formula(formula, db)
    db.add_clause((literal,))


def _conjunction_literals(formula: object, db: ClauseDB) -> list[Literal] | None:
    """Return literal terms for a conjunction, or ``None`` if it is complex."""
    args = formula.args if isinstance(formula, Formula) and formula.op == "and" else (formula,)
    literals = [_as_literal(arg, db) for arg in args]
    if all(literal is not None for literal in literals):
        return cast("list[Literal]", literals)
    return None


def _disjunction_literals(formula: object, db: ClauseDB) -> list[Literal] | None:
    """Return literal terms for a disjunction, or ``None`` if it is complex."""
    args = formula.args if isinstance(formula, Formula) and formula.op == "or" else (formula,)
    literals = [_as_literal(arg, db) for arg in args]
    if all(literal is not None for literal in literals):
        return cast("list[Literal]", literals)
    return None


def _is_literal_formula(formula: object) -> bool:
    """Whether ``_as_literal`` would succeed for *formula*, without
    allocating any variable."""
    if formula is True or formula is False:
        return True
    if isinstance(formula, Formula):
        return formula.op == "not" and _is_literal_formula(formula.args[0])
    return True


def _flat_disjunction(formula: object) -> bool:
    """Whether *formula* is a literal or a flat disjunction of them."""
    terms = formula.args if isinstance(formula, Formula) and formula.op == "or" else (formula,)
    return all(_is_literal_formula(term) for term in terms)


def _cnf_disjunct_formulas(formula: object) -> tuple[tuple[object, ...], ...] | None:
    """Return the disjuncts of an Or-of-Ands of literal-shaped terms.

    Each disjunct is a conjunction of literal-shaped terms, held as the raw
    term formulas so callers materialize variable ids only when they commit
    to emitting the distributed clauses.  ``None`` when *formula* does not
    have this shape.
    """
    if not (isinstance(formula, Formula) and formula.op == "or"):
        return None
    disjuncts = []
    for arg in formula.args:
        terms = arg.args if isinstance(arg, Formula) and arg.op == "and" else (arg,)
        if not all(_is_literal_formula(term) for term in terms):
            return None
        disjuncts.append(terms)
    return tuple(disjuncts)


__all__ = [
    "AND", "OR", "NOT", "IMPLIES", "EQUIVALENT", "XOR", "ITE",
    "ClauseDB", "Formula", "Literal", "SharedClauses",
    "assert_formula", "compile_formula", "iter_atoms",
]
