import os
import logging
import asyncio
import base64
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import openai
import aiohttp

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SHOW_CHAT_ID = os.getenv('SHOW_CHAT_ID', 'false').lower() == 'true'

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не найден в .env файле")

client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

# Путь к файлу с системными инструкциями
INSTRUCTIONS_PATH = os.path.join(os.path.dirname(__file__), 'system_instructions.txt')

def load_system_instructions() -> str:
    """Загружает системные инструкции из файла"""
    try:
        with open(INSTRUCTIONS_PATH, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning("Файл system_instructions.txt не найден, используются стандартные инструкции")
        return ("Ты - Пояснительная Бригада! Объясняй мемы кратко и смешно. "
                "Формат: 1) Что мы тут имеем? 2) В чём прикол? 3) Откуда ноги растут? 4) Почему это зашло?")

TRIGGER_PHRASES = [
    "можно пояснительную бригаду",
    "мпб",
    "пояснительную бригаду", 
    "пояснительная бригада",
    "не понял"
]

async def download_image(file_url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as response:
            return await response.read()

async def analyze_image_with_openai(image_data: bytes) -> str:
    try:
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        system_instructions = load_system_instructions()
        
        logger.info("Загружены системные инструкции для анализа")
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_instructions
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Объясни этот мем или шутку на изображении!"
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
            max_tokens=1000,
            temperature=1,
            top_p=0.9,
            frequency_penalty=0.3,
            presence_penalty=0.2
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при анализе изображения: {e}")
        return "Извините, не смог проанализировать изображение. Попробуйте позже."

async def analyze_text_with_openai(text: str) -> str:
    try:
        system_instructions = load_system_instructions()
        
        logger.info(f"Анализирую текст: {text[:50]}...")
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": system_instructions
                },
                {
                    "role": "user",
                    "content": f"Объясни этот мем или шутку в тексте: '{text}'"
                }
            ],
            max_tokens=1000,
            temperature=1.1,
            top_p=0.9,
            frequency_penalty=0.3,
            presence_penalty=0.2
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при анализе текста: {e}")
        return "Извините, не смог проанализировать текст. Попробуйте позже."

async def get_image_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bytes:
    photo = None
    
    logger.info(f"=== ОТЛАДКА ИЗОБРАЖЕНИЙ ===")
    logger.info(f"Тип сообщения: {type(update.message)}")
    logger.info(f"ID сообщения: {update.message.message_id}")
    logger.info(f"Есть ли фото в сообщении: {bool(update.message.photo)}")
    if update.message.photo:
        logger.info(f"Количество фото: {len(update.message.photo)}")
        for i, p in enumerate(update.message.photo):
            logger.info(f"Фото {i}: {p.file_id}, размер: {p.width}x{p.height}")
    
    logger.info(f"Есть ли reply: {bool(update.message.reply_to_message)}")
    if update.message.reply_to_message:
        logger.info(f"ID reply сообщения: {update.message.reply_to_message.message_id}")
        logger.info(f"Есть ли фото в reply: {bool(update.message.reply_to_message.photo)}")
        if update.message.reply_to_message.photo:
            logger.info(f"Количество фото в reply: {len(update.message.reply_to_message.photo)}")
            for i, p in enumerate(update.message.reply_to_message.photo):
                logger.info(f"Reply фото {i}: {p.file_id}, размер: {p.width}x{p.height}")
    
    # Проверяем документы (может быть сжатое изображение)
    logger.info(f"Есть ли документ: {bool(update.message.document)}")
    if update.message.document:
        logger.info(f"Тип документа: {update.message.document.mime_type}")
    
    if update.message.reply_to_message and update.message.reply_to_message.document:
        logger.info(f"Есть документ в reply: {update.message.reply_to_message.document.mime_type}")
    
    # Основная логика поиска фото
    if update.message.photo:
        photo = update.message.photo[-1]
        logger.info(f"✅ Найдено фото в сообщении: {photo.file_id}")
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
        logger.info(f"✅ Найдено фото в reply: {photo.file_id}")
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith('image/'):
        logger.info(f"✅ Найдено изображение как документ: {update.message.document.file_id}")
        try:
            file = await context.bot.get_file(update.message.document.file_id)
            logger.info(f"Скачиваю изображение-документ: {file.file_path}")
            image_data = await download_image(file.file_path)
            return image_data
        except Exception as e:
            logger.error(f"Ошибка при скачивании документа: {e}")
    elif update.message.reply_to_message and update.message.reply_to_message.document and update.message.reply_to_message.document.mime_type and update.message.reply_to_message.document.mime_type.startswith('image/'):
        logger.info(f"✅ Найдено изображение как документ в reply: {update.message.reply_to_message.document.file_id}")
        try:
            file = await context.bot.get_file(update.message.reply_to_message.document.file_id)
            logger.info(f"Скачиваю изображение-документ из reply: {file.file_path}")
            image_data = await download_image(file.file_path)
            return image_data
        except Exception as e:
            logger.error(f"Ошибка при скачивании документа из reply: {e}")
    
    if photo:
        try:
            file = await context.bot.get_file(photo.file_id)
            logger.info(f"Скачиваю изображение: {file.file_path}")
            image_data = await download_image(file.file_path)
            logger.info(f"Изображение скачано, размер: {len(image_data)} bytes")
            return image_data
        except Exception as e:
            logger.error(f"Ошибка при скачивании фото: {e}")
            return None
    
    logger.info("❌ Изображение не найдено")
    return None

