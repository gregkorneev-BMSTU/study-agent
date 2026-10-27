"""Bounded local answers with citations verified against backend retrieval metadata."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from study_agent.math_content import formula_warnings, mask_markdown_code
from study_agent.search import SearchHit

_ERROR_MESSAGES = {
    "missing_citations": (
        "Модель не указала ссылки [1], [2] на переданные источники.",
        "The model did not cite the supplied sources using [1], [2].",
    ),
    "unknown_source": (
        "Модель сослалась на источник, которого нет в переданном контексте.",
        "The model cited a source that was not supplied in its context.",
    ),
    "uncited_paragraph": (
        "В ответе есть содержательный абзац без ссылки на источник.",
        "A substantive paragraph in the answer has no source citation.",
    ),
    "generated_links": (
        "Модель добавила внешнюю или Markdown-ссылку вместо номера источника.",
        "Model-generated links are not allowed; open indexed sources instead.",
    ),
    "source_quality": (
        "В найденных формулах есть признаки повреждения. Сверьте их с оригиналом.",
        "The retrieved formulas may be damaged. Check the original document.",
    ),
}


class CitationError(RuntimeError):
    """Safe structured diagnostics: never retain model output or source text."""

    def __init__(
        self,
        reason: str,
        *,
        source_count: int = 0,
        invalid_sources: list[int] | None = None,
        paragraph_index: int | None = None,
        warning_codes: list[str] | None = None,
    ) -> None:
        self.reason = reason
        self.details: dict[str, object] = {"source_count": source_count}
        if invalid_sources is not None:
            self.details["invalid_sources"] = invalid_sources
        if paragraph_index is not None:
            self.details["paragraph_index"] = paragraph_index
        if warning_codes is not None:
            self.details["warning_codes"] = warning_codes
        super().__init__(self.message("en"))

    def message(self, language: str | None) -> str:
        return _ERROR_MESSAGES[self.reason][1 if language == "en" else 0]

    def action(self, language: str | None) -> str:
        if self.reason == "source_quality":
            return (
                "Check the original and correct the local extraction before reindexing."
                if language == "en"
                else "Сверьте формулы с оригиналом, исправьте локальную копию "
                "и проверьте изменения."
            )
        return (
            "Retrieved excerpts remain available. Retry with another installed local model."
            if language == "en"
            else "Найденные фрагменты доступны. Повторите ответ с другой локальной моделью."
        )


_MATH_BLOCK = re.compile(
    r"\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)"
    r"|(?<!\\)\$(?!\$)[^\n$]+(?<!\\)\$(?!\$)"
)
_CITATION = re.compile(r"(?<!\\)\[(\d+(?:\s*[,;]\s*\d+)*)\]")


def _citation_matches(content: str) -> list[re.Match[str]]:
    # Numeric brackets in math/code are data rather than source references.
    masked = _MATH_BLOCK.sub(lambda match: " " * len(match[0]), mask_markdown_code(content))
    return list(_CITATION.finditer(masked))


def _numbers(match: re.Match[str]) -> list[int]:
    return [int(value.strip()) for value in re.split(r"[,;]", match[1])]


def _uncited_paragraph(content: str, matches: list[re.Match[str]]) -> int | None:
    # Global masking matters for blank lines inside fenced code/display equations.
    visible = _MATH_BLOCK.sub(lambda match: " " * len(match[0]), mask_markdown_code(content))
    paragraphs = []
    offset = 0
    for paragraph in re.split(r"\n\s*\n", content):
        start = content.find(paragraph, offset)
        end = start + len(paragraph)
        offset = end
        if not paragraph.strip():
            continue
        cited = any(start <= match.start() < end for match in matches)
        structured_only = not visible[start:end].strip(" \n\t:;.,*_")
        paragraphs.append((paragraph, cited, structured_only))
    for index, (paragraph, cited, structured_only) in enumerate(paragraphs):
        if len(paragraph.strip()) <= 30 or cited:
            continue
        if structured_only:
            adjacent_citation = False
            for direction in (-1, 1):
                neighbor = index + direction
                while 0 <= neighbor < len(paragraphs):
                    _, neighbor_cited, neighbor_structured = paragraphs[neighbor]
                    if neighbor_cited:
                        adjacent_citation = True
                        break
                    if not neighbor_structured:
                        break
                    neighbor += direction
            if adjacent_citation:
                continue
        return index + 1
    return None


@dataclass(frozen=True)
class AnswerResult:
    answer: str
    sources: list[SearchHit]
    grounded: bool


def refusal(language: str | None) -> str:
    if language == "en":
        return (
            "The connected study materials do not contain enough information "
            "to answer this question."
        )
    return "В подключённых учебных материалах недостаточно информации для ответа на этот вопрос."


def build_context(
    hits: list[SearchHit],
    *,
    max_bytes: int = 5000,
    max_sources: int = 5,
) -> tuple[str, list[SearchHit]]:
    """Bound all source labels and text, preserving the exact snippets shown by the UI."""
    pieces: list[str] = []
    sources: list[SearchHit] = []
    remaining = max_bytes
    for hit in hits:
        if hit.quality_warnings or formula_warnings(hit.excerpt):
            continue
        if len(sources) >= max_sources:
            break
        location = f"; page {hit.page_number}" if hit.page_number else ""
        if hit.heading:
            location += f"; section {hit.heading[:160]}"
        label = f"[{len(sources) + 1}] {hit.title[:120]} ({hit.document_id[:180]}{location})\n"
        room = remaining - len(label.encode("utf-8")) - 2
        if room < 80:
            break
        text = hit.excerpt.encode("utf-8")[:room].decode("utf-8", errors="ignore").strip()
        # Never send half a display formula because the context budget ended inside it.
        for match in _MATH_BLOCK.finditer(hit.excerpt):
            if (
                len(hit.excerpt[: match.start()].encode("utf-8"))
                < room
                < len(hit.excerpt[: match.end()].encode("utf-8"))
            ):
                text = hit.excerpt[: match.start()].strip()
                break
        if not text:
            continue
        meaningful = (
            re.sub(r"(?m)^ {0,3}#{1,6}(?:\s.*)?$", "", text).strip()
            if hit.document_id.lower().endswith(".md")
            else text
        )
        if not meaningful:
            continue
        part = label + text
        pieces.append(part)
        sources.append(replace(hit, excerpt=text))
        remaining -= len(part.encode("utf-8")) + 2
    return "\n\n".join(pieces), sources


def generate_answer(
    model: str,
    question: str,
    hits: list[SearchHit],
    *,
    language: str | None = None,
    generator: Callable[..., str],
    citation_repair: Callable[..., str] | None = None,
) -> AnswerResult:
    if len(question.encode("utf-8")) > 1024:
        raise ValueError("Question is too long; limit is 1024 UTF-8 bytes")
    context, sources = build_context(hits)
    if not sources:
        warnings = sorted(
            {
                code
                for hit in hits
                for code in [*hit.quality_warnings, *formula_warnings(hit.excerpt)]
            }
        )
        if warnings:
            raise CitationError("source_quality", source_count=0, warning_codes=warnings)
        return AnswerResult(refusal(language), [], False)
    content = generator(model, question, context, language=language).strip()
    try:
        return _validated_answer(content, sources, language)
    except CitationError as error:
        if citation_repair is None:
            raise
        # One bounded fresh attempt using the same sources; never fabricate citations.
        content = citation_repair(model, question, context, language, error).strip()
        return _validated_answer(content, sources, language)


def _validated_answer(
    content: str, sources: list[SearchHit], language: str | None
) -> AnswerResult:
    if content == "INSUFFICIENT_CONTEXT":
        return AnswerResult(refusal(language), [], False)
    if re.search(r"\b[a-z][a-z0-9+.-]*://|mailto:|\[[^\]]+\]\([^)]*\)", content, re.I):
        raise CitationError("generated_links", source_count=len(sources))
    matches = _citation_matches(content)
    numbers = [number for match in matches for number in _numbers(match)]
    if not numbers:
        raise CitationError("missing_citations", source_count=len(sources))
    invalid = sorted({number for number in numbers if not 1 <= number <= len(sources)})
    if invalid:
        raise CitationError("unknown_source", source_count=len(sources), invalid_sources=invalid)
    paragraph_index = _uncited_paragraph(content, matches)
    if paragraph_index is not None:
        raise CitationError(
            "uncited_paragraph", source_count=len(sources), paragraph_index=paragraph_index
        )
    cited = list(dict.fromkeys(numbers))
    mapping = {number: index for index, number in enumerate(cited, 1)}
    # Replace only actual citation spans, preserving numeric brackets inside math/code.
    for match in reversed(matches):
        replacement = ", ".join(f"[{mapping[number]}]" for number in _numbers(match))
        content = content[: match.start()] + replacement + content[match.end() :]
    return AnswerResult(content, [sources[number - 1] for number in cited], True)
