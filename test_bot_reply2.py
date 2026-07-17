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
    
    with open("bot_response2.txt", "w", encoding="utf-8") as f:
        f.write("Callback query b'EREGL:akd' gonderiliyor...\n")
        
        # Odaya gidip son mesaji bul ve butonuna tikla
        messages = await client.get_messages('@hisseyorumbot', limit=3)
        for msg in messages:
            if msg.reply_markup:
                # EREGL:akd butonunu bul ve tikla
                await msg.click(data=b'EREGL:akd')
                f.write("Butona tiklandi!\n")
                
                # 3 saniye bekle
                await asyncio.sleep(3)
                
                # Yeni mesaji (veya degisen mesaji) oku
                messages_after = await client.get_messages('@hisseyorumbot', limit=1)
                for msg2 in messages_after:
                    f.write(f"\n[{msg2.date}] Gonderen: {msg2.sender_id} Mesaj: {msg2.text}\n")
                break

if __name__ == "__main__":
    asyncio.run(main())
