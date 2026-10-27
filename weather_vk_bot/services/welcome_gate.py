"""Защита от повторного приветствия при старте диалога."""

from __future__ import annotations

import time
from collections.abc import Callable

DEFAULT_COOLDOWN_SECONDS = 5.0


class WelcomeGate:
    """Не даёт отправить приветствие дважды подряд одному получателю."""

    def __init__(
        self,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._last_welcome: dict[int, float] = {}

    def claim(self, peer_id: int) -> bool:
        """Возвращает True, если приветствие можно отправить сейчас."""
        now = self._clock()
        last = self._last_welcome.get(peer_id)
        if last is not None and now - last < self._cooldown_seconds:
            return False
        self._last_welcome[peer_id] = now
        if len(self._last_welcome) > 10_000:
            cutoff = now - self._cooldown_seconds
            self._last_welcome = {
                key: value
                for key, value in self._last_welcome.items()
                if value >= cutoff
            }
        return True
