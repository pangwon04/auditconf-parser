"""데모 생성기로 만든 가상 회신본 2부를 끝까지 돌려 본다(엑셀까지)."""
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import make_demo  # noqa: E402


def test_demo_end_to_end(tmp_path):
    make_demo.main(str(tmp_path))
    wb = openpyxl.load_workbook(tmp_path / "demo_result.xlsx")
    assert wb.sheetnames[:3] == ["요약", "점검", "BANK"]
    rows = [r for r in wb["BANK"].iter_rows(values_only=True) if r[0] == "가상은행"]
    nums = {r[8] for r in rows if r[4] in ("기업자유예금", "정기예금")}
    assert nums == {1234567890, 500000000}
    loan = next(r for r in rows if r[4] == "시설자금대출")
    assert 1000000000 in loan and 800000000 in loan   # 붙어 있던 두 금액이 각 열로 나뉜다
    assert [r[8] for r in wb["요약"].iter_rows(min_row=5, values_only=True)] == ["완료", "완료"]
