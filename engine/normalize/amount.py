"""금액 원문을 (통화, Decimal) 로 바꾼다 (A-09).

회신본마다 금액 표기가 다르다.
  (KRW)61,318,497 ()        KRW     154984695.00()     KRW 167,434,051.00(167,434,051.00)
  KRW11000000000.00         WON -206900                122,916,000 (통화 없음)
  0  /  생략  /  -  /  해당 거래 없음
괄호 뒤 숫자는 원화 환산액 등 보조 표기이므로 첫 번째 숫자만 금액으로 본다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .none_words import is_blank, is_none_word, is_omitted

_CCY_ALIAS = {"WON": "KRW", "원": "KRW", "\\": "KRW", "₩": "KRW"}
RE_CCY_PAREN = re.compile(r"^\(\s*([A-Z]{3})\s*\)")
RE_CCY = re.compile(r"^(WON|[A-Z]{3})(?![A-Z])")
RE_NUM = re.compile(r"[-−]?\s*\d[\d,]*(?:\.\d+)?")


@dataclass(frozen=True)
class Amount:
    currency: str | None
    value: Decimal | None
    status: str          # ok | none | omitted | blank | error
    note: str = ""


def parse_amount(text: str | None) -> Amount:
    if is_blank(text):
        return Amount(None, None, "blank")
    s = str(text).strip()
    if is_none_word(s):
        return Amount(None, None, "none")
    if is_omitted(s):
        return Amount(None, None, "omitted", "금액 생략 표기")

    ccy = None
    m = RE_CCY_PAREN.match(s)
    if m:
        ccy, s = m.group(1), s[m.end():]
    else:
        m = RE_CCY.match(s)
        if m:
            ccy, s = m.group(1), s[m.end():]
    if ccy:
        ccy = _CCY_ALIAS.get(ccy, ccy)
    s = s.strip()
    if s.endswith("원") and not ccy:
        ccy, s = "KRW", s[:-1]

    m = RE_NUM.search(s)
    if not m or s[:m.start()].strip() not in ("",):
        return Amount(ccy, None, "error", f"금액으로 읽을 수 없음: {text!r}")
    raw = m.group(0).replace(",", "").replace(" ", "").replace("−", "-")
    try:
        val = Decimal(raw)
    except InvalidOperation:
        return Amount(ccy, None, "error", f"금액으로 읽을 수 없음: {text!r}")

    rest = s[m.end():].strip()
    if rest and not re.fullmatch(r"\(\s*[-\d,.\s]*\)", rest):
        return Amount(ccy, val, "ok", f"금액 뒤 추가 표기 확인: {rest!r}")
    note = ""
    if ccy is None:
        ccy = "KRW"
        note = "통화 표기 없음 → KRW로 추정"
    return Amount(ccy, val, "ok", note)
