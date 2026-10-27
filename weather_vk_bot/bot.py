"""Класс VKWeatherBot на high-level VKBottle."""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import certifi
from vkbottle import AiohttpClient, API, BaseMiddleware, BuiltinStateDispenser, CtxStorage
from vkbottle.bot import Bot, Message
from vkbottle.exception_factory import VKAPIError

from weather_core.services.weather_service import WeatherService
from weather_vk_bot.handlers import register_handlers
from weather_vk_bot.handlers.common import HandlerDeps
from weather_vk_bot.services.state_manager import StateManager
from weather_vk_bot.services.welcome_gate import WelcomeGate

LOGGER = logging.getLogger(__name__)


class BotConfigError(Exception):
    """Ошибка конфигурации бота."""


class BotAuthError(Exception):
    """VK отклонил токен или доступ к сообществу."""


class BotStartupError(Exception):
    """Критические настройки VK не позволяют запустить бота."""


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    """Один пункт проверки настроек VK."""

    title: str
    ok: bool | None
    detail: str
    fix: str = ""
    blocking: bool = True


@dataclass(frozen=True, slots=True)
class StartupDiagnostics:
    """Результат проверки настроек сообщества."""

    group_id: int
    group_name: str
    checks: tuple[DiagnosticCheck, ...]

    @property
    def ready(self) -> bool:
        return all(
            check.ok is not False
            for check in self.checks
            if check.blocking
        )


def _response_payload(response: Any) -> Mapping[str, Any]:
    payload = response.get("response") if isinstance(response, Mapping) else None
    return payload if isinstance(payload, Mapping) else {}


