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
        if msg.reply_markup:
            for row in msg.reply_markup.rows:
                for button in row.buttons:
                    text = getattr(button, 'text', '')
                    data = getattr(button, 'data', b'').decode('utf-8', errors='ignore')
                    url = getattr(button, 'url', '')
                    print(f'Button: {text} | Data: {data} | URL: {url}')

if __name__ == '__main__':
    asyncio.run(main())
