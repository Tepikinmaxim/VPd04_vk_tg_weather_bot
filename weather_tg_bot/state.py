"""Состояния и адаптер FSM для Telegram-бота."""

from __future__ import annotations

from typing import Any, Protocol

from aiogram.fsm.context import FSMContext


class TgState:
    """Строковые состояния диалога Telegram."""

    MAIN_MENU = "tg_main_menu"
    WAITING_CITY = "tg_waiting_city"
    WAITING_FORECAST_CITY = "tg_waiting_forecast_city"
    WAITING_GEO = "tg_waiting_geo"
    WAITING_EXTENDED = "tg_waiting_extended"
    WAITING_CHANGE_CITY = "tg_waiting_change_city"
    WAITING_COMPARE_CITY_1 = "tg_waiting_compare_city_1"
    WAITING_COMPARE_CITY_2 = "tg_waiting_compare_city_2"


class StateStore(Protocol):
    async def get_state(self) -> str | None: ...

    async def set_state(self, state: str | None) -> None: ...

    async def get_data(self) -> dict[str, Any]: ...

    async def update_data(self, **kwargs: Any) -> None: ...


class FSMStateStore:
    """Обёртка над ``FSMContext`` для тестируемых сценариев."""

    def __init__(self, context: FSMContext) -> None:
        self._context = context

    async def get_state(self) -> str | None:
        state = await self._context.get_state()
        return state if isinstance(state, str) else None

    async def set_state(self, state: str | None) -> None:
        await self._context.set_state(state)

    async def get_data(self) -> dict[str, Any]:
        return await self._context.get_data()

    async def update_data(self, **kwargs: Any) -> None:
        await self._context.update_data(**kwargs)


__all__ = ("FSMStateStore", "StateStore", "TgState")
