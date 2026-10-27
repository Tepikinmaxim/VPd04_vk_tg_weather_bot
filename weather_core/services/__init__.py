"""Общие сервисы погодных ботов."""

from __future__ import annotations

from .formatter import (
    format_air_quality,
    format_comparison,
    format_current,
    format_forecast,
    format_weather_result,
    weather_city,
)
from .weather_service import WeatherResult, WeatherService

__all__ = (
    "WeatherResult",
    "WeatherService",
    "format_air_quality",
    "format_comparison",
    "format_current",
    "format_forecast",
    "format_weather_result",
    "weather_city",
)
