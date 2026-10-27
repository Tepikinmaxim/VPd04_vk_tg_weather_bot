"""Оформление ответов VK Weather Bot."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from OpenWeatherAPI import MSK_TIMEZONE, select_daily_forecast

SEPARATOR = "──────────────"

POLLUTANT_LABELS: dict[str, str] = {
    "so2": "SO2",
    "no2": "NO2",
    "pm10": "PM10",
    "pm2_5": "PM2.5",
    "o3": "O3",
    "co": "CO",
}
WEEKDAYS = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _text(value: Any, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _temperature(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "—"
    if number.is_integer():
        return f"{number:+.0f}°C"
    return f"{number:+.1f}°C"


def _unit(value: Any, unit: str, digits: int = 1) -> str:
    number = _number(value)
    if number is None:
        return "—"
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return f"{text} {unit}"


def _percent(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "—"
    return f"{number:g}%"


def _difference(first: Any, second: Any) -> float | None:
    first_number = _number(first)
    second_number = _number(second)
    if first_number is None or second_number is None:
        return None
    return second_number - first_number


def _amount(value: float, unit: str) -> str:
    text = f"{abs(value):.1f}".rstrip("0").rstrip(".")
    return f"{text}{unit}"


def _summary_line(
    icon: str,
    label: str,
    first_city: str,
    second_city: str,
    difference: float | None,
    unit: str,
    *,
    higher: str,
) -> str:
    if difference is None:
        return f"{icon} {label}: нет данных"
    if abs(difference) < 0.05:
        return f"{icon} {label}: одинаково"
    city = second_city if difference > 0 else first_city
    return f"{icon} {city} {higher} на {_amount(difference, unit)}"


def _time_msk(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "—"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MSK_TIMEZONE).strftime("%H:%M MSK")


def _forecast_date(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Дата не указана"
    try:
        moment = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    msk_moment = moment.astimezone(MSK_TIMEZONE)
    return f"{msk_moment:%d.%m.%Y}, {WEEKDAYS[msk_moment.weekday()]}"


def weather_city(result: Mapping[str, Any]) -> str | None:
    """Возвращает нормализованное название города из результата."""
    name = _mapping(result.get("location")).get("name")
    if not isinstance(name, str):
        return None
    normalized = name.strip()
    return normalized or None


def _city(result: Mapping[str, Any]) -> str:
    return weather_city(result) or "неизвестно"


def _actual_on() -> str:
    return f"🕒 Актуально на {datetime.now():%d.%m.%Y, %H:%M}"


def _weather_block(result: Mapping[str, Any]) -> list[str]:
    weather = _mapping(result.get("weather"))
    lines = [
        f"🌍 Город: {_city(result)}",
        _actual_on(),
        f"📝 Описание: {_text(weather.get('description'))}",
        f"🌡 Температура: {_temperature(weather.get('temperature_c'))}",
        f"🤔 Ощущается как: {_temperature(weather.get('feels_like_c'))}",
        f"💧 Влажность: {_percent(weather.get('humidity_percent'))}",
        f"💨 Ветер: {_unit(weather.get('wind_speed_ms'), 'м/с')}",
        f"☁️ Облачность: {_percent(weather.get('clouds_percent'))}",
    ]
    return lines


def format_air_quality(air_quality: Mapping[str, Any]) -> list[str]:
    """Форматирует расширенный блок качества воздуха."""
    overall_label = _text(
        air_quality.get("overall_label"),
        _text(air_quality.get("aqi_label"), "нет данных"),
    )
    overall_index = air_quality.get("overall_aqi_index")
    if overall_index is None:
        overall_index = air_quality.get("aqi_index")

    lines = [
        SEPARATOR,
        f"🌫 Воздух: {overall_label} (AQI {_text(overall_index)})",
    ]

    pollutants = _mapping(air_quality.get("pollutants"))
    for key, label in POLLUTANT_LABELS.items():
        item = _mapping(pollutants.get(key))
        if not item:
            continue
        value = _text(item.get("value"))
        unit = _text(item.get("unit"), "")
        category = _text(item.get("category"), "нет данных")
        mark = " ⚠️" if item.get("exceeded") else ""
        unit_suffix = f" {unit}" if unit else ""
        lines.append(f"📊 {label}: {value}{unit_suffix} — {category}{mark}")

    summary = _text(air_quality.get("human_summary"), "")
    if summary:
        lines.append(f"💬 {summary}")
    return lines


def format_current(
    result: Mapping[str, Any],
    *,
    extended: bool = False,
) -> str:
    """Форматирует текущую погоду или расширенный режим."""
    lines = [
        "🌫 Расширенная погода" if extended else "🌤 Погода сейчас",
        SEPARATOR,
    ]
    lines.extend(_weather_block(result))

    if extended:
        weather = _mapping(result.get("weather"))
        sun = _mapping(result.get("sun"))
        lines.extend(
            [
                SEPARATOR,
                "📊 Дополнительно",
                f"🧭 Давление: {_unit(weather.get('pressure_hpa'), 'гПа')}",
                f"👁 Видимость: {_unit(weather.get('visibility_km'), 'км')}",
                f"🌅 Рассвет: {_time_msk(sun.get('sunrise_utc'))}",
                f"🌇 Закат: {_time_msk(sun.get('sunset_utc'))}",
            ]
        )
        air_quality = result.get("air_quality")
        if isinstance(air_quality, Mapping):
            lines.extend(format_air_quality(air_quality))

    return "\n".join(lines).strip()


def _comparison_block(result: Mapping[str, Any]) -> list[str]:
    weather = _mapping(result.get("weather"))
    return [
        f"🌍 {_city(result)}",
        f"📝 {_text(weather.get('description'))}",
        f"🌡 Температура: {_temperature(weather.get('temperature_c'))}",
        f"🤔 Ощущается как: {_temperature(weather.get('feels_like_c'))}",
        f"💧 Влажность: {_percent(weather.get('humidity_percent'))}",
        f"💨 Ветер: {_unit(weather.get('wind_speed_ms'), 'м/с')}",
        f"☁️ Облачность: {_percent(weather.get('clouds_percent'))}",
    ]


def format_comparison(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> str:
    """Сравнивает текущую погоду в двух городах."""
    first_weather = _mapping(first.get("weather"))
    second_weather = _mapping(second.get("weather"))
    first_city = _city(first)
    second_city = _city(second)

    first_temperature = _number(first_weather.get("temperature_c"))
    second_temperature = _number(second_weather.get("temperature_c"))
    if (
        first_temperature is not None
        and second_temperature is not None
        and second_temperature - first_temperature >= 0.05
    ):
        warmer, cooler = second, first
    else:
        warmer, cooler = first, second

    lines = ["📊 Сравнение погоды", SEPARATOR, _actual_on()]
    lines.extend(_comparison_block(warmer))
    lines.append(SEPARATOR)
    lines.extend(_comparison_block(cooler))
    lines.append(SEPARATOR)
    lines.append("📊 Итог сравнения")

    lines.append(
        _summary_line(
            "🌡",
            "Температура",
            first_city,
            second_city,
            _difference(
                first_weather.get("temperature_c"),
                second_weather.get("temperature_c"),
            ),
            "°C",
            higher="теплее",
        )
    )
    lines.append(
        _summary_line(
            "🤔",
            "Ощущается как",
            first_city,
            second_city,
            _difference(
                first_weather.get("feels_like_c"),
                second_weather.get("feels_like_c"),
            ),
            "°C",
            higher="ощущается теплее",
        )
    )
    lines.append(
        _summary_line(
            "💧",
            "Влажность",
            first_city,
            second_city,
            _difference(
                first_weather.get("humidity_percent"),
                second_weather.get("humidity_percent"),
            ),
            " п.п.",
            higher="влажнее",
        )
    )
    lines.append(
        _summary_line(
            "💨",
            "Ветер",
            first_city,
            second_city,
            _difference(
                first_weather.get("wind_speed_ms"),
                second_weather.get("wind_speed_ms"),
            ),
            " м/с",
            higher="ветренее",
        )
    )
    lines.append(
        _summary_line(
            "☁️",
            "Облачность",
            first_city,
            second_city,
            _difference(
                first_weather.get("clouds_percent"),
                second_weather.get("clouds_percent"),
            ),
            " п.п.",
            higher="облачнее",
        )
    )
    return "\n".join(lines).strip()


def format_forecast(result: Mapping[str, Any]) -> str:
    """Форматирует пятидневный прогноз по одному блоку на день."""
    lines = [
        "📅 Прогноз на 5 дней",
        SEPARATOR,
        f"🌍 Город: {_city(result)}",
        "🕛 Прогноз на 12:00 MSK (UTC+3)",
    ]

    raw_forecast = result.get("forecast")
    forecast: Sequence[Any] = raw_forecast if isinstance(raw_forecast, list) else []
    daily = select_daily_forecast(forecast)
    if not daily:
        lines.extend([SEPARATOR, "Нет данных для прогноза."])
        return "\n".join(lines)

    for raw_item in daily:
        item = _mapping(raw_item)
        probability = item.get("precipitation_probability_percent")
        if probability is None:
            raw_probability = item.get("precipitation_probability")
            if isinstance(raw_probability, (int, float)) and not isinstance(
                raw_probability,
                bool,
            ):
                probability = raw_probability * 100.0
        lines.extend(
            [
                SEPARATOR,
                f"📆 {_forecast_date(item.get('datetime'))}",
                f"📝 Описание: {_text(item.get('description'))}",
                f"🌡 Температура: {_temperature(item.get('temperature_c'))}",
                f"💧 Влажность: {_percent(item.get('humidity_percent'))}",
                f"💨 Ветер: {_unit(item.get('wind_speed_ms'), 'м/с')}",
                f"☁️ Облачность: {_percent(item.get('clouds_percent'))}",
                f"🌧 Осадки: {_percent(probability)}",
            ]
        )

    return "\n".join(lines).strip()


def format_weather_result(result: Mapping[str, Any]) -> str:
    """Выбирает формат ответа по структуре результата."""
    forecast = result.get("forecast")
    if isinstance(forecast, list):
        return format_forecast(result)
    return format_current(result)
