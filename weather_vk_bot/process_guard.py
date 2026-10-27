"""Защита от одновременного запуска нескольких экземпляров VK-бота."""

from __future__ import annotations

import fcntl
import logging
import os
import signal
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class AlreadyRunningError(Exception):
    """Текущий экземпляр бота уже удерживает lock."""

    def __init__(self, pid: int | None = None) -> None:
        self.pid = pid
        detail = f" (PID {pid})" if pid is not None else ""
        super().__init__(f"VK-бот уже запущен{detail}.")


@dataclass(frozen=True, slots=True)
class BotProcess:
    """Процесс ``main.py``, запущенный из каталога проекта."""

    pid: int
    uid: int
    cwd: Path
    command: str


def _iter_process_entries() -> list[tuple[int, int, str]]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,uid=,command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.warning("Не удалось получить список процессов: %s", exc)
        return []
    if result.returncode != 0:
        LOGGER.warning("ps завершился с кодом %s", result.returncode)
        return []

    entries: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            uid = int(parts[1])
        except ValueError:
            continue
        entries.append((pid, uid, parts[2]))
    return entries


def _process_cwd(pid: int) -> Path | None:
    try:
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.debug("Не удалось определить cwd для PID %s: %s", pid, exc)
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("n") and len(line) > 1:
            return Path(line[1:]).resolve()
    return None


def _is_main_process(command: str) -> bool:
    tokens = command.split()
    if not any(Path(token).name == "main.py" for token in tokens):
        return False
    return "--check" not in tokens


def find_other_bot_processes(
    project_dir: Path,
    *,
    current_pid: int | None = None,
) -> list[BotProcess]:
    """Находит другие экземпляры ``main.py`` этого проекта."""
    project = project_dir.resolve()
    current = os.getpid() if current_pid is None else current_pid
    uid = os.getuid()
    found: list[BotProcess] = []

    for pid, process_uid, command in _iter_process_entries():
        if pid == current or process_uid != uid:
            continue
        if not _is_main_process(command):
            continue
        cwd = _process_cwd(pid)
        if cwd is None or cwd != project:
            continue
        found.append(BotProcess(pid=pid, uid=process_uid, cwd=cwd, command=command))

    return sorted(found, key=lambda process: process.pid)


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_processes(
    processes: list[BotProcess],
    *,
    timeout: float = 5.0,
) -> tuple[list[int], list[int]]:
    """Останавливает процессы: сначала SIGTERM, затем SIGKILL."""
    terminated: list[int] = []
    failed: list[int] = []

    for process in processes:
        try:
            os.kill(process.pid, signal.SIGTERM)
            terminated.append(process.pid)
            LOGGER.info("Отправлен SIGTERM старому экземпляру: PID %s", process.pid)
        except ProcessLookupError:
            LOGGER.info("Процесс уже завершён: PID %s", process.pid)
        except PermissionError as exc:
            LOGGER.warning(
                "Нет прав остановить PID %s: %s",
                process.pid,
                exc,
            )
            failed.append(process.pid)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_is_alive(pid) for pid in terminated):
            break
        time.sleep(0.1)

    for pid in terminated:
        if not _is_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            LOGGER.info("Отправлен SIGKILL старому экземпляру: PID %s", pid)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            LOGGER.warning("Нет прав остановить PID %s: %s", pid, exc)
            failed.append(pid)

    return terminated, sorted(set(failed))


def format_other_processes(processes: list[BotProcess]) -> str:
    """Форматирует отчёт о найденных экземплярах для ``--check``."""
    if not processes:
        return "✅ Других экземпляров VK-бота не найдено."
    pids = ", ".join(str(process.pid) for process in processes)
    return (
        f"⚠️ Найдены другие экземпляры VK-бота: PID {pids}.\n"
        "   При обычном запуске старые экземпляры будут остановлены "
        "автоматически;\n"
        "   активный экземпляр с lock не затрагивается."
    )


@contextmanager
def single_instance_lock(path: Path) -> Iterator[None]:
    """Удерживает lock на время работы процесса."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.seek(0)
        raw_pid = handle.read().strip()
        pid = int(raw_pid) if raw_pid.isdigit() else None
        handle.close()
        raise AlreadyRunningError(pid) from exc

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    try:
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


__all__ = (
    "AlreadyRunningError",
    "BotProcess",
    "find_other_bot_processes",
    "format_other_processes",
    "single_instance_lock",
    "terminate_processes",
)
