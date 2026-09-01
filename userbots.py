import asyncio
import logging
import os
import math
import re
import time
import json
import aiohttp
import hashlib
import base64
from datetime import datetime
from typing import Optional, Dict, List, Any
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from deep_translator import GoogleTranslator
import pytesseract
from PIL import Image, ImageDraw, ImageFont
import io

# ================= НАСТРОЙКИ =================
API_ID = 38110829
API_HASH = "c6b2393e8484ea4a78aab06641637595"
SUDO_USERS = [6034090849]

# Погода API ключ (бесплатный на https://openweathermap.org/)
WEATHER_API_KEY = "ааа18c5201f6b58251ef2e737e7c4e09"
# =============================================

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Создаем клиент
app = Client("my_userbot", api_id=API_ID, api_hash=API_HASH, in_memory=False)

# ================= ДАННЫЕ ДЛЯ ХРАНЕНИЯ =================
user_data = {}
bot_data = {}

# ================= УПРАВЛЕНИЕ СПАМОМ =================

# Хранилище активных спам-задач
active_spams = {}
spam_counter = 0

class SpamTask:
    def __init__(self, task_id, client, chat_id, text, delay, total_count, reply_to_message=None):
        self.id = task_id
        self.client = client
        self.chat_id = chat_id
        self.text = text
        self.delay = delay
        self.total = total_count
        self.sent = 0
        self.running = True
        self.reply_to_message = reply_to_message
        self.start_time = time.time()
        self.task = None

    async def run(self):
        while self.running and self.sent < self.total:
            try:
                if self.reply_to_message:
                    await self.client.send_message(
                        self.chat_id,
                        self.text,
                        reply_to_message_id=self.reply_to_message.id
                    )
                else:
                    await self.client.send_message(self.chat_id, self.text)
                
                self.sent += 1
                await asyncio.sleep(self.delay)
            except Exception as e:
                logger.error(f"Ошибка спама #{self.id}: {e}")
                break
        
        if self.sent >= self.total:
            self.running = False

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

def format_number(num: int) -> str:
    return f"{num:,}".replace(",", ".")

def parse_balance(text: str) -> int:
    text = text.lower().replace(" ", "")
    match = re.search(r"([\d.,]+)([kк]{1,4})?$", text)
    if not match:
        return 0
    num_str = match.group(1)
    suffix = match.group(2) or ""
    num_str = num_str.replace(",", ".") if suffix else num_str.replace(",", "").replace(".", "")
    try:
        num = float(num_str)
        multipliers = {"": 1, "k": 1000, "к": 1000, "kk": 1000000, "кк": 1000000, 
                      "kkk": 1000000000, "ккк": 1000000000, "kkkk": 100000000, "кккк": 100000000}
        return int(num * multipliers.get(suffix, 1))
    except:
        return 0

async def get_weather(city: str) -> str:
    """Получает погоду через OpenWeatherMap API"""
    if not WEATHER_API_KEY or WEATHER_API_KEY == "ааа18c5201f6b58251ef2e737e7c4e09":
        try:
            url = f"https://wttr.in/{city}?format=%C+%t+%w+%h&lang=ru"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return f"❌ Город '{city}' не найден!"
                    data = await response.text()
                    parts = data.strip().split()
                    if len(parts) < 4:
                        return f"❌ Не удалось получить погоду для '{city}'"
                    description = " ".join(parts[:-3])
                    temp = parts[-3]
                    wind = parts[-2]
                    humidity = parts[-1]
                    return (
                        f"🌤 **Погода в {city}**\n\n"
                        f"🌡 Температура: **{temp}**\n"
                        f"💨 Ветер: **{wind}**\n"
                        f"💧 Влажность: **{humidity}**\n"
                        f"📝 Описание: **{description}**"
                    )
        except Exception as e:
            return f"❌ Ошибка: {e}"
    
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return f"❌ Город '{city}' не найден!"
            
            data = await response.json()
            
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            humidity = data['main']['humidity']
            wind = data['wind']['speed']
            description = data['weather'][0]['description'].capitalize()
            
            return (
                f"🌤 **Погода в {city}**\n\n"
                f"🌡 Температура: **{temp:.1f}°C** (ощущается как {feels_like:.1f}°C)\n"
                f"💧 Влажность: **{humidity}%**\n"
                f"💨 Ветер: **{wind} м/с**\n"
                f"📝 Описание: **{description}**"
            )

async def get_exchange_rate(from_currency: str, to_currency: str) -> str:
    """Получает курс валют"""
    try:
        url = f"https://api.frankfurter.app/latest?from={from_currency.upper()}&to={to_currency.upper()}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return "❌ Ошибка получения курса валют! Попробуй позже."
                
                data = await response.json()
                
                if to_currency.upper() not in data['rates']:
                    return f"❌ Валюта '{to_currency}' не найдена!"
                
                rate = data['rates'][to_currency.upper()]
                date = data['date']
                
                return (
                    f"💱 **Курс валют**\n\n"
                    f"1 **{from_currency.upper()}** = **{rate:.4f} {to_currency.upper()}**\n"
                    f"📅 Дата: {date}"
                )
    except Exception as e:
        return f"❌ Ошибка: {e}"

async def translate_text(text: str, target_lang: str) -> str:
    """Переводит текст на указанный язык"""
    try:
        translated = GoogleTranslator(source='auto', target=target_lang).translate(text)
        return (
            f"🌐 **Перевод**\n\n"
            f"📝 **Оригинал:** {text}\n"
            f"✅ **Перевод ({target_lang.upper()}):** {translated}"
        )
    except Exception as e:
        return f"❌ Ошибка перевода: {e}"

async def ocr_image(client, message: Message) -> str:
    """Распознает текст с фото"""
    try:
        if not message.reply_to_message or not message.reply_to_message.photo:
            return "❌ Ответь на сообщение с фото!"
        
        file_path = await client.download_media(message.reply_to_message.photo.file_id)
        
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img, lang='rus+eng')
        
        os.remove(file_path)
        
        if not text.strip():
            return "❌ Не удалось распознать текст на изображении!"
        
        return f"📷 **Распознанный текст:**\n\n{text.strip()}"
    except Exception as e:
        return f"❌ Ошибка распознавания: {e}"

