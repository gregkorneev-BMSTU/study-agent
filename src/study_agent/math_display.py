"""Conservative, plain-text LaTeX fallback for the lightweight Qt client.

This changes notation only; it neither evaluates nor repairs source formulas.
Unknown commands stay visible and the UI always offers the original text.
"""

import re

from study_agent.math_content import mask_markdown_code

_MATH = re.compile(
    r"\$\$(.*?)\$\$|\\\[(.*?)\\\]|\\\((.*?)\\\)|(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)",
    re.S,
)
_COMMANDS = {
    "int": "∫", "iint": "∬", "sum": "∑", "prod": "∏", "infty": "∞",
    "cdot": "·", "times": "×", "neq": "≠", "leq": "≤", "geq": "≥",
    "alpha": "α", "beta": "β", "gamma": "γ", "pi": "π", "theta": "θ",
    "sin": "sin", "cos": "cos", "tan": "tan", "ln": "ln", "log": "log",
    "arcsin": "arcsin", "arccos": "arccos", "arctan": "arctan",
    "left": "", "right": "",
}


def has_math(text: str) -> bool:
    """Detect delimited math or common commands, including incomplete OCR output."""
    visible = mask_markdown_code(text)
    return bool(_MATH.search(visible) or re.search(r"\\(?:int|sqrt|frac)\b", visible))


def _group(text: str, start: int) -> tuple[str, int] | None:
    if start >= len(text) or text[start] != "{":
        return None
    depth = 1
    for index in range(start + 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
    return None


def _formula(text: str, depth: int = 0) -> str:
    if depth > 20:
        return text
    output: list[str] = []
    index = 0
    while index < len(text):
        if text[index:index + 2] in {r"\,", r"\;", r"\:", r"\!"}:
            output.append(" " if text[index + 1] != "!" else "")
            index += 2
            continue
        if text[index] in "^_":
            argument = _group(text, index + 1)
            if argument:
                output.append(f"{text[index]}({_formula(argument[0], depth + 1)})")
                index = argument[1]
                continue
        match = re.match(r"\\([A-Za-z]+)", text[index:])
        if not match:
            output.append(text[index])
            index += 1
            continue
        command = match[1]
        end = index + match.end()
        argument = _group(text, end)
        if command in {"frac", "dfrac", "tfrac"} and argument:
            denominator = _group(text, argument[1])
            if denominator:
                output.append(f"({_formula(argument[0], depth + 1)})/"
                              f"({_formula(denominator[0], depth + 1)})")
                index = denominator[1]
                continue
        if command in {"sqrt", "operatorname", "mathrm", "text", "textcircled"} and argument:
            content = _formula(argument[0], depth + 1)
            output.append(f"√({content})" if command == "sqrt" else
                          f"({content})" if command == "textcircled" else content)
            index = argument[1]
            continue
        output.append(_COMMANDS.get(command, match[0]))
        index = end
    return "".join(output)


def readable_math(text: str) -> str:
    """Return plain text, preserving Markdown code and unsupported notation."""
    visible = mask_markdown_code(text)
    output: list[str] = []
    cursor = 0
    for match in _MATH.finditer(visible):
        # Do not process a formula crossing literal Markdown code.
        if visible[match.start():match.end()] != text[match.start():match.end()]:
            continue
        group = next(index for index in range(1, 5) if match[index] is not None)
        output.append(text[cursor:match.start()])
        output.append(_formula(text[match.start(group):match.end(group)]))
        cursor = match.end()
    output.append(text[cursor:])
    return "".join(output)
