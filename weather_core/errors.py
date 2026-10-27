"""Общие сообщения об ошибках погодного API."""

from __future__ import annotations

from OpenWeatherAPI import APIConnectionError, CityNotFoundError, OpenWeatherAPIError


def describe_weather_error(exc: Exception) -> str:
    if isinstance(exc, CityNotFoundError):
        return (
            "❌ Город не найден. Проверьте название и попробуйте снова.\n"
            "Например: Москва или Санкт-Петербург."
        )
    if isinstance(exc, APIConnectionError):
        return (
            "📡 Сервис погоды временно недоступен. "
            "Попробуйте ещё раз через несколько минут."
        )
    if isinstance(exc, OpenWeatherAPIError):
        return f"⚠️ Не удалось получить погоду: {exc}"
    return "⚠️ Не удалось получить погоду. Попробуйте позже."


__all__ = ("describe_weather_error",)
