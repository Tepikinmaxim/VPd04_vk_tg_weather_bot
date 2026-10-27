"""Общая логика сравнения городов."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from weather_core.services.formatter import weather_city
from weather_core.texts import COMPARE_CITY_2_PROMPT

COMPARE_CITY_EXAMPLES = ("Москва", "Санкт-Петербург", "Сочи", "Казань")


def city_key(value: str) -> str:
    normalized = value.casefold().replace("ё", "е")
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = " ".join(normalized.split())
    for prefix in ("городской округ ", "город ", "г "):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :]
    return normalized


def comparison_example(first_city: str) -> str | None:
    if not re.search(r"[а-яё]", first_city.casefold()):
        return None
    first_key = city_key(first_city)
    for city in COMPARE_CITY_EXAMPLES:
        if city_key(city) != first_key:
            return city
    return None


def location_coordinates(
    result: Mapping[str, Any],
) -> tuple[float, float] | None:
    location = result.get("location")
    if not isinstance(location, Mapping):
        return None
    lat = location.get("lat")
    lon = location.get("lon")
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return (round(float(lat), 6), round(float(lon), 6))


def same_location(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    first_name = weather_city(first)
    second_name = weather_city(second)
    if (
        first_name
        and second_name
        and city_key(first_name) == city_key(second_name)
    ):
        return True

    first_coordinates = location_coordinates(first)
    return (
        first_coordinates is not None
        and first_coordinates == location_coordinates(second)
    )


def second_city_prompt(first_city: str, *, duplicate: bool = False) -> str:
    lines: list[str] = []
    if duplicate:
        lines.append("⚠️ Этот город уже выбран первым. Введите другой город.")
    lines.append(f"📊 Первый город: {first_city}")
    lines.append(COMPARE_CITY_2_PROMPT)
    example = comparison_example(first_city)
    if example:
        lines.append(f"Например: {example}.")
    return "\n".join(lines)


__all__ = (
    "COMPARE_CITY_EXAMPLES",
    "city_key",
    "comparison_example",
    "location_coordinates",
    "same_location",
    "second_city_prompt",
)