# ================= МОДУЛЬ 1: AutoBanki =================
class AutoBankiModule:
    def __init__(self):
        self.running = False
        self.task = None
        self.bot = "@bfgbunker_bot"
        self.mode = "banks"
        self.caps_per_bank_cost = 1000
        self.rating_item_cost = 10000
        self.bank_purchase_limit_caps = 1000000000
        self.buy_less_threshold_caps = 1000000
        self.buy_less_quantity = 100

    async def get_balance(self, client) -> int:
        await client.send_message(self.bot, "Бб")
        await asyncio.sleep(3)
        msgs = await client.get_messages(self.bot, limit=3)
        for msg in msgs:
            if msg.text and "Баланс:" in msg.text:
                match = re.search(r"Баланс:\s*([\d.,\s]+(?:[kк]{1,4})?)", msg.text)
                if match:
                    return parse_balance(match.group(1))
        return 0

    async def buy_fuel(self, client):
        await client.send_message(self.bot, "Бензин")
        await asyncio.sleep(3)
        msgs = await client.get_messages(self.bot, limit=5)
        for msg in msgs:
            if msg.sender_id == 5813222348 and msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        if btn.text == "Купить бензин":
                            await btn.click()
                            logger.info("Купил бензин")
                            return

    async def buy_banks(self, client, count: int):
        if count > 0:
            await client.send_message(self.bot, f"Пополнить банки {count}")
            logger.info(f"Купил банки: {count}")

    async def buy_rating(self, client, count: int):
        if count > 0:
            await client.send_message(self.bot, f"Купить рейтинг {count}")
            logger.info(f"Купил рейтинг: {count}")

    async def worker(self, client, user_id):
        while self.running:
            try:
                await self.buy_fuel(client)
                await asyncio.sleep(3)
                balance = await self.get_balance(client)
                logger.info(f"Баланс: {balance:,} крышек")

                if self.mode == "banks":
                    caps_to_spend = min(balance, self.bank_purchase_limit_caps) if self.bank_purchase_limit_caps else balance
                    max_banks = caps_to_spend // self.caps_per_bank_cost
                    
                    if balance < self.buy_less_threshold_caps:
                        banks_to_buy = max_banks
                    else:
                        banks_to_buy = max(0, max_banks - self.buy_less_quantity)
                    
                    if banks_to_buy > 0:
                        await self.buy_banks(client, banks_to_buy)

                elif self.mode == "rating":
                    max_rating = balance // self.rating_item_cost
                    if balance < self.buy_less_threshold_caps:
                        rating_to_buy = max_rating
                    else:
                        rating_to_buy = max(0, max_rating - self.buy_less_quantity)
                    
                    if rating_to_buy > 0:
                        await self.buy_rating(client, rating_to_buy)

                await asyncio.sleep(3600)

            except asyncio.CancelledError:
                logger.info("AutoBanki остановлен")
                break
            except Exception as e:
                logger.error(f"Ошибка AutoBanki: {e}")
                await asyncio.sleep(60)

# ================= МОДУЛЬ 2: BFGBunker =================
class BFGBunkerModule:
    def __init__(self):
        self.bot = "@bfgbunker_bot"
        self.bot_id = 5813222348
        self.resources_map = {
            range(0, 500): "картошку",
            range(501, 2000): "морковь",
            range(2001, 5000): "рис",
            range(5001, 10000): "чеснок",
            range(10001, 25000): "свеклу",
            range(25001, 40000): "огурец",
            range(40001, 60000): "капусту",
            range(60001, 100000): "фасоль",
            range(100001, 125000): "помидор",
            range(125001, 10**50): "баклажан"
        }
        self.room_names = [
            "Теплица", "Генераторная", "Столовая", "Станция обработки воды", "Сейф",
            "Игровая комната", "Медпункт", "Радиостанция", "Оружейная", "Кухня",
            "Гостиная", "Шахта", "Отдел аномалий", "Лаборатория",
            "Сад", "Автомастерская", "Гильдия", "Киберспортивная комната",
            "Адронный коллайдер", "Реактор"
        ]
        self.base_caps = [
            6, 6, 6, 6, 12, 20, 32, 52, 92, 144,
            234, 380, 450, 520, 750, 1030, 1430, 2020, 3520, 5020
        ]
        self.emoji_to_num = {
            '1️⃣': 1, '2️⃣': 2, '3️⃣': 3, '4️⃣': 4, '5️⃣': 5,
            '6️⃣': 6, '7️⃣': 7, '8️⃣': 8, '9️⃣': 9, '🔟': 10,
        }
        self.mine_resources = ["Песок", "Уголь", "Железо", "Медь", "Серебро", "Алмаз", "Уран"]
        self.pickaxe_type = "каменную кирку"
        self.vip_level = 0
        self.mine_diamond = False
        self.auto_mine = False
        self.auto_greenhouse = False
        self.auto_fuel = False
        self.auto_entrance = False
        self.auto_daily = False
        self.auto_cans = False
        self.auto_room = False

    async def get_resource_by_exp(self, exp: int) -> str:
        for range_obj, resource in self.resources_map.items():
            if exp in range_obj:
                return resource
        return "баклажан"

    async def mine(self, client):
        try:
            await client.send_message(self.bot, "копать")
            await asyncio.sleep(2)
            msgs = await client.get_messages(self.bot, limit=2)
            
            for msg in msgs:
                if not msg.text:
                    continue
                text = msg.text.lower()
                
                if "у тебя нет кирки" in text:
                    await client.send_message(self.bot, f"Купить {self.pickaxe_type}")
                    return
                
                if "отдохнёт" in text:
                    return
                
                if msg.buttons and "нашёл" in text:
                    if len(msg.buttons) > 0 and len(msg.buttons[0]) > 0:
                        await msg.buttons[0][0].click()
                        
        except Exception as e:
            logger.error(f"Ошибка при копании: {e}")

    async def greenhouse(self, client):
        try:
            await client.send_message(self.bot, "Моя теплица")
            await asyncio.sleep(3)
            msgs = await client.get_messages(self.bot, limit=2)
            
            for msg in msgs:
                if not msg.text:
                    continue
                if "Опыт:" in msg.text and "Вода:" in msg.text:
                    exp_match = re.search(r"Опыт:\s*(\d+)", msg.text)
                    water_match = re.search(r"Вода:\s*(\d+)/", msg.text)
                    if exp_match and water_match:
                        exp = int(exp_match.group(1))
                        water = int(water_match.group(1))
                        resource = await self.get_resource_by_exp(exp)
                        
                        for _ in range(water):
                            await client.send_message(self.bot, f"вырастить {resource}")
                            await asyncio.sleep(1)
                            msgs2 = await client.get_messages(self.bot, limit=1)
                            if msgs2 and msgs2[0].text and "у тебя не хватает" in msgs2[0].text.lower():
                                break
        except Exception as e:
            logger.error(f"Ошибка теплицы: {e}")

    async def fuel(self, client):
        try:
            await client.send_message(self.bot, "Бензин")
            await asyncio.sleep(2)
            msgs = await client.get_messages(self.bot, limit=3)
            for msg in msgs:
                if msg.sender_id == self.bot_id and msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if btn.text == "Купить бензин":
                                await btn.click()
                                return
        except Exception as e:
            logger.error(f"Ошибка бензина: {e}")

    async def entrance(self, client):
        try:
            await client.send_message(self.bot, "Бункер")
            await asyncio.sleep(3)
            msgs = await client.get_messages(self.bot, limit=2)
            
            for msg in msgs:
                if not msg.text:
                    continue
                lines = msg.text.splitlines()
                people_in_bunker = None
                people_in_queue = None
                max_capacity = None
                
                for line in lines:
                    if "Людей в бункере:" in line:
                        people_in_bunker = int(''.join(filter(str.isdigit, line)))
                    elif "Людей в очереди в бункер:" in line:
                        parts = line.split("/")
                        if len(parts) > 0:
                            people_in_queue = int(''.join(filter(str.isdigit, parts[0])))
                    elif "Макс. вместимость людей:" in line:
                        max_capacity = int(''.join(filter(str.isdigit, line)))
                
                if people_in_queue and people_in_bunker is not None and max_capacity:
                    max_to_admit = min(people_in_queue, max_capacity - people_in_bunker)
                    if max_to_admit > 0:
                        await client.send_message(self.bot, f"впустить {max_to_admit}")
        except Exception as e:
            logger.error(f"Ошибка впуска: {e}")

    async def daily(self, client):
        try:
            await client.send_message(self.bot, "Ежедневный бонус")
        except Exception as e:
            logger.error(f"Ошибка ежедневного бонуса: {e}")

    async def cans(self, client):
        try:
            await client.send_message(self.bot, "Бункер")
            await asyncio.sleep(2)
            msgs = await client.get_messages(self.bot, limit=2)
            for msg in msgs:
                if not msg.text:
                    continue
                if "Бутылок:" in msg.text:
                    bottles = int(''.join(filter(str.isdigit, msg.text.split("Бутылок:")[1].split()[0])))
                    if bottles > 0:
                        await client.send_message(self.bot, f"Купить банки {bottles // 10}")
        except Exception as e:
            logger.error(f"Ошибка покупки банок: {e}")

    async def room_upgrade(self, client):
        try:
            await client.send_message(self.bot, "Бункер")
            await asyncio.sleep(3)
            msgs = await client.get_messages(self.bot, limit=2)
            
            for msg in msgs:
                if not msg.text:
                    continue
                lines = msg.text.splitlines()
                room_levels = {}
                
                for line in lines:
                    if "ур." in line:
                        parts = line.strip().split()
                        if len(parts) < 2:
                            continue
                        emoji = parts[0]
                        room_num = self.emoji_to_num.get(emoji)
                        if not room_num:
                            digits = ''.join(filter(str.isdigit, emoji))
                            if digits:
                                room_num = int(digits)
                        if room_num and 1 <= room_num <= 20:
                            level_match = re.search(r"(\d+)\s*ур\.", line)
                            if level_match:
                                room_levels[room_num] = int(level_match.group(1))
                
                if room_levels:
                    min_room = None
                    min_cap = float('inf')
                    for room_num, level in room_levels.items():
                        cap = self.base_caps[room_num - 1] + (level - 1) * 2
                        if cap < min_cap:
                            min_cap = cap
                            min_room = room_num
                    
                    if min_room:
                        await client.send_message(self.bot, f"к {min_room}")
                        await asyncio.sleep(2)
                        msgs2 = await client.get_messages(self.bot, limit=2)
                        for m in msgs2:
                            if m.buttons:
                                for row in m.buttons:
                                    for btn in row:
                                        if "upgrade_roommi" in str(btn.callback_data):
                                            await btn.click()
                                            await asyncio.sleep(1)
                                            break
                        await client.send_message(self.bot, "починить бункер")
        except Exception as e:
            logger.error(f"Ошибка прокачки комнат: {e}")

    async def get_bunker_info(self, client) -> str:
        try:
            await client.send_message(self.bot, "Бункер")
            await asyncio.sleep(3)
            msgs = await client.get_messages(self.bot, limit=2)
            for msg in msgs:
                if msg.text:
                    return msg.text
            return "Не удалось получить информацию"
        except Exception as e:
            return f"Ошибка: {e}"

