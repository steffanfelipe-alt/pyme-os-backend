from dotenv import load_dotenv
load_dotenv()

import os
import httpx

token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
NGROK_URL = os.environ.get("TELEGRAM_WEBHOOK_URL", "").rstrip("/")

if not token:
    print("ERROR: TELEGRAM_BOT_TOKEN no configurado en .env")
    exit(1)

if not NGROK_URL:
    print("ERROR: TELEGRAM_WEBHOOK_URL no configurado en .env")
    exit(1)

webhook_url = f"{NGROK_URL}/webhooks/telegram"
print(f"Registrando webhook: {webhook_url}")

r = httpx.post(
    f"https://api.telegram.org/bot{token}/setWebhook",
    json={"url": webhook_url}
)
print(r.json())
