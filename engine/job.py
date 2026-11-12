"""작업 단위 실행 (backend ↔ parser 계약).

    python -m engine.job <job.json>

교환 디렉터리 = job.json이 있는 디렉터리. job의 PDF를 읽어 result.json과 result.xlsx를 쓴다.
계약: contracts/parse-job.schema.json, contracts/parse-result.schema.json
종료 코드: 0 = ok/partial, 2 = 작업 실패(result.json에 status=failed).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import jsonschema

from . import __version__ as ENGINE_VERSION
from .checks.completeness import check_doc, consensus
from .checks.integrity import check_rows
from .excel.writer import write_workbook
from .pipeline import load, rows_for

# shortcut: 저장소 배치(parser/ 옆 contracts/)를 가정, 컨테이너에서는 AUDITCONF_CONTRACTS로 지정
CONTRACTS = Path(os.environ.get("AUDITCONF_CONTRACTS") or Path(__file__).resolve().parents[2] / "contracts")
LEVEL = {"오류": "error", "검토": "review", "참고": "info"}
META_KEYS = ("company", "biz_no", "as_of", "issued_on", "auditor_firm", "auditor_cpa", "kftc_issued")


class JobError(Exception):
    pass


def schema(name: str) -> dict:
    return json.loads((CONTRACTS / f"{name}.schema.json").read_text(encoding="utf-8"))


def _inside(base: Path, rel: str) -> Path:
    """교환 디렉터리 밖(심볼릭 링크 포함)을 가리키면 거부한다."""
    p = (base / rel).resolve()
    if not p.is_relative_to(base.resolve()):
        raise JobError(f"교환 디렉터리 밖 경로: {rel}")
    return p


def _value(v):
    if v is None or isinstance(v, int):
        return v
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _outcome(d) -> str:
    # excel.writer._result_text와 같은 순서
    if d.meta.get("error"):
        return "failed"
    if not d.has_text:
        return "scan"
    if d.form is None:
        return "unknown_form"
    return "no_activity" if d.all_none else "done"


def _page(p):
    return None if p is None else p + 1


def _document(d, inp, rows) -> dict:
    return {
        "file_id": inp["file_id"],
        "name": inp["name"],
        "outcome": _outcome(d),
        "error": d.meta.get("error"),
        "page_count": d.page_count,
        "has_text": d.has_text,
        "form": d.form.key if d.form else None,
        "institution": d.meta.get("institution") or Path(inp["name"]).stem,
        "meta": {k: d.meta[k] for k in META_KEYS if d.meta.get(k) not in (None, "")},
        "sections": [{
            "no": s.section.no, "title": s.title or s.section.title, "found": s.found, "page": _page(s.page),
            "confirmer": s.confirmer, "period": list(s.period) if s.period else None,
        } for s in d.sections],
        "rows": [{
            "table_key": r.table.key, "table_label": r.table.label, "status": r.status,
            "page": _page(r.page), "notes": list(r.notes),
            "cells": {n: {"raw": c.raw, "kind": c.kind, "status": c.status, "note": c.note,
                          "ccy": c.ccy, "value": _value(c.value)} for n, c in r.cells.items()},
        } for r in rows if r.doc is d],
    }


def execute(job: dict, base: Path) -> dict:
    jsonschema.validate(job, schema("parse-job"))
    stored = [_inside(base, i["path"]) for i in job["inputs"]]
    if len({p.name for p in stored}) != len(stored):
        raise JobError("입력 파일 이름이 겹칩니다(점검 결과를 파일에 연결할 수 없음).")
    out_json = _inside(base, job["output"]["result_json"])
    out_xlsx = _inside(base, job["output"]["result_xlsx"])

    docs = load(stored)
    by_name = {d.path.name: (d, inp) for d, inp in zip(docs, job["inputs"])}
    exp = consensus([d for d in docs if d.has_text])
    rows = [r for d in docs for r in rows_for(d)]
    issues = [i for d in docs for i in check_doc(d, exp)] + check_rows(rows)
    proj = job.get("options", {}).get("project") or \
        f"{exp.get('company', '조회대상 회사')} 금융기관조회서 (기준일 {exp.get('as_of', '-')})"

    result = {
        "schema_version": "1", "job_id": job["job_id"], "engine_version": ENGINE_VERSION,
        "status": "partial" if any(d.meta.get("error") for d in docs) else "ok", "error": None,
        "project": proj,
        "expect": {k: exp[k] for k in ("company", "biz_no", "as_of") if exp.get(k)},
        "counts": {v: sum(1 for i in issues if i.level == k) for k, v in LEVEL.items()},
        "documents": [_document(d, inp, rows) for d, inp in zip(docs, job["inputs"])],
        "issues": [{
            "level": LEVEL[i.level], "file_id": by_name[i.file][1]["file_id"] if i.file in by_name else None,
            "institution": i.institution, "where": i.where, "item": i.item, "detail": i.detail,
        } for i in issues],
    }
    # 엑셀 '원본 파일' 열은 저장 이름이 아니라 사용자 파일명으로
    for i in issues:
        if i.file in by_name:
            i.file = Path(by_name[i.file][1]["name"]).name
    for d, inp in zip(docs, job["inputs"]):
        d.path = d.path.with_name(Path(inp["name"]).name)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    write_workbook(out_xlsx, docs, rows, issues, proj)
    _write(out_json, result)
    return result


def _write(path: Path, result: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


def _fail_path(job, base: Path) -> Path:
    """잘못된 job이라도 결과를 돌려줄 곳: 쓸 수 있으면 지정 경로, 아니면 result.json."""
    try:
        rel = job["output"]["result_json"]
        jsonschema.validate(rel, schema("parse-job")["$defs"]["relpath"])
        return _inside(base, rel)
    except Exception:
        return base / "result.json"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("사용법: python -m engine.job <job.json>", file=sys.stderr)
        return 2
    job_path = Path(argv[0]).resolve()
    base, job = job_path.parent, None
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
        r = execute(job, base)
    except (OSError, ValueError, JobError, jsonschema.ValidationError) as e:
        msg = e.message if isinstance(e, jsonschema.ValidationError) else str(e)
        _write(_fail_path(job, base), {
            "schema_version": "1", "job_id": str((job or {}).get("job_id", "")) if isinstance(job, dict) else "",
            "engine_version": ENGINE_VERSION, "status": "failed", "error": f"{type(e).__name__}: {msg}",
            "project": "", "expect": {}, "counts": {"error": 0, "review": 0, "info": 0},
            "documents": [], "issues": []})
        print(f"작업 실패: {msg}", file=sys.stderr)
        return 2
    c = r["counts"]
    print(f"{r['job_id']}: 회신본 {len(r['documents'])}부 → {r['status']} (오류 {c['error']} · 검토 {c['review']} · 참고 {c['info']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
