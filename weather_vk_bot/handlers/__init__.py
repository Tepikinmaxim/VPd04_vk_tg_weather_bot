"""Регистрация всех handlers VK Weather Bot."""

from __future__ import annotations

from vkbottle.bot import Bot

from . import forecast, geo, help as help_handler, menu, weather
from .common import HandlerDeps


def register_handlers(bot: Bot, deps: HandlerDeps) -> None:
    menu.register(bot, deps)
    help_handler.register(bot, deps)
    weather.register(bot, deps)
    forecast.register(bot, deps)
    geo.register(bot, deps)
    menu.register_fallback(bot, deps)
