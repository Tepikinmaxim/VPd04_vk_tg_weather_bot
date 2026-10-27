import io
import json
import os
import unittest
from unittest.mock import Mock, call, patch

import cli.cli as module
from OpenWeatherAPI import OpenWeatherAPI, OpenWeatherAPIError


class OpenWeatherAPICLITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = patch.dict(
            os.environ,
            {"OPENWEATHER_API_KEY": "test-key"},
            clear=True,
        )
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = module.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_city_basic(self, get_weather: Mock) -> None:
        get_weather.return_value = {"location": {"name": "Москва"}}

        code, stdout, stderr = self._run(["Москва", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(stdout),
            {"местоположение": {"название": "Москва"}},
        )
        self.assertIn("Москва", stdout)
        self.assertEqual(stderr, "")
        get_weather.assert_called_once_with("Москва", extended=False)

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_city_extended(self, get_weather: Mock) -> None:
        get_weather.return_value = {"weather": {"temperature_c": 20.0}}

        code, _, _ = self._run(["Москва", "--extended"])

        self.assertEqual(code, 0)
        get_weather.assert_called_once_with("Москва", extended=True)

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_text_output_is_structured(self, get_weather: Mock) -> None:
        get_weather.return_value = {
            "location": {
                "name": "Сочи",
                "lat": 43.5854823,
                "lon": 39.723109,
                "country": "RU",
                "state": "Krasnodar Krai",
            },
            "weather": {
                "description": "ясно",
                "condition": "Clear",
                "temperature_c": 15.04,
                "feels_like_c": 14.77,
                "temp_min_c": 15.04,
                "temp_max_c": 15.04,
                "humidity_percent": 83.0,
                "wind_speed_ms": 1.65,
                "clouds_percent": 1.0,
                "pressure_hpa": 1016.0,
                "sea_level_hpa": 1016.0,
                "ground_level_hpa": 993.0,
                "visibility_m": 10000.0,
                "visibility_km": 10.0,
            },
            "sun": {
                "sunrise_utc": "2026-10-25T03:47:07+00:00",
                "sunset_utc": "2026-10-25T14:23:03+00:00",
            },
            "air_quality": {
                "aqi_index": 2,
                "aqi_label": "Удовлетворительное",
                "overall_aqi_index": 2,
                "overall_label": "Удовлетворительное",
                "pollutants": {
                    "o3": {
                        "value": 91.98,
                        "unit": "мкг/м³",
                        "category": "Удовлетворительное",
                        "safe_limit": 60.0,
                        "exceeded": True,
                    }
                },
                "exceeded_pollutant_names": ["O3"],
                "human_summary": (
                    "Качество воздуха удовлетворительное. "
                    "Слегка повышено содержание: O3."
                ),
            },
        }

        code, stdout, stderr = self._run(["Сочи", "--extended"])

        self.assertEqual(code, 0)
        self.assertIn("Местоположение", stdout)
        self.assertIn("Название", stdout)
        self.assertIn("Сочи", stdout)
        self.assertIn("Широта", stdout)
        self.assertIn("43.5854823", stdout)
        self.assertRegex(stdout, r"Актуально на \d{2}\.\d{2}\.\d{4}, \d{2}:\d{2}")
        self.assertIn("Погода", stdout)
        self.assertIn("Температура", stdout)
        self.assertIn("15.04 °C", stdout)
        self.assertIn("Давление на уровне земли", stdout)
        self.assertIn("993 гПа", stdout)
        self.assertIn("Видимость", stdout)
        self.assertIn("10 км", stdout)
        self.assertIn("Солнце", stdout)
        self.assertIn("25.10.2026 03:47 UTC", stdout)
        self.assertIn("Качество воздуха", stdout)
        self.assertIn("O3", stdout)
        self.assertIn("превышен", stdout)
        self.assertNotIn('"местоположение"', stdout)
        self.assertEqual(stderr, "")

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_extended_output_uses_russian_keys(self, get_weather: Mock) -> None:
        get_weather.return_value = {
            "location": {"name": "Москва", "lat": 55.75, "lon": 37.62},
            "weather": {"description": "ясно", "pressure_hpa": 1028.0},
            "sun": {"sunrise_utc": "2026-10-25T04:20:09+00:00"},
            "air_quality": {
                "aqi_index": 2,
                "pollutants": {
                    "pm10": {
                        "value": 33.34,
                        "unit": "мкг/м³",
                        "safe_limit": 20.0,
                        "exceeded": True,
                    }
                },
            },
        }

        code, stdout, _ = self._run(["Москва", "--extended", "--json"])

        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(stdout),
            {
                "местоположение": {
                    "название": "Москва",
                    "широта": 55.75,
                    "долгота": 37.62,
                },
                "погода": {
                    "описание": "ясно",
                    "давление_гпа": 1028.0,
                },
                "солнце": {"восход_utc": "2026-10-25T04:20:09+00:00"},
                "качество_воздуха": {
                    "индекс_aqi": 2,
                    "загрязнители": {
                        "pm10": {
                            "значение": 33.34,
                            "единица": "мкг/м³",
                            "безопасный_предел": 20.0,
                            "превышен": True,
                        }
                    },
                },
            },
        )

    @patch.object(OpenWeatherAPI, "get_forecast_by_city")
    def test_forecast_extended(self, get_forecast: Mock) -> None:
        get_forecast.return_value = {
            "location": {"name": "Москва"},
            "forecast": [
                {
                    "datetime": "2026-10-25 12:00:00",
                    "description": "ясно",
                    "temperature_c": 10.0,
                    "humidity_percent": 50.0,
                    "pressure_hpa": 1010.0,
                    "clouds_percent": 20.0,
                    "wind_speed_ms": 2.0,
                    "precipitation_probability": 0.1,
                    "precipitation_probability_percent": 10.0,
                }
            ],
        }

        code, stdout, _ = self._run(
            ["Москва", "--forecast", "--extended", "--json"]
        )

        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(stdout),
            {
                "местоположение": {"название": "Москва"},
                "прогноз": [
                    {
                        "дата_время": "2026-10-25 12:00:00",
                        "описание": "ясно",
                        "температура_c": 10.0,
                        "влажность_процент": 50.0,
                        "давление_гпа": 1010.0,
                        "облачность_процент": 20.0,
                        "скорость_ветра_м_с": 2.0,
                        "вероятность_осадков": 0.1,
                        "вероятность_осадков_процент": 10.0,
                    }
                ],
            },
        )
        get_forecast.assert_called_once_with("Москва", extended=True)

    @patch.object(OpenWeatherAPI, "get_forecast_by_city")
    def test_forecast_text_output(self, get_forecast: Mock) -> None:
        get_forecast.return_value = {
            "location": {"name": "Сочи"},
            "forecast": [
                {
                    "datetime": "2026-10-25 09:00:00",
                    "description": "ясно",
                    "temperature_c": 10.0,
                    "humidity_percent": 50.0,
                    "pressure_hpa": 1010.0,
                    "clouds_percent": 20.0,
                    "wind_speed_ms": 2.0,
                    "precipitation_probability_percent": 10.0,
                }
            ],
        }

        code, stdout, stderr = self._run(["Сочи", "--forecast"])

        self.assertEqual(code, 0)
        self.assertIn("Прогноз на 5 дней", stdout)
        self.assertIn("По одному прогнозу на день", stdout)
        self.assertNotIn("По одному блоку на день", stdout)
        self.assertNotIn("Актуально на", stdout)
        self.assertIn("12:00 MSK (UTC+3)", stdout)
        self.assertIn("данные в UTC", stdout)
        self.assertIn("25.10.2026 12:00 MSK", stdout)
        self.assertIn("Описание", stdout)
        self.assertIn("10 °C", stdout)
        self.assertIn("Влажность", stdout)
        self.assertIn("50 %", stdout)
        self.assertIn("Вероятность осадков", stdout)
        self.assertIn("10 %", stdout)
        self.assertEqual(stderr, "")

    @patch.object(OpenWeatherAPI, "get_forecast_by_city")
    def test_forecast_text_keeps_one_noon_block_per_day(
        self,
        get_forecast: Mock,
    ) -> None:
        get_forecast.return_value = {
            "location": {"name": "Москва"},
            "forecast": [
                {
                    "datetime": "2026-10-26 09:00:00",
                    "description": "ясно",
                    "temperature_c": 5.0,
                },
                {
                    "datetime": "2026-10-26 12:00:00",
                    "description": "облачно",
                    "temperature_c": 7.0,
                },
                {
                    "datetime": "2026-10-26 18:00:00",
                    "description": "дождь",
                    "temperature_c": 6.0,
                },
                {
                    "datetime": "2026-10-27 09:00:00",
                    "description": "снег",
                    "temperature_c": 0.0,
                },
            ],
        }

        code, stdout, stderr = self._run(["Москва", "--forecast"])

        self.assertEqual(code, 0)
        self.assertNotIn("Актуально на", stdout)
        self.assertIn("26.10.2026 12:00 MSK", stdout)
        self.assertIn("27.10.2026 12:00 MSK", stdout)
        self.assertNotIn("15:00 MSK", stdout)
        self.assertNotIn("21:00 MSK", stdout)
        self.assertNotIn("облачно", stdout)
        self.assertNotIn("дождь", stdout)
        self.assertEqual(stdout.count("Температура"), 2)
        self.assertIn("5 °C", stdout)
        self.assertIn("0 °C", stdout)
        self.assertEqual(stderr, "")

    @patch.object(OpenWeatherAPI, "get_weather_by_coordinates")
    def test_coordinates_extended(self, get_weather: Mock) -> None:
        get_weather.return_value = {"location": {"name": "Москва"}}

        code, _, _ = self._run(
            ["--coords", "55.7558", "37.6173", "--extended"]
        )

        self.assertEqual(code, 0)
        get_weather.assert_called_once_with(55.7558, 37.6173, extended=True)

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_api_error(self, get_weather: Mock) -> None:
        get_weather.side_effect = OpenWeatherAPIError("сервис недоступен")

        code, stdout, stderr = self._run(["Москва"])

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("Ошибка: сервис недоступен", stderr)

    def test_requires_location_when_stdin_is_not_tty(self) -> None:
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(SystemExit) as context:
                self._run([])

        self.assertEqual(context.exception.code, 2)

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_prompts_for_city_when_stdin_is_tty(self, get_weather: Mock) -> None:
        get_weather.return_value = {"location": {"name": "Москва"}}

        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            side_effect=[" Москва ", ""],
        ) as input_mock:
            code, stdout, stderr = self._run(["--json"])

        self.assertEqual(code, 0)
        self.assertEqual(
            input_mock.call_args_list,
            [
                call("Введите город: "),
                call(
                    "Выберите вариант: РАСШИРЕННАЯ ПОГОДА-1 / "
                    "ТЕКУЩАЯ ПОГОДА-2 / ПРОГНОЗ НА 5 ДНЕЙ-3: "
                ),
            ],
        )
        get_weather.assert_called_once_with("Москва", extended=False)
        self.assertEqual(
            json.loads(stdout),
            {"местоположение": {"название": "Москва"}},
        )
        self.assertEqual(stderr, "")

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_prompts_for_extended_mode(self, get_weather: Mock) -> None:
        get_weather.return_value = {"weather": {"temperature_c": 20.0}}

        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            side_effect=["Москва", "1"],
        ):
            code, stdout, _ = self._run(["--json"])

        self.assertEqual(code, 0)
        get_weather.assert_called_once_with("Москва", extended=True)
        self.assertEqual(
            json.loads(stdout),
            {"погода": {"температура_c": 20.0}},
        )

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_extended_flag_skips_extended_prompt(self, get_weather: Mock) -> None:
        get_weather.return_value = {"weather": {"pressure_hpa": 1013.0}}

        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            return_value="Москва",
        ) as input_mock:
            code, stdout, _ = self._run(["--extended", "--json"])

        self.assertEqual(code, 0)
        input_mock.assert_called_once_with("Введите город: ")
        get_weather.assert_called_once_with("Москва", extended=True)
        self.assertEqual(
            json.loads(stdout),
            {"погода": {"давление_гпа": 1013.0}},
        )

    @patch.object(OpenWeatherAPI, "get_forecast_by_city")
    def test_menu_option_three_shows_forecast(self, get_forecast: Mock) -> None:
        get_forecast.return_value = {
            "location": {"name": "Москва"},
            "forecast": [
                {
                    "datetime": "2026-10-26 09:00:00",
                    "description": "ясно",
                    "temperature_c": 5.0,
                }
            ],
        }

        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            side_effect=["Москва", "3", "2"],
        ) as input_mock:
            code, stdout, stderr = self._run([])

        self.assertEqual(code, 0)
        get_forecast.assert_called_once_with("Москва", extended=False)
        self.assertEqual(
            input_mock.call_args_list,
            [
                call("Введите город: "),
                call(
                    "Выберите вариант: РАСШИРЕННАЯ ПОГОДА-1 / "
                    "ТЕКУЩАЯ ПОГОДА-2 / ПРОГНОЗ НА 5 ДНЕЙ-3: "
                ),
                call("Введите город — 1 или выйти из приложения — 2: "),
            ],
        )
        self.assertIn("Прогноз", stdout)
        self.assertIn("26.10.2026 12:00 MSK", stdout)
        self.assertIn("5 °C", stdout)
        self.assertEqual(stderr, "")

    @patch.object(OpenWeatherAPI, "get_forecast_by_city")
    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_session_menu_requests_new_city(
        self,
        get_weather: Mock,
        get_forecast: Mock,
    ) -> None:
        get_forecast.return_value = {
            "location": {"name": "Москва"},
            "forecast": [],
        }
        get_weather.return_value = {"location": {"name": "Сочи"}}

        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            side_effect=["Москва", "3", "1", "Сочи", "2", "2"],
        ):
            code, stdout, stderr = self._run([])

        self.assertEqual(code, 0)
        get_forecast.assert_called_once_with("Москва", extended=False)
        get_weather.assert_called_once_with("Сочи", extended=False)
        self.assertIn("Москва", stdout)
        self.assertIn("Сочи", stdout)
        self.assertEqual(stderr, "")

    @patch.object(OpenWeatherAPI, "get_weather_by_city")
    def test_session_menu_repeats_on_unknown_choice(
        self,
        get_weather: Mock,
    ) -> None:
        get_weather.return_value = {"location": {"name": "Москва"}}

        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            side_effect=["Москва", "2", "x", "2"],
        ):
            code, stdout, _ = self._run([])

        self.assertEqual(code, 0)
        get_weather.assert_called_once_with("Москва", extended=False)
        self.assertIn("Неизвестный выбор. Введите 1 или 2.", stdout)

    def test_rejects_empty_prompted_city(self) -> None:
        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            return_value="   ",
        ):
            with self.assertRaises(SystemExit) as context:
                self._run([])

        self.assertEqual(context.exception.code, 2)

    def test_prompt_eof_raises_parser_error(self) -> None:
        with patch("sys.stdin.isatty", return_value=True), patch(
            "builtins.input",
            side_effect=EOFError,
        ):
            with self.assertRaises(SystemExit) as context:
                self._run([])

        self.assertEqual(context.exception.code, 2)

    def test_rejects_city_with_coordinates(self) -> None:
        with self.assertRaises(SystemExit) as context:
            self._run(["Москва", "--coords", "55.75", "37.62"])

        self.assertEqual(context.exception.code, 2)

    def test_rejects_forecast_by_coordinates(self) -> None:
        with self.assertRaises(SystemExit) as context:
            self._run(["--coords", "55.75", "37.62", "--forecast"])

        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
