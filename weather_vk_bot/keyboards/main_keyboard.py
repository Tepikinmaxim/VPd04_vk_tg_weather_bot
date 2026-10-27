"""Клавиатуры главного меню и геолокации."""

from __future__ import annotations

from vkbottle import Keyboard, KeyboardButtonColor, Location, Text

BTN_WEATHER = "🌤 Погода сейчас"
BTN_FORECAST = "📅 Прогноз 5 дней"
BTN_COMPARE = "📊 Сравнить погоду"
BTN_GEO = "📍 Геолокация"
BTN_EXTENDED = "🌫 Расширенный режим"
BTN_CHANGE_CITY = "🏙 Сменить город"
BTN_HELP = "ℹ️ Помощь"
BTN_MANUAL_COORDS = "✍️ Ввести координаты"


def main_menu_keyboard() -> str:
    """Возвращает основную клавиатуру с разделами бота."""
    keyboard = Keyboard(one_time=False, inline=False)
    keyboard.add(Text(BTN_WEATHER), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text(BTN_FORECAST), color=KeyboardButtonColor.POSITIVE)
    keyboard.row()
    keyboard.add(Text(BTN_COMPARE), color=KeyboardButtonColor.PRIMARY)
    keyboard.add(Text(BTN_EXTENDED), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(BTN_GEO), color=KeyboardButtonColor.SECONDARY)
    keyboard.add(Text(BTN_CHANGE_CITY), color=KeyboardButtonColor.SECONDARY)
    keyboard.row()
    keyboard.add(Text(BTN_HELP), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def geo_keyboard() -> str:
    """Клавиатура с нативной отправкой геопозиции и ручным вводом."""
    keyboard = Keyboard(one_time=False, inline=False)
    keyboard.add(Location())
    keyboard.row()
    keyboard.add(Text(BTN_MANUAL_COORDS), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()
