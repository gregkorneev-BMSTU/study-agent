"""Small Markdown section reader; preserves source text rather than rendering it."""

from __future__ import annotations

import re

from study_agent.models import ExtractedBlock

MARKDOWN_VERSION = 2
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?)|[ \t]*)$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _fence_end(line: str, fence: str) -> bool:
    return bool(
        re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line)
    )


def markdown_units(text: str) -> list[str]:
    """Keep fenced code and pipe-table rows together; separate ordinary paragraphs."""
    units: list[str] = []
    pending: list[str] = []
    fence: str | None = None
    math_end: str | None = None
    for line in text.splitlines(keepends=True):
        match = _FENCE.match(line.rstrip("\r\n"))
        if math_end is not None:
            pending.append(line)
            if math_end in line:
                math_end = None
                units.append("".join(pending))
                pending = []
        elif fence is not None:
            pending.append(line)
            if _fence_end(line.rstrip("\r\n"), fence):
                units.append("".join(pending))
                pending = []
                fence = None
        elif match:
            if pending:
                units.append("".join(pending))
            pending = [line]
            fence = match[1]
        elif line.lstrip().startswith(("$$", r"\[")):
            if pending:
                units.append("".join(pending))
            pending = [line]
            closing = "$$" if line.lstrip().startswith("$$") else r"\]"
            opening = "$$" if closing == "$$" else r"\["
            tail = line.lstrip()[len(opening) :]
            if closing in tail:
                units.append("".join(pending))
                pending = []
            else:
                math_end = closing
        elif not line.strip():
            if pending:
                units.append("".join(pending))
                pending = []
            if units:
                units[-1] += line
        else:
            pending.append(line)
    if pending:
        units.append("".join(pending))
    return units


def extract_markdown(text: str) -> list[ExtractedBlock]:
    """Recognize ATX/Setext headings outside fenced/indented code, retaining Markdown."""
    lines = text.splitlines(keepends=True)
    blocks: list[ExtractedBlock] = []
    headings: list[tuple[int, str]] = []
    pending: list[str] = []
    start = 1
    fence: str | None = None

    def flush() -> None:
        value = "".join(pending)
        if value.strip():
            blocks.append(
                ExtractedBlock(
                    value,
                    "markdown",
                    "digital",
                    heading=" › ".join(title for _, title in headings) or None,
                    marker=f"line:{start}",
                )
            )
        pending.clear()

    index = 0
    while index < len(lines):
        line = lines[index].rstrip("\r\n")
        match = _FENCE.match(line)
        if fence is not None:
            pending.append(lines[index])
            if _fence_end(line, fence):
                fence = None
            index += 1
            continue
        if match:
            fence = match[1]
            pending.append(lines[index])
            index += 1
            continue
        heading = _ATX.match(line)
        setext = (
            _SETEXT.match(lines[index + 1].rstrip("\r\n"))
            if index + 1 < len(lines) and line.strip() and not line.startswith(("    ", "\t"))
            else None
        )
        if heading or setext:
            flush()
            if heading:
                level = len(heading[1])
                title = re.sub(r"[ \t]+#+[ \t]*$", "", heading[2] or "").strip()
            else:
                assert setext is not None
                level = 1 if setext[1][0] == "=" else 2
                title = line.strip()
            headings[:] = [(depth, name) for depth, name in headings if depth < level]
            if title:
                headings.append((level, title))
            start = index + 1
            pending.append(lines[index])
            if setext and not heading:
                index += 1
                pending.append(lines[index])
        else:
            pending.append(lines[index])
        index += 1
    flush()
    return blocks
