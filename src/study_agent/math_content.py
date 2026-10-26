"""Conservative extractive math focusing, not a mathematical correctness checker.

All excerpts are literal source substrings. The lexical intent baseline distinguishes
common functions and arguments; it neither solves expressions nor repairs OCR.
"""

from __future__ import annotations

import re

_DISPLAY = re.compile(r"\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]")
_MATH_QUERY = re.compile(
    r"интеграл|производн|корн|корен|синус|косинус|integral|sqrt|\\int|\\sin|\\cos|√",
    re.IGNORECASE,
)


def mask_markdown_code(text: str) -> str:
    """Mask Markdown code without shifting source offsets for literal extraction."""
    characters = list(text)
    fence: str | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        match = re.match(r" {0,3}(`{3,}|~{3,})", line)
        masked = fence is not None or match is not None or line.startswith(("    ", "\t"))
        if fence is None and match:
            fence = match[1]
        elif fence is not None and re.fullmatch(
            r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*", line
        ):
            fence = None
        if masked:
            characters[offset : offset + len(line)] = [
                "\n" if char == "\n" else " " for char in line
            ]
        offset += len(line)
    visible = "".join(characters)
    for match in re.finditer(r"(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)", visible):
        characters[match.start() : match.end()] = [" "] * len(match[0])
    return "".join(characters)


def is_math_query(query: str) -> bool:
    if not _MATH_QUERY.search(query):
        return False
    functions, argument, _, _ = _intent(query)
    # A request for a lecture/table as a whole must keep its surrounding text.
    return bool(functions - {"integral"} or argument or r"\int" in query)


def formula_warnings(text: str) -> list[str]:
    """Flag narrow syntactic OCR suspicions, without certifying formula validity."""
    text = mask_markdown_code(text)
    if not re.search(r"\$|\\(?:int|sqrt|frac|\[)", text):
        return []
    suspect = bool(re.search(r"\\sqrt\s*\{\s*d\s*[a-z]\s*\}", text))
    balance = 0
    for match in re.finditer(r"(?<!\\)[{}]", text):
        balance += 1 if match[0] == "{" else -1
        if balance < 0:
            suspect = True
    suspect |= balance != 0
    suspect |= text.count("$$") % 2 != 0
    suspect |= text.count(r"\[") != text.count(r"\]")
    # Narrow OCR heuristic: applying the ordinary power rule to sqrt(x^n)
    # verbatim loses the square root. This is not general algebra validation.
    compact = re.sub(r"\s+", "", text)
    for match in re.finditer(r"\\int\\sqrt\{([a-z])\^([a-z])\}", compact):
        variable, power = match.groups()
        wrong_rule = rf"\frac{{{variable}^{{{power}+1}}}}{{{power}+1}}"
        same_formula = compact[match.end() :].split("$$", 1)[0].split(r"\]", 1)[0]
        if wrong_rule in same_formula:
            suspect = True
    return ["formula_suspect"] if suspect else []


def _intent(query: str) -> tuple[set[str], str | None, bool | None, bool | None]:
    lower = query.casefold()
    functions: set[str] = set()
    for name, pattern in (
        ("integral", r"интеграл|integral|\\int"),
        ("sqrt", r"корн|корен|sqrt|√"),
        ("sin", r"(?<!ко)синус|(?<![a-z])sin"),
        ("cos", r"косинус|(?<![a-z])cos"),
    ):
        if re.search(pattern, lower):
            functions.add(name)
    argument = next(iter(re.findall(r"(?<![a-zа-я])([a-z])(?![a-zа-я])", lower)), None)
    reciprocal = bool(re.search(r"1\s*/|единиц\w*\s+(?:на|дел)|обратн|dx\s*/|\\frac\{dx\}", lower))
    power = bool(re.search(r"\^|степен|квадрат|куб", lower))
    return functions, argument, reciprocal if "sqrt" in functions else None, power


