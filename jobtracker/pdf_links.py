from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .url_tools import clean_url


@dataclass(frozen=True)
class PdfLink:
    url: str
    raw_url: str
    page_number: int
    annotation_index: int
    rect: tuple[float, ...]


def _resolve(value: Any) -> Any:
    return value.get_object() if hasattr(value, "get_object") else value


def extract_pdf_links(path: str | Path, min_x: float | None = 400.0) -> list[PdfLink]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf is required to read PDF links. Install dependencies with `python3 -m pip install -r requirements.txt`."
        ) from exc

    reader = PdfReader(str(path))
    links: list[PdfLink] = []
    for page_index, page in enumerate(reader.pages, start=1):
        annotations = _resolve(page.get("/Annots")) or []
        for annotation_index, annotation_ref in enumerate(annotations, start=1):
            annotation = _resolve(annotation_ref)
            action = _resolve(annotation.get("/A")) if annotation.get("/A") else None
            raw_url = _resolve(action.get("/URI")) if action and action.get("/URI") else None
            if not raw_url:
                continue
            rect = tuple(float(part) for part in (annotation.get("/Rect") or ()))
            if min_x is not None and rect and rect[0] < min_x:
                continue
            cleaned = clean_url(str(raw_url))
            if not cleaned:
                continue
            links.append(
                PdfLink(
                    url=cleaned,
                    raw_url=str(raw_url),
                    page_number=page_index,
                    annotation_index=annotation_index,
                    rect=rect,
                )
            )
    return links

