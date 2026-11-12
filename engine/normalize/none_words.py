"""'거래 없음' 계열 표기와 '미기재' 계열 표기를 판별한다."""
from __future__ import annotations

import re

_NONE = {
    "해당거래없음", "해당사항없음", "해당없음", "거래없음", "해당내역없음", "내역없음",
    "담보보증내역없음", "없음", "-", "--", "—",
}
_INQUIRE = ("문의바람", "문의하시기바랍니다", "별도문의")
_ERROR = ("SCRIPTERROR", "ERROR", "오류")


def _c(text: str) -> str:
    return re.sub(r"[\s*·.]+", "", text or "")


def is_none_word(text: str) -> bool:
    c = _c(text)
    return bool(c) and c in _NONE


def is_inquire(text: str) -> bool:
    c = _c(text)
    return any(k in c for k in _INQUIRE)


def is_error_text(text: str) -> bool:
    c = _c(text).upper()
    return any(k in c for k in _ERROR)


def is_omitted(text: str) -> bool:
    return _c(text) in {"생략", "생략~생략", "~생략"}


def is_blank(text: str | None) -> bool:
    return text is None or not str(text).strip()
