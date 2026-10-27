import unittest
from typing import Any

from OpenWeatherAPI import OpenWeatherAPIError
from weather_core.services.weather_service import WeatherService


class FakeOpenWeatherAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.error: Exception | None = None

    def __enter__(self) -> "FakeOpenWeatherAPI":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def _result(self, kind: str) -> dict[str, Any]:
        return {"kind": kind}

    def get_weather_by_city(
        self,
        city: str,
        *,
        extended: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(("current", city, extended))
        if self.error:
            raise self.error
        return self._result("current")

    def get_forecast_by_city(
        self,
        city: str,
        *,
        extended: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(("forecast", city, extended))
        if self.error:
            raise self.error
        return self._result("forecast")

    def get_weather_by_coordinates(
        self,
        lat: float,
        lon: float,
        *,
        extended: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(("coords", lat, lon, extended))
        if self.error:
            raise self.error
        return self._result("coords")


class WeatherServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.api = FakeOpenWeatherAPI()
        self.service = WeatherService(api_factory=lambda: self.api)

    async def test_get_current_calls_backend(self) -> None:
        result = await self.service.get_current("Москва", extended=True)

        self.assertEqual(result, {"kind": "current"})
        self.assertEqual(self.api.calls, [("current", "Москва", True)])

    async def test_get_forecast_calls_backend(self) -> None:
        result = await self.service.get_forecast("Сочи")

        self.assertEqual(result, {"kind": "forecast"})
        self.assertEqual(self.api.calls, [("forecast", "Сочи", False)])

    async def test_get_by_coordinates_calls_backend(self) -> None:
        result = await self.service.get_by_coordinates(55.7558, 37.6173)

        self.assertEqual(result, {"kind": "coords"})
        self.assertEqual(
            self.api.calls,
            [("coords", 55.7558, 37.6173, False)],
        )

    async def test_empty_city_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            await self.service.get_current("   ")

        self.assertEqual(self.api.calls, [])

    async def test_backend_error_is_propagated(self) -> None:
        self.api.error = OpenWeatherAPIError("API недоступен")

        with self.assertRaises(OpenWeatherAPIError):
            await self.service.get_current("Москва")


if __name__ == "__main__":
    unittest.main()
