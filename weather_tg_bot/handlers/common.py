"""Общие зависимости и функции Telegram handlers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram.types import Message, ReplyKeyboardMarkup

from weather_core.errors import describe_weather_error
from weather_core.message import split_message
from weather_core.services.weather_service import WeatherService
from weather_core.texts import (
    CHANGE_CITY_PROMPT,
    CITY_PROMPT,
    COMPARE_CITY_1_PROMPT,
    COMPARE_CITY_2_PROMPT,
    EXTENDED_CITY_PROMPT,
    FORECAST_CITY_PROMPT,
    GEO_PROMPT,
    HELP_TEXT,
    INVALID_COORDS_TEXT,
    UNKNOWN_TEXT,
    WELCOME_TEXT,
)
from weather_tg_bot.state import StateStore, TgState

LOGGER = logging.getLogger(__name__)
TELEGRAM_MESSAGE_LIMIT = 4096


@dataclass(frozen=True, slots=True)
class TgDeps:
    service: WeatherService


def message_text(message: Message) -> str:
    return (message.text or "").strip()


async def send_text(
    message: Message,
    text: str,
    keyboard: ReplyKeyboardMarkup | None = None,
) -> None:
    """Отправляет текст частями; клавиатура ставится на последнюю часть."""
    chunks = split_message(text, limit=TELEGRAM_MESSAGE_LIMIT)
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=keyboard if index == len(chunks) - 1 else None,
        )


async def last_city(store: StateStore) -> str | None:
    data = await store.get_data()
    value = data.get("last_city")
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


async def remember_city(
    store: StateStore,
    *,
    city: str | None = None,
    mode: str | None = None,
) -> None:
    data = await store.get_data()
    updates: dict[str, str] = {}
    if city is not None:
        updates["last_city"] = city
    elif isinstance(data.get("last_city"), str):
        updates["last_city"] = data["last_city"]
    if mode is not None:
        updates["last_mode"] = mode
    if updates:
        await store.update_data(**updates)


async def main_menu_text(store: StateStore, text: str = WELCOME_TEXT) -> str:
    city = await last_city(store)
    if city:
        text = f"{text}\n\n🏙 Текущий город: {city}"
    return text


async def show_main_menu(
    message: Message,
    deps: TgDeps,
    store: StateStore,
    text: str = WELCOME_TEXT,
) -> None:
    from weather_tg_bot.keyboards import main_menu_keyboard

    text = await main_menu_text(store, text)
    await store.set_state(TgState.MAIN_MENU)
    await send_text(message, text, main_menu_keyboard())


async def prompt_for_city(
    message: Message,
    deps: TgDeps,
    store: StateStore,
    state: str,
    prompt: str,
) -> None:
    from weather_tg_bot.keyboards import main_menu_keyboard

    await store.set_state(state)
    await send_text(message, prompt, main_menu_keyboard())


async def reply_weather_error(
    message: Message,
    exc: Exception,
    *,
    keyboard: ReplyKeyboardMarkup | None = None,
) -> None:
    from weather_tg_bot.keyboards import main_menu_keyboard

    LOGGER.warning(
        "Ошибка получения погоды: chat_id=%s, type=%s",
        message.chat.id,
        type(exc).__name__,
    )
    await send_text(
        message,
        describe_weather_error(exc),
        keyboard or main_menu_keyboard(),
    )


__all__ = (
    "CHANGE_CITY_PROMPT",
    "CITY_PROMPT",
    "COMPARE_CITY_1_PROMPT",
    "COMPARE_CITY_2_PROMPT",
    "EXTENDED_CITY_PROMPT",
    "FORECAST_CITY_PROMPT",
    "GEO_PROMPT",
    "HELP_TEXT",
    "INVALID_COORDS_TEXT",
    "LOGGER",
    "TELEGRAM_MESSAGE_LIMIT",
    "TgDeps",
    "UNKNOWN_TEXT",
    "WELCOME_TEXT",
    "last_city",
    "main_menu_text",
    "message_text",
    "prompt_for_city",
    "remember_city",
    "reply_weather_error",
    "send_text",
    "show_main_menu",
)
