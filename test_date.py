import asyncio
from telethon import TelegramClient
import env

async def test():
    client = TelegramClient('tahtaci_session', env.TELEGRAM_API_ID, env.TELEGRAM_API_HASH)
    await client.start()
    await client.send_message('@hisseyorumbot', '/akd THYAO 2026-07-16 2026-07-16')
    await asyncio.sleep(3)
    msgs = await client.get_messages('@hisseyorumbot', limit=2)
    for m in msgs:
        if m.reply_markup:
            for r in m.reply_markup.rows:
                for b in r.buttons:
                    if hasattr(b, 'url') and 'webapi.hisseplus.com' in b.url:
                        print('FOUND URL:', b.url)

asyncio.run(test())
