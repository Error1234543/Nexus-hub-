import os
import asyncio
import random
import string
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

# ==========================================
# FLASK WEB SERVER
# ==========================================

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

# ==========================================
# ENV VARIABLES
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

API_ID = int(os.getenv("API_ID"))

API_HASH = os.getenv("API_HASH")

OWNER_ID = int(os.getenv("OWNER_ID"))

MONGO_URI = os.getenv("MONGO_URI")

VPLINK_API = os.getenv("VPLINK_API")

BOT_USERNAME = os.getenv("BOT_USERNAME")

# ==========================================
# CHANNELS
# ==========================================

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

# ==========================================
# PYROGRAM BOT
# ==========================================

app = Client(
    "TempAccessBot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# ==========================================
# DATABASE
# ==========================================

mongo = AsyncIOMotorClient(MONGO_URI)

db = mongo.temp_access_bot

users = db.users

tokens = db.tokens

# ==========================================
# SCHEDULER
# ==========================================

scheduler = AsyncIOScheduler()

# ==========================================
# GENERATE TOKEN
# ==========================================

def generate_token(length=12):

    return ''.join(
        random.choices(
            string.ascii_letters + string.digits,
            k=length
        )
    )

# ==========================================
# SHORTLINK GENERATOR
# ==========================================

async def generate_shortlink(user_id):

    token = generate_token()

    deep_link = (
        f"https://t.me/"
        f"{BOT_USERNAME}"
        f"?start={token}"
    )

    # SAVE TOKEN

    await tokens.insert_one(
        {
            "user_id": user_id,
            "token": token,
            "used": False,
            "created_at": datetime.utcnow()
        }
    )

    api_url = (
        f"https://vplink.in/api"
        f"?api={VPLINK_API}"
        f"&url={deep_link}"
    )

    try:

        async with aiohttp.ClientSession() as session:

            async with session.get(api_url) as response:

                data = await response.json()

                print(data)

                if data.get("status") == "success":

                    return data.get(
                        "shortenedUrl"
                    )

    except Exception as e:
        print(e)

    return None

# ==========================================
# START COMMAND
# ==========================================

@app.on_message(filters.command("start"))
async def start_command(client, message):

    data = message.text.split()

    user = message.from_user

    user_id = user.id

    # ======================================
    # TOKEN VERIFY SYSTEM
    # ======================================

    if len(data) > 1:

        token = data[1]

        token_data = await tokens.find_one(
            {
                "token": token
            }
        )

        # INVALID TOKEN

        if not token_data:

            return await message.reply_text(
                "❌ Invalid verification token"
            )

        # USED TOKEN

        if token_data.get("used"):

            return await message.reply_text(
                "❌ This verification link is already used"
            )

        # TOKEN OWNER CHECK

        if token_data["user_id"] != user_id:

            return await message.reply_text(
                "❌ This verification link belongs to another user"
            )

        # TOKEN EXPIRE CHECK

        created_time = token_data["created_at"]

        if (
            datetime.utcnow() - created_time
        ).total_seconds() > 300:

            return await message.reply_text(
                "❌ Verification link expired"
            )

        # MARK TOKEN USED

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
                    f"❌ Failed For "
                    f"{channel['name']}\n\n"
                )

        final_text += (
            "⏰ Links expire in 1 minute\n"
            "⚠️ Access valid for 12 hours only"
        )

        expiry_12h = (
            datetime.utcnow()
            + timedelta(hours=12)
        )

        # SAVE USER

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

        # OWNER ALERT

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

        return await message.reply_text(
            final_text
        )

    # ======================================
    # NORMAL START
    # ======================================

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
        "✅ Complete shortlink verification\n"
        "✅ Get temporary channel access\n"
        "✅ Access valid for 12 hours\n"
        "✅ Rejoin anytime after expiry\n\n"
        "👇 Click below to continue"
    )

    await message.reply_text(
        text,
        reply_markup=keyboard
    )

# ==========================================
# GENERATE LINK BUTTON
# ==========================================

@app.on_callback_query(
    filters.regex("generate_link")
)
async def generate_link(
    client,
    callback_query
):

    user_id = callback_query.from_user.id

    shortlink = await generate_shortlink(
        user_id
    )

    if not shortlink:

        return await callback_query.message.reply_text(
            "❌ Failed to generate verification link"
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔗 Verify & Get Access",
                    url=shortlink
                )
            ]
        ]
    )

    await callback_query.message.reply_text(
        (
            "🔐 Complete shortlink verification.\n\n"
            "⚠️ Verification link valid for 5 minutes."
        ),
        reply_markup=keyboard
    )

# ==========================================
# REMOVE EXPIRED USERS
# ==========================================

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

        # MESSAGE USER

        try:

            await app.send_message(
                user_id,
                (
                    "⏰ Your access expired.\n\n"
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

# ==========================================
# STARTUP
# ==========================================

async def startup():

    scheduler.add_job(
        remove_expired_users,
        "interval",
        minutes=5
    )

    scheduler.start()

    print("Scheduler Started!")

# ==========================================
# START BOT
# ==========================================

async def main():

    await startup()

    print("Bot Started Successfully!")

    await app.start()

    from pyrogram.idle import idle

    await idle()

# ==========================================
# RUN
# ==========================================

app.run()