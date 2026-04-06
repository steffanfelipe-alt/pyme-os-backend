from dotenv import load_dotenv
load_dotenv()

import os
import httpx

token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Limpiar updates pendientes
r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates?offset=-1")
print("Updates pendientes limpiados:", r.json())

# Verificar estado del webhook
r2 = httpx.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
info = r2.json()["result"]
print("Webhook URL:", info.get("url"))
print("Pending updates:", info.get("pending_update_count"))
print("Last error:", info.get("last_error_message", "ninguno"))
