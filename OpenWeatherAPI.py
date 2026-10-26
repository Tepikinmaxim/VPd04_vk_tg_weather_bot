"""Production-ready клиент OpenWeatherMap API.

Модуль предоставляет OOP-обёртку над актуальными endpoint OpenWeatherMap:
Current Weather, 5 Day Forecast, Air Pollution и Geocoding. Пользовательские
тексты формируются на русском языке, а структура результатов использует
стабильные английские ключи для интеграции с ботом или другим приложением.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from types import TracebackType
from typing import Any, Final, Mapping, Sequence

import requests
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger(__name__)
MSK_TIMEZONE: Final = timezone(timedelta(hours=3))


class OpenWeatherAPIError(Exception):
    """Базовая ошибка модуля OpenWeatherAPI."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.endpoint = endpoint


class CityNotFoundError(OpenWeatherAPIError):
    """Город не найден или Geocoding API вернул пустой результат."""


class APIConnectionError(OpenWeatherAPIError):
    """Не удалось установить соединение с OpenWeatherMap."""


def _as_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OpenWeatherAPIError(
            f"OpenWeather вернул некорректные данные: поле «{field}» должно быть объектом."
        )
    return value


def _as_list(value: Any, field: str, *, non_empty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        raise OpenWeatherAPIError(
            f"OpenWeather вернул некорректные данные: поле «{field}» должно быть массивом."
        )
    if non_empty and not value:
        raise OpenWeatherAPIError(
            f"OpenWeather вернул пустой массив в поле «{field}»."
        )
    return value


def _as_str(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise OpenWeatherAPIError(
            f"OpenWeather вернул некорректные данные: поле «{field}» должно быть строкой."
        )
    result = value.strip()
    if not result:
        raise OpenWeatherAPIError(
            f"OpenWeather вернул пустое значение в поле «{field}»."
        )
    return result


def _optional_str(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, field)


def _as_number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenWeatherAPIError(
            f"Некорректное значение поля «{field}»: ожидается число."
        )
    result = float(value)
    if not math.isfinite(result):
        raise OpenWeatherAPIError(
            f"Некорректное значение поля «{field}»: число должно быть конечным."
        )
    if minimum is not None and result < minimum:
        raise OpenWeatherAPIError(
            f"Некорректное значение поля «{field}»: минимум {minimum:g}."
        )
    if maximum is not None and result > maximum:
        raise OpenWeatherAPIError(
            f"Некорректное значение поля «{field}»: максимум {maximum:g}."
        )
    return result


def _optional_number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    return _as_number(value, field, minimum=minimum, maximum=maximum)


def _as_int(
    value: Any,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpenWeatherAPIError(
            f"Некорректное значение поля «{field}»: ожидается целое число."
        )
    if minimum is not None and value < minimum:
        raise OpenWeatherAPIError(
            f"Некорректное значение поля «{field}»: минимум {minimum}."
        )
    if maximum is not None and value > maximum:
        raise OpenWeatherAPIError(
            f"Некорректное значение поля «{field}»: максимум {maximum}."
        )
    return value


class OpenWeatherAPI:
    """Клиент OpenWeatherMap с текущей погодой, прогнозом и качеством воздуха."""

    CURRENT_WEATHER_URL: Final[str] = (
        "https://api.openweathermap.org/data/2.5/weather"
    )
    FORECAST_URL: Final[str] = "https://api.openweathermap.org/data/2.5/forecast"
    AIR_POLLUTION_URL: Final[str] = (
        "https://api.openweathermap.org/data/2.5/air_pollution"
    )
    DIRECT_GEOCODING_URL: Final[str] = (
        "https://api.openweathermap.org/geo/1.0/direct"
    )
    REVERSE_GEOCODING_URL: Final[str] = (
        "https://api.openweathermap.org/geo/1.0/reverse"
    )

    ENV_API_KEY: Final[str] = "OPENWEATHER_API_KEY"
    DEFAULT_TIMEOUT: Final[float] = 10.0
    DEFAULT_MAX_RETRIES: Final[int] = 3
    RETRY_DELAYS: Final[tuple[float, ...]] = (1.0, 2.0, 4.0)
    RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset(
        {429, 500, 502, 503, 504}
    )
    GEOCODING_LIMIT: Final[int] = 1
    UNITS: Final[str] = "metric"
    LANGUAGE: Final[str] = "ru"

    CATEGORY_LABELS: Final[Mapping[str, str]] = {
        "good": "Хорошее",
        "fair": "Удовлетворительное",
        "moderate": "Умеренное",
        "poor": "Плохое",
        "very_poor": "Очень плохое",
    }
    CATEGORY_ORDER: Final[Mapping[str, int]] = {
        "good": 0,
        "fair": 1,
        "moderate": 2,
        "poor": 3,
        "very_poor": 4,
    }
    OWM_AQI_CATEGORIES: Final[Mapping[int, str]] = {
        1: "good",
        2: "fair",
        3: "moderate",
        4: "poor",
        5: "very_poor",
    }

    POLLUTANT_ORDER: Final[tuple[str, ...]] = (
        "so2",
        "no2",
        "pm10",
        "pm2_5",
        "o3",
        "co",
    )
    POLLUTANT_SHORT_NAMES: Final[Mapping[str, str]] = {
        "so2": "SO2",
        "no2": "NO2",
        "pm10": "PM10",
        "pm2_5": "PM2.5",
        "o3": "O3",
        "co": "CO",
    }
    POLLUTANT_FULL_NAMES: Final[Mapping[str, str]] = {
        "so2": "диоксид серы (SO2)",
        "no2": "диоксид азота (NO2)",
        "pm10": "взвешенные частицы PM10",
        "pm2_5": "мелкодисперсные частицы PM2.5",
        "o3": "озон (O3)",
        "co": "угарный газ (CO)",
    }
    POLLUTANT_UNITS: Final[Mapping[str, str]] = {
        "so2": "мкг/м³",
        "no2": "мкг/м³",
        "pm10": "мкг/м³",
        "pm2_5": "мкг/м³",
        "o3": "мкг/м³",
        "co": "мкг/м³",
    }
    POLLUTANT_THRESHOLDS: Final[Mapping[str, tuple[tuple[float, str], ...]]] = {
        "so2": ((20.0, "good"), (80.0, "fair"), (250.0, "moderate"), (350.0, "poor")),
        "no2": ((40.0, "good"), (70.0, "fair"), (150.0, "moderate"), (200.0, "poor")),
        "pm10": ((20.0, "good"), (50.0, "fair"), (100.0, "moderate"), (200.0, "poor")),
        "pm2_5": ((10.0, "good"), (25.0, "fair"), (50.0, "moderate"), (75.0, "poor")),
        "o3": ((60.0, "good"), (100.0, "fair"), (140.0, "moderate"), (180.0, "poor")),
        "co": (
            (4400.0, "good"),
            (9400.0, "fair"),
            (12400.0, "moderate"),
            (15400.0, "poor"),
        ),
    }

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        """Создаёт клиент и проверяет наличие API-ключа.

        Ключ берётся из аргумента ``api_key`` или переменной окружения
        ``OPENWEATHER_API_KEY``. Переданная снаружи ``session`` не закрывается
        методом :meth:`close`.
        """
        if api_key is not None and not isinstance(api_key, str):
            raise OpenWeatherAPIError("API-ключ должен быть строкой.")

        explicit_key = (api_key or "").strip()
        env_key = (os.getenv(self.ENV_API_KEY) or "").strip()
        self._api_key = explicit_key or env_key
        if not self._api_key:
            raise OpenWeatherAPIError(
                "Не найден API-ключ OpenWeather. Заполните OPENWEATHER_API_KEY в .env."
            )

        if timeout is None:
            self._timeout = self.DEFAULT_TIMEOUT
        else:
            self._timeout = _as_number(timeout, "timeout", minimum=0.001)

        if max_retries is None:
            self._max_retries = self.DEFAULT_MAX_RETRIES
        elif (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or max_retries < 0
        ):
            raise OpenWeatherAPIError(
                "Количество повторов должно быть целым неотрицательным числом."
            )
        else:
            self._max_retries = max_retries

        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(timeout={self._timeout!r}, "
            f"max_retries={self._max_retries!r})"
        )

    def __enter__(self) -> OpenWeatherAPI:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Закрывает HTTP-сессию, созданную внутри клиента."""
        if self._owns_session:
            self._session.close()

    def _make_request(self, endpoint: str, params: Mapping[str, Any]) -> Any:
        """Выполняет GET-запрос с повторами и безопасной обработкой ошибок."""
        request_params = dict(params)
        request_params["appid"] = self._api_key
        attempts = self._max_retries + 1

        for attempt in range(attempts):
            try:
                response = self._session.get(
                    endpoint,
                    params=request_params,
                    timeout=self._timeout,
                )
            except requests.RequestException:
                if attempt < self._max_retries:
                    LOGGER.warning(
                        "Сетевая ошибка OpenWeather, повтор %s из %s",
                        attempt + 1,
                        self._max_retries,
                    )
                    self._sleep_before_retry(attempt)
                    continue
                raise APIConnectionError(
                    "Не удалось связаться с OpenWeather. Проверьте подключение "
                    "к интернету и повторите попытку.",
                    endpoint=endpoint,
                ) from None

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    raise OpenWeatherAPIError(
                        "OpenWeather вернул ответ, который не является корректным JSON.",
                        status_code=response.status_code,
                        endpoint=endpoint,
                    ) from None

            if (
                response.status_code in self.RETRYABLE_STATUS_CODES
                and attempt < self._max_retries
            ):
                LOGGER.warning(
                    "OpenWeather вернул HTTP %s, повтор %s из %s",
                    response.status_code,
                    attempt + 1,
                    self._max_retries,
                )
                self._sleep_before_retry(attempt)
                continue

            api_message = self._extract_api_message(response)
            suffix = f" {api_message}" if api_message else ""
            if response.status_code == 401:
                raise OpenWeatherAPIError(
                    "OpenWeather отклонил API-ключ. Проверьте значение "
                    f"OPENWEATHER_API_KEY в .env.{suffix}",
                    status_code=response.status_code,
                    endpoint=endpoint,
                )
            if response.status_code == 429:
                raise OpenWeatherAPIError(
                    "OpenWeather временно ограничил частоту запросов. "
                    f"Попробуйте позже.{suffix}",
                    status_code=response.status_code,
                    endpoint=endpoint,
                )
            raise OpenWeatherAPIError(
                f"OpenWeather вернул ошибку HTTP {response.status_code}.{suffix}",
                status_code=response.status_code,
                endpoint=endpoint,
            )

        raise APIConnectionError(
            "Не удалось выполнить запрос к OpenWeather.",
            endpoint=endpoint,
        )

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
        time.sleep(delay)

    def _extract_api_message(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        if not isinstance(payload, dict):
            return ""
        message = payload.get("message")
        if not isinstance(message, str):
            return ""
        sanitized = message.strip().replace(self._api_key, "***")
        return sanitized[:300]

    @staticmethod
    def _validate_coordinates(lat: Any, lon: Any) -> tuple[float, float]:
        latitude = _as_number(lat, "Широта", minimum=-90.0, maximum=90.0)
        longitude = _as_number(lon, "Долгота", minimum=-180.0, maximum=180.0)
        return latitude, longitude

    @staticmethod
    def _normalize_location(location: Mapping[str, Any]) -> dict[str, Any]:
        data = _as_mapping(dict(location), "location")
        return {
            "name": _as_str(data.get("name"), "location.name"),
            "lat": _as_number(data.get("lat"), "location.lat", minimum=-90.0, maximum=90.0),
            "lon": _as_number(
                data.get("lon"),
                "location.lon",
                minimum=-180.0,
                maximum=180.0,
            ),
            "country": _optional_str(data.get("country"), "location.country"),
            "state": _optional_str(data.get("state"), "location.state"),
        }

    @staticmethod
    def _first_weather(data: Mapping[str, Any], field: str) -> dict[str, Any]:
        items = _as_list(data.get("weather"), f"{field}.weather", non_empty=True)
        return _as_mapping(items[0], f"{field}.weather[0]")

    def _direct_geocode(self, city: str) -> dict[str, Any]:
        """Возвращает первый результат прямого геокодирования города."""
        if not isinstance(city, str):
            raise OpenWeatherAPIError("Название города должно быть строкой.")
        clean_city = city.strip()
        if not clean_city:
            raise OpenWeatherAPIError("Название города не может быть пустым.")
        if len(clean_city) > 200:
            raise OpenWeatherAPIError("Название города слишком длинное.")

        try:
            payload = self._make_request(
                self.DIRECT_GEOCODING_URL,
                {"q": clean_city, "limit": self.GEOCODING_LIMIT},
            )
        except OpenWeatherAPIError as exc:
            if exc.status_code == 404:
                raise CityNotFoundError(
                    f"Город «{clean_city}» не найден. Проверьте название."
                ) from None
            raise

        items = _as_list(payload, "ответ Direct Geocoding")
        if not items:
            raise CityNotFoundError(
                f"Город «{clean_city}» не найден. Проверьте название."
            )

        first = _as_mapping(items[0], "ответ Direct Geocoding[0]")
        latitude, longitude = self._validate_coordinates(
            first.get("lat"),
            first.get("lon"),
        )
        return {
            "name": _as_str(first.get("name"), "name"),
            "lat": latitude,
            "lon": longitude,
            "country": _as_str(first.get("country"), "country"),
            "state": _optional_str(first.get("state"), "state"),
        }

    def _reverse_geocode(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Возвращает населённый пункт по координатам или ``None``."""
        latitude, longitude = self._validate_coordinates(lat, lon)
        payload = self._make_request(
            self.REVERSE_GEOCODING_URL,
            {"lat": latitude, "lon": longitude, "limit": self.GEOCODING_LIMIT},
        )
        items = _as_list(payload, "ответ Reverse Geocoding")
        if not items:
            return None

        first = _as_mapping(items[0], "ответ Reverse Geocoding[0]")
        location_lat, location_lon = self._validate_coordinates(
            first.get("lat"),
            first.get("lon"),
        )
        return {
            "name": _as_str(first.get("name"), "name"),
            "lat": location_lat,
            "lon": location_lon,
            "country": _as_str(first.get("country"), "country"),
            "state": _optional_str(first.get("state"), "state"),
        }

    def _current_weather(self, lat: float, lon: float) -> dict[str, Any]:
        """Запрашивает текущую погоду по координатам."""
        latitude, longitude = self._validate_coordinates(lat, lon)
        payload = self._make_request(
            self.CURRENT_WEATHER_URL,
            {
                "lat": latitude,
                "lon": longitude,
                "units": self.UNITS,
                "lang": self.LANGUAGE,
            },
        )
        data = _as_mapping(payload, "ответ Current Weather")
        self._first_weather(data, "ответ Current Weather")
        return data

    def _forecast_weather(self, lat: float, lon: float) -> dict[str, Any]:
        """Запрашивает пятидневный прогноз с шагом три часа."""
        latitude, longitude = self._validate_coordinates(lat, lon)
        payload = self._make_request(
            self.FORECAST_URL,
            {
                "lat": latitude,
                "lon": longitude,
                "units": self.UNITS,
                "lang": self.LANGUAGE,
            },
        )
        data = _as_mapping(payload, "ответ Forecast")
        _as_list(data.get("list"), "ответ Forecast.list", non_empty=True)
        return data

    def _air_pollution(self, lat: float, lon: float) -> dict[str, Any]:
        """Запрашивает данные о загрязнении воздуха по координатам."""
        latitude, longitude = self._validate_coordinates(lat, lon)
        payload = self._make_request(
            self.AIR_POLLUTION_URL,
            {"lat": latitude, "lon": longitude},
        )
        data = _as_mapping(payload, "ответ Air Pollution")
        _as_list(data.get("list"), "ответ Air Pollution.list", non_empty=True)
        return data

    @classmethod
    def _classify_pollutant(cls, pollutant: str, value: float) -> str:
        for limit, category in cls.POLLUTANT_THRESHOLDS[pollutant]:
            if value < limit:
                return category
        return "very_poor"

    @staticmethod
    def _join_russian(items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return ", ".join(items[:-1]) + " и " + items[-1]

    @classmethod
    def _build_air_summary(cls, category: str, pollutant_names: list[str]) -> str:
        if category == "good":
            return (
                "Качество воздуха хорошее. Все основные загрязнители "
                "находятся в пределах безопасных значений."
            )

        joined = cls._join_russian(pollutant_names)
        if category == "fair":
            return (
                "Качество воздуха удовлетворительное. "
                f"Слегка повышено содержание: {joined}."
            )
        if category == "moderate":
            return (
                "Качество воздуха умеренное. "
                f"Выше оптимальных значений: {joined}."
            )
        if category == "poor":
            return (
                "Качество воздуха плохое. Чувствительным группам рекомендуется "
                f"сократить пребывание на улице. Выше нормы: {joined}."
            )
        return (
            "Качество воздуха очень плохое. Высокий риск для здоровья. "
            f"Выше нормы: {joined}."
        )

    def _analyze_air_quality(
        self,
        air_data: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Анализирует загрязнители и формирует человекочитаемую сводку."""
        data = _as_mapping(air_data, "ответ Air Pollution")
        items = _as_list(data.get("list"), "ответ Air Pollution.list", non_empty=True)
        first = _as_mapping(items[0], "ответ Air Pollution.list[0]")
        main = _as_mapping(first.get("main"), "list[0].main")
        components = _as_mapping(first.get("components"), "list[0].components")
        aqi_index = _as_int(
            main.get("aqi"),
            "list[0].main.aqi",
            minimum=1,
            maximum=5,
        )

        pollutant_details: dict[str, dict[str, Any]] = {}
        for pollutant in self.POLLUTANT_ORDER:
            value = _as_number(
                components.get(pollutant),
                f"list[0].components.{pollutant}",
                minimum=0.0,
            )
            category_key = self._classify_pollutant(pollutant, value)
            safe_limit = self.POLLUTANT_THRESHOLDS[pollutant][0][0]
            pollutant_details[pollutant] = {
                "value": value,
                "unit": self.POLLUTANT_UNITS[pollutant],
                "category_key": category_key,
                "category": self.CATEGORY_LABELS[category_key],
                "safe_limit": safe_limit,
                "exceeded": category_key != "good",
            }

        worst_pollutant = max(
            self.POLLUTANT_ORDER,
            key=lambda pollutant: self.CATEGORY_ORDER[
                pollutant_details[pollutant]["category_key"]
            ],
        )
        overall_category = pollutant_details[worst_pollutant]["category_key"]
        exceeded = sorted(
            (
                pollutant
                for pollutant in self.POLLUTANT_ORDER
                if pollutant_details[pollutant]["exceeded"]
            ),
            key=lambda pollutant: (
                -self.CATEGORY_ORDER[pollutant_details[pollutant]["category_key"]],
                self.POLLUTANT_ORDER.index(pollutant),
            ),
        )
        exceeded_names = [
            self.POLLUTANT_SHORT_NAMES[pollutant] for pollutant in exceeded
        ]

        owm_category = self.OWM_AQI_CATEGORIES[aqi_index]
        human_summary = self._build_air_summary(overall_category, exceeded_names)
        details = "\n".join(
            (
                f"{self.POLLUTANT_FULL_NAMES[pollutant]}: "
                f"{pollutant_details[pollutant]['value']:g} "
                f"{pollutant_details[pollutant]['unit']} — "
                f"{pollutant_details[pollutant]['category']}."
            )
            for pollutant in self.POLLUTANT_ORDER
        )

        return {
            "aqi_index": aqi_index,
            "aqi_label": self.CATEGORY_LABELS[owm_category],
            "aqi_category": owm_category,
            "overall_aqi_index": self.CATEGORY_ORDER[overall_category] + 1,
            "overall_category": overall_category,
            "overall_label": self.CATEGORY_LABELS[overall_category],
            "pollutants": pollutant_details,
            "exceeded_pollutants": exceeded,
            "exceeded_pollutant_names": exceeded_names,
            "human_summary": human_summary,
            "details": details,
        }

    @staticmethod
    def _format_timestamp(value: Any, field: str) -> tuple[int | None, str | None]:
        if value is None:
            return None, None
        timestamp = int(_as_number(value, field, minimum=0.0))
        try:
            utc_value = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise OpenWeatherAPIError(
                f"Некорректная временная метка в поле «{field}»."
            ) from exc
        return timestamp, utc_value.isoformat()

    def _format_sun(
        self,
        source: Mapping[str, Any],
        field_prefix: str,
    ) -> dict[str, Any]:
        sunrise_unix, sunrise_utc = self._format_timestamp(
            source.get("sunrise"),
            f"{field_prefix}.sunrise",
        )
        sunset_unix, sunset_utc = self._format_timestamp(
            source.get("sunset"),
            f"{field_prefix}.sunset",
        )
        return {
            "sunrise_unix": sunrise_unix,
            "sunrise_utc": sunrise_utc,
            "sunset_unix": sunset_unix,
            "sunset_utc": sunset_utc,
        }

    def _format_basic_weather(
        self,
        weather_data: Mapping[str, Any],
        location: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Формирует базовый результат текущей погоды."""
        data = _as_mapping(weather_data, "ответ Current Weather")
        main = _as_mapping(data.get("main"), "main")
        weather_item = self._first_weather(data, "ответ Current Weather")
        wind = _as_mapping(data.get("wind"), "wind")
        clouds = _as_mapping(data.get("clouds"), "clouds")

        return {
            "location": self._normalize_location(location),
            "weather": {
                "description": _as_str(weather_item.get("description"), "weather.description"),
                "condition": _optional_str(weather_item.get("main"), "weather.main"),
                "temperature_c": _as_number(main.get("temp"), "main.temp"),
                "feels_like_c": _as_number(
                    main.get("feels_like"),
                    "main.feels_like",
                ),
                "temp_min_c": _as_number(main.get("temp_min"), "main.temp_min"),
                "temp_max_c": _as_number(main.get("temp_max"), "main.temp_max"),
                "humidity_percent": _as_number(
                    main.get("humidity"),
                    "main.humidity",
                    minimum=0.0,
                    maximum=100.0,
                ),
                "wind_speed_ms": _as_number(
                    wind.get("speed"),
                    "wind.speed",
                    minimum=0.0,
                ),
                "clouds_percent": _as_number(
                    clouds.get("all"),
                    "clouds.all",
                    minimum=0.0,
                    maximum=100.0,
                ),
            },
        }

    def _format_extended_weather(
        self,
        weather_data: Mapping[str, Any],
        location: Mapping[str, Any],
        air_data: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Дополняет текущую погоду давлением, видимостью, солнцем и воздухом."""
        data = _as_mapping(weather_data, "ответ Current Weather")
        main = _as_mapping(data.get("main"), "main")
        sys_data = _as_mapping(data.get("sys"), "sys")
        result = self._format_basic_weather(data, location)

        visibility = _optional_number(
            data.get("visibility"),
            "visibility",
            minimum=0.0,
        )
        result["weather"].update(
            {
                "pressure_hpa": _as_number(
                    main.get("pressure"),
                    "main.pressure",
                    minimum=0.0,
                ),
                "sea_level_hpa": _optional_number(
                    main.get("sea_level"),
                    "main.sea_level",
                    minimum=0.0,
                ),
                "ground_level_hpa": _optional_number(
                    main.get("grnd_level"),
                    "main.grnd_level",
                    minimum=0.0,
                ),
                "visibility_m": visibility,
                "visibility_km": None if visibility is None else visibility / 1000.0,
            }
        )
        result["sun"] = self._format_sun(sys_data, "sys")
        result["air_quality"] = self._analyze_air_quality(air_data)
        return result

    def _format_forecast_data(
        self,
        forecast_data: Mapping[str, Any],
        location: Mapping[str, Any],
        *,
        extended: bool = False,
        air_data: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Формирует список трёхчасовых периодов прогноза."""
        data = _as_mapping(forecast_data, "ответ Forecast")
        raw_items = _as_list(
            data.get("list"),
            "ответ Forecast.list",
            non_empty=True,
        )
        forecast: list[dict[str, Any]] = []

        for index, raw_item in enumerate(raw_items):
            item = _as_mapping(raw_item, f"list[{index}]")
            main = _as_mapping(item.get("main"), f"list[{index}].main")
            weather_item = self._first_weather(item, f"list[{index}]")
            clouds = _as_mapping(item.get("clouds"), f"list[{index}].clouds")
            wind = _as_mapping(item.get("wind"), f"list[{index}].wind")
            precipitation_probability = _as_number(
                item.get("pop"),
                f"list[{index}].pop",
                minimum=0.0,
                maximum=1.0,
            )
            forecast.append(
                {
                    "datetime": _as_str(item.get("dt_txt"), f"list[{index}].dt_txt"),
                    "description": _as_str(
                        weather_item.get("description"),
                        f"list[{index}].weather.description",
                    ),
                    "temperature_c": _as_number(
                        main.get("temp"),
                        f"list[{index}].main.temp",
                    ),
                    "humidity_percent": _as_number(
                        main.get("humidity"),
                        f"list[{index}].main.humidity",
                        minimum=0.0,
                        maximum=100.0,
                    ),
                    "pressure_hpa": _as_number(
                        main.get("pressure"),
                        f"list[{index}].main.pressure",
                        minimum=0.0,
                    ),
                    "clouds_percent": _as_number(
                        clouds.get("all"),
                        f"list[{index}].clouds.all",
                        minimum=0.0,
                        maximum=100.0,
                    ),
                    "wind_speed_ms": _as_number(
                        wind.get("speed"),
                        f"list[{index}].wind.speed",
                        minimum=0.0,
                    ),
                    "precipitation_probability": precipitation_probability,
                    "precipitation_probability_percent": round(
                        precipitation_probability * 100.0,
                        1,
                    ),
                }
            )

        result: dict[str, Any] = {
            "location": self._normalize_location(location),
            "forecast": forecast,
        }
        if extended:
            if air_data is None:
                raise OpenWeatherAPIError(
                    "Для расширенного прогноза требуются данные о качестве воздуха."
                )
            city = _as_mapping(data.get("city"), "city")
            result["sun"] = self._format_sun(city, "city")
            result["air_quality"] = self._analyze_air_quality(air_data)
        return result

    def get_weather_by_city(
        self,
        city: str,
        extended: bool = False,
    ) -> dict[str, Any]:
        """Возвращает текущую погоду по названию города."""
        location = self._direct_geocode(city)
        weather = self._current_weather(location["lat"], location["lon"])
        if not extended:
            return self._format_basic_weather(weather, location)

        air = self._air_pollution(location["lat"], location["lon"])
        return self._format_extended_weather(weather, location, air)

    def get_forecast_by_city(
        self,
        city: str,
        extended: bool = False,
    ) -> dict[str, Any]:
        """Возвращает пятидневный прогноз по названию города."""
        location = self._direct_geocode(city)
        forecast = self._forecast_weather(location["lat"], location["lon"])
        air = (
            self._air_pollution(location["lat"], location["lon"])
            if extended
            else None
        )
        return self._format_forecast_data(
            forecast,
            location,
            extended=extended,
            air_data=air,
        )

    def get_weather_by_coordinates(
        self,
        lat: float,
        lon: float,
        extended: bool = False,
    ) -> dict[str, Any]:
        """Возвращает текущую погоду по координатам."""
        latitude, longitude = self._validate_coordinates(lat, lon)
        weather = self._current_weather(latitude, longitude)

        try:
            reverse_location = self._reverse_geocode(latitude, longitude)
        except OpenWeatherAPIError as exc:
            LOGGER.warning(
                "Не удалось определить населённый пункт по координатам: %s",
                exc,
            )
            reverse_location = None

        location = self._build_coordinate_location(
            latitude,
            longitude,
            weather,
            reverse_location,
        )
        if not extended:
            return self._format_basic_weather(weather, location)

        air = self._air_pollution(latitude, longitude)
        return self._format_extended_weather(weather, location, air)

    def _build_coordinate_location(
        self,
        lat: float,
        lon: float,
        weather_data: Mapping[str, Any],
        reverse_location: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if reverse_location is not None:
            return self._normalize_location(reverse_location)

        data = _as_mapping(weather_data, "ответ Current Weather")
        name = _optional_str(data.get("name"), "name")
        if name is None:
            name = f"Координаты {lat:.4f}, {lon:.4f}"

        sys_data = data.get("sys")
        country = (
            _optional_str(sys_data.get("country"), "sys.country")
            if isinstance(sys_data, dict)
            else None
        )
        return {
            "name": name,
            "lat": lat,
            "lon": lon,
            "country": country,
            "state": None,
        }


CLI_KEY_TRANSLATIONS = {
    "location": "местоположение",
    "name": "название",
    "lat": "широта",
    "lon": "долгота",
    "country": "страна",
    "state": "регион",
    "weather": "погода",
    "description": "описание",
    "condition": "состояние",
    "temperature_c": "температура_c",
    "feels_like_c": "ощущается_как_c",
    "temp_min_c": "температура_мин_c",
    "temp_max_c": "температура_макс_c",
    "humidity_percent": "влажность_процент",
    "wind_speed_ms": "скорость_ветра_м_с",
    "clouds_percent": "облачность_процент",
    "pressure_hpa": "давление_гпа",
    "sea_level_hpa": "давление_на_уровне_моря_гпа",
    "ground_level_hpa": "давление_на_уровне_земли_гпа",
    "visibility_m": "видимость_м",
    "visibility_km": "видимость_км",
    "sun": "солнце",
    "sunrise_unix": "восход_unix",
    "sunrise_utc": "восход_utc",
    "sunset_unix": "закат_unix",
    "sunset_utc": "закат_utc",
    "air_quality": "качество_воздуха",
    "aqi_index": "индекс_aqi",
    "aqi_label": "описание_aqi",
    "aqi_category": "категория_aqi",
    "overall_aqi_index": "общий_индекс_aqi",
    "overall_category": "общая_категория",
    "overall_label": "общее_описание",
    "pollutants": "загрязнители",
    "value": "значение",
    "unit": "единица",
    "category_key": "ключ_категории",
    "category": "категория",
    "safe_limit": "безопасный_предел",
    "exceeded": "превышен",
    "exceeded_pollutants": "превышенные_загрязнители",
    "exceeded_pollutant_names": "названия_превышенных_загрязнителей",
    "human_summary": "краткое_описание",
    "details": "подробности",
    "forecast": "прогноз",
    "datetime": "дата_время",
    "precipitation_probability": "вероятность_осадков",
    "precipitation_probability_percent": "вероятность_осадков_процент",
}


def _translate_cli_keys(value: Any) -> Any:
    """Переводит ключи результата для CLI, не меняя ответ библиотеки."""
    if isinstance(value, dict):
        return {
            CLI_KEY_TRANSLATIONS.get(key, key): _translate_cli_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_translate_cli_keys(item) for item in value]
    return value


POLLUTANT_DISPLAY_NAMES = {
    "so2": "SO2",
    "no2": "NO2",
    "pm10": "PM10",
    "pm2_5": "PM2.5",
    "o3": "O3",
    "co": "CO",
}


def _format_value(value: Any) -> str:
    if value is None:
        return "нет данных"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (int, float)):
        return f"{value:.12g}"
    return str(value)


def _format_with_unit(value: Any, unit: str) -> str:
    text = _format_value(value)
    if text == "нет данных" or not unit:
        return text
    return f"{text} {unit}"


def _format_utc(value: Any, unix_value: Any = None) -> str:
    if isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            pass
        else:
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return moment.astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    if isinstance(unix_value, (int, float)) and not isinstance(unix_value, bool):
        try:
            moment = datetime.fromtimestamp(unix_value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
        else:
            return moment.strftime("%d.%m.%Y %H:%M UTC")
    return "нет данных"


def _parse_forecast_moment(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _format_forecast_datetime(value: Any) -> str:
    moment = _parse_forecast_moment(value)
    if moment is None:
        return _format_value(value)
    return moment.astimezone(MSK_TIMEZONE).strftime("%d.%m.%Y %H:%M MSK")


def _select_daily_forecast(forecast: Sequence[Any]) -> list[Mapping[str, Any]]:
    """Оставляет по одному периоду на день — 12:00 MSK (09:00 UTC)."""
    selected: dict[date, Mapping[str, Any]] = {}
    for raw_item in forecast:
        if not isinstance(raw_item, Mapping):
            continue
        moment = _parse_forecast_moment(raw_item.get("datetime"))
        if moment is None:
            continue
        msk_moment = moment.astimezone(MSK_TIMEZONE)
        if msk_moment.hour != 12 or msk_moment.minute != 0:
            continue
        selected[msk_moment.date()] = raw_item
    return [selected[day] for day in sorted(selected)]


def _format_aqi(index: Any, label: Any) -> str:
    index_text = _format_value(index)
    label_text = _format_value(label)
    if label_text == "нет данных":
        return index_text
    return f"{index_text} ({label_text})"


def _format_rows(
    rows: Sequence[tuple[str, str]],
    indent: str = "  ",
) -> list[str]:
    if not rows:
        return []
    width = max(len(label) for label, _ in rows)
    return [f"{indent}{label:<{width}} — {value}" for label, value in rows]


def _format_section(
    title: str,
    rows: Sequence[tuple[str, str]],
) -> list[str]:
    lines = _format_rows(rows)
    if not lines:
        return []
    return [title, *lines, ""]


def _format_location(result: Mapping[str, Any]) -> list[str]:
    location = result.get("location")
    if not isinstance(location, Mapping):
        return []
    return _format_section(
        "Местоположение",
        [
            ("Название", _format_value(location.get("name"))),
            ("Широта", _format_value(location.get("lat"))),
            ("Долгота", _format_value(location.get("lon"))),
            ("Страна", _format_value(location.get("country"))),
            ("Регион", _format_value(location.get("state"))),
        ],
    )


def _format_current_weather(result: Mapping[str, Any]) -> list[str]:
    weather = result.get("weather")
    if not isinstance(weather, Mapping):
        return []
    rows = [
        ("Описание", _format_value(weather.get("description"))),
        ("Состояние", _format_value(weather.get("condition"))),
        ("Температура", _format_with_unit(weather.get("temperature_c"), "°C")),
        ("Ощущается как", _format_with_unit(weather.get("feels_like_c"), "°C")),
        ("Температура (мин.)", _format_with_unit(weather.get("temp_min_c"), "°C")),
        ("Температура (макс.)", _format_with_unit(weather.get("temp_max_c"), "°C")),
        ("Влажность", _format_with_unit(weather.get("humidity_percent"), "%")),
        ("Скорость ветра", _format_with_unit(weather.get("wind_speed_ms"), "м/с")),
        ("Облачность", _format_with_unit(weather.get("clouds_percent"), "%")),
    ]
    if "pressure_hpa" in weather:
        rows.append(
            ("Давление", _format_with_unit(weather.get("pressure_hpa"), "гПа"))
        )
    if "sea_level_hpa" in weather:
        rows.append(
            (
                "Давление на уровне моря",
                _format_with_unit(weather.get("sea_level_hpa"), "гПа"),
            )
        )
    if "ground_level_hpa" in weather:
        rows.append(
            (
                "Давление на уровне земли",
                _format_with_unit(weather.get("ground_level_hpa"), "гПа"),
            )
        )
    if "visibility_km" in weather:
        rows.append(
            ("Видимость", _format_with_unit(weather.get("visibility_km"), "км"))
        )
    elif "visibility_m" in weather:
        rows.append(
            ("Видимость", _format_with_unit(weather.get("visibility_m"), "м"))
        )
    return _format_section("Погода", rows)


def _format_sun(sun: Mapping[str, Any]) -> list[str]:
    return _format_section(
        "Солнце",
        [
            (
                "Восход",
                _format_utc(sun.get("sunrise_utc"), sun.get("sunrise_unix")),
            ),
            (
                "Закат",
                _format_utc(sun.get("sunset_utc"), sun.get("sunset_unix")),
            ),
        ],
    )


def _format_air_quality(air: Mapping[str, Any]) -> list[str]:
    rows = [
        ("Индекс AQI", _format_aqi(air.get("aqi_index"), air.get("aqi_label"))),
        (
            "Общий индекс AQI",
            _format_aqi(air.get("overall_aqi_index"), air.get("overall_label")),
        ),
        ("Краткое описание", _format_value(air.get("human_summary"))),
    ]
    exceeded_names = air.get("exceeded_pollutant_names")
    if isinstance(exceeded_names, list):
        exceeded_text = ", ".join(str(name) for name in exceeded_names) or "нет"
        rows.append(("Превышены", exceeded_text))
    lines = _format_section("Качество воздуха", rows)

    pollutants = air.get("pollutants")
    if not isinstance(pollutants, Mapping):
        return lines
    pollutant_rows: list[tuple[str, str]] = []
    for key, details in pollutants.items():
        if not isinstance(details, Mapping):
            continue
        name = POLLUTANT_DISPLAY_NAMES.get(str(key), str(key).upper())
        unit = _format_value(details.get("unit"))
        if unit == "нет данных":
            unit = ""
        text = _format_with_unit(details.get("value"), unit)
        category = _format_value(details.get("category"))
        if category != "нет данных":
            text += f", {category}"
        safe_limit = details.get("safe_limit")
        if safe_limit is not None:
            text += f", предел {_format_with_unit(safe_limit, unit)}"
        if details.get("exceeded"):
            text += ", превышен"
        pollutant_rows.append((name, text))
    return lines + _format_section("Загрязнители", pollutant_rows)


def _format_forecast(forecast: Sequence[Any]) -> list[str]:
    lines = [
        "Прогноз на 5 дней",
        "  По одному блоку на день; время — 12:00 MSK (UTC+3).",
        "  OpenWeatherMap отдаёт данные в UTC; 12:00 MSK = 09:00 UTC.",
        "",
    ]
    daily_forecast = _select_daily_forecast(forecast)
    if not daily_forecast:
        return [*lines, "  нет данных", ""]
    for raw_item in daily_forecast:
        if not isinstance(raw_item, Mapping):
            continue
        lines.append(f"  {_format_forecast_datetime(raw_item.get('datetime'))}")
        probability = raw_item.get("precipitation_probability_percent")
        if probability is None:
            raw_probability = raw_item.get("precipitation_probability")
            if isinstance(raw_probability, (int, float)) and not isinstance(
                raw_probability,
                bool,
            ):
                probability = raw_probability * 100.0
        rows = [
            ("Описание", _format_value(raw_item.get("description"))),
            (
                "Температура",
                _format_with_unit(raw_item.get("temperature_c"), "°C"),
            ),
            (
                "Влажность",
                _format_with_unit(raw_item.get("humidity_percent"), "%"),
            ),
            (
                "Давление",
                _format_with_unit(raw_item.get("pressure_hpa"), "гПа"),
            ),
            (
                "Облачность",
                _format_with_unit(raw_item.get("clouds_percent"), "%"),
            ),
            (
                "Скорость ветра",
                _format_with_unit(raw_item.get("wind_speed_ms"), "м/с"),
            ),
        ]
        if probability is not None:
            rows.append(
                ("Вероятность осадков", _format_with_unit(probability, "%"))
            )
        lines.extend(_format_rows(rows, indent="    "))
        lines.append("")
    return lines


def format_result_text(result: Mapping[str, Any]) -> str:
    """Возвращает готовый текст результата для CLI и VK-бота."""
    lines: list[str] = []
    lines.extend(_format_location(result))
    forecast = result.get("forecast")
    if isinstance(forecast, list):
        lines.extend(_format_forecast(forecast))
    else:
        lines.extend(_format_current_weather(result))
    sun = result.get("sun")
    if isinstance(sun, Mapping):
        lines.extend(_format_sun(sun))
    air_quality = result.get("air_quality")
    if isinstance(air_quality, Mapping):
        lines.extend(_format_air_quality(air_quality))
    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"


def _print_result(result: Mapping[str, Any]) -> None:
    print(format_result_text(result), end="")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Погода OpenWeatherMap для погодного бота VK.",
        epilog=(
            "Примеры:\n"
            "  python %(prog)s Москва\n"
            "  python %(prog)s Москва --extended\n"
            "  python %(prog)s Москва --forecast --extended\n"
            "  python %(prog)s --coords 55.7558 37.6173 --extended"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "city",
        nargs="?",
        help="Название города; при пробелах заключите в кавычки.",
    )
    parser.add_argument(
        "--coords",
        nargs=2,
        type=float,
        metavar=("LAT", "LON"),
        help="Координаты: широта и долгота.",
    )
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Добавить давление, видимость, восход/закат и качество воздуха.",
    )
    parser.add_argument(
        "--forecast",
        action="store_true",
        help="Показать прогноз на пять дней вместо текущей погоды.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывести JSON вместо текста.",
    )
    return parser


def _prompt_city(parser: argparse.ArgumentParser) -> str:
    try:
        city = input("Введите город: ").strip()
    except EOFError:
        parser.error("Не удалось прочитать название города.")
    if not city:
        parser.error("Название города не может быть пустым.")
    return city


def _prompt_variant() -> tuple[bool, bool]:
    try:
        answer = input(
            "Выберите вариант: РАСШИРЕННАЯ ПОГОДА-1 / "
            "ТЕКУЩАЯ ПОГОДА-2 / ПРОГНОЗ НА 5 ДНЕЙ-3: "
        )
    except EOFError:
        answer = ""
    choice = answer.strip().lower()
    extended = choice in {"1", "y", "yes", "д", "да"}
    forecast = choice in {"3", "прогноз", "forecast"}
    return extended, forecast


def _prompt_continue() -> bool:
    while True:
        try:
            answer = input("Введите город — 1 или выйти из приложения — 2: ")
        except EOFError:
            return False
        choice = answer.strip()
        if choice == "1":
            return True
        if choice in {"2", ""}:
            return False
        print("Неизвестный выбор. Введите 1 или 2.")


def main(argv: Sequence[str] | None = None) -> int:
    """Запускает CLI и возвращает код завершения."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.city is not None and args.coords is not None:
        parser.error("Укажите город или координаты, но не оба варианта.")
    if args.forecast and args.coords is not None:
        parser.error("Прогноз по координатам не поддерживается; укажите город.")

    interactive = args.city is None and args.coords is None
    if interactive and not sys.stdin.isatty():
        parser.error("Укажите город или координаты (--coords LAT LON).")

    base_extended = args.extended
    base_forecast = args.forecast

    while True:
        if interactive:
            args.city = _prompt_city(parser)
            args.extended = base_extended
            args.forecast = base_forecast
            if not args.extended and not args.forecast:
                args.extended, choose_forecast = _prompt_variant()
                if choose_forecast:
                    args.forecast = True

        try:
            with OpenWeatherAPI() as api:
                if args.forecast:
                    result = api.get_forecast_by_city(
                        args.city,
                        extended=args.extended,
                    )
                elif args.coords is not None:
                    latitude, longitude = args.coords
                    result = api.get_weather_by_coordinates(
                        latitude,
                        longitude,
                        extended=args.extended,
                    )
                else:
                    result = api.get_weather_by_city(
                        args.city,
                        extended=args.extended,
                    )
        except OpenWeatherAPIError as exc:
            print(f"Ошибка: {exc}", file=sys.stderr)
            return 1

        if args.json:
            print(
                json.dumps(
                    _translate_cli_keys(result),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            _print_result(result)

        if not interactive or args.json:
            return 0
        if not _prompt_continue():
            return 0
        args.city = None


if __name__ == "__main__":
    raise SystemExit(main())
