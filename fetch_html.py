import asyncio
import os
import urllib.request
from dotenv import load_dotenv
from telethon import TelegramClient

import env
API_ID = env.TELEGRAM_API_ID
API_HASH = env.TELEGRAM_API_HASH

async def main():
    client = TelegramClient('tahtaci_session', API_ID, API_HASH)
    await client.start()
    
    print("Sorgu basladi...")
    await client.send_message('@hisseyorumbot', 'THYAO')
    await asyncio.sleep(2)
    
    messages = await client.get_messages('@hisseyorumbot', limit=3)
    for msg in messages:
        if msg.reply_markup:
            await msg.click(data=b'THYAO:akd')
            print("AKD Butonuna tiklandi, yanit bekleniyor...")
            
            await asyncio.sleep(2)
            messages_after = await client.get_messages('@hisseyorumbot', limit=2)
            for msg2 in messages_after:
                if msg2.reply_markup:
                    for row in msg2.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'url') and 'webapi.hisseplus.com' in button.url:
                                url = button.url
                                print(f"Bulunan URL: {url}")
                                
                                # Hemen URL'yi indir
                                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                                res = urllib.request.urlopen(req)
                                html = res.read().decode('utf-8')
                                
                                with open("akd_raw.html", "w", encoding="utf-8") as f:
                                    f.write(html)
                                print("HTML basariyla kaydedildi!")
                                return

if __name__ == "__main__":
    asyncio.run(main())
