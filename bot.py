import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
import asyncio
from datetime import datetime
from aiohttp import web

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8344746821:AAFBYCVkjmclVCTXKtOB6CGoLzJWSIWruxg"
OFFICE_CHAT_ID = -4897185289  # Чат для офісних задач
MASTERS_CHAT_ID = -4847787413  # Чат для майстрів
PORT = int(os.getenv('PORT', 8000))
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-actual-render-url.onrender.com')

worker_responses = {}

class TelegramTaskBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()

    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("webhook_info", self.webhook_info_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        worker_responses[user_id] = {
            'stage': 'ask_chat_type',
            'data': {},
            'timestamp': datetime.now()
        }
        await update.message.reply_text(
            "👋 Привіт! Я бот для управління завданнями\n"
            "🏆 \"Маркет послуг №1\"\n\n"
            "Допоможу розподілити задачі між командою!\n"
            "Почнемо! 🚀"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔧 Задачі майстрам", callback_data="chat_masters")],
            [InlineKeyboardButton("🏢 Задачі офісу", callback_data="chat_office")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Куди відправити завдання? 🎯", reply_markup=reply_markup)

    async def webhook_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            webhook_info = await context.bot.get_webhook_info()
            info_text = (
                f"🔗 **Webhook Info:**\n"
                f"URL: `{webhook_info.url}`\n"
                f"Has Custom Certificate: {webhook_info.has_custom_certificate}\n"
                f"Pending Update Count: {webhook_info.pending_update_count}\n"
                f"Last Error Date: {webhook_info.last_error_date}\n"
                f"Last Error Message: {webhook_info.last_error_message}\n"
                f"Max Connections: {webhook_info.max_connections}"
            )
            await update.message.reply_text(info_text, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"Error getting webhook info: {e}")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Для початку надішліть /start.\n"
            "Просто відповідайте на запитання, що з'являться.\n"
            "По кнопках обирайте варіанти."
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        logger.info(f"Processing message from user {user_id}: {text}")
        if user_id not in worker_responses:
            await update.message.reply_text("Будь ласка, надішліть /start щоб почати.")
            return
        stage = worker_responses[user_id]['stage']
        data = worker_responses[user_id]['data']
        if stage == 'ask_executor_name':
            data['executor_name'] = text
            worker_responses[user_id]['stage'] = 'ask_task_description'
            await update.message.reply_text("Опис задачі: 📋")
        elif stage == 'ask_task_description':
            data['task_description'] = text
            worker_responses[user_id]['stage'] = 'ask_deadline'
            
            keyboard = [
                [InlineKeyboardButton("🔴 Терміново зараз", callback_data="deadline_urgent")],
                [InlineKeyboardButton("🟠 1-2 дні", callback_data="deadline_1_2_days")],
                [InlineKeyboardButton("🟡 Тиждень", callback_data="deadline_week")],
                [InlineKeyboardButton("🟢 Місяць", callback_data="deadline_month")],
                [InlineKeyboardButton("⚪ Без терміну", callback_data="deadline_no_deadline")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Термін виконання: ⏰", reply_markup=reply_markup)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        data = query.data
        
        logger.info(f"CALLBACK QUERY - Button clicked by user {user_id}: {data}")
        
        try:
            await query.answer()
            logger.info(f"CALLBACK QUERY - Successfully answered callback for user {user_id}")
        except Exception as e:
            logger.error(f"CALLBACK QUERY - Error answering callback: {e}")
            return
        if user_id not in worker_responses:
            logger.warning(f"CALLBACK QUERY - User {user_id} not found in worker_responses")
            try:
                await query.edit_message_text("Сесія втрачена. Почніть заново /start.")
            except Exception as e:
                logger.error(f"CALLBACK QUERY - Error editing message: {e}")
            return
        if data.startswith("chat_"):
            chat_types = {
                "chat_masters": "🔧 Задачі майстрам",
                "chat_office": "🏢 Задачі офісу"
            }
            selected = chat_types.get(data, "Не вказано")
            worker_responses[user_id]['data']['chat_type'] = data
            worker_responses[user_id]['data']['chat_type_name'] = selected
            worker_responses[user_id]['stage'] = 'ask_executor_name'
            try:
                await query.edit_message_text(
                    f"Ви вибрали: {selected}\n\n"
                    "Ім'я виконавця: 👤"
                )
                logger.info(f"CALLBACK QUERY - User {user_id} selected chat type: {selected}")
            except Exception as e:
                logger.error(f"CALLBACK QUERY - Error updating message: {e}")
        elif data.startswith("deadline_"):
            deadline_options = {
                "deadline_urgent": "🔴 Терміново зараз",
                "deadline_1_2_days": "🟠 1-2 дні",
                "deadline_week": "🟡 Тиждень", 
                "deadline_month": "🟢 Місяць",
                "deadline_no_deadline": "⚪ Без терміну"
            }
            selected = deadline_options.get(data, "Не вказано")
            worker_responses[user_id]['data']['deadline'] = selected
            worker_responses[user_id]['stage'] = 'ready_to_submit'
            logger.info(f"CALLBACK QUERY - User {user_id} selected deadline: {selected}")
            keyboard = [
                [InlineKeyboardButton("📤 Відправити завдання", callback_data="submit_task")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await query.edit_message_text(
                    f"Термін виконання: {selected}\n\n"
                    "Натисніть кнопку для відправки завдання:",
                    reply_markup=reply_markup
                )
                logger.info(f"CALLBACK QUERY - Successfully updated message for user {user_id}")
            except Exception as e:
                logger.error(f"CALLBACK QUERY - Error updating message: {e}")
        elif data == "submit_task":
            logger.info(f"CALLBACK QUERY - User {user_id} submitting task")
            
            try:
                await self.send_task_from_callback(query, context, user_id)
                del worker_responses[user_id]
                await query.edit_message_text("✅ Ваше завдання успішно відправлено! Дякуємо!")
                logger.info(f"CALLBACK QUERY - Successfully submitted task for user {user_id}")
            except Exception as e:
                logger.error(f"CALLBACK QUERY - Error submitting task: {e}")
                await query.edit_message_text("❌ Помилка відправки завдання. Спробуйте пізніше.")

    async def send_task_from_callback(self, query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        data = worker_responses[user_id]['data']
        chat_id = MASTERS_CHAT_ID if data.get('chat_type') == 'chat_masters' else OFFICE_CHAT_ID
        
        if data.get('chat_type') == 'chat_masters':
            message = (
                "🔧 НОВЕ ЗАВДАННЯ ДЛЯ МАЙСТРІВ\n\n"
                f"👤 Виконавець: {data.get('executor_name', '-')}\n"
                f"📝 Завдання: {data.get('task_description', '-')}\n"
                f"⏰ Термін: {data.get('deadline', '-')}\n\n"
                "────────────────────────\n"
                "🏆 Маркет послуг №1"
            )
        else:
            message = (
                "📋 НОВЕ ЗАВДАННЯ ДЛЯ ОФІСУ\n\n"
                f"👤 Виконавець: {data.get('executor_name', '-')}\n"
                f"📝 Завдання: {data.get('task_description', '-')}\n"
                f"⏰ Термін: {data.get('deadline', '-')}\n\n"
                "────────────────────────\n"
                "🏆 Маркет послуг №1"
            )
        await context.bot.send_message(chat_id, message)

    async def run_webhook(self):
        await self.application.initialize()
        await self.application.start()
        
        app = web.Application()

        async def handle_post(request):
            try:
                data = await request.json()
                logger.info(f"Received webhook data: {data}")
                
                if 'callback_query' in data:
                    logger.info(f"WEBHOOK - Callback query detected: {data['callback_query']}")
                elif 'message' in data:
                    logger.info(f"WEBHOOK - Regular message detected: {data['message']}")
                else:
                    logger.warning(f"WEBHOOK - Unknown update type: {list(data.keys())}")
                
                update = Update.de_json(data, self.application.bot)
                
                if update is None:
                    logger.error("WEBHOOK - Failed to parse update from JSON")
                    return web.Response(text="ERROR: Failed to parse update", status=400)
                
                logger.info(f"WEBHOOK - Successfully parsed update: {update.update_id}")
                
                await self.application.process_update(update)
                logger.info(f"WEBHOOK - Successfully processed update: {update.update_id}")
                
                return web.Response(text="OK")
            except Exception as e:
                logger.error(f"WEBHOOK - Error processing webhook: {e}", exc_info=True)
                return web.Response(text="ERROR", status=500)

        async def handle_get(request):
            return web.Response(text="Task Management Webhook працює")

        async def handle_health(request):
            return web.Response(text="OK")

        app.router.add_post('/webhook', handle_post)
        app.router.add_get('/webhook', handle_get)
        app.router.add_get('/health', handle_health)
        app.router.add_get('/', handle_health)  # For UptimeRobot

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        webhook_url = f"{WEBHOOK_URL}/webhook"

        try:
            await self.application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Deleted existing webhook")
            
            await asyncio.sleep(2)
            
            result = await self.application.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                max_connections=40,
                allowed_updates=["message", "callback_query"]
            )
            logger.info(f"Webhook встановлено: {webhook_url}, result: {result}")
            
            webhook_info = await self.application.bot.get_webhook_info()
            logger.info(f"Webhook verification: {webhook_info}")
            
        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
            raise
        
        logger.info("Task Management Bot запущено на webhook")
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Bot stopped")
        finally:
            await self.application.stop()
            await self.application.shutdown()

async def main():
    bot = TelegramTaskBot()
    await bot.run_webhook()

if __name__ == '__main__':
    asyncio.run(main())
