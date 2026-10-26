"""Главное меню и общие команды."""

from __future__ import annotations

from vkbottle.bot import Bot, Message

from weather_vk_bot.keyboards import (
    BTN_BACK,
    BTN_EXTENDED,
    BTN_FORECAST,
    BTN_GEO,
    BTN_HOME,
    BTN_WEATHER,
    geo_keyboard,
)
from weather_vk_bot.services.state_manager import BotState

from .common import (
    CITY_PROMPT,
    EXTENDED_CITY_PROMPT,
    FORECAST_CITY_PROMPT,
    GEO_PROMPT,
    UNKNOWN_TEXT,
    WELCOME_TEXT,
    HandlerDeps,
    message_text,
    prompt_for_city,
    send_text,
    show_main_menu,
)


def register(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message(text=["/start", "start", "начать"])
    async def start(message: Message) -> None:
        await show_main_menu(message, deps)

    @bot.on.message(text=[BTN_WEATHER])
    async def weather_button(message: Message) -> None:
        deps.states.remember(message.peer_id, mode="current")
        await prompt_for_city(
            message,
            deps,
            BotState.WAITING_CITY,
            CITY_PROMPT,
        )

    @bot.on.message(text=[BTN_FORECAST])
    async def forecast_button(message: Message) -> None:
        deps.states.remember(message.peer_id, mode="forecast")
        await prompt_for_city(
            message,
            deps,
            BotState.WAITING_FORECAST_CITY,
            FORECAST_CITY_PROMPT,
        )

    @bot.on.message(text=[BTN_EXTENDED])
    async def extended_button(message: Message) -> None:
        deps.states.remember(message.peer_id, mode="extended")
        await prompt_for_city(
            message,
            deps,
            BotState.WAITING_EXTENDED,
            EXTENDED_CITY_PROMPT,
        )

    @bot.on.message(text=[BTN_GEO])
    async def geo_button(message: Message) -> None:
        await deps.states.set_state(message.peer_id, BotState.WAITING_GEO)
        await send_text(message, GEO_PROMPT, geo_keyboard())

    @bot.on.message(text=[BTN_BACK, BTN_HOME, "/cancel", "cancel", "отмена"])
    async def back_to_menu(message: Message) -> None:
        await show_main_menu(message, deps)


def register_fallback(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message()
    async def fallback(message: Message) -> None:
        text = message_text(message)
        await show_main_menu(
            message,
            deps,
            WELCOME_TEXT if not text else UNKNOWN_TEXT,
        )
