#!/usr/bin/env python3
"""
Создание сессии для Telethon (запустить один раз интерактивно)
"""

import os
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
phone = os.getenv('TELEGRAM_PHONE')

if not all([api_id, api_hash, phone]):
    print("Ошибка: установите TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE в .env")
    exit(1)

async def create_session():
    client = TelegramClient('session', int(api_id), api_hash)
    
    print("Создание сессии Telethon...")
    await client.start(phone=phone)
    print("✅ Сессия создана успешно!")
    
    # Тест подключения
    me = await client.get_me()
    print(f"Подключен как: {me.first_name} ({me.phone})")
    
    await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(create_session())