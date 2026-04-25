#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
IMAGE_RE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")
CODE_FENCE_RE = re.compile(r"^```")


def _make_styles():
    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}

    styles["body"] = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        spaceAfter=4,
    )
    styles["h1"] = ParagraphStyle(
        "H1",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=24,
        spaceBefore=8,
        spaceAfter=8,
    )
    styles["h2"] = ParagraphStyle(
        "H2",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=20,
        spaceBefore=8,
        spaceAfter=6,
    )
    styles["h3"] = ParagraphStyle(
        "H3",
        parent=base["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=17,
        spaceBefore=7,
        spaceAfter=5,
    )
    styles["h4"] = ParagraphStyle(
        "H4",
        parent=base["Heading4"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        spaceBefore=6,
        spaceAfter=4,
    )
    styles["code"] = ParagraphStyle(
        "Code",
        parent=base["Code"],
        fontName="Courier",
        fontSize=9,
        leading=12,
        backColor=colors.whitesmoke,
        borderColor=colors.lightgrey,
        borderWidth=0.5,
        borderPadding=6,
        borderRadius=2,
    )
    return styles


def _escape_inline_markdown(text: str) -> str:
    escaped = html.escape(text)

    # Bold: **text**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)

    # Inline code: `code`
    escaped = re.sub(
        r"`([^`]+)`",
        lambda m: f"<font face='Courier'>{html.escape(m.group(1))}</font>",
        escaped,
    )
    return escaped


def _add_image(story, styles, md_dir: Path, image_ref: str, max_width: float):
    image_path = Path(image_ref)
    if not image_path.is_absolute():
        image_path = (md_dir / image_path).resolve()

    if not image_path.exists():
        story.append(
            Paragraph(
                _escape_inline_markdown(f"[Missing image: {image_ref}]"),
                styles["body"],
            )
        )
        story.append(Spacer(1, 4))
        return

    img = Image(str(image_path))
    img.hAlign = "LEFT"

    if img.drawWidth > max_width:
        ratio = max_width / float(img.drawWidth)
        img.drawWidth = max_width
        img.drawHeight = float(img.drawHeight) * ratio

    story.append(img)
    story.append(Spacer(1, 7))


def markdown_to_story(md_text: str, md_path: Path, page_width: float):
    styles = _make_styles()
    story = []

    lines = md_text.splitlines()
    md_dir = md_path.parent
    max_image_width = page_width - (20 * mm)

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()

        if not line.strip():
            story.append(Spacer(1, 6))
            i += 1
            continue

        if CODE_FENCE_RE.match(line.strip()):
            i += 1
            code_lines = []
            while i < len(lines) and not CODE_FENCE_RE.match(lines[i].strip()):
                code_lines.append(lines[i].rstrip("\n"))
                i += 1
            if i < len(lines):
                i += 1
            story.append(Preformatted("\n".join(code_lines), styles["code"]))
            story.append(Spacer(1, 6))
            continue

        image_match = IMAGE_RE.match(line.strip())
        if image_match:
            _add_image(story, styles, md_dir, image_match.group(1).strip(), max_image_width)
            i += 1
            continue

        heading_match = HEADING_RE.match(line)
        if heading_match:
            level = min(len(heading_match.group(1)), 4)
            heading_text = _escape_inline_markdown(heading_match.group(2).strip())
            story.append(Paragraph(heading_text, styles[f"h{level}"]))
            i += 1
            continue

        text = _escape_inline_markdown(line)
        story.append(Paragraph(text, styles["body"]))
        i += 1

    return story


def build_pdf(input_path: Path, output_path: Path) -> None:
    input_text = input_path.read_text(encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=input_path.stem,
    )

    story = markdown_to_story(input_text, input_path, page_width=A4[0] - (32 * mm))
    doc.build(story)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Markdown file to PDF.")
    parser.add_argument("--input", required=True, help="Path to markdown file.")
    parser.add_argument("--output", required=True, help="Path to output PDF.")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input markdown file not found: {input_path}")

    build_pdf(input_path, output_path)
    print(f"Wrote PDF: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