# ================= МОДУЛЬ 3: BunkerMine =================
class BunkerMineModule:
    def __init__(self):
        self.bot = "@bfgbunker_bot"
        self.bot_id = 5813222348
        self.mine_active = False
        self.fuel_active = False
        self.is_repairing = False
        self.mine_task = None
        self.fuel_task = None
        self.check_delay = 15
        self.fuel_delay = 30
        self.fuel_threshold = 50

    async def check_mine(self, client, user_id: int):
        try:
            if self.is_repairing:
                return
            
            await client.send_message(self.bot, "Моя шахта")
            await asyncio.sleep(4)
            msgs = await client.get_messages(self.bot, limit=3)
            
            for msg in msgs:
                if not msg.text:
                    continue
                text = msg.text.lower()
                
                if "сломан" in text or "🛠" in text:
                    if msg.buttons:
                        for row in msg.buttons:
                            for btn in row:
                                if "почин" in btn.text.lower() and ("крыш" in btn.text.lower() or "10" in btn.text):
                                    await btn.click()
                                    self.is_repairing = True
                                    logger.info("Шахта сломана, начат ремонт")
                                    await asyncio.sleep(15 * 60)
                                    self.is_repairing = False
                                    logger.info("Ремонт завершен")
                                    return
        except Exception as e:
            logger.error(f"Ошибка проверки шахты: {e}")

    async def check_fuel(self, client):
        try:
            await client.send_message(self.bot, "Бензин")
            await asyncio.sleep(3)
            msgs = await client.get_messages(self.bot, limit=2)
            
            for msg in msgs:
                if msg.sender_id == self.bot_id and msg.text:
                    percent_match = re.search(r'(\d+)%', msg.text)
                    if percent_match:
                        fuel_percent = int(percent_match.group(1))
                        if fuel_percent <= self.fuel_threshold and msg.buttons:
                            for row in msg.buttons:
                                for btn in row:
                                    if "заправить" in btn.text.lower() or "пополнить" in btn.text.lower():
                                        await btn.click()
                                        logger.info(f"Бензин пополнен ({fuel_percent}%)")
                                        return
        except Exception as e:
            logger.error(f"Ошибка проверки бензина: {e}")

    async def mine_loop(self, client, user_id: int):
        while self.mine_active:
            try:
                if not self.is_repairing:
                    await self.check_mine(client, user_id)
                await asyncio.sleep(self.check_delay * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка цикла шахты: {e}")
                await asyncio.sleep(60)

    async def fuel_loop(self, client):
        while self.fuel_active:
            try:
                await self.check_fuel(client)
                await asyncio.sleep(self.fuel_delay * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка цикла бензина: {e}")
                await asyncio.sleep(60)

# ================= ИНИЦИАЛИЗАЦИЯ МОДУЛЕЙ =================
autobanki = AutoBankiModule()
bfgbunker = BFGBunkerModule()
bunkermine = BunkerMineModule()

# ================= КОМАНДЫ =================

# 1. Проверка пинга
@app.on_message(filters.command("ping", prefixes="/") & filters.user(SUDO_USERS))
async def ping_command(client, message: Message):
    start = time.time()
    await message.edit_text("🏓 Понг...")
    delta = (time.time() - start) * 1000
    await message.edit_text(f"🏓 Понг! Задержка: {delta:.2f} мс")

# 2. Информация о себе с аватаркой
@app.on_message(filters.command("info", prefixes="/") & filters.user(SUDO_USERS))
async def info_command(client, message: Message):
    me = await client.get_me()
    
    await message.edit_text("⏳ Загружаю информацию...")
    
    photo_path = None
    try:
        chat = await client.get_chat(me.id)
        if chat.photo:
            photo_path = await client.download_media(
                chat.photo.big_file_id,
                file_name="my_avatar.jpg"
            )
    except Exception as e:
        logging.warning(f"Не удалось скачать аватарку: {e}")
        photo_path = None
    
    text = (
        f"👤 **Мой профиль**\n\n"
        f"🆔 **ID:** `{me.id}`\n"
        f"📛 **Имя:** {me.first_name or 'Нет'}\n"
        f"📛 **Фамилия:** {me.last_name or 'Нет'}\n"
        f"👥 **Юзернейм:** @{me.username or 'Нет'}\n"
        f"📱 **Номер:** А вот тебе все скажи\n"
    )
    
    if hasattr(me, 'date') and me.date:
        text += f"📅 **Аккаунт создан:** {me.date.date()}\n"
    
    if photo_path and os.path.exists(photo_path):
        try:
            await message.delete()
            await client.send_photo(
                chat_id=message.chat.id,
                photo=photo_path,
                caption=text
            )
            os.remove(photo_path)
        except Exception as e:
            logging.error(f"Ошибка при отправке фото: {e}")
            await message.edit_text(text)
    else:
        await message.edit_text(text)

# 3. Информация о пользователе с аватаркой
@app.on_message(filters.command("find", prefixes="/") & filters.user(SUDO_USERS))
async def find_command(client, message: Message):
    if not message.reply_to_message:
        me = await client.get_me()
        
        await message.edit_text("⏳ Загружаю информацию...")
        
        photo_path = None
        try:
            chat = await client.get_chat(me.id)
            if chat.photo:
                photo_path = await client.download_media(
                    chat.photo.big_file_id,
                    file_name="my_avatar.jpg"
                )
        except Exception as e:
            logging.warning(f"Не удалось скачать аватарку: {e}")
            photo_path = None
        
        text = (
            f"👤 **Мой профиль**\n\n"
            f"🆔 **ID:** `{me.id}`\n"
            f"📛 **Имя:** {me.first_name or 'Нет'}\n"
            f"📛 **Фамилия:** {me.last_name or 'Нет'}\n"
            f"👥 **Юзернейм:** @{me.username or 'Нет'}\n"
            f"📱 **Номер:** А вот тебе все скажи\n"
        )
        
        if hasattr(me, 'date') and me.date:
            text += f"📅 **Аккаунт создан:** {me.date.date()}\n"
        
        if photo_path and os.path.exists(photo_path):
            try:
                await message.delete()
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=photo_path,
                    caption=text
                )
                os.remove(photo_path)
            except Exception as e:
                logging.error(f"Ошибка при отправке фото: {e}")
                await message.edit_text(text)
        else:
            await message.edit_text(text)
    else:
        target_user = message.reply_to_message.from_user
        
        if not target_user:
            await message.edit_text("❌ Не удалось получить информацию о пользователе.")
            return
        
        await message.edit_text("⏳ Ищу информацию о пользователе...")
        
        photo_path = None
        try:
            chat = await client.get_chat(target_user.id)
            if chat.photo:
                photo_path = await client.download_media(
                    chat.photo.big_file_id,
                    file_name=f"user_avatar_{target_user.id}.jpg"
                )
        except Exception as e:
            logging.warning(f"Не удалось скачать аватарку пользователя: {e}")
            photo_path = None
        
        text = (
            f"👤 **Информация о пользователе**\n\n"
            f"🆔 **ID:** `{target_user.id}`\n"
            f"📛 **Имя:** {target_user.first_name or 'Нет'}\n"
            f"📛 **Фамилия:** {target_user.last_name or 'Нет'}\n"
            f"👥 **Юзернейм:** @{target_user.username or 'Нет'}\n"
            f"📱 **Номер:** без курымдыка не расскажу\n"
        )
        
        if photo_path and os.path.exists(photo_path):
            try:
                await message.delete()
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=photo_path,
                    caption=text
                )
                os.remove(photo_path)
            except Exception as e:
                logging.error(f"Ошибка при отправке фото: {e}")
                await message.edit_text(text)
        else:
            await message.edit_text(text + "\n\n❌ Аватарка не найдена")

