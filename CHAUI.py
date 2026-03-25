import asyncio
import logging
import random
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Set, List, Tuple
import aiohttp
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, CallbackQuery
from aiogram.enums import ParseMode

# ========== КОНФИГУРАЦИЯ ==========
# Загружаем переменные окружения с преобразованием типов
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("API_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# Проверяем наличие обязательных переменных
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения!")
if not TWITCH_CLIENT_ID:
    raise ValueError("TWITCH_CLIENT_ID не найден в переменных окружения!")
if not TWITCH_CLIENT_SECRET:
    raise ValueError("TWITCH_CLIENT_SECRET не найден в переменных окружения!")

# Глобальные переменные с настройками
STREAMERS_TO_TRACK = [
    "0TV3CHAU"
]

# Загружаем ALLOWED_CHAT_IDS из переменной окружения
allowed_chat_ids_str = os.getenv("ALLOWED_CHAT_IDS", "-1001745405911")
try:
    ALLOWED_CHAT_IDS = {int(x.strip()) for x in allowed_chat_ids_str.split(",")}
except:
    ALLOWED_CHAT_IDS = {-1001745405911}

# Загружаем OWNER_ID
try:
    OWNER_ID = int(os.getenv("OWNER_ID", "1487919102"))
except:
    OWNER_ID = 1487919102

# Загружаем интервалы
try:
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))
except:
    CHECK_INTERVAL = 30

try:
    SCREENSHOT_UPDATE_INTERVAL = int(os.getenv("SCREENSHOT_UPDATE_INTERVAL", "120"))
except:
    SCREENSHOT_UPDATE_INTERVAL = 120

# Файл для сохранения настроек
SETTINGS_FILE = "bot_settings.json"

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

notified_streamers: Dict[str, dict] = {}
twitch_access_token = None
token_expires_at = None

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== РАНДОМНЫЕ ФРАЗЫ ДЛЯ ОПОВЕЩЕНИЙ ==========
RANDOM_PHRASES = [
    "Прямо сейчас происходит что-то невероятное!",
    "Заходи, будет весело!",
    "Не пропусти самое интересное!",
    "Стрим уже в эфире, ждём тебя!",
    "Лучший контент прямо сейчас!",
    "Скучно не будет — обещаю!",
    "Ты где? Стрим уже начался!",
    "Заходи посмотреть, что тут творится!",
    "Срочно на стрим! Там такое...",
    "Пропустишь — пожалеешь!",
]

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def is_allowed(chat_id: int) -> bool:
    """Проверяет, разрешен ли чат для использования бота"""
    # Админ всегда может использовать бота в личном чате
    if chat_id == OWNER_ID:
        return True
    # Иначе проверяем по списку разрешенных чатов
    return chat_id in ALLOWED_CHAT_IDS

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    return user_id == OWNER_ID

# ========== ЗАГРУЗКА/СОХРАНЕНИЕ НАСТРОЕК ==========
def load_settings():
    """Загружает настройки из файла"""
    global RANDOM_PHRASES, CHECK_INTERVAL, SCREENSHOT_UPDATE_INTERVAL, STREAMERS_TO_TRACK, ALLOWED_CHAT_IDS
    
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                
                if "random_phrases" in settings:
                    RANDOM_PHRASES = settings["random_phrases"]
                if "check_interval" in settings:
                    CHECK_INTERVAL = settings["check_interval"]
                if "screenshot_update_interval" in settings:
                    SCREENSHOT_UPDATE_INTERVAL = settings["screenshot_update_interval"]
                if "streamers_to_track" in settings:
                    STREAMERS_TO_TRACK = settings["streamers_to_track"]
                if "allowed_chat_ids" in settings:
                    ALLOWED_CHAT_IDS = set(settings["allowed_chat_ids"])
                    
            logger.info("Настройки загружены из файла")
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}")

def save_settings():
    """Сохраняет настройки в файл"""
    try:
        settings = {
            "random_phrases": RANDOM_PHRASES,
            "check_interval": CHECK_INTERVAL,
            "screenshot_update_interval": SCREENSHOT_UPDATE_INTERVAL,
            "streamers_to_track": STREAMERS_TO_TRACK,
            "allowed_chat_ids": list(ALLOWED_CHAT_IDS)
        }
        
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            
        logger.info("Настройки сохранены в файл")
    except Exception as e:
        logger.error(f"Ошибка сохранения настроек: {e}")

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_number_with_emoji(number: int) -> str:
    emoji_digits = {
        '0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
        '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'
    }
    return ''.join(emoji_digits[digit] for digit in str(number))


