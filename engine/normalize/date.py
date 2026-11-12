"""날짜·이자율·매수 원문을 값으로 바꾼다 (A-09)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .none_words import is_blank, is_none_word, is_omitted

PLACEHOLDER_DATES = {"00000000", "00010101", "99991231", "00000101"}
RE_YMD = re.compile(r"(\d{4})\s*[-./년]?\s*(\d{1,2})\s*[-./월]?\s*(\d{1,2})\s*일?")


@dataclass(frozen=True)
class Parsed:
    value: object | None
    status: str          # ok | none | placeholder | blank | error
    note: str = ""


def parse_date(text: str | None) -> Parsed:
    if is_blank(text):
        return Parsed(None, "blank")
    s = str(text).strip()
    if is_none_word(s) or is_omitted(s):
        return Parsed(None, "none")
    digits = re.sub(r"\D", "", s)
    if digits in PLACEHOLDER_DATES or set(digits) <= {"0"}:
        return Parsed(None, "placeholder", f"날짜 자리표시자({s})")
    m = RE_YMD.search(s)
    if not m:
        return Parsed(None, "error", f"날짜로 읽을 수 없음: {s!r}")
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return Parsed(date(y, mo, d), "ok")
    except ValueError:
        return Parsed(None, "error", f"없는 날짜: {s!r}")


def parse_rate(text: str | None) -> Parsed:
    """연이자율 원문(퍼센트 수치)을 Decimal로. 2.697 → 2.697 (%)."""
    if is_blank(text):
        return Parsed(None, "blank")
    s = str(text).strip().replace("%", "")
    if is_none_word(s) or is_omitted(s):
        return Parsed(None, "none")
    m = re.fullmatch(r"[-]?\d+(?:\.\d+)?", s.replace(",", ""))
    if not m:
        return Parsed(None, "error", f"이자율로 읽을 수 없음: {text!r}")
    try:
        return Parsed(Decimal(m.group(0)), "ok")
    except InvalidOperation:
        return Parsed(None, "error", f"이자율로 읽을 수 없음: {text!r}")


def parse_count(text: str | None) -> Parsed:
    if is_blank(text):
        return Parsed(None, "blank")
    s = str(text).strip()
    if is_none_word(s) or is_omitted(s):
        return Parsed(None, "none")
    m = re.fullmatch(r"(-?[\d,]+(?:\.\d+)?)\s*(매|건|좌|주)?", s)
    if not m:
        return Parsed(None, "error", f"수량으로 읽을 수 없음: {text!r}")
    v = Decimal(m.group(1).replace(",", ""))
    return Parsed(int(v) if v == v.to_integral_value() else v, "ok")
