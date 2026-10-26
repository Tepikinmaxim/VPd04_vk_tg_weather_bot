import unittest
from types import SimpleNamespace

from weather_vk_bot.handlers.geo import (
    _parse_coordinates,
    extract_geo_coordinates,
)


class CoordinateParserTests(unittest.TestCase):
    def test_comma_separated(self) -> None:
        self.assertEqual(
            _parse_coordinates("55.7558,37.6173"),
            (55.7558, 37.6173),
        )

    def test_space_separated(self) -> None:
        self.assertEqual(
            _parse_coordinates("55.7558 37.6173"),
            (55.7558, 37.6173),
        )

    def test_decimal_comma(self) -> None:
        self.assertEqual(
            _parse_coordinates("55,7558 37,6173"),
            (55.7558, 37.6173),
        )

    def test_negative_coordinates(self) -> None:
        self.assertEqual(
            _parse_coordinates("-33.8688, 151.2093"),
            (-33.8688, 151.2093),
        )

    def test_invalid_format(self) -> None:
        for value in ("Москва", "55.7558", "55.7558,", "abc,def", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _parse_coordinates(value)

    def test_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            _parse_coordinates("91, 37")
        with self.assertRaises(ValueError):
            _parse_coordinates("55, 181")


class GeoExtractionTests(unittest.TestCase):
    def test_extracts_coordinates_from_message_geo(self) -> None:
        message = SimpleNamespace(
            geo=SimpleNamespace(
                coordinates=SimpleNamespace(latitude=55.7558, longitude=37.6173)
            )
        )

        self.assertEqual(
            extract_geo_coordinates(message),  # type: ignore[arg-type]
            (55.7558, 37.6173),
        )

    def test_extracts_coordinates_from_mapping(self) -> None:
        message = SimpleNamespace(
            geo={"coordinates": {"latitude": 59.9343, "longitude": 30.3351}}
        )

        self.assertEqual(
            extract_geo_coordinates(message),  # type: ignore[arg-type]
            (59.9343, 30.3351),
        )

    def test_missing_geo_returns_none(self) -> None:
        self.assertIsNone(extract_geo_coordinates(SimpleNamespace(geo=None)))  # type: ignore[arg-type]

    def test_invalid_geo_returns_none(self) -> None:
        message = SimpleNamespace(
            geo=SimpleNamespace(
                coordinates=SimpleNamespace(latitude=100, longitude=37)
            )
        )

        self.assertIsNone(extract_geo_coordinates(message))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
