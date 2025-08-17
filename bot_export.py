#!/usr/bin/env python3
"""
Экспорт истории чата через Bot API (без Telethon)
Использует только Bot API для получения сообщений
"""

import asyncio
import json
import base64
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from io import BytesIO

import aiohttp
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

@dataclass
class ChatMessage:
    """Структура сообщения для векторной базы"""
    id: int
    chat_id: int
    user_id: Optional[int]
    username: Optional[str]
    user_full_name: Optional[str]
    date: str
    text: str
    message_type: str
    has_media: bool
    media_description: Optional[str] = None
    image_base64: Optional[str] = None

class BotChatExporter:
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        self.chat_id = os.getenv('CHAT_ID')
        
        if not all([self.bot_token, self.chat_id]):
            raise ValueError("Необходимо установить BOT_TOKEN и CHAT_ID в .env")
        
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.exported_messages: List[ChatMessage] = []

    async def get_chat_info(self, session):
        """Получение информации о чате"""
        url = f"{self.base_url}/getChat"
        params = {"chat_id": self.chat_id}
        
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data["ok"]:
                    chat = data["result"]
                    return chat.get("title", "Unknown Chat")
        return "Unknown Chat"

    async def download_file(self, session, file_path: str) -> Optional[bytes]:
        """Скачивание файла через Bot API"""
        file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        
        try:
            async with session.get(file_url) as response:
                if response.status == 200:
                    return await response.read()
        except Exception as e:
            print(f"Ошибка при скачивании файла: {e}")
        return None

    async def get_file_info(self, session, file_id: str) -> Optional[str]:
        """Получение информации о файле"""
        url = f"{self.base_url}/getFile"
        params = {"file_id": file_id}
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data["ok"]:
                        return data["result"]["file_path"]
        except Exception as e:
            print(f"Ошибка при получении информации о файле: {e}")
        return None

    async def process_photo(self, session, photos: List[Dict]) -> tuple:
        """Обработка фотографий"""
        if not photos:
            return None, None
        
        # Берем фото наибольшего размера
        largest_photo = max(photos, key=lambda p: p["width"] * p["height"])
        file_id = largest_photo["file_id"]
        
        file_path = await self.get_file_info(session, file_id)
        if not file_path:
            return None, "Изображение (не удалось загрузить)"
        
        file_bytes = await self.download_file(session, file_path)
        if not file_bytes:
            return None, "Изображение (не удалось загрузить)"
        
        try:
            image = Image.open(BytesIO(file_bytes))
            
            # Уменьшение размера
            max_size = (800, 800)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Конвертация в base64
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            return image_base64, "Изображение"
        
        except Exception as e:
            print(f"Ошибка при обработке изображения: {e}")
            return None, "Изображение (ошибка обработки)"

    async def get_updates(self, session, offset: int = 0, limit: int = 100):
        """Получение обновлений через getUpdates"""
        url = f"{self.base_url}/getUpdates"
        params = {
            "offset": offset,
            "limit": limit,
            "timeout": 1
        }
        
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data["ok"]:
                        return data["result"]
        except Exception as e:
            print(f"Ошибка при получении обновлений: {e}")
        return []

    async def export_recent_messages(self, limit: int = 100):
        """Экспорт последних сообщений через getUpdates"""
        async with aiohttp.ClientSession() as session:
            chat_title = await self.get_chat_info(session)
            print(f"Экспорт чата: {chat_title} (ID: {self.chat_id})")
            
            # Получаем последние обновления
            updates = await self.get_updates(session, limit=limit)
            
            messages = []
            for update in updates:
                if "message" in update:
                    message = update["message"]
                    if message.get("chat", {}).get("id") == int(self.chat_id):
                        messages.append(message)
            
            print(f"Найдено {len(messages)} сообщений в обновлениях")
            
            if not messages:
                print("Сообщения не найдены. Попробуйте отправить новые сообщения в чат.")
                return
            
            for i, message in enumerate(messages):
                try:
                    # Информация о пользователе
                    user = message.get("from", {})
                    user_id = user.get("id")
                    username = user.get("username")
                    first_name = user.get("first_name", "")
                    last_name = user.get("last_name", "")
                    user_full_name = f"{first_name} {last_name}".strip()
                    
                    # Текст сообщения
                    text = message.get("text", "")
                    
                    # Дата
                    date = datetime.fromtimestamp(message["date"]).isoformat()
                    
                    # Тип сообщения и медиа
                    message_type = "text"
                    has_media = False
                    image_base64 = None
                    media_description = None
                    
                    # Обработка фотографий
                    if "photo" in message:
                        has_media = True
                        message_type = "photo"
                        image_base64, media_description = await self.process_photo(session, message["photo"])
                    
                    # Обработка документов
                    elif "document" in message:
                        has_media = True
                        message_type = "document"
                        doc = message["document"]
                        if doc.get("mime_type", "").startswith("image/"):
                            media_description = "Документ с изображением"
                    
                    # Обработка стикеров
                    elif "sticker" in message:
                        has_media = True
                        message_type = "sticker"
                        media_description = "Стикер"
                    
                    # Создание объекта сообщения
                    chat_message = ChatMessage(
                        id=message["message_id"],
                        chat_id=int(self.chat_id),
                        user_id=user_id,
                        username=username,
                        user_full_name=user_full_name,
                        date=date,
                        text=text,
                        message_type=message_type,
                        has_media=has_media,
                        media_description=media_description,
                        image_base64=image_base64
                    )
                    
                    self.exported_messages.append(chat_message)
                    
                    print(f"Обработано сообщение {i+1}/{len(messages)}: {text[:50]}...")
                    
                except Exception as e:
                    print(f"Ошибка при обработке сообщения: {e}")
                    continue

    def save_to_json(self, filename: str = None):
        """Сохранение в JSON формат"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"bot_export_{timestamp}.json"
        
        data = []
        for msg in self.exported_messages:
            msg_dict = {
                "id": msg.id,
                "chat_id": msg.chat_id,
                "user_id": msg.user_id,
                "username": msg.username,
                "user_full_name": msg.user_full_name,
                "date": msg.date,
                "text": msg.text,
                "message_type": msg.message_type,
                "has_media": msg.has_media,
                "media_description": msg.media_description,
                "image_base64": msg.image_base64
            }
            data.append(msg_dict)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"Данные сохранены в {filename}")
        return filename

    def prepare_for_vector_db(self, filename: str = None):
        """Подготовка данных для векторной базы OpenAI"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"bot_vector_db_{timestamp}.jsonl"
        
        with open(filename, 'w', encoding='utf-8') as f:
            for msg in self.exported_messages:
                content_parts = []
                
                if msg.text:
                    content_parts.append(f"Текст: {msg.text}")
                
                if msg.media_description:
                    content_parts.append(f"Медиа: {msg.media_description}")
                
                metadata = {
                    "message_id": msg.id,
                    "chat_id": msg.chat_id,
                    "user_id": msg.user_id,
                    "username": msg.username,
                    "user_full_name": msg.user_full_name,
                    "date": msg.date,
                    "message_type": msg.message_type,
                    "has_media": msg.has_media
                }
                
                vector_entry = {
                    "content": " | ".join(content_parts) if content_parts else "Пустое сообщение",
                    "metadata": metadata
                }
                
                if msg.image_base64:
                    vector_entry["image_base64"] = msg.image_base64
                
                f.write(json.dumps(vector_entry, ensure_ascii=False) + '\n')
        
        print(f"Данные для векторной базы сохранены в {filename}")
        return filename

async def main():
    """Основная функция"""
    try:
        exporter = BotChatExporter()
        
        print(f"Экспорт чата ID: {exporter.chat_id}")
        print("Получение последних сообщений через Bot API...")
        
        await exporter.export_recent_messages(limit=100)
        
        if exporter.exported_messages:
            json_file = exporter.save_to_json()
            vector_file = exporter.prepare_for_vector_db()
            
            print(f"\nЭкспорт завершен!")
            print(f"Обработано сообщений: {len(exporter.exported_messages)}")
            print(f"JSON файл: {json_file}")
            print(f"Файл для векторной базы: {vector_file}")
        else:
            print("Сообщения не найдены")
            print("Отправьте несколько сообщений в чат и повторите экспорт")
            
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())