"""Сценарии текущей и расширенной погоды."""

from __future__ import annotations

from vkbottle.bot import Bot, Message

from weather_vk_bot.keyboards import navigation_keyboard
from weather_vk_bot.services.formatter import format_current
from weather_vk_bot.services.state_manager import BotState

from .common import (
    CITY_PROMPT,
    EXTENDED_CITY_PROMPT,
    HandlerDeps,
    message_text,
    prompt_for_city,
    reply_weather_error,
    send_text,
)


async def _handle_city(
    message: Message,
    deps: HandlerDeps,
    *,
    extended: bool,
) -> None:
    city = message_text(message)
    if not city:
        await prompt_for_city(
            message,
            deps,
            BotState.WAITING_EXTENDED if extended else BotState.WAITING_CITY,
            EXTENDED_CITY_PROMPT if extended else CITY_PROMPT,
        )
        return

    try:
        result = await deps.service.get_current(city, extended=extended)
    except Exception as exc:
        await reply_weather_error(message, exc)
        return

    deps.states.remember(
        message.peer_id,
        city=city,
        mode="extended" if extended else "current",
    )
    text = format_current(result, extended=extended)
    await send_text(message, text, navigation_keyboard())
    await deps.states.reset(message.peer_id)


def register(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message(state=BotState.WAITING_CITY)
    async def current_weather(message: Message) -> None:
        await _handle_city(message, deps, extended=False)

    @bot.on.message(state=BotState.WAITING_EXTENDED)
    async def extended_weather(message: Message) -> None:
        await _handle_city(message, deps, extended=True)
