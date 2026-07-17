import pandas as pd
import urllib.request
import asyncio, os
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

async def main():
    client = TelegramClient('tahtaci_session', API_ID, API_HASH)
    await client.start()
    
    await client.send_message('@hisseyorumbot', 'THYAO')
    await asyncio.sleep(2.5)
    
    messages = await client.get_messages('@hisseyorumbot', limit=3)
    for msg in messages:
        if not msg.reply_markup: continue
        try:
            await msg.click(data=b'THYAO:takas')
            print('Clicked Takas')
            await asyncio.sleep(3.0)
            
            msgs_after = await client.get_messages('@hisseyorumbot', limit=2)
            for m2 in msgs_after:
                if m2.reply_markup:
                    for row in m2.reply_markup.rows:
                        for button in row.buttons:
                            if hasattr(button, 'url') and 'webapi.hisseplus.com/ui/takas' in button.url:
                                print('URL:', button.url)
                                req = urllib.request.Request(button.url, headers={'User-Agent':'Mozilla/5.0'})
                                res = urllib.request.urlopen(req)
                                html = res.read().decode('utf-8')
                                
                                dfs = pd.read_html(html)
                                if dfs:
                                    print(dfs[0].head())
                                return
        except Exception as e:
            print(e)

if __name__ == '__main__':
    asyncio.run(main())
