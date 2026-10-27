"""Главное меню и общие команды."""

from __future__ import annotations

from vkbottle.bot import Bot, Message

from weather_vk_bot.keyboards import (
    BTN_CHANGE_CITY,
    BTN_EXTENDED,
    BTN_FORECAST,
    BTN_GEO,
    BTN_WEATHER,
    geo_keyboard,
)
from weather_vk_bot.services.state_manager import BotState

from .common import (
    CHANGE_CITY_PROMPT,
    CITY_PROMPT,
    EXTENDED_CITY_PROMPT,
    FORECAST_CITY_PROMPT,
    GEO_PROMPT,
    HELP_TEXT,
    UNKNOWN_TEXT,
    WELCOME_TEXT,
    HandlerDeps,
    message_text,
    prompt_for_city,
    send_text,
    show_main_menu,
)
from .forecast import show_forecast
from .weather import show_current_weather


def register(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message(text=["/start", "start", "начать"])
    async def start(message: Message) -> None:
        if not deps.welcome_gate.claim(message.peer_id):
            return
        await show_main_menu(message, deps, HELP_TEXT)

    @bot.on.message(text=["/cancel", "cancel", "отмена"])
    async def cancel(message: Message) -> None:
        await show_main_menu(message, deps)

    @bot.on.message(text=[BTN_WEATHER])
    async def weather_button(message: Message) -> None:
        deps.states.remember(message.peer_id, mode="current")
        city = deps.states.get_context(message.peer_id).last_city
        if city:
            await show_current_weather(message, deps, city)
            return
        await prompt_for_city(
            message,
            deps,
            BotState.WAITING_CITY,
            CITY_PROMPT,
        )

    @bot.on.message(text=[BTN_FORECAST])
    async def forecast_button(message: Message) -> None:
        deps.states.remember(message.peer_id, mode="forecast")
        city = deps.states.get_context(message.peer_id).last_city
        if city:
            await show_forecast(message, deps, city)
            return
        await prompt_for_city(
            message,
            deps,
            BotState.WAITING_FORECAST_CITY,
            FORECAST_CITY_PROMPT,
        )

    @bot.on.message(text=[BTN_EXTENDED])
    async def extended_button(message: Message) -> None:
        deps.states.remember(message.peer_id, mode="extended")
        city = deps.states.get_context(message.peer_id).last_city
        if city:
            await show_current_weather(message, deps, city, extended=True)
            return
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

    @bot.on.message(text=[BTN_CHANGE_CITY])
    async def change_city_button(message: Message) -> None:
        await prompt_for_city(
            message,
            deps,
            BotState.WAITING_CHANGE_CITY,
            CHANGE_CITY_PROMPT,
        )

    @bot.on.message(state=BotState.WAITING_CHANGE_CITY)
    async def save_new_city(message: Message) -> None:
        city = message_text(message)
        if not city:
            await prompt_for_city(
                message,
                deps,
                BotState.WAITING_CHANGE_CITY,
                CHANGE_CITY_PROMPT,
            )
            return

        deps.states.remember(message.peer_id, city=city)
        await show_main_menu(message, deps, "✅ Новый город сохранён.")


def register_fallback(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message()
    async def fallback(message: Message) -> None:
        text = message_text(message)
        await show_main_menu(
            message,
            deps,
            WELCOME_TEXT if not text else UNKNOWN_TEXT,
        )
