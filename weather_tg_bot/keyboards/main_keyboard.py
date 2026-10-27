"""Клавиатуры Telegram-бота."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from weather_core.buttons import (
    BTN_BACK,
    BTN_CHANGE_CITY,
    BTN_COMPARE,
    BTN_EXTENDED,
    BTN_FORECAST,
    BTN_GEO,
    BTN_HELP,
    BTN_MANUAL_COORDS,
    BTN_WEATHER,
)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Возвращает основную reply-клавиатуру."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_WEATHER), KeyboardButton(text=BTN_FORECAST)],
            [KeyboardButton(text=BTN_COMPARE), KeyboardButton(text=BTN_EXTENDED)],
            [KeyboardButton(text=BTN_GEO), KeyboardButton(text=BTN_CHANGE_CITY)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def geo_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура геопозиции и ручного ввода координат."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_GEO, request_location=True)],
            [KeyboardButton(text=BTN_MANUAL_COORDS)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


__all__ = ("geo_keyboard", "main_menu_keyboard")
