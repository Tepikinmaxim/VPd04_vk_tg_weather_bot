import unittest
from typing import Any
from unittest.mock import patch

from aiogram import Router

from weather_tg_bot.handlers import (
    comparison,
    geo,
    help as help_handler,
    menu,
    onboarding,
    register_handlers,
    weather,
)
from weather_tg_bot.handlers.common import (
    HELP_TEXT,
    TgDeps,
    send_text,
)
from weather_tg_bot.handlers.geo import CoordinatesFilter
from weather_tg_bot.keyboards import geo_keyboard, main_menu_keyboard
from weather_tg_bot.state import FSMStateStore, TgState


class FakeChat:
    def __init__(self, chat_id: int = 10) -> None:
        self.id = chat_id


class FakeLocation:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude


class FakeMessage:
    def __init__(
        self,
        text: str = "",
        *,
        chat_id: int = 10,
        location: Any = None,
    ) -> None:
        self.text = text
        self.chat = FakeChat(chat_id)
        self.location = location
        self.answers: list[dict[str, Any]] = []

    async def answer(self, text: str, **kwargs: Any) -> dict[str, Any]:
        self.answers.append({"text": text, **kwargs})
        return {"message_id": len(self.answers)}


class FakeFSMContext:
    def __init__(self) -> None:
        self.state: str | None = None
        self.data: dict[str, Any] = {}

    async def get_state(self) -> str | None:
        return self.state

    async def set_state(self, state: str | None) -> None:
        self.state = state

    async def get_data(self) -> dict[str, Any]:
        return dict(self.data)

    async def update_data(self, **kwargs: Any) -> None:
        self.data.update(kwargs)


def make_store() -> FSMStateStore:
    return FSMStateStore(FakeFSMContext())  # type: ignore[arg-type]


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


class TelegramScenarioTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = FakeWeatherService()
        self.deps = TgDeps(service=self.service)  # type: ignore[arg-type]
        self.store = make_store()

    async def test_start_shows_help_and_menu(self) -> None:
        message = FakeMessage("/start")

        await onboarding.handle_start(message, self.deps, self.store)

        self.assertEqual(message.answers[0]["text"], HELP_TEXT)
        self.assertIsNotNone(message.answers[0]["reply_markup"])
        self.assertEqual(await self.store.get_state(), TgState.MAIN_MENU)

    async def test_weather_button_without_city_prompts(self) -> None:
        message = FakeMessage("🌤 Погода сейчас")

        await menu.handle_weather_button(message, self.deps, self.store)

        self.assertIn("Введите название города", message.answers[0]["text"])
        self.assertEqual(await self.store.get_state(), TgState.WAITING_CITY)
        self.assertEqual(self.service.calls, [])

    async def test_weather_button_uses_saved_city(self) -> None:
        await self.store.update_data(last_city="Москва")
        message = FakeMessage("🌤 Погода сейчас")

        await menu.handle_weather_button(message, self.deps, self.store)

        self.assertEqual(self.service.calls, [("current", "Москва", False)])
        self.assertIn("Погода сейчас", message.answers[-1]["text"])

    async def test_waiting_city_fetches_weather(self) -> None:
        await self.store.set_state(TgState.WAITING_CITY)
        message = FakeMessage("Казань")

        await weather.handle_waiting_city(message, self.deps, self.store)

        self.assertEqual(self.service.calls, [("current", "Казань", False)])
        self.assertEqual(await self.store.get_state(), TgState.MAIN_MENU)
        self.assertEqual((await self.store.get_data())["last_city"], "Казань")

    async def test_forecast_uses_saved_city(self) -> None:
        await self.store.update_data(last_city="Сочи")
        message = FakeMessage("📅 Прогноз 5 дней")

        await menu.handle_forecast_button(message, self.deps, self.store)

        self.assertEqual(self.service.calls, [("forecast", "Сочи", False)])
        self.assertIn("Прогноз на 5 дней", message.answers[-1]["text"])

    async def test_extended_uses_saved_city(self) -> None:
        await self.store.update_data(last_city="Сочи")
        message = FakeMessage("🌫 Расширенный режим")

        await menu.handle_extended_button(message, self.deps, self.store)

        self.assertEqual(self.service.calls, [("current", "Сочи", True)])
        self.assertIn("Расширенная погода", message.answers[-1]["text"])

    async def test_change_city_saves_new_city(self) -> None:
        await self.store.set_state(TgState.WAITING_CHANGE_CITY)
        message = FakeMessage("Омск")

        await menu.handle_save_new_city(message, self.deps, self.store)

        self.assertEqual((await self.store.get_data())["last_city"], "Омск")
        self.assertIn("Новый город сохранён", message.answers[-1]["text"])
        self.assertEqual(await self.store.get_state(), TgState.MAIN_MENU)

    async def test_compare_with_saved_city_asks_second(self) -> None:
        await self.store.update_data(last_city="Москва")
        message = FakeMessage("📊 Сравнить погоду")

        await comparison.handle_compare_button(message, self.deps, self.store)

        self.assertIn("второй город", message.answers[-1]["text"])
        self.assertEqual(
            await self.store.get_state(),
            TgState.WAITING_COMPARE_CITY_2,
        )

    async def test_compare_success(self) -> None:
        await self.store.update_data(last_city="Москва")
        await self.store.set_state(TgState.WAITING_COMPARE_CITY_2)
        await self.store.update_data(first_city="Москва")
        message = FakeMessage("Сочи")

        await comparison.handle_compare_second_city(
            message,
            self.deps,
            self.store,
        )

        self.assertEqual(
            self.service.calls,
            [("current", "Москва", False), ("current", "Сочи", False)],
        )
        self.assertIn("Сравнение погоды", message.answers[-1]["text"])
        self.assertEqual(await self.store.get_state(), TgState.MAIN_MENU)

    async def test_compare_rejects_duplicate_before_api(self) -> None:
        await self.store.set_state(TgState.WAITING_COMPARE_CITY_2)
        await self.store.update_data(first_city="Москва")
        message = FakeMessage("москва")

        await comparison.handle_compare_second_city(
            message,
            self.deps,
            self.store,
        )

        self.assertEqual(self.service.calls, [])
        self.assertIn("уже выбран первым", message.answers[-1]["text"])

    async def test_compare_rejects_same_coordinates(self) -> None:
        self.service.city_coordinates = {
            "Москва": (55.75, 37.61),
            "Столица": (55.75, 37.61),
        }
        await self.store.set_state(TgState.WAITING_COMPARE_CITY_2)
        await self.store.update_data(first_city="Москва")
        message = FakeMessage("Столица")

        await comparison.handle_compare_second_city(
            message,
            self.deps,
            self.store,
        )

        self.assertIn("уже выбран первым", message.answers[-1]["text"])
        self.assertEqual(len(self.service.calls), 2)

    async def test_geo_text_coordinates(self) -> None:
        await self.store.set_state(TgState.WAITING_GEO)
        message = FakeMessage("54.989347, 73.368221")

        await geo.handle_waiting_geo(message, self.deps, self.store)

        self.assertEqual(
            self.service.calls,
            [("coords", 54.989347, 73.368221, False)],
        )
        self.assertEqual(await self.store.get_state(), TgState.MAIN_MENU)

    async def test_geo_native_location(self) -> None:
        await self.store.set_state(TgState.WAITING_GEO)
        message = FakeMessage(
            "",
            location=FakeLocation(59.9343, 30.3351),
        )

        await geo.handle_waiting_geo(message, self.deps, self.store)

        self.assertEqual(
            self.service.calls,
            [("coords", 59.9343, 30.3351, False)],
        )

    async def test_invalid_geo_keeps_state(self) -> None:
        await self.store.set_state(TgState.WAITING_GEO)
        message = FakeMessage("не координаты")

        await geo.handle_waiting_geo(message, self.deps, self.store)

        self.assertIn("Не удалось распознать", message.answers[-1]["text"])
        self.assertEqual(await self.store.get_state(), TgState.WAITING_GEO)

    async def test_coordinates_filter(self) -> None:
        filter_ = CoordinatesFilter()

        self.assertTrue(
            await filter_(FakeMessage("54.989347, 73.368221"))  # type: ignore[arg-type]
        )
        self.assertTrue(
            await filter_(FakeMessage("54.989347 73.368221"))  # type: ignore[arg-type]
        )
        self.assertFalse(
            await filter_(FakeMessage("Москва"))  # type: ignore[arg-type]
        )
        self.assertFalse(
            await filter_(FakeMessage("54.989347"))  # type: ignore[arg-type]
        )

    async def test_help_shows_same_text(self) -> None:
        message = FakeMessage("/help")

        await help_handler.handle_help(message, self.deps, self.store)

        self.assertEqual(message.answers[-1]["text"], HELP_TEXT)

    async def test_long_message_is_split_with_keyboard_on_last_part(self) -> None:
        message = FakeMessage("")
        keyboard = main_menu_keyboard()

        await send_text(message, "x" * 5000, keyboard)

        self.assertEqual(len(message.answers), 2)
        self.assertIsNone(message.answers[0].get("reply_markup"))
        self.assertIs(message.answers[1]["reply_markup"], keyboard)


