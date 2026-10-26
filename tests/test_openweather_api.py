import copy
import io
import json
import os
import unittest
from unittest.mock import Mock, call, patch

import requests

import OpenWeatherAPI as module
from OpenWeatherAPI import (
    APIConnectionError,
    CityNotFoundError,
    OpenWeatherAPI,
    OpenWeatherAPIError,
)


def make_response(status_code: int = 200, payload=None, *, json_error: bool = False):
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    if json_error:
        response.json.side_effect = ValueError("invalid json")
    else:
        response.json.return_value = payload
    return response


CURRENT_WEATHER = {
    "weather": [{"main": "Rain", "description": "умеренный дождь"}],
    "main": {
        "temp": 25.33,
        "feels_like": 25.59,
        "temp_min": 24.41,
        "temp_max": 26.9,
        "pressure": 1015,
        "humidity": 64,
        "sea_level": 1015,
        "grnd_level": 933,
    },
    "visibility": 10000,
    "wind": {"speed": 0.62},
    "clouds": {"all": 100},
    "sys": {
        "country": "IT",
        "sunrise": 1661834187,
        "sunset": 1661882248,
    },
    "name": "Zocca",
}

FORECAST = {
    "list": [
        {
            "dt_txt": "2022-08-30 15:00:00",
            "main": {"temp": 23.61, "humidity": 69, "pressure": 1015},
            "weather": [{"description": "небольшой дождь"}],
            "clouds": {"all": 100},
            "wind": {"speed": 0.62},
            "pop": 0.32,
        }
    ],
    "city": {
        "name": "Zocca",
        "country": "IT",
        "sunrise": 1661834187,
        "sunset": 1661882248,
    },
}

AIR_POLLUTION = {
    "list": [
        {
            "main": {"aqi": 4},
            "components": {
                "co": 203.609,
                "no2": 0.396,
                "o3": 75.102,
                "so2": 0.648,
                "pm2_5": 23.253,
                "pm10": 92.214,
            },
        }
    ]
}

DIRECT_GEOCODING = [
    {
        "name": "Zocca",
        "lat": 44.34,
        "lon": 10.99,
        "country": "IT",
        "state": "Emilia-Romagna",
    }
]

REVERSE_GEOCODING = [
    {
        "name": "Zocca",
        "lat": 44.34,
        "lon": 10.99,
        "country": "IT",
        "state": "Emilia-Romagna",
    }
]

LOCATION = {
    "name": "Zocca",
    "lat": 44.34,
    "lon": 10.99,
    "country": "IT",
    "state": "Emilia-Romagna",
}


class OpenWeatherAPITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.session = Mock(spec=requests.Session)
        self.api = OpenWeatherAPI(
            "test-key",
            timeout=1.0,
            max_retries=3,
            session=self.session,
        )
        self.sleep_patcher = patch.object(module.time, "sleep")
        self.mock_sleep = self.sleep_patcher.start()
        self.addCleanup(self.sleep_patcher.stop)

    def test_missing_api_key_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OpenWeatherAPIError) as context:
                OpenWeatherAPI(session=self.session)

        self.assertIn("OPENWEATHER_API_KEY", str(context.exception))

    def test_api_key_can_be_read_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {"OPENWEATHER_API_KEY": "env-test-key"},
            clear=True,
        ):
            client = OpenWeatherAPI(session=self.session)

        self.assertEqual(client._api_key, "env-test-key")

    def test_repr_does_not_expose_api_key(self) -> None:
        self.assertNotIn("test-key", repr(self.api))

    def test_direct_geocode_success(self) -> None:
        self.session.get.return_value = make_response(200, DIRECT_GEOCODING)

        location = self.api._direct_geocode(" Zocca ")

        self.assertEqual(location, LOCATION)
        args, kwargs = self.session.get.call_args
        self.assertEqual(args[0], OpenWeatherAPI.DIRECT_GEOCODING_URL)
        self.assertEqual(kwargs["params"]["q"], "Zocca")
        self.assertEqual(kwargs["params"]["limit"], 1)
        self.assertEqual(kwargs["params"]["appid"], "test-key")
        self.assertEqual(kwargs["timeout"], 1.0)

    def test_direct_geocode_empty_result_raises(self) -> None:
        self.session.get.return_value = make_response(200, [])

        with self.assertRaises(CityNotFoundError):
            self.api._direct_geocode("Несуществующий город")

    def test_direct_geocode_http_404_raises_city_not_found(self) -> None:
        self.session.get.return_value = make_response(
            404,
            {"message": "city not found"},
        )

        with self.assertRaises(CityNotFoundError):
            self.api._direct_geocode("Несуществующий город")

    def test_empty_city_does_not_send_request(self) -> None:
        with self.assertRaises(OpenWeatherAPIError):
            self.api._direct_geocode("   ")

        self.session.get.assert_not_called()

    def test_malformed_geocoding_result_raises(self) -> None:
        self.session.get.return_value = make_response(
            200,
            [{"name": "Zocca", "lat": "bad", "lon": 10.99, "country": "IT"}],
        )

        with self.assertRaises(OpenWeatherAPIError):
            self.api._direct_geocode("Zocca")

    def test_current_weather_request_params(self) -> None:
        self.session.get.return_value = make_response(200, CURRENT_WEATHER)

        data = self.api._current_weather(44.34, 10.99)

        self.assertEqual(data, CURRENT_WEATHER)
        args, kwargs = self.session.get.call_args
        self.assertEqual(args[0], OpenWeatherAPI.CURRENT_WEATHER_URL)
        self.assertEqual(kwargs["params"]["lat"], 44.34)
        self.assertEqual(kwargs["params"]["lon"], 10.99)
        self.assertEqual(kwargs["params"]["units"], "metric")
        self.assertEqual(kwargs["params"]["lang"], "ru")
        self.assertEqual(kwargs["params"]["appid"], "test-key")

    def test_current_weather_malformed_result_raises(self) -> None:
        self.session.get.return_value = make_response(
            200,
            {"main": {}, "wind": {}, "clouds": {}},
        )

        with self.assertRaises(OpenWeatherAPIError):
            self.api._current_weather(44.34, 10.99)

    def test_invalid_coordinates_do_not_send_request(self) -> None:
        with self.assertRaises(OpenWeatherAPIError):
            self.api.get_weather_by_coordinates(91.0, 10.99)

        self.session.get.assert_not_called()

    def test_basic_weather_format(self) -> None:
        result = self.api._format_basic_weather(CURRENT_WEATHER, LOCATION)

        self.assertEqual(result["location"], LOCATION)
        self.assertEqual(result["weather"]["description"], "умеренный дождь")
        self.assertEqual(result["weather"]["condition"], "Rain")
        self.assertEqual(result["weather"]["temperature_c"], 25.33)
        self.assertEqual(result["weather"]["feels_like_c"], 25.59)
        self.assertEqual(result["weather"]["temp_min_c"], 24.41)
        self.assertEqual(result["weather"]["temp_max_c"], 26.9)
        self.assertEqual(result["weather"]["humidity_percent"], 64.0)
        self.assertEqual(result["weather"]["wind_speed_ms"], 0.62)
        self.assertEqual(result["weather"]["clouds_percent"], 100.0)
        self.assertNotIn("pressure_hpa", result["weather"])
        self.assertNotIn("sun", result)

    def test_extended_weather_format(self) -> None:
        result = self.api._format_extended_weather(
            CURRENT_WEATHER,
            LOCATION,
            AIR_POLLUTION,
        )

        self.assertEqual(result["weather"]["pressure_hpa"], 1015.0)
        self.assertEqual(result["weather"]["sea_level_hpa"], 1015.0)
        self.assertEqual(result["weather"]["ground_level_hpa"], 933.0)
        self.assertEqual(result["weather"]["visibility_m"], 10000.0)
        self.assertEqual(result["weather"]["visibility_km"], 10.0)
        self.assertEqual(result["sun"]["sunrise_unix"], 1661834187)
        self.assertEqual(
            result["sun"]["sunrise_utc"],
            "2022-08-30T04:36:27+00:00",
        )
        self.assertEqual(result["sun"]["sunset_unix"], 1661882248)
        self.assertEqual(result["air_quality"]["aqi_index"], 4)
        self.assertEqual(result["air_quality"]["overall_aqi_index"], 3)
        self.assertEqual(result["air_quality"]["overall_label"], "Умеренное")
        self.assertEqual(result["air_quality"]["aqi_label"], "Плохое")
        self.assertEqual(
            result["air_quality"]["exceeded_pollutant_names"],
            ["PM10", "PM2.5", "O3"],
        )
        self.assertIn("умеренное", result["air_quality"]["human_summary"])
        self.assertIn("PM10", result["air_quality"]["details"])

    def test_extended_weather_allows_missing_optional_fields(self) -> None:
        weather = copy.deepcopy(CURRENT_WEATHER)
        del weather["visibility"]
        del weather["main"]["sea_level"]
        del weather["main"]["grnd_level"]
        del weather["sys"]["sunrise"]
        del weather["sys"]["sunset"]

        result = self.api._format_extended_weather(
            weather,
            LOCATION,
            AIR_POLLUTION,
        )

        self.assertIsNone(result["weather"]["visibility_m"])
        self.assertIsNone(result["weather"]["visibility_km"])
        self.assertIsNone(result["weather"]["sea_level_hpa"])
        self.assertIsNone(result["weather"]["ground_level_hpa"])
        self.assertIsNone(result["sun"]["sunrise_unix"])
        self.assertIsNone(result["sun"]["sunrise_utc"])

    def test_air_quality_analysis_of_sample(self) -> None:
        result = self.api._analyze_air_quality(AIR_POLLUTION)

        self.assertEqual(result["aqi_index"], 4)
        self.assertEqual(result["aqi_label"], "Плохое")
        self.assertEqual(result["overall_aqi_index"], 3)
        self.assertEqual(result["overall_category"], "moderate")
        self.assertEqual(result["overall_label"], "Умеренное")
        self.assertEqual(result["pollutants"]["so2"]["category_key"], "good")
        self.assertEqual(result["pollutants"]["no2"]["category_key"], "good")
        self.assertEqual(result["pollutants"]["pm10"]["category_key"], "moderate")
        self.assertEqual(result["pollutants"]["pm2_5"]["category_key"], "fair")
        self.assertEqual(result["pollutants"]["o3"]["category_key"], "fair")
        self.assertEqual(result["pollutants"]["co"]["category_key"], "good")
        self.assertEqual(
            result["exceeded_pollutants"],
            ["pm10", "pm2_5", "o3"],
        )
        self.assertEqual(
            result["exceeded_pollutant_names"],
            ["PM10", "PM2.5", "O3"],
        )
        self.assertIn("Качество воздуха умеренное", result["human_summary"])
        self.assertIn("PM10", result["human_summary"])
        self.assertIn("PM2.5", result["human_summary"])
        self.assertIn("O3", result["human_summary"])
        self.assertEqual(result["details"].count("\n"), 5)

    def test_air_quality_threshold_boundaries(self) -> None:
        boundaries = {
            "so2": [
                (0.0, "good"),
                (20.0, "fair"),
                (80.0, "moderate"),
                (250.0, "poor"),
                (350.0, "very_poor"),
            ],
            "no2": [
                (0.0, "good"),
                (40.0, "fair"),
                (70.0, "moderate"),
                (150.0, "poor"),
                (200.0, "very_poor"),
            ],
            "pm10": [
                (0.0, "good"),
                (20.0, "fair"),
                (50.0, "moderate"),
                (100.0, "poor"),
                (200.0, "very_poor"),
            ],
            "pm2_5": [
                (0.0, "good"),
                (10.0, "fair"),
                (25.0, "moderate"),
                (50.0, "poor"),
                (75.0, "very_poor"),
            ],
            "o3": [
                (0.0, "good"),
                (60.0, "fair"),
                (100.0, "moderate"),
                (140.0, "poor"),
                (180.0, "very_poor"),
            ],
            "co": [
                (0.0, "good"),
                (4400.0, "fair"),
                (9400.0, "moderate"),
                (12400.0, "poor"),
                (15400.0, "very_poor"),
            ],
        }

        for pollutant, cases in boundaries.items():
            for value, expected in cases:
                with self.subTest(pollutant=pollutant, value=value):
                    components = {
                        name: 0.0 for name in OpenWeatherAPI.POLLUTANT_ORDER
                    }
                    components[pollutant] = value
                    payload = {
                        "list": [
                            {
                                "main": {"aqi": 1},
                                "components": components,
                            }
                        ]
                    }

                    result = self.api._analyze_air_quality(payload)

                    self.assertEqual(
                        result["pollutants"][pollutant]["category_key"],
                        expected,
                    )
                    self.assertEqual(result["overall_category"], expected)
                    self.assertEqual(
                        result["overall_aqi_index"],
                        OpenWeatherAPI.CATEGORY_ORDER[expected] + 1,
                    )

    def test_air_quality_rejects_negative_component(self) -> None:
        payload = copy.deepcopy(AIR_POLLUTION)
        payload["list"][0]["components"]["pm2_5"] = -1.0

        with self.assertRaises(OpenWeatherAPIError):
            self.api._analyze_air_quality(payload)

    def test_air_quality_rejects_missing_component(self) -> None:
        payload = copy.deepcopy(AIR_POLLUTION)
        del payload["list"][0]["components"]["o3"]

        with self.assertRaises(OpenWeatherAPIError):
            self.api._analyze_air_quality(payload)

    def test_forecast_format(self) -> None:
        result = self.api._format_forecast_data(FORECAST, LOCATION)

        self.assertEqual(result["location"], LOCATION)
        self.assertEqual(len(result["forecast"]), 1)
        period = result["forecast"][0]
        self.assertEqual(period["datetime"], "2022-08-30 15:00:00")
        self.assertEqual(period["description"], "небольшой дождь")
        self.assertEqual(period["temperature_c"], 23.61)
        self.assertEqual(period["humidity_percent"], 69.0)
        self.assertEqual(period["pressure_hpa"], 1015.0)
        self.assertEqual(period["clouds_percent"], 100.0)
        self.assertEqual(period["wind_speed_ms"], 0.62)
        self.assertEqual(period["precipitation_probability"], 0.32)
        self.assertEqual(period["precipitation_probability_percent"], 32.0)
        self.assertNotIn("sun", result)
        self.assertNotIn("air_quality", result)

    def test_forecast_extended_format(self) -> None:
        result = self.api._format_forecast_data(
            FORECAST,
            LOCATION,
            extended=True,
            air_data=AIR_POLLUTION,
        )

        self.assertEqual(result["sun"]["sunrise_unix"], 1661834187)
        self.assertEqual(result["sun"]["sunset_unix"], 1661882248)
        self.assertEqual(result["air_quality"]["overall_label"], "Умеренное")

    def test_forecast_extended_requires_air_data(self) -> None:
        with self.assertRaises(OpenWeatherAPIError):
            self.api._format_forecast_data(
                FORECAST,
                LOCATION,
                extended=True,
            )

    def test_get_weather_by_city_basic(self) -> None:
        self.session.get.side_effect = [
            make_response(200, DIRECT_GEOCODING),
            make_response(200, CURRENT_WEATHER),
        ]

        result = self.api.get_weather_by_city("Zocca")

        self.assertEqual(self.session.get.call_count, 2)
        self.assertEqual(result["location"]["name"], "Zocca")
        self.assertEqual(result["weather"]["temperature_c"], 25.33)
        self.assertNotIn("air_quality", result)

    def test_get_weather_by_city_extended(self) -> None:
        self.session.get.side_effect = [
            make_response(200, DIRECT_GEOCODING),
            make_response(200, CURRENT_WEATHER),
            make_response(200, AIR_POLLUTION),
        ]

        result = self.api.get_weather_by_city("Zocca", extended=True)

        self.assertEqual(self.session.get.call_count, 3)
        self.assertEqual(result["location"]["name"], "Zocca")
        self.assertEqual(result["air_quality"]["overall_label"], "Умеренное")

    def test_get_forecast_by_city_extended(self) -> None:
        self.session.get.side_effect = [
            make_response(200, DIRECT_GEOCODING),
            make_response(200, FORECAST),
            make_response(200, AIR_POLLUTION),
        ]

        result = self.api.get_forecast_by_city("Zocca", extended=True)

        self.assertEqual(self.session.get.call_count, 3)
        self.assertEqual(result["forecast"][0]["temperature_c"], 23.61)
        self.assertEqual(result["sun"]["sunset_unix"], 1661882248)
        self.assertEqual(result["air_quality"]["overall_label"], "Умеренное")

    def test_get_weather_by_coordinates_extended(self) -> None:
        self.session.get.side_effect = [
            make_response(200, CURRENT_WEATHER),
            make_response(200, REVERSE_GEOCODING),
            make_response(200, AIR_POLLUTION),
        ]

        result = self.api.get_weather_by_coordinates(
            44.34,
            10.99,
            extended=True,
        )

        self.assertEqual(self.session.get.call_count, 3)
        self.assertEqual(result["location"]["name"], "Zocca")
        self.assertEqual(result["location"]["state"], "Emilia-Romagna")
        self.assertEqual(result["air_quality"]["overall_label"], "Умеренное")

    def test_get_weather_by_coordinates_falls_back_if_reverse_geocode_fails(self) -> None:
        self.session.get.side_effect = [
            make_response(200, CURRENT_WEATHER),
            make_response(400, {"message": "bad request"}),
        ]

        with self.assertLogs(module.LOGGER, level="WARNING"):
            result = self.api.get_weather_by_coordinates(44.34, 10.99)

        self.assertEqual(self.session.get.call_count, 2)
        self.assertEqual(result["location"]["name"], "Zocca")
        self.assertIsNone(result["location"]["state"])

    def test_invalid_api_key_is_not_retried_and_not_leaked(self) -> None:
        self.session.get.return_value = make_response(
            401,
            {"message": "Invalid API key"},
        )

        with self.assertRaises(OpenWeatherAPIError) as context:
            self.api._direct_geocode("Zocca")

        self.assertEqual(self.session.get.call_count, 1)
        self.mock_sleep.assert_not_called()
        self.assertEqual(context.exception.status_code, 401)
        self.assertNotIn("test-key", str(context.exception))

    def test_429_is_retried_with_exponential_delays(self) -> None:
        self.session.get.side_effect = [
            make_response(429, {}),
            make_response(429, {}),
            make_response(200, DIRECT_GEOCODING),
        ]

        result = self.api._direct_geocode("Zocca")

        self.assertEqual(result["name"], "Zocca")
        self.assertEqual(self.session.get.call_count, 3)
        self.assertEqual(self.mock_sleep.call_args_list, [call(1.0), call(2.0)])

    def test_server_error_retries_exhausted(self) -> None:
        self.session.get.return_value = make_response(503, {})

        with self.assertRaises(OpenWeatherAPIError) as context:
            self.api._direct_geocode("Zocca")

        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(self.session.get.call_count, 4)
        self.assertEqual(
            self.mock_sleep.call_args_list,
            [call(1.0), call(2.0), call(4.0)],
        )

    def test_network_error_retries_exhausted(self) -> None:
        self.session.get.side_effect = requests.ConnectionError("connection failed")

        with self.assertRaises(APIConnectionError):
            self.api._direct_geocode("Zocca")

        self.assertEqual(self.session.get.call_count, 4)
        self.assertEqual(
            self.mock_sleep.call_args_list,
            [call(1.0), call(2.0), call(4.0)],
        )

    def test_invalid_json_raises(self) -> None:
        self.session.get.return_value = make_response(200, json_error=True)

        with self.assertRaises(OpenWeatherAPIError):
            self.api._direct_geocode("Zocca")

        self.assertEqual(self.session.get.call_count, 1)

    def test_injected_session_is_not_closed(self) -> None:
        self.api.close()

        self.session.close.assert_not_called()

    def test_owned_session_is_closed_by_context_manager(self) -> None:
        owned_session = Mock(spec=requests.Session)
        with patch.object(
            module.requests,
            "Session",
            return_value=owned_session,
        ):
            with OpenWeatherAPI("test-key"):
                pass

        owned_session.close.assert_called_once()

    def test_invalid_timeout_is_rejected(self) -> None:
        with self.assertRaises(OpenWeatherAPIError):
            OpenWeatherAPI("test-key", timeout=0, session=self.session)

    def test_invalid_max_retries_is_rejected(self) -> None:
        with self.assertRaises(OpenWeatherAPIError):
            OpenWeatherAPI("test-key", max_retries=-1, session=self.session)


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
