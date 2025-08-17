#!/usr/bin/env python3
"""
Скрипт для экспорта истории чата Telegram в формат для векторной базы OpenAI.
Собирает текстовые сообщения и изображения из чатов.
"""

import asyncio
import json
import base64
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from io import BytesIO

from telethon import TelegramClient
from telethon.tl.types import (
    Message, 
    MessageMediaPhoto, 
    MessageMediaDocument,
    User,
    Chat,
    Channel
)
from PIL import Image
import openai
from dotenv import load_dotenv

load_dotenv()

@dataclass
class ChatMessage:
    """Структура сообщения для векторной базы"""
    id: int
    chat_id: int
    chat_title: str
    user_id: Optional[int]
    username: Optional[str]
    user_full_name: Optional[str]
    date: str
    text: str
    message_type: str  # 'text', 'photo', 'document'
    has_media: bool
    media_description: Optional[str] = None
    image_base64: Optional[str] = None
    reply_to_message_id: Optional[int] = None

class TelegramChatExporter:
    def __init__(self):
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        
        if not all([self.api_id, self.api_hash, self.phone]):
            raise ValueError("Необходимо установить TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE в .env")
        
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
        
        self.client = TelegramClient('session', int(self.api_id), self.api_hash)
        self.exported_messages: List[ChatMessage] = []

    async def connect(self):
        """Подключение к Telegram"""
        await self.client.start(phone=self.phone)
        print("Подключен к Telegram")

    async def get_chat_info(self, entity) -> tuple:
        """Получение информации о чате"""
        if isinstance(entity, User):
            return entity.id, f"{entity.first_name or ''} {entity.last_name or ''}".strip()
        elif isinstance(entity, Chat):
            return entity.id, entity.title
        elif isinstance(entity, Channel):
            return entity.id, entity.title
        else:
            return None, "Unknown"

    async def describe_image_with_openai(self, image_base64: str) -> Optional[str]:
        """Описание изображения через OpenAI Vision API"""
        if not self.openai_api_key:
            return None
        
        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Опиши это изображение подробно на русском языке. Если это мем или шутка, объясни контекст и юмор."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Ошибка при описании изображения: {e}")
            return None

    async def process_media(self, message: Message) -> tuple:
        """Обработка медиафайлов из сообщения"""
        image_base64 = None
        media_description = None
        
        if message.media:
            if isinstance(message.media, MessageMediaPhoto):
                try:
                    # Скачивание фото
                    photo_bytes = await self.client.download_media(message.media, file=BytesIO())
                    
                    # Конвертация в base64
                    if photo_bytes:
                        photo_bytes.seek(0)
                        image = Image.open(photo_bytes)
                        
                        # Уменьшение размера для экономии места
                        max_size = (800, 800)
                        image.thumbnail(max_size, Image.Resampling.LANCZOS)
                        
                        # Конвертация в base64
                        buffer = BytesIO()
                        image.save(buffer, format='JPEG', quality=85)
                        image_base64 = base64.b64encode(buffer.getvalue()).decode()
                        
                        # Получение описания через OpenAI
                        media_description = await self.describe_image_with_openai(image_base64)
                        
                except Exception as e:
                    print(f"Ошибка при обработке фото: {e}")
                    
            elif isinstance(message.media, MessageMediaDocument):
                # Обработка документов (стикеры, GIF и т.д.)
                if message.media.document.mime_type.startswith('image/'):
                    try:
                        doc_bytes = await self.client.download_media(message.media, file=BytesIO())
                        if doc_bytes:
                            doc_bytes.seek(0)
                            image = Image.open(doc_bytes)
                            
                            max_size = (800, 800)
                            image.thumbnail(max_size, Image.Resampling.LANCZOS)
                            
                            buffer = BytesIO()
                            image.save(buffer, format='JPEG', quality=85)
                            image_base64 = base64.b64encode(buffer.getvalue()).decode()
                            
                            media_description = await self.describe_image_with_openai(image_base64)
                            
                    except Exception as e:
                        print(f"Ошибка при обработке документа: {e}")
        
        return image_base64, media_description

    async def export_chat_history(self, chat_username_or_id: str, limit: int = 1000):
        """Экспорт истории чата"""
        try:
            entity = await self.client.get_entity(chat_username_or_id)
            chat_id, chat_title = await self.get_chat_info(entity)
            
            print(f"Экспорт чата: {chat_title} (ID: {chat_id})")
            
            messages = []
            async for message in self.client.iter_messages(entity, limit=limit):
                if isinstance(message, Message):
                    messages.append(message)
            
            print(f"Найдено {len(messages)} сообщений")
            
            for i, message in enumerate(messages):
                try:
                    # Информация о пользователе
                    user_id = None
                    username = None
                    user_full_name = None
                    
                    if message.sender:
                        if isinstance(message.sender, User):
                            user_id = message.sender.id
                            username = message.sender.username
                            user_full_name = f"{message.sender.first_name or ''} {message.sender.last_name or ''}".strip()
                    
                    # Текст сообщения
                    text = message.text or ""
                    
                    # Тип сообщения
                    message_type = "text"
                    has_media = False
                    
                    if message.media:
                        has_media = True
                        if isinstance(message.media, MessageMediaPhoto):
                            message_type = "photo"
                        elif isinstance(message.media, MessageMediaDocument):
                            message_type = "document"
                    
                    # Обработка медиафайлов
                    image_base64, media_description = await self.process_media(message)
                    
                    # Создание объекта сообщения
                    chat_message = ChatMessage(
                        id=message.id,
                        chat_id=chat_id,
                        chat_title=chat_title,
                        user_id=user_id,
                        username=username,
                        user_full_name=user_full_name,
                        date=message.date.isoformat(),
                        text=text,
                        message_type=message_type,
                        has_media=has_media,
                        media_description=media_description,
                        image_base64=image_base64,
                        reply_to_message_id=message.reply_to_msg_id
                    )
                    
                    self.exported_messages.append(chat_message)
                    
                    if (i + 1) % 50 == 0:
                        print(f"Обработано {i + 1}/{len(messages)} сообщений")
                        
                except Exception as e:
                    print(f"Ошибка при обработке сообщения {message.id}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Ошибка при экспорте чата: {e}")

    def save_to_json(self, filename: str = None):
        """Сохранение в JSON формат"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chat_export_{timestamp}.json"
        
        # Конвертация в словари для JSON
        data = []
        for msg in self.exported_messages:
            msg_dict = {
                "id": msg.id,
                "chat_id": msg.chat_id,
                "chat_title": msg.chat_title,
                "user_id": msg.user_id,
                "username": msg.username,
                "user_full_name": msg.user_full_name,
                "date": msg.date,
                "text": msg.text,
                "message_type": msg.message_type,
                "has_media": msg.has_media,
                "media_description": msg.media_description,
                "image_base64": msg.image_base64,
                "reply_to_message_id": msg.reply_to_message_id
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
            filename = f"vector_db_data_{timestamp}.jsonl"
        
        with open(filename, 'w', encoding='utf-8') as f:
            for msg in self.exported_messages:
                # Создание текста для векторизации
                content_parts = []
                
                # Основной текст
                if msg.text:
                    content_parts.append(f"Текст: {msg.text}")
                
                # Описание медиа
                if msg.media_description:
                    content_parts.append(f"Изображение: {msg.media_description}")
                
                # Метаданные
                metadata = {
                    "message_id": msg.id,
                    "chat_id": msg.chat_id,
                    "chat_title": msg.chat_title,
                    "user_id": msg.user_id,
                    "username": msg.username,
                    "user_full_name": msg.user_full_name,
                    "date": msg.date,
                    "message_type": msg.message_type,
                    "has_media": msg.has_media,
                    "reply_to_message_id": msg.reply_to_message_id
                }
                
                # Запись для векторной базы
                vector_entry = {
                    "content": " | ".join(content_parts),
                    "metadata": metadata
                }
                
                # Добавление base64 изображения отдельно если нужно
                if msg.image_base64:
                    vector_entry["image_base64"] = msg.image_base64
                
                f.write(json.dumps(vector_entry, ensure_ascii=False) + '\n')
        
        print(f"Данные для векторной базы сохранены в {filename}")
        return filename

    async def close(self):
        """Закрытие соединения"""
        await self.client.disconnect()

async def main():
    """Основная функция"""
    exporter = TelegramChatExporter()
    
    try:
        await exporter.connect()
        
        # Проверяем CHAT_ID в .env
        chat_id = os.getenv('CHAT_ID')
        
        if chat_id:
            print(f"Используется CHAT_ID из .env: {chat_id}")
            limit_input = input("Количество сообщений для экспорта (по умолчанию 1000): ")
            limit = int(limit_input) if limit_input.strip() else 1000
            await exporter.export_chat_history(int(chat_id), limit)
        else:
            # Примеры использования:
            # Экспорт по username чата
            chat_input = input("Введите username чата (например, @chatname) или ID: ")
            limit_input = input("Количество сообщений для экспорта (по умолчанию 1000): ")
            
            limit = int(limit_input) if limit_input.strip() else 1000
            
            await exporter.export_chat_history(chat_input, limit)
        
        if exporter.exported_messages:
            # Сохранение в JSON
            json_file = exporter.save_to_json()
            
            # Подготовка для векторной базы
            vector_file = exporter.prepare_for_vector_db()
            
            print(f"\nЭкспорт завершен!")
            print(f"Обработано сообщений: {len(exporter.exported_messages)}")
            print(f"JSON файл: {json_file}")
            print(f"Файл для векторной базы: {vector_file}")
        else:
            print("Сообщения не найдены")
            
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        await exporter.close()

if __name__ == "__main__":
    asyncio.run(main())