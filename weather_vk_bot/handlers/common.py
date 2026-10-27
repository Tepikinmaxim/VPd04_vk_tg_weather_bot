"""Общие зависимости и вспомогательные функции handlers."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any

from vkbottle.api import ABCAPI
from vkbottle.bot import Message

from weather_core.errors import describe_weather_error
from weather_core.message import split_message
from weather_core.services.weather_service import WeatherService
from weather_core.texts import (
    CHANGE_CITY_PROMPT,
    CITY_PROMPT,
    COMPARE_CITY_1_PROMPT,
    COMPARE_CITY_2_PROMPT,
    DEFAULT_MESSAGE_LIMIT,
    EXTENDED_CITY_PROMPT,
    FORECAST_CITY_PROMPT,
    GEO_PROMPT,
    HELP_TEXT,
    INVALID_COORDS_TEXT,
    UNKNOWN_TEXT,
    WELCOME_TEXT,
)
from weather_vk_bot.keyboards import main_menu_keyboard
from weather_vk_bot.services.state_manager import BotState, StateManager
from weather_vk_bot.services.welcome_gate import WelcomeGate

LOGGER = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = DEFAULT_MESSAGE_LIMIT


@dataclass(frozen=True, slots=True)
class HandlerDeps:
    service: WeatherService
    states: StateManager
    welcome_gate: WelcomeGate


def message_text(message: Message) -> str:
    return (message.text or "").strip()


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
