"""명령줄 실행.

    python -m engine.cli <PDF 폴더 또는 파일들> -o 결과.xlsx [--project "FY2025 ○○ 금융기관조회서"]

PDF는 읽기만 하고 고치지 않는다. 네트워크를 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checks.completeness import check_doc, consensus
from .checks.integrity import check_rows
from .excel.writer import write_workbook
from .pipeline import load, rows_for


def collect(inputs: list[str]) -> list[Path]:
    out: list[Path] = []
    for s in inputs:
        p = Path(s)
        if p.is_dir():
            out += sorted(q for q in p.rglob("*") if q.suffix.lower() == ".pdf")
        elif p.suffix.lower() == ".pdf" and p.exists():
            out.append(p)
        else:
            print(f"건너뜀(없거나 PDF 아님): {p}", file=sys.stderr)
    return out


def run(inputs: list[str], out: str, project: str | None = None) -> Path:
    paths = collect(inputs)
    if not paths:
        raise SystemExit("처리할 PDF가 없습니다.")
    docs = load(paths)
    exp = consensus([d for d in docs if d.has_text])
    rows = [r for d in docs for r in rows_for(d)]
    issues = [i for d in docs for i in check_doc(d, exp)] + check_rows(rows)
    proj = project or f"{exp.get('company', '조회대상 회사')} 금융기관조회서 (기준일 {exp.get('as_of', '-')})"
    path = write_workbook(Path(out), docs, rows, issues, proj)
    lv = {}
    for i in issues:
        lv[i.level] = lv.get(i.level, 0) + 1
    print(f"회신본 {len(docs)}부 → {path}  (오류 {lv.get('오류', 0)} · 검토 {lv.get('검토', 0)} · 참고 {lv.get('참고', 0)})")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="auditconf", description="전자조회 회신 PDF → 키인 엑셀")
    ap.add_argument("inputs", nargs="+", help="PDF 파일 또는 폴더")
    ap.add_argument("-o", "--out", default="auditconf_result.xlsx", help="결과 엑셀 경로")
    ap.add_argument("--project", help="엑셀 상단 프로젝트명")
    a = ap.parse_args(argv)
    run(a.inputs, a.out, a.project)


if __name__ == "__main__":
    main()
