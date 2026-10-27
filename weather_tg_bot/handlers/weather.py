"""Сценарии текущей и расширенной погоды Telegram."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from weather_core.services.formatter import format_current, weather_city
from weather_tg_bot.handlers.common import (
    CITY_PROMPT,
    EXTENDED_CITY_PROMPT,
    TgDeps,
    message_text,
    prompt_for_city,
    remember_city,
    reply_weather_error,
    send_text,
)
from weather_tg_bot.keyboards import main_menu_keyboard
from weather_tg_bot.state import FSMStateStore, TgState


async def show_current_weather(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
    city: str,
    *,
    extended: bool = False,
) -> bool:
    normalized = city.strip()
    if not normalized:
        return False

    try:
        result = await deps.service.get_current(normalized, extended=extended)
    except Exception as exc:
        await reply_weather_error(message, exc)
        return False

    await remember_city(
        store,
        city=weather_city(result) or normalized,
        mode="extended" if extended else "current",
    )
    await send_text(
        message,
        format_current(result, extended=extended),
        main_menu_keyboard(),
    )
    await store.set_state(TgState.MAIN_MENU)
    return True


async def handle_waiting_city(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
    *,
    extended: bool = False,
) -> None:
    city = message_text(message)
    if not city:
        await prompt_for_city(
            message,
            deps,
            store,
            TgState.WAITING_EXTENDED if extended else TgState.WAITING_CITY,
            EXTENDED_CITY_PROMPT if extended else CITY_PROMPT,
        )
        return
    await show_current_weather(message, deps, store, city, extended=extended)



def register(router: Router, deps: TgDeps) -> None:
    @router.message(StateFilter(TgState.WAITING_CITY))
    async def current_weather(message: Message, state: FSMContext) -> None:
        await handle_waiting_city(message, deps, FSMStateStore(state))

    @router.message(StateFilter(TgState.WAITING_EXTENDED))
    async def extended_weather(message: Message, state: FSMContext) -> None:
        await handle_waiting_city(
            message,
            deps,
            FSMStateStore(state),
            extended=True,
        )
