"""전자조회(금융결제원) 회신 양식 4종의 섹션·열 정의.

열 하나는 (출력 이름, 머리글 키워드들, 종류, 행) 으로 정한다.
- 키워드는 공백을 뺀 머리글 조각이다. 여러 줄로 나뉜 머리글은 그중 한 조각만 맞아도 된다.
- 종류: text | id(계좌·증권번호, 줄바꿈 시 공백 없이 잇기) | amount | date | rate | count
- 행: 2행 레코드(증권 9번 거래내역)에서 몇 번째 줄인지. 보통은 1.
출력 열 이름은 Accio 산출물과 맞춰 두어, 기존 조서와 나란히 대조하기 쉽게 했다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Col:
    name: str
    kws: tuple[str, ...]
    kind: str = "text"
    row: int = 1


@dataclass(frozen=True)
class Table:
    key: str                    # 출력 구획 번호 ("1", "2-2", "6-1" ...)
    label: str                  # 출력 구획 제목에 붙일 짧은 이름
    cols: tuple[Col, ...] = ()
    start: str | None = None    # 섹션 안에서 이 표가 시작하는 머리글(공백 제거 정규식). None = 섹션 첫 표
    kv: str | None = None       # "키 : 값" 한 줄짜리 항목이면 키(공백 제거)
    kv_kind: str = "text"
    row_label: bool = False     # 왼쪽 행 이름(전자어음, 수표·어음)이 머리글 없이 붙는 표
    anchor_rows: int = 1        # 레코드 한 건이 차지하는 줄 수(2 = 증권 9번)


@dataclass(frozen=True)
class Section:
    no: int
    title: str
    tables: tuple[Table, ...]


@dataclass(frozen=True)
class FormSpec:
    key: str             # BANK | INVESTMENT | INSURANCE | GUARANTEE
    name: str
    signature: tuple[str, ...]   # 1번 섹션 제목에서 찾을 문구(공백 제거)
    sections: tuple[Section, ...] = field(default_factory=tuple)


def C(name, *kws, kind="text", row=1):
    return Col(name, tuple(kws) if kws else (name.replace(" ", ""),), kind, row)


# ---------------------------------------------------------------- 공통 조각
def _loan(prefix_acct: bool, rate_kw: str, rate_name: str, last_pay_name: str, collat_name: str):
    cols = []
    if prefix_acct:
        cols.append(C("계좌번호", kind="id"))
    cols += [
        C("대출 종류" if not prefix_acct else "대출종류", "대출종류"),
        C("금액_약정한도액", "약정한도액", kind="amount"),
        C("금액_대출금액", "대출금액", kind="amount"),
        C("대출일", kind="date"),
        C("최종만기일", kind="date"),
        C(rate_name, rate_kw, kind="rate"),
        C(last_pay_name, "최종이자지급일", kind="date"),
        C("상환방법"),
        C(collat_name, "담보보증및관련약정", "담보보증및관련약", "담보보증"),
    ]
    return tuple(cols)


def _guarantee_line(note=True):
    cols = [
        C("내용"),
        C("한도액", kind="amount"),
        C("실행금액", kind="amount"),
        C("지급보증 수수료율", "지급보증수수료율", kind="rate"),
        C("기간"),
        C("담보 지급보증", "담보지급보증"),
    ]
    if note:
        cols.append(C("비고"))
    return tuple(cols)


def _bills(purpose_name="담보 견질의 목적", first="구분"):
    return (
        C(first, "구분"),
        C("번호"),
        C("금액", kind="amount"),
        C("발행일자", kind="date"),
        C("만기일자", kind="date"),
        C(purpose_name, "담보견질의목적", "담보·견질의목적"),
    )


def _joint(target_kw="대상여신", target_name="연대보증 등의 대상 여신",
           recv_name="연대보증 등을 제공받은 회사(개인)"):
    return (
        C("내용"),
        C(recv_name, "연대보증등을제공받은회사(개인)", "연대보증등을제공받은"),
        C(target_name, target_kw),
        C("연대보증 등의 한도", "연대보증등의한도"),
        C("담보제공한 자산", "담보제공한자산"),
    )


def _collateral(appraisal_kws=("감정금액",), appraisal_name="감정금액"):
    return (
        C("구분"),
        C("담보보증의 내용", "담보보증의내용", "담보·보증의내용"),
        C("소유자(제공자)", "소유자(제공자)", "소유자"),
        C(appraisal_name, *appraisal_kws, kind="amount"),
        C("설정금액", kind="amount"),
        C("설정순위"),
        C("선순위 설정금액", "선순위설정금액", kind="amount"),
    )


# ---------------------------------------------------------------- BANK
BANK = FormSpec(
    key="BANK", name="은행",
    signature=("당은행에대한금융상품",),
    sections=(
        Section(1, "금융상품", (Table("1", "금융상품", (
            C("금융상품의 종류", "금융상품의종류"),
            C("계좌번호", kind="id"),
            C("금액", kind="amount"),
            C("연이자율", kind="rate"),
            C("최종이자지급일", kind="date"),
            C("만기일", kind="date"),
            C("인출제한 등", "인출제한등", "인출제한"),
        )),)),
        Section(2, "대출거래", (
            Table("2-1", "총 한도액", kv="총한도액", kv_kind="amount"),
            Table("2-2", "대출거래의 내용", _loan(False, "연이율", "이자_연이율", "이자_최종이자지급일",
                                                "담보 보증 및 관련약정"), start=r"대출종류|약정한도액|금액이자"),
        )),
        Section(3, "지급보증 및 기타 약정", (Table("3", "지급보증 및 기타 약정", _guarantee_line(note=False)),)),
        Section(4, "미결제 파생상품", (Table("4", "미결제 파생상품", (
            C("계약의 종류", "계약의종류"),
            C("계약일", kind="date"),
            C("한도액", kind="amount"),
            C("당행의매입금액", "매입금액", kind="amount"),
            C("당행의매도금액", "매도금액", kind="amount"),
            C("계약실행일/만기일", "계약실행일/", "계약실행일"),
            C("약정환율/이자율/주가지수 등", "약정환율/이자율"),
            C("평가금액", kind="amount"),
            C("비고(결제조건 등)", "비고"),
        )),)),
        Section(5, "타인을 위한 담보·연대보증", (Table("5", "타인을 위한 담보·연대보증", _joint()),)),
        Section(6, "교부 어음·수표 용지", (
            Table("6-1", "전자어음", (C("교부일자", kind="date"), C("매수", kind="count")),
                  start=r"^교부일자매수$", row_label=True),
            Table("6-2", "수표·어음", (C("교부일자", kind="date"), C("매수", kind="count"), C("일련번호")),
                  start=r"^교부일자매수일련번호$", row_label=True),
        )),
        Section(7, "미발행·미결제 어음·수표", (
            Table("7-1", "조회기준일 현재 전자어음 미발행 매수", kv="전자어음미발행매수", kv_kind="count"),
            Table("7-2", "미결제 전자어음", (C("만기일자", kind="date"), C("금액", kind="amount"), C("일련번호")),
                  start=r"^만기일자금액일련번호$", row_label=True),
            Table("7-3", "수표·어음", (C("교부일자", kind="date"), C("매수", kind="count"), C("일련번호")),
                  start=r"^교부일자매수일련번호$", row_label=True),
        )),
        Section(8, "담보·견질 어음·수표", (Table("8", "담보·견질 어음·수표",
                                            _bills("담보견질의 목적", "구분(어음 또는 수표)")),)),
        Section(9, "담보·보증 제공 내역", (Table("9", "담보·보증 제공 내역", _collateral()),)),
        Section(10, "당좌거래명세", (Table("10", "당좌거래명세", (
            C("구 분", "구분"),
            C("일 자", "일자", kind="date"),
            C("입금금액", kind="amount"),
            C("지급금액", kind="amount"),
            C("일련번호"),
            C("적 요", "적요"),
        )),)),
    ),
)

# ---------------------------------------------------------------- INVESTMENT
INVESTMENT = FormSpec(
    key="INVESTMENT", name="증권",
    signature=("당사가보유하고있는조회대상회사의유가증권",),
    sections=(
        Section(1, "금융상품", (Table("1", "금융상품", (
            C("계좌번호", kind="id"),
            C("금융상품의 종류", "금융상품의종류"),
            C("금융상품 금액", "금융상품금액", kind="amount"),
            C("예수금", kind="amount"),
            C("신용설정 보증금", "신용설정보증금", kind="amount"),
            C("미수금액", kind="amount"),
            C("담보제공 및 처분제한 등", "담보제공및처분제한등"),
        )),)),
        Section(2, "유가증권 상세명세", (Table("2", "유가증권 상세명세", (
            C("계좌번호", kind="id"),
            C("종목명"),
            C("수량", kind="count"),
            C("액면금액", kind="amount"),
            C("기준가", kind="amount"),
            C("평가액", kind="amount"),
            C("만기일", kind="date"),
            C("담보제공 내역", "담보제공내역"),
            C("비고"),
        )),)),
        Section(3, "대출거래", (Table("3", "대출거래", _loan(True, "연이자율", "이자_연이자율", "이자_최종이자 지급일",
                                                          "담보 보증 및 관련약정")),)),
        Section(4, "지급보증 및 기타 약정", (Table("4", "지급보증 및 기타 약정", _guarantee_line()),)),
        Section(5, "미결제 파생상품", (Table("5", "미결제 파생상품", (
            C("계좌번호", kind="id"),
            C("계약의 종류", "계약의종류"),
            C("종목명"),
            C("계약일", kind="date"),
            C("매수/매도"),
            C("계약수량", kind="count"),
            C("계약체결 당시 매수/매도 가격", "계약체결당시", "매수/매도가격", kind="amount"),
            C("평가금액", kind="amount"),
            C("계약실행일/ 만기일", "계약실행일"),
            C("행사가격 등", "행사가격등"),
        )),)),
        Section(6, "타인을 위한 담보·연대보증", (Table("6", "타인을 위한 담보·연대보증",
                                                 _joint(recv_name="연대보증 등을 제공 받은 회사(개인)")),)),
        Section(7, "담보·견질 어음·수표", (Table("7", "담보·견질 어음·수표", _bills()),)),
        Section(8, "담보·보증 제공 내역", (Table("8", "담보·보증 제공 내역", _collateral()),)),
        Section(9, "거래내역", (Table("9", "거래내역", (
            C("거래일자", kind="date", row=1),
            C("상품명", row=2),
            C("거래번호", row=2),
            C("계좌번호", kind="id", row=1),
            C("계약번호", row=2),
            C("FCM", row=2),
            C("적요명", row=1),
            C("종목명", row=2),
            C("수량", kind="count", row=1),
            C("단가", kind="amount", row=2),
            C("거래금액", kind="amount", row=1),
            C("정산금액", kind="amount", row=2),
            C("수수료", kind="amount", row=1),
            C("제세금", kind="amount", row=2),
            C("신용/상환 금액", "신용/상환금액", kind="amount", row=1),
            C("이자/상환 이자", "이자/상환이자", kind="amount", row=2),
            C("미수발생 금액", "미수발생금액", kind="amount", row=1),
            C("미수/연체료변제금액", kind="amount", row=2),
            C("예수금 잔고", "예수금잔고", kind="amount", row=1),
            C("유가증권잔고", kind="amount", row=2),
            C("처리부점명", row=2),
        ), anchor_rows=2),)),
    ),
)

# ---------------------------------------------------------------- INSURANCE
INSURANCE = FormSpec(
    key="INSURANCE", name="보험",
    signature=("당사에대한보험거래",),
    sections=(
        Section(1, "보험거래", (Table("1", "보험거래", (
            C("보험의 종류", "보험의종류"),
            C("증권번호", kind="id"),
            C("부보금액", kind="amount"),
            C("연간보험료_보장성보험료 및 사업비", "보장성보험료", "및사업비", kind="amount"),
            C("연간보험료_이외", "이외", kind="amount"),
            C("부보기간_시작", "시작", kind="date"),
            C("부보기간_종료", "종료", kind="date"),
            C("누적 적립금", "누적적립금", kind="amount"),
            C("해약환급금", kind="amount"),
            C("연이자율", kind="rate"),
            C("권리제한"),
            C("비고"),
        )),)),
        Section(2, "대출거래", (Table("2", "대출거래", _loan(False, "연이자율", "이자_연이자율", "이자_최종이자 지급일",
                                                          "담보보증 및 관련약정")),)),
        Section(3, "지급보증 및 기타 약정", (Table("3", "지급보증 및 기타 약정", _guarantee_line()),)),
        Section(4, "담보·견질 어음·수표", (Table("4", "담보·견질 어음·수표", _bills()),)),
        Section(5, "타인을 위한 담보·연대보증", (Table("5", "타인을 위한 담보·연대보증",
                                                 _joint(recv_name="연대보증 등을 제공받은 회사 (개인)")),)),
        Section(6, "담보·보증 제공 내역", (Table("6", "담보·보증 제공 내역", _collateral()),)),
    ),
)

# ---------------------------------------------------------------- GUARANTEE (서울보증 등)
GUARANTEE = FormSpec(
    key="GUARANTEE", name="보증보험",
    signature=("의무를보증하기위하여", "보증(보험)의내용"),
    sections=(
        Section(1, "보증(보험)", (Table("1", "보증(보험)", (
            C("보증(보험)의 종류", "보증(보험)의종류", "보증(보험)의"),
            C("증권번호"),
            C("보증상대처(피보험자)", "보증상대처"),
            C("보증금액(보험가입금액)", "보증금액", kind="amount"),
            C("보증잔액", kind="amount"),
            C("연간 보증(보험)료", "연간보증(보험)료", kind="amount"),
            C("보증(보험)기간", "보증(보험)기간", "보증(보험)"),
            C("비고"),
        )),)),
        Section(2, "신용보험", (Table("2", "신용보험", (
            C("상품의 종류", "상품의종류"),
            C("증권번호"),
            C("보험 대상 자산", "보험대상자산"),
            C("보험금액(보증금액)", "보험금액(보증금액)", "보험금액", kind="amount"),
            C("연간보험료", kind="amount"),
            C("보험기간"),
            C("비고"),
        )),)),
        Section(3, "기타 공제·보험", (Table("3", "기타 공제·보험", (
            C("상품의 종류", "상품의종류"),
            C("증권번호"),
            C("보장 금액", "보장금액", kind="amount"),
            C("계약 공제(보험)료", "계약공제(보험)료", kind="amount"),
            C("공제(보험)기간", "공제(보험)기간", "공제(보험)"),
            C("누적적립금", kind="amount"),
            C("해약환급금", kind="amount"),
            C("권리제한"),
            C("비고"),
        )),)),
        Section(4, "대출·융자·투자", (Table("4", "대출·융자·투자", (
            C("대출·융자·투자종류"),
            C("금액_약정한도액", "약정한도액", kind="amount"),
            C("금액_대출·융자·투자금액", "대출·융자·투자금액", kind="amount"),
            C("대출·융자일", kind="date"),
            C("최종만기일", kind="date"),
            C("이자_연이자율", "연이자율", kind="rate"),
            C("이자_최종이자지급일", "최종이자지급일", kind="date"),
            C("상환방법"),
            C("담보·보증 및 관련 약정", "담보·보증및관련약정", "담보·보증및관련"),
        )),)),
        Section(5, "출자금", (Table("5", "출자금", (
            C("출자일", kind="date"),
            C("출자금액", kind="amount"),
            C("출자좌수", kind="count"),
            C("평가금액", kind="amount"),
            C("지분율", kind="rate"),
            C("담보제공"),
        )),)),
        Section(6, "한도거래 및 기타 약정", (Table("6", "한도거래 및 기타 약정", (
            C("내용"),
            C("한도액", kind="amount"),
            C("실행금액", kind="amount"),
            C("기간"),
            C("담보·지급보증"),
            C("비고"),
        )),)),
        Section(7, "담보·견질 어음·수표", (Table("7", "담보·견질 어음·수표", _bills("담보·견질의 목적")),)),
        Section(8, "타인을 위한 담보·연대보증", (Table("8", "타인을 위한 담보·연대보증",
                                                 _joint(target_kw="대상보증·융자등",
                                                        target_name="연대보증 등의 대상 보증·융자 등")),)),
        Section(9, "담보·보증 제공 내역", (Table("9", "담보·보증 제공 내역",
                                            _collateral(("감정(평가)금액", "감정금액"), "감정(평가)금액")),)),
    ),
)

FORMS: tuple[FormSpec, ...] = (BANK, INVESTMENT, INSURANCE, GUARANTEE)
FORM_BY_KEY = {f.key: f for f in FORMS}