# 4. Калькулятор
@app.on_message(filters.command("e", prefixes="/") & filters.user(SUDO_USERS))
async def calc_command(client, message: Message):
    try:
        expression = message.text.split("/e", 1)[1].strip()
        if not expression:
            await message.edit_text(
                "❌ **Ошибка!**\n\n"
                "📝 **Использование:** `/e выражение`\n"
                "📌 **Примеры:**\n"
                "   `/e 2+2` → 4\n"
                "   `/e 10*5` → 50\n"
                "   `/e 100/4` → 25\n"
                "   `/e 2**10` → 1024\n"
                "   `/e (10+5)*2` → 30"
            )
            return
        result = eval(expression, {"__builtins__": {}}, {"sqrt": math.sqrt})
        text = (
            f"Калькулятор\n\n"
            f'Выражение: "{expression}"\n'
            f'Результат: "{result}"'
        )
        await message.edit_text(text)
    except ZeroDivisionError:
        await message.edit_text("❌ Ошибка: Деление на ноль!")
    except Exception as e:
        await message.edit_text(f"❌ Ошибка: {e}")

# ================= КОМАНДЫ СПАМА =================

# 5. Спам с управлением
@app.on_message(filters.command("spam", prefixes="/") & filters.user(SUDO_USERS))
async def spam_command(client, message: Message):
    global spam_counter, active_spams
    
    try:
        parts = message.text.split("/spam", 1)[1].strip()
        args = parts.rsplit(" ", 2)
        
        if len(args) < 3:
            await message.edit_text(
                "❌ Ошибка в параметрах!\n\n"
                "📝 Использование: /spam сообщение задержка кол-во\n"
                "⏱️ Задержка: число (секунды)\n"
                "🔢 Кол-во: целое число\n\n"
                "Пример: /spam Привет всем! 2 5"
            )
            return
        
        text_to_spam = args[0].strip()
        delay = float(args[1].strip())
        count = int(args[2].strip())
        
        if count > 50:
            await message.edit_text("⚠️ Слишком много! Максимум 50 сообщений.")
            return
        
        if delay < 0.5:
            await message.edit_text("⚠️ Слишком маленькая задержка! Минимум 0.5 секунды.")
            return
        
        if count <= 0 or delay <= 0:
            await message.edit_text("❌ Задержка и количество должны быть больше 0!")
            return
        
        spam_counter += 1
        task_id = spam_counter
        
        spam_task = SpamTask(
            task_id=task_id,
            client=client,
            chat_id=message.chat.id,
            text=text_to_spam,
            delay=delay,
            total_count=count,
            reply_to_message=message.reply_to_message
        )
        
        active_spams[task_id] = spam_task
        spam_task.task = asyncio.create_task(spam_task.run())
        
        chat_name = message.chat.title or "личка"
        
        await message.edit_text(
            f"✅ **Спам запущен!**\n\n"
            f"🆔 **Номер спама:** `{task_id}`\n"
            f"📝 **Текст:** {text_to_spam}\n"
            f"⏱️ **Задержка:** {delay} сек.\n"
            f"🔢 **Всего:** {count}\n"
            f"💬 **Чат:** {chat_name}\n\n"
            f"🛑 `/stopspam {task_id}`"
        )
        
    except ValueError:
        await message.edit_text(
            "❌ Ошибка в параметрах!\n\n"
            "📝 Использование: /spam сообщение задержка кол-во\n"
            "⏱️ Задержка: число (секунды)\n"
            "🔢 Кол-во: целое число\n\n"
            "Пример: /spam Привет всем! 2 5"
        )
    except Exception as e:
        await message.edit_text(f"❌ Ошибка: {e}")

# 6. Хард спам с управлением
@app.on_message(filters.command("hspam", prefixes="/") & filters.user(SUDO_USERS))
async def hspam_command(client, message: Message):
    global spam_counter, active_spams
    
    try:
        parts = message.text.split("/hspam", 1)[1].strip()
        args = parts.rsplit(" ", 1)
        
        if len(args) < 2:
            await message.edit_text(
                "❌ Ошибка в параметрах!\n\n"
                "📝 Использование: /hspam сообщение кол-во\n"
                "⏱️ Задержка: 0.1 секунды\n"
                "🔢 Кол-во: целое число\n\n"
                "Пример: /hspam Привет всем! 10"
            )
            return
        
        text_to_spam = args[0].strip()
        count = int(args[1].strip())
        
        if count > 100:
            await message.edit_text("⚠️ Слишком много! Максимум 100 сообщений.")
            return
        
        if count <= 0:
            await message.edit_text("❌ Количество должно быть больше 0!")
            return
        
        spam_counter += 1
        task_id = spam_counter
        
        spam_task = SpamTask(
            task_id=task_id,
            client=client,
            chat_id=message.chat.id,
            text=text_to_spam,
            delay=0.1,
            total_count=count,
            reply_to_message=message.reply_to_message
        )
        
        active_spams[task_id] = spam_task
        spam_task.task = asyncio.create_task(spam_task.run())
        
        chat_name = message.chat.title or "личка"
        
        await message.edit_text(
            f"⚡ **Хард спам запущен!**\n\n"
            f"🆔 **Номер спама:** `{task_id}`\n"
            f"📝 **Текст:** {text_to_spam}\n"
            f"⏱️ **Задержка:** 0.1 сек.\n"
            f"🔢 **Всего:** {count}\n"
            f"💬 **Чат:** {chat_name}\n\n"
            f"🛑 `/stopspam {task_id}`"
        )
        
    except ValueError:
        await message.edit_text(
            "❌ Ошибка в параметрах!\n\n"
            "📝 Использование: /hspam сообщение кол-во\n"
            "⏱️ Задержка: 0.1 секунды\n\n"
            "Пример: /hspam Привет всем! 10"
        )
    except Exception as e:
        await message.edit_text(f"❌ Ошибка: {e}")

