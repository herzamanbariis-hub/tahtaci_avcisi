import asyncio, os, urllib.request
from telethon import TelegramClient
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

async def main():
    client = TelegramClient('tahtaci_session', API_ID, API_HASH)
    await client.start()
    
    await client.send_message('@hisseyorumbot', 'EREGL')
    await asyncio.sleep(2.5)
    
    messages = await client.get_messages('@hisseyorumbot', limit=2)
    for msg in messages:
        if not msg.reply_markup: continue
        try:
            await msg.click(data=b'EREGL:takas')
            await asyncio.sleep(2.5)
            msgs2 = await client.get_messages('@hisseyorumbot', limit=2)
            for m in msgs2:
                if m.reply_markup:
                    for r in m.reply_markup.rows:
                        for b in r.buttons:
                            if hasattr(b, 'url') and 'ui/takas' in b.url:
                                url = b.url.replace('ilk=2026-07-10', 'ilk=2026-06-10')
                                print('TAMPERED URL:', url)
                                try:
                                    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
                                    res = urllib.request.urlopen(req)
                                    html = res.read().decode('utf-8')
                                    soup = BeautifulSoup(html, 'html.parser')
                                    table = soup.find('table', id='takasveri')
                                    if table:
                                        heads = [th.text.strip() for th in table.find_all('th')]
                                        print('Columns:', heads)
                                        row1 = [td.text.strip() for td in table.find('tbody').find_all('tr')[0].find_all('td')]
                                        print('Row1:', row1)
                                except Exception as e:
                                    print('Failed:', e)
                                return
        except Exception as e:
            print(e)

if __name__ == '__main__':
    asyncio.run(main())
