"""Сценарий пятидневного прогноза."""

from __future__ import annotations

from vkbottle.bot import Bot, Message

from weather_vk_bot.keyboards import navigation_keyboard
from weather_vk_bot.services.formatter import format_forecast
from weather_vk_bot.services.state_manager import BotState

from .common import (
    FORECAST_CITY_PROMPT,
    HandlerDeps,
    message_text,
    prompt_for_city,
    reply_weather_error,
    send_text,
)


def register(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message(state=BotState.WAITING_FORECAST_CITY)
    async def forecast_by_city(message: Message) -> None:
        city = message_text(message)
        if not city:
            await prompt_for_city(
                message,
                deps,
                BotState.WAITING_FORECAST_CITY,
                FORECAST_CITY_PROMPT,
            )
            return

        try:
            result = await deps.service.get_forecast(city)
        except Exception as exc:
            await reply_weather_error(message, exc)
            return

        deps.states.remember(
            message.peer_id,
            city=city,
            mode="forecast",
        )
        text = format_forecast(result)
        await send_text(message, text, navigation_keyboard())
        await deps.states.reset(message.peer_id)
