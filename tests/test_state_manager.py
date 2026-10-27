import unittest

from vkbottle import CtxStorage
from vkbottle.dispatch import BuiltinStateDispenser

from weather_vk_bot.services.state_manager import (
    BotState,
    StateManager,
    UserContext,
)


class StateManagerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.manager = StateManager(
            BuiltinStateDispenser(),
            CtxStorage(force_reset=True),
        )

    async def test_set_get_and_reset_state(self) -> None:
        await self.manager.set_state(
            10,
            BotState.WAITING_CITY,
            city="Москва",
        )

        peer = await self.manager.get_state(10)
        self.assertIsNotNone(peer)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_CITY)
        self.assertEqual(peer.payload["city"], "Москва")

        await self.manager.reset(10)
        peer = await self.manager.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_missing_state_is_none(self) -> None:
        self.assertIsNone(await self.manager.get_state(999))

    async def test_context_remembers_city_and_mode(self) -> None:
        self.manager.remember(10, city="Москва")
        self.manager.remember(10, mode="extended")

        self.assertEqual(
            self.manager.get_context(10),
            UserContext(last_city="Москва", last_mode="extended"),
        )

    async def test_context_is_per_peer(self) -> None:
        self.manager.remember(10, city="Москва")
        self.manager.remember(20, city="Сочи")

        self.assertEqual(self.manager.get_context(10).last_city, "Москва")
        self.assertEqual(self.manager.get_context(20).last_city, "Сочи")

    async def test_clear_context(self) -> None:
        self.manager.remember(10, city="Москва")
        self.manager.clear_context(10)

        self.assertEqual(self.manager.get_context(10), UserContext())

    def test_state_values_match_requirements(self) -> None:
        self.assertEqual(BotState.MAIN_MENU.value, "main_menu")
        self.assertEqual(BotState.WAITING_CITY.value, "awaiting_city_weather")
        self.assertEqual(
            BotState.WAITING_FORECAST_CITY.value,
            "awaiting_city_forecast",
        )
        self.assertEqual(BotState.WAITING_GEO.value, "waiting_geo")
        self.assertEqual(
            BotState.WAITING_EXTENDED.value,
            "awaiting_extended_city",
        )
        self.assertEqual(
            BotState.WAITING_CHANGE_CITY.value,
            "awaiting_new_city",
        )
        self.assertEqual(
            BotState.WAITING_COMPARE_CITY_1.value,
            "awaiting_compare_city_1",
        )
        self.assertEqual(
            BotState.WAITING_COMPARE_CITY_2.value,
            "awaiting_compare_city_2",
        )


if __name__ == "__main__":
    unittest.main()
