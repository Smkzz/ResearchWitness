"""Exact rationals and certified square-root enclosures, standard library only."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from math import isqrt
import re
from typing import Any
from .strict import fields, require, integer, Invalid

RATIONAL_RE = re.compile(r'-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z')


def rational(value: Any) -> Fraction:
    require(type(value) is str and len(value) <= 130 and RATIONAL_RE.fullmatch(value) is not None,
            'Expected bounded exact integer/fraction string, not a float or decimal')
    parts = value.split('/')
    require(all(len(p.lstrip('-')) <= 64 for p in parts), 'Rational magnitude limit exceeded')
    return Fraction(value)


def bounded_fraction(value: Fraction) -> Fraction:
    require(value.numerator.bit_length() <= 8192 and value.denominator.bit_length() <= 8192,
            'Rational arithmetic resource limit exceeded')
    return value


@dataclass(frozen=True)
class Interval:
    lo: Fraction
    hi: Fraction

    def __post_init__(self) -> None:
        bounded_fraction(self.lo)
        bounded_fraction(self.hi)
        require(self.lo <= self.hi, 'Reversed interval')

    def add(self, other: 'Interval') -> 'Interval':
        return Interval(self.lo + other.lo, self.hi + other.hi)

    def scale(self, coefficient: Fraction) -> 'Interval':
        a, b = coefficient * self.lo, coefficient * self.hi
        return Interval(min(a, b), max(a, b))

    def subtract(self, other: 'Interval') -> 'Interval':
        return Interval(self.lo - other.hi, self.hi - other.lo)

    def record(self) -> dict:
        return {'lower_exact': str(self.lo), 'upper_exact': str(self.hi),
                'lower_display': decimal(self.lo), 'upper_display': decimal(self.hi)}


def decimal(value: Fraction) -> str:
    with localcontext() as ctx:
        ctx.prec = 45
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def sqrt_interval(value: Fraction, digits: int = 40) -> Interval:
    require(value >= 0, 'Negative square-root argument')
    integer(digits, 1, 80)
    scale = 10 ** digits
    floor = isqrt((value.numerator * scale * scale) // value.denominator)
    low = Fraction(floor, scale)
    high = low if low * low == value else Fraction(floor + 1, scale)
    require(low * low <= value <= high * high, 'Internal square-root certificate failure')
    return Interval(low, high)


def radical_sum(spec: Any, digits: int = 40) -> Interval:
    fields(spec, {'constant', 'terms'})
    value = rational(spec['constant'])
    out = Interval(value, value)
    terms = spec['terms']
    require(type(terms) is list and len(terms) <= 32, 'Too many radical terms')
    for term in terms:
        fields(term, {'coefficient', 'radicand'})
        out = out.add(sqrt_interval(rational(term['radicand']), digits).scale(rational(term['coefficient'])))
    return out
