import os
import asyncio
import aiohttp
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ==================================================
# FLASK WEB SERVER (KOYEB HEALTH CHECK FIX)
# ==================================================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Bot Running Successfully!"


@web_app.route("/health")
def health():
    return "OK", 200


def run_web():
    port = int(os.environ.get("PORT", 8000))
    web_app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()


# ==================================================
# ENV VARIABLES
# ==================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

OWNER_ID = int(os.getenv("OWNER_ID"))

MONGO_URI = os.getenv("MONGO_URI")

VPLINK_API = os.getenv("VPLINK_API")

BASE_URL = os.getenv(
    "BASE_URL",
    "https://southern-dorotea-error1234543-b32c9d69.koyeb.app"
)

# ==================================================
# CHANNELS
# ==================================================

CHANNELS = [
    {
        "name": "NEET MAIN",
        "id": -1002432150473
    },
    {
        "name": "VIP CHANNEL",
        "id": -1002246684537
    }
]

# ==================================================
# START FLASK
# ==================================================

keep_alive()

# ==================================================
# BOT CLIENT
# ==================================================

app = Client(
    "TempAccessBot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# ==================================================
# DATABASE
# ==================================================

mongo = AsyncIOMotorClient(MONGO_URI)

db = mongo.temp_access_bot

users = db.users

# ==================================================
# SCHEDULER
# ==================================================

scheduler = AsyncIOScheduler()

# ==================================================
# GENERATE SHORTLINK
# ==================================================


async def generate_shortlink(user_id):

    verify_url = f"{BASE_URL}/verify?user_id={user_id}"

    api_url = (
        f"https://vplink.in/api"
        f"?api={VPLINK_API}"
        f"&url={verify_url}"
    )

    async with aiohttp.ClientSession() as session:

        async with session.get(api_url) as response:

            data = await response.json()

            print(data)

            if data.get("status") == "success":
                return data.get("shortenedUrl")

    return None

# ==================================================
# START COMMAND
# ==================================================


@app.on_message(filters.command("start"))
async def start_command(client, message):

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
        "✅ Access valid for 12 hours\n"
        "✅ Rejoin anytime after expiry\n\n"
        "👇 Click below to continue"
    )

    await message.reply_text(
        text,
        reply_markup=keyboard
    )

# ==================================================
# GENERATE LINK
# ==================================================


@app.on_callback_query(filters.regex("generate_link"))
async def generate_link(client, callback_query):

    user_id = callback_query.from_user.id

    shortlink = await generate_shortlink(user_id)

    if not shortlink:

        return await callback_query.message.reply_text(
            "❌ Failed to generate verification link"
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Verify Now",
                    url=shortlink
                )
            ],
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

# ==================================================
# VERIFIED USER
# ==================================================


@app.on_callback_query(filters.regex("verified"))
async def verified_user(client, callback_query):

    user = callback_query.from_user

    user_id = user.id

    invite_expire = datetime.utcnow() + timedelta(minutes=1)

    final_text = (
        "✅ Verification Successful\n\n"
        "📢 Temporary Access Links:\n\n"
    )

    for channel in CHANNELS:

        try:

            invite = await client.create_chat_invite_link(
                chat_id=channel["id"],
                expire_date=invite_expire,
                member_limit=1
            )

            final_text += (
                f"🔹 {channel['name']}\n"
                f"{invite.invite_link}\n\n"
            )

        except Exception as e:

            print(e)

            final_text += (
                f"❌ Failed to generate for "
                f"{channel['name']}\n\n"
            )

    final_text += (
        "⏰ Links expire in 1 minute\n"
        "⚠️ Access valid only for 12 hours"
    )

    expiry_12h = datetime.utcnow() + timedelta(hours=12)

    await users.update_one(
        {
            "user_id": user_id
        },
        {
            "$set": {
                "user_id": user_id,
                "verified": True,
                "expires_at": expiry_12h
            }
        },
        upsert=True
    )

    # OWNER NOTIFICATION

    owner_text = (
        f"🚨 New Access Request\n\n"
        f"👤 User: {user.mention}\n"
        f"🆔 ID: {user_id}\n\n"
        f"🔗 tg://user?id={user_id}"
    )

    try:

        await client.send_message(
            OWNER_ID,
            owner_text
        )

    except:
        pass

    await callback_query.message.reply_text(
        final_text
    )

# ==================================================
# REMOVE EXPIRED USERS
# ==================================================


async def remove_expired_users():

    now = datetime.utcnow()

    expired_users = users.find(
        {
            "expires_at": {
                "$lte": now
            },
            "verified": True
        }
    )

    async for user in expired_users:

        user_id = user["user_id"]

        for channel in CHANNELS:

            try:

                # BAN USER

                await app.ban_chat_member(
                    channel["id"],
                    user_id
                )

                await asyncio.sleep(1)

                # UNBAN USER

                await app.unban_chat_member(
                    channel["id"],
                    user_id
                )

            except Exception as e:
                print(e)

        # SEND MESSAGE

        try:

            await app.send_message(
                user_id,
                (
                    "⏰ Your access has expired\n\n"
                    "🔄 Generate a new verification "
                    "link to join again."
                )
            )

        except:
            pass

        # UPDATE DATABASE

        await users.update_one(
            {
                "user_id": user_id
            },
            {
                "$set": {
                    "verified": False
                }
            }
        )

# ==================================================
# STARTUP EVENT
# ==================================================


@app.on_message(filters.command("ping"))
async def ping(_, message):
    await message.reply_text("🏓 Pong!")

# ==================================================
# MAIN START
# ==================================================


async def main():

    scheduler.add_job(
        remove_expired_users,
        "interval",
        minutes=5
    )

    scheduler.start()

    print("Bot Started Successfully!")

    await app.start()

    print("Pyrogram Client Started!")

    await asyncio.Event().wait()

# ==================================================
# RUN BOT
# ==================================================

if __name__ == "__main__":

    loop = asyncio.get_event_loop()

    loop.run_until_complete(main())