def get_random_viewers() -> int:
    """смешнявка с рандомными зрителями"""
    return random.randint(4, 20)


def get_random_phrase() -> str:
    """Возвращает случайную фразу из списка"""
    return random.choice(RANDOM_PHRASES)


async def send_log_to_owner(text: str):
    """Отправляет лог владельцу бота"""
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Не удалось отправить лог владельцу: {e}")


async def take_screenshot(streamer_login: str, stream_info: dict) -> str:
    """Делает скриншот стрима"""
    try:
        thumbnail_url = stream_info.get('thumbnail_url')
        if not thumbnail_url:
            thumbnail_url = f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{streamer_login}-640x360.jpg"

        filename = SCREENSHOTS_DIR / f"{streamer_login}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url) as response:
                if response.status == 200:
                    with open(filename, 'wb') as f:
                        f.write(await response.read())
                    logger.info(f"Скриншот сохранен: {filename}")
                    return str(filename)
                else:
                    logger.error(f"Не удалось загрузить скриншот: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при создании скриншота: {e}")
        return None


async def delete_screenshot(filepath: str):
    """Удаляет файл скриншота"""
    try:
        if filepath and Path(filepath).exists():
            Path(filepath).unlink()
            logger.info(f"Удален скриншот: {filepath}")
    except Exception as e:
        logger.error(f"Ошибка при удалении скриншота {filepath}: {e}")


def format_notification_text(streamer_login: str, stream_info: dict, random_viewers: int) -> str:
    """Форматирует текст оповещения в новом формате"""
    title = stream_info['title']
    game_name = stream_info['game_name']
    random_phrase = get_random_phrase()
    
    formatted_viewers = format_number_with_emoji(random_viewers)
    stream_url = f"https://twitch.tv/{streamer_login}"
    
    text = (
        f"🟣 <b>{title}</b>\n\n"
        f"{random_phrase}\n\n"
        f"<a href='{stream_url}'>twitch.tv/{streamer_login}</a>\n"
        f"<a href='{stream_url}'>Смотреть на Twitch</a>\n"
        f"<a href='{stream_url}'>Перейти к стриму</a>"
    )
    
    return text


