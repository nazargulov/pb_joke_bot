#!/usr/bin/env python3
"""
Скрипт для отлова и записи group ID при добавлении бота в группы.
Записывает информацию о всех группах, в которые добавлен бот.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, filters, ChatMemberHandler
from telegram.constants import ChatMemberStatus, ChatType
from dotenv import load_dotenv

load_dotenv()

class GroupIDDetector:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("BOT_TOKEN не найден в .env файле")
        
        self.groups_file = "detected_groups.json"
        self.groups_data = self.load_groups_data()
        
    def load_groups_data(self) -> Dict[str, Any]:
        """Загрузка существующих данных о группах"""
        if Path(self.groups_file).exists():
            try:
                with open(self.groups_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {"groups": {}, "last_updated": None}
        return {"groups": {}, "last_updated": None}
    
    def save_groups_data(self):
        """Сохранение данных о группах"""
        self.groups_data["last_updated"] = datetime.now().isoformat()
        with open(self.groups_file, 'w', encoding='utf-8') as f:
            json.dump(self.groups_data, f, ensure_ascii=False, indent=2)
        print(f"Данные сохранены в {self.groups_file}")
    
    async def save_group_info(self, chat_id: int, chat_title: str, chat_type: str, event_type: str = "detected"):
        """Сохранение информации о группе"""
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
        if group_key in self.groups_data["groups"]:
            existing = self.groups_data["groups"][group_key]
            group_info["first_detected"] = existing.get("first_detected", group_info["first_detected"])
            group_info["status"] = "active"
        
        self.groups_data["groups"][group_key] = group_info
        self.save_groups_data()
        
        print(f"📝 Группа сохранена:")
        print(f"   ID: {chat_id}")
        print(f"   Название: {chat_title}")
        print(f"   Тип: {chat_type}")
        print(f"   Событие: {event_type}")
    
    async def bot_added_handler(self, update: Update, context):
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
            
            await self.save_group_info(
                chat_id=chat.id,
                chat_title=chat.title or "Без названия",
                chat_type=chat.type,
                event_type="bot_added"
            )
            
            print(f"🚀 Бот добавлен в группу: {chat.title} (ID: {chat.id})")
        
        # Бот был удален из группы
        elif (old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR] and 
              new_status == ChatMemberStatus.LEFT):
            
            group_key = str(chat.id)
            if group_key in self.groups_data["groups"]:
                self.groups_data["groups"][group_key]["status"] = "removed"
                self.groups_data["groups"][group_key]["removed_at"] = datetime.now().isoformat()
                self.save_groups_data()
            
            print(f"❌ Бот удален из группы: {chat.title} (ID: {chat.id})")
    
    async def message_handler(self, update: Update, context):
        """Обработчик всех сообщений для отлова групп"""
        chat = update.effective_chat
        
        # Обрабатываем только группы и супергруппы
        if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
            await self.save_group_info(
                chat_id=chat.id,
                chat_title=chat.title or "Без названия",
                chat_type=chat.type,
                event_type="message_received"
            )
    
    async def scan_existing_chats(self, bot: Bot):
        """Сканирование существующих чатов при запуске"""
        print("🔍 Сканирование существующих чатов...")
        
        try:
            # Получаем обновления для поиска активных чатов
            updates = await bot.get_updates(limit=100, timeout=1)
            
            processed_chats = set()
            
            for update in updates:
                chat = None
                
                if update.message:
                    chat = update.message.chat
                elif update.edited_message:
                    chat = update.edited_message.chat
                elif update.channel_post:
                    chat = update.channel_post.chat
                elif update.edited_channel_post:
                    chat = update.edited_channel_post.chat
                
                if (chat and 
                    chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and 
                    chat.id not in processed_chats):
                    
                    processed_chats.add(chat.id)
                    
                    await self.save_group_info(
                        chat_id=chat.id,
                        chat_title=chat.title or "Без названия",
                        chat_type=chat.type,
                        event_type="startup_scan"
                    )
            
            print(f"✅ Найдено {len(processed_chats)} групп при сканировании")
            
        except Exception as e:
            print(f"⚠️ Ошибка при сканировании: {e}")
    
    def print_current_groups(self):
        """Вывод текущего списка групп"""
        print("\n📋 Текущие группы:")
        print("=" * 60)
        
        if not self.groups_data["groups"]:
            print("Группы не найдены")
            return
        
        for group_id, info in self.groups_data["groups"].items():
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
    
    async def run(self):
        """Запуск бота"""
        print("🤖 Запуск детектора Group ID...")
        print(f"📁 Файл для сохранения: {self.groups_file}")
        
        # Создание приложения
        application = Application.builder().token(self.bot_token).build()
        
        # Добавление обработчиков
        application.add_handler(ChatMemberHandler(self.bot_added_handler, ChatMemberHandler.MY_CHAT_MEMBER))
        application.add_handler(MessageHandler(filters.ALL, self.message_handler))
        
        # Сканирование существующих чатов
        await self.scan_existing_chats(application.bot)
        
        # Вывод текущих групп
        self.print_current_groups()
        
        print("\n🚀 Бот запущен! Добавляйте его в группы для отлова ID...")
        print("Для остановки нажмите Ctrl+C")
        
        # Запуск бота
        await application.run_polling(drop_pending_updates=True)

async def main():
    """Главная функция"""
    detector = None
    try:
        detector = GroupIDDetector()
        await detector.run()
    except KeyboardInterrupt:
        print("\n🛑 Остановка бота...")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        if detector:
            print("📋 Финальный список групп:")
            detector.print_current_groups()

if __name__ == "__main__":
    asyncio.run(main())