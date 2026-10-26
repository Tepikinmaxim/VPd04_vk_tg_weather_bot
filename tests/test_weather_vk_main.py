import io
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from weather_vk_bot.main import main


class MainTests(unittest.TestCase):
    def test_missing_token_prints_variable_name(self) -> None:
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("weather_vk_bot.main.load_dotenv"),
            redirect_stderr(stderr),
        ):
            code = main([])

        self.assertEqual(code, 2)
        self.assertIn("VK_BOT_TOKEN", stderr.getvalue())

    def test_check_requires_token_before_network(self) -> None:
        stderr = io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("weather_vk_bot.main.load_dotenv"),
            redirect_stderr(stderr),
        ):
            code = main(["--check"])

        self.assertEqual(code, 2)
        self.assertIn("VK_BOT_TOKEN", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