# ========== API ==========
async def get_twitch_token() -> str:
    global twitch_access_token, token_expires_at

    if twitch_access_token and token_expires_at and datetime.now() < token_expires_at - timedelta(minutes=10):
        return twitch_access_token

    try:
        url = "https://id.twitch.tv/oauth2/token"
        
        data = {
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    data = await response.json()
                    twitch_access_token = data["access_token"]
                    expires_in = data.get("expires_in", 3600)
                    token_expires_at = datetime.now() + timedelta(seconds=expires_in)
                    logger.info(f"Twitch token получен")
                    await send_log_to_owner("✅ <b>Twitch токен получен</b>")
                    return twitch_access_token
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка получения токена. Статус: {response.status}, Ответ: {error_text}")
                    await send_log_to_owner(f"❌ <b>Ошибка получения Twitch токена</b>\nСтатус: {response.status}\nОтвет: {error_text[:200]}. Пиши Мишане, тут наши полномочия всё.")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при получении токена Twitch: {e}")
        return None


async def get_stream_info(streamer_login: str) -> dict:
    token = await get_twitch_token()
    if not token:
        return None

    try:
        url = "https://api.twitch.tv/helix/streams"
        headers = {
            "Client-ID": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        params = {'user_login': streamer_login}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    streams = data.get("data", [])
                    if streams:
                        stream = streams[0]
                        return {
                            "user_name": stream["user_name"],
                            "title": stream["title"],
                            "game_name": stream["game_name"],
                            "viewer_count": stream["viewer_count"],
                            "started_at": stream["started_at"],
                            "thumbnail_url": stream["thumbnail_url"].format(width=640, height=360) if stream.get("thumbnail_url") else None,
                        }
                return None
    except Exception as e:
        logger.error(f"Ошибка при получении информации о стримере {streamer_login}: {e}")
        return None


async def check_streams() -> Dict[str, dict]:
    """Проверяет актив"""
    token = await get_twitch_token()
    if not token:
        logger.error("Нет токена для доступа к Twitch API")
        return {}

    try:
        all_streams = {}
        
        for i in range(0, len(STREAMERS_TO_TRACK), 100):
            batch = STREAMERS_TO_TRACK[i:i + 100]

            url = "https://api.twitch.tv/helix/streams"
            headers = {
                "Client-ID": TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {token}",
            }
            
            params: List[Tuple[str, str]] = []
            for login in batch:
                params.append(('user_login', login))
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for stream in data.get("data", []):
                            login = stream["user_login"]
                            all_streams[login] = {
                                "user_name": stream["user_name"],
                                "title": stream["title"],
                                "game_name": stream["game_name"],
                                "viewer_count": stream["viewer_count"],
                                "started_at": stream["started_at"],
                                "thumbnail_url": stream["thumbnail_url"].format(width=640, height=360) if stream.get("thumbnail_url") else None,
                            }
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка Twitch API {response.status}: {error_text}")
                        return {}
                        
        return all_streams
    except Exception as e:
        logger.error(f"Ошибка при проверке стримов: {e}")
        return {}


# ========== УВЕДОМЛЕНИЯ ==========
async def send_stream_notification(chat_id: int, streamer_login: str, stream_info: dict):
    
    random_viewers = get_random_viewers()
    text = format_notification_text(streamer_login, stream_info, random_viewers)

    screenshot_path = await take_screenshot(streamer_login, stream_info)
    
    try:
        if screenshot_path:
            with open(screenshot_path, 'rb') as photo:
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=types.FSInputFile(screenshot_path),
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    disable_notification=True,
                )
            await delete_screenshot(screenshot_path)
        else:
            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_notification=True,
                disable_web_page_preview=False,
            )
        
        logger.info(f"Отправлено уведомление о стриме {streamer_login} (сообщение ID: {message.message_id})")
        await send_log_to_owner(f"<b>Отправлено уведомление о стриме</b>\n{streamer_login}\n {stream_info['title'][:50]}...")
        
        return {
            "message_id": message.message_id,
            "chat_id": chat_id,
            "stream_info": stream_info,
            "random_viewers": random_viewers,
            "last_screenshot_update": datetime.now()
        }
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        await send_log_to_owner(f"<b>Ошибка отправки уведомления</b>\n{streamer_login}\n{e}")
        return None


