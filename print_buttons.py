import asyncio, os, json
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
    results = []
    for msg in messages:
        if not msg.reply_markup: continue
        for row in msg.reply_markup.rows:
            for button in row.buttons:
                text = getattr(button, 'text', '')
                try:
                    data = getattr(button, 'data', b'').decode('utf-8')
                except:
                    data = str(getattr(button, 'data', ''))
                results.append({'text': text, 'data': data})
    
    with open('buttons.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    asyncio.run(main())
