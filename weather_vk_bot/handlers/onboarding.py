"""Автоматический старт личного диалога."""

from __future__ import annotations

import logging

from vkbottle import GroupEventType
from vkbottle.bot import Bot
from vkbottle_types.events.bot_events import MessageAllow

from .common import HELP_TEXT, HandlerDeps, show_main_menu_for_peer

LOGGER = logging.getLogger(__name__)


def register(bot: Bot, deps: HandlerDeps) -> None:
    @bot.on.raw_event(GroupEventType.MESSAGE_ALLOW, MessageAllow)
    async def auto_start_dialog(event: MessageAllow) -> None:
        user_id = event.object.user_id
        if not deps.welcome_gate.claim(user_id):
            LOGGER.debug(
                "Приветствие уже отправлено: user_id=%s",
                user_id,
            )
            return

        LOGGER.info(
            "Пользователь разрешил сообщения, отправляю меню: user_id=%s",
            user_id,
        )
        await show_main_menu_for_peer(event.ctx_api, deps, user_id, HELP_TEXT)
