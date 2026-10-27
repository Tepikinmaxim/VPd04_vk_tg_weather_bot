"""Погодный CLI OpenWeatherMap."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from OpenWeatherAPI import OpenWeatherAPI, OpenWeatherAPIError, format_result_text


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



def _print_result(result: Mapping[str, Any]) -> None:
    print(format_result_text(result), end="")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Погода OpenWeatherMap для погодного бота VK.",
        epilog=(
            "Примеры:\n"
            "  %(prog)s Москва\n"
            "  %(prog)s Москва --extended\n"
            "  %(prog)s Москва --forecast --extended\n"
            "  %(prog)s --coords 55.7558 37.6173 --extended"
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
