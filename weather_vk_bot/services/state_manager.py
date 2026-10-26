"""FSM-состояния и пользовательский контекст VK Weather Bot."""

from __future__ import annotations

from dataclasses import dataclass

from vkbottle import CtxStorage
from vkbottle.dispatch import ABCStateDispenser, BaseStateGroup, StatePeer


class BotState(BaseStateGroup):
    """Состояния диалога с пользователем."""

    MAIN_MENU = "main_menu"
    WAITING_CITY = "awaiting_city_weather"
    WAITING_FORECAST_CITY = "awaiting_city_forecast"
    WAITING_GEO = "waiting_geo"
    WAITING_EXTENDED = "awaiting_extended_city"


@dataclass(slots=True)
class UserContext:
    """Данные, которые пригодятся при расширении бота."""

    last_city: str | None = None
    last_mode: str | None = None


class StateManager:
    """Обёртка над StateDispenser и CtxStorage."""

    def __init__(
        self,
        dispenser: ABCStateDispenser,
        storage: CtxStorage | None = None,
    ) -> None:
        self._dispenser = dispenser
        self._storage = storage or CtxStorage()

    async def set_state(
        self,
        peer_id: int,
        state: BotState,
        **payload: object,
    ) -> None:
        await self._dispenser.set(peer_id, state, **payload)

    async def get_state(self, peer_id: int) -> StatePeer | None:
        return await self._dispenser.get(peer_id)

    async def reset(self, peer_id: int) -> None:
        await self._dispenser.set(peer_id, BotState.MAIN_MENU)

    def get_context(self, peer_id: int) -> UserContext:
        value = self._storage.get(peer_id)
        return value if isinstance(value, UserContext) else UserContext()

    def remember(
        self,
        peer_id: int,
        *,
        city: str | None = None,
        mode: str | None = None,
    ) -> None:
        context = self.get_context(peer_id)
        self._storage.set(
            peer_id,
            UserContext(
                last_city=city if city is not None else context.last_city,
                last_mode=mode if mode is not None else context.last_mode,
            ),
        )

    def clear_context(self, peer_id: int) -> None:
        self._storage.delete(peer_id)
