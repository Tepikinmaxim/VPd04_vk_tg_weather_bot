"""Регистрация handlers Telegram-бота."""

from __future__ import annotations

from aiogram import Router

from weather_tg_bot.handlers import (
    comparison,
    forecast,
    geo,
    help as help_handler,
    menu,
    onboarding,
    weather,
)
from weather_tg_bot.handlers.common import TgDeps


def register_handlers(router: Router, deps: TgDeps) -> None:
    onboarding.register(router, deps)
    geo.register_global(router, deps)
    menu.register(router, deps)
    help_handler.register(router, deps)
    comparison.register(router, deps)
    weather.register(router, deps)
    forecast.register(router, deps)
    geo.register_state(router, deps)
    menu.register_fallback(router, deps)


__all__ = ("register_handlers",)
