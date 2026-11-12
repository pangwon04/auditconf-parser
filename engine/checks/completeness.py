"""회신 점검 (B-06) — 회신본이 온전한지, 조회 조건과 맞는지 본다."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from ..forms.parser import ParsedDoc


@dataclass
class Issue:
    institution: str
    file: str
    where: str
    item: str
    detail: str
    level: str = "검토"     # 오류 | 검토 | 참고


def _iso(s: str | None) -> date | None:
    try:
        y, m, d = map(int, (s or "").split("-"))
        return date(y, m, d)
    except Exception:
        return None


def check_doc(doc: ParsedDoc, expect: dict) -> list[Issue]:
    out: list[Issue] = []
    inst, f = doc.institution, doc.path.name

    def add(where, item, detail, level="검토"):
        out.append(Issue(inst, f, where, item, detail, level))

    if not doc.has_text:
        add("문서", "스캔본", "텍스트 레이어가 없는 스캔본입니다. 이번 버전은 OCR을 지원하지 않아 수기 키인이 필요합니다.", "오류")
        return out
    if doc.form is None:
        add("문서", "양식 미인식", "전자조회 4종 양식(은행·증권·보험·보증보험) 중 어느 것도 아닙니다.", "오류")
        return out

    m = doc.meta
    if not m.get("kftc_issued"):
        add("문서", "발급 경로", "'금융결제원을 통하여 제공' 문구를 찾지 못했습니다.", "검토")
    # 쪽번호
    pn = doc.page_numbers
    if not pn:
        add("문서", "쪽번호", "쪽번호(n/m)를 찾지 못했습니다.")
    else:
        totals = {t for _, _, t in pn}
        nums = sorted(n for _, n, _ in pn)
        if len(totals) != 1 or totals.pop() != doc.page_count:
            add("문서", "쪽번호", f"표기된 총 쪽수와 실제 쪽수({doc.page_count})가 다릅니다.", "오류")
        elif nums != list(range(1, doc.page_count + 1)):
            add("문서", "쪽번호", f"빠진 쪽이 있습니다: 표기 {nums}", "오류")
    # 머리말
    for key, label in (("company", "조회대상 회사"), ("biz_no", "사업자등록번호"), ("as_of", "조회기준일"),
                       ("auditor_firm", "감사인")):
        if not m.get(key):
            add("머리말", f"{label} 공란", f"{label}을(를) 찾지 못했습니다.", "오류")
    if expect.get("biz_no") and m.get("biz_no") and m["biz_no"] != expect["biz_no"]:
        add("머리말", "사업자번호 불일치", f"{m['biz_no']} (다른 회신본 다수: {expect['biz_no']})", "오류")
    if expect.get("as_of") and m.get("as_of") and m["as_of"] != expect["as_of"]:
        add("머리말", "조회기준일 불일치", f"{m['as_of']} (다른 회신본 다수: {expect['as_of']})", "오류")

    as_of = _iso(m.get("as_of"))
    blank_conf: list[str] = []
    for s in doc.sections:
        where = f"{s.section.no}. {s.section.title}"
        if not s.found:
            add(where, "섹션 누락", "이 섹션 제목을 찾지 못했습니다.", "오류")
            continue
        if s.confirmer is None:
            add(where, "확인자 줄 없음", "'확인자 소속 및 성명' 줄을 찾지 못했습니다.")
        elif not s.confirmer.strip():
            blank_conf.append(where)
        for t in s.tables:
            tw = f"{t.table.key}. {t.table.label}"
            if t.status == "inquire":
                add(tw, "미기재", f"'{t.raw}' — 발급기관에 직접 확인이 필요합니다.", "오류")
            elif t.status == "missing" and t.table.kv is None:
                add(tw, "내용 없음", "표 구간을 찾지 못했거나 비어 있습니다. " + " ".join(t.notes), "오류")
            for n in t.notes:
                if "오류 문구" in n or "짝이" in n:
                    add(tw, "양식 이상", n)
        if s.period:
            st, en = s.period
            if st.startswith("0000") or en.startswith("0000"):
                add(where, "거래내역 기간", f"기간이 자리표시자({st} ~ {en})로 회신되었습니다.")
            elif as_of:
                d0, d1 = _iso(st), _iso(en)
                fy_start = date(as_of.year - 1, as_of.month, as_of.day) + timedelta(days=1)
                if doc.form.key == "BANK" and (d0 != fy_start or d1 != as_of):
                    add(where, "거래내역 기간", f"{st} ~ {en} — 조회기간({fy_start} ~ {as_of})과 다릅니다.")
                elif d0 and d1 and (d0 > as_of or d1 < as_of):
                    add(where, "거래내역 기간", f"{st} ~ {en} — 조회기준일({as_of})을 포함하지 않습니다.")
    found = [s for s in doc.sections if s.found]
    if blank_conf and len(blank_conf) == len(found):
        add("전 섹션", "확인자 공란", "모든 섹션의 확인자 소속·성명이 비어 있습니다.")
    else:
        for w in blank_conf:
            add(w, "확인자 공란", "확인자 소속·성명이 비어 있습니다.")
    return out


def consensus(docs: list[ParsedDoc]) -> dict:
    out = {}
    for key in ("biz_no", "as_of", "company"):
        c = Counter(d.meta.get(key) for d in docs if d.meta.get(key))
        if c:
            out[key] = c.most_common(1)[0][0]
    return out
