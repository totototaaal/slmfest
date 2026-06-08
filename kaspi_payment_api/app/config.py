import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
ALLOWED_IPS = [ip.strip() for ip in os.getenv("ALLOWED_IPS", "194.187.247.152,194.187.245.108,197.187.244.108").split(",") if ip.strip()]
ACCOUNT_REGEX = os.getenv("ACCOUNT_REGEX", r"^[A-Za-z0-9_.@#\-]{1,200}$")
HTTPS_HEADER = os.getenv("HTTPS_HEADER", "X-Forwarded-Proto")
HTTPS_VALUE = os.getenv("HTTPS_VALUE", "https")
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "true").strip().lower() in {"1", "true", "yes", "on"}
SQL_ECHO = os.getenv("SQL_ECHO", "false").strip().lower() in {"1", "true", "yes", "on"}
KASPI_ONLINE_URL = os.getenv("KASPI_ONLINE_URL", os.getenv("KASPI_FAST_PAYMENT_URL", "https://kaspi.kz/online"))
KASPI_FAST_PAYMENT_URL = KASPI_ONLINE_URL
KASPI_SERVICE_ID = os.getenv("KASPI_SERVICE_ID", "").strip()
KASPI_RETURN_URL = os.getenv("KASPI_RETURN_URL", "https://slmfest.kz/payment-success")
KASPI_REFERER_HOST = os.getenv("KASPI_REFERER_HOST", "slmfest.kz")
KASPI_REQUEST_TIMEOUT = float(os.getenv("KASPI_REQUEST_TIMEOUT", "15"))