# 7. Информация о спаме
@app.on_message(filters.command("spaminfo", prefixes="/") & filters.user(SUDO_USERS))
async def spaminfo_command(client, message: Message):
    """Показать информацию о активных спамах"""
    if not active_spams:
        await message.edit_text("❌ Нет активных спам-задач.")
        return
    
    text = "📊 **Активные спам-задачи:**\n\n"
    found = False
    
    for task_id, task in active_spams.items():
        if not task.running:
            continue
        
        found = True
        chat_name = "личка"
        try:
            chat = await client.get_chat(task.chat_id)
            chat_name = chat.title or "личка"
        except:
            pass
        
        remaining = task.total - task.sent
        elapsed = int(time.time() - task.start_time)
        minutes = elapsed // 60
        seconds = elapsed % 60
        
        text += (
            f"🆔 **#{task_id}**\n"
            f"📝 Текст: `{task.text[:30]}{'...' if len(task.text) > 30 else ''}`\n"
            f"📤 Отправлено: {task.sent}/{task.total}\n"
            f"⏳ Осталось: **{remaining}**\n"
            f"⏱️ Задержка: {task.delay} сек.\n"
            f"💬 Чат: {chat_name}\n"
            f"🕐 Время: {minutes}м {seconds}с\n"
            f"🛑 `/stopspam {task_id}`\n\n"
        )
    
    if not found:
        await message.edit_text("❌ Нет активных спам-задач.")
        return
    
    await message.edit_text(text)

# 8. Остановка спама по номеру
@app.on_message(filters.command("stopspam", prefixes="/") & filters.user(SUDO_USERS))
async def stopspam_command(client, message: Message):
    """Остановить спам по номеру"""
    args = message.text.split("/stopspam", 1)[1].strip() if "/stopspam" in message.text else None
    
    if not args:
        await message.edit_text(
            "❌ Укажи номер спама!\n\n"
            "📝 Использование: `/stopspam [номер]`\n"
            "📌 Номер можно узнать через `/spaminfo`"
        )
        return
    
    try:
        task_id = int(args.strip())
    except ValueError:
        await message.edit_text("❌ Номер должен быть числом!")
        return
    
    if task_id not in active_spams:
        await message.edit_text(f"❌ Спам с номером `{task_id}` не найден!")
        return
    
    task = active_spams[task_id]
    
    if not task.running:
        await message.edit_text(f"❌ Спам с номером `{task_id}` уже остановлен!")
        return
    
    task.running = False
    if task.task:
        task.task.cancel()
    
    remaining = task.total - task.sent
    
    await message.edit_text(
        f"⏹️ **Спам #{task_id} остановлен!**\n\n"
        f"📤 Отправлено: {task.sent}/{task.total}\n"
        f"⏳ Осталось: {remaining}\n"
        f"📝 Текст: {task.text[:50]}{'...' if len(task.text) > 50 else ''}"
    )

# 9. Остановка всех спамов
@app.on_message(filters.command("stopallspam", prefixes="/") & filters.user(SUDO_USERS))
async def stopallspam_command(client, message: Message):
    """Остановить все активные спамы"""
    if not active_spams:
        await message.edit_text("❌ Нет активных спам-задач.")
        return
    
    stopped_count = 0
    
    for task_id, task in list(active_spams.items()):
        if task.running:
            task.running = False
            if task.task:
                task.task.cancel()
            stopped_count += 1
    
    await message.edit_text(f"⏹️ **Остановлено {stopped_count} спам-задач!**")

# ================= НОВЫЕ КОМАНДЫ =================

# 10. Тегирование всех
@app.on_message(filters.command("all", prefixes="/") & filters.user(SUDO_USERS))
async def all_command(client, message: Message):
    """Тегирование всех участников чата"""
    if not message.chat:
        await message.edit_text("❌ Эта команда работает только в группах!")
        return
    
    text = message.text.split("/all", 1)[1].strip() if "/all" in message.text else "Внимание!"
    
    if not text:
        text = "Внимание!"
    
    await message.edit_text("⏳ Получаю список участников...")
    
    try:
        members = []
        async for member in client.get_chat_members(message.chat.id):
            try:
                if member.user.username:
                    members.append(f"@{member.user.username}")
                elif member.user.first_name:
                    members.append(f"[{member.user.first_name}](tg://user?id={member.user.id})")
                else:
                    members.append(f"[Пользователь](tg://user?id={member.user.id})")
            except:
                continue
        
        if not members:
            await message.edit_text("❌ Не удалось получить список участников!")
            return
        
        chunk_size = 50
        chunks = [members[i:i + chunk_size] for i in range(0, len(members), chunk_size)]
        
        await message.delete()
        
        for i, chunk in enumerate(chunks):
            try:
                if i == 0:
                    await client.send_message(
                        message.chat.id,
                        f"📢 **{text}**\n\n" + "\n".join(chunk),
                        disable_web_page_preview=True
                    )
                else:
                    await client.send_message(
                        message.chat.id,
                        "\n".join(chunk),
                        disable_web_page_preview=True
                    )
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Ошибка отправки тегов: {e}")
                break
                
    except Exception as e:
        await message.edit_text(f"❌ Ошибка: {e}")

# 11. Погода
@app.on_message(filters.command("weather", prefixes="/") & filters.user(SUDO_USERS))
async def weather_command(client, message: Message):
    city = message.text.split("/weather", 1)[1].strip() if "/weather" in message.text else None
    if not city:
        await message.edit_text("❌ Укажи город!\nПример: `/weather Москва`")
        return
    await message.edit_text("⏳ Получаю погоду...")
    result = await get_weather(city)
    await message.edit_text(result)

# 12. Курс валют
@app.on_message(filters.command("currency", prefixes="/") & filters.user(SUDO_USERS))
async def currency_command(client, message: Message):
    args = message.text.split("/currency", 1)[1].strip().split() if "/currency" in message.text else []
    if len(args) < 2:
        await message.edit_text("❌ Укажи валюты!\nПример: `/currency USD RUB`")
        return
    from_currency = args[0].upper()
    to_currency = args[1].upper()
    await message.edit_text("⏳ Получаю курс...")
    result = await get_exchange_rate(from_currency, to_currency)
    await message.edit_text(result)

# 13. Переводчик
@app.on_message(filters.command("translate", prefixes="/") & filters.user(SUDO_USERS))
async def translate_command(client, message: Message):
    args = message.text.split("/translate", 1)[1].strip().split(" ", 1) if "/translate" in message.text else []
    if len(args) < 2:
        await message.edit_text("❌ Укажи язык и текст!\nПример: `/translate en Привет мир!`")
        return
    target_lang = args[0].strip()
    text = args[1].strip()
    if not text:
        await message.edit_text("❌ Напиши текст для перевода!")
        return
    await message.edit_text("⏳ Перевожу...")
    result = await translate_text(text, target_lang)
    await message.edit_text(result)

