import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from weather_vk_bot.process_guard import (
    AlreadyRunningError,
    BotProcess,
    find_other_bot_processes,
    format_other_processes,
    single_instance_lock,
    terminate_processes,
)


class FindProcessTests(unittest.TestCase):
    def test_returns_only_other_project_bot_processes(self) -> None:
        project = Path("/tmp/weather-project").resolve()
        entries = [
            (100, os.getuid(), "/usr/bin/Python main.py"),
            (101, os.getuid(), "/usr/bin/Python main.py --check"),
            (102, os.getuid(), "/usr/bin/Python other.py"),
            (103, os.getuid() + 1, "/usr/bin/Python main.py"),
            (999, os.getuid(), "/usr/bin/Python main.py"),
        ]
        with (
            patch(
                "weather_vk_bot.process_guard._iter_process_entries",
                return_value=entries,
            ),
            patch(
                "weather_vk_bot.process_guard._process_cwd",
                return_value=project,
            ),
        ):
            found = find_other_bot_processes(project, current_pid=999)

        self.assertEqual([process.pid for process in found], [100])

    def test_ignores_process_from_another_directory(self) -> None:
        project = Path("/tmp/weather-project").resolve()
        with (
            patch(
                "weather_vk_bot.process_guard._iter_process_entries",
                return_value=[(100, os.getuid(), "/usr/bin/Python main.py")],
            ),
            patch(
                "weather_vk_bot.process_guard._process_cwd",
                return_value=Path("/tmp/other-project"),
            ),
        ):
            found = find_other_bot_processes(project, current_pid=999)

        self.assertEqual(found, [])

    def test_ignores_process_with_unknown_cwd(self) -> None:
        project = Path("/tmp/weather-project")
        with (
            patch(
                "weather_vk_bot.process_guard._iter_process_entries",
                return_value=[(100, os.getuid(), "/usr/bin/Python main.py")],
            ),
            patch(
                "weather_vk_bot.process_guard._process_cwd",
                return_value=None,
            ),
        ):
            found = find_other_bot_processes(project, current_pid=999)

        self.assertEqual(found, [])

    def test_formats_no_processes(self) -> None:
        self.assertIn("не найдено", format_other_processes([]))

    def test_formats_found_processes(self) -> None:
        text = format_other_processes(
            [BotProcess(1, os.getuid(), Path("/tmp"), "Python main.py")]
        )

        self.assertIn("PID 1", text)
        self.assertIn("будут остановлены автоматически", text)


class LockTests(unittest.TestCase):
    def test_second_acquire_is_rejected_and_lock_can_be_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bot.lock"

            with single_instance_lock(path):
                with self.assertRaises(AlreadyRunningError) as context:
                    with single_instance_lock(path):
                        pass
                self.assertEqual(context.exception.pid, os.getpid())

            with single_instance_lock(path):
                pass


class TerminateTests(unittest.TestCase):
    def test_missing_process_is_ignored(self) -> None:
        process = BotProcess(
            pid=999_999_999,
            uid=os.getuid(),
            cwd=Path("/tmp"),
            command="Python main.py",
        )

        terminated, failed = terminate_processes([process], timeout=0.1)

        self.assertEqual(terminated, [])
        self.assertEqual(failed, [])

    def test_terminates_real_project_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "main.py").write_text(
                "import time\ntime.sleep(30)\n",
                encoding="utf-8",
            )
            child = subprocess.Popen(
                [sys.executable, "main.py"],
                cwd=project,
            )
            try:
                found: list[BotProcess] = []
                for _ in range(30):
                    found = find_other_bot_processes(project)
                    if found:
                        break
                    time.sleep(0.1)

                self.assertTrue(found, "дочерний main.py не найден")
                terminated, failed = terminate_processes(found, timeout=3)

                self.assertIn(child.pid, terminated)
                self.assertEqual(failed, [])
                child.wait(timeout=3)
                self.assertIsNotNone(child.returncode)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()


if __name__ == "__main__":
    unittest.main()