class TelegramKeyboardTests(unittest.TestCase):
    def test_main_menu_labels(self) -> None:
        keyboard = main_menu_keyboard()
        labels = [[button.text for button in row] for row in keyboard.keyboard]

        self.assertEqual(
            labels,
            [
                ["🌤 Погода сейчас", "📅 Прогноз 5 дней"],
                ["📊 Сравнить погоду", "🌫 Расширенный режим"],
                ["📍 Геолокация", "🏙 Сменить город"],
                ["ℹ️ Помощь"],
            ],
        )
        self.assertTrue(keyboard.resize_keyboard)

    def test_geo_keyboard_requests_location_and_has_back(self) -> None:
        keyboard = geo_keyboard()
        buttons = [button for row in keyboard.keyboard for button in row]

        self.assertTrue(any(button.request_location for button in buttons))
        self.assertIn("⬅️ В меню", [button.text for button in buttons])


class TelegramRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = FakeWeatherService()
        self.deps = TgDeps(service=self.service)  # type: ignore[arg-type]

    async def test_fallback_shows_unknown_and_menu(self) -> None:
        router = Router()
        menu.register_fallback(router, self.deps)
        callback = router.message.handlers[-1].callback
        message = FakeMessage("неизвестный текст")

        await callback(message, FakeFSMContext())

        self.assertIn("Не понял команду", message.answers[-1]["text"])

    def test_handler_order_keeps_global_coordinates_and_menu_priority(self) -> None:
        router = Router()
        register_handlers(router, self.deps)
        names = [handler.callback.__name__ for handler in router.message.handlers]

        self.assertLess(
            names.index("coordinates_anywhere"),
            names.index("weather_button"),
        )
        self.assertLess(
            names.index("change_city_button"),
            names.index("weather_by_geo"),
        )
        self.assertEqual(names[-1], "fallback")
