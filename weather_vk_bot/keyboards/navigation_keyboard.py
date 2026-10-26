"""Навигационные клавиатуры."""

from __future__ import annotations

from vkbottle import Keyboard, KeyboardButtonColor, Text

from .main_keyboard import BTN_BACK, BTN_HOME


def navigation_keyboard(
    *,
    back: bool = True,
    home: bool = True,
) -> str:
    keyboard = Keyboard(one_time=False, inline=False)
    if back:
        keyboard.add(Text(BTN_BACK), color=KeyboardButtonColor.SECONDARY)
    if home:
        keyboard.add(Text(BTN_HOME), color=KeyboardButtonColor.SECONDARY)
    return keyboard.get_json()


def city_prompt_keyboard() -> str:
    return navigation_keyboard()