# 14. OCR
@app.on_message(filters.command("ocr", prefixes="/") & filters.user(SUDO_USERS))
async def ocr_command(client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.edit_text("❌ Ответь на сообщение с фото!\nПример: ответь на фото и напиши `/ocr`")
        return
    await message.edit_text("📷 Распознаю текст...")
    result = await ocr_image(client, message)
    await message.edit_text(result)

# ================= КОМАНДЫ AUTOBANKI =================

@app.on_message(filters.command("bb", prefixes="/") & filters.user(SUDO_USERS))
async def bb_command(client, message: Message):
    await bb_menu(client, message, edit=False)

async def bb_menu(client, message: Message, edit: bool = False):
    text = (f"💎 **Автобанки**\n"
            f"Статус: {'❤️‍🩹 Запущен' if autobanki.running else '💤 Остановлен'}\n"
            f"Режим: {'🍺 Банки' if autobanki.mode == 'banks' else '🎖️ Рейтинг'}")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🍺 Банки", callback_data="bb_banks"),
         InlineKeyboardButton("🎖️ Рейтинг", callback_data="bb_rating")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="close")]
    ])
    if edit:
        await message.edit(text, reply_markup=keyboard)
    else:
        await message.edit_text(text, reply_markup=keyboard)

@app.on_message(filters.command("setbanklimit", prefixes="/") & filters.user(SUDO_USERS))
async def setbanklimit_command(client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        limit_display = "Без лимита" if autobanki.bank_purchase_limit_caps is None else f"{autobanki.bank_purchase_limit_caps:,}".replace(",", " ")
        await message.edit_text(f"Текущий лимит: {limit_display} крышек.\nИспользуйте: /setbanklimit <количество> или /setbanklimit 0 для снятия")
        return
    arg = args[1].strip()
    if arg.lower() in ["0", "nolimit"]:
        autobanki.bank_purchase_limit_caps = None
        await message.edit_text("✅ Лимит снят!")
    else:
        try:
            limit = int(arg)
            if limit < 0:
                await message.edit_text("❌ Лимит не может быть отрицательным!")
                return
            autobanki.bank_purchase_limit_caps = limit
            await message.edit_text(f"✅ Лимит установлен: {limit:,} крышек".replace(",", " "))
        except ValueError:
            await message.edit_text("❌ Введите число или 'nolimit'")

@app.on_message(filters.command("start_autobanki", prefixes="/") & filters.user(SUDO_USERS))
async def start_autobanki(client, message: Message):
    if autobanki.running:
        await message.edit_text("⚠️ Автобанки уже запущены!")
        return
    autobanki.running = True
    autobanki.mode = "banks"
    autobanki.task = asyncio.create_task(autobanki.worker(client, message.from_user.id))
    await message.edit_text("✅ Автобанки запущены!\nРежим: Банки")

@app.on_message(filters.command("stop_autobanki", prefixes="/") & filters.user(SUDO_USERS))
async def stop_autobanki(client, message: Message):
    if not autobanki.running:
        await message.edit_text("⚠️ Автобанки не запущены!")
        return
    autobanki.running = False
    if autobanki.task:
        autobanki.task.cancel()
        autobanki.task = None
    await message.edit_text("⏹️ Автобанки остановлены!")

# ================= КОМАНДЫ BFGBUNKER =================

@app.on_message(filters.command("b", prefixes="/") & filters.user(SUDO_USERS))
async def b_command(client, message: Message):
    info = await bfgbunker.get_bunker_info(client)
    await message.edit_text(info)

@app.on_message(filters.command("minfo", prefixes="/") & filters.user(SUDO_USERS))
async def minfo_command(client, message: Message):
    text = (
        f"💡 **Статус модуля BFGBunker**\n\n"
        f"🔧 **Основные функции:**\n"
        f"• Добыча алмазов: {'✅' if bfgbunker.mine_diamond else '❌'}\n"
        f"• Ресурсы: {', '.join(bfgbunker.mine_resources)}\n"
        f"• Тип кирки: {bfgbunker.pickaxe_type}\n"
        f"• VIP уровень: {bfgbunker.vip_level}\n\n"
        f"🆔 **Бункер:**\n"
        f"• Авто-копание: {'✅' if bfgbunker.auto_mine else '❌'}\n"
        f"• Авто-теплица: {'✅' if bfgbunker.auto_greenhouse else '❌'}\n"
        f"• Авто-бензин: {'✅' if bfgbunker.auto_fuel else '❌'}\n"
        f"• Авто-впуск: {'✅' if bfgbunker.auto_entrance else '❌'}\n"
        f"• Авто-банки: {'✅' if bfgbunker.auto_cans else '❌'}\n"
        f"• Авто-прокачка: {'✅' if bfgbunker.auto_room else '❌'}\n\n"
        f"❗ **Дополнительно:**\n"
        f"• Ежедневный бонус: {'✅' if bfgbunker.auto_daily else '❌'}"
    )
    await message.edit_text(text)

@app.on_message(filters.command("max", prefixes="/") & filters.user(SUDO_USERS))
async def max_command(client, message: Message):
    await message.edit_text("⏳ Получаю данные...")
    info = await bfgbunker.get_bunker_info(client)
    caps = {}
    found = 0
    current_people = "?"
    for i in range(len(bfgbunker.room_names)):
        patterns = [
            rf"{i+1}[^\d]*?{bfgbunker.room_names[i]}[^\d]*?(\d+)\s*ур\b",
            rf"{bfgbunker.room_names[i]}[^\d]*?(\d+)\s*ур\b"
        ]
        lvl = None
        for p in patterns:
            m = re.search(p, info)
            if m:
                lvl = int(m.group(1))
                break
        if lvl:
            found += 1
            caps[f"K{i+1}"] = (lvl - 1) * 2 + bfgbunker.base_caps[i]
    if not caps:
        await message.edit_text("❌ Не удалось получить данные о бункере")
        return
    current_people_match = re.search(r"🧍 Людей в бункере: (\d+)", info)
    if current_people_match:
        current_people = current_people_match.group(1)
    min_cap = min(caps.values()) if caps else 0
    result = f"❓ **Вместимость бункера**\n\n"
    for room, cap in sorted(caps.items(), key=lambda x: int(x[0][1:])):
        result += f"🔵 {room} - {cap} чел.\n"
    result += f"\n👤 Чел сейчас: {current_people}\n"
    result += f"📊 Макс. вместимость: {min_cap} чел.\n"
    result += f"🍔 Комнат открыто: {found}/{len(bfgbunker.room_names)}"
    await message.edit_text(result)

# ================= КОМАНДЫ BUNKERMINE =================

@app.on_message(filters.command("bmine", prefixes="/") & filters.user(SUDO_USERS))
async def bmine_command(client, message: Message):
    await bmine_menu(client, message, edit=False)

async def bmine_menu(client, message: Message, edit: bool = False):
    mine_status = "✅" if bunkermine.mine_active else "❌"
    fuel_status = "✅" if bunkermine.fuel_active else "❌"
    text = (
        f"🎮 **Панель управления**\n\n"
        f"⛽ Бензин: {fuel_status}\n"
        f"🔧 Авто-починка: {mine_status}\n"
        f"⏱ Интервал: {bunkermine.check_delay} мин\n"
        f"📊 Порог бензина: {bunkermine.fuel_threshold}%\n"
        f"⏱ Интервал бензина: {bunkermine.fuel_delay} мин"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅' if bunkermine.fuel_active else '❌'} Бензин", callback_data="mine_fuel_toggle")],
        [InlineKeyboardButton(f"{'✅' if bunkermine.mine_active else '❌'} Авто-починка", callback_data="mine_toggle")],
        [InlineKeyboardButton("⏲ Интервал проверки", callback_data="mine_interval")],
        [InlineKeyboardButton("📊 Интервал бензина", callback_data="mine_fuel_interval")],
        [InlineKeyboardButton("📊 Порог бензина", callback_data="mine_threshold")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="close")]
    ])
    if edit:
        await message.edit(text, reply_markup=keyboard)
    else:
        await message.edit_text(text, reply_markup=keyboard)

