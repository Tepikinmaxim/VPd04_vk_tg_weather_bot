#!/usr/bin/env python3
"""Low-level VK-бот погоды на vkbottle.

Точка входа использует ``API`` и ``BotPolling`` напрямую, без high-level
``Bot``/labeler. Токены читаются только из ``.env``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import ssl
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import aiohttp
import certifi
from dotenv import load_dotenv
from vkbottle import API, BotPolling, Keyboard, KeyboardButtonColor, Text
from vkbottle.exception_factory import VKAPIError
from vkbottle.http import AiohttpClient

from OpenWeatherAPI import (
    OpenWeatherAPI,
    OpenWeatherAPIError,
    format_result_text,
)

BASE_DIR = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 4000

WELCOME_TEXT = (
    "Я погодный бот. Введите город, например: Москва.\n"
    "Затем выберите вариант кнопками ниже."
)
HELP_TEXT = (
    "Как пользоваться ботом:\n"
    "1. Введите название города.\n"
    "2. Выберите «Погода сейчас», «Подробно» или «Прогноз на 5 дней».\n"
    "Кнопка «Другой город» сбрасывает выбранный город."
)
CITY_PROMPT = "Введите город."
MODE_PROMPT = "Сначала введите город, затем выберите вариант."

MODE_CURRENT = "current"
MODE_EXTENDED = "extended"
MODE_FORECAST = "forecast"

MODE_BY_TEXT = {
    "погода сейчас": MODE_CURRENT,
    "текущая погода": MODE_CURRENT,
    "подробно": MODE_EXTENDED,
    "расширенная погода": MODE_EXTENDED,
    "прогноз на 5 дней": MODE_FORECAST,
    "прогноз": MODE_FORECAST,
}

WeatherLoader = Callable[[str, str], Mapping[str, Any]]


class BotConfigError(Exception):
    """Ошибка конфигурации VK-бота."""


class BotAuthError(Exception):
    """VK отклонил токен или доступ к сообществу."""


@dataclass
class PeerState:
    city: str | None = None
    pending_mode: str | None = None


def build_keyboard() -> str:
    keyboard = Keyboard(one_time=False, inline=False)
    keyboard.add(Text("Погода сейчас"), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text("Подробно"), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text("Прогноз на 5 дней"), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    keyboard.add(Text("Другой город"), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Делит длинный текст на части, не разрывая строки без необходимости."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for line in text.splitlines():
        while len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_length = 0
            chunks.append(line[:limit])
            line = line[limit:]

        extra = len(line) + (1 if current else 0)
        if current and current_length + extra > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length += extra

    if current:
        chunks.append("\n".join(current))
    return chunks or [""]


def load_weather_sync(city: str, mode: str) -> Mapping[str, Any]:
    """Синхронно получает данные OpenWeatherMap для режима бота."""
    with OpenWeatherAPI() as api:
        if mode == MODE_FORECAST:
            return api.get_forecast_by_city(city)
        if mode == MODE_EXTENDED:
            return api.get_weather_by_city(city, extended=True)
        return api.get_weather_by_city(city)


class WeatherBot:
    """Обрабатывает обновления message_new через low-level API."""

    def __init__(
        self,
        api: Any,
        loader: WeatherLoader = load_weather_sync,
    ) -> None:
        self.api = api
        self.loader = loader
        self.states: dict[tuple[int, int], PeerState] = {}

    async def handle_update(self, update: Mapping[str, Any]) -> bool:
        if update.get("type") != "message_new":
            return False

        obj = update.get("object")
        if not isinstance(obj, Mapping):
            return False
        message = obj.get("message")
        if not isinstance(message, Mapping):
            return False
        if message.get("out") == 1:
            return False

        peer_id = message.get("peer_id")
        if not isinstance(peer_id, int):
            return False
        user_id = message.get("from_id")
        if not isinstance(user_id, int):
            user_id = 0
        text = message.get("text")
        if not isinstance(text, str):
            text = ""

        await self.handle_message(peer_id, user_id, text)
        LOGGER.info("Обработано message_new: peer_id=%s", peer_id)
        return True

    async def handle_message(
        self,
        peer_id: int,
        user_id: int,
        text: str,
    ) -> None:
        raw_text = text.strip()
        normalized = raw_text.lower().replace("ё", "е")
        key = (peer_id, user_id)
        state = self.states.setdefault(key, PeerState())

        if not raw_text:
            await self.send_text(peer_id, WELCOME_TEXT, build_keyboard())
            return

        if normalized in {"/start", "start", "начать"}:
            self.states[key] = PeerState()
            await self.send_text(peer_id, WELCOME_TEXT, build_keyboard())
            return

        if normalized in {"/help", "help", "помощь"}:
            await self.send_text(peer_id, HELP_TEXT, build_keyboard())
            return

        if normalized in {"/cancel", "cancel", "отмена"}:
            self.states[key] = PeerState()
            await self.send_text(peer_id, CITY_PROMPT, build_keyboard())
            return

        if normalized in {"другой город", "/city", "город"}:
            self.states[key] = PeerState()
            await self.send_text(peer_id, CITY_PROMPT, build_keyboard())
            return

        mode = MODE_BY_TEXT.get(normalized)
        if mode is not None:
            if state.city is None:
                state.pending_mode = mode
                await self.send_text(peer_id, MODE_PROMPT, build_keyboard())
                return
            await self.send_weather(peer_id, state.city, mode)
            return

        if raw_text.startswith("/"):
            await self.send_text(
                peer_id,
                "Неизвестная команда. Введите /help или название города.",
                build_keyboard(),
            )
            return

        state.city = raw_text
        if state.pending_mode is not None:
            mode = state.pending_mode
            state.pending_mode = None
            await self.send_weather(peer_id, state.city, mode)
            return

        await self.send_text(
            peer_id,
            f"Город: {state.city}\nВыберите вариант кнопками ниже.",
            build_keyboard(),
        )

    async def send_weather(self, peer_id: int, city: str, mode: str) -> None:
        try:
            result = await asyncio.to_thread(self.loader, city, mode)
            text = format_result_text(result).strip()
        except OpenWeatherAPIError as exc:
            await self.send_text(
                peer_id,
                f"Не удалось получить погоду: {exc}",
                build_keyboard(),
            )
            return
        except Exception:
            LOGGER.exception("Ошибка при получении погоды для %s", city)
            await self.send_text(
                peer_id,
                "Не удалось получить погоду. Попробуйте позже.",
                build_keyboard(),
            )
            return

        if not text:
            text = "Нет данных."
        await self.send_text(peer_id, text, build_keyboard())

    async def send_text(
        self,
        peer_id: int,
        text: str,
        keyboard: str | None = None,
    ) -> None:
        chunks = split_message(text)
        for index, chunk in enumerate(chunks):
            params: dict[str, Any] = {
                "peer_id": peer_id,
                "message": chunk,
                "random_id": secrets.randbits(31),
            }
            if keyboard is not None and index == len(chunks) - 1:
                params["keyboard"] = keyboard
            await self.api.messages.send(**params)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise BotConfigError(
            f"Не задан {name}. Откройте .env и вставьте значение в строку {name}=."
        )
    return value


def _parse_group_id(raw: str) -> int:
    value = raw.strip().rstrip("/")
    if not value:
        raise BotConfigError(
            "VK_GROUP_ID пуст. Укажите число, например 242611812, "
            "или короткий адрес club242611812 в .env."
        )

    lowered = value.lower()
    if "vk.com/" in lowered or "vk.ru/" in lowered:
        value = value.rsplit("/", 1)[-1]
        lowered = value.lower()

    for prefix in ("club", "public"):
        if lowered.startswith(prefix):
            digits = lowered[len(prefix):]
            if digits.isdigit():
                return int(digits)
            break

    try:
        group_id = int(value)
    except ValueError as exc:
        raise BotConfigError(
            "VK_GROUP_ID должен быть числом или коротким адресом вида "
            "club242611812. Проверьте строку VK_GROUP_ID= в .env."
        ) from exc

    return abs(group_id)


def _group_id_from_env() -> int | None:
    raw = os.getenv("VK_GROUP_ID", "").strip()
    if not raw:
        return None
    return _parse_group_id(raw)


def _handle_vk_error(exc: VKAPIError) -> None:
    if exc.code in {5, 28}:
        raise BotAuthError(
            "VK отклонил токен или доступ к сообществу. "
            "Проверьте VK_BOT_TOKEN и VK_GROUP_ID в .env."
        ) from exc
    LOGGER.error("Ошибка VK API, код %s", exc.code)


async def _fetch_group(api: API, group_id: int | None) -> tuple[int, str]:
    params = {} if group_id is None else {"group_id": group_id}
    response = await api.request("groups.getById", params)
    payload = response.get("response") if isinstance(response, Mapping) else None
    groups = payload.get("groups") if isinstance(payload, Mapping) else None
    if not isinstance(groups, list) or not groups:
        raise BotAuthError(
            "VK не вернул данные сообщества. Проверьте VK_BOT_TOKEN "
            "и VK_GROUP_ID в .env."
        )
    group = groups[0]
    resolved_id = group.get("id") if isinstance(group, Mapping) else None
    if not isinstance(resolved_id, int):
        raise BotAuthError(
            "VK не вернул ID сообщества. Проверьте VK_BOT_TOKEN "
            "и VK_GROUP_ID в .env."
        )
    name = group.get("name") if isinstance(group, Mapping) else None
    return resolved_id, str(name or "без названия")


async def _run_check(api: API, group_id: int | None) -> None:
    resolved_id, name = await _fetch_group(api, group_id)
    print(f"VK API доступен. Сообщество: {name} (id {resolved_id}).")


def _create_http_client() -> AiohttpClient:
    context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=context)
    return AiohttpClient(connector=connector)


async def _run_bot(
    token: str,
    group_id: int | None,
    *,
    check: bool = False,
    loader: WeatherLoader = load_weather_sync,
) -> None:
    http_client = _create_http_client()
    api = API(token, http_client=http_client)
    polling: BotPolling | None = None
    try:
        if check:
            await _run_check(api, group_id)
            return

        resolved_id, name = await _fetch_group(api, group_id)
        bot = WeatherBot(api, loader=loader)
        polling = BotPolling(api=api, group_id=resolved_id)
        print(
            f"VK API доступен. Сообщество: {name} (id {resolved_id})."
        )
        print("VK-бот запущен. Ожидаю сообщения...")
        try:
            async for event in polling.listen():
                updates = event.get("updates")
                if not isinstance(updates, list):
                    continue
                for update in updates:
                    try:
                        await bot.handle_update(update)
                    except VKAPIError as exc:
                        _handle_vk_error(exc)
                    except Exception:
                        LOGGER.exception("Не удалось обработать событие VK")
        except VKAPIError as exc:
            _handle_vk_error(exc)
    finally:
        if polling is not None:
            polling.stop()
        await http_client.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="VK-бот погоды на low-level API vkbottle.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить VK_BOT_TOKEN и VK_GROUP_ID без запуска Long Poll.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_dotenv(BASE_DIR / ".env")

    try:
        token = _required_env("VK_BOT_TOKEN")
        group_id = _group_id_from_env()
    except BotConfigError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    try:
        asyncio.run(_run_bot(token, group_id, check=args.check))
    except KeyboardInterrupt:
        print("\nБот остановлен.")
        return 0
    except BotConfigError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except BotAuthError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except VKAPIError as exc:
        print(
            f"Ошибка VK API: код {exc.code}. "
            "Проверьте VK_BOT_TOKEN и VK_GROUP_ID в .env.",
            file=sys.stderr,
        )
        return 1
    except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as exc:
        print(
            f"Ошибка сети VK: {exc}. Проверьте интернет и SSL-сертификаты.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
