"""engine.job: 가상 회신본 → result.json(계약 검증) + result.xlsx(CLI와 동일)."""
import json
import sys
from pathlib import Path

import jsonschema
import openpyxl

from engine import job
from engine.cli import run

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import make_demo  # noqa: E402

DEPOSITS = [("기업자유예금", "11122233344455", "(KRW)1,234,567,890 ()", "0.1", "20251220", "00000000"),
            ("외화보통예금", "11122233399999", "(USD)45,678.90 ()", "-", "20251220", "00000000")]


def _job(tmp_path, inputs, **extra):
    j = {"schema_version": "1", "job_id": "job-1", "inputs": inputs,
         "output": {"result_json": "out/result.json", "result_xlsx": "out/result.xlsx"}, **extra}
    p = tmp_path / "job.json"
    p.write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    return p


def _result(tmp_path, path="out/result.json"):
    r = json.loads((tmp_path / path).read_text(encoding="utf-8"))
    jsonschema.validate(r, job.schema("parse-result"))
    return r


def test_job_writes_valid_result(tmp_path):
    (tmp_path / "in").mkdir()
    make_demo.bank_pdf(tmp_path / "in" / "f1.pdf", "가상은행", DEPOSITS)
    (tmp_path / "in" / "f2.pdf").write_bytes(b"not a pdf")
    p = _job(tmp_path, [{"file_id": "a", "path": "in/f1.pdf", "name": "가상은행_회신.pdf"},
                        {"file_id": "b", "path": "in/f2.pdf", "name": "깨진.pdf"}])
    assert job.main([str(p)]) == 0
    r = _result(tmp_path)
    assert (r["job_id"], r["status"]) == ("job-1", "partial")
    ok, bad = r["documents"]
    assert (ok["file_id"], ok["outcome"], ok["form"]) == ("a", "done", "BANK")
    assert (bad["outcome"], bad["error"] is not None) == ("failed", True)
    vals = {row["cells"]["금액"]["value"]: row["cells"]["금액"]["ccy"]
            for row in ok["rows"] if row["status"] == "data" and "금액" in row["cells"]}
    assert vals == {"1234567890": "KRW", "45678.90": "USD"}     # 금액은 10진 문자열
    assert all(row["page"] is None or row["page"] >= 1 for row in ok["rows"])
    assert {i["file_id"] for i in r["issues"]} <= {"a", "b"}
    # 엑셀 '원본 파일'은 저장 이름이 아닌 사용자 파일명
    wb = openpyxl.load_workbook(tmp_path / "out" / "result.xlsx")
    files = {c for row in wb["요약"].iter_rows(values_only=True) for c in row if isinstance(c, str) and c.endswith(".pdf")}
    assert files == {"가상은행_회신.pdf", "깨진.pdf"}


def test_job_excel_matches_cli(tmp_path):
    (tmp_path / "in").mkdir()
    make_demo.bank_pdf(tmp_path / "in" / "가상은행_회신.pdf", "가상은행", DEPOSITS)
    p = _job(tmp_path, [{"file_id": "a", "path": "in/가상은행_회신.pdf", "name": "가상은행_회신.pdf"}],
             options={"project": "데모"})
    assert job.main([str(p)]) == 0
    run([str(tmp_path / "in")], str(tmp_path / "cli.xlsx"), "데모")
    a, b = (openpyxl.load_workbook(f) for f in (tmp_path / "out" / "result.xlsx", tmp_path / "cli.xlsx"))
    assert a.sheetnames == b.sheetnames
    for name in a.sheetnames:
        ra = [r for i, r in enumerate(a[name].iter_rows(values_only=True)) if not (name == "요약" and i == 1)]
        rb = [r for i, r in enumerate(b[name].iter_rows(values_only=True)) if not (name == "요약" and i == 1)]
        assert ra == rb, name   # 요약 2행(생성 시각)만 뺀다


def test_job_rejects_escape_path(tmp_path):
    p = _job(tmp_path, [{"file_id": "a", "path": "../secret.pdf", "name": "x.pdf"}])
    assert job.main([str(p)]) == 2
    r = _result(tmp_path)
    assert r["status"] == "failed" and r["error"]
    assert not (tmp_path / "out" / "result.xlsx").exists()


def test_job_schema_rejects_bad_jobs():
    s = job.schema("parse-job")
    good = {"schema_version": "1", "job_id": "j", "inputs": [{"file_id": "a", "path": "a.pdf", "name": "a.pdf"}],
            "output": {"result_json": "r.json", "result_xlsx": "r.xlsx"}}
    jsonschema.validate(good, s)
    for path in ("/etc/x.pdf", "C:/x.pdf", "..", "a/../../x.pdf", "a\\..\\x.pdf", "\\\\srv\\x.pdf"):
        bad = json.loads(json.dumps(good))
        bad["inputs"][0]["path"] = path
        try:
            jsonschema.validate(bad, s)
        except jsonschema.ValidationError:
            continue
        raise AssertionError(f"통과하면 안 됨: {path}")
    for bad in ({**good, "inputs": []}, {**good, "extra": 1}, {k: v for k, v in good.items() if k != "output"}):
        try:
            jsonschema.validate(bad, s)
        except jsonschema.ValidationError:
            continue
        raise AssertionError(bad)


def test_file_name_is_not_excel_formula(tmp_path):
    (tmp_path / "in").mkdir()
    make_demo.bank_pdf(tmp_path / "in" / "f1.pdf", "가상은행", DEPOSITS)
    evil = "=SUM(1,2).pdf"
    p = _job(tmp_path, [{"file_id": "a", "path": "in/f1.pdf", "name": evil}])
    assert job.main([str(p)]) == 0
    wb = openpyxl.load_workbook(tmp_path / "out" / "result.xlsx")
    cells = [c for ws in wb for row in ws.iter_rows() for c in row if c.value == evil]
    assert cells and all(c.data_type == "s" for c in cells)
