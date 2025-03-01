import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

BSCSCAN_API_KEY = os.getenv("BSCSCAN_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEB3_PROVIDER_URL = os.getenv("WEB3_PROVIDER_URL")
