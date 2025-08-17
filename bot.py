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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не найден в .env файле")

client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

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
        
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Объясни этот мем или шутку на изображении. Расскажи, в чем юмор, какие культурные отсылки или контекст нужно знать, чтобы понять смысл. Отвечай на русском языке кратко и понятно."
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
            max_tokens=1000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка при анализе изображения: {e}")
        return "Извините, не смог проанализировать изображение. Попробуйте позже."

async def get_image_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bytes:
    photo = None
    
    logger.info(f"Проверяю изображения в сообщении")
    logger.info(f"Есть ли фото в сообщении: {bool(update.message.photo)}")
    logger.info(f"Есть ли reply: {bool(update.message.reply_to_message)}")
    
    if update.message.photo:
        photo = update.message.photo[-1]
        logger.info(f"Найдено фото в сообщении: {photo.file_id}")
    elif update.message.reply_to_message and update.message.reply_to_message.photo:
        photo = update.message.reply_to_message.photo[-1]
        logger.info(f"Найдено фото в reply: {photo.file_id}")
    
    if photo:
        file = await context.bot.get_file(photo.file_id)
        logger.info(f"Скачиваю изображение: {file.file_path}")
        image_data = await download_image(file.file_path)
        return image_data
    
    logger.info("Изображение не найдено")
    return None

async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        logger.info(f"Получена команда /explain от пользователя {user_id} в чате {chat_id}")
        
        image_data = await get_image_from_message(update, context)
        
        if not image_data:
            logger.info(f"Изображение не найдено в чате {chat_id}")
            await update.message.reply_text(
                f"Не найдено изображение для анализа. Прикрепите фото к сообщению или ответьте на сообщение с фото. (chat_id: {chat_id})"
            )
            return
        
        logger.info(f"Изображение найдено в чате {chat_id}, начинаю анализ")
        await update.message.reply_text(f"Анализирую изображение... (chat_id: {chat_id})")
        
        explanation = await analyze_image_with_openai(image_data)
        await update.message.reply_text(f"{explanation}\n\n(chat_id: {chat_id})")
        
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
            image_data = await get_image_from_message(update, context)
            
            if not image_data:
                logger.info(f"Изображение не найдено для триггерной фразы в чате {chat_id}")
                await update.message.reply_text(
                    f"Не вижу изображения для пояснения. Прикрепите фото или ответьте на сообщение с фото. (chat_id: {chat_id})"
                )
                return
            
            logger.info(f"Изображение найдено для триггерной фразы в чате {chat_id}, начинаю анализ")
            await update.message.reply_text(f"Пояснительная бригада прибыла! Анализирую... (chat_id: {chat_id})")
            
            explanation = await analyze_image_with_openai(image_data)
            await update.message.reply_text(f"🔍 {explanation}\n\n(chat_id: {chat_id})")
    
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = """
🤖 Пояснительная бригада готова к работе!

Я помогаю объяснять мемы и шутки на изображениях.

Команды:
/explain - объяснить мем на фото

Триггерные фразы:
• "Можно пояснительную бригаду?"
• "МПБ"
• "пояснительную бригаду"
• "не понял"

Просто напишите одну из фраз и прикрепите фото, или ответьте на сообщение с фото.
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