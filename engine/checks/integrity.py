"""값 점검 (B-01 합계·금액 판독, B-07 거래내역 상대계좌 교차대사)."""
from __future__ import annotations

import re
from decimal import Decimal

from ..pipeline import OutRow
from .completeness import Issue

RE_ACCT = re.compile(r"\d{10,16}")


def _acct(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def check_rows(rows: list[OutRow]) -> list[Issue]:
    out: list[Issue] = []
    by_tab: dict[tuple, list[OutRow]] = {}
    notes: dict[tuple, list[str]] = {}
    for r in rows:
        by_tab.setdefault((id(r.doc), r.table.key), []).append(r)
        if r.status not in ("data", "kv"):
            continue
        inst, f = r.doc.institution, r.doc.path.name
        tw = f"{r.table.key}. {r.table.label}"
        for name, c in r.cells.items():
            if c.status == "error":
                out.append(Issue(inst, f, tw, "값 판독 실패", f"[{name}] {c.note}", "오류"))
            elif c.note and c.kind == "amount" and not (c.value == 0 and "KRW로 추정" in c.note):
                notes.setdefault((inst, f, tw, c.note), []).append(f"{name}={c.raw}")

    for (inst, f, tw, note), items in notes.items():
        items = list(dict.fromkeys(items))
        out.append(Issue(inst, f, tw, "금액 표기", f"{note}: {', '.join(items[:6])}" +
                         (f" 외 {len(items) - 6}건" if len(items) > 6 else ""), "참고"))

    # 합계 행 대사
    for (_, key), rs in by_tab.items():
        data = [r for r in rs if r.status == "data"]
        if not data:
            continue
        first = data[0].table.cols[0].name
        totals = [r for r in data if r.cells[first].raw.replace(" ", "") in ("합계", "계", "총계")]
        body = [r for r in data if r not in totals]
        for tot in totals:
            for c in data[0].table.cols:
                if c.kind != "amount" or tot.cells[c.name].value is None:
                    continue
                vals = [b.cells[c.name].value for b in body if b.cells[c.name].value is not None]
                if not vals:
                    continue
                s = sum(vals, Decimal(0))
                if s != tot.cells[c.name].value:
                    out.append(Issue(tot.doc.institution, tot.doc.path.name, f"{key}. {tot.table.label}",
                                     "합계 불일치", f"[{c.name}] 명세 합 {s:,} ≠ 합계행 {tot.cells[c.name].value:,}", "오류"))

    # 거래내역 상대계좌 ↔ 다른 회신본의 계좌번호
    known: dict[str, str] = {}
    for r in rows:
        if r.status == "data" and r.table.key == "1" and "계좌번호" in r.cells:
            a = _acct(r.cells["계좌번호"].raw)
            if len(a) >= 10:
                known[a] = r.doc.institution
    seen = set()
    for r in rows:
        if r.status != "data":
            continue
        src = None
        if r.doc.form and r.doc.form.key == "INVESTMENT" and r.table.key == "9":
            src = " ".join(r.cells[k].raw for k in ("종목명", "적요명") if k in r.cells)
        elif r.doc.form and r.doc.form.key == "BANK" and r.table.key == "10":
            src = r.cells.get("적 요").raw if r.cells.get("적 요") else ""
        if not src:
            continue
        own = {_acct(x.cells["계좌번호"].raw) for x in rows
               if x.doc is r.doc and x.status == "data" and "계좌번호" in x.cells}
        for a in RE_ACCT.findall(src):
            if a in own or (r.doc.institution, a) in seen:
                continue
            seen.add((r.doc.institution, a))
            tw = f"{r.table.key}. {r.table.label}"
            if a in known:
                out.append(Issue(r.doc.institution, r.doc.path.name, tw, "교차대사 일치",
                                 f"거래 상대계좌 {a} = {known[a]} 회신본 1번 계좌", "참고"))
            else:
                out.append(Issue(r.doc.institution, r.doc.path.name, tw, "교차대사 미확인",
                                 f"거래 상대계좌 {a} 가 받은 회신본 계좌 목록에 없습니다. 조회 대상 누락 여부를 검토하세요."))
    return out