async def get_text_from_message(update: Update) -> str:
    """Получает текст из текущего сообщения или reply"""
    text = None
    
    logger.info("=== ОТЛАДКА ТЕКСТА ===")
    
    # Проверяем текст в текущем сообщении (исключая команду)
    if update.message.text:
        current_text = update.message.text.strip()
        # Убираем команду /explain если она есть
        if current_text.startswith('/explain'):
            current_text = current_text.replace('/explain', '').strip()
        
        if current_text and not any(phrase in current_text.lower() for phrase in TRIGGER_PHRASES):
            text = current_text
            logger.info(f"✅ Найден текст в сообщении: {text[:100]}...")
    
    # Проверяем текст в reply сообщении
    if not text and update.message.reply_to_message and update.message.reply_to_message.text:
        reply_text = update.message.reply_to_message.text.strip()
        if reply_text:
            text = reply_text
            logger.info(f"✅ Найден текст в reply: {text[:100]}...")
    
    if not text:
        logger.info("❌ Текст для анализа не найден")
    
    return text

async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        logger.info(f"Получена команда /explain от пользователя {user_id} в чате {chat_id}")
        
        # Сначала ищем изображение
        image_data = await get_image_from_message(update, context)
        
        if image_data:
            logger.info(f"Изображение найдено в чате {chat_id}, начинаю анализ")
            status_msg = "Анализирую изображение..."
            if SHOW_CHAT_ID:
                status_msg += f" (chat_id: {chat_id})"
            await update.message.reply_text(status_msg)
            
            explanation = await analyze_image_with_openai(image_data)
            response_msg = explanation
            if SHOW_CHAT_ID:
                response_msg += f"\n\n(chat_id: {chat_id})"
            await update.message.reply_text(response_msg)
            return
        
        # Если изображения нет, ищем текст
        text_to_analyze = await get_text_from_message(update)
        
        if text_to_analyze:
            logger.info(f"Текст найден в чате {chat_id}, начинаю анализ")
            status_msg = "Анализирую текст..."
            if SHOW_CHAT_ID:
                status_msg += f" (chat_id: {chat_id})"
            await update.message.reply_text(status_msg)
            
            explanation = await analyze_text_with_openai(text_to_analyze)
            response_msg = explanation
            if SHOW_CHAT_ID:
                response_msg += f"\n\n(chat_id: {chat_id})"
            await update.message.reply_text(response_msg)
            return
        
        # Если ничего не найдено
        logger.info(f"Ни изображение, ни текст не найдены в чате {chat_id}")
        error_msg = "Не найдено содержимое для анализа. Прикрепите фото, добавьте текст к команде или ответьте на сообщение с контентом."
        if SHOW_CHAT_ID:
            error_msg += f" (chat_id: {chat_id})"
        await update.message.reply_text(error_msg)
        
    except Exception as e:
        logger.error(f"Ошибка в команде /explain: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.")

async def handle_trigger_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = update.effective_chat.id
        message_text = update.message.text.lower() if update.message.text else ""
        logger.info(f"Получено сообщение: '{message_text}' в чате {chat_id}")
        
        if any(phrase in message_text for phrase in TRIGGER_PHRASES):
            logger.info(f"Найдена триггерная фраза в сообщении в чате {chat_id}")
            
            # Сначала ищем изображение
            image_data = await get_image_from_message(update, context)
            
            if image_data:
                logger.info(f"Изображение найдено для триггерной фразы в чате {chat_id}, начинаю анализ")
                status_msg = "Пояснительная бригада прибыла! Анализирую изображение..."
                if SHOW_CHAT_ID:
                    status_msg += f" (chat_id: {chat_id})"
                await update.message.reply_text(status_msg)
                
                explanation = await analyze_image_with_openai(image_data)
                response_msg = f"🔍 {explanation}"
                if SHOW_CHAT_ID:
                    response_msg += f"\n\n(chat_id: {chat_id})"
                await update.message.reply_text(response_msg)
                return
            
            # Если изображения нет, ищем текст
            text_to_analyze = await get_text_from_message(update)
            
            if text_to_analyze:
                logger.info(f"Текст найден для триггерной фразы в чате {chat_id}, начинаю анализ")
                status_msg = "Пояснительная бригада прибыла! Анализирую текст..."
                if SHOW_CHAT_ID:
                    status_msg += f" (chat_id: {chat_id})"
                await update.message.reply_text(status_msg)
                
                explanation = await analyze_text_with_openai(text_to_analyze)
                response_msg = f"🔍 {explanation}"
                if SHOW_CHAT_ID:
                    response_msg += f"\n\n(chat_id: {chat_id})"
                await update.message.reply_text(response_msg)
                return
            
            # Если ничего не найдено
            logger.info(f"Ни изображение, ни текст не найдены для триггерной фразы в чате {chat_id}")
            error_msg = "Не вижу контента для пояснения. Прикрепите фото, текст или ответьте на сообщение с контентом."
            if SHOW_CHAT_ID:
                error_msg += f" (chat_id: {chat_id})"
            await update.message.reply_text(error_msg)
    
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = """
🤖 Пояснительная бригада готова к работе!

Я помогаю объяснять мемы и шутки на изображениях И в тексте!

Команды:
/explain - объяснить мем (с фото, текстом или ответом на сообщение)

Триггерные фразы:
• "Можно пояснительную бригаду?"
• "МПБ"
• "пояснительную бригаду"
• "не понял"

Способы использования:
📸 Прикрепите фото к команде/фразе
📝 Добавьте текст к команде: "/explain твой мем 😂"
💬 Ответьте на сообщение с контентом
🎯 Смайлы тоже понимаю!
"""
    await update.message.reply_text(welcome_text)

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("explain", explain_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trigger_message))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()