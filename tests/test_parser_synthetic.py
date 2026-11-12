"""가상의 은행 회신본(금융결제원 양식 모양)을 만들어 파서를 검증한다. 실제 고객 자료는 쓰지 않는다."""
from decimal import Decimal

import pymupdf
import pytest

from engine.forms.parser import parse_pdf
from engine.pipeline import rows_for

F = "korea"


def _t(page, x, y, s, size=9):
    # 한글은 CJK 내장 글꼴, 숫자·영문은 Helvetica(실제 회신본처럼 좁은 글자폭)
    page.insert_text((x, y), s, fontname="helv" if s.isascii() else F, fontsize=size)


@pytest.fixture
def bank_pdf(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page(width=842, height=595)
    _t(p, 48, 50, "가나회계법인 담당공인회계사 : 홍길동 귀중")
    _t(p, 43, 82, "조회대상 회사: 주식회사 예시 사업자등록번호 : 123-45-67890 조회기준일 : 2025 년 12 월 31 일 현재")
    _t(p, 33, 115, "1. 조회기준일 현재 조회대상회사의 당 은행에 대한 금융상품의 내용은 다음과 같습니다.")
    for x, s in ((45, "금융상품의 종류"), (163, "계좌번호"), (275, "금액"), (352, "연이자율"),
                 (414, "최종이자지급일"), (508, "만기일"), (661, "인출제한 등")):
        _t(p, x, 140, s)
    # 1행: 한 줄짜리, 2행: 금액이 위·아래로 나뉜 양식
    for x, s in ((61, "보통예금"), (147, "11112222333344"), (255, "(KRW)1,234,567 ()"),
                 (405, "-"), (427, "20251220"), (502, "00000000")):
        _t(p, x, 158, s)
    _t(p, 244, 176, "USD"); _t(p, 274, 176, "9,876.50")
    for x, s in ((56, "외화예금"), (147, "55556666777788"), (427, "20251221"), (502, "20260131")):
        _t(p, x, 182, s)
    _t(p, 326, 188, "()")
    _t(p, 515, 225, "확인자 소속 및 성명 : 본점 김예시")
    _t(p, 33, 290, "2. 조회기준일 현재 조회대상회사에 대한 당 은행의 대출거래의 내용은 다음과 같습니다.")
    _t(p, 42, 306, "총 한도액 : -")
    _t(p, 194, 326, "금액"); _t(p, 470, 326, "이자")
    for x, s in ((59, "대출 종류"), (296, "대출일"), (352, "최종만기일"), (580, "상환방법"), (681, "담보 보증 및 관련약정")):
        _t(p, x, 336, s)
    for x, s in ((141, "약정한도액"), (222, "대출금액"), (428, "연이율"), (482, "최종이자지급일")):
        _t(p, x, 346, s)
    _t(p, 346, 364, "해당 거래 없음")
    _t(p, 514, 400, "확인자 소속 및 성명 : 본점 김예시")
    _t(p, 413, 560, "1/1")
    path = tmp_path / "bank.pdf"
    doc.save(path)
    return path


def test_bank_sections(bank_pdf):
    d = parse_pdf(bank_pdf)
    assert d.form.key == "BANK"
    assert d.meta["biz_no"] == "123-45-67890" and d.meta["as_of"] == "2025-12-31"
    s1 = d.sections[0]
    assert s1.found and s1.confirmer == "본점 김예시"
    recs = s1.tables[0].records
    assert [r.values["계좌번호"] for r in recs] == ["11112222333344", "55556666777788"]
    assert recs[1].values["금액"] == "USD 9,876.50 ()"
    s2 = d.sections[1]
    assert s2.tables[0].kv_value == "-"
    assert s2.tables[1].status == "none"

    rows = [r for r in rows_for(d) if r.table.key == "1"]
    assert rows[0].cells["금액"].value == Decimal("1234567")
    assert rows[1].cells["금액"].ccy == "USD"
    assert rows[0].cells["만기일"].status == "placeholder"
