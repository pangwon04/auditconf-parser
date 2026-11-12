from datetime import date
from decimal import Decimal

from engine.normalize.amount import parse_amount
from engine.normalize.date import parse_count, parse_date, parse_rate


def test_amount_formats():
    cases = {
        "(KRW)61,318,497 ()": ("KRW", Decimal("61318497")),
        "KRW     154984695.00()": ("KRW", Decimal("154984695.00")),
        "KRW 167,434,051.00(167,434,051.00)": ("KRW", Decimal("167434051.00")),
        "KRW11000000000.00": ("KRW", Decimal("11000000000.00")),
        "WON -206900": ("KRW", Decimal("-206900")),
        "(USD)3,124.53 ()": ("USD", Decimal("3124.53")),
        "USD 912061.78 ()": ("USD", Decimal("912061.78")),
    }
    for raw, (ccy, val) in cases.items():
        a = parse_amount(raw)
        assert (a.currency, a.value, a.status) == (ccy, val, "ok"), raw


def test_amount_no_currency_and_none():
    a = parse_amount("122,916,000")
    assert a.currency == "KRW" and a.value == Decimal("122916000") and "추정" in a.note
    assert parse_amount("해당 거래 없음").status == "none"
    assert parse_amount("** 해당사항 없음 **").status == "none"
    assert parse_amount("생략").status == "omitted"
    assert parse_amount("-").status == "none"
    assert parse_amount("").status == "blank"
    assert parse_amount("abc").status == "error"


def test_dates():
    assert parse_date("20251220").value == date(2025, 12, 20)
    assert parse_date("2025년 12월 31일").value == date(2025, 12, 31)
    for p in ("00000000", "00010101", "0000년 00월 00일", "0"):
        assert parse_date(p).status == "placeholder", p
    assert parse_date("20251340").status == "error"


def test_rate_count():
    assert parse_rate("2.697").value == Decimal("2.697")
    assert parse_rate("2.10000").value == Decimal("2.10000")
    assert parse_rate("-").status == "none"
    assert parse_count("0매").value == 0
    assert parse_count("1,234.5").value == Decimal("1234.5")
