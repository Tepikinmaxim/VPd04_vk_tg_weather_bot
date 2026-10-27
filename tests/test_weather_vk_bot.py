import unittest
from typing import Any
from unittest.mock import AsyncMock

from vkbottle.dispatch import BuiltinStateDispenser

from OpenWeatherAPI import CityNotFoundError
from weather_vk_bot.bot import (
    BotConfigError,
    SSLAiohttpClient,
    VKWeatherBot,
    format_startup_diagnostics,
)
from weather_vk_bot.handlers.common import HELP_TEXT
from weather_vk_bot.keyboards import geo_keyboard, main_menu_keyboard
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
        self.coords_result: dict[str, Any] = {
            **CURRENT_RESULT,
            "location": {"name": "Санкт-Петербург"},
        }
        self.city_aliases: dict[str, str] = {}
        self.city_coordinates: dict[str, tuple[float, float]] = {}

    def _with_city(self, result: dict[str, Any], city: str) -> dict[str, Any]:
        location = {
            **result.get("location", {}),
            "name": self.city_aliases.get(city, city),
        }
        coordinates = self.city_coordinates.get(city)
        if coordinates is not None:
            location["lat"], location["lon"] = coordinates
        return {**result, "location": location}

    async def get_current(
        self,
        city: str,
        *,
        extended: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(("current", city, extended))
        if self.error:
            raise self.error
        return self._with_city(CURRENT_RESULT, city)

    async def get_forecast(
        self,
        city: str,
        *,
        extended: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(("forecast", city, extended))
        if self.error:
            raise self.error
        return self._with_city(FORECAST_RESULT, city)

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
        return self.coords_result


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

        self.assertEqual(message.answers[0]["text"], HELP_TEXT)
        self.assertIn("Погодный эксперт", message.answers[0]["text"])
        self.assertIn("ℹ️ Что могу", message.answers[0]["text"])
        self.assertIn("keyboard", message.answers[0])
        peer = await self.bot.states.get_state(message.peer_id)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_help_matches_first_message(self) -> None:
        start_message = FakeMessage("/start")
        await find_handler(self.bot, "start")(start_message)
        help_message = FakeMessage("ℹ️ Помощь")

        await find_handler(self.bot, "help_message")(help_message)

        self.assertEqual(
            help_message.answers[-1]["text"],
            start_message.answers[0]["text"],
        )
        self.assertEqual(help_message.answers[-1]["text"], HELP_TEXT)
        self.assertIn(
            "📅 Прогноз 5 дней — прогноз на 12:00 MSK каждого из 5 дней.",
            HELP_TEXT,
        )
        self.assertIn(
            "Если город ещё не выбран, бот попросит его ввести.",
            HELP_TEXT,
        )
        self.assertIn(
            "Принимает и название города и  Координаты в формате:  "
            "55.7558, 37.6173 или 55.7558 37.6173.",
            HELP_TEXT,
        )
        self.assertIn("Координаты можно отправить в любой момент", HELP_TEXT)
        self.assertNotIn("по одному блоку", HELP_TEXT)
        self.assertNotIn("не сохранён", HELP_TEXT)

    async def test_weather_button_sets_waiting_state(self) -> None:
        message = FakeMessage("🌤 Погода сейчас")

        await find_handler(self.bot, "weather_button")(message)

        self.assertIn("Введите название города", message.answers[0]["text"])
        self.assertEqual(message.answers[0]["keyboard"], main_menu_keyboard())
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
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())
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
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())

    async def test_forecast_flow(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_FORECAST_CITY)
        message = FakeMessage("Казань")

        await find_handler(self.bot, "forecast_by_city")(message)

        self.assertEqual(self.service.calls, [("forecast", "Казань", False)])
        self.assertIn("Прогноз на 5 дней", message.answers[-1]["text"])
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())

    async def test_weather_button_uses_saved_city(self) -> None:
        self.bot.states.remember(10, city="Москва")
        message = FakeMessage("🌤 Погода сейчас")

        await find_handler(self.bot, "weather_button")(message)

        self.assertEqual(self.service.calls, [("current", "Москва", False)])
        self.assertIn("Погода сейчас", message.answers[-1]["text"])
        self.assertIn("Москва", message.answers[-1]["text"])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_forecast_button_uses_saved_city(self) -> None:
        self.bot.states.remember(10, city="Казань")
        message = FakeMessage("📅 Прогноз 5 дней")

        await find_handler(self.bot, "forecast_button")(message)

        self.assertEqual(self.service.calls, [("forecast", "Казань", False)])
        self.assertIn("Прогноз на 5 дней", message.answers[-1]["text"])

    async def test_extended_button_uses_saved_city(self) -> None:
        self.bot.states.remember(10, city="Сочи")
        message = FakeMessage("🌫 Расширенный режим")

        await find_handler(self.bot, "extended_button")(message)

        self.assertEqual(self.service.calls, [("current", "Сочи", True)])
        self.assertIn("Расширенная погода", message.answers[-1]["text"])

    async def test_start_shows_saved_city(self) -> None:
        self.bot.states.remember(10, city="Москва")
        message = FakeMessage("/start")

        await find_handler(self.bot, "start")(message)

        self.assertIn("Текущий город: Москва", message.answers[-1]["text"])

    async def test_change_city_button_requests_new_city(self) -> None:
        message = FakeMessage("🏙 Сменить город")

        await find_handler(self.bot, "change_city_button")(message)

        self.assertIn("Введите новый город", message.answers[-1]["text"])
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_CHANGE_CITY)

    async def test_save_new_city_returns_to_menu(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_CHANGE_CITY)
        message = FakeMessage("Казань")

        await find_handler(self.bot, "save_new_city")(message)

        self.assertEqual(self.bot.states.get_context(10).last_city, "Казань")
        self.assertIn("Новый город сохранён", message.answers[-1]["text"])
        self.assertIn("Текущий город: Казань", message.answers[-1]["text"])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_empty_new_city_prompts_again(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_CHANGE_CITY)
        message = FakeMessage("   ")

        await find_handler(self.bot, "save_new_city")(message)

        self.assertIn("Введите новый город", message.answers[-1]["text"])
        self.assertIsNone(self.bot.states.get_context(10).last_city)
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_CHANGE_CITY)

    async def test_compare_without_saved_city_asks_both(self) -> None:
        message = FakeMessage("📊 Сравнить погоду")
        await find_handler(self.bot, "compare_button")(message)

        self.assertIn("первый город", message.answers[-1]["text"])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_COMPARE_CITY_1)

        first = FakeMessage("Москва")
        await find_handler(self.bot, "compare_first_city")(first)

        self.assertIn("Первый город: Москва", first.answers[-1]["text"])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_COMPARE_CITY_2)
        self.assertEqual(peer.payload["first_city"], "Москва")

        second = FakeMessage("Сочи")
        await find_handler(self.bot, "compare_second_city")(second)

        self.assertEqual(
            self.service.calls,
            [
                ("current", "Москва", False),
                ("current", "Сочи", False),
            ],
        )
        self.assertIn("Сравнение погоды", second.answers[-1]["text"])
        self.assertIn("Сочи", second.answers[-1]["text"])
        self.assertEqual(second.answers[-1]["keyboard"], main_menu_keyboard())
        self.assertEqual(self.bot.states.get_context(10).last_city, "Москва")
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_compare_with_saved_city_asks_second_only(self) -> None:
        self.bot.states.remember(10, city="Москва")
        message = FakeMessage("📊 Сравнить погоду")

        await find_handler(self.bot, "compare_button")(message)

        self.assertIn("Первый город: Москва", message.answers[-1]["text"])
        self.assertIn("Например: Санкт-Петербург.", message.answers[-1]["text"])
        self.assertNotIn("Например: Москва.", message.answers[-1]["text"])
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_COMPARE_CITY_2)

        second = FakeMessage("Сочи")
        await find_handler(self.bot, "compare_second_city")(second)

        self.assertEqual(
            self.service.calls,
            [
                ("current", "Москва", False),
                ("current", "Сочи", False),
            ],
        )
        self.assertIn("Сравнение погоды", second.answers[-1]["text"])

    async def test_compare_second_prompt_excludes_first_city(self) -> None:
        self.bot.states.remember(10, city="Сочи")
        message = FakeMessage("📊 Сравнить погоду")

        await find_handler(self.bot, "compare_button")(message)

        self.assertIn("Например: Москва.", message.answers[-1]["text"])
        self.assertNotIn("Например: Сочи.", message.answers[-1]["text"])
        self.assertIn("Он должен отличаться от первого.", message.answers[-1]["text"])

    async def test_compare_rejects_same_second_city_before_api(self) -> None:
        await self.bot.states.set_state(
            10,
            BotState.WAITING_COMPARE_CITY_2,
            first_city="Москва",
        )
        message = FakeMessage("  москва  ")

        await find_handler(self.bot, "compare_second_city")(message)

        self.assertIn("уже выбран первым", message.answers[-1]["text"])
        self.assertIn("Например: Санкт-Петербург.", message.answers[-1]["text"])
        self.assertEqual(self.service.calls, [])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_COMPARE_CITY_2)
        self.assertEqual(peer.payload["first_city"], "Москва")
        self.assertIsNone(self.bot.states.get_context(10).last_city)

    async def test_compare_rejects_resolved_duplicate_city(self) -> None:
        self.service.city_aliases = {
            "Moscow": "Москва",
            "Москва": "Москва",
        }
        await self.bot.states.set_state(
            10,
            BotState.WAITING_COMPARE_CITY_2,
            first_city="Moscow",
        )
        message = FakeMessage("Москва")

        await find_handler(self.bot, "compare_second_city")(message)

        self.assertIn("уже выбран первым", message.answers[-1]["text"])
        self.assertEqual(
            self.service.calls,
            [
                ("current", "Moscow", False),
                ("current", "Москва", False),
            ],
        )
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_COMPARE_CITY_2)
        self.assertEqual(peer.payload["first_city"], "Moscow")

    async def test_compare_rejects_same_coordinates(self) -> None:
        self.service.city_coordinates = {
            "Город А": (55.0, 37.0),
            "Город Б": (55.0, 37.0),
        }
        await self.bot.states.set_state(
            10,
            BotState.WAITING_COMPARE_CITY_2,
            first_city="Город А",
        )
        message = FakeMessage("Город Б")

        await find_handler(self.bot, "compare_second_city")(message)

        self.assertIn("уже выбран первым", message.answers[-1]["text"])
        self.assertEqual(
            self.service.calls,
            [
                ("current", "Город А", False),
                ("current", "Город Б", False),
            ],
        )
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_COMPARE_CITY_2)

    async def test_compare_empty_second_city_prompts_again(self) -> None:
        await self.bot.states.set_state(
            10,
            BotState.WAITING_COMPARE_CITY_2,
            first_city="Москва",
        )
        message = FakeMessage("   ")

        await find_handler(self.bot, "compare_second_city")(message)

        self.assertIn("второй город", message.answers[-1]["text"])
        self.assertEqual(self.service.calls, [])
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_COMPARE_CITY_2)

    async def test_geo_saves_resolved_city(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_GEO)
        message = FakeMessage("59.9343,30.3351")

        await find_handler(self.bot, "weather_by_geo")(message)

        self.assertEqual(
            self.bot.states.get_context(10).last_city,
            "Санкт-Петербург",
        )
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_geo_flow_with_text_coordinates(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_GEO)
        message = FakeMessage("55.7558,37.6173")

        await find_handler(self.bot, "weather_by_geo")(message)

        self.assertEqual(
            self.service.calls,
            [("coords", 55.7558, 37.6173, False)],
        )
        self.assertIn("Погода сейчас", message.answers[-1]["text"])
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())

    async def test_coordinates_from_main_menu_start_geo(self) -> None:
        message = FakeMessage("54.989347, 73.368221")

        await find_handler(self.bot, "coordinates_anywhere")(message)

        self.assertEqual(
            self.service.calls,
            [("coords", 54.989347, 73.368221, False)],
        )
        self.assertIn("Погода сейчас", message.answers[-1]["text"])
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)
        self.assertEqual(
            self.bot.states.get_context(10).last_city,
            "Санкт-Петербург",
        )

    async def test_coordinates_override_waiting_city_state(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_CITY)
        message = FakeMessage("54.989347 73.368221")

        await find_handler(self.bot, "coordinates_anywhere")(message)

        self.assertEqual(
            self.service.calls,
            [("coords", 54.989347, 73.368221, False)],
        )
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_coordinates_override_comparison_state(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_COMPARE_CITY_2)
        message = FakeMessage("54.989347, 73.368221")

        await find_handler(self.bot, "coordinates_anywhere")(message)

        self.assertEqual(
            self.service.calls,
            [("coords", 54.989347, 73.368221, False)],
        )
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_coordinate_text_filter_rejects_city_and_single_number(
        self,
    ) -> None:
        from weather_vk_bot.handlers.geo import _is_coordinate_text

        self.assertTrue(_is_coordinate_text(FakeMessage("54.989347, 73.368221")))
        self.assertTrue(_is_coordinate_text(FakeMessage("54.989347 73.368221")))
        self.assertFalse(_is_coordinate_text(FakeMessage("Москва")))
        self.assertFalse(_is_coordinate_text(FakeMessage("54.989347")))

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

    async def test_geo_button_prompts_with_geo_keyboard(self) -> None:
        message = FakeMessage("📍 Геолокация")

        await find_handler(self.bot, "geo_button")(message)

        self.assertEqual(message.answers[-1]["keyboard"], geo_keyboard())
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.WAITING_GEO)

    async def test_cancel_returns_to_main_menu(self) -> None:
        await self.bot.states.set_state(10, BotState.WAITING_CHANGE_CITY)
        message = FakeMessage("/cancel")

        await find_handler(self.bot, "cancel")(message)

        self.assertIn("Погодный эксперт", message.answers[-1]["text"])
        self.assertEqual(message.answers[-1]["keyboard"], main_menu_keyboard())
        peer = await self.bot.states.get_state(10)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

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

    async def test_diagnose_reports_ready_settings(self) -> None:
        responses = {
            "groups.getById": {
                "response": {
                    "groups": [{"id": 242611812, "name": "Weather Bot"}]
                }
            },
            "groups.getTokenPermissions": {
                "response": {
                    "permissions": [{"name": "messages"}],
                }
            },
            "groups.getLongPollSettings": {
                "response": {
                    "is_enabled": True,
                    "events": {"message_new": 1, "message_allow": 1},
                }
            },
        }
        self.bot.api.request = AsyncMock(  # type: ignore[method-assign]
            side_effect=lambda method, params: responses[method]
        )

        report = await self.bot.diagnose()

        self.assertTrue(report.ready)
        self.assertEqual(report.group_name, "Weather Bot")
        text = format_startup_diagnostics(report)
        self.assertIn("✅ Право messages", text)
        self.assertIn("✅ Long Poll API", text)
        self.assertIn("✅ Событие message_new", text)
        self.assertIn("✅ Событие message_allow", text)
        self.assertIn("⚠️ Возможности ботов", text)
        self.assertIn("Критические проверки пройдены", text)

    async def test_diagnose_marks_broken_settings_as_blocking(self) -> None:
        responses = {
            "groups.getById": {
                "response": {
                    "groups": [{"id": 242611812, "name": "Weather Bot"}]
                }
            },
            "groups.getTokenPermissions": {
                "response": {"permissions": []},
            },
            "groups.getLongPollSettings": {
                "response": {
                    "is_enabled": False,
                    "events": {"message_new": 0, "message_allow": 0},
                }
            },
        }
        self.bot.api.request = AsyncMock(  # type: ignore[method-assign]
            side_effect=lambda method, params: responses[method]
        )

        report = await self.bot.diagnose()

        self.assertFalse(report.ready)
        text = format_startup_diagnostics(report)
        self.assertIn("❌ Право messages", text)
        self.assertIn("❌ Long Poll API", text)
        self.assertIn("❌ Событие message_new", text)
        self.assertIn("❌ Событие message_allow", text)
        self.assertIn("Ключи доступа", text)
        self.assertIn("Есть критические проблемы", text)

    async def test_diagnose_handles_api_errors(self) -> None:
        def request(method: str, params: dict[str, Any]) -> dict[str, Any]:
            if method == "groups.getById":
                return {
                    "response": {
                        "groups": [{"id": 242611812, "name": "Weather Bot"}]
                    }
                }
            raise RuntimeError("network")

        self.bot.api.request = AsyncMock(  # type: ignore[method-assign]
            side_effect=request
        )

        report = await self.bot.diagnose()

        self.assertFalse(report.ready)
        text = format_startup_diagnostics(report)
        self.assertIn("не удалось проверить", text)
        self.assertIn("RuntimeError", text)



