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
    msg = messages[0]
    
    print("Clicking AKD...")
    try:
        await msg.click(text="?? AKD")
        print("Clicked AKD by text successfully")
    except Exception as e:
        print("Failed to click AKD by text:", e)
        
    await asyncio.sleep(2)
    messages = await client.get_messages('@hisseyorumbot', limit=1)
    
    found_url = None
    if messages[0].reply_markup:
        for row in messages[0].reply_markup.rows:
            for button in row.buttons:
                if hasattr(button, 'url'):
                    found_url = button.url
                    print("Found URL after AKD click:", button.url)
                    break

    await client.send_message('@hisseyorumbot', 'BIMAS')
    await asyncio.sleep(2)
    
    messages = await client.get_messages('@hisseyorumbot', limit=1)
    msg = messages[0]
    
    print("Clicking Takas...")
    try:
        await msg.click(text="?? Takas")
        print("Clicked Takas by text successfully")
    except Exception as e:
        print("Failed to click Takas by text:", e)
        
    await asyncio.sleep(2)
    messages = await client.get_messages('@hisseyorumbot', limit=1)
    
    found_url = None
    if messages[0].reply_markup:
        for row in messages[0].reply_markup.rows:
            for button in row.buttons:
                if hasattr(button, 'url'):
                    found_url = button.url
                    print("Found URL after Takas click:", button.url)
                    break
                    
if __name__ == '__main__':
    asyncio.run(main())
