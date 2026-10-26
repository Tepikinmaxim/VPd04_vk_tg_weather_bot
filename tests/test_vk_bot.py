import io
import json
import unittest
from contextlib import redirect_stderr
from typing import Any, Mapping
from unittest.mock import patch

import vk_bot
from OpenWeatherAPI import OpenWeatherAPIError


CURRENT_RESULT: dict[str, Any] = {
    "location": {
        "name": "Москва",
        "lat": 55.7558,
        "lon": 37.6173,
        "country": "RU",
        "state": None,
    },
    "weather": {
        "description": "ясно",
        "condition": "Clear",
        "temperature_c": 20.5,
        "feels_like_c": 19.8,
        "temp_min_c": 18.0,
        "temp_max_c": 22.0,
        "humidity_percent": 50.0,
        "wind_speed_ms": 2.0,
        "clouds_percent": 10.0,
    },
}

FORECAST_RESULT: dict[str, Any] = {
    "location": CURRENT_RESULT["location"],
    "forecast": [
        {
            "datetime": "2026-10-27 09:00:00",
            "description": "ясно",
            "temperature_c": 21.0,
            "humidity_percent": 45.0,
            "pressure_hpa": 1015.0,
            "clouds_percent": 5.0,
            "wind_speed_ms": 3.0,
            "precipitation_probability_percent": 0.0,
        },
        {
            "datetime": "2026-10-27 12:00:00",
            "description": "облачно",
            "temperature_c": 22.0,
        },
    ],
}


class FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send(self, **kwargs: Any) -> dict[str, int]:
        self.calls.append(kwargs)
        return {"message_id": len(self.calls)}


class FakeAPI:
    def __init__(self) -> None:
        self.messages = FakeMessages()


def make_update(
    text: str,
    *,
    peer_id: int = 10,
    user_id: int = 20,
) -> dict[str, Any]:
    return {
        "type": "message_new",
        "object": {
            "message": {
                "peer_id": peer_id,
                "from_id": user_id,
                "text": text,
            }
        },
    }


def keyboard_labels(keyboard: str) -> list[str]:
    data = json.loads(keyboard)
    return [
        button["action"]["label"]
        for row in data["buttons"]
        for button in row
    ]


class WeatherBotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.api = FakeAPI()
        self.calls: list[tuple[str, str]] = []

    def make_loader(self, result: Mapping[str, Any] | None = None):
        def loader(city: str, mode: str) -> Mapping[str, Any]:
            self.calls.append((city, mode))
            return result if result is not None else CURRENT_RESULT

        return loader

    async def test_start_asks_for_city_and_shows_keyboard(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())

        handled = await bot.handle_update(make_update("/start"))

        self.assertTrue(handled)
        self.assertEqual(len(self.api.messages.calls), 1)
        call = self.api.messages.calls[0]
        self.assertIn("Введите город", call["message"])
        self.assertIsInstance(call["random_id"], int)
        self.assertEqual(
            keyboard_labels(call["keyboard"]),
            [
                "Погода сейчас",
                "Подробно",
                "Прогноз на 5 дней",
                "Другой город",
            ],
        )

    async def test_city_then_forecast_uses_loader_and_renders_text(self) -> None:
        bot = vk_bot.WeatherBot(
            self.api,
            loader=self.make_loader(FORECAST_RESULT),
        )

        await bot.handle_update(make_update("Москва"))
        self.assertEqual(self.calls, [])
        self.assertIn("Город: Москва", self.api.messages.calls[0]["message"])

        await bot.handle_update(make_update("Прогноз на 5 дней"))

        self.assertEqual(self.calls, [("Москва", "forecast")])
        reply = self.api.messages.calls[-1]
        self.assertIn("Прогноз на 5 дней", reply["message"])
        self.assertIn("12:00 MSK", reply["message"])
        self.assertNotIn("27.10.2026 15:00 MSK", reply["message"])
        self.assertIn("keyboard", reply)

    async def test_mode_before_city_is_remembered(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())

        await bot.handle_update(make_update("Подробно"))
        self.assertIn("Сначала введите город", self.api.messages.calls[-1]["message"])

        await bot.handle_update(make_update("Казань"))

        self.assertEqual(self.calls, [("Казань", "extended")])
        self.assertIn("Погода", self.api.messages.calls[-1]["message"])

    async def test_current_weather_button(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())

        await bot.handle_update(make_update("Москва"))
        await bot.handle_update(make_update("Погода сейчас"))

        self.assertEqual(self.calls, [("Москва", "current")])
        self.assertIn("Температура", self.api.messages.calls[-1]["message"])

    async def test_other_city_resets_state(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())
        await bot.handle_update(make_update("Москва"))

        await bot.handle_update(make_update("Другой город"))
        self.assertIn("Введите город", self.api.messages.calls[-1]["message"])

        await bot.handle_update(make_update("Сочи"))
        await bot.handle_update(make_update("Погода сейчас"))

        self.assertEqual(self.calls, [("Сочи", "current")])

    async def test_weather_error_is_reported_to_user(self) -> None:
        def failing_loader(city: str, mode: str) -> Mapping[str, Any]:
            raise OpenWeatherAPIError("сервис временно недоступен")

        bot = vk_bot.WeatherBot(self.api, loader=failing_loader)

        await bot.handle_update(make_update("Москва"))
        await bot.handle_update(make_update("Погода сейчас"))

        message = self.api.messages.calls[-1]["message"]
        self.assertIn("Не удалось получить погоду", message)
        self.assertIn("сервис временно недоступен", message)

    async def test_unknown_command_and_help(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())

        await bot.handle_update(make_update("/unknown"))
        self.assertIn("Неизвестная команда", self.api.messages.calls[-1]["message"])

        await bot.handle_update(make_update("/help"))
        self.assertIn("Как пользоваться ботом", self.api.messages.calls[-1]["message"])

    async def test_non_message_event_is_ignored(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())

        handled = await bot.handle_update(
            {"type": "message_event", "object": {"event_id": "1"}}
        )

        self.assertFalse(handled)
        self.assertEqual(self.api.messages.calls, [])

    async def test_outgoing_message_is_ignored(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())
        update = make_update("Москва")
        update["object"]["message"]["out"] = 1

        handled = await bot.handle_update(update)

        self.assertFalse(handled)
        self.assertEqual(self.api.messages.calls, [])

    async def test_states_are_separate_for_different_peers(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())

        await bot.handle_update(make_update("Москва", peer_id=1, user_id=1))
        await bot.handle_update(make_update("Сочи", peer_id=2, user_id=2))
        await bot.handle_update(make_update("Погода сейчас", peer_id=1, user_id=1))
        await bot.handle_update(make_update("Погода сейчас", peer_id=2, user_id=2))

        self.assertEqual(self.calls, [("Москва", "current"), ("Сочи", "current")])

    async def test_long_message_is_split_and_keyboard_goes_last(self) -> None:
        bot = vk_bot.WeatherBot(self.api, loader=self.make_loader())
        text = "\n".join(["строка"] * 2000)

        await bot.send_text(1, text, "keyboard-json")

        self.assertGreater(len(self.api.messages.calls), 1)
        self.assertTrue(all(len(call["message"]) <= vk_bot.MAX_MESSAGE_LENGTH for call in self.api.messages.calls))
        self.assertNotIn("keyboard", self.api.messages.calls[0])
        self.assertEqual(self.api.messages.calls[-1]["keyboard"], "keyboard-json")


