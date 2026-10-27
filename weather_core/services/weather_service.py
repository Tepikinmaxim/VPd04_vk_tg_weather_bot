"""Асинхронный сервисный слой между VKBottle и OpenWeatherAPI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from OpenWeatherAPI import OpenWeatherAPI

WeatherResult = dict[str, Any]
APIFactory = Callable[[], OpenWeatherAPI]


class WeatherService:
    """Выполняет синхронные запросы OpenWeather в отдельных потоках."""

    def __init__(self, api_factory: APIFactory = OpenWeatherAPI) -> None:
        self._api_factory = api_factory

    async def get_current(
        self,
        city: str,
        *,
        extended: bool = False,
    ) -> WeatherResult:
        city = self._validate_city(city)
        return await asyncio.to_thread(self._get_current_sync, city, extended)

    async def get_forecast(
        self,
        city: str,
        *,
        extended: bool = False,
    ) -> WeatherResult:
        city = self._validate_city(city)
        return await asyncio.to_thread(self._get_forecast_sync, city, extended)

    async def get_by_coordinates(
        self,
        lat: float,
        lon: float,
        *,
        extended: bool = False,
    ) -> WeatherResult:
        return await asyncio.to_thread(
            self._get_by_coordinates_sync,
            lat,
            lon,
            extended,
        )

    def _get_current_sync(self, city: str, extended: bool) -> WeatherResult:
        with self._api_factory() as api:
            return api.get_weather_by_city(city, extended=extended)

    def _get_forecast_sync(self, city: str, extended: bool) -> WeatherResult:
        with self._api_factory() as api:
            return api.get_forecast_by_city(city, extended=extended)

    def _get_by_coordinates_sync(
        self,
        lat: float,
        lon: float,
        extended: bool,
    ) -> WeatherResult:
        with self._api_factory() as api:
            return api.get_weather_by_coordinates(lat, lon, extended=extended)

    @staticmethod
    def _validate_city(city: str) -> str:
        normalized = city.strip()
        if not normalized:
            raise ValueError("Название города не может быть пустым.")
        return normalized
