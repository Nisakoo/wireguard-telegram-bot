from dotenv import load_dotenv, find_dotenv
from bot.telegram_bot import main as run_bot


if __name__ == "__main__":
    load_dotenv(find_dotenv())
    run_bot()
