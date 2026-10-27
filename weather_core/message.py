"""Разбиение длинных сообщений."""

from __future__ import annotations

from weather_core.texts import DEFAULT_MESSAGE_LIMIT


def split_message(
    text: str,
    limit: int = DEFAULT_MESSAGE_LIMIT,
) -> list[str]:
    """Делит длинный текст на части, не разрывая строки без необходимости."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for line in text.splitlines():
        while len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_length = 0
            chunks.append(line[:limit])
            line = line[limit:]

        extra = len(line) + (1 if current else 0)
        if current and current_length + extra > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length += extra

    if current:
        chunks.append("\n".join(current))
    return chunks or [""]


__all__ = ("split_message",)
