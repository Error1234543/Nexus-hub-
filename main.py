import os
import asyncio
import aiohttp
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
OWNER_ID = int(os.getenv("OWNER_ID"))
MONGO_URI = os.getenv("MONGO_URI")
VPLINK_API = os.getenv("VPLINK_API")
BASE_URL = os.getenv("BASE_URL", "https://google.com")

app = Client(
    "TempAccessBot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo.temp_access_bot
users = db.users

scheduler = AsyncIOScheduler()

CHANNELS = [
    {
        "name": "NEET FULL BATCH 1 GUJARATI",
        "id": -1002703950742
    },
    {
        "name": "NEET FULL BATCH 2 GUJARATI",
        "id": -1003870505207
    }
]


async def generate_shortlink(user_id):
    url = f"{BASE_URL}/verify?user_id={user_id}"

    api = f"https://vplink.in/api?api={VPLINK_API}&url={url}"

    async with aiohttp.ClientSession() as session:
        async with session.get(api) as resp:
            data = await resp.json()

            if data.get("status") == "success":
                return data.get("shortenedUrl")

    return None


@app.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔐 Generate Verification Link",
                    callback_data="generate_link"
                )
            ]
        ]
    )

    text = (
        "🔥 Welcome To Temporary Access Bot\n\n"
        "✅ Verify using shortlink\n"
        "✅ Get temporary channel access\n"
        "✅ Access valid for 12 hours only\n"
        "✅ Rejoin anytime by verifying again\n\n"
        "👇 Click below to generate link"
    )

    await message.reply_text(text, reply_markup=keyboard)


@app.on_callback_query(filters.regex("generate_link"))
async def generate_link_callback(client, callback_query):
    user_id = callback_query.from_user.id

    shortlink = await generate_shortlink(user_id)

    if not shortlink:
        return await callback_query.message.reply_text(
            "❌ Failed to generate verification link"
        )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Verify Now", url=shortlink)],
            [
                InlineKeyboardButton(
                    "🔄 I Have Verified",
                    callback_data="verified"
                )
            ]
        ]
    )

    await callback_query.message.reply_text(
        "🔐 Complete verification then click below.",
        reply_markup=keyboard
    )


@app.on_callback_query(filters.regex("verified"))
async def verified_callback(client, callback_query):
    user = callback_query.from_user
    user_id = user.id

    expire_time = datetime.utcnow() + timedelta(minutes=1)

    text = "✅ Verification Successful\n\n📢 Temporary Access Links:\n\n"

    for channel in CHANNELS:
        invite = await client.create_chat_invite_link(
            chat_id=channel["id"],
            expire_date=expire_time,
            member_limit=1
        )

        text += f"🔹 {channel['name']}\n{invite.invite_link}\n\n"

    text += "⏰ Links expire in 1 minute\n⚠️ Access valid for 12 hours only"

    expiry_12h = datetime.utcnow() + timedelta(hours=12)

    await users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "expires_at": expiry_12h,
                "verified": True
            }
        },
        upsert=True
    )

    profile_link = f"tg://user?id={user_id}"

    owner_text = (
        f"🚨 New Access Request\n\n"
        f"👤 User: {user.mention}\n"
        f"🆔 ID: {user_id}\n\n"
        f"🔗 {profile_link}"
    )

    await client.send_message(OWNER_ID, owner_text)

    await callback_query.message.reply_text(text)


async def remove_expired_users():
    now = datetime.utcnow()

    expired_users = users.find({
        "expires_at": {"$lte": now},
        "verified": True
    })

    async for user in expired_users:
        user_id = user["user_id"]

        for channel in CHANNELS:
            try:
                await app.ban_chat_member(channel["id"], user_id)
                await asyncio.sleep(1)
                await app.unban_chat_member(channel["id"], user_id)
            except Exception as e:
                print(e)

        try:
            await app.send_message(
                user_id,
                "⏰ Your access has expired\n\n🔄 Verify again to rejoin channels"
            )
        except:
            pass

        await users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "verified": False
                }
            }
        )


scheduler.add_job(remove_expired_users, "interval", minutes=5)
scheduler.start()


print("Bot Started...")
app.run()