def _error_label(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return f"VK API, код {code}" if code else type(exc).__name__


def format_startup_diagnostics(report: StartupDiagnostics) -> str:
    """Форматирует отчёт о настройках VK для терминала."""
    lines = [
        "🔎 Проверка настроек VK",
        "──────────────",
        f"👥 Сообщество: {report.group_name} (id {report.group_id})",
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
            "❌ Есть критические проблемы. "
            "Исправьте пункты выше и запустите бота снова."
        )
    return "\n".join(lines)


class LoggingMiddleware(BaseMiddleware[Message]):
    """Логирует факт обработки сообщения без его текста."""

    async def pre(self) -> None:
        self._started_at = time.perf_counter()  # type: ignore[attr-defined]
        state = self.event.state_peer.state if self.event.state_peer else "none"
        LOGGER.info(
            "Получено сообщение: peer_id=%s, state=%s",
            self.event.peer_id,
            state,
        )

    async def post(self) -> None:
        started_at = getattr(self, "_started_at", None)
        elapsed = time.perf_counter() - started_at if started_at else 0.0
        LOGGER.info(
            "Сообщение обработано: peer_id=%s, %.3f с",
            self.event.peer_id,
            elapsed,
        )


class SSLAiohttpClient(AiohttpClient):
    """Aiohttp-клиент с явным CA-контекстом для каждого запроса."""

    def __init__(self, context: ssl.SSLContext) -> None:
        super().__init__()
        self._ssl_context = context

    @asynccontextmanager
    async def request(
        self,
        url: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        kwargs.setdefault("ssl", self._ssl_context)
        async with super().request(url, method, data, **kwargs) as response:
            yield response


def _build_api(token: str) -> API:
    """Создаёт API с явными CA-сертификатами для macOS/venv."""
    context = ssl.create_default_context(cafile=certifi.where())
    return API(token, http_client=SSLAiohttpClient(context))


class VKWeatherBot:
    """Собирает Bot, handlers, FSM и сервис погоды."""

    def __init__(
        self,
        token: str,
        *,
        service: WeatherService | None = None,
        state_manager: StateManager | None = None,
        ctx_storage: CtxStorage | None = None,
        welcome_gate: WelcomeGate | None = None,
    ) -> None:
        token = token.strip()
        if not token:
            raise BotConfigError("Не задан VK_BOT_TOKEN.")

        self.api = _build_api(token)
        self.bot = Bot(
            api=self.api,
            state_dispenser=BuiltinStateDispenser(),
        )
        self.bot.labeler.vbml_ignore_case = True

        self.ctx_storage = ctx_storage or CtxStorage(force_reset=True)
        self.states = state_manager or StateManager(
            self.bot.state_dispenser,
            self.ctx_storage,
        )
        self.service = service or WeatherService()
        self.welcome_gate = welcome_gate or WelcomeGate()
        self.deps = HandlerDeps(
            service=self.service,
            states=self.states,
            welcome_gate=self.welcome_gate,
        )

        register_handlers(self.bot, self.deps)
        self.bot.labeler.message_view.register_middleware(LoggingMiddleware)
        self.bot.error_handler.register_undefined_error_handler(
            self._handle_unexpected_error
        )

    async def _handle_unexpected_error(self, error: Exception) -> None:
        LOGGER.error(
            "Необработанная ошибка VK Weather Bot: %s",
            type(error).__name__,
            exc_info=error,
        )

    async def check(self) -> tuple[int, str]:
        """Проверяет токен и возвращает ID и название сообщества."""
        response = await self.api.request("groups.getById", {})
        payload = response.get("response") if isinstance(response, Mapping) else None
        groups = payload.get("groups") if isinstance(payload, Mapping) else None
        if not isinstance(groups, list) or not groups:
            raise BotAuthError(
                "VK не вернул данные сообщества. Проверьте VK_BOT_TOKEN в .env."
            )

        group = groups[0]
        group_id = group.get("id") if isinstance(group, Mapping) else None
        if not isinstance(group_id, int):
            raise BotAuthError(
                "VK не вернул ID сообщества. Проверьте VK_BOT_TOKEN в .env."
            )
        name = group.get("name") if isinstance(group, Mapping) else None
        return group_id, str(name or "без названия")

    async def diagnose(self) -> StartupDiagnostics:
        """Проверяет доступные через API настройки сообщества."""
        group_id, group_name = await self.check()
        checks: list[DiagnosticCheck] = []

        try:
            response = await self.api.request("groups.getTokenPermissions", {})
            payload = _response_payload(response)
            raw_permissions = payload.get("permissions")
            permissions: set[str] = set()
            if isinstance(raw_permissions, list):
                permissions = {
                    str(item.get("name"))
                    for item in raw_permissions
                    if isinstance(item, Mapping)
                }
            has_messages = "messages" in permissions
            checks.append(
                DiagnosticCheck(
                    "Право messages",
                    has_messages,
                    "токен может работать с сообщениями"
                    if has_messages
                    else "в ключе нет права messages",
                    ""
                    if has_messages
                    else "Создайте ключ сообщества с правом messages: "
                    "Управление → Дополнительно → Работа с API → "
                    "Ключи доступа.",
                )
            )
        except Exception as exc:
            checks.append(
                DiagnosticCheck(
                    "Право messages",
                    False,
                    f"не удалось проверить ({_error_label(exc)})",
                    "Проверьте ключ сообщества и право messages в разделе "
                    "Управление → Дополнительно → Работа с API.",
                )
            )

        try:
            response = await self.api.request(
                "groups.getLongPollSettings",
                {"group_id": group_id},
            )
            payload = _response_payload(response)
            enabled = payload.get("is_enabled") is True
            checks.append(
                DiagnosticCheck(
                    "Long Poll API",
                    enabled,
                    "включён" if enabled else "выключен",
                    ""
                    if enabled
                    else "Включите Long Poll API: Управление → Дополнительно "
                    "→ Работа с API → Long Poll API.",
                )
            )

            events = payload.get("events")
            message_new = (
                isinstance(events, Mapping)
                and events.get("message_new") in (1, True)
            )
            checks.append(
                DiagnosticCheck(
                    "Событие message_new",
                    message_new,
                    "включено" if message_new else "выключено",
                    ""
                    if message_new
                    else "Включите событие «Входящие сообщения» "
                    "(message_new) в настройках Long Poll API.",
                )
            )

            message_allow = (
                isinstance(events, Mapping)
                and events.get("message_allow") in (1, True)
            )
            checks.append(
                DiagnosticCheck(
                    "Событие message_allow",
                    message_allow,
                    "включено" if message_allow else "выключено",
                    ""
                    if message_allow
                    else "Включите событие «Разрешение на отправку сообщений» "
                    "(message_allow) в настройках Long Poll API: "
                    "бот должен получать сигнал для автоматического "
                    "приветствия без /start.",
                )
            )
        except Exception as exc:
            checks.append(
                DiagnosticCheck(
                    "Long Poll API, message_new и message_allow",
                    False,
                    f"не удалось проверить ({_error_label(exc)})",
                    "Проверьте Long Poll API и события message_new, "
                    "message_allow: Управление → Дополнительно → Работа с API.",
                )
            )

        checks.append(
            DiagnosticCheck(
                "Возможности ботов и кнопка «Начать»",
                None,
                "проверяются только в интерфейсе VK",
                "Управление → Сообщения → Настройки для бота: включите "
                "«Возможности ботов» и «Добавить кнопку \"Начать\"». "
                "Если кнопки бота не видны в чате, в первую очередь "
                "проверьте «Возможности ботов».",
                blocking=False,
            )
        )

        return StartupDiagnostics(
            group_id=group_id,
            group_name=group_name,
            checks=tuple(checks),
        )

    async def close(self) -> None:
        await self.api.http_client.close()

    async def _run(self) -> None:
        try:
            report = await self.diagnose()
            print(format_startup_diagnostics(report), flush=True)
            if not report.ready:
                raise BotStartupError(
                    "Критические проверки VK не пройдены. "
                    "Исправьте пункты выше и запустите бота снова."
                )
            print("VK-бот запущен. Ожидаю события...", flush=True)
            await self.bot.run_polling()
        finally:
            await self.close()

    def run(self) -> None:
        """Проверяет настройки, запускает Long Poll и закрывает клиент."""
        asyncio.run(self._run())


def handle_vk_error(exc: VKAPIError) -> None:
    """Преобразует частые ошибки VK в понятное сообщение."""
    if exc.code in {5, 28}:
        raise BotAuthError(
            "VK отклонил токен или доступ к сообществу. "
            "Проверьте VK_BOT_TOKEN в .env."
        ) from exc
    LOGGER.error("Ошибка VK API, код %s", exc.code)


__all__ = (
    "BotAuthError",
    "BotConfigError",
    "BotStartupError",
    "DiagnosticCheck",
    "LoggingMiddleware",
    "SSLAiohttpClient",
    "StartupDiagnostics",
    "VKWeatherBot",
    "format_startup_diagnostics",
    "handle_vk_error",
)
