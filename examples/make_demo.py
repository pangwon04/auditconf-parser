"""가상 회사·가상 은행의 전자조회 회신 PDF를 만들고, 엔진으로 키인 엑셀까지 만든다.

    python examples/make_demo.py            # demo/ 폴더에 PDF 2부와 결과 엑셀 생성

모든 회사명·계좌·금액은 지어낸 값이다. 실제 회신본의 배치(좌표)를 흉내 낸다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

KO, EN = pymupdf.Font("korea"), pymupdf.Font("helv")
SIZE = 9


class Writer:
    def __init__(self, institution: str):
        self.doc = pymupdf.open()
        self.inst = institution
        self.page = None
        self.y = 0.0
        self._new_page()

    def _new_page(self):
        self.page = self.doc.new_page(width=842, height=595)
        self.y = 40.0
        self.text(742, 486, self.inst)

    def text(self, x: float, y: float, s: str):
        """공백으로 나눈 낱말마다 글꼴을 골라 찍는다(한글은 CJK 글꼴, 숫자·영문은 Helvetica)."""
        for word in s.split(" "):
            if not word:
                x += 3
                continue
            font, name = (EN, "helv") if word.isascii() else (KO, "korea")
            # 낱말 뒤에 실제 공백 문자를 넣어야 PDF 텍스트 레이어에서 낱말이 나뉜다
            self.page.insert_text((x, y), word + " ", fontname=name, fontsize=SIZE)
            x += font.text_length(word + " ", fontsize=SIZE)

    def row(self, cells: list[tuple[float, str]], gap: float = 14):
        if self.y > 440:
            self._new_page()
        for x, s in cells:
            self.text(x, self.y, s)
        self.y += gap

    def space(self, h: float):
        self.y += h

    def section(self, title: str, header_rows: list[list[tuple[float, str]]], body: list[list[tuple[float, str]]],
                confirmer: str = "본점 홍길동"):
        if self.y > 360:
            self._new_page()
        self.row([(33, title)], 22)
        for hr in header_rows:
            self.row(hr, 10)
        self.space(8)
        for b in body:
            self.row(b)
        self.space(14)
        self.row([(515, f"확인자 소속 및 성명 : {confirmer}")], 40)

    def save(self, path: Path, issued: str):
        self.row([(418, f"{issued} {self.inst} 본점")], 20)
        self.row([(560, "본점 담당자 : 김예시")], 20)
        self.row([(476, "(문의전화 : 0200000000 )")], 40)
        self.row([(136, "본 조회서는 해당 금융기관에서 발급한 것이며, 금융결제원을 통하여 제공되었습니다.")], 20)
        n = self.doc.page_count
        for i, p in enumerate(self.doc):
            p.insert_text((413, 560), f"{i + 1}/{n}", fontname="helv", fontsize=SIZE)
        self.doc.save(path)


NONE = "해당 거래 없음"


def header(w: Writer, company: str, biz: str):
    w.row([(48, "가나회계법인 담당공인회계사 : 이감사 귀중")], 32)
    w.row([(43, f"조회대상 회사: {company} 사업자등록번호 : {biz} 조회기준일 : 2025 년 12 월 31 일 현재")], 34)


def bank_pdf(path: Path, inst: str, accounts, loan=None):
    w = Writer(inst)
    header(w, "주식회사 예시상사", "123-45-67890")
    w.section("1. 조회기준일 현재 조회대상회사의 당 은행에 대한 금융상품의 내용은 다음과 같습니다.",
              [[(45, "금융상품의 종류"), (163, "계좌번호"), (275, "금액"), (352, "연이자율"), (414, "최종이자지급일"),
                (508, "만기일"), (661, "인출제한 등")]],
              [[(50, k), (147, a), (240, amt), (360, r), (427, d), (502, m)] for k, a, amt, r, d, m in accounts])
    w.row([(33, "2. 조회기준일 현재 조회대상회사에 대한 당 은행의 대출거래의 내용은 다음과 같습니다.")], 16)
    w.row([(42, "총 한도액 : -")], 20)
    body = [[(34, loan[0]), (126, loan[1]), (207, loan[2]), (291, loan[3]), (355, loan[4]), (454, loan[5]),
             (495, loan[6]), (572, loan[7]), (717, loan[8])]] if loan else [[(346, NONE)]]
    for hr in ([(194, "금액"), (470, "이자")],
               [(59, "대출 종류"), (296, "대출일"), (352, "최종만기일"), (580, "상환방법"), (681, "담보 보증 및 관련약정")],
               [(141, "약정한도액"), (222, "대출금액"), (428, "연이율"), (482, "최종이자지급일")]):
        w.row(hr, 10)
    w.space(8)
    for b in body:
        w.row(b)
    w.space(14)
    w.row([(515, "확인자 소속 및 성명 : 본점 홍길동")], 40)
    w.section("3. 조회기준일 현재 조회대상회사에 대한 당 은행의 지급보증 및 기타 약정사항의 내용은 다음과 같습니다.",
              [[(104, "내용"), (232, "한도액"), (328, "실행금액"), (403, "지급보증수수료율"), (517, "기간"), (662, "담보지급보증")]],
              [[(337, NONE)]])
    w.section("4. 조회기준일 현재 조회대상회사의 미결제파생상품계약 등의 내용은 다음과 같습니다.",
              [[(62, "계약의 종류"), (161, "계약일"), (232, "한도액"), (306, "매입금액"), (389, "매도금액"),
                (460, "계약실행일/"), (518, "약정환율/이자율"), (602, "평가금액"), (720, "비고")]],
              [[(392, NONE)]])
    w.section("5. 조회기준일 현재 조회대상회사가 타 법인(개인)을 위하여 당행 앞으로 제공한 담보 및 연대보증의 내용은 다음과 같습니다.",
              [[(103, "내용"), (219, "연대보증 등을 제공받은"), (394, "대상 여신"), (521, "연대보증 등의 한도"), (687, "담보제공한 자산")]],
              [[(384, NONE)]])
    w.row([(33, "6. 당 은행이 2025년 01월 01일 부터 2025년 12월 31일 까지 조회대상에 교부한 전자어음, 어음수표의 용지는 다음과 같습니다.")], 30)
    w.row([(183, "교부일자"), (349, "매수")], 15)
    w.row([(63, "전자어음"), (259, NONE)], 30)
    w.row([(184, "교부일자"), (348, "매수"), (609, "일련번호")], 15)
    w.row([(62, "수표·어음"), (443, NONE)], 30)
    w.row([(515, "확인자 소속 및 성명 : 본점 홍길동")], 40)
    w.row([(33, "7. 당 은행이 조회대상회사에게 교부한 전자어음과 어음·수표 중 미발행·미결제·미회수 내역은 다음과 같습니다.")], 20)
    w.row([(31, "※ 조회기준일 현재 전자어음 미발행 매수 : 0 매")], 28)
    w.row([(185, "만기일자"), (349, "금액"), (607, "일련번호")], 15)
    w.row([(49, "미결제 전자어음"), (442, NONE)], 28)
    w.row([(185, "교부일자"), (349, "매수"), (608, "일련번호")], 15)
    w.row([(62, "수표·어음"), (442, NONE)], 30)
    w.row([(515, "확인자 소속 및 성명 : 본점 홍길동")], 40)
    w.section("8. 당 은행이 조회대상회사로부터 조회기준일 현재 담보, 견질 목적으로 보관하고 있는 어음이나 수표의 내역은 다음과 같습니다.",
              [[(72, "구분"), (173, "번호"), (291, "금액"), (394, "발행일자"), (482, "만기일자"), (643, "담보견질의 목적")]],
              [[(383, NONE)]])
    w.section("9. 조회기준일 현재 조회대상회사의 자산 등이 당 은행에 담보와 보증 등으로 제공된 내역은 다음과 같습니다.",
              [[(71, "구분"), (161, "담보보증의 내용"), (284, "소유자(제공자)"), (410, "감정금액"), (523, "설정금액"),
                (618, "설정순위"), (706, "선순위 설정금액")]],
              [[(72, "공장"), (150, "경기 가상시 1번지"), (265, "주식회사 예시상사"), (395, "KRW 2500000000.00"),
                (510, "KRW 1200000000.00"), (634, "1"), (740, "KRW 0.00")]] if loan else [[(424, NONE)]])
    w.section("10. 2025년 01월 01일 부터 2025년 12월 31일 까지 조회대상회사가 거래한 당좌거래명세는 다음과 같습니다.",
              [[(70, "구 분"), (167, "일 자"), (264, "입금금액"), (375, "지급금액"), (489, "일련번호"), (677, "적 요")]],
              [[(387, NONE)]])
    w.save(path, "2026년 01월 14일")


def main(out_dir: str = "demo"):
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    bank_pdf(out / "가상은행_회신.pdf", "가상은행", [
        ("기업자유예금", "11122233344455", "(KRW)1,234,567,890 ()", "0.1", "20251220", "00000000"),
        ("외화보통예금", "11122233399999", "(USD)45,678.90 ()", "-", "20251220", "00000000"),
        ("정기예금", "11122233377777", "(KRW)500,000,000 ()", "3.25", "20251115", "20261115"),
    ], loan=("시설자금대출", "KRW 1,000,000,000", "KRW 800,000,000", "20250301", "20280301", "4.15", "20251201",
             "만기일시상환", "공장"))
    bank_pdf(out / "예시저축은행_회신.pdf", "예시저축은행", [
        ("보통예금", "99988877766655", "KRW 98,765,432 ()", "0.1", "20251221", "00000000"),
    ])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from engine.cli import run
    run([str(out)], str(out / "demo_result.xlsx"), "데모 — 가상 회사 금융기관조회서")


if __name__ == "__main__":
    main(*sys.argv[1:])
