"""전자조회 회신 PDF 한 부를 양식 정의(schemas)에 맞춰 표 단위 레코드로 읽는다 (A-04~A-08).

흐름
  1. 텍스트 레이어 → 줄(layout)
  2. 1번 섹션 제목으로 양식(BANK/INVESTMENT/INSURANCE/GUARANTEE) 판별
  3. "N." 제목 줄로 섹션을 자르고, 섹션 안에서 표(머리글) 구간을 자른다
  4. 머리글 줄에서 열마다 x 중심을 찾고, 데이터 줄의 칸을 가장 가까운 열 구간에 넣는다
  5. 칸이 많은 줄을 기준 줄로 삼고, 위·아래로 넘친 줄(줄바꿈된 셀)을 가까운 기준 줄에 붙여 레코드를 만든다
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..extract.layout import Chunk, Layout, Line, build_layout
from ..extract.text_layer import read_pdf
from ..normalize.none_words import is_error_text, is_inquire, is_none_word
from .schemas import FORMS, Col, FormSpec, Section, Table

RE_DATE_KO = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
RE_DATA_LIKE = re.compile(r"\d{3,}|KRW|USD|WON|EUR|JPY|CNY")
HEADER_ABSORB_GAP = 7.5     # 마지막 머리글 줄 바로 아래 붙은 머리글 조각 허용 간격
ISOLATED_GAP = 13.0         # 이 간격보다 멀리 떨어진 줄은 단독 레코드로 본다


# ------------------------------------------------------------------ 결과 자료형
@dataclass
class Record:
    values: dict[str, str]
    page: int
    y: float


@dataclass
class TableResult:
    table: Table
    status: str                 # data | none | inquire | missing | kv
    records: list[Record] = field(default_factory=list)
    kv_value: str | None = None
    raw: str = ""               # 'none' / 'inquire' 일 때 원문
    notes: list[str] = field(default_factory=list)
    page: int | None = None
    located: dict[str, float] = field(default_factory=dict)


@dataclass
class SectionResult:
    section: Section
    found: bool
    title: str = ""
    page: int | None = None
    tables: list[TableResult] = field(default_factory=list)
    confirmer: str | None = None
    period: tuple[str, str] | None = None


@dataclass
class ParsedDoc:
    path: Path
    page_count: int
    has_text: bool
    form: FormSpec | None
    meta: dict
    page_numbers: list[tuple[int, int, int]]
    sections: list[SectionResult] = field(default_factory=list)

    @property
    def institution(self) -> str:
        return self.meta.get("institution") or self.path.stem

    @property
    def all_none(self) -> bool:
        tabs = [t for s in self.sections for t in s.tables if t.status != "kv"]
        return bool(tabs) and all(t.status == "none" for t in tabs)


# ------------------------------------------------------------------ 도우미
def _compact(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _chars(line: Line) -> list[tuple[str, float]]:
    """줄의 글자(공백 제외)와 각 글자의 x 중심."""
    out = []
    for w in line.words:
        t = w.text
        n = len(t)
        if not n:
            continue
        step = (w.x1 - w.x0) / n
        for i, ch in enumerate(t):
            if not ch.isspace():
                out.append((ch, w.x0 + step * (i + 0.5)))
    return out


def classify(layout: Layout) -> FormSpec | None:
    head = "".join(_compact(l.text) for l in layout.lines[:12])
    for form in FORMS:
        if any(sig in head for sig in form.signature):
            return form
    return None


def _is_title(line: Line, n: int) -> bool:
    return line.x0 < 50 and re.match(rf"^{n}\.(?:\s|\D|$)", line.text.strip()) is not None


def _period(text: str) -> tuple[str, str] | None:
    ds = RE_DATE_KO.findall(text)
    if len(ds) >= 2:
        f = lambda t: f"{int(t[0]):04d}-{int(t[1]):02d}-{int(t[2]):02d}"
        return f(ds[0]), f(ds[1])
    return None


# ------------------------------------------------------------------ 머리글
@dataclass
class _Loc:
    col: Col
    xc: float
    x0: float
    x1: float
    y: float


def _locate_header(lines: list[Line], cols: tuple[Col, ...]) -> tuple[dict[str, _Loc], int]:
    """머리글 줄들에서 열 위치를 찾는다. (열 이름 → 위치, 마지막 머리글 줄 index) 반환."""
    found: dict[str, _Loc] = {}
    pairs = sorted(((c, kw) for c in cols for kw in c.kws), key=lambda p: -len(p[1]))
    last = -1
    for i, ln in enumerate(lines):
        if ln.kind != "text":
            break
        c = ln.compact
        if RE_DATA_LIKE.search(c) or is_none_word(ln.text) or is_inquire(ln.text):
            break
        if any(len(_compact(ch.text)) > 30 for ch in ln.chunks()):
            continue  # 제목 이어지는 문장
        chars = _chars(ln)
        s = "".join(ch for ch, _ in chars)
        used = [False] * len(s)
        hit = False
        for col, kw in pairs:
            if col.name in found:
                continue
            start = 0
            while True:
                j = s.find(kw, start)
                if j < 0:
                    break
                if not any(used[j:j + len(kw)]):
                    xs = [x for _, x in chars[j:j + len(kw)]]
                    found[col.name] = _Loc(col, sum(xs) / len(xs), min(xs), max(xs), ln.y)
                    for k in range(j, j + len(kw)):
                        used[k] = True
                    hit = True
                    break
                start = j + 1
        if hit:
            last = i
        if len(found) == len(cols):
            break
    # 마지막 머리글 줄 바로 아래 붙은 조각("및 사업비", "(어음 또는 수표)")도 머리글로 본다
    if last >= 0:
        while last + 1 < len(lines):
            nxt, prev = lines[last + 1], lines[last]
            if nxt.kind == "text" and nxt.page == prev.page and nxt.y - prev.y <= HEADER_ABSORB_GAP \
                    and not RE_DATA_LIKE.search(nxt.compact) and not is_none_word(nxt.text) \
                    and not is_inquire(nxt.text):
                last += 1
            else:
                break
    return found, last


# ------------------------------------------------------------------ 칸 배정
def _intervals(locs: list[_Loc]) -> list[tuple[float, float, _Loc]]:
    locs = sorted(locs, key=lambda l: l.xc)
    out = []
    for k, l in enumerate(locs):
        lo = -math.inf if k == 0 else (locs[k - 1].xc + l.xc) / 2
        hi = math.inf if k == len(locs) - 1 else (l.xc + locs[k + 1].xc) / 2
        out.append((lo, hi, l))
    return out


RE_PAREN_TAIL = re.compile(r"^\(\s*[-\d,.\s]*\)$")


def _assign(chunk: Chunk, ivs) -> _Loc | None:
    if RE_PAREN_TAIL.match(chunk.text):
        # 금액 뒤 "()", "(167,434,051.00)" 조각은 왼쪽 금액 열에 붙인다
        amts = [l for _, _, l in ivs if l.col.kind == "amount" and l.xc <= chunk.xc]
        if amts:
            return max(amts, key=lambda l: l.xc)
    for lo, hi, l in ivs:
        if lo <= chunk.xc < hi:
            return l
    return None


RE_WRAP_END = re.compile(r"[가-힣)\]]$")
RE_WRAP_START = re.compile(r"^[가-힣(\[]")


def _join(parts: list[tuple[float, float, str, float]], kind: str) -> str:
    """같은 셀 조각을 잇는다. 줄이 바뀌며 끊긴 한글 낱말은 공백 없이, 나머지는 공백으로."""
    parts.sort()
    if not parts:
        return ""
    # 줄 단위로 묶기
    lines: list[list[tuple[float, float, str, float]]] = []
    for p in parts:
        if lines and abs(lines[-1][0][0] - p[0]) < 1.0:
            lines[-1].append(p)
        else:
            lines.append([p])
    widths = [ln[-1][3] - ln[0][1] for ln in lines]
    wmax = max(widths) if widths else 0
    out = ""
    for k, ln in enumerate(lines):
        t = " ".join(p[2] for p in ln)
        if not out:
            out = t
        elif kind == "id" and re.match(r"[0-9A-Za-z\-]", t) and re.search(r"[0-9A-Za-z\-]$", out):
            out += t
        elif RE_WRAP_END.search(out) and RE_WRAP_START.match(t) and widths[k - 1] >= 0.85 * wmax:
            out += t
        else:
            out += " " + t
    return out.strip()


# ------------------------------------------------------------------ 표 하나
def _parse_grid(lines: list[Line], table: Table) -> TableResult:
    res = TableResult(table, "missing")
    if lines:
        res.page = lines[0].page
    locs, last = _locate_header(lines, table.cols)
    res.located = {k: v.xc for k, v in locs.items()}
    data = [l for l in lines[last + 1:] if l.kind == "text"]
    if not locs:
        res.notes.append("머리글을 찾지 못함")
    row_label_cut = None
    if table.row_label and locs:
        row_label_cut = min(l.x0 for l in locs.values()) - 25

    err_chunks: list[str] = []

    def payload(ln: Line) -> list[Chunk]:
        chs = ln.chunks()
        if row_label_cut is not None:
            chs = [c for c in chs if c.x1 >= row_label_cut]
        return [c for c in chs if not is_error_text(c.text)]

    for ln in data:
        err_chunks += [c.text for c in ln.chunks() if is_error_text(c.text)]
    if err_chunks:
        res.notes.append(f"회신 양식 오류 문구: {', '.join(err_chunks)}")

    texts = [" ".join(c.text for c in payload(l)) for l in data]
    texts = [t for t in texts if t.strip()]
    if not texts:
        res.status = "missing"
        return res
    joined = " ".join(texts)
    rest = texts
    if rest and all(is_none_word(t) or all(is_none_word(p) for p in re.split(r"\s{2,}|\|", t)) for t in rest):
        res.status, res.raw = "none", joined
        return res
    if any(is_inquire(t) for t in rest) and len(rest) <= 2:
        res.status, res.raw = "inquire", joined
        return res
    if not locs:
        res.status, res.raw = "missing", joined
        return res

    rows = sorted({l.col.row for l in locs.values()})
    ivs_by_row = {r: _intervals([l for l in locs.values() if l.col.row == r]) for r in rows}
    ivs_all = _intervals([l for l in locs.values() if l.col.row == rows[0]])
    ncols = len(ivs_all)
    centers = sorted(l.xc for l in locs.values())

    base_payload = payload

    def payload(ln: Line) -> list[Chunk]:  # noqa: F811 — 열 두 개 이상에 걸친 칸은 낱말 단위로 다시 나눈다
        out: list[Chunk] = []
        for ch in base_payload(ln):
            spans = sum(1 for c in centers if ch.x0 <= c <= ch.x1)
            if spans < 2 or len(ch.words) < 2:
                out.append(ch)
                continue
            for w in ch.words:
                loc = _assign(Chunk([w]), ivs_all)
                if out and out[-1].words[-1] in ch.words and _assign(out[-1], ivs_all) is loc:
                    out[-1].words.append(w)
                else:
                    out.append(Chunk([w]))
        return out

    # 기준 줄 고르기
    hits = []
    for ln in data:
        cols_hit = {id(_assign(c, ivs_all)) for c in payload(ln)}
        hits.append(len(cols_hit))
    need = max(2, math.ceil(ncols * 0.4))
    anchors = []
    for i, ln in enumerate(data):
        if not payload(ln):
            continue
        near = min((abs(o.y - ln.y) for j, o in enumerate(data) if j != i and o.page == ln.page),
                   default=math.inf)
        if hits[i] >= need or near > ISOLATED_GAP:
            anchors.append(i)
    if not anchors:
        anchors = [i for i, ln in enumerate(data) if payload(ln)]

    groups: dict[int, list[int]] = {a: [a] for a in anchors}
    for i, ln in enumerate(data):
        if i in groups or not payload(ln):
            continue
        best = min(anchors, key=lambda a: (abs(data[a].y - ln.y) if data[a].page == ln.page else math.inf,
                                           -a if data[a].y < ln.y else a))
        if data[best].page == ln.page:
            groups[best].append(i)

    # 2행 레코드: 기준 줄을 1행/2행 번갈아 묶는다
    nrow = table.anchor_rows if len(rows) > 1 else 1
    ordered = sorted(anchors, key=lambda a: (data[a].page, data[a].y))
    records_idx = [ordered[k:k + nrow] for k in range(0, len(ordered), nrow)]
    for rec in records_idx:
        parts: dict[str, list[tuple[float, float, str]]] = {}
        for r_off, a in enumerate(rec):
            row = rows[r_off] if r_off < len(rows) else rows[-1]
            ivs = ivs_by_row[row]
            for li in groups[a]:
                ln = data[li]
                for ch in payload(ln):
                    loc = _assign(ch, ivs)
                    if loc is None:
                        continue
                    parts.setdefault(loc.col.name, []).append((ln.page * 10000 + ln.y, ch.x0, ch.text, ch.x1))
        vals = {c.name: _join(parts.get(c.name, []), c.kind) for c in table.cols}
        if any(vals.values()):
            res.records.append(Record(vals, data[rec[0]].page, data[rec[0]].y))
    if len(rows) > 1 and len(ordered) % nrow:
        res.notes.append("2행 레코드 짝이 맞지 않음(마지막 레코드 확인 필요)")
    res.status = "data" if res.records else "missing"
    return res


def _parse_kv(lines: list[Line], table: Table) -> TableResult:
    res = TableResult(table, "kv")
    for ln in lines:
        if table.kv in ln.compact:
            res.page = ln.page
            t = ln.text
            val = t.split(":", 1)[1] if ":" in t else ""
            res.kv_value = re.sub(r"\s+", "", val) if table.kv_kind == "count" else val.strip()
            return res
    res.status = "missing"
    return res


# ------------------------------------------------------------------ 문서
def parse_pdf(path: str | Path) -> ParsedDoc:
    pdf = read_pdf(path)
    if not pdf.has_text:
        return ParsedDoc(Path(path), pdf.page_count, False, None, {}, [])
    layout = build_layout(pdf)
    form = classify(layout)
    doc = ParsedDoc(Path(path), pdf.page_count, True, form, layout.meta, layout.page_numbers)
    if form is None:
        return doc

    lines = layout.lines
    # 섹션 제목 위치
    starts: dict[int, int] = {}
    nexts = [s.no for s in form.sections]
    pos = 0
    for sec in form.sections:
        for i in range(pos, len(lines)):
            if lines[i].kind == "text" and _is_title(lines[i], sec.no):
                starts[sec.no] = i
                pos = i + 1
                break
    bounds = sorted(starts.values())

    for sec in form.sections:
        if sec.no not in starts:
            doc.sections.append(SectionResult(sec, False))
            continue
        i0 = starts[sec.no]
        later = [b for b in bounds if b > i0]
        i1 = later[0] if later else len(lines)
        region = lines[i0 + 1:i1]
        title = lines[i0].text
        # 제목이 다음 줄로 이어지는 경우
        k = 0
        while k < len(region) and region[k].kind == "text" and region[k].x0 < 50 \
                and len(region[k].chunks()) == 1 and len(region[k].compact) > 20:
            title += " " + region[k].text
            k += 1
        region = region[k:]
        sr = SectionResult(sec, True, title=title, page=lines[i0].page, period=_period(title))
        conf = [l for l in region if l.kind == "confirmer"]
        if conf:
            sr.confirmer = conf[0].extra.get("name", "")
            cut = region.index(conf[0])
            region = region[:cut]

        # 섹션 안 표 구간
        t_starts: list[int] = []
        p = 0
        for t_i, tab in enumerate(sec.tables):
            if t_i == 0 and tab.start is None and tab.kv is None:
                t_starts.append(0)
                continue
            idx = None
            for j in range(p, len(region)):
                c = region[j].compact
                if (tab.kv and tab.kv in c) or (tab.start and re.search(tab.start, c)):
                    idx = j
                    break
            t_starts.append(idx if idx is not None else -1)
            if idx is not None:
                p = idx + (0 if tab.kv else 1)
        for t_i, tab in enumerate(sec.tables):
            s0 = t_starts[t_i]
            if s0 < 0:
                sr.tables.append(TableResult(tab, "missing", notes=["표 구간을 찾지 못함"]))
                continue
            nxt = [s for s in t_starts[t_i + 1:] if s > s0]
            seg = region[s0:(nxt[0] if nxt else len(region))]
            if tab.kv:
                sr.tables.append(_parse_kv(seg[:1], tab))
            else:
                if t_i > 0 and sec.tables[t_i - 1].kv and s0 == t_starts[t_i - 1]:
                    seg = seg[1:]
                sr.tables.append(_parse_grid(seg, tab))
        doc.sections.append(sr)
    return doc
