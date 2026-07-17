import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName

load_dotenv()
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

async def main():
    client = TelegramClient('tahtaci_session', API_ID, API_HASH)
    await client.start()
    
    print("AppWebView isleniyor...")
    try:
        # Mini App'i app short name ile cagir
        # startapp genelde bot'un kendi adidir.
        result = await client(RequestAppWebViewRequest(
            peer='@hisseyorumbot',
            app=InputBotAppShortName(bot_id=await client.get_input_entity('@hisseyorumbot'), short_name='app'),
            platform='android',
            start_param=''
        ))
        print("GERCEK WEB SITESI ADRESI:")
        print(result.url)
    except Exception as e:
        print(f"Hata olustu: {e}")
        try:
            result = await client(RequestAppWebViewRequest(
                peer='@hisseyorumbot',
                app=InputBotAppShortName(bot_id=await client.get_input_entity('@hisseyorumbot'), short_name='startapp'),
                platform='android',
                start_param=''
            ))
            print("GERCEK WEB SITESI ADRESI (startapp ile):")
            print(result.url)
        except Exception as e2:
            print(f"Hata 2: {e2}")

if __name__ == "__main__":
    asyncio.run(main())
