"""단어를 줄 단위로 묶고, 머리말·꼬리말·고정 문구를 걷어낸 본문 줄 흐름을 만든다.

- 페이지를 넘어가는 섹션을 이어 붙일 수 있도록 모든 페이지의 줄을 (page, y) 순서로 이어 둔다.
- 머리말(감사인·조회대상·기준일), 쪽번호, 등본 인정 문구, 발급기관명 꼬리말, 발급 정보 블록은
  본문에서 빼고 메타 정보로 보관한다.
- "확인자 소속 및 성명" 줄은 섹션 끝 표시로 남긴다(kind="confirmer").
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .text_layer import PdfText, Word

LINE_TOL = 2.5      # 같은 줄로 볼 y 차이(pt)
CHUNK_GAP = 4.5     # 같은 칸으로 붙일 단어 간격(pt)

RE_PAGE_NO = re.compile(r"^(\d+)\s*/\s*(\d+)$")
RE_BIZ_NO = re.compile(r"\d{3}-\d{2}-\d{5}")
RE_YMD_KO = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")


@dataclass
class Chunk:
    """같은 줄에서 간격 없이 붙어 있는 단어 묶음(=하나의 칸 후보)."""
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def x0(self) -> float:
        return self.words[0].x0

    @property
    def x1(self) -> float:
        return self.words[-1].x1

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y(self) -> float:
        return min(w.y0 for w in self.words)


@dataclass
class Line:
    page: int
    y: float
    words: list[Word]
    kind: str = "text"            # text | confirmer
    extra: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def compact(self) -> str:
        return re.sub(r"\s+", "", self.text)

    @property
    def x0(self) -> float:
        return self.words[0].x0

    @property
    def key(self) -> tuple[int, float]:
        return (self.page, self.y)

    def chunks(self, gap: float = CHUNK_GAP) -> list[Chunk]:
        out: list[Chunk] = []
        for w in self.words:
            if out and w.x0 - out[-1].x1 <= gap:
                out[-1].words.append(w)
            else:
                out.append(Chunk([w]))
        return out


@dataclass
class Layout:
    lines: list[Line]
    meta: dict
    page_numbers: list[tuple[int, int, int]]   # (pdf page, printed n, printed m)


def group_lines(words: list[Word]) -> list[Line]:
    lines: list[Line] = []
    for page in sorted({w.page for w in words}):
        ws = sorted((w for w in words if w.page == page), key=lambda w: (w.y0, w.x0))
        cur: list[Word] = []
        cy = None
        for w in ws:
            if cy is None or abs(w.y0 - cy) > LINE_TOL:
                if cur:
                    lines.append(Line(page, cy, sorted(cur, key=lambda w: w.x0)))
                cur, cy = [w], w.y0
            else:
                cur.append(w)
        if cur:
            lines.append(Line(page, cy, sorted(cur, key=lambda w: w.x0)))
    return lines


def _parse_header(line: Line, meta: dict) -> bool:
    """1쪽 머리말 두 줄을 메타로 읽는다. 머리말이면 True."""
    t = line.text
    if "담당공인회계사" in t and "귀중" in t:
        words = line.words
        idx = next(i for i, w in enumerate(words) if "담당공인회계사" in w.text)
        meta["auditor_firm"] = " ".join(w.text for w in words[:idx]).strip()
        rest = " ".join(w.text for w in words[idx + 1:])
        rest = rest.replace(":", " ").replace("귀중", " ")
        meta["auditor_cpa"] = re.sub(r"\s+", " ", rest).strip()
        return True
    if "조회대상" in t and "사업자등록번호" in t:
        m = re.search(r"회사\s*:\s*(.*?)\s*사업자등록번호", t)
        if m:
            meta["company"] = re.sub(r"\s+", " ", m.group(1)).strip()
        m = RE_BIZ_NO.search(t)
        if m:
            meta["biz_no"] = m.group(0)
        m = RE_YMD_KO.search(t.split("조회기준일")[-1])
        if m:
            meta["as_of"] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return True
    return False


def build_layout(pdf: PdfText) -> Layout:
    raw = group_lines(pdf.words)
    meta: dict = {"kftc_issued": False}
    page_numbers: list[tuple[int, int, int]] = []
    footer_texts: Counter[str] = Counter()
    out: list[Line] = []
    stop_after: tuple[int, float] | None = None

    # 발급 정보 블록(마지막 쪽 "담당자 :", "문의전화") 위치를 먼저 찾는다.
    for ln in raw:
        if "담당자" in ln.text and ":" in ln.text or "문의전화" in ln.text:
            if stop_after is None or ln.key < stop_after:
                stop_after = ln.key
    if stop_after is not None:
        # 발급일은 블록 바로 위 줄들에 있다(예: "2026년 01월 13일 교보증권 ...").
        block = [l for l in raw if l.page == stop_after[0] and stop_after[1] - 30 <= l.y <= stop_after[1] + 30]
        for l in block:
            m = RE_YMD_KO.search(l.text)
            if m:
                meta["issued_on"] = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                stop_after = min(stop_after, l.key)
                break

    bonmun_y: dict[int, float] = {}
    for ln in raw:
        if ln.compact.startswith("본조회서는원본의전부를"):
            bonmun_y[ln.page] = ln.y

    for ln in raw:
        c = ln.compact
        m = RE_PAGE_NO.match(ln.text.strip())
        if m and len(ln.words) <= 3:
            page_numbers.append((ln.page, int(m.group(1)), int(m.group(2))))
            continue
        if stop_after is not None and ln.key >= stop_after:
            if "금융결제원을통하여제공" in c:
                meta["kftc_issued"] = True
            continue
        if c.startswith("본조회서는원본의전부를"):
            continue
        if "금융결제원을통하여제공" in c:
            meta["kftc_issued"] = True
            continue
        if ln.page == 0 and _parse_header(ln, meta):
            continue
        # 발급기관명 꼬리말: 오른쪽 끝, 등본 문구 위 80pt 이내 또는 페이지 하단
        by = bonmun_y.get(ln.page)
        near_footer = (by is not None and by - 90 <= ln.y < by) or ln.y > pdf.page_height * 0.78
        if ln.x0 > 600 and near_footer and len(ln.words) <= 3 and "확인자" not in c:
            footer_texts[c] += 1
            continue
        if c.startswith("확인자소속및성명"):
            after = ln.text.split(":", 1)[1].strip() if ":" in ln.text else ""
            out.append(Line(ln.page, ln.y, ln.words, kind="confirmer", extra={"name": after}))
            continue
        out.append(ln)

    if footer_texts:
        meta["institution"] = footer_texts.most_common(1)[0][0]
    _attach_detached_confirmer_names(out)
    return Layout(lines=out, meta=meta, page_numbers=page_numbers)


def _attach_detached_confirmer_names(lines: list[Line]) -> None:
    """확인자 이름이 같은 줄이 아닌 바로 위·아래 줄 오른쪽에 찍힌 양식을 처리한다."""
    for i, ln in enumerate(lines):
        if ln.kind != "confirmer" or ln.extra.get("name"):
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(lines):
                cand = lines[j]
                if cand.kind == "text" and cand.page == ln.page and abs(cand.y - ln.y) <= 14 \
                        and cand.x0 > 600 and len(cand.words) <= 3:
                    ln.extra["name"] = cand.text
                    cand.kind = "consumed"
                    break
    lines[:] = [l for l in lines if l.kind != "consumed"]
