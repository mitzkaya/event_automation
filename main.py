from fastapi import FastAPI
from pydantic import BaseModel
from telethon import TelegramClient
from datetime import datetime, timedelta, timezone
import asyncio
import threading

from my_config import api_id, api_hash, tnumber

app = FastAPI()

client = TelegramClient('anon', api_id, api_hash)

# отдельный loop для Telethon
telethon_loop = asyncio.new_event_loop()


@app.on_event("startup")
async def startup_event():
    def start_telethon():
        asyncio.set_event_loop(telethon_loop)

        async def init():
            await client.connect()

            if not await client.is_user_authorized():
                await client.send_code_request(tnumber)
                code = input("Enter Telegram code: ")
                await client.sign_in(tnumber, code)

        telethon_loop.run_until_complete(init())
        telethon_loop.run_forever()

    threading.Thread(target=start_telethon, daemon=True).start()


class RequestData(BaseModel):
    channels: list[str]


async def parse_channel(CHANNEL):
    posts = []
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    try:
        async for message in client.iter_messages(CHANNEL, limit=500):
            # ⛔️ если сообщение старше недели — прекращаем цикл
            if message.date < week_ago:
                break

            # пропускаем посты без текста
            if not message.text or not message.text.strip():
                continue

            post_url = f"https://t.me/{CHANNEL}/{message.id}"

            images = []
            if message.photo or message.grouped_id:
                images.append(post_url)

            posts.append({
                "channel": CHANNEL,
                "post_url": post_url,
                "date": message.date.isoformat(),
                "text": message.text,
                "images": images
            })

    except Exception as e:
        print(f"Error parsing channel {CHANNEL}: {e}")

    return posts


async def parse_all_channels(channelsList):
    tasks = [parse_channel(CH) for CH in channelsList]
    results = await asyncio.gather(*tasks)

    # объединяем списки
    all_posts = [post for sublist in results for post in sublist]
    return all_posts


@app.post("/parse")
async def parse(data: RequestData):
    future = asyncio.run_coroutine_threadsafe(
        parse_all_channels(data.channels),
        telethon_loop
    )

    try:
        posts = future.result(timeout=60)  # ⏱️ таймаут 60 сек
    except Exception as e:
        return {"error": str(e)}

    return {"posts": posts}