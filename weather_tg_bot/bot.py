"""Класс Telegram-бота на aiogram 3."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, Message

from weather_core.services.weather_service import WeatherService
from weather_tg_bot.handlers import register_handlers
from weather_tg_bot.handlers.common import TgDeps

LOGGER = logging.getLogger(__name__)


class TgBotConfigError(Exception):
    """Ошибка конфигурации Telegram-бота."""


class TgBotStartupError(Exception):
    """Критические проверки не позволяют запустить бота."""


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    title: str
    ok: bool | None
    detail: str
    fix: str = ""
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class StartupDiagnostics:
    bot_id: int
    username: str
    checks: tuple[DiagnosticCheck, ...]

    @property
    def ready(self) -> bool:
        return all(
            check.ok is not False
            for check in self.checks
            if check.blocking
        )


def format_startup_diagnostics(report: StartupDiagnostics) -> str:
    lines = [
        "🔎 Проверка настроек Telegram",
        "──────────────",
        f"🤖 Бот: @{report.username} (id {report.bot_id})",
        "──────────────",
    ]
    for check in report.checks:
        if check.ok is True:
            icon = "✅"
        elif check.ok is False:
            icon = "❌"
        else:
            icon = "⚠️"
        lines.append(f"{icon} {check.title}: {check.detail}")
        if check.fix:
            lines.append(f"   ↳ {check.fix}")

    lines.append("──────────────")
    if report.ready:
        lines.append("✅ Критические проверки пройдены.")
    else:
        lines.append(
            "❌ Есть критические проблемы. Исправьте пункты выше и запустите "
            "бота снова."
        )
    return "\n".join(lines)


class LoggingMiddleware(BaseMiddleware):
    """Логирует обработку сообщений без их текста."""

    async def __call__(
        self,
        handler: Any,
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        started_at = time.perf_counter()
        chat_id = getattr(getattr(event, "chat", None), "id", None)
        LOGGER.info("Получено сообщение: chat_id=%s", chat_id)
        try:
            return await handler(event, data)
        finally:
            elapsed = time.perf_counter() - started_at
            LOGGER.info(
                "Сообщение обработано: chat_id=%s, %.3f с",
                chat_id,
                elapsed,
            )


class TgWeatherBot:
    """Собирает Bot, Dispatcher, handlers и сервис погоды."""

    def __init__(
        self,
        token: str,
        *,
        service: WeatherService | None = None,
    ) -> None:
        token = token.strip()
        if not token:
            raise TgBotConfigError("Не задан TELEGRAM_BOT_TOKEN.")

        self.bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=None),
        )
        self.dp = Dispatcher(storage=MemoryStorage())
        self.service = service or WeatherService()
        self.deps = TgDeps(service=self.service)

        router = Router()
        register_handlers(router, self.deps)
        self.dp.include_router(router)
        self.dp.message.outer_middleware(LoggingMiddleware())
        self.dp.errors.register(self._handle_unexpected_error)

    async def _handle_unexpected_error(self, event: ErrorEvent) -> None:
        LOGGER.error(
            "Необработанная ошибка Telegram-бота: %s",
            type(event.exception).__name__,
            exc_info=event.exception,
        )

    async def check(self) -> tuple[int, str]:
        me = await self.bot.get_me()
        username = me.username or me.first_name or "без имени"
        return me.id, username

    async def diagnose(self) -> StartupDiagnostics:
        bot_id, username = await self.check()
        checks: list[DiagnosticCheck] = [
            DiagnosticCheck("Токен", True, f"действителен для @{username}"),
        ]

        try:
            webhook = await self.bot.get_webhook_info()
            url = (webhook.url or "").strip()
            checks.append(
                DiagnosticCheck(
                    "Вебхук",
                    not url,
                    "не установлен, polling доступен"
                    if not url
                    else f"установлен: {url}",
                    ""
                    if not url
                    else "Удалите вебхук, иначе polling не будет получать "
                    "обновления.",
                    blocking=False,
                )
            )
        except Exception as exc:
            checks.append(
                DiagnosticCheck(
                    "Вебхук",
                    False,
                    f"не удалось проверить ({type(exc).__name__})",
                    "Проверьте доступ к Telegram API.",
                    blocking=False,
                )
            )

        has_openweather = bool(os.getenv("OPENWEATHER_API_KEY", "").strip())
        checks.append(
            DiagnosticCheck(
                "OpenWeatherMap",
                has_openweather,
                "ключ задан" if has_openweather else "ключ не задан",
                ""
                if has_openweather
                else "Укажите OPENWEATHER_API_KEY в .env.",
            )
        )

        return StartupDiagnostics(
            bot_id=bot_id,
            username=username,
            checks=tuple(checks),
        )

    async def close(self) -> None:
        await self.bot.session.close()

    async def _run(self) -> None:
        try:
            report = await self.diagnose()
            print(format_startup_diagnostics(report), flush=True)
            if not report.ready:
                raise TgBotStartupError(
                    "Критические проверки Telegram не пройдены. "
                    "Исправьте пункты выше и запустите бота снова."
                )
            print("Telegram-бот запущен. Ожидаю события...", flush=True)
            await self.dp.start_polling(
                self.bot,
                drop_pending_updates=True,
            )
        finally:
            await self.close()

    def run(self) -> None:
        asyncio.run(self._run())


__all__ = (
    "DiagnosticCheck",
    "StartupDiagnostics",
    "TgBotConfigError",
    "TgBotStartupError",
    "TgWeatherBot",
    "format_startup_diagnostics",
)
