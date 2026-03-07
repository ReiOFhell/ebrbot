from __future__ import annotations

import re

MAX_MONEY_VALUE = 9_000_000_000_000_000_000

_SUFFIX = {
    "k": 1_000,
    "m": 1_000_000,
    "kk": 1_000_000,
    "b": 1_000_000_000,
    "bi": 1_000_000_000,
    "t": 1_000_000_000_000,
    "milhao": 1_000_000,
    "milhoes": 1_000_000,
    "milhão": 1_000_000,
    "milhões": 1_000_000,
    "bilhao": 1_000_000_000,
    "bilhoes": 1_000_000_000,
    "bilhão": 1_000_000_000,
    "bilhões": 1_000_000_000,
}

_MONEY_RE = re.compile(r"^\s*([0-9]+(?:[\.,][0-9]+)?)\s*([a-zA-ZãõçÃÕÇ]*)\s*$")


def parse_money(raw: str) -> int:
    text = (raw or "").strip().lower()
    match = _MONEY_RE.match(text)
    if not match:
        raise ValueError("invalid_money")

    num_txt, suffix = match.groups()
    suffix = suffix.strip()
    if suffix not in _SUFFIX and suffix != "":
        raise ValueError("invalid_suffix")

    num_txt = num_txt.replace(",", ".")
    value = float(num_txt)
    if value < 0:
        raise ValueError("negative")
    mult = _SUFFIX.get(suffix, 1)
    total = int(round(value * mult))
    if total > MAX_MONEY_VALUE:
        raise ValueError("too_large")
    return total


def _trim(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s


def format_money(value: int) -> str:
    n = int(value)
    sign = "-" if n < 0 else ""
    a = abs(n)
    if a < 1_000:
        return f"{sign}{a}"
    if a < 1_000_000:
        return f"{sign}{_trim(a/1_000)}k"
    if a < 1_000_000_000:
        return f"{sign}{_trim(a/1_000_000)}m"
    if a < 1_000_000_000_000:
        return f"{sign}{_trim(a/1_000_000_000)}bi"
    return f"{sign}{_trim(a/1_000_000_000_000)}t"
