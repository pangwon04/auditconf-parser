"""키인 결과 엑셀 출력 (A-09 숫자 열, B-06 점검 시트).

시트: 요약 · 점검 · BANK · INVESTMENT · INSURANCE · GUARANTEE (받은 양식만)
양식 시트 안에서는 구획(1, 2-1, 2-2 ...)마다 제목 줄 → 머리글 → 기관별 행을 쌓는다.
금액 원문 바로 오른쪽에 `_통화`, `_숫자` 열을, 날짜 옆에 `_일자`, 이자율 옆에 `_숫자(%)` 열을 둔다.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..checks.completeness import Issue
from ..forms.parser import ParsedDoc
from ..forms.schemas import FORMS, Table
from ..pipeline import Cell, OutRow

FONT = "Arial"
F_BASE = Font(name=FONT, size=9)
F_BOLD = Font(name=FONT, size=9, bold=True)
F_TITLE = Font(name=FONT, size=11, bold=True)
F_HEAD = Font(name=FONT, size=9, bold=True, color="FFFFFF")
FILL_HEAD = PatternFill("solid", fgColor="44546A")
FILL_NUM_HEAD = PatternFill("solid", fgColor="2F75B5")
FILL_SEC = PatternFill("solid", fgColor="D9E1F2")
FILL_NOTE = PatternFill("solid", fgColor="FFF2CC")
FILL_ERR = PatternFill("solid", fgColor="F8CBAD")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")

FMT_KRW = '#,##0;[Red](#,##0);"-"'
FMT_FX = '#,##0.00;[Red](#,##0.00);"-"'
FMT_DATE = "yyyy-mm-dd"
FMT_RATE = '0.0##;[Red]-0.0##;"-"'
FMT_COUNT = '#,##0.###;[Red]-#,##0.###;"-"'

STATUS_KO = {"data": "자료", "kv": "자료", "none": "해당 없음", "inquire": "미기재",
             "missing": "확인 필요", "notfound": "섹션 누락"}
COMMON = ("금융기관명", "조회대상 회사", "사업자번호", "조회기준일")
TRAIL = ("상태", "원본 파일", "쪽", "검토 메모")


def _num(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() and abs(v) < 10**15 else float(v)
    return v


def _columns(table: Table) -> list[tuple[str, str, str]]:
    """(머리글, 원래 열 이름, 역할) — 역할: raw | ccy | num | date | rate | count"""
    if table.kv:
        cols = [(table.label, table.label, "raw")]
        if table.kv_kind == "amount":
            cols += [(f"{table.label}_통화", table.label, "ccy"), (f"{table.label}_숫자", table.label, "num")]
        elif table.kv_kind == "count":
            cols += [(f"{table.label}_숫자", table.label, "count")]
        return cols
    out = []
    for c in table.cols:
        out.append((c.name, c.name, "raw"))
        if c.kind == "amount":
            out += [(f"{c.name}_통화", c.name, "ccy"), (f"{c.name}_숫자", c.name, "num")]
        elif c.kind == "date":
            out.append((f"{c.name}_일자", c.name, "date"))
        elif c.kind == "rate":
            out.append((f"{c.name}_숫자(%)", c.name, "rate"))
        elif c.kind == "count":
            out.append((f"{c.name}_숫자", c.name, "count"))
    return out


def _print_setup(ws):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0


def _put(ws, r, c, v, font=F_BASE, fill=None, fmt=None, border=True, align=None):
    cell = ws.cell(row=r, column=c, value=v)
    if isinstance(v, str) and v.startswith("="):
        cell.data_type = "s"     # PDF 원문·파일명이 수식으로 실행되지 않게 (수식 주입 방지)
    cell.font = font
    if fill:
        cell.fill = fill
    if fmt:
        cell.number_format = fmt
    if border:
        cell.border = BORDER
    if align:
        cell.alignment = align
    return cell


def _form_sheet(wb, form, docs: list[ParsedDoc], rows: list[OutRow], project: str):
    ws = wb.create_sheet(form.key)
    _put(ws, 1, 1, f"프로젝트명: {project}", F_TITLE, border=False)
    _put(ws, 2, 1, "'_숫자' 열은 엑셀 숫자 셀입니다(합계·필터 가능). 노란 칸은 검토 메모가 있는 값, "
                   "주황 칸은 미기재·확인 필요 행입니다.", Font(name=FONT, size=9, italic=True, color="595959"),
         border=False)
    r = 4
    widths: dict[int, int] = {}
    fdocs = [d for d in docs if d.form is form]
    for sec in form.sections:
        for tab in sec.tables:
            cols = _columns(tab)
            heads = list(COMMON) + [h for h, _, _ in cols] + list(TRAIL)
            # 구획 제목: 첫 회신본의 원문 제목을 쓴다
            title = next((s.title for d in fdocs for s in d.sections if s.section is sec and s.found), sec.title)
            label = f"{tab.key}. [{tab.label}] " if (len(sec.tables) > 1) else ""
            t = title if not label else label + title.split(".", 1)[-1].strip()
            _put(ws, r, 1, t, F_BOLD, FILL_SEC, border=False)
            for cc in range(2, len(heads) + 1):
                ws.cell(row=r, column=cc).fill = FILL_SEC
            r += 1
            for ci, h in enumerate(heads, 1):
                role = cols[ci - len(COMMON) - 1][2] if len(COMMON) < ci <= len(COMMON) + len(cols) else "raw"
                _put(ws, r, ci, h, F_HEAD, FILL_NUM_HEAD if role != "raw" else FILL_HEAD,
                     align=Alignment(wrap_text=True, vertical="center", horizontal="center"))
                widths[ci] = max(widths.get(ci, 8), min(len(h) * 2 + 2, 28))
            ws.row_dimensions[r].height = 30
            r += 1
            trs = [x for x in rows if x.table is tab]
            trs.sort(key=lambda x: (x.doc.institution, x.page or 0))
            for x in trs:
                m = x.doc.meta
                vals = [x.doc.institution, m.get("company"), m.get("biz_no"), m.get("as_of")]
                for ci, v in enumerate(vals, 1):
                    _put(ws, r, ci, v)
                notes = list(x.notes)
                row_fill = FILL_ERR if x.status in ("inquire", "missing", "notfound") else None
                for k, (h, name, role) in enumerate(cols):
                    ci = len(COMMON) + 1 + k
                    cell: Cell | None = x.cells.get(name)
                    if cell is None:
                        v = None
                        if k == 0 and x.status != "data":
                            v = {"none": "해당 없음", "inquire": "미기재", "missing": "확인 필요",
                                 "notfound": "섹션 누락"}.get(x.status)
                        _put(ws, r, ci, v, fill=row_fill)
                        continue
                    fill = FILL_NOTE if cell.note else None
                    if role == "raw":
                        _put(ws, r, ci, cell.raw or None, fill=fill, align=WRAP)
                        widths[ci] = max(widths.get(ci, 8), min(len(cell.raw) + 2, 40))
                        if cell.note:
                            notes.append(f"{name}: {cell.note}")
                    elif role == "ccy":
                        _put(ws, r, ci, cell.ccy, fill=fill)
                    elif role == "num":
                        fmt = FMT_KRW if (cell.ccy in (None, "KRW")) else FMT_FX
                        _put(ws, r, ci, _num(cell.value), fill=fill, fmt=fmt)
                        widths[ci] = max(widths.get(ci, 8), 16)
                    elif role == "date":
                        _put(ws, r, ci, cell.value, fill=fill, fmt=FMT_DATE)
                        widths[ci] = max(widths.get(ci, 8), 11)
                    elif role == "rate":
                        _put(ws, r, ci, _num(cell.value), fill=fill, fmt=FMT_RATE)
                    elif role == "count":
                        _put(ws, r, ci, _num(cell.value), fill=fill, fmt=FMT_COUNT)
                base = len(COMMON) + len(cols)
                _put(ws, r, base + 1, STATUS_KO.get(x.status, x.status), fill=row_fill)
                _put(ws, r, base + 2, x.doc.path.name)
                _put(ws, r, base + 3, (x.page + 1) if x.page is not None else None)
                _put(ws, r, base + 4, " / ".join(dict.fromkeys(n for n in notes if n)) or None, align=WRAP)
                widths[base + 4] = max(widths.get(base + 4, 8), 30)
                r += 1
            if not trs:
                _put(ws, r, 1, "(이 양식의 회신본 없음)", border=False)
                r += 1
            r += 1
    widths[1] = max(widths.get(1, 8), 16)
    widths[2] = max(widths.get(2, 8), 20)
    widths[3] = max(widths.get(3, 8), 13)
    for ci, w in widths.items():
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.sheet_view.zoomScale = 90
    _print_setup(ws)


def _result_text(d: ParsedDoc, issues: list[Issue]) -> str:
    if d.meta.get("error"):
        return f"처리 실패: {d.meta['error']}"
    if not d.has_text:
        return "스캔본 — OCR 미지원, 수기 키인 필요"
    if d.form is None:
        return "양식 미인식 — 전자조회 양식이 아님"
    errs = sum(1 for i in issues if i.level == "오류")
    if d.all_none:
        return "거래 없음(전 섹션 해당 없음)" + (f" · 오류 {errs}건" if errs else "")
    return "완료" + (f" · 오류 {errs}건 확인" if errs else "")


def write_workbook(out: Path, docs: list[ParsedDoc], rows: list[OutRow], issues: list[Issue],
                   project: str) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "요약"
    _put(ws, 1, 1, f"프로젝트명: {project}", F_TITLE, border=False)
    _put(ws, 2, 1, f"생성: {datetime.now():%Y-%m-%d %H:%M} · auditconf 엔진 0.1 (전자조회 회신본 키인)",
         Font(name=FONT, size=9, color="595959"), border=False)
    heads = ["No", "금융기관명", "양식", "조회대상 회사", "사업자번호", "조회기준일", "발급일", "쪽수",
             "결과", "오류", "검토", "참고", "원본 파일"]
    for ci, h in enumerate(heads, 1):
        _put(ws, 4, ci, h, F_HEAD, FILL_HEAD, align=Alignment(horizontal="center"))
    by_doc: dict[int, list[Issue]] = {}
    for i in issues:
        for d in docs:
            if d.path.name == i.file:
                by_doc.setdefault(id(d), []).append(i)
    order = sorted(docs, key=lambda d: ([f.key for f in FORMS].index(d.form.key) if d.form else 9, d.institution))
    for n, d in enumerate(order, 1):
        iss = by_doc.get(id(d), [])
        lv = Counter(i.level for i in iss)
        res = _result_text(d, iss)
        m = d.meta
        vals = [n, d.institution if d.has_text else d.path.stem, d.form.name if d.form else "-",
                m.get("company"), m.get("biz_no"), m.get("as_of"), m.get("issued_on"), d.page_count,
                res, lv.get("오류", 0), lv.get("검토", 0), lv.get("참고", 0), d.path.name]
        for ci, v in enumerate(vals, 1):
            fill = FILL_ERR if ci == 9 and not res.startswith(("완료", "거래 없음")) else \
                (FILL_NOTE if ci == 9 and "오류" in res else None)
            _put(ws, 4 + n, ci, v, fill=fill)
    for ci, w in enumerate([5, 18, 9, 22, 13, 11, 11, 6, 34, 6, 6, 6, 60], 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = "A5"
    _print_setup(ws)

    ws2 = wb.create_sheet("점검")
    h2 = ["수준", "금융기관명", "위치", "항목", "내용", "원본 파일"]
    for ci, h in enumerate(h2, 1):
        _put(ws2, 1, ci, h, F_HEAD, FILL_HEAD)
    rank = {"오류": 0, "검토": 1, "참고": 2}
    for k, i in enumerate(sorted(issues, key=lambda i: (rank.get(i.level, 3), i.institution)), 2):
        fill = FILL_ERR if i.level == "오류" else (FILL_NOTE if i.level == "검토" else None)
        for ci, v in enumerate([i.level, i.institution, i.where, i.item, i.detail, i.file], 1):
            _put(ws2, k, ci, v, fill=fill if ci == 1 else None, align=WRAP if ci == 5 else None)
    if not issues:
        _put(ws2, 2, 1, "점검 결과 지적 사항 없음", border=False)
    for ci, w in enumerate([7, 18, 28, 18, 80, 50], 1):
        ws2.column_dimensions[get_column_letter(ci)].width = w
    ws2.freeze_panes = "A2"
    _print_setup(ws2)
    ws2.auto_filter.ref = f"A1:F{max(2, len(issues) + 1)}"

    for form in FORMS:
        if any(d.form is form for d in docs):
            _form_sheet(wb, form, docs, rows, project)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
