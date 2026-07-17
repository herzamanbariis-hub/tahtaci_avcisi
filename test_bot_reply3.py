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
    
    with open("bot_response3.txt", "w", encoding="utf-8") as f:
        messages_after = await client.get_messages('@hisseyorumbot', limit=2)
        for msg2 in messages_after:
            f.write(f"\n[{msg2.date}] Gonderen: {msg2.sender_id} Mesaj: {msg2.text}\n")
            if msg2.reply_markup:
                f.write(f"Markup: {msg2.reply_markup}\n")
            if msg2.photo:
                f.write(f"Fotograf var!\n")
            if msg2.document:
                f.write(f"Dokuman var!\n")

if __name__ == "__main__":
    asyncio.run(main())
