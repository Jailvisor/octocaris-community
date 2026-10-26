"""Metadata cleanup shared by the publisher and one-off catalog fixes."""

GENERIC_TAGS = {"anime", "wallpaper engine", "game"}
DESCRIPTION_NOISE = ("设置请移动", "bug反馈", "Q群", "QQ群")
NAME_SEPARATOR = "｜"  # full-width bar: ASCII '|' is illegal in Windows names
SERIES = "Blue Archive"


def sanitize_tags(tags) -> list[str]:
    cleaned: list[str] = []
    for tag in tags or []:
        value = str(tag).strip()
        if not value or value.lower() in GENERIC_TAGS:
            continue
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def sanitize_description(text) -> str:
    lines = []
    for line in str(text or "").splitlines():
        if any(marker in line for marker in DESCRIPTION_NOISE):
            continue
        lines.append(line.rstrip())
    cleaned = "\n".join(lines).strip()
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned


def name_problems(name: str) -> list[str]:
    """Check the `中文｜English｜日本語｜Blue Archive` naming rule."""
    parts = name.split(NAME_SEPARATOR)
    problems = []
    if len(parts) != 4:
        problems.append(f"expected 4 segments, found {len(parts)}")
    if any(not part.strip() for part in parts):
        problems.append("empty segment")
    if len(parts) == 4 and parts[3].strip() != SERIES:
        problems.append(f"series must be {SERIES!r}")
    return problems
