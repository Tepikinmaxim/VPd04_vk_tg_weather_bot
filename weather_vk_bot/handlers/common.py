"""Общие зависимости и вспомогательные функции handlers."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any

from vkbottle.api import ABCAPI
from vkbottle.bot import Message

from OpenWeatherAPI import APIConnectionError, CityNotFoundError, OpenWeatherAPIError
from weather_vk_bot.keyboards import main_menu_keyboard
from weather_vk_bot.services.state_manager import BotState, StateManager
from weather_vk_bot.services.weather_service import WeatherService
from weather_vk_bot.services.welcome_gate import WelcomeGate

LOGGER = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 4000

WELCOME_TEXT = (
    "Погодный эксперт\n"
    "──────────────\n"
    "Выберите действие кнопками ниже или введите город.\n"
    "Я запоминаю город и показываю текущую погоду, прогноз на 5 дней, "
    "сравнение городов и качество воздуха."
)
CITY_PROMPT = (
    "🏙 Введите название города, например: Москва.\n"
    "Или выберите другой пункт меню."
)
FORECAST_CITY_PROMPT = (
    "📅 Введите город, для которого нужен прогноз на 5 дней.\n"
    "Например: Санкт-Петербург."
)
EXTENDED_CITY_PROMPT = (
    "🌫 Введите город для расширенного режима.\n"
    "Будут показаны давление, видимость, солнце и качество воздуха."
)
CHANGE_CITY_PROMPT = (
    "🏙 Введите новый город, который нужно запомнить.\n"
    "После сохранения вернусь в главное меню."
)
COMPARE_CITY_1_PROMPT = (
    "📊 Введите первый город для сравнения.\n"
    "Например: Москва."
)
COMPARE_CITY_2_PROMPT = (
    "📊 Теперь введите второй город для сравнения.\n"
    "Он должен отличаться от первого."
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
    "Погодный эксперт\n"
    "\n"
    "ℹ️ Что могу:\n"
    "──────────────\n"
    "🌤 Погода сейчас — текущая погода по сохранённому городу.\n"
    "📅 Прогноз 5 дней — прогноз на 12:00 MSK каждого из 5 дней.\n"
    "📊 Сравнить погоду — текущая погода в двух городах.\n"
    "🌫 Расширенный режим — давление, видимость, солнце и воздух.\n"
    "📍 Геолокация — отправьте геопозицию или координаты текстом.\n"
    "Координаты можно отправить в любой момент — бот сам откроет "
    "геолокацию.\n"
    "После результата бот сразу возвращается в главное меню.\n\n"
    "Если город ещё не выбран, бот попросит его ввести.\n"
    "Принимает и название города и  Координаты в формате:  "
    "55.7558, 37.6173 или 55.7558 37.6173."
)


@dataclass(frozen=True, slots=True)
class HandlerDeps:
    service: WeatherService
    states: StateManager
    welcome_gate: WelcomeGate


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


def main_menu_text(
    deps: HandlerDeps,
    peer_id: int,
    text: str = WELCOME_TEXT,
) -> str:
    context = deps.states.get_context(peer_id)
    if context.last_city:
        text = f"{text}\n\n🏙 Текущий город: {context.last_city}"
    return text


async def send_peer_text(
    api: ABCAPI,
    peer_id: int,
    text: str,
    keyboard: str | None = None,
) -> None:
    """Отправляет текст в диалог без входящего Message."""
    chunks = split_message(text)
    for index, chunk in enumerate(chunks):
        await api.messages.send(
            peer_id=peer_id,
            message=chunk,
            random_id=secrets.randbits(31),
            keyboard=keyboard if index == len(chunks) - 1 else None,
        )


async def show_main_menu_for_peer(
    api: ABCAPI,
    deps: HandlerDeps,
    peer_id: int,
    text: str = WELCOME_TEXT,
) -> None:
    """Показывает главное меню по peer_id без объекта Message."""
    text = main_menu_text(deps, peer_id, text)
    await deps.states.set_state(peer_id, BotState.MAIN_MENU)
    await send_peer_text(api, peer_id, text, main_menu_keyboard())


async def show_main_menu(
    message: Message,
    deps: HandlerDeps,
    text: str = WELCOME_TEXT,
) -> None:
    text = main_menu_text(deps, message.peer_id, text)
    await deps.states.set_state(message.peer_id, BotState.MAIN_MENU)
    await send_text(message, text, main_menu_keyboard())


async def prompt_for_city(
    message: Message,
    deps: HandlerDeps,
    state: BotState,
    prompt: str,
) -> None:
    await deps.states.set_state(message.peer_id, state)
    await send_text(message, prompt, main_menu_keyboard())


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
        keyboard or main_menu_keyboard(),
    )
