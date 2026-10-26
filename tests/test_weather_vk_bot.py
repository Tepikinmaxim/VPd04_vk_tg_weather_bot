import unittest
from typing import Any
from unittest.mock import AsyncMock

from vkbottle.dispatch import BuiltinStateDispenser

from OpenWeatherAPI import CityNotFoundError
from weather_vk_bot.bot import BotConfigError, SSLAiohttpClient, VKWeatherBot
from weather_vk_bot.services.state_manager import BotState, StateManager

CURRENT_RESULT: dict[str, Any] = {
    "location": {"name": "Москва"},
    "weather": {
        "description": "ясно",
        "temperature_c": 20.5,
        "feels_like_c": 19.8,
        "humidity_percent": 50.0,
        "wind_speed_ms": 2.0,
        "clouds_percent": 10.0,
    },
}

FORECAST_RESULT: dict[str, Any] = {
    "location": {"name": "Москва"},
    "forecast": [
        {
            "datetime": "2026-10-27 09:00:00",
            "description": "ясно",
            "temperature_c": 21.0,
        }
    ],
}


class FakeMessage:
    def __init__(
        self,
        text: str = "",
        *,
        peer_id: int = 10,
        geo: Any = None,
    ) -> None:
        self.text = text
        self.peer_id = peer_id
        self.geo = geo
        self.answers: list[dict[str, Any]] = []

    async def answer(self, message: str, **kwargs: Any) -> dict[str, Any]:
        self.answers.append({"text": message, **kwargs})
        return {"message_id": len(self.answers)}


class FakeWeatherService:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.error: Exception | None = None

    async def get_current(
        self,
        city: str,
        *,
        extended: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(("current", city, extended))
        if self.error:
            raise self.error
        return CURRENT_RESULT

    async def get_forecast(
        self,
        city: str,
        *,
        extended: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(("forecast", city, extended))
        if self.error:
            raise self.error
        return FORECAST_RESULT

    async def get_by_coordinates(
        self,
        lat: float,
        lon: float,
        *,
        extended: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(("coords", lat, lon, extended))
        if self.error:
            raise self.error
        return CURRENT_RESULT


def find_handler(bot: VKWeatherBot, name: str):
    for handler in bot.bot.labeler.message_view.handlers:
        if handler.handler.__name__ == name:
            return handler.handler
    raise AssertionError(f"Handler {name} not found")


class VKWeatherBotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = FakeWeatherService()
        self.bot = VKWeatherBot("test-token", service=self.service)

    async def test_empty_token_is_rejected(self) -> None:
        with self.assertRaises(BotConfigError):
            VKWeatherBot("   ")

    async def test_start_shows_main_menu(self) -> None:
        message = FakeMessage("/start")

        await find_handler(self.bot, "start")(message)

        self.assertIn("VK Weather Bot", message.answers[0]["text"])
        self.assertIn("keyboard", message.answers[0])
        peer = await self.bot.states.get_state(message.peer_id)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_weather_button_sets_waiting_state(self) -> None:
        message = FakeMessage("🌤 Погода сейчас")

        await find_handler(self.bot, "weather_button")(message)

        self.assertIn("Введите название города", message.answers[0]["text"])
        peer = await self.bot.states.get_state(message.peer_id)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_CITY)
        self.assertEqual(self.bot.states.get_context(message.peer_id).last_mode, "current")

    async def test_city_weather_flow_resets_state(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_CITY)
        message = FakeMessage("Москва")

        await find_handler(self.bot, "current_weather")(message)

        self.assertEqual(self.service.calls, [("current", "Москва", False)])
        self.assertIn("🌤 Погода сейчас", message.answers[-1]["text"])
        self.assertIn("Москва", message.answers[-1]["text"])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)
        self.assertEqual(self.bot.states.get_context(10).last_city, "Москва")

    async def test_extended_flow_passes_extended_flag(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_EXTENDED)
        message = FakeMessage("Сочи")

        await find_handler(self.bot, "extended_weather")(message)

        self.assertEqual(self.service.calls, [("current", "Сочи", True)])
        self.assertIn("Расширенная погода", message.answers[-1]["text"])

    async def test_forecast_flow(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_FORECAST_CITY)
        message = FakeMessage("Казань")

        await find_handler(self.bot, "forecast_by_city")(message)

        self.assertEqual(self.service.calls, [("forecast", "Казань", False)])
        self.assertIn("Прогноз на 5 дней", message.answers[-1]["text"])

    async def test_geo_flow_with_text_coordinates(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_GEO)
        message = FakeMessage("55.7558,37.6173")

        await find_handler(self.bot, "weather_by_geo")(message)

        self.assertEqual(
            self.service.calls,
            [("coords", 55.7558, 37.6173, False)],
        )
        self.assertIn("Погода сейчас", message.answers[-1]["text"])

    async def test_geo_flow_with_native_attachment(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_GEO)
        message = FakeMessage(
            "",
            geo={
                "coordinates": {
                    "latitude": 59.9343,
                    "longitude": 30.3351,
                }
            },
        )

        await find_handler(self.bot, "weather_by_geo")(message)

        self.assertEqual(
            self.service.calls,
            [("coords", 59.9343, 30.3351, False)],
        )

    async def test_invalid_coordinates_keep_state(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_GEO)
        message = FakeMessage("не координаты")

        await find_handler(self.bot, "weather_by_geo")(message)

        self.assertIn("Не удалось распознать", message.answers[-1]["text"])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_GEO)

    async def test_city_not_found_keeps_state(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_CITY)
        self.service.error = CityNotFoundError("Город не найден")
        message = FakeMessage("Неизвестный город")

        await find_handler(self.bot, "current_weather")(message)

        self.assertIn("Город не найден", message.answers[-1]["text"])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_CITY)

    async def test_empty_city_prompts_again(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_CITY)
        message = FakeMessage("   ")

        await find_handler(self.bot, "current_weather")(message)

        self.assertIn("Введите название города", message.answers[-1]["text"])
        self.assertEqual(self.service.calls, [])

    async def test_check_parses_group(self) -> None:
        self.bot.api.request = AsyncMock(  # type: ignore[method-assign]
            return_value={
                "response": {
                    "groups": [{"id": 242611812, "name": "Weather Bot"}]
                }
            }
        )

        group_id, name = await self.bot.check()

        self.assertEqual(group_id, 242611812)
        self.assertEqual(name, "Weather Bot")



class StateManagerFactoryTest(unittest.TestCase):
    def test_builtin_dispenser_can_be_wrapped(self) -> None:
        manager = StateManager(BuiltinStateDispenser())
        self.assertIsNotNone(manager)

    def test_handlers_are_blocking_and_fallback_is_last(self) -> None:
        bot = VKWeatherBot("test-token", service=FakeWeatherService())
        handlers = bot.bot.labeler.message_view.handlers

        self.assertTrue(all(handler.blocking for handler in handlers))
        self.assertEqual(handlers[-1].handler.__name__, "fallback")

    def test_ssl_is_passed_per_request_not_to_client_session(self) -> None:
        bot = VKWeatherBot("test-token", service=FakeWeatherService())
        client = bot.api.http_client

        self.assertIsInstance(client, SSLAiohttpClient)
        self.assertNotIn("ssl", client._session_params)
        self.assertIsNotNone(client._ssl_context)


if __name__ == "__main__":
    unittest.main()
