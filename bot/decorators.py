from telegram import Update
from telegram.ext import ContextTypes


def white_list(func):
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        username = update.effective_user.username

        if (not username) or (f"@{username}" not in self.users_config):
            await update.message.reply_text(self.messages["cannot_use_bot"])
            return

        return await func(self, update, context)
    return wrapper

def admin_command(func):
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)

        if user_id != self.admin_id:
            await update.message.reply_text(self.messages["permissions_denied"])
            return

        return await func(self, update, context)
    return wrapper
