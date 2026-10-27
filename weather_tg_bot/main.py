"""CLI-точка входа Telegram Weather Bot."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramUnauthorizedError,
)
from dotenv import load_dotenv

from weather_tg_bot.bot import (
    StartupDiagnostics,
    TgBotConfigError,
    TgBotStartupError,
    TgWeatherBot,
    format_startup_diagnostics,
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise TgBotConfigError(
            f"Не задан {name}. Откройте .env и вставьте значение в строку "
            f"{name}=."
        )
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Telegram Weather Bot на aiogram 3 и long polling.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Проверить токен и настройки Telegram без запуска polling.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Уровень логирования (по умолчанию INFO).",
    )
    return parser


async def _run_check(bot: TgWeatherBot) -> StartupDiagnostics:
    try:
        return await bot.diagnose()
    finally:
        await bot.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_dotenv(PROJECT_DIR / ".env")

    try:
        token = _required_env("TELEGRAM_BOT_TOKEN")
        _required_env("OPENWEATHER_API_KEY")
        bot = TgWeatherBot(token)

        if args.check:
            report = asyncio.run(_run_check(bot))
            print(format_startup_diagnostics(report))
            return 0 if report.ready else 1

        bot.run()
        return 0
    except TgBotConfigError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except TelegramUnauthorizedError:
        print(
            "Ошибка: Telegram отклонил токен. Проверьте TELEGRAM_BOT_TOKEN "
            "в .env.",
            file=sys.stderr,
        )
        return 1
    except TgBotStartupError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except TelegramNetworkError as exc:
        print(
            f"Ошибка сети Telegram: {exc}. Проверьте интернет.",
            file=sys.stderr,
        )
        return 1
    except TelegramAPIError as exc:
        print(f"Ошибка Telegram API: {exc}.", file=sys.stderr)
        return 1
    except (OSError, asyncio.TimeoutError) as exc:
        print(
            f"Ошибка сети Telegram: {exc}. Проверьте интернет.",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("\nБот остановлен.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
