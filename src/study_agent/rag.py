"""Bounded local answers with citations verified against backend retrieval metadata."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from study_agent.search import SearchHit


class CitationError(RuntimeError):
    """A model response references sources outside the supplied context."""


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
) -> AnswerResult:
    if len(question.encode("utf-8")) > 1024:
        raise ValueError("Question is too long; limit is 1024 UTF-8 bytes")
    context, sources = build_context(hits)
    if not sources:
        return AnswerResult(refusal(language), [], False)
    content = generator(model, question, context, language=language).strip()
    if content == "INSUFFICIENT_CONTEXT":
        return AnswerResult(refusal(language), [], False)
    if re.search(r"\b[a-z][a-z0-9+.-]*://|mailto:|\[[^\]]+\]\([^)]*\)", content, re.I):
        raise CitationError("Model-generated links are not allowed; open indexed sources instead")
    numbers = [int(value) for value in re.findall(r"\[(\d+)\]", content)]
    if not numbers or any(number < 1 or number > len(sources) for number in numbers):
        raise CitationError("The local model returned missing or invalid source citations")
    # Every substantive paragraph must carry a supplied source reference.
    if any(
        len(paragraph.strip()) > 30 and not re.search(r"\[\d+\]", paragraph)
        for paragraph in re.split(r"\n\s*\n", content)
        if paragraph.strip()
    ):
        raise CitationError("The local model returned an uncited paragraph")
    # Expose only cited sources and renumber them together with the displayed text.
    cited = list(dict.fromkeys(numbers))
    mapping = {number: index for index, number in enumerate(cited, 1)}
    content = re.sub(r"\[(\d+)\]", lambda match: f"[{mapping[int(match[1])]}]", content)
    return AnswerResult(content, [sources[number - 1] for number in cited], True)
