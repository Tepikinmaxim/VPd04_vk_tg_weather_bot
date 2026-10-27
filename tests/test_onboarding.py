import unittest
from typing import Any

from vkbottle import GroupEventType
from vkbottle_types.events.bot_events import MessageAllow

from weather_vk_bot.bot import VKWeatherBot
from weather_vk_bot.handlers.common import HELP_TEXT
from weather_vk_bot.keyboards import main_menu_keyboard
from weather_vk_bot.services.state_manager import BotState
from weather_vk_bot.services.welcome_gate import WelcomeGate


class FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send(self, **kwargs: Any) -> dict[str, int]:
        self.calls.append(kwargs)
        return {"message_id": len(self.calls)}


class FakeAPI:
    def __init__(self) -> None:
        self.messages = FakeMessages()


class FakeMessage:
    def __init__(self, text: str, peer_id: int = 77) -> None:
        self.text = text
        self.peer_id = peer_id
        self.answers: list[dict[str, Any]] = []

    async def answer(self, message: str, **kwargs: Any) -> dict[str, int]:
        self.answers.append({"text": message, **kwargs})
        return {"message_id": len(self.answers)}


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def find_message_handler(bot: VKWeatherBot, name: str):
    for handler in bot.bot.labeler.message_view.handlers:
        if handler.handler.__name__ == name:
            return handler.handler
    raise AssertionError(f"Handler {name} not found")


def find_raw_handler(bot: VKWeatherBot, event_type: GroupEventType):
    for basement in bot.bot.labeler.raw_event_view.handlers[event_type]:
        if basement.handler.handler.__name__ == "auto_start_dialog":
            return basement.handler.handler
    raise AssertionError("Handler auto_start_dialog not found")


def make_allow_event(api: FakeAPI, user_id: int = 77) -> MessageAllow:
    event = MessageAllow(
        type=GroupEventType.MESSAGE_ALLOW,
        object={"user_id": user_id, "key": "allow-key"},
        group_id=1,
    )
    event.unprepared_ctx_api = api
    return event


class OnboardingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.api = FakeAPI()
        self.clock = FakeClock()
        self.bot = VKWeatherBot(
            "test-token",
            service=object(),
            welcome_gate=WelcomeGate(clock=self.clock),
        )

    async def test_message_allow_sends_menu_without_start(self) -> None:
        await find_raw_handler(
            self.bot,
            GroupEventType.MESSAGE_ALLOW,
        )(make_allow_event(self.api))

        self.assertEqual(len(self.api.messages.calls), 1)
        call = self.api.messages.calls[0]
        self.assertEqual(call["peer_id"], 77)
        self.assertEqual(call["message"], HELP_TEXT)
        self.assertIn("Погодный эксперт", call["message"])
        self.assertIn("ℹ️ Что могу", call["message"])
        self.assertNotIn("Сменить город — сохранить", call["message"])
        self.assertEqual(call["keyboard"], main_menu_keyboard())
        peer = await self.bot.states.get_state(77)
        assert peer is not None
        self.assertEqual(peer.state, BotState.MAIN_MENU)

    async def test_message_allow_includes_saved_city(self) -> None:
        self.bot.states.remember(77, city="Москва")

        await find_raw_handler(
            self.bot,
            GroupEventType.MESSAGE_ALLOW,
        )(make_allow_event(self.api))

        self.assertIn("Текущий город: Москва", self.api.messages.calls[0]["message"])

    async def test_start_does_not_duplicate_auto_welcome(self) -> None:
        await find_raw_handler(
            self.bot,
            GroupEventType.MESSAGE_ALLOW,
        )(make_allow_event(self.api))
        message = FakeMessage("/start")

        await find_message_handler(self.bot, "start")(message)

        self.assertEqual(message.answers, [])
        self.assertEqual(len(self.api.messages.calls), 1)

    async def test_start_works_after_cooldown(self) -> None:
        await find_raw_handler(
            self.bot,
            GroupEventType.MESSAGE_ALLOW,
        )(make_allow_event(self.api))
        self.clock.value += 6.0
        message = FakeMessage("/start")

        await find_message_handler(self.bot, "start")(message)

        self.assertEqual(len(message.answers), 1)
        self.assertEqual(message.answers[0]["text"], HELP_TEXT)
        self.assertEqual(message.answers[0]["keyboard"], main_menu_keyboard())


if __name__ == "__main__":
    unittest.main()
