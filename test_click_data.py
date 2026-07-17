import asyncio, os
from telethon import TelegramClient
from dotenv import load_dotenv

load_dotenv()
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

async def main():
    client = TelegramClient('tahtaci_session', API_ID, API_HASH)
    await client.start()
    
    await client.send_message('@hisseyorumbot', 'BIMAS')
    await asyncio.sleep(2)
    messages = await client.get_messages('@hisseyorumbot', limit=1)
    
    print("Clicking AKD with data='BIMAS:akd'...")
    try:
        await messages[0].click(data=b'BIMAS:akd')
        print("Click command sent.")
    except Exception as e:
        print("Exception:", e)
        
    await asyncio.sleep(2)
    messages = await client.get_messages('@hisseyorumbot', limit=2)
    for msg in messages:
        if msg.reply_markup:
            for row in msg.reply_markup.rows:
                for button in row.buttons:
                    if hasattr(button, 'url'):
                        print("URL:", button.url)
                        
if __name__ == '__main__':
    asyncio.run(main())
