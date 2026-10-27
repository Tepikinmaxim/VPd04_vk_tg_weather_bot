"""Справка Telegram-бота."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from weather_core.buttons import BTN_HELP
from weather_tg_bot.handlers.common import HELP_TEXT, TgDeps, show_main_menu
from weather_tg_bot.state import FSMStateStore


async def handle_help(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    await show_main_menu(message, deps, store, HELP_TEXT)


def register(router: Router, deps: TgDeps) -> None:
    @router.message(Command("help"))
    @router.message(F.text.in_({BTN_HELP, "help", "помощь"}))
    async def help_message(message: Message, state: FSMContext) -> None:
        await handle_help(message, deps, FSMStateStore(state))
