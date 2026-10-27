"""Главное меню и общие команды Telegram."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from weather_core.buttons import (
    BTN_BACK,
    BTN_CHANGE_CITY,
    BTN_EXTENDED,
    BTN_FORECAST,
    BTN_GEO,
    BTN_WEATHER,
)
from weather_tg_bot.handlers.common import (
    CHANGE_CITY_PROMPT,
    CITY_PROMPT,
    EXTENDED_CITY_PROMPT,
    FORECAST_CITY_PROMPT,
    GEO_PROMPT,
    UNKNOWN_TEXT,
    WELCOME_TEXT,
    TgDeps,
    last_city,
    message_text,
    prompt_for_city,
    remember_city,
    send_text,
    show_main_menu,
)
from weather_tg_bot.handlers.forecast import show_forecast
from weather_tg_bot.handlers.weather import show_current_weather
from weather_tg_bot.keyboards import geo_keyboard
from weather_tg_bot.state import FSMStateStore, TgState


async def handle_weather_button(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    await remember_city(store, mode="current")
    city = await last_city(store)
    if city:
        await show_current_weather(message, deps, store, city)
        return
    await prompt_for_city(
        message,
        deps,
        store,
        TgState.WAITING_CITY,
        CITY_PROMPT,
    )


async def handle_forecast_button(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    await remember_city(store, mode="forecast")
    city = await last_city(store)
    if city:
        await show_forecast(message, deps, store, city)
        return
    await prompt_for_city(
        message,
        deps,
        store,
        TgState.WAITING_FORECAST_CITY,
        FORECAST_CITY_PROMPT,
    )


async def handle_extended_button(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    await remember_city(store, mode="extended")
    city = await last_city(store)
    if city:
        await show_current_weather(
            message,
            deps,
            store,
            city,
            extended=True,
        )
        return
    await prompt_for_city(
        message,
        deps,
        store,
        TgState.WAITING_EXTENDED,
        EXTENDED_CITY_PROMPT,
    )


async def handle_geo_button(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    await store.set_state(TgState.WAITING_GEO)
    await send_text(message, GEO_PROMPT, geo_keyboard())


async def handle_change_city_button(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    await prompt_for_city(
        message,
        deps,
        store,
        TgState.WAITING_CHANGE_CITY,
        CHANGE_CITY_PROMPT,
    )


async def handle_save_new_city(
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
            TgState.WAITING_CHANGE_CITY,
            CHANGE_CITY_PROMPT,
        )
        return

    await remember_city(store, city=city)
    await show_main_menu(
        message,
        deps,
        store,
        "✅ Новый город сохранён.",
    )


def register(router: Router, deps: TgDeps) -> None:
    @router.message(F.text == BTN_WEATHER)
    async def weather_button(message: Message, state: FSMContext) -> None:
        await handle_weather_button(message, deps, FSMStateStore(state))

    @router.message(F.text == BTN_FORECAST)
    async def forecast_button(message: Message, state: FSMContext) -> None:
        await handle_forecast_button(message, deps, FSMStateStore(state))

    @router.message(F.text == BTN_EXTENDED)
    async def extended_button(message: Message, state: FSMContext) -> None:
        await handle_extended_button(message, deps, FSMStateStore(state))

    @router.message(F.text == BTN_GEO)
    async def geo_button(message: Message, state: FSMContext) -> None:
        await handle_geo_button(message, deps, FSMStateStore(state))

    @router.message(F.text == BTN_CHANGE_CITY)
    async def change_city_button(message: Message, state: FSMContext) -> None:
        await handle_change_city_button(
            message,
            deps,
            FSMStateStore(state),
        )

    @router.message(F.text == BTN_BACK)
    async def back_button(message: Message, state: FSMContext) -> None:
        await show_main_menu(message, deps, FSMStateStore(state))

    @router.message(Command("cancel"))
    @router.message(F.text.in_({"cancel", "отмена"}))
    async def cancel(message: Message, state: FSMContext) -> None:
        await show_main_menu(message, deps, FSMStateStore(state))

    @router.message(StateFilter(TgState.WAITING_CHANGE_CITY))
    async def save_new_city(message: Message, state: FSMContext) -> None:
        await handle_save_new_city(message, deps, FSMStateStore(state))


def register_fallback(router: Router, deps: TgDeps) -> None:
    @router.message()
    async def fallback(message: Message, state: FSMContext) -> None:
        text = message_text(message)
        await show_main_menu(
            message,
            deps,
            FSMStateStore(state),
            WELCOME_TEXT if not text else UNKNOWN_TEXT,
        )
