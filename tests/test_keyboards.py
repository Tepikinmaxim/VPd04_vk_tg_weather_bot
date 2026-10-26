import json
import unittest

from weather_vk_bot.keyboards import (
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
    navigation_keyboard,
)


def load_keyboard(raw: str) -> dict:
    return json.loads(raw)


def button_labels(raw: str) -> list[str]:
    data = load_keyboard(raw)
    return [
        button["action"]["label"]
        for row in data["buttons"]
        for button in row
        if "label" in button["action"]
    ]


class KeyboardTests(unittest.TestCase):
    def test_main_menu_is_non_inline_and_has_all_sections(self) -> None:
        data = load_keyboard(main_menu_keyboard())

        self.assertFalse(data["one_time"])
        self.assertFalse(data["inline"])
        self.assertEqual(
            button_labels(main_menu_keyboard()),
            [
                BTN_WEATHER,
                BTN_FORECAST,
                BTN_GEO,
                BTN_EXTENDED,
                BTN_HELP,
            ],
        )
        self.assertEqual(
            button_labels(main_menu_keyboard())[0],
            "🌤 Погода сейчас",
        )

    def test_main_menu_button_colors(self) -> None:
        data = load_keyboard(main_menu_keyboard())
        buttons = [
            button for row in data["buttons"] for button in row
        ]

        self.assertEqual(buttons[0]["color"], "primary")
        self.assertEqual(buttons[1]["color"], "positive")
        self.assertEqual(buttons[2]["color"], "secondary")

    def test_geo_keyboard_has_native_location(self) -> None:
        data = load_keyboard(geo_keyboard())
        actions = [
            button["action"]["type"]
            for row in data["buttons"]
            for button in row
        ]

        self.assertIn("location", actions)
        self.assertIn(BTN_MANUAL_COORDS, button_labels(geo_keyboard()))
        self.assertIn(BTN_BACK, button_labels(geo_keyboard()))
        self.assertIn(BTN_HOME, button_labels(geo_keyboard()))

    def test_navigation_keyboard(self) -> None:
        self.assertEqual(
            button_labels(navigation_keyboard()),
            [BTN_BACK, BTN_HOME],
        )
        self.assertEqual(
            button_labels(navigation_keyboard(back=False, home=False)),
            [],
        )

    def test_all_keyboards_are_not_inline(self) -> None:
        for raw in (
            main_menu_keyboard(),
            geo_keyboard(),
            navigation_keyboard(),
        ):
            data = load_keyboard(raw)
            self.assertFalse(data["one_time"])
            self.assertFalse(data["inline"])


if __name__ == "__main__":
    unittest.main()
