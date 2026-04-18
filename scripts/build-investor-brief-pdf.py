from __future__ import annotations

import argparse
import textwrap
from pathlib import Path


def _normalize_markdown_line(line: str) -> str:
    text = line.rstrip()
    if not text:
        return ""
    if text.startswith("#"):
        text = text.lstrip("#").strip().upper()
    if text.startswith("- "):
        text = f"* {text[2:].strip()}"
    return text


def _wrap_lines(markdown_text: str, width: int = 96) -> list[str]:
    wrapped: list[str] = []
    for raw in markdown_text.splitlines():
        normalized = _normalize_markdown_line(raw)
        if not normalized:
            wrapped.append("")
            continue
        segments = textwrap.wrap(
            normalized,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        if not segments:
            wrapped.append("")
        else:
            wrapped.extend(segments)
    return wrapped


def _paginate(lines: list[str], lines_per_page: int = 50) -> list[list[str]]:
    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        current.append(line)
        if len(current) >= lines_per_page:
            pages.append(current)
            current = []
    if current:
        pages.append(current)
    if not pages:
        pages = [[]]
    return pages


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf_bytes(pages: list[list[str]]) -> bytes:
    objects: list[bytes | None] = [None, None, None]  # 1=catalog, 2=pages, 3=font
    objects[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    font_obj_id = 3

    page_obj_ids: list[int] = []

    for page_lines in pages:
        content_parts = [
            "BT",
            "/F1 11 Tf",
            "14 TL",
            "50 790 Td",
        ]
        first = True
        for line in page_lines:
            safe = _escape_pdf_text(line)
            if first:
                content_parts.append(f"({safe}) Tj")
                first = False
            else:
                content_parts.append("T*")
                content_parts.append(f"({safe}) Tj")
        content_parts.append("ET")
        content_text = "\n".join(content_parts) + "\n"
        content_bytes = content_text.encode("latin-1", errors="replace")
        content_obj = (
            f"<< /Length {len(content_bytes)} >>\nstream\n".encode("ascii")
            + content_bytes
            + b"endstream"
        )
        objects.append(content_obj)
        content_obj_id = len(objects)

        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> "
            f"/Contents {content_obj_id} 0 R >>"
        ).encode("ascii")
        objects.append(page_obj)
        page_obj_ids.append(len(objects))

    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_ids)} >>".encode("ascii")
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    body = bytearray(header)
    offsets = [0]

    for obj_id, obj in enumerate(objects, start=1):
        if obj is None:
            raise RuntimeError(f"PDF object {obj_id} is empty.")
        offsets.append(len(body))
        body.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        body.extend(obj)
        body.extend(b"\nendobj\n")

    xref_pos = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    body.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        body.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    body.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a plain-text PDF from a markdown investor brief.")
    parser.add_argument("--input", required=True, help="Path to source markdown file.")
    parser.add_argument("--output", required=True, help="Path to output PDF file.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    markdown_text = input_path.read_text(encoding="utf-8")
    lines = _wrap_lines(markdown_text)
    pages = _paginate(lines)
    pdf_bytes = _build_pdf_bytes(pages)
    output_path.write_bytes(pdf_bytes)

    print(f"Wrote PDF: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
