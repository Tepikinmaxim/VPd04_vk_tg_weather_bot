"""Сравнение текущей погоды в двух городах (Telegram)."""

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from weather_core.comparison import city_key, same_location, second_city_prompt
from weather_core.services.formatter import format_comparison, weather_city
from weather_tg_bot.handlers.common import (
    COMPARE_CITY_1_PROMPT,
    TgDeps,
    last_city,
    message_text,
    prompt_for_city,
    remember_city,
    reply_weather_error,
    send_text,
)
from weather_tg_bot.keyboards import main_menu_keyboard
from weather_tg_bot.state import FSMStateStore, TgState


async def prompt_for_second_city(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
    first_city: str,
    *,
    duplicate: bool = False,
) -> None:
    await store.set_state(TgState.WAITING_COMPARE_CITY_2)
    await store.update_data(first_city=first_city)
    await send_text(
        message,
        second_city_prompt(first_city, duplicate=duplicate),
        main_menu_keyboard(),
    )


async def first_city_from_state(store: FSMStateStore) -> str | None:
    data = await store.get_data()
    value = data.get("first_city")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return await last_city(store)


async def handle_compare_button(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    await remember_city(store, mode="compare")
    city = await last_city(store)
    if city:
        await prompt_for_second_city(message, deps, store, city)
        return
    await prompt_for_city(
        message,
        deps,
        store,
        TgState.WAITING_COMPARE_CITY_1,
        COMPARE_CITY_1_PROMPT,
    )


async def handle_compare_first_city(
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
            TgState.WAITING_COMPARE_CITY_1,
            COMPARE_CITY_1_PROMPT,
        )
        return
    await prompt_for_second_city(message, deps, store, city)


async def handle_compare_second_city(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    first_city = await first_city_from_state(store)
    if not first_city:
        await prompt_for_city(
            message,
            deps,
            store,
            TgState.WAITING_COMPARE_CITY_1,
            COMPARE_CITY_1_PROMPT,
        )
        return

    second_city = message_text(message)
    if not second_city:
        await prompt_for_second_city(message, deps, store, first_city)
        return

    if city_key(second_city) == city_key(first_city):
        await prompt_for_second_city(
            message,
            deps,
            store,
            first_city,
            duplicate=True,
        )
        return

    try:
        first_result, second_result = await asyncio.gather(
            deps.service.get_current(first_city),
            deps.service.get_current(second_city),
        )
    except Exception as exc:
        await reply_weather_error(message, exc)
        return

    if same_location(first_result, second_result):
        await prompt_for_second_city(
            message,
            deps,
            store,
            first_city,
            duplicate=True,
        )
        return

    await remember_city(
        store,
        city=weather_city(first_result) or first_city,
        mode="compare",
    )
    await send_text(
        message,
        format_comparison(first_result, second_result),
        main_menu_keyboard(),
    )
    await store.set_state(TgState.MAIN_MENU)


def register(router: Router, deps: TgDeps) -> None:
    from weather_core.buttons import BTN_COMPARE

    @router.message(F.text == BTN_COMPARE)
    async def compare_button(message: Message, state: FSMContext) -> None:
        await handle_compare_button(message, deps, FSMStateStore(state))

    @router.message(StateFilter(TgState.WAITING_COMPARE_CITY_1))
    async def compare_first_city(message: Message, state: FSMContext) -> None:
        await handle_compare_first_city(message, deps, FSMStateStore(state))

    @router.message(StateFilter(TgState.WAITING_COMPARE_CITY_2))
    async def compare_second_city(message: Message, state: FSMContext) -> None:
        await handle_compare_second_city(message, deps, FSMStateStore(state))
