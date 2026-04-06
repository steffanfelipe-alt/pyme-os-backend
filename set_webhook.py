from dotenv import load_dotenv
load_dotenv()

import os
import httpx

token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Cambiá esta URL por la que aparece en http://localhost:4040
NGROK_URL = "https://neonatal-radioactively-ewa.ngrok-free.dev"

webhook_url = f"{NGROK_URL}/webhooks/telegram"

r = httpx.post(
    f"https://api.telegram.org/bot{token}/setWebhook",
    json={"url": webhook_url}
)
print(r.json())
