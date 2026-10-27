"""Сценарий сравнения текущей погоды в двух городах."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from typing import Any

from vkbottle.bot import Bot, Message

from weather_vk_bot.keyboards import BTN_COMPARE, main_menu_keyboard
from weather_vk_bot.services.formatter import format_comparison, weather_city
from weather_vk_bot.services.state_manager import BotState

from .common import (
    COMPARE_CITY_1_PROMPT,
    COMPARE_CITY_2_PROMPT,
    HandlerDeps,
    message_text,
    prompt_for_city,
    reply_weather_error,
    send_text,
)


_COMPARE_CITY_EXAMPLES = ("Москва", "Санкт-Петербург", "Сочи", "Казань")


def _city_key(value: str) -> str:
    normalized = value.casefold().replace("ё", "е")
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    normalized = " ".join(normalized.split())
    for prefix in ("городской округ ", "город ", "г "):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :]
    return normalized


def _comparison_example(first_city: str) -> str | None:
    if not re.search(r"[а-яё]", first_city.casefold()):
        return None
    first_key = _city_key(first_city)
    for city in _COMPARE_CITY_EXAMPLES:
        if _city_key(city) != first_key:
            return city
    return None


def _coordinates(result: Mapping[str, Any]) -> tuple[float, float] | None:
    location = result.get("location")
    if not isinstance(location, Mapping):
        return None
    lat = location.get("lat")
    lon = location.get("lon")
    if isinstance(lat, bool) or isinstance(lon, bool):
        return None
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return (round(float(lat), 6), round(float(lon), 6))


def _same_location(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> bool:
    first_name = weather_city(first)
    second_name = weather_city(second)
    if (
        first_name
        and second_name
        and _city_key(first_name) == _city_key(second_name)
    ):
        return True

    first_coordinates = _coordinates(first)
    return (
        first_coordinates is not None
        and first_coordinates == _coordinates(second)
    )


def _second_city_prompt(first_city: str, *, duplicate: bool = False) -> str:
    lines: list[str] = []
    if duplicate:
        lines.append("⚠️ Этот город уже выбран первым. Введите другой город.")
    lines.append(f"📊 Первый город: {first_city}")
    lines.append(COMPARE_CITY_2_PROMPT)
    example = _comparison_example(first_city)
    if example:
        lines.append(f"Например: {example}.")
    return "\n".join(lines)


async def _prompt_for_second_city(
    message: Message,
    deps: HandlerDeps,
    first_city: str,
    *,
    duplicate: bool = False,
) -> None:
    await deps.states.set_state(
        message.peer_id,
        BotState.WAITING_COMPARE_CITY_2,
        first_city=first_city,
    )
    await send_text(
        message,
        _second_city_prompt(first_city, duplicate=duplicate),
        main_menu_keyboard(),
    )


async def _first_city_from_state(
    message: Message,
    deps: HandlerDeps,
) -> str | None:
    peer = await deps.states.get_state(message.peer_id)
    if peer is not None:
        value = peer.payload.get("first_city")
        if isinstance(value, str) and value.strip():
            return value.strip()

    context = deps.states.get_context(message.peer_id)
    if context.last_city:
        return context.last_city
    return None


def register(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.message(text=[BTN_COMPARE])
    async def compare_button(message: Message) -> None:
        deps.states.remember(message.peer_id, mode="compare")
        first_city = deps.states.get_context(message.peer_id).last_city
        if first_city:
            await _prompt_for_second_city(message, deps, first_city)
            return

        await prompt_for_city(
            message,
            deps,
            BotState.WAITING_COMPARE_CITY_1,
            COMPARE_CITY_1_PROMPT,
        )

    @bot.on.message(state=BotState.WAITING_COMPARE_CITY_1)
    async def compare_first_city(message: Message) -> None:
        first_city = message_text(message)
        if not first_city:
            await prompt_for_city(
                message,
                deps,
                BotState.WAITING_COMPARE_CITY_1,
                COMPARE_CITY_1_PROMPT,
            )
            return

        await _prompt_for_second_city(message, deps, first_city)

    @bot.on.message(state=BotState.WAITING_COMPARE_CITY_2)
    async def compare_second_city(message: Message) -> None:
        first_city = await _first_city_from_state(message, deps)
        if not first_city:
            await prompt_for_city(
                message,
                deps,
                BotState.WAITING_COMPARE_CITY_1,
                COMPARE_CITY_1_PROMPT,
            )
            return

        second_city = message_text(message)
        if not second_city:
            await _prompt_for_second_city(message, deps, first_city)
            return

        if _city_key(second_city) == _city_key(first_city):
            await _prompt_for_second_city(
                message,
                deps,
                first_city,
                duplicate=True,
            )
            return

        try:
            first_result, second_result = await asyncio.gather(
                deps.service.get_current(first_city),
                deps.service.get_current(second_city),
            )
        except Exception as exc:
            await reply_weather_error(message, exc)
            return

        if _same_location(first_result, second_result):
            await _prompt_for_second_city(
                message,
                deps,
                first_city,
                duplicate=True,
            )
            return

        deps.states.remember(
            message.peer_id,
            city=weather_city(first_result) or first_city,
            mode="compare",
        )
        text = format_comparison(first_result, second_result)
        await send_text(message, text, main_menu_keyboard())
        await deps.states.reset(message.peer_id)
