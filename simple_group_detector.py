#!/usr/bin/env python3
"""
Простой скрипт для отлова group ID при добавлении бота в группы.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ChatMemberHandler
from telegram.constants import ChatMemberStatus, ChatType
from dotenv import load_dotenv

load_dotenv()

# Глобальные переменные
GROUPS_FILE = "detected_groups.json"
groups_data = {"groups": {}, "last_updated": None}

def load_groups_data():
    """Загрузка существующих данных о группах"""
    global groups_data
    if Path(GROUPS_FILE).exists():
        try:
            with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                groups_data = json.load(f)
        except json.JSONDecodeError:
            groups_data = {"groups": {}, "last_updated": None}

def save_groups_data():
    """Сохранение данных о группах"""
    global groups_data
    groups_data["last_updated"] = datetime.now().isoformat()
    with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
        json.dump(groups_data, f, ensure_ascii=False, indent=2)
    print(f"✅ Данные сохранены в {GROUPS_FILE}")

def save_group_info(chat_id: int, chat_title: str, chat_type: str, event_type: str = "detected"):
    """Сохранение информации о группе"""
    global groups_data
    group_key = str(chat_id)
    
    group_info = {
        "id": chat_id,
        "title": chat_title,
        "type": chat_type,
        "first_detected": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat(),
        "event_type": event_type,
        "status": "active"
    }
    
    # Если группа уже есть, обновляем только время последней активности
    if group_key in groups_data["groups"]:
        existing = groups_data["groups"][group_key]
        group_info["first_detected"] = existing.get("first_detected", group_info["first_detected"])
        group_info["status"] = "active"
    
    groups_data["groups"][group_key] = group_info
    save_groups_data()
    
    print(f"📝 Группа сохранена:")
    print(f"   ID: {chat_id}")
    print(f"   Название: {chat_title}")
    print(f"   Тип: {chat_type}")
    print(f"   Событие: {event_type}")

async def bot_added_handler(update: Update, context):
    """Обработчик добавления бота в группу"""
    chat_member_update = update.my_chat_member or update.chat_member
    
    if not chat_member_update:
        return
    
    chat = chat_member_update.chat
    old_status = chat_member_update.old_chat_member.status if chat_member_update.old_chat_member else None
    new_status = chat_member_update.new_chat_member.status
    
    # Бот был добавлен в группу
    if (old_status in [ChatMemberStatus.LEFT, None] and 
        new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]):
        
        save_group_info(
            chat_id=chat.id,
            chat_title=chat.title or "Без названия",
            chat_type=chat.type,
            event_type="bot_added"
        )
        
        print(f"🚀 Бот добавлен в группу: {chat.title} (ID: {chat.id})")
    
    # Бот был удален из группы
    elif (old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR] and 
          new_status == ChatMemberStatus.LEFT):
        
        global groups_data
        group_key = str(chat.id)
        if group_key in groups_data["groups"]:
            groups_data["groups"][group_key]["status"] = "removed"
            groups_data["groups"][group_key]["removed_at"] = datetime.now().isoformat()
            save_groups_data()
        
        print(f"❌ Бот удален из группы: {chat.title} (ID: {chat.id})")

async def message_handler(update: Update, context):
    """Обработчик всех сообщений для отлова групп"""
    chat = update.effective_chat
    
    # Обрабатываем только группы и супергруппы
    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        save_group_info(
            chat_id=chat.id,
            chat_title=chat.title or "Без названия",
            chat_type=chat.type,
            event_type="message_received"
        )

def print_current_groups():
    """Вывод текущего списка групп"""
    global groups_data
    print("\n📋 Текущие группы:")
    print("=" * 60)
    
    if not groups_data["groups"]:
        print("Группы не найдены")
        return
    
    for group_id, info in groups_data["groups"].items():
        status_emoji = "✅" if info.get("status") == "active" else "❌"
        print(f"{status_emoji} {info['title']}")
        print(f"   ID: {info['id']}")
        print(f"   Тип: {info['type']}")
        print(f"   Статус: {info.get('status', 'unknown')}")
        print(f"   Обнаружено: {info.get('event_type', 'unknown')}")
        print(f"   Первое обнаружение: {info.get('first_detected', 'unknown')}")
        if info.get("removed_at"):
            print(f"   Удален: {info['removed_at']}")
        print("-" * 40)

def main():
    """Главная функция"""
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        print("❌ BOT_TOKEN не найден в .env файле")
        return
    
    print("🤖 Запуск детектора Group ID...")
    print(f"📁 Файл для сохранения: {GROUPS_FILE}")
    
    # Загрузка существующих данных
    load_groups_data()
    
    # Создание приложения
    application = Application.builder().token(bot_token).build()
    
    # Добавление обработчиков
    application.add_handler(ChatMemberHandler(bot_added_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.ALL, message_handler))
    
    # Вывод текущих групп
    print_current_groups()
    
    print("\n🚀 Бот запущен! Добавляйте его в группы для отлова ID...")
    print("Для остановки нажмите Ctrl+C")
    
    try:
        # Запуск бота
        application.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n🛑 Остановка бота...")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        print("📋 Финальный список групп:")
        print_current_groups()

if __name__ == "__main__":
    main()