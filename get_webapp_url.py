import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

async def main():
    client = TelegramClient('tahtaci_session', API_ID, API_HASH)
    await client.start()
    
    print("Son mesajlar taranarak Mini App (Web App) linki bulmaya calisiliyor...")
    
    # hisseyorumbot'taki son 20 mesaja bak
    messages = await client.get_messages('@hisseyorumbot', limit=20)
    found = False
    
    for msg in messages:
        if msg.reply_markup:
            for row in msg.reply_markup.rows:
                for button in row.buttons:
                    if hasattr(button, 'url') and button.url:
                        print(f"URL Bulundu: {button.url}")
                        found = True
                    # web_app ozelligi varsa
                    if hasattr(button, 'web_app') and button.web_app:
                        print(f"WEB_APP URL Bulundu: {button.web_app.url}")
                        found = True
                        
    if not found:
        print("Mini app linki bulunamadi. Botun menusu farkli bir yapida olabilir.")

if __name__ == "__main__":
    asyncio.run(main())
