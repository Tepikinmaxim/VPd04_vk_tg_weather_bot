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
    BotStartupError,
    StartupDiagnostics,
    VKWeatherBot,
    format_startup_diagnostics,
    handle_vk_error,
)
from weather_vk_bot.process_guard import (
    AlreadyRunningError,
    find_other_bot_processes,
    format_other_processes,
    single_instance_lock,
    terminate_processes,
)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
LOCK_PATH = PROJECT_DIR / ".vkbottle" / "vk_bot.lock"


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
        help="Проверить токен, права и настройки Long Poll без запуска бота.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help="Уровень логирования (по умолчанию INFO).",
    )
    parser.add_argument(
        "--no-kill-stale",
        action="store_true",
        help=(
            "Не останавливать другие экземпляры VK-бота, "
            "а завершиться с ошибкой."
        ),
    )
    return parser


async def _run_check(bot: VKWeatherBot) -> StartupDiagnostics:
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

    bot: VKWeatherBot | None = None
    try:
        if args.check:
            token = _required_env("VK_BOT_TOKEN")
            bot = VKWeatherBot(token)
            report = asyncio.run(_run_check(bot))
            print(format_startup_diagnostics(report))
            print(format_other_processes(find_other_bot_processes(PROJECT_DIR)))
            return 0 if report.ready else 1

        token = _required_env("VK_BOT_TOKEN")
        _required_env("OPENWEATHER_API_KEY")
        with single_instance_lock(LOCK_PATH):
            duplicates = find_other_bot_processes(PROJECT_DIR)
            if duplicates:
                if args.no_kill_stale:
                    pids = ", ".join(str(item.pid) for item in duplicates)
                    raise BotStartupError(
                        "Найдены другие экземпляры VK-бота: "
                        f"PID {pids}. Остановите их или запустите без "
                        "--no-kill-stale."
                    )
                terminated, failed = terminate_processes(duplicates)
                if terminated:
                    pids = ", ".join(str(pid) for pid in terminated)
                    print(
                        f"Остановлены старые экземпляры VK-бота: PID {pids}.",
                        flush=True,
                    )
                if failed:
                    pids = ", ".join(str(pid) for pid in failed)
                    raise BotStartupError(
                        f"Не удалось остановить экземпляры VK-бота: PID {pids}."
                    )

            bot = VKWeatherBot(token)
            bot.run()
        return 0
    except AlreadyRunningError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except BotConfigError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except BotAuthError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    except BotStartupError as exc:
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
