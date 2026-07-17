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
    
    with open("bot_response.txt", "w", encoding="utf-8") as f:
        f.write("Test mesaji EREGL gonderiliyor...\n")
        
        messages = await client.get_messages('@hisseyorumbot', limit=2)
        for msg in messages:
            f.write(f"[{msg.date}] Gonderen: {msg.sender_id} Mesaj: {msg.text}\n")
            if msg.reply_markup:
                f.write(f"Markup var: {msg.reply_markup}\n")

if __name__ == "__main__":
    asyncio.run(main())
