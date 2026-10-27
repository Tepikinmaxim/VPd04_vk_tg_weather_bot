"""Геолокация и координаты в Telegram."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Filter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from weather_core.buttons import BTN_MANUAL_COORDS
from weather_core.geo import (
    coordinate_value,
    is_coordinate_text,
    parse_coordinates,
    validate_coordinates,
)
from weather_core.services.formatter import format_current, weather_city
from weather_tg_bot.handlers.common import (
    GEO_PROMPT,
    INVALID_COORDS_TEXT,
    TgDeps,
    message_text,
    remember_city,
    reply_weather_error,
    send_text,
)
from weather_tg_bot.keyboards import geo_keyboard, main_menu_keyboard
from weather_tg_bot.state import FSMStateStore, TgState


class CoordinatesFilter(Filter):
    """Пропускает сообщения, похожие на пару координат."""

    async def __call__(self, message: Message) -> bool:
        return is_coordinate_text(message.text or "")


def extract_location_coordinates(message: Message) -> tuple[float, float] | None:
    location = getattr(message, "location", None)
    if location is None:
        return None
    latitude = getattr(location, "latitude", None)
    longitude = getattr(location, "longitude", None)
    lat = coordinate_value(latitude)
    lon = coordinate_value(longitude)
    if lat is None or lon is None:
        return None
    try:
        return validate_coordinates(lat, lon)
    except ValueError:
        return None


async def show_weather_by_coordinates(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
    coordinates: tuple[float, float],
) -> None:
    try:
        result = await deps.service.get_by_coordinates(*coordinates)
    except Exception as exc:
        await reply_weather_error(message, exc, keyboard=geo_keyboard())
        return

    await remember_city(store, city=weather_city(result), mode="geo")
    await send_text(message, format_current(result), main_menu_keyboard())
    await store.set_state(TgState.MAIN_MENU)


async def handle_waiting_geo(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    coordinates = extract_location_coordinates(message)
    if coordinates is None:
        text = message_text(message)
        if not text or text == BTN_MANUAL_COORDS:
            await send_text(message, GEO_PROMPT, geo_keyboard())
            return
        try:
            coordinates = parse_coordinates(text)
        except ValueError as exc:
            await send_text(
                message,
                f"{INVALID_COORDS_TEXT}\n\n{exc}",
                geo_keyboard(),
            )
            return

    await show_weather_by_coordinates(message, deps, store, coordinates)


def register_global(router: Router, deps: TgDeps) -> None:
    @router.message(CoordinatesFilter())
    async def coordinates_anywhere(message: Message, state: FSMContext) -> None:
        coordinates = parse_coordinates(message.text or "")
        await show_weather_by_coordinates(
            message,
            deps,
            FSMStateStore(state),
            coordinates,
        )


def register_state(router: Router, deps: TgDeps) -> None:
    @router.message(StateFilter(TgState.WAITING_GEO))
    async def weather_by_geo(message: Message, state: FSMContext) -> None:
        await handle_waiting_geo(message, deps, FSMStateStore(state))
