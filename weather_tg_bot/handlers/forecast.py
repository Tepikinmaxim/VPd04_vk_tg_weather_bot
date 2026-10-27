"""Сценарий пятидневного прогноза Telegram."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from weather_core.services.formatter import format_forecast, weather_city
from weather_tg_bot.handlers.common import (
    FORECAST_CITY_PROMPT,
    TgDeps,
    message_text,
    prompt_for_city,
    remember_city,
    reply_weather_error,
    send_text,
)
from weather_tg_bot.keyboards import main_menu_keyboard
from weather_tg_bot.state import FSMStateStore, TgState


async def show_forecast(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
    city: str,
) -> bool:
    normalized = city.strip()
    if not normalized:
        return False

    try:
        result = await deps.service.get_forecast(normalized)
    except Exception as exc:
        await reply_weather_error(message, exc)
        return False

    await remember_city(
        store,
        city=weather_city(result) or normalized,
        mode="forecast",
    )
    await send_text(message, format_forecast(result), main_menu_keyboard())
    await store.set_state(TgState.MAIN_MENU)
    return True


async def handle_waiting_forecast_city(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    city = message_text(message)
    if not city:
        await prompt_for_city(
            message,
            deps,
            store,
            TgState.WAITING_FORECAST_CITY,
            FORECAST_CITY_PROMPT,
        )
        return
    await show_forecast(message, deps, store, city)



def register(router: Router, deps: TgDeps) -> None:
    @router.message(StateFilter(TgState.WAITING_FORECAST_CITY))
    async def forecast_by_city(message: Message, state: FSMContext) -> None:
        await handle_waiting_forecast_city(
            message,
            deps,
            FSMStateStore(state),
        )
