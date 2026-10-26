@vkbottle-tutor @VK Bottle-API

[Контекст]:

Разработка production-ready VK Community Bot для сообщества ВКонтакте с использованием VKBottle (актуальный современный framework для VK API). Бот выступает frontend-слоем для OpenWeatherAPI.py и должен предоставлять красивый интерфейс, кнопочное управление, FSM-состояния, геолокацию, прогнозы и расширенную аналитику.

Цель — создать масштабируемого коммерческого погодного бота, готового к дальнейшему расширению:

подписки,

уведомления,

избранные города,

персональные настройки.

[Реализация]:

Сгенерируй полный Python-проект VK Weather Bot на VKBottle через Long Poll API

[Технологии]:

Python 3.11+

vkbottle

python-dotenv

requests

logging

OOP

FSM / StateDispenser

OpenWeatherAPI.py (как отдельный backend-модуль)

[КРИТИЧЕСКИ ВАЖНО]:

Использовать только актуальный синтаксис VKBottle:

Bot

Message

Keyboard

Text

OpenLink

Callback

CtxStorage / StateDispenser

Не использовать устаревший vk_api.

[Структура проекта]:

weather_vk_bot/

main.py bot.py

handlers/

menu.py

weather.py

forecast.py

geo.py

help.py

services/

weather_service.py

formatter.py

state_manager.py

keyboards/

main_keyboard.py

navigation_keyboard.py

OpenWeatherAPI.py .env requirements.txt

[.env]:

VK_BOT_TOKEN=your_vk_group_token OPENWEATHER_API_KEY=your_openweather_api_key

[Основной класс]:

VKWeatherBot

[Главное меню — красивый UX]:

Кнопки:

🌤 Погода сейчас

📅 Прогноз 5 дней

📍 Геолокация

🌫 Расширенный режим

ℹ️ Помощь

Навигация:

⬅️ Назад

🏠 Главное меню

[UI требования]:

Keyboard(one_time=False, inline=False)

Цвета кнопок:

PRIMARY

SECONDARY

POSITIVE

Emoji

Разделители: ──────────────

[Основные бизнес-функции]:

1. Погода сейчас:

Пользователь: 🌤

Бот: “Введите город:”

State: awaiting_city_weather

Далее: OpenWeatherAPI.get_weather_by_city(city)

2. Прогноз:

Пользователь: 📅

State: awaiting_city_forecast

Далее: OpenWeatherAPI.get_forecast_by_city(city)

3. Геолокация (ОСОБО ВАЖНО):

Проверить реальные возможности VKBottle:

В VK сообщения могут содержать geo attachment: message.geo

Реализовать:

if message.geo: lat = message.geo.coordinates.latitude lon = message.geo.coordinates.longitude

Далее:

OpenWeatherAPI.get_weather_by_coordinates(lat, lon)

[Fallback]:

Если VK geo unavailable: Бот: “Отправьте координаты в формате: 55.7558, 37.6173”

[_parse_coordinates]:

Поддержка:

"55.7558,37.6173"

"55.7558 37.6173"

[4. Расширенный режим]:

При активации: State: awaiting_extended_city

Следующий запрос: extended=True

[FSM]:

Использовать StateDispenser

Создать состояния:

MAIN_MENU

WAITING_CITY

WAITING_FORECAST_CITY

WAITING_GEO

WAITING_EXTENDED

[Formatter]:

formatter.py должен красиво оформлять:

Базовая погода:

🌍 Город: Москва 🌡 Температура: +21°C 💧 Влажность: 64% 💨 Ветер: 3 м/с

Extended:

🌅 Рассвет 🌇 Закат 🌫 AQI 📊 Загрязнители 💬 Анализ воздуха

[Пример Extended]:

🌫 Воздух: Fair 📊 PM2.5 слегка повышен 💬 Качество воздуха хорошее, но чувствительным группам стоит сократить длительные прогулки у дорог.

[Обработка ошибок]:

Город не найден

API недоступен

Неверные координаты

Пустой ввод

Ошибка геолокации

[Архитектурные требования]:

weather_service.py:

Связующее звено между VKBottle и OpenWeatherAPI

formatter.py:

Только оформление

state_manager.py:

Логика состояний

handlers:

Только обработка пользовательских сценариев

[main.py]:

Запуск Bot

Регистрация роутов

Подключение middleware

Logging

[Безопасность]:

Все токены через dotenv

Без хардкода

try/except

logging

[requirements.txt]:

vkbottle python-dotenv requests

[Будущая масштабируемость]:

Подготовить архитектуру под:

уведомления о погоде

ежедневные прогнозы

сохранённые города

предупреждения о плохом воздухе

мультиязычность

[Вход]:

Сообщения пользователя VK Community

[Выход]:

Полный production-ready код проекта на VKBottle

[Ограничения]:

Только VKBottle

Только актуальный API

Только рабочие обработчики

Геолокация должна быть реализована максимально доступным способом

Красивый UX

Код должен запускаться сразу после вставки токенов

Без устаревших решений

Без воды
