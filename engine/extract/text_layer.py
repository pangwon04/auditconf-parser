"""PDF 텍스트 레이어에서 단어와 좌표를 읽는다 (A-03).

전자조회 회신본은 텍스트 레이어가 있으므로 OCR 없이 단어 단위 좌표를 얻는다.
워터마크("열람용")처럼 글자 높이가 큰 단어는 버린다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

WATERMARK_MIN_HEIGHT = 20.0  # 본문 글자 높이는 9~10pt, "열람용" 워터마크는 90pt


@dataclass(frozen=True)
class Word:
    page: int          # 0부터
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class PdfText:
    path: Path
    page_count: int
    page_height: float
    words: list[Word]

    @property
    def has_text(self) -> bool:
        return len(self.words) > 20


def read_pdf(path: str | Path) -> PdfText:
    path = Path(path)
    doc = pymupdf.open(path)
    words: list[Word] = []
    height = 0.0
    for pno, page in enumerate(doc):
        height = max(height, page.rect.height)
        # 회전된 쪽(DB손보 등 /Rotate 90)은 좌표를 보이는 방향으로 돌려 둔다.
        rot = page.rotation_matrix if page.rotation else None
        for x0, y0, x1, y1, text, *_ in page.get_text("words"):
            if rot is not None:
                r = pymupdf.Rect(x0, y0, x1, y1) * rot
                x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
            if (y1 - y0) >= WATERMARK_MIN_HEIGHT:
                continue
            for piece in _split_nbsp(text, x0, x1):
                t, px0, px1 = piece
                words.append(Word(pno, px0, y0, px1, y1, t))
    count = doc.page_count
    doc.close()
    return PdfText(path=path, page_count=count, page_height=height, words=words)


def _split_nbsp(text: str, x0: float, x1: float):
    """NBSP·전각 공백으로 붙은 단어를 나누고, x 좌표는 글자 수 비례로 나눈다."""
    text = text.replace("　", " ").replace("\xa0", " ")
    if not text.strip():
        return []
    n = len(text)
    w = (x1 - x0) / n if n else 0
    out = []
    i = 0
    while i < n:
        if text[i] == " ":
            i += 1
            continue
        j = i
        while j < n and text[j] != " ":
            j += 1
        out.append((text[i:j], x0 + w * i, x0 + w * j))
        i = j
    return out