async def update_stream_screenshot(streamer_login: str, notification_data: dict):
    """Обновляет скриншот в сообщении о стриме"""
    try:
        current_stream_info = await get_stream_info(streamer_login)
        if not current_stream_info:
            logger.warning(f"Не удалось получить актуальную информацию о стриме {streamer_login}")
            return False
        
        new_screenshot_path = await take_screenshot(streamer_login, current_stream_info)
        if not new_screenshot_path:
            logger.warning(f"Не удалось создать новый скриншот для {streamer_login}")
            return False
        
        random_viewers = get_random_viewers()
        text = format_notification_text(streamer_login, current_stream_info, random_viewers)
        
        with open(new_screenshot_path, 'rb') as photo:
            await bot.edit_message_media(
                chat_id=notification_data["chat_id"],
                message_id=notification_data["message_id"],
                media=InputMediaPhoto(
                    media=types.FSInputFile(new_screenshot_path),
                    caption=text,
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=None
            )
        
        await delete_screenshot(new_screenshot_path)
        
        notification_data["stream_info"] = current_stream_info
        notification_data["random_viewers"] = random_viewers
        notification_data["last_screenshot_update"] = datetime.now()
        
        logger.info(f"Обновлен скриншот для {streamer_login}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении скриншота для {streamer_login}: {e}")
        return False


async def delete_stream_notification(chat_id: int, message_id: int):
    """Удаляет сообщение о стриме"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Удалено сообщение {message_id} о завершившемся стриме")
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения {message_id}: {e}")
        return False


# ========== ФОНОВАЯ ЗАДАЧА ПРОВЕРКИ ==========
async def check_streams_task():
    logger.info("Запущена фоновая задача проверки стримов")
    await send_log_to_owner("<b>Бот запущен</b>\nНачинаю отслеживание стримов...")
    
    await asyncio.sleep(5)

    while True:
        try:
            # Используем глобальные переменные для получения текущих значений
            current_check_interval = CHECK_INTERVAL
            current_streamers = STREAMERS_TO_TRACK.copy()
            current_allowed_chats = ALLOWED_CHAT_IDS.copy()
            
            logger.info("Начинаю проверку стримов...")
            active_streams = await check_streams()
            active_logins = set(active_streams.keys())
            
            logger.info(f"Активные стримы: {active_logins}")
            logger.info(f"Уведомленные стримеры: {list(notified_streamers.keys())}")
            
            for login in current_streamers:
                is_live = login in active_logins
                was_notified = login in notified_streamers

                if is_live and not was_notified:
                    stream_info = active_streams[login]
                    logger.info(f"СТРИМ НАЧАЛСЯ: {login}")
                    await send_log_to_owner(f"<b>СТРИМ НАЧАЛСЯ</b>\n {login}\n{stream_info['game_name']}")
                    for chat_id in current_allowed_chats:
                        result = await send_stream_notification(chat_id, login, stream_info)
                        if result:
                            notified_streamers[login] = result

                elif not is_live and was_notified:
                    logger.info(f"СТРИМ ЗАКОНЧИЛСЯ: {login}")
                    await send_log_to_owner(f"<b>СТРИМ ЗАКОНЧИЛСЯ</b>\n{login}")
                    stream_data = notified_streamers[login]
                    await delete_stream_notification(
                        chat_id=stream_data["chat_id"],
                        message_id=stream_data["message_id"]
                    )
                    del notified_streamers[login]

        except Exception as e:
            logger.error(f"Ошибка в фоновой задаче: {e}", exc_info=True)
            await send_log_to_owner(f"<b>Ошибка в фоновой задаче</b>\n{e}")

        logger.info(f"💤 Следующая проверка через {CHECK_INTERVAL} секунд")
        await asyncio.sleep(CHECK_INTERVAL)


# ========== ФОНОВАЯ ЗАДАЧА ОБНОВЛЕНИЯ СКРИНШОТОВ ==========
async def update_screenshots_task():
    """Фоновая задача для обновления скриншотов каждые 2 минуты"""
    logger.info("Запущена фоновая задача обновления скриншотов")
    
    await asyncio.sleep(10)
    
    while True:
        try:
            if notified_streamers:
                logger.info(f"Обновляю скриншоты для {len(notified_streamers)} активных стримов...")
                
                for login, notification_data in list(notified_streamers.items()):
                    time_since_update = datetime.now() - notification_data.get("last_screenshot_update", datetime.min)
                    
                    if time_since_update.total_seconds() >= SCREENSHOT_UPDATE_INTERVAL:
                        logger.info(f"Обновляю скриншот для {login} (прошло {time_since_update.total_seconds():.0f} сек)")
                        await update_stream_screenshot(login, notification_data)
                    else:
                        remaining = SCREENSHOT_UPDATE_INTERVAL - time_since_update.total_seconds()
                        logger.debug(f"Скриншот для {login} обновится через {remaining:.0f} сек")
            else:
                logger.debug("Нет активных стримов, обновление скриншотов не требуется")
                
        except Exception as e:
            logger.error(f"Ошибка в задаче обновления скриншотов: {e}", exc_info=True)
            await send_log_to_owner(f"<b>Ошибка обновления скриншотов</b>\n{e}")
        
        await asyncio.sleep(30)


# ========== КОМАНДЫ БОТА ==========
@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    # Админ всегда может использовать бота
    if not is_allowed(message.chat.id):
        await message.answer("Этот бот не предназначен для использования в этом чате.")
        return

    text = (
        "<b>ГЛАЗ САБЗИРОУ!</b>\n\n"
        f"Интервал проверки: {CHECK_INTERVAL} сек.\n"
        f"Интервал обновления скриншотов: {SCREENSHOT_UPDATE_INTERVAL // 60} мин.\n\n"
        "<b>Доступные команды:</b>\n"
        "/settings — Тех. инфа бота\n"
        "/phrases — управление фразами\n"
        "/add_streamer — добавить стримера\n"
        "/remove_streamer — удалить стримера\n"
    )
    
    # Добавляем админские команды для личного чата
    if message.chat.id == OWNER_ID:
        text += (
            "\n<b>Админ-команды (только в ЛС):</b>\n"
            "/add_chat — добавить чат в список разрешенных\n"
            "/remove_chat — удалить чат из списка\n"
            "/list_chats — список разрешенных чатов\n"
        )
    
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    """Показывает текущие настройки бота"""
    if not is_allowed(message.chat.id):
        return
    
    text = (
        "<b>Настройки бота</b>\n\n"
        f"<b>ALLOWED_CHAT_IDS</b>: {list(ALLOWED_CHAT_IDS)}\n"
        f"<b>CHECK_INTERVAL</b>: {CHECK_INTERVAL} сек.\n"
        f"<b>SCREENSHOT_UPDATE_INTERVAL</b>: {SCREENSHOT_UPDATE_INTERVAL} сек. ({SCREENSHOT_UPDATE_INTERVAL // 60} мин.)\n\n"
        f"<b>Количество фраз</b>: {len(RANDOM_PHRASES)}\n"
        f"<b>Отслеживаемый стример ({len(STREAMERS_TO_TRACK)}):</b>\n"
    )
    
    for login in STREAMERS_TO_TRACK:
        text += f"• {login}\n"
    
    if len(text) > 4000:
        text = text[:4000] + "\n\n... и другие"
    
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("phrases"))
async def cmd_phrases(message: Message):
    """Показывает и управляет фразами"""
    if not is_allowed(message.chat.id):
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить фразу", callback_data="add_phrase")],
            [InlineKeyboardButton(text="Удалить фразу", callback_data="remove_phrase")],
            [InlineKeyboardButton(text="Показать все фразы", callback_data="show_phrases")]
        ]
    )
    
    await message.answer("<b>Управление фразами</b>\n\nВыберите действие:", parse_mode=ParseMode.HTML, reply_markup=keyboard)


@dp.message(Command("add_chat"))
async def cmd_add_chat(message: Message):
    """Добавляет чат в список разрешенных (только для админа в ЛС)"""
    if message.chat.id != OWNER_ID:
        await message.answer("Эта команда доступна только админу в личном чате.")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /add_chat <chat_id>\n\nПример: /add_chat -1001234567890")
        return
    
    try:
        chat_id = int(args[1])
        ALLOWED_CHAT_IDS.add(chat_id)
        save_settings()
        await message.answer(f"✅ Чат {chat_id} добавлен в список разрешенных.\n\nТекущий список: {list(ALLOWED_CHAT_IDS)}")
        await send_log_to_owner(f"➕ <b>Добавлен чат</b>\nID: {chat_id}")
    except ValueError:
        await message.answer("❌ Неверный формат chat_id. Должен быть числом.")


@dp.message(Command("remove_chat"))
async def cmd_remove_chat(message: Message):
    """Удаляет чат из списка разрешенных (только для админа в ЛС)"""
    if message.chat.id != OWNER_ID:
        await message.answer("Эта команда доступна только админу в личном чате.")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /remove_chat <chat_id>\n\nПример: /remove_chat -1001234567890")
        return
    
    try:
        chat_id = int(args[1])
        if chat_id in ALLOWED_CHAT_IDS:
            ALLOWED_CHAT_IDS.remove(chat_id)
            save_settings()
            await message.answer(f"✅ Чат {chat_id} удален из списка разрешенных.\n\nТекущий список: {list(ALLOWED_CHAT_IDS)}")
            await send_log_to_owner(f"➖ <b>Удален чат</b>\nID: {chat_id}")
        else:
            await message.answer(f"❌ Чат {chat_id} не найден в списке разрешенных.")
    except ValueError:
        await message.answer("❌ Неверный формат chat_id. Должен быть числом.")


@dp.message(Command("list_chats"))
async def cmd_list_chats(message: Message):
    """Показывает список разрешенных чатов (только для админа)"""
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админу.")
        return
    
    text = "<b>Разрешенные чаты:</b>\n\n"
    for chat_id in ALLOWED_CHAT_IDS:
        text += f"• {chat_id}\n"
    
    text += f"\n<b>Всего чатов:</b> {len(ALLOWED_CHAT_IDS)}"
    
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("add_streamer"))
async def cmd_add_streamer(message: Message):
    """Добавляет стримера в список отслеживания (только для админа)"""
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админу.")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /add_streamer <twitch_login>\n\nПример: /add_streamer ninja")
        return
    
    login = args[1].lower()
    if login in STREAMERS_TO_TRACK:
        await message.answer(f"❌ Стример {login} уже отслеживается.")
        return
    
    STREAMERS_TO_TRACK.append(login)
    save_settings()
    await message.answer(f"✅ Стример {login} добавлен в список отслеживания.")
    await send_log_to_owner(f"➕ <b>Добавлен стример</b>\n{login}")


@dp.message(Command("remove_streamer"))
async def cmd_remove_streamer(message: Message):
    """Удаляет стримера из списка отслеживания (только для админа)"""
    if not is_admin(message.from_user.id):
        await message.answer("Эта команда доступна только админу.")
        return
    
    args = message.text.split()
    if len(args) != 2:
        await message.answer("Использование: /remove_streamer <twitch_login>\n\nПример: /remove_streamer ninja")
        return
    
    login = args[1].lower()
    if login not in STREAMERS_TO_TRACK:
        await message.answer(f"❌ Стример {login} не найден в списке отслеживания.")
        return
    
    STREAMERS_TO_TRACK.remove(login)
    save_settings()
    await message.answer(f"✅ Стример {login} удален из списка отслеживания.")
    await send_log_to_owner(f"➖ <b>Удален стример</b>\n{login}")


@dp.callback_query()
async def handle_phrases_callback(callback: CallbackQuery):
    """Обрабатывает callback'и от кнопок управления фразами"""
    if not is_allowed(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    
    if callback.data == "add_phrase":
        await callback.message.answer("Отправьте новую фразу (текст):")
        await callback.answer()
        
    elif callback.data == "remove_phrase":
        if not RANDOM_PHRASES:
            await callback.message.answer("Список фраз пуст!")
            await callback.answer()
            return
        
        # Создаем кнопки для каждой фразы
        keyboard = []
        for i, phrase in enumerate(RANDOM_PHRASES):
            short_phrase = phrase[:30] + "..." if len(phrase) > 30 else phrase
            keyboard.append([InlineKeyboardButton(text=f"{short_phrase}", callback_data=f"del_phrase_{i}")])
        
        keyboard.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_delete")])
        
        await callback.message.edit_text(
            "<b>Выберите фразу для удаления:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await callback.answer()
        
    elif callback.data == "show_phrases":
        text = "<b>Список фраз:</b>\n\n"
        for i, phrase in enumerate(RANDOM_PHRASES, 1):
            text += f"{i}. {phrase}\n"
        
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
        await callback.answer()
        
    elif callback.data.startswith("del_phrase_"):
        try:
            index = int(callback.data.split("_")[2])
            if 0 <= index < len(RANDOM_PHRASES):
                removed = RANDOM_PHRASES.pop(index)
                save_settings()
                await callback.message.edit_text(f"✅ Фраза удалена:\n«{removed}»")
                await callback.answer("Фраза удалена")
        except:
            await callback.answer("Ошибка при удалении")
            
    elif callback.data == "cancel_delete":
        await callback.message.delete()
        await callback.answer()


@dp.message()
async def handle_new_phrase(message: Message):
    """Обрабатывает добавление новой фразы"""
    if not is_allowed(message.chat.id):
        return
    
    # Проверяем, ожидаем ли мы добавление фразы (упрощенная логика)
    if message.text and not message.text.startswith("/"):
        RANDOM_PHRASES.append(message.text)
        save_settings()
        await message.answer(f"✅ Фраза добавлена:\n«{message.text}»")
        await send_log_to_owner(f"📝 <b>Добавлена новая фраза</b>\n{message.text}")


# ========== ЗАПУСК БОТА ==========
async def main():
    # Загружаем настройки
    load_settings()
    
    # Очищаем старые скриншоты при запуске
    for file in SCREENSHOTS_DIR.glob("*.jpg"):
        try:
            file.unlink()
        except:
            pass
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_streams_task())
    asyncio.create_task(update_screenshots_task())
    
    logger.info("🤖 Бот запущен")
    await send_log_to_owner("🤖 <b>Бот запущен</b>")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
