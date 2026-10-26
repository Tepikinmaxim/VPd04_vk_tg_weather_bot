"""Общие зависимости и вспомогательные функции handlers."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any

from vkbottle.bot import Message

from OpenWeatherAPI import APIConnectionError, CityNotFoundError, OpenWeatherAPIError
from weather_vk_bot.keyboards import (
    main_menu_keyboard,
    navigation_keyboard,
)
from weather_vk_bot.services.state_manager import BotState, StateManager
from weather_vk_bot.services.weather_service import WeatherService

LOGGER = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 4000

WELCOME_TEXT = (
    "🌤 VK Weather Bot\n"
    "──────────────\n"
    "Выберите действие кнопками ниже или введите город.\n"
    "Я покажу текущую погоду, прогноз на 5 дней и качество воздуха."
)
CITY_PROMPT = (
    "🏙 Введите название города, например: Москва.\n"
    "Для возврата используйте кнопки ниже."
)
FORECAST_CITY_PROMPT = (
    "📅 Введите город, для которого нужен прогноз на 5 дней.\n"
    "Например: Санкт-Петербург."
)
EXTENDED_CITY_PROMPT = (
    "🌫 Введите город для расширенного режима.\n"
    "Будут показаны давление, видимость, солнце и качество воздуха."
)
GEO_PROMPT = (
    "📍 Отправьте геопозицию кнопкой ниже или введите координаты текстом.\n"
    "Формат: 55.7558, 37.6173 или 55.7558 37.6173."
)
INVALID_COORDS_TEXT = (
    "❌ Не удалось распознать координаты.\n"
    "Отправьте их в формате: 55.7558, 37.6173\n"
    "Широта — от -90 до 90, долгота — от -180 до 180."
)
UNKNOWN_TEXT = (
    "🤔 Не понял команду. Выберите действие кнопками ниже."
)
HELP_TEXT = (
    "ℹ️ Помощь\n"
    "──────────────\n"
    "🌤 Погода сейчас — текущая погода по городу.\n"
    "📅 Прогноз 5 дней — прогноз по одному блоку на 12:00 MSK.\n"
    "🌫 Расширенный режим — давление, видимость, солнце и воздух.\n"
    "📍 Геолокация — отправьте геопозицию или координаты текстом.\n"
    "⬅️ Назад и 🏠 Главное меню — возврат в начало.\n\n"
    "Координаты: 55.7558, 37.6173 или 55.7558 37.6173."
)


@dataclass(frozen=True, slots=True)
class HandlerDeps:
    service: WeatherService
    states: StateManager


def message_text(message: Message) -> str:
    return (message.text or "").strip()


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
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


async def send_text(
    message: Message,
    text: str,
    keyboard: str | None = None,
) -> None:
    """Отправляет текст частями; клавиатура ставится на последнюю часть."""
    chunks = split_message(text)
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            random_id=secrets.randbits(31),
            keyboard=keyboard if index == len(chunks) - 1 else None,
        )


async def show_main_menu(
    message: Message,
    deps: HandlerDeps,
    text: str = WELCOME_TEXT,
) -> None:
    await deps.states.set_state(message.peer_id, BotState.MAIN_MENU)
    await send_text(message, text, main_menu_keyboard())


async def show_navigation(message: Message, text: str) -> None:
    await send_text(message, text, navigation_keyboard())


async def prompt_for_city(
    message: Message,
    deps: HandlerDeps,
    state: BotState,
    prompt: str,
) -> None:
    await deps.states.set_state(message.peer_id, state)
    await send_text(message, prompt, navigation_keyboard())


def describe_weather_error(exc: Exception) -> str:
    if isinstance(exc, CityNotFoundError):
        return (
            "❌ Город не найден. Проверьте название и попробуйте снова.\n"
            "Например: Москва или Санкт-Петербург."
        )
    if isinstance(exc, APIConnectionError):
        return (
            "📡 Сервис погоды временно недоступен. "
            "Попробуйте ещё раз через несколько минут."
        )
    if isinstance(exc, OpenWeatherAPIError):
        return f"⚠️ Не удалось получить погоду: {exc}"
    return "⚠️ Не удалось получить погоду. Попробуйте позже."


async def reply_weather_error(
    message: Message,
    exc: Exception,
    *,
    keyboard: str | None = None,
) -> None:
    LOGGER.warning(
        "Ошибка получения погоды: peer_id=%s, type=%s",
        message.peer_id,
        type(exc).__name__,
    )
    await send_text(
        message,
        describe_weather_error(exc),
        keyboard or navigation_keyboard(),
    )
