"""Сценарий геолокации и ручного ввода координат."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from vkbottle.bot import Bot, Message

from weather_vk_bot.keyboards import (
    BTN_MANUAL_COORDS,
    geo_keyboard,
    navigation_keyboard,
)
from weather_vk_bot.services.formatter import format_current
from weather_vk_bot.services.state_manager import BotState

from .common import (
    GEO_PROMPT,
    INVALID_COORDS_TEXT,
    HandlerDeps,
    message_text,
    reply_weather_error,
    send_text,
)

_COORDINATES_RE = re.compile(
    r"^\s*(-?\d+(?:[.,]\d+)?)\s*(?:,|\s)\s*(-?\d+(?:[.,]\d+)?)\s*$"
)


def _validate_coordinates(lat: float, lon: float) -> tuple[float, float]:
    if not -90.0 <= lat <= 90.0:
        raise ValueError("Широта должна быть от -90 до 90.")
    if not -180.0 <= lon <= 180.0:
        raise ValueError("Долгота должна быть от -180 до 180.")
    return lat, lon


def _parse_coordinates(text: str) -> tuple[float, float]:
    """Разбирает ``55.7558,37.6173`` и ``55.7558 37.6173``."""
    match = _COORDINATES_RE.match(text)
    if match is None:
        raise ValueError("Неверный формат координат.")
    try:
        lat = float(match.group(1).replace(",", "."))
        lon = float(match.group(2).replace(",", "."))
    except ValueError as exc:
        raise ValueError("Неверный формат координат.") from exc
    return _validate_coordinates(lat, lon)


def _coordinate_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def extract_geo_coordinates(message: Message) -> tuple[float, float] | None:
    """Возвращает координаты из вложения VK, если они корректны."""
    geo = getattr(message, "geo", None)
    coordinates: Any = getattr(geo, "coordinates", None)
    if coordinates is None and isinstance(geo, Mapping):
        coordinates = geo.get("coordinates")

    if coordinates is None:
        return None

    latitude = (
        coordinates.get("latitude")
        if isinstance(coordinates, Mapping)
        else getattr(coordinates, "latitude", None)
    )
    longitude = (
        coordinates.get("longitude")
        if isinstance(coordinates, Mapping)
        else getattr(coordinates, "longitude", None)
    )
    lat = _coordinate_value(latitude)
    lon = _coordinate_value(longitude)
    if lat is None or lon is None:
        return None
    try:
        return _validate_coordinates(lat, lon)
    except ValueError:
        return None


def register(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message(state=BotState.WAITING_GEO)
    async def weather_by_geo(message: Message) -> None:
        coordinates = extract_geo_coordinates(message)
        if coordinates is None:
            text = message_text(message)
            if not text:
                await send_text(message, GEO_PROMPT, geo_keyboard())
                return
            if text == BTN_MANUAL_COORDS:
                await send_text(message, GEO_PROMPT, geo_keyboard())
                return
            try:
                coordinates = _parse_coordinates(text)
            except ValueError as exc:
                await send_text(
                    message,
                    f"{INVALID_COORDS_TEXT}\n\n{exc}",
                    geo_keyboard(),
                )
                return

        try:
            result = await deps.service.get_by_coordinates(*coordinates)
        except Exception as exc:
            await reply_weather_error(
                message,
                exc,
                keyboard=geo_keyboard(),
            )
            return

        deps.states.remember(
            message.peer_id,
            mode="geo",
        )
        text = format_current(result)
        await send_text(message, text, navigation_keyboard())
        await deps.states.reset(message.peer_id)
