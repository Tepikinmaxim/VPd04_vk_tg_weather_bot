"""Справка по использованию бота."""

from __future__ import annotations

from vkbottle.bot import Bot, Message

from weather_vk_bot.keyboards import BTN_HELP

from .common import HELP_TEXT, HandlerDeps, show_main_menu


def register(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message(text=[BTN_HELP, "/help", "help", "помощь"])
    async def help_message(message: Message) -> None:
        await show_main_menu(message, deps, HELP_TEXT)