class SplitMessageTests(unittest.TestCase):
    def test_short_message_is_unchanged(self) -> None:
        self.assertEqual(vk_bot.split_message("привет"), ["привет"])

    def test_long_line_is_split(self) -> None:
        chunks = vk_bot.split_message("x" * 25, limit=10)

        self.assertEqual(chunks, ["x" * 10, "x" * 10, "x" * 5])

    def test_lines_are_not_broken_unnecessarily(self) -> None:
        chunks = vk_bot.split_message("aaa\nbbb\nccc", limit=7)

        self.assertEqual(chunks, ["aaa\nbbb", "ccc"])


class GroupLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_id_is_resolved_from_token(self) -> None:
        class FakeRequestAPI:
            def __init__(self) -> None:
                self.requests: list[tuple[str, Mapping[str, Any]]] = []

            async def request(
                self,
                method: str,
                params: Mapping[str, Any],
            ) -> Mapping[str, Any]:
                self.requests.append((method, params))
                return {
                    "response": {
                        "groups": [{"id": 123, "name": "Погода"}],
                    }
                }

        api = FakeRequestAPI()

        group_id, name = await vk_bot._fetch_group(api, None)

        self.assertEqual((group_id, name), (123, "Погода"))
        self.assertEqual(api.requests, [("groups.getById", {})])

    async def test_configured_group_id_is_passed_to_vk(self) -> None:
        class FakeRequestAPI:
            def __init__(self) -> None:
                self.requests: list[tuple[str, Mapping[str, Any]]] = []

            async def request(
                self,
                method: str,
                params: Mapping[str, Any],
            ) -> Mapping[str, Any]:
                self.requests.append((method, params))
                return {
                    "response": {
                        "groups": [{"id": 123, "name": "Погода"}],
                    }
                }

        api = FakeRequestAPI()

        await vk_bot._fetch_group(api, 123)

        self.assertEqual(api.requests, [("groups.getById", {"group_id": 123})])

    async def test_missing_group_data_is_reported(self) -> None:
        class FakeRequestAPI:
            async def request(
                self,
                method: str,
                params: Mapping[str, Any],
            ) -> Mapping[str, Any]:
                return {"response": {"groups": []}}

        with self.assertRaises(vk_bot.BotAuthError):
            await vk_bot._fetch_group(FakeRequestAPI(), None)


class ConfigTests(unittest.TestCase):
    def test_group_id_accepts_club_short_name(self) -> None:
        self.assertEqual(vk_bot._parse_group_id("club242611812"), 242611812)

    def test_group_id_accepts_public_url(self) -> None:
        self.assertEqual(
            vk_bot._parse_group_id("https://vk.com/public242611812/"),
            242611812,
        )

    def test_group_id_accepts_negative_numeric_value(self) -> None:
        self.assertEqual(vk_bot._parse_group_id("-242611812"), 242611812)

    def test_main_requires_vk_token(self) -> None:
        stderr = io.StringIO()
        with patch.object(vk_bot, "load_dotenv"), patch.dict(
            vk_bot.os.environ,
            {},
            clear=True,
        ), redirect_stderr(stderr):
            code = vk_bot.main([])

        self.assertEqual(code, 2)
        self.assertIn("VK_BOT_TOKEN", stderr.getvalue())
        self.assertIn(".env", stderr.getvalue())

    def test_main_rejects_non_numeric_group_id(self) -> None:
        stderr = io.StringIO()
        with patch.object(vk_bot, "load_dotenv"), patch.dict(
            vk_bot.os.environ,
            {"VK_BOT_TOKEN": "test-token", "VK_GROUP_ID": "not-a-number"},
            clear=True,
        ), redirect_stderr(stderr):
            code = vk_bot.main([])

        self.assertEqual(code, 2)
        self.assertIn("VK_GROUP_ID", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