# ================= КОМАНДЫ ВКЛЮЧЕНИЯ BFGBUNKER =================

@app.on_message(filters.command("mine_on", prefixes="/") & filters.user(SUDO_USERS))
async def mine_on(client, message: Message):
    bfgbunker.auto_mine = True
    await message.edit_text("✅ Авто-копание включено!")

@app.on_message(filters.command("mine_off", prefixes="/") & filters.user(SUDO_USERS))
async def mine_off(client, message: Message):
    bfgbunker.auto_mine = False
    await message.edit_text("❌ Авто-копание выключено!")

@app.on_message(filters.command("greenhouse_on", prefixes="/") & filters.user(SUDO_USERS))
async def greenhouse_on(client, message: Message):
    bfgbunker.auto_greenhouse = True
    await message.edit_text("✅ Авто-теплица включена!")

@app.on_message(filters.command("greenhouse_off", prefixes="/") & filters.user(SUDO_USERS))
async def greenhouse_off(client, message: Message):
    bfgbunker.auto_greenhouse = False
    await message.edit_text("❌ Авто-теплица выключена!")

@app.on_message(filters.command("fuel_on", prefixes="/") & filters.user(SUDO_USERS))
async def fuel_on(client, message: Message):
    bfgbunker.auto_fuel = True
    await message.edit_text("✅ Авто-бензин включен!")

@app.on_message(filters.command("fuel_off", prefixes="/") & filters.user(SUDO_USERS))
async def fuel_off(client, message: Message):
    bfgbunker.auto_fuel = False
    await message.edit_text("❌ Авто-бензин выключен!")

@app.on_message(filters.command("entrance_on", prefixes="/") & filters.user(SUDO_USERS))
async def entrance_on(client, message: Message):
    bfgbunker.auto_entrance = True
    await message.edit_text("✅ Авто-впуск включен!")

@app.on_message(filters.command("entrance_off", prefixes="/") & filters.user(SUDO_USERS))
async def entrance_off(client, message: Message):
    bfgbunker.auto_entrance = False
    await message.edit_text("❌ Авто-впуск выключен!")

@app.on_message(filters.command("cans_on", prefixes="/") & filters.user(SUDO_USERS))
async def cans_on(client, message: Message):
    bfgbunker.auto_cans = True
    await message.edit_text("✅ Авто-банки включены!")

@app.on_message(filters.command("cans_off", prefixes="/") & filters.user(SUDO_USERS))
async def cans_off(client, message: Message):
    bfgbunker.auto_cans = False
    await message.edit_text("❌ Авто-банки выключены!")

@app.on_message(filters.command("room_on", prefixes="/") & filters.user(SUDO_USERS))
async def room_on(client, message: Message):
    bfgbunker.auto_room = True
    await message.edit_text("✅ Авто-прокачка включена!")

@app.on_message(filters.command("room_off", prefixes="/") & filters.user(SUDO_USERS))
async def room_off(client, message: Message):
    bfgbunker.auto_room = False
    await message.edit_text("❌ Авто-прокачка выключена!")

@app.on_message(filters.command("all_on", prefixes="/") & filters.user(SUDO_USERS))
async def all_on(client, message: Message):
    bfgbunker.auto_mine = True
    bfgbunker.auto_greenhouse = True
    bfgbunker.auto_fuel = True
    bfgbunker.auto_entrance = True
    bfgbunker.auto_cans = True
    bfgbunker.auto_room = True
    await message.edit_text("✅ Все авто-функции включены!")

@app.on_message(filters.command("all_off", prefixes="/") & filters.user(SUDO_USERS))
async def all_off(client, message: Message):
    bfgbunker.auto_mine = False
    bfgbunker.auto_greenhouse = False
    bfgbunker.auto_fuel = False
    bfgbunker.auto_entrance = False
    bfgbunker.auto_cans = False
    bfgbunker.auto_room = False
    await message.edit_text("❌ Все авто-функции выключены!")

# ================= КОМАНДЫ BUNKERMINE (текстовые) =================

@app.on_message(filters.command("repair_on", prefixes="/") & filters.user(SUDO_USERS))
async def repair_on(client, message: Message):
    bunkermine.mine_active = True
    if bunkermine.mine_task:
        bunkermine.mine_task.cancel()
    bunkermine.mine_task = asyncio.create_task(bunkermine.mine_loop(client, message.from_user.id))
    await message.edit_text("✅ Авто-починка шахты включена!")

@app.on_message(filters.command("repair_off", prefixes="/") & filters.user(SUDO_USERS))
async def repair_off(client, message: Message):
    bunkermine.mine_active = False
    if bunkermine.mine_task:
        bunkermine.mine_task.cancel()
        bunkermine.mine_task = None
    await message.edit_text("❌ Авто-починка шахты выключена!")

@app.on_message(filters.command("fuel_mine_on", prefixes="/") & filters.user(SUDO_USERS))
async def fuel_mine_on(client, message: Message):
    bunkermine.fuel_active = True
    if bunkermine.fuel_task:
        bunkermine.fuel_task.cancel()
    bunkermine.fuel_task = asyncio.create_task(bunkermine.fuel_loop(client))
    await message.edit_text("✅ Автобензин в шахте включен!")

@app.on_message(filters.command("fuel_mine_off", prefixes="/") & filters.user(SUDO_USERS))
async def fuel_mine_off(client, message: Message):
    bunkermine.fuel_active = False
    if bunkermine.fuel_task:
        bunkermine.fuel_task.cancel()
        bunkermine.fuel_task = None
    await message.edit_text("❌ Автобензин в шахте выключен!")

# ================= КОЛБЭКИ =================