class StateManagerFactoryTest(unittest.TestCase):
    def test_builtin_dispenser_can_be_wrapped(self) -> None:
        manager = StateManager(BuiltinStateDispenser())
        self.assertIsNotNone(manager)

    def test_handlers_are_blocking_and_fallback_is_last(self) -> None:
        bot = VKWeatherBot("test-token", service=FakeWeatherService())
        handlers = bot.bot.labeler.message_view.handlers

        self.assertTrue(all(handler.blocking for handler in handlers))
        self.assertEqual(handlers[-1].handler.__name__, "fallback")

    def test_coordinate_handler_is_registered_before_state_handlers(self) -> None:
        bot = VKWeatherBot("test-token", service=FakeWeatherService())
        names = [
            handler.handler.__name__
            for handler in bot.bot.labeler.message_view.handlers
        ]
        coordinate_index = names.index("coordinates_anywhere")

        for name in (
            "current_weather",
            "forecast_by_city",
            "compare_first_city",
            "save_new_city",
        ):
            self.assertLess(coordinate_index, names.index(name))

    def test_ssl_is_passed_per_request_not_to_client_session(self) -> None:
        bot = VKWeatherBot("test-token", service=FakeWeatherService())
        client = bot.api.http_client

        self.assertIsInstance(client, SSLAiohttpClient)
        self.assertNotIn("ssl", client._session_params)
        self.assertIsNotNone(client._ssl_context)


if __name__ == "__main__":
    unittest.main()
