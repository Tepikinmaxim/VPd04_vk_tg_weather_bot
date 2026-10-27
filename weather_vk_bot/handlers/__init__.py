"""Регистрация всех handlers VK Weather Bot."""

from __future__ import annotations

from vkbottle.bot import Bot

from . import comparison, forecast, geo, help as help_handler, menu, onboarding, weather
from .common import HandlerDeps


def register_handlers(bot: Bot, deps: HandlerDeps) -> None:
    onboarding.register(bot, deps)
    geo.register_global(bot, deps)
    menu.register(bot, deps)
    help_handler.register(bot, deps)
    weather.register(bot, deps)
    forecast.register(bot, deps)
    comparison.register(bot, deps)
    geo.register_state(bot, deps)
    menu.register_fallback(bot, deps)