def math_relevance(text: str, query: str) -> int:
    """Rank literal math candidates by explicit function/argument intent (baseline)."""
    if not is_math_query(query):
        return 0
    functions, argument, reciprocal, power = _intent(query)
    # Consider the requested expression, not functions appearing on the answer side.
    text = mask_markdown_code(text)
    expression = text.split("=", 1)[0]
    present = {
        name
        for name, pattern in (
            ("integral", r"\\int|∫"),
            ("sqrt", r"\\sqrt|√"),
            ("sin", r"\\sin|sin"),
            ("cos", r"\\cos|cos"),
        )
        if re.search(pattern, expression)
    }
    if not present:
        return 0
    score = sum(6 if name in present else -8 for name in functions)
    if argument:
        score += 3 if re.search(rf"(?<![a-z]){re.escape(argument)}(?![a-z])", expression) else -3
    if reciprocal is not None and "sqrt" in present:
        actual = bool(
            re.search(r"\\frac\s*\{(?:dx|1)\}\s*\{\s*\\sqrt|/\s*(?:\\sqrt|√)", expression)
        )
        score += 5 if actual == reciprocal else -8
    if power is not None:
        score += 3 if bool(re.search(r"\^", expression)) == power else -4
    if formula_warnings(text):
        score -= 30
    return score


def focus_excerpt(text: str, query: str) -> str:
    """Select a complete display formula verbatim, or keep the original excerpt."""
    if not is_math_query(query):
        return text
    visible = mask_markdown_code(text)
    if visible.count("$$") % 2 or visible.count(r"\[") != visible.count(r"\]"):
        return text
    matches = list(_DISPLAY.finditer(visible))
    if not matches:
        return text
    best = max(matches, key=lambda match: math_relevance(match[0], query))
    if math_relevance(best[0], query) <= 0:
        return text
    start, end = best.span()
    # Preserve directly adjacent caveats/conditions as one literal source span.
    qualifier = re.compile(
        r"\b(?:неверн\w*|ошиб\w*|не\s+использ\w*|только|услов\w*|"
        r"при|где|если|if|where|provided|invalid|incorrect|wrong|only)\b", re.IGNORECASE
    )
    preceding = visible[:start].rstrip()
    preceding_start = preceding.rfind("\n") + 1
    previous_line = preceding[preceding_start:]
    if (qualifier.search(previous_line) and "$" not in previous_line
            and not re.search(r"\\[\[\]]", previous_line)
            and text[preceding_start:start] == visible[preceding_start:start]):
        start = preceding_start
    following = visible[end:]
    whitespace = re.match(r"\s*", following)
    assert whitespace is not None
    following_start = end + whitespace.end()
    following_end = visible.find("\n", following_start)
    if following_end < 0:
        following_end = len(visible)
    next_line = visible[following_start:following_end]
    if (qualifier.search(next_line) and "$" not in next_line
            and not re.search(r"\\[\[\]]", next_line)
            and text[end:following_end] == visible[end:following_end]):
        end = following_end
    return text[start:end]


def math_signature_matches(text: str, query: str) -> bool:
    """Match all explicit baseline features, without checking the equation's truth."""
    if not is_math_query(query):
        return False
    functions, argument, reciprocal, power = _intent(query)
    ideal = 6 * len(functions) + (3 if argument else 0)
    ideal += 5 if reciprocal is not None else 0
    ideal += 3 if power is not None else 0
    return math_relevance(text, query) == ideal


def conflicting_math(text: str, query: str) -> bool:
    """Detect explicit formula candidates that contradict the narrow query signature."""
    text = mask_markdown_code(text)
    return bool(re.search(r"\\int|\\sqrt|\\sin|\\cos|∫|√", text)) and not (
        math_signature_matches(text, query)
    )


def supports_math_query(text: str, query: str) -> bool:
    """Retain matching formulas and explicit supporting prose under a narrow gate."""
    visible = mask_markdown_code(text)
    if conflicting_math(visible, query):
        return False
    requested, _, _, _ = _intent(query)
    mentioned, _, _, _ = _intent(visible)
    return bool(requested) and requested <= mentioned