@app.on_callback_query()
async def callback_handler(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in SUDO_USERS:
        await callback.answer("⛔ Нет доступа!", show_alert=True)
        return
    
    data = callback.data
    
    # ===== BUNKERMINE =====
    if data == "mine_toggle":
        bunkermine.mine_active = not bunkermine.mine_active
        if bunkermine.mine_active:
            if bunkermine.mine_task:
                bunkermine.mine_task.cancel()
            bunkermine.mine_task = asyncio.create_task(bunkermine.mine_loop(client, user_id))
            await callback.answer("✅ Авто-починка включена!")
        else:
            if bunkermine.mine_task:
                bunkermine.mine_task.cancel()
                bunkermine.mine_task = None
            await callback.answer("❌ Авто-починка выключена!")
        await bmine_menu(client, callback.message, edit=True)
    
    elif data == "mine_fuel_toggle":
        bunkermine.fuel_active = not bunkermine.fuel_active
        if bunkermine.fuel_active:
            if bunkermine.fuel_task:
                bunkermine.fuel_task.cancel()
            bunkermine.fuel_task = asyncio.create_task(bunkermine.fuel_loop(client))
            await callback.answer("✅ Бензин включен!")
        else:
            if bunkermine.fuel_task:
                bunkermine.fuel_task.cancel()
                bunkermine.fuel_task = None
            await callback.answer("❌ Бензин выключен!")
        await bmine_menu(client, callback.message, edit=True)
    
    elif data == "mine_interval":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("2 мин", callback_data="mine_set_2"),
             InlineKeyboardButton("5 мин", callback_data="mine_set_5"),
             InlineKeyboardButton("10 мин", callback_data="mine_set_10")],
            [InlineKeyboardButton("15 мин", callback_data="mine_set_15")],
            [InlineKeyboardButton("🔙 Назад", callback_data="mine_back")]
        ])
        await callback.edit_message_text("⏲ Выберите интервал проверки шахты:", reply_markup=keyboard)
    
    elif data == "mine_fuel_interval":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("5 мин", callback_data="fuel_set_5"),
             InlineKeyboardButton("10 мин", callback_data="fuel_set_10"),
             InlineKeyboardButton("15 мин", callback_data="fuel_set_15")],
            [InlineKeyboardButton("30 мин", callback_data="fuel_set_30"),
             InlineKeyboardButton("45 мин", callback_data="fuel_set_45"),
             InlineKeyboardButton("60 мин", callback_data="fuel_set_60")],
            [InlineKeyboardButton("🔙 Назад", callback_data="mine_back")]
        ])
        await callback.edit_message_text("⛽ Выберите интервал проверки бензина:", reply_markup=keyboard)
    
    elif data == "mine_threshold":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("20%", callback_data="thr_set_20"),
             InlineKeyboardButton("30%", callback_data="thr_set_30"),
             InlineKeyboardButton("40%", callback_data="thr_set_40")],
            [InlineKeyboardButton("50%", callback_data="thr_set_50"),
             InlineKeyboardButton("60%", callback_data="thr_set_60"),
             InlineKeyboardButton("70%", callback_data="thr_set_70")],
            [InlineKeyboardButton("80%", callback_data="thr_set_80")],
            [InlineKeyboardButton("🔙 Назад", callback_data="mine_back")]
        ])
        await callback.edit_message_text("📊 Выберите порог бензина:", reply_markup=keyboard)
    
    elif data.startswith("mine_set_"):
        minutes = int(data.split("_")[2])
        bunkermine.check_delay = minutes
        await callback.answer(f"✅ Интервал: {minutes} мин")
        await bmine_menu(client, callback.message, edit=True)
    
    elif data.startswith("fuel_set_"):
        minutes = int(data.split("_")[2])
        bunkermine.fuel_delay = minutes
        await callback.answer(f"✅ Интервал бензина: {minutes} мин")
        await bmine_menu(client, callback.message, edit=True)
    
    elif data.startswith("thr_set_"):
        percent = int(data.split("_")[2])
        bunkermine.fuel_threshold = percent
        await callback.answer(f"✅ Порог бензина: {percent}%")
        await bmine_menu(client, callback.message, edit=True)
    
    elif data == "mine_back":
        await bmine_menu(client, callback.message, edit=True)
    
    # ===== AUTOBANKI =====
    elif data == "bb_banks":
        autobanki.mode = "banks"
        text = (f"🍺 **Режим: Банки**\n"
                f"Статус: {'❤️‍🩹 Запущен' if autobanki.running else '💤 Остановлен'}\n\n"
                f"Стоимость 1 банки: {autobanki.caps_per_bank_cost} крышек\n"
                f"Порог 'покупать меньше': {autobanki.buy_less_threshold_caps:,} кр".replace(",", " "))
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💤 Остановить" if autobanki.running else "❤️‍🩹 Запустить", callback_data="bb_toggle")],
            [InlineKeyboardButton("🔙 Назад", callback_data="bb_back")]
        ])
        await callback.edit_message_text(text, reply_markup=keyboard)
    
    elif data == "bb_rating":
        autobanki.mode = "rating"
        text = (f"🎖️ **Режим: Рейтинг**\n"
                f"Статус: {'❤️‍🩹 Запущен' if autobanki.running else '💤 Остановлен'}\n\n"
                f"Стоимость 1 рейтинга: {autobanki.rating_item_cost} крышек\n"
                f"Порог 'покупать меньше': {autobanki.buy_less_threshold_caps:,} кр".replace(",", " "))
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💤 Остановить" if autobanki.running else "❤️‍🩹 Запустить", callback_data="bb_toggle")],
            [InlineKeyboardButton("🔙 Назад", callback_data="bb_back")]
        ])
        await callback.edit_message_text(text, reply_markup=keyboard)
    
    elif data == "bb_toggle":
        if autobanki.running:
            autobanki.running = False
            if autobanki.task:
                autobanki.task.cancel()
                autobanki.task = None
            await callback.answer("⏹️ Автобанки остановлены!", show_alert=True)
        else:
            autobanki.running = True
            autobanki.task = asyncio.create_task(autobanki.worker(client, user_id))
            await callback.answer("✅ Автобанки запущены!", show_alert=True)
        await bb_menu(client, callback.message, edit=True)
    
    elif data == "bb_back":
        await bb_menu(client, callback.message, edit=True)
    
    # ===== ОБЩЕЕ =====
    elif data == "close":
        await callback.message.delete()
        await callback.answer()

# ================= ЗАПУСК =================
if __name__ == "__main__":
    print("🚀 Юзербот запускается...")
    print("📝 Доступные команды:")
    print("   /ping - Проверка задержки")
    print("   /info - Информация о профиле (с аватаркой)")
    print("   /find - Информация о пользователе (с аватаркой)")
    print("   /e [выражение] - Калькулятор")
    print("   /spam [текст] [задержка] [кол-во] - Спам с управлением")
    print("   /hspam [текст] [кол-во] - Хард спам (0.1 сек)")
    print("   /spaminfo - Информация о активных спамах")
    print("   /stopspam [номер] - Остановить спам по номеру")
    print("   /stopallspam - Остановить все спамы")
    print("   /all [текст] - Тегирование всех участников")
    print("   /weather [город] - Погода")
    print("   /currency [из] [в] - Курс валют")
    print("   /translate [язык] [текст] - Переводчик")
    print("   /ocr - Распознать текст с фото (ответь на фото)")
    print("")
    print("💎 КОМАНДЫ AUTOBANKI:")
    print("   /bb - Меню автобанков")
    print("   /setbanklimit - Установить лимит банок")
    print("   /start_autobanki - Запустить автобанки")
    print("   /stop_autobanki - Остановить автобанки")
    print("")
    print("🏗 КОМАНДЫ BFGBUNKER:")
    print("   /b - Информация из бункера")
    print("   /minfo - Статус модуля BFGBunker")
    print("   /max - Вместимость бункера")
    print("   /mine_on/off - Авто-копание")
    print("   /greenhouse_on/off - Авто-теплица")
    print("   /fuel_on/off - Авто-бензин")
    print("   /entrance_on/off - Авто-впуск")
    print("   /cans_on/off - Авто-банки")
    print("   /room_on/off - Авто-прокачка")
    print("   /all_on/off - Включить всё")
    print("")
    print("⛏ КОМАНДЫ BUNKERMINE:")
    print("   /bmine - Панель управления шахтой")
    print("   /repair_on/off - Авто-починка шахты")
    print("   /fuel_mine_on/off - Автобензин в шахте")
    
    # ЗАПУСК БЕЗ phone_number (будет запрошен в консоли, но на Railway не работает)
    app.run()
