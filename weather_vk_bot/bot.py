"""Класс VKWeatherBot на high-level VKBottle."""

from __future__ import annotations

import logging
import ssl
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import certifi
from vkbottle import AiohttpClient, API, BaseMiddleware, BuiltinStateDispenser, CtxStorage
from vkbottle.bot import Bot, Message
from vkbottle.exception_factory import VKAPIError

from weather_vk_bot.handlers import register_handlers
from weather_vk_bot.handlers.common import HandlerDeps
from weather_vk_bot.services.state_manager import StateManager
from weather_vk_bot.services.weather_service import WeatherService

LOGGER = logging.getLogger(__name__)


class BotConfigError(Exception):
    """Ошибка конфигурации бота."""


class BotAuthError(Exception):
    """VK отклонил токен или доступ к сообществу."""


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
        self.deps = HandlerDeps(service=self.service, states=self.states)

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

    async def close(self) -> None:
        await self.api.http_client.close()

    def run(self) -> None:
        """Запускает Long Poll и закрывает HTTP-клиент при остановке."""
        self.bot.on_shutdown.append(self.close())
        self.bot.run()


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
    "LoggingMiddleware",
    "SSLAiohttpClient",
    "VKWeatherBot",
    "handle_vk_error",
)
