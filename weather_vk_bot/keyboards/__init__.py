"""Клавиатуры VK Weather Bot."""

from .main_keyboard import (
    BTN_BACK,
    BTN_EXTENDED,
    BTN_FORECAST,
    BTN_GEO,
    BTN_HELP,
    BTN_HOME,
    BTN_MANUAL_COORDS,
    BTN_WEATHER,
    geo_keyboard,
    main_menu_keyboard,
)
from .navigation_keyboard import city_prompt_keyboard, navigation_keyboard

__all__ = (
    "BTN_BACK",
    "BTN_EXTENDED",
    "BTN_FORECAST",
    "BTN_GEO",
    "BTN_HELP",
    "BTN_HOME",
    "BTN_MANUAL_COORDS",
    "BTN_WEATHER",
    "city_prompt_keyboard",
    "geo_keyboard",
    "main_menu_keyboard",
    "navigation_keyboard",
)
