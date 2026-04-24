"""Register the Telegram webhook with the bot API."""

import os
import sys
import urllib.request
import json

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN not set in .env")
    sys.exit(1)


def set_webhook(base_url):
    webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
    api_url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    payload = json.dumps({"url": webhook_url}).encode()
    req = urllib.request.Request(api_url, data=payload,
                                headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    print(f"Webhook set to: {webhook_url}")
    print(f"Response: {result}")


def get_webhook_info():
    api_url = f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
    resp = urllib.request.urlopen(api_url)
    result = json.loads(resp.read())
    print(f"Current webhook: {json.dumps(result, indent=2)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  uv run python setup_telegram.py set <base_url>")
        print("  uv run python setup_telegram.py info")
        print()
        print("Example:")
        print("  uv run python setup_telegram.py set https://excercise-tracker-8uer.onrender.com")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "set":
        if len(sys.argv) < 3:
            print("Error: provide the base URL")
            sys.exit(1)
        set_webhook(sys.argv[2])
    elif cmd == "info":
        get_webhook_info()
    else:
        print(f"Unknown command: {cmd}")
