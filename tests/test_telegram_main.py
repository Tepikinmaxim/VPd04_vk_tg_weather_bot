import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from weather_tg_bot.bot import DiagnosticCheck, StartupDiagnostics
from weather_tg_bot.main import main


class TelegramMainTests(unittest.TestCase):
    def test_missing_token_prints_variable_name(self) -> None:
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("weather_tg_bot.main.load_dotenv"),
            redirect_stderr(stderr),
        ):
            code = main([])

        self.assertEqual(code, 2)
        self.assertIn("TELEGRAM_BOT_TOKEN", stderr.getvalue())

    def test_check_requires_openweather_key(self) -> None:
        stderr = io.StringIO()
        with (
            patch.dict(
                os.environ,
                {"TELEGRAM_BOT_TOKEN": "token"},
                clear=True,
            ),
            patch("weather_tg_bot.main.load_dotenv"),
            redirect_stderr(stderr),
        ):
            code = main(["--check"])

        self.assertEqual(code, 2)
        self.assertIn("OPENWEATHER_API_KEY", stderr.getvalue())

    def test_check_returns_success(self) -> None:
        report = StartupDiagnostics(
            bot_id=1,
            username="weather_bot",
            checks=(
                DiagnosticCheck("Токен", True, "действителен"),
                DiagnosticCheck("Вебхук", True, "не установлен"),
            ),
        )
        bot = _FakeBot(report)
        stdout = io.StringIO()

        with (
            patch.dict(
                os.environ,
                {
                    "TELEGRAM_BOT_TOKEN": "token",
                    "OPENWEATHER_API_KEY": "key",
                },
                clear=True,
            ),
            patch("weather_tg_bot.main.load_dotenv"),
            patch("weather_tg_bot.main.TgWeatherBot", return_value=bot),
            redirect_stdout(stdout),
        ):
            code = main(["--check"])

        self.assertEqual(code, 0)
        self.assertIn("Проверка настроек Telegram", stdout.getvalue())
        self.assertIn("@weather_bot", stdout.getvalue())
        self.assertIn("Критические проверки пройдены", stdout.getvalue())

    def test_check_returns_error_for_blocking_problem(self) -> None:
        report = StartupDiagnostics(
            bot_id=1,
            username="weather_bot",
            checks=(
                DiagnosticCheck("OpenWeatherMap", False, "ключ не задан"),
            ),
        )
        bot = _FakeBot(report)
        stdout = io.StringIO()

        with (
            patch.dict(
                os.environ,
                {
                    "TELEGRAM_BOT_TOKEN": "token",
                    "OPENWEATHER_API_KEY": "key",
                },
                clear=True,
            ),
            patch("weather_tg_bot.main.load_dotenv"),
            patch("weather_tg_bot.main.TgWeatherBot", return_value=bot),
            redirect_stdout(stdout),
        ):
            code = main(["--check"])

        self.assertEqual(code, 1)
        self.assertIn("Есть критические проблемы", stdout.getvalue())


class _FakeBot:
    def __init__(self, report: StartupDiagnostics) -> None:
        self._report = report

    async def diagnose(self) -> StartupDiagnostics:
        return self._report

    async def close(self) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
