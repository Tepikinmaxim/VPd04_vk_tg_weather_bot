"""CLI-точка входа VK Weather Bot."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from vkbottle.exception_factory import VKAPIError

from weather_vk_bot.bot import (
    BotAuthError,
    BotConfigError,
    VKWeatherBot,
    handle_vk_error,
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise BotConfigError(
            f"Не задан {name}. Откройте .env и вставьте значение в строку {name}=."
        )
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VK Weather Bot на high-level VKBottle и Long Poll API.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить VK_BOT_TOKEN и доступ к сообществу без запуска Long Poll.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Уровень логирования (по умолчанию INFO).",
    )
    return parser


async def _run_check(bot: VKWeatherBot) -> tuple[int, str]:
    try:
        return await bot.check()
    finally:
        await bot.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_dotenv(PROJECT_DIR / ".env")

    bot: VKWeatherBot | None = None
    try:
        if args.check:
            token = _required_env("VK_BOT_TOKEN")
            bot = VKWeatherBot(token)
            group_id, name = asyncio.run(_run_check(bot))
            print(f"VK API доступен. Сообщество: {name} (id {group_id}).")
            return 0

        token = _required_env("VK_BOT_TOKEN")
        _required_env("OPENWEATHER_API_KEY")
        bot = VKWeatherBot(token)
        print("VK-бот запущен. Ожидаю сообщения...")
        bot.run()
        return 0
    except BotConfigError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except BotAuthError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except VKAPIError as exc:
        try:
            handle_vk_error(exc)
        except BotAuthError as auth_exc:
            print(f"Ошибка: {auth_exc}", file=sys.stderr)
            return 1
        print(f"Ошибка VK API: код {exc.code}.", file=sys.stderr)
        return 1
    except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as exc:
        print(
            f"Ошибка сети VK: {exc}. Проверьте интернет и SSL-сертификаты.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nБот остановлен.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
