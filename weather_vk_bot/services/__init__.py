"""Сервисы VK Weather Bot."""

from __future__ import annotations

from weather_core.services.formatter import (
    format_air_quality,
    format_current,
    format_forecast,
    format_weather_result,
    weather_city,
)
from weather_core.services.weather_service import WeatherResult, WeatherService

from .state_manager import BotState, StateManager, UserContext

__all__ = (
    "BotState",
    "StateManager",
    "UserContext",
    "WeatherResult",
    "WeatherService",
    "format_air_quality",
    "format_current",
    "format_forecast",
    "format_weather_result",
    "weather_city",
)
