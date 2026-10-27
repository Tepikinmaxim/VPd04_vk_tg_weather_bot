import io
import os
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from weather_vk_bot.bot import DiagnosticCheck, StartupDiagnostics
from weather_vk_bot.main import main
from weather_vk_bot.process_guard import AlreadyRunningError, BotProcess


class MainTests(unittest.TestCase):
    def test_missing_token_prints_variable_name(self) -> None:
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("weather_vk_bot.main.load_dotenv"),
            redirect_stderr(stderr),
        ):
            code = main([])

        self.assertEqual(code, 2)
        self.assertIn("VK_BOT_TOKEN", stderr.getvalue())

    def test_check_requires_token_before_network(self) -> None:
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("weather_vk_bot.main.load_dotenv"),
            redirect_stderr(stderr),
        ):
            code = main(["--check"])

        self.assertEqual(code, 2)
        self.assertIn("VK_BOT_TOKEN", stderr.getvalue())

    def test_check_returns_success_for_ready_settings(self) -> None:
        report = StartupDiagnostics(
            group_id=1,
            group_name="Weather Bot",
            checks=(
                DiagnosticCheck("Право messages", True, "есть"),
                DiagnosticCheck("Возможности ботов", None, "вручную", blocking=False),
            ),
        )
        bot = _FakeBot(report)
        stdout = io.StringIO()

        with (
            patch.dict(os.environ, {"VK_BOT_TOKEN": "token"}, clear=True),
            patch("weather_vk_bot.main.load_dotenv"),
            patch("weather_vk_bot.main.VKWeatherBot", return_value=bot),
            patch("weather_vk_bot.main.find_other_bot_processes", return_value=[]),
            redirect_stdout(stdout),
        ):
            code = main(["--check"])

        self.assertEqual(code, 0)
        self.assertIn("Проверка настроек VK", stdout.getvalue())
        self.assertIn("Критические проверки пройдены", stdout.getvalue())
        self.assertIn("Других экземпляров VK-бота не найдено", stdout.getvalue())

    def test_check_returns_error_for_blocking_problem(self) -> None:
        report = StartupDiagnostics(
            group_id=1,
            group_name="Weather Bot",
            checks=(
                DiagnosticCheck("Право messages", False, "нет", "исправить"),
            ),
        )
        bot = _FakeBot(report)
        stdout = io.StringIO()

        with (
            patch.dict(os.environ, {"VK_BOT_TOKEN": "token"}, clear=True),
            patch("weather_vk_bot.main.load_dotenv"),
            patch("weather_vk_bot.main.VKWeatherBot", return_value=bot),
            patch("weather_vk_bot.main.find_other_bot_processes", return_value=[]),
            redirect_stdout(stdout),
        ):
            code = main(["--check"])

        self.assertEqual(code, 1)
        self.assertIn("❌ Право messages", stdout.getvalue())
        self.assertIn("Есть критические проблемы", stdout.getvalue())


    def test_check_reports_other_instances(self) -> None:
        report = StartupDiagnostics(
            group_id=1,
            group_name="Weather Bot",
            checks=(DiagnosticCheck("Право messages", True, "есть"),),
        )
        bot = _FakeBot(report)
        stale = BotProcess(
            pid=123,
            uid=os.getuid(),
            cwd=Path("/tmp"),
            command="Python main.py",
        )
        stdout = io.StringIO()

        with (
            patch.dict(os.environ, {"VK_BOT_TOKEN": "token"}, clear=True),
            patch("weather_vk_bot.main.load_dotenv"),
            patch("weather_vk_bot.main.VKWeatherBot", return_value=bot),
            patch(
                "weather_vk_bot.main.find_other_bot_processes",
                return_value=[stale],
            ),
            redirect_stdout(stdout),
        ):
            code = main(["--check"])

        self.assertEqual(code, 0)
        self.assertIn("PID 123", stdout.getvalue())
        self.assertIn("будут остановлены автоматически", stdout.getvalue())

    def test_start_stops_stale_instances(self) -> None:
        stale = BotProcess(
            pid=123,
            uid=os.getuid(),
            cwd=Path("/tmp"),
            command="Python main.py",
        )
        bot = _FakeRunBot()
        stdout = io.StringIO()

        with (
            patch.dict(
                os.environ,
                {
                    "VK_BOT_TOKEN": "token",
                    "OPENWEATHER_API_KEY": "key",
                },
                clear=True,
            ),
            patch("weather_vk_bot.main.load_dotenv"),
            patch(
                "weather_vk_bot.main.single_instance_lock",
                return_value=nullcontext(),
            ),
            patch(
                "weather_vk_bot.main.find_other_bot_processes",
                return_value=[stale],
            ),
            patch(
                "weather_vk_bot.main.terminate_processes",
                return_value=([123], []),
            ) as terminate,
            patch("weather_vk_bot.main.VKWeatherBot", return_value=bot),
            redirect_stdout(stdout),
        ):
            code = main([])

        self.assertEqual(code, 0)
        self.assertTrue(bot.ran)
        terminate.assert_called_once_with([stale])
        self.assertIn("Остановлены старые экземпляры", stdout.getvalue())
        self.assertIn("PID 123", stdout.getvalue())

    def test_start_with_no_kill_stale_returns_error(self) -> None:
        stale = BotProcess(
            pid=123,
            uid=os.getuid(),
            cwd=Path("/tmp"),
            command="Python main.py",
        )
        stderr = io.StringIO()

        with (
            patch.dict(
                os.environ,
                {
                    "VK_BOT_TOKEN": "token",
                    "OPENWEATHER_API_KEY": "key",
                },
                clear=True,
            ),
            patch("weather_vk_bot.main.load_dotenv"),
            patch(
                "weather_vk_bot.main.single_instance_lock",
                return_value=nullcontext(),
            ),
            patch(
                "weather_vk_bot.main.find_other_bot_processes",
                return_value=[stale],
            ),
            patch("weather_vk_bot.main.terminate_processes") as terminate,
            redirect_stderr(stderr),
        ):
            code = main(["--no-kill-stale"])

        self.assertEqual(code, 1)
        terminate.assert_not_called()
        self.assertIn("Найдены другие экземпляры VK-бота", stderr.getvalue())
        self.assertIn("PID 123", stderr.getvalue())

    def test_start_returns_error_when_already_running(self) -> None:
        stderr = io.StringIO()

        with (
            patch.dict(
                os.environ,
                {
                    "VK_BOT_TOKEN": "token",
                    "OPENWEATHER_API_KEY": "key",
                },
                clear=True,
            ),
            patch("weather_vk_bot.main.load_dotenv"),
            patch(
                "weather_vk_bot.main.single_instance_lock",
                side_effect=AlreadyRunningError(555),
            ),
            redirect_stderr(stderr),
        ):
            code = main([])

        self.assertEqual(code, 1)
        self.assertIn("VK-бот уже запущен", stderr.getvalue())
        self.assertIn("PID 555", stderr.getvalue())

    def test_start_returns_error_when_stale_not_stopped(self) -> None:
        stale = BotProcess(
            pid=123,
            uid=os.getuid(),
            cwd=Path("/tmp"),
            command="Python main.py",
        )
        stderr = io.StringIO()

        with (
            patch.dict(
                os.environ,
                {
                    "VK_BOT_TOKEN": "token",
                    "OPENWEATHER_API_KEY": "key",
                },
                clear=True,
            ),
            patch("weather_vk_bot.main.load_dotenv"),
            patch(
                "weather_vk_bot.main.single_instance_lock",
                return_value=nullcontext(),
            ),
            patch(
                "weather_vk_bot.main.find_other_bot_processes",
                return_value=[stale],
            ),
            patch(
                "weather_vk_bot.main.terminate_processes",
                return_value=([], [123]),
            ),
            redirect_stderr(stderr),
        ):
            code = main([])

        self.assertEqual(code, 1)
        self.assertIn("Не удалось остановить", stderr.getvalue())
        self.assertIn("PID 123", stderr.getvalue())


class _FakeBot:
    def __init__(self, report: StartupDiagnostics) -> None:
        self._report = report

    async def diagnose(self) -> StartupDiagnostics:
        return self._report

    async def close(self) -> None:
        return None


class _FakeRunBot:
    def __init__(self) -> None:
        self.ran = False

    def run(self) -> None:
        self.ran = True


if __name__ == "__main__":
    unittest.main()
