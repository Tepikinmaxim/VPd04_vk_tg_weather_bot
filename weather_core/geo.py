"""Разбор и проверка координат."""

from __future__ import annotations

import re
from typing import Any

COORDINATES_RE = re.compile(
    r"^\s*(-?\d+(?:[.,]\d+)?)\s*(?:,|\s)\s*(-?\d+(?:[.,]\d+)?)\s*$"
)


def validate_coordinates(lat: float, lon: float) -> tuple[float, float]:
    if not -90.0 <= lat <= 90.0:
        raise ValueError("Широта должна быть от -90 до 90.")
    if not -180.0 <= lon <= 180.0:
        raise ValueError("Долгота должна быть от -180 до 180.")
    return lat, lon


def parse_coordinates(text: str) -> tuple[float, float]:
    """Разбирает ``55.7558,37.6173`` и ``55.7558 37.6173``."""
    match = COORDINATES_RE.match(text)
    if match is None:
        raise ValueError("Неверный формат координат.")
    try:
        lat = float(match.group(1).replace(",", "."))
        lon = float(match.group(2).replace(",", "."))
    except ValueError as exc:
        raise ValueError("Неверный формат координат.") from exc
    return validate_coordinates(lat, lon)


def coordinate_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def is_coordinate_text(text: str) -> bool:
    try:
        parse_coordinates(text.strip())
    except ValueError:
        return False
    return True


__all__ = (
    "COORDINATES_RE",
    "coordinate_value",
    "is_coordinate_text",
    "parse_coordinates",
    "validate_coordinates",
)
