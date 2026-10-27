"""Сценарий геолокации и ручного ввода координат."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vkbottle.bot import Bot, Message

from weather_core.geo import (
    coordinate_value as _coordinate_value,
    parse_coordinates as _parse_coordinates,
    validate_coordinates as _validate_coordinates,
)
from weather_core.services.formatter import format_current, weather_city
from weather_vk_bot.keyboards import (
    BTN_MANUAL_COORDS,
    geo_keyboard,
    main_menu_keyboard,
)
from weather_vk_bot.services.state_manager import BotState

from .common import (
    GEO_PROMPT,
    INVALID_COORDS_TEXT,
    HandlerDeps,
    message_text,
    reply_weather_error,
    send_text,
)


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


def _is_coordinate_text(message: Any) -> bool:
    """Проверяет, похоже ли сообщение на пару координат."""
    text = str(getattr(message, "text", "") or "").strip()
    if not text:
        return False
    try:
        _parse_coordinates(text)
    except ValueError:
        return False
    return True


async def show_weather_by_coordinates(
    message: Message,
    deps: HandlerDeps,
    coordinates: tuple[float, float],
) -> None:
    """Запрашивает погоду по координатам и возвращает меню."""
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
        city=weather_city(result),
        mode="geo",
    )
    text = format_current(result)
    await send_text(message, text, main_menu_keyboard())
    await deps.states.reset(message.peer_id)


def register_global(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message(func=_is_coordinate_text)
    async def coordinates_anywhere(message: Message) -> None:
        coordinates = _parse_coordinates(message_text(message))
        await show_weather_by_coordinates(message, deps, coordinates)


def register_state(bot: Bot, deps: HandlerDeps) -> None:
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

        await show_weather_by_coordinates(message, deps, coordinates)
