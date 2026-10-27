"""Telegram onboarding."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from weather_tg_bot.handlers.common import HELP_TEXT, TgDeps, show_main_menu
from weather_tg_bot.state import FSMStateStore


async def handle_start(
    message: Message,
    deps: TgDeps,
    store: FSMStateStore,
) -> None:
    await show_main_menu(message, deps, store, HELP_TEXT)


def register(router: Router, deps: TgDeps) -> None:
    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await handle_start(message, deps, FSMStateStore(state))
