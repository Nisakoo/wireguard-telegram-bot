import os
import csv
import io
import logging
from datetime import datetime
from typing import Dict
from croniter import croniter
import cairosvg

from telegram import Update, Document
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from bot.messages import Messages
import bot.decorators as decorators
from wireguard import WireguardAPI

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.admin_id = os.environ.get("ADMIN_TELEGRAM_ID")
        self.users_config: Dict[str, Dict] = {}
        self.user_chat_ids: Dict[str, int] = {}  # Сохраняем chat_id пользователей
        self.messages = Messages()

        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        if not self.admin_id:
            raise ValueError("ADMIN_TELEGRAM_ID environment variable is required")

        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()

    def _setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        # Команды для всех пользователей
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("conf", self.conf_command))
        self.application.add_handler(CommandHandler("qrcode", self.qrcode_command))

        # Команды только для админа
        self.application.add_handler(CommandHandler("broadcast", self.broadcast_command))
        self.application.add_handler(CommandHandler("config", self.show_config_command))

        # Обработчик загрузки CSV файла
        self.application.add_handler(MessageHandler(filters.Document.MimeType("text/csv"), self.handle_csv_upload))

    @decorators.white_list
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        username = update.effective_user.username

        # Сохраняем chat_id пользователя для рассылок
        user_tag = f"@{username}"
        self.user_chat_ids[user_tag] = update.effective_chat.id
        logger.info(f"Saved chat_id {update.effective_chat.id} for user {user_tag}")

        await update.message.reply_text(self.messages["start_message"])

    @decorators.white_list
    async def conf_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /conf - получение конфигурации Wireguard"""
        username = update.effective_user.username

        # Сохраняем chat_id пользователя
        user_tag = f"@{username}"
        self.user_chat_ids[user_tag] = update.effective_chat.id

        if user_tag not in self.users_config:
            await update.message.reply_text(self.messages["configuration_not_found"])
            return

        wireguard_id = self.users_config[user_tag]["wireguard_id"]

        try:
            with WireguardAPI() as api:
                config = api.get_configuration(wireguard_id)

                # Отправляем конфигурацию как файл
                config_file = io.BytesIO(config.encode('utf-8'))
                config_file.name = f"{username}.conf"

                await update.message.reply_document(
                    document=config_file,
                    caption=self.messages["configuration_found"]
                )

        except Exception as e:
            logger.error(f"Error getting configuration for {username}: {e}")
            await update.message.reply_text(self.messages["configuration_getting_error"])

    @decorators.white_list
    async def qrcode_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /qrcode - получение QR-кода"""
        username = update.effective_user.username

        # Сохраняем chat_id пользователя
        user_tag = f"@{username}"
        self.user_chat_ids[user_tag] = update.effective_chat.id

        if user_tag not in self.users_config:
            await update.message.reply_text(self.messages["configuration_not_found"])
            return

        wireguard_id = self.users_config[user_tag]["wireguard_id"]

        try:
            with WireguardAPI() as api:
                qr_svg = api.get_qrcode(wireguard_id)

                # Конвертируем SVG в PNG
                png_data = cairosvg.svg2png(bytestring=qr_svg.encode('utf-8'))
                png_buffer = io.BytesIO(png_data)
                png_buffer.seek(0)

                # Отправляем QR-код как PNG изображение
                await update.message.reply_photo(
                    photo=png_buffer,
                    caption=self.messages["qrcode_found"]
                )

        except Exception as e:
            logger.error(f"Error getting QR code for {username}: {e}")
            await update.message.reply_text(self.messages["qrcode_getting_error"])

    @decorators.admin_command
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /broadcast - массовая рассылка (только для админа)"""
        if not context.args:
            await update.message.reply_text(self.messages["broadcast_command_message"])
            return

        message = " ".join(context.args)
        await self._send_broadcast(update, message)

    @decorators.admin_command
    async def show_config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать текущую конфигурацию пользователей (только для админа)"""
        if not self.users_config:
            await update.message.reply_text(self.messages["users_configuration_empty"])
            return

        config_text = self.messages["current_users_configuration"]
        config_text += "\n\n"
        config_text += self._get_user_configuration()

        await update.message.reply_text(config_text)

    @decorators.admin_command
    async def handle_csv_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик загрузки CSV файла (только для админа)"""
        document: Document = update.message.document

        try:
            # Скачиваем файл
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()

            # Парсим CSV
            csv_content = file_content.decode('utf-8')
            csv_reader = csv.DictReader(io.StringIO(csv_content))

            new_config = {}
            for row in csv_reader:
                telegram_id = row['telegram_id'].strip()
                wireguard_id = row['wireguard_id'].strip()
                expire_day = row['expire_day'].strip()

                # Валидация cron выражения
                try:
                    croniter(expire_day)
                except Exception:
                    await update.message.reply_text(
                        self.messages["cron_format_error"].format(
                            telegram_id=telegram_id, expire_day=expire_day
                        )
                    )
                    return

                new_config[telegram_id] = {
                    'wireguard_id': wireguard_id,
                    'expire_day': expire_day
                }

            # Обновляем конфигурацию
            self.users_config = new_config

            # Отправляем подтверждение с новой конфигурацией
            config_text = self.messages["configuration_successfully_updated"]
            config_text += "\n\n"
            config_text += self.messages["users_uploaded_template"].format(users_count=len(self.users_config))
            config_text += "\n"
            config_text += self._get_user_configuration()

            await update.message.reply_text(config_text)

        except Exception as e:
            logger.error(f"Error processing CSV file: {e}")
            await update.message.reply_text(
                self.messages["configuration_csv_validate_error"].format(
                    error=str(e)
                )
            )

    async def _send_broadcast(self, update: Update, message: str):
        """Отправка сообщения всем пользователям"""
        if not self.users_config:
            await update.message.reply_text(self.messages["users_configuration_empty"])
            return

        sent_count = 0
        failed_count = 0

        for telegram_id in self.users_config.keys():
            try:
                # Проверяем, есть ли сохраненный chat_id для пользователя
                if telegram_id in self.user_chat_ids:
                    chat_id = self.user_chat_ids[telegram_id]
                    await update.get_bot().send_message(chat_id=chat_id, text=message)
                    logger.info(f"Broadcast message sent to {telegram_id}")
                    sent_count += 1
                else:
                    logger.warning(f"No chat_id found for user {telegram_id}")
                    failed_count += 1

            except Exception as e:
                logger.error(f"Failed to send message to {telegram_id}: {e}")
                failed_count += 1

        result_message = self.messages["broadcast_completed"]
        result_message += "\n"
        result_message += self.messages["broadcast_messages_sent"].format(sent_count=sent_count)
        result_message += "\n"
        result_message += self.messages["broadcast_messages_sent_error"].format(failed_count=failed_count)

        await update.message.reply_text(result_message)

    def _get_user_configuration(self) -> str:
        text = str()
        for telegram_id, user_data in self.users_config.items():
            text += self.messages["telegram_id_template"].format(telegram_id=telegram_id)
            text += "\n"
            text += self.messages["wireguard_id_template"].format(wireguard_id=user_data["wireguard_id"])
            text += "\n"
            text += self.messages["expire_day_template"].format(expire_day=user_data["expire_day"])
            text += "\n\n"

        return text

    async def check_payment_reminders(self, context: ContextTypes.DEFAULT_TYPE):
        """Проверка напоминаний об оплате (вызывается по расписанию)"""
        current_time = datetime.now()

        for telegram_id, user_data in self.users_config.items():
            expire_cron = user_data['expire_day']

            try:
                cron = croniter(expire_cron, current_time)
                next_payment = cron.get_next(datetime)

                # Проверяем, если следующий платеж сегодня
                if next_payment.date() == current_time.date():
                    # Отправляем напоминание пользователю
                    user_message = self.messages["reminder_message"]

                    if telegram_id in self.user_chat_ids:
                        try:
                            user_chat_id = self.user_chat_ids[telegram_id]
                            await context.bot.send_message(chat_id=user_chat_id, text=user_message)
                            logger.info(f"Payment reminder sent to user {telegram_id}")
                        except Exception as e:
                            logger.error(f"Failed to send payment reminder to user {telegram_id}: {e}")

                    # Отправляем уведомление админу
                    admin_message = self.messages["admin_remainder_message"].format(
                        telegram_id=telegram_id
                    )

                    try:
                        await context.bot.send_message(chat_id=self.admin_id, text=admin_message)
                        logger.info(f"Payment reminder notification sent to admin for user {telegram_id}")
                    except Exception as e:
                        logger.error(f"Failed to send payment reminder to admin: {e}")

            except Exception as e:
                logger.error(f"Error processing payment reminder for {telegram_id}: {e}")

    def run(self):
        """Запуск бота"""
        logger.info("Starting Telegram bot...")

        # Добавляем задачу проверки платежей (каждый час)
        job_queue = self.application.job_queue
        job_queue.run_repeating(self.check_payment_reminders, interval=3600, first=60)

        self.application.run_polling()


def main():
    """Главная функция для запуска бота"""
    try:
        bot = TelegramBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    main()
