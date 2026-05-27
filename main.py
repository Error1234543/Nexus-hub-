import os
import asyncio
import random
import string
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
# FLASK SERVER
# ==================================================

web = Flask(__name__)

@web.route("/")
def home():
    return "Bot Running Successfully!"

@web.route("/health")
def health():
    return "OK", 200

def run_web():

    port = int(os.environ.get("PORT", 8000))

    web.run(
        host="0.0.0.0",
        port=port
    )

Thread(target=run_web).start()

# ==================================================
# ENV
# ==================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

API_ID = int(os.getenv("API_ID"))

API_HASH = os.getenv("API_HASH")

OWNER_ID = int(os.getenv("OWNER_ID"))

MONGO_URI = os.getenv("MONGO_URI")

# ==================================================
# BOT USERNAME
# ==================================================

BOT_USERNAME = "Jetxcntbot"

# ==================================================
# CHANNELS
# ==================================================

CHANNELS = [
    {
        "name": "Main Channel",
        "id": -1002432150473
    },

    {
        "name": "VIP Channel",
        "id": -1002246684537
    }
]

# ==================================================
# BOT CLIENT
# ==================================================

app = Client(
    "AccessBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==================================================
# DATABASE
# ==================================================

mongo = AsyncIOMotorClient(
    MONGO_URI,
    tls=True,
    tlsAllowInvalidCertificates=True
)

db = mongo.access_bot

tokens = db.tokens

users = db.users

# ==================================================
# SCHEDULER
# ==================================================

scheduler = AsyncIOScheduler()

# ==================================================
# TOKEN GENERATOR
# ==================================================

def generate_token(length=12):

    return ''.join(
        random.choices(
            string.ascii_letters + string.digits,
            k=length
        )
    )

# ==================================================
# CREATE LINK
# ==================================================

async def generate_link(user_id):

    token = generate_token()

    await tokens.insert_one(
        {
            "user_id": user_id,
            "token": token,
            "used": False,
            "created_at": datetime.utcnow()
        }
    )

    deep_link = (
        f"https://t.me/"
        f"{BOT_USERNAME}"
        f"?start={token}"
    )

    return deep_link

# ==================================================
# START COMMAND
# ==================================================

@app.on_message(filters.command("start"))
async def start_command(client, message):

    data = message.text.split()

    user = message.from_user

    user_id = user.id

    # ==================================================
    # VERIFY TOKEN
    # ==================================================

    if len(data) > 1:

        token = data[1]

        token_data = await tokens.find_one(
            {
                "token": token
            }
        )

        if not token_data:

            return await message.reply_text(
                "❌ Invalid Token"
            )

        if token_data["used"]:

            return await message.reply_text(
                "❌ This Link Already Used"
            )

        if token_data["user_id"] != user_id:

            return await message.reply_text(
                "❌ This Link Belongs To Another User"
            )

        # EXPIRE CHECK

        created_time = token_data["created_at"]

        if (
            datetime.utcnow() - created_time
        ).total_seconds() > 300:

            return await message.reply_text(
                "❌ Verification Link Expired"
            )

        # MARK USED

        await tokens.update_one(
            {
                "token": token
            },
            {
                "$set": {
                    "used": True
                }
            }
        )

        # CREATE INVITE LINKS

        invite_expire = (
            datetime.utcnow()
            + timedelta(minutes=1)
        )

        text = (
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

                text += (
                    f"🔹 {channel['name']}\n"
                    f"{invite.invite_link}\n\n"
                )

            except Exception as e:

                print(e)

                text += (
                    f"❌ Failed For "
                    f"{channel['name']}\n\n"
                )

        text += (
            "⏰ Links Expire In 1 Minute\n"
            "⚠️ Access Valid For 12 Hours"
        )

        # SAVE USER

        expiry_time = (
            datetime.utcnow()
            + timedelta(hours=12)
        )

        await users.update_one(
            {
                "user_id": user_id
            },
            {
                "$set": {
                    "user_id": user_id,
                    "expires_at": expiry_time,
                    "verified": True
                }
            },
            upsert=True
        )

        # OWNER MESSAGE

        try:

            await client.send_message(
                OWNER_ID,
                (
                    f"🚨 New User Verified\n\n"
                    f"👤 {user.mention}\n"
                    f"🆔 {user_id}"
                )
            )

        except:
            pass

        return await message.reply_text(text)

    # ==================================================
    # NORMAL START
    # ==================================================

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔐 Generate Verification Link",
                    callback_data="generate"
                )
            ]
        ]
    )

    await message.reply_text(
        (
            "🔥 Welcome To Access Bot\n\n"
            "✅ Temporary Channel Access\n"
            "✅ Access Valid For 12 Hours\n"
            "✅ Rejoin Anytime\n\n"
            "👇 Click Below *"
        ),
        reply_markup=keyboard
    )

# ==================================================
# GENERATE BUTTON
# ==================================================

@app.on_callback_query(
    filters.regex("generate")
)
async def generate_callback(client, callback_query):

    user_id = callback_query.from_user.id

    await callback_query.answer(
        "⏳ Generating Link..."
    )

    try:

        link = await generate_link(user_id)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔗 VERIFY NOW",
                        url=link
                    )
                ]
            ]
        )

        await callback_query.message.reply_text(
            (
                "✅ Verification Link Generated\n\n"
                "⚠️ Valid For 5 Minutes"
            ),
            reply_markup=keyboard
        )

    except Exception as e:

        print(e)

        await callback_query.message.reply_text(
            f"❌ Error:\n{e}"
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

                # BAN

                await app.ban_chat_member(
                    channel["id"],
                    user_id
                )

                await asyncio.sleep(1)

                # UNBAN

                await app.unban_chat_member(
                    channel["id"],
                    user_id
                )

            except Exception as e:
                print(e)

        # MESSAGE USER

        try:

            await app.send_message(
                user_id,
                (
                    "⏰ Your Access Expired\n\n"
                    "🔄 Generate New Verification Link"
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
# PING
# ==================================================

@app.on_message(filters.command("ping"))
async def ping(_, message):

    await message.reply_text(
        "🏓 Pong!"
    )

# ==================================================
# STARTUP
# ==================================================

async def startup():

    scheduler.add_job(
        remove_expired_users,
        "interval",
        minutes=5
    )

    scheduler.start()

    print("Scheduler Started")

# ==================================================
# MAIN
# ==================================================

async def main():

    await startup()

    await app.start()

    print("Bot Started Successfully!")

    from pyrogram.idle import idle

    await idle()

# ==================================================
# RUN
# ==================================================

app.run()