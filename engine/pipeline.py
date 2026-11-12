"""파싱 결과를 엑셀 행 단위로 펼치고 값을 정규화한다 (A-09)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .forms.parser import ParsedDoc, parse_pdf
from .forms.schemas import Table
from .normalize.amount import parse_amount
from .normalize.date import parse_count, parse_date, parse_rate


@dataclass
class Cell:
    raw: str
    kind: str
    ccy: str | None = None
    value: object | None = None      # Decimal | date | int
    note: str = ""
    status: str = "blank"


@dataclass
class OutRow:
    doc: ParsedDoc
    table: Table
    status: str                      # data | none | inquire | missing | kv | notfound
    cells: dict[str, Cell] = field(default_factory=dict)
    page: int | None = None
    notes: list[str] = field(default_factory=list)


def make_cell(raw: str | None, kind: str) -> Cell:
    raw = (raw or "").strip()
    c = Cell(raw, kind)
    if kind == "amount":
        a = parse_amount(raw)
        c.ccy, c.value, c.status, c.note = a.currency, a.value, a.status, a.note
    elif kind == "date":
        p = parse_date(raw)
        c.value, c.status, c.note = p.value, p.status, p.note
    elif kind == "rate":
        p = parse_rate(raw)
        c.value, c.status, c.note = p.value, p.status, p.note
    elif kind == "count":
        p = parse_count(raw)
        c.value, c.status, c.note = p.value, p.status, p.note
    else:
        c.status = "ok" if raw else "blank"
    return c


def rows_for(doc: ParsedDoc) -> list[OutRow]:
    out: list[OutRow] = []
    if doc.form is None:
        return out
    for s in doc.sections:
        if not s.found:
            for t in s.section.tables:
                out.append(OutRow(doc, t, "notfound", notes=["섹션 누락"]))
            continue
        for tr in s.tables:
            t = tr.table
            if tr.status == "kv":
                out.append(OutRow(doc, t, "kv", {t.label: make_cell(tr.kv_value, t.kv_kind)}, tr.page))
            elif tr.status == "data":
                for r in tr.records:
                    cells = {c.name: make_cell(r.values.get(c.name), c.kind) for c in t.cols}
                    out.append(OutRow(doc, t, "data", cells, r.page, list(tr.notes)))
            else:
                out.append(OutRow(doc, t, tr.status, page=tr.page, notes=list(tr.notes) + ([tr.raw] if tr.raw else [])))
    return out


def load(paths: list[Path]) -> list[ParsedDoc]:
    docs = []
    for p in paths:
        try:
            docs.append(parse_pdf(p))
        except Exception as e:  # 한 부가 깨져도 나머지는 진행
            d = ParsedDoc(Path(p), 0, False, None, {"error": f"{type(e).__name__}: {e}"}, [])
            docs.append(d)
    return docs
