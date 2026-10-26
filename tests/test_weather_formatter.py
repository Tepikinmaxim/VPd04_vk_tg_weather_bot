import unittest
from typing import Any

from weather_vk_bot.services.formatter import (
    format_air_quality,
    format_current,
    format_forecast,
    format_weather_result,
)


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
        "humidity_percent": 50.0,
        "wind_speed_ms": 2.0,
        "clouds_percent": 10.0,
    },
}

EXTENDED_RESULT = {
    **CURRENT_RESULT,
    "weather": {
        **CURRENT_RESULT["weather"],
        "pressure_hpa": 1013.0,
        "visibility_km": 10.0,
    },
    "sun": {
        "sunrise_utc": "2026-10-26T03:47:07+00:00",
        "sunset_utc": "2026-10-26T14:23:03+00:00",
    },
    "air_quality": {
        "aqi_index": 2,
        "aqi_label": "Удовлетворительное",
        "overall_aqi_index": 2,
        "overall_label": "Удовлетворительное",
        "pollutants": {
            "pm2_5": {
                "value": 12.3,
                "unit": "мкг/м³",
                "category": "Удовлетворительное",
                "exceeded": True,
            }
        },
        "human_summary": "Качество воздуха удовлетворительное.",
    },
}

FORECAST_RESULT = {
    "location": CURRENT_RESULT["location"],
    "forecast": [
        {
            "datetime": "2026-10-27 09:00:00",
            "description": "ясно",
            "temperature_c": 21.0,
            "humidity_percent": 45.0,
            "wind_speed_ms": 3.0,
            "clouds_percent": 5.0,
            "precipitation_probability_percent": 10.0,
        },
        {
            "datetime": "2026-10-27 12:00:00",
            "description": "облачно",
            "temperature_c": 22.0,
        },
        {
            "datetime": "2026-10-28 09:00:00",
            "description": "дождь",
            "temperature_c": 15.0,
        },
    ],
}


class FormatterTests(unittest.TestCase):
    def test_current_weather_has_emoji_and_units(self) -> None:
        text = format_current(CURRENT_RESULT)

        self.assertIn("🌤 Погода сейчас", text)
        self.assertIn("🌍 Город: Москва", text)
        self.assertIn("🌡 Температура: +20.5°C", text)
        self.assertIn("💧 Влажность: 50%", text)
        self.assertIn("💨 Ветер: 2 м/с", text)
        self.assertIn("──────────────", text)

    def test_extended_weather_has_sun_air_and_details(self) -> None:
        text = format_current(EXTENDED_RESULT, extended=True)

        self.assertIn("🌫 Расширенная погода", text)
        self.assertIn("🧭 Давление: 1013 гПа", text)
        self.assertIn("👁 Видимость: 10 км", text)
        self.assertIn("🌅 Рассвет: 06:47 MSK", text)
        self.assertIn("🌇 Закат: 17:23 MSK", text)
        self.assertIn("🌫 Воздух: Удовлетворительное (AQI 2)", text)
        self.assertIn("📊 PM2.5: 12.3 мкг/м³", text)
        self.assertIn("💬 Качество воздуха удовлетворительное.", text)

    def test_air_quality_without_pollutants(self) -> None:
        lines = format_air_quality(
            {
                "aqi_index": 1,
                "aqi_label": "Хорошее",
            }
        )

        self.assertIn("🌫 Воздух: Хорошее (AQI 1)", "\n".join(lines))

    def test_forecast_selects_one_block_per_day_at_noon_msk(self) -> None:
        text = format_forecast(FORECAST_RESULT)

        self.assertIn("📅 Прогноз на 5 дней", text)
        self.assertIn("🕛 Время среза: 12:00 MSK (UTC+3)", text)
        self.assertIn("📆 27.10.2026, вторник", text)
        self.assertIn("📆 28.10.2026, среда", text)
        self.assertIn("🌧 Осадки: 10%", text)
        self.assertEqual(text.count("📆"), 2)
        self.assertNotIn("Температура: +22°C", text)

    def test_forecast_without_daily_slots(self) -> None:
        text = format_forecast(
            {
                "location": {"name": "Москва"},
                "forecast": [
                    {"datetime": "2026-10-27 10:00:00", "description": "ясно"}
                ],
            }
        )

        self.assertIn("Нет данных для прогноза.", text)

    def test_missing_fields_are_replaced_by_dash(self) -> None:
        text = format_current({"location": {}, "weather": {}})

        self.assertIn("🌍 Город: неизвестно", text)
        self.assertIn("🌡 Температура: —", text)

    def test_format_weather_result_detects_forecast(self) -> None:
        self.assertIn("📅 Прогноз", format_weather_result(FORECAST_RESULT))
        self.assertIn("🌤 Погода", format_weather_result(CURRENT_RESULT))


if __name__ == "__main__":
    unittest.main()
