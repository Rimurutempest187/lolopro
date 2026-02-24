#!/usr/bin/env python3
# coding: utf-8
"""
Production-ready single-file Telegram bot (fixed).
Requirements:
  - python 3.10+
  - python-telegram-bot >= 20.0
Install:
  pip install -r requirements.txt
Run:
  export BOT_TOKEN="12345:ABC..."
  python bot.py
Create by : @Enoch_777 (fixed version)
"""

import os
import json
import random
import logging
import asyncio
from datetime import datetime, timedelta
from html import escape

from dotenv import load_dotenv

# Telegram imports (v20+)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ----------------- CONFIG -----------------
load_dotenv()

DATA_FILE = os.getenv("DATA_FILE", "data.json")  # <-- ensure defined before load_data()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
DROP_COUNT = int(os.getenv("DROP_COUNT", 10))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# ----------------- LOGGING -----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG if DEBUG else logging.INFO,
)
logger = logging.getLogger(__name__)

# ----------------- GLOBAL STATE -----------------
data_lock = asyncio.Lock()  # used to serialize writes


def load_data():
    """Load JSON data from disk (synchronous)."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except Exception as e:
            logger.exception("Failed to load data file, starting with defaults: %s", e)
            obj = {}
    else:
        obj = {}

    default = {
        "users": {},  # keys are strings of user_id
        "groups": {},  # keys are strings of chat_id
        "cards": [],  # list of card dicts
        "sudos": [],  # list of ints
        "drop_count": DROP_COUNT,
        "group_messages": {},
        "vote_options": [],
        "votes": {},
        "dropped_cards": {},
    }

    for k, v in default.items():
        if k not in obj:
            obj[k] = v

    # normalize sudos to ints
    try:
        obj["sudos"] = [int(x) for x in obj.get("sudos", [])]
    except Exception:
        obj["sudos"] = []

    # ensure drop_count respects env default if not present
    if "drop_count" not in obj or not isinstance(obj.get("drop_count"), int):
        obj["drop_count"] = DROP_COUNT

    return obj


data = load_data()


async def save_data_safe():
    """Async-safe write to JSON file using a lock."""
    global data
    async with data_lock:
        tmp = DATA_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception:
            logger.exception("Failed to save data to disk")
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass


# ----------------- RARITY -----------------
RARITIES = {
    "Common": {"emoji": "🟤", "price": 5000},
    "Rare": {"emoji": "🟡", "price": 15000},
    "Epic": {"emoji": "🔮", "price": 35000},
    "Legendary": {"emoji": "⚡", "price": 75000},
    "Mythic": {"emoji": "👑", "price": 150000},
}


# ----------------- HELPERS -----------------
def uid_str(user_id):
    return str(int(user_id))


def get_user(user_id: int):
    """Return user dict, create default if missing. Note: does NOT auto-save."""
    user_key = uid_str(user_id)
    if user_key not in data["users"]:
        data["users"][user_key] = {
            "coins": 10_000,
            "cards": [],  # legacy field
            "harem": [],
            "fav_card": None,
            "last_daily": None,
            "last_slime": None,
        }
    return data["users"][user_key]


def is_admin(user_id: int) -> bool:
    """Check admin (explicit ADMIN_IDS or sudos)."""
    try:
        return int(user_id) in ADMIN_IDS or int(user_id) in [int(x) for x in data.get("sudos", [])]
    except Exception:
        return False


def safe_name(s: str) -> str:
    """Escape text for HTML parse mode."""
    return escape(str(s))


def check_cooldown(user_id: int, action: str, cooldown_seconds: int):
    """Return (can_use: bool, remaining_seconds: int)."""
    user = get_user(user_id)
    last_time = user.get(f"last_{action}")
    if last_time:
        try:
            last_dt = datetime.fromisoformat(last_time)
            delta = (datetime.now() - last_dt).total_seconds()
            if delta < cooldown_seconds:
                remaining = int(cooldown_seconds - delta)
                return False, remaining
        except Exception:
            # invalid timestamp, allow
            return True, 0
    return True, 0


def get_rarity_weight():
    """Return a random rarity based on weights."""
    weights = {"Common": 50, "Rare": 30, "Epic": 12, "Legendary": 6, "Mythic": 2}
    rarities = list(weights.keys())
    weights_list = list(weights.values())
    return random.choices(rarities, weights=weights_list)[0]


# ----------------- COMMAND HANDLERS -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id)  # initialize if needed
    await save_data_safe()

    welcome_text = (
        f"👋 <b>ကြိုဆိုပါတယ် {safe_name(user.first_name)}!</b>\n\n"
        "🎴 <b>Character Collection Game Bot မှကြိုဆိုပါတယ်!</b>\n\n"
        "🎮 <b>ဂိမ်းနည်းလမ်း:</b>\n"
        "• /slime - ကဒ်များကောက်ယူပါ\n"
        "• /harem - သင့် collection ကြည့်ပါ\n"
        "• /shop - ဆိုင်\n"
        "• /daily - နေ့စဉ်ဆု\n\n"
        "💰 ဂိမ်း: /slots <amount>, /basket <amount>\n\n"
        "━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    )

    if update.message:
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)


# --------- SLIME (claim dropped card) ----------
async def slime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    can_use, remaining = check_cooldown(user_id, "slime", 10)
    if not can_use:
        await update.message.reply_text(f"⏰ ခဏစောင့်ပါ! {remaining} စက္ကန့်ကျန်ပါသေးတယ်။")
        return

    chat_id = str(update.effective_chat.id)
    dropped_cards = data.get("dropped_cards", {})
    if chat_id not in dropped_cards:
        await update.message.reply_text("❌ လောလောဆယ် card ကျထားတာမရှိပါဘူး!")
        return

    dropped_card = dropped_cards[chat_id]

    if not context.args:
        await update.message.reply_text("❌ Character အမည်ရေးပါ!\nဥပမာ: /slime <character name>")
        return

    guess_name = " ".join(context.args).strip()
    if guess_name.lower() != dropped_card["name"].lower():
        await update.message.reply_text(f"❌ မှားပါတယ်! {safe_name(update.effective_user.first_name)}")
        return

    user = get_user(user_id)
    new_card = dropped_card.copy()
    new_card["id"] = f"{dropped_card['id']}_{random.randint(1000,9999)}"

    user["harem"].append(new_card)
    user["last_slime"] = datetime.now().isoformat()

    try:
        del data["dropped_cards"][chat_id]
    except KeyError:
        pass

    await save_data_safe()

    rarity_emoji = RARITIES.get(dropped_card.get("rarity", "Common"), {}).get("emoji", "")
    await update.message.reply_text(
        (
            f"🎉 <b>အောင်မြင်ပါပြီ {safe_name(update.effective_user.first_name)}!</b>\n\n"
            f"{rarity_emoji} <b>{safe_name(dropped_card['name'])}</b>\n"
            f"🎬 {safe_name(dropped_card['movie'])}\n"
            f"🆔 <code>{safe_name(new_card['id'])}</code>\n"
            f"✨ {safe_name(dropped_card['rarity'])}\n\n"
            f"သင့် harem ထဲသို့ ထည့်ပြီးပါပြီ! ✨"
        ),
        parse_mode=ParseMode.HTML,
    )


# --------- HAREM (view collection) ----------
async def harem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user["harem"]:
        await update.message.reply_text(
            "📭 သင့်မှာ card တစ်ခုမှမရှိသေးပါဘူး!\n💡 /slime နဲ့ card များကောက်ယူပါ!"
        )
        return

    page = 0
    if context.args and context.args[0].isdigit():
        page = max(0, int(context.args[0]) - 1)

    cards_per_page = 5
    all_cards = user["harem"]
    total_pages = max(1, (len(all_cards) + cards_per_page - 1) // cards_per_page)
    if page >= total_pages:
        page = 0

    start_idx = page * cards_per_page
    end_idx = min(start_idx + cards_per_page, len(all_cards))

    message = f"🎴 <b>{safe_name(update.effective_user.first_name)} ရဲ့ Collection</b>\n\n"
    message += f"💎 Total Cards: {len(all_cards)}\n\n"

    for card in all_cards[start_idx:end_idx]:
        rarity_emoji = RARITIES.get(card.get("rarity", "Common"), {}).get("emoji", "")
        movie_cards_owned = len([c for c in all_cards if c.get("movie") == card.get("movie")])
        total_movie_cards = len([c for c in data.get("cards", []) if c.get("movie") == card.get("movie")])
        message += (
            f"{rarity_emoji} <b>{safe_name(card.get('name'))}</b>\n"
            f"🎬 {safe_name(card.get('movie'))} (own: {movie_cards_owned}/{total_movie_cards})\n"
            f"🆔 <code>{safe_name(card.get('id'))}</code>\n\n"
        )

    keyboard = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"harem_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="page_info"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"harem_{page+1}"))
    keyboard.append(nav_buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)

    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"

    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def harem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "page_info":
        return

    try:
        page = int(query.data.split("_")[1])
    except Exception:
        page = 0

    user_id = query.from_user.id
    user = get_user(user_id)
    cards_per_page = 5
    all_cards = user["harem"]
    total_pages = max(1, (len(all_cards) + cards_per_page - 1) // cards_per_page)
    if page < 0 or page >= total_pages:
        page = 0

    start_idx = page * cards_per_page
    end_idx = min(start_idx + cards_per_page, len(all_cards))

    message = f"🎴 <b>{safe_name(query.from_user.first_name)} ရဲ့ Collection</b>\n\n"
    message += f"💎 Total Cards: {len(all_cards)}\n\n"

    for card in all_cards[start_idx:end_idx]:
        rarity_emoji = RARITIES.get(card.get("rarity", "Common"), {}).get("emoji", "")
        movie_cards_owned = len([c for c in all_cards if c.get("movie") == card.get("movie")])
        total_movie_cards = len([c for c in data.get("cards", []) if c.get("movie") == card.get("movie")])
        message += (
            f"{rarity_emoji} <b>{safe_name(card.get('name'))}</b>\n"
            f"🎬 {safe_name(card.get('movie'))} (own: {movie_cards_owned}/{total_movie_cards})\n"
            f"🆔 <code>{safe_name(card.get('id'))}</code>\n\n"
        )

    keyboard = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"harem_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="page_info"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"harem_{page+1}"))
    keyboard.append(nav_buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)

    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"

    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


# --------- Set favorite card ----------
async def set_fav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    user = get_user(user_id)

    if not context.args:
        await update.message.reply_text("❌ Card ID ထည့်ပါ!\nဥပမာ: /set <card_id>")
        return

    card_id = context.args[0]
    card = next((c for c in user["harem"] if c.get("id") == card_id), None)
    if not card:
        await update.message.reply_text("❌ သင့် harem မှာ ဒီ card မရှိပါဘူး!")
        return

    user["fav_card"] = card_id
    await save_data_safe()

    rarity_emoji = RARITIES.get(card.get("rarity", "Common"), {}).get("emoji", "")
    await update.message.reply_text(
        (
            f"⭐ <b>Favorite Card သတ်မှတ်ပြီးပါပြီ!</b>\n\n"
            f"{rarity_emoji} <b>{safe_name(card.get('name'))}</b>\n"
            f"🎬 {safe_name(card.get('movie'))}"
        ),
        parse_mode=ParseMode.HTML,
    )


# --------- SLOTS ----------
async def slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    user = get_user(user_id)

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Bet ပမာဏထည့်ပါ!\nဥပမာ: /slots 1000")
        return

    bet = int(context.args[0])
    if bet < 100:
        await update.message.reply_text("❌ အနည်းဆုံး 100 coins bet ထားရပါမယ်!")
        return

    if user["coins"] < bet:
        await update.message.reply_text(f"❌ Coins မလောက်ပါဘူး!\n💰 လက်ကျန်: {user['coins']} coins")
        return

    user["coins"] -= bet

    symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎"]
    result = [random.choice(symbols) for _ in range(3)]

    multiplier = 0
    if result[0] == result[1] == result[2]:
        if result[0] == "💎":
            multiplier = 3
        else:
            multiplier = 2

    if multiplier > 0:
        winnings = bet * multiplier
        user["coins"] += winnings
        message = (
            f"🎰 <b>SLOT MACHINE</b> 🎰\n\n"
            f"{''.join(result)}\n\n"
            f"🎉 <b>သင်နိုင်ပါတယ်!</b>\n"
            f"💰 +{winnings} coins (×{multiplier})\n"
            f"💵 လက်ကျန်: {user['coins']} coins"
        )
    else:
        message = (
            f"🎰 <b>SLOT MACHINE</b> 🎰\n\n"
            f"{''.join(result)}\n\n"
            f"😢 <b>သင်ရှုံးပါတယ်!</b>\n"
            f"💸 -{bet} coins\n"
            f"💵 လက်ကျန်: {user['coins']} coins"
        )

    await save_data_safe()
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


# --------- BASKET ----------
async def basket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    user = get_user(user_id)

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ Bet ပမာဏထည့်ပါ!\nဥပမာ: /basket 1000")
        return

    bet = int(context.args[0])
    if bet < 100:
        await update.message.reply_text("❌ အနည်းဆုံး 100 coins bet ထားရပါမယ်!")
        return

    if user["coins"] < bet:
        await update.message.reply_text(f"❌ Coins မလောက်ပါဘူး!\n💰 လက်ကျန်: {user['coins']} coins")
        return

    user["coins"] -= bet

    dice = await update.message.reply_dice(emoji="🏀")
    await asyncio.sleep(1.5)

    value = None
    try:
        value = dice.dice.value
    except Exception:
        value = random.randint(1, 6)

    if value in [4, 5]:
        multiplier = 3 if value == 5 else 2
        winnings = bet * multiplier
        user["coins"] += winnings
        message = (
            f"🏀 <b>BASKETBALL GAME</b> 🏀\n\n"
            f"🎯 <b>ဝင်ပါတယ်!</b>\n"
            f"💰 +{winnings} coins (×{multiplier})\n"
            f"💵 လက်ကျန်: {user['coins']} coins"
        )
    else:
        message = (
            f"🏀 <b>BASKETBALL GAME</b> 🏀\n\n"
            f"😢 <b>လွဲသွားပါတယ်!</b>\n"
            f"💸 -{bet} coins\n"
            f"💵 လက်ကျန်: {user['coins']} coins"
        )

    await save_data_safe()
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


# --------- GIVE COIN ----------
async def givecoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    sender_id = update.effective_user.id
    sender = get_user(sender_id)

    target_user_id = None
    amount = None

    if update.message.reply_to_message:
        try:
            amount = int(context.args[0]) if context.args and context.args[0].isdigit() else None
            target_user_id = update.message.reply_to_message.from_user.id
        except Exception:
            amount = None
    else:
        if context.args and len(context.args) >= 2:
            try:
                target_user_id = int(context.args[0])
                amount = int(context.args[1])
            except Exception:
                target_user_id = None
                amount = None

    if not target_user_id or amount is None:
        await update.message.reply_text(
            "❌ အသုံးပြုနည်း:\nReply လုပ်ပြီး: /givecoin <amount>\nသို့မဟုတ်: /givecoin <user_id> <amount>"
        )
        return

    if amount < 1:
        await update.message.reply_text("❌ အနည်းဆုံး 1 coin ပို့ရပါမယ်!")
        return

    if sender["coins"] < amount:
        await update.message.reply_text(f"❌ Coins မလောက်ပါဘူး!\n💰 လက်ကျန်: {sender['coins']} coins")
        return

    if int(target_user_id) == int(sender_id):
        await update.message.reply_text("❌ မိမိကိုယ်ကို coins မပို့နိုင်ပါဘူး!")
        return

    receiver = get_user(target_user_id)
    sender["coins"] -= amount
    receiver["coins"] += amount

    await save_data_safe()
    await update.message.reply_text(
        (
            f"✅ <b>အောင်မြင်ပါတယ်!</b>\n\n"
            f"💸 {amount} coins ပို့ပြီးပါပြီ!\n"
            f"💰 သင့်လက်ကျန်: {sender['coins']} coins"
        ),
        parse_mode=ParseMode.HTML,
    )


# --------- BALANCE ----------
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user = get_user(update.effective_user.id)
    await update.message.reply_text(
        (
            f"💰 <b>{safe_name(update.effective_user.first_name)} ရဲ့ Balance</b>\n\n"
            f"💵 Coins: <b>{user['coins']:,}</b>\n"
            f"🎴 Cards: <b>{len(user['harem'])}</b>"
        ),
        parse_mode=ParseMode.HTML,
    )


# --------- DAILY ----------
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    user_id = update.effective_user.id
    user = get_user(user_id)

    last_daily = user.get("last_daily")
    if last_daily:
        try:
            last_dt = datetime.fromisoformat(last_daily)
            if datetime.now().date() == last_dt.date():
                next_time = (last_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0)
                remaining = next_time - datetime.now()
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                await update.message.reply_text(
                    f"⏰ နေ့စဉ်ဆုလာဘ် ယူပြီးပါပြီ!\n⏳ နောက်တစ်ခါယူရန် {hours}နာရီ {minutes}မိနစ်ကျန်ပါသေးတယ်။"
                )
                return
        except Exception:
            pass

    bonus = random.randint(5000, 50000)
    user["coins"] += bonus
    user["last_daily"] = datetime.now().isoformat()
    await save_data_safe()

    await update.message.reply_text(
        (
            f"🎁 <b>နေ့စဉ်ဆုလာဘ်!</b>\n\n"
            f"💰 +{bonus:,} coins\n"
            f"💵 လက်ကျန်: {user['coins']:,} coins\n\n"
            f"🔄 နောက်တစ်ခါ 24 နာရီအကြာယူနိုင်ပါမယ်!"
        ),
        parse_mode=ParseMode.HTML,
    )


# --------- SHOP & Shop callback ----------
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not data.get("cards"):
        await update.message.reply_text("❌ ဆိုင်မှာ card များမရှိသေးပါဘူး!")
        return

    idx = 0
    card = data["cards"][idx]
    rarity_emoji = RARITIES.get(card.get("rarity", "Common"), {}).get("emoji", "")
    price = RARITIES.get(card.get("rarity", "Common"), {}).get("price", 0)

    message = (
        f"🏪 <b>CHARACTER SHOP</b>\n\n"
        f"{rarity_emoji} <b>{safe_name(card.get('name'))}</b>\n"
        f"🎬 {safe_name(card.get('movie'))}\n"
        f"✨ {safe_name(card.get('rarity'))}\n"
        f"💰 ဈေးနှုန်း: <b>{price:,} coins</b>\n\n"
        f"📦 Card {idx+1}/{len(data['cards'])}"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ ဝယ်မယ်", callback_data=f"buy_{idx}"),
            InlineKeyboardButton("➡️ Next", callback_data=f"shop_{(idx+1)%len(data['cards'])}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        action, idx = query.data.split("_")
        idx = int(idx)
    except Exception:
        await query.answer("Invalid action", show_alert=True)
        return

    if action == "buy":
        user_id = query.from_user.id
        user = get_user(user_id)
        if idx < 0 or idx >= len(data["cards"]):
            await query.answer("Card not found", show_alert=True)
            return
        card = data["cards"][idx]
        price = RARITIES.get(card.get("rarity", "Common"), {}).get("price", 0)

        if user["coins"] < price:
            await query.answer(f"❌ Coins မလောက်ပါဘူး! လိုအပ်တယ်: {price:,} coins", show_alert=True)
            return

        new_card = card.copy()
        new_card["id"] = f"{card['id']}_{random.randint(1000,9999)}"

        user["coins"] -= price
        user["harem"].append(new_card)
        await save_data_safe()

        rarity_emoji = RARITIES.get(card.get("rarity", "Common"), {}).get("emoji", "")
        await query.edit_message_text(
            (
                f"🎉 <b>ဝယ်ယူမှုအောင်မြင်ပါတယ်!</b>\n\n"
                f"{rarity_emoji} <b>{safe_name(card.get('name'))}</b>\n"
                f"🎬 {safe_name(card.get('movie'))}\n"
                f"💸 -{price:,} coins\n"
                f"💰 လက်ကျန်: {user['coins']:,} coins"
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    elif action == "shop":
        if idx < 0 or not data.get("cards"):
            idx = 0
        else:
            idx = idx % len(data["cards"])

        card = data["cards"][idx]
        rarity_emoji = RARITIES.get(card.get("rarity", "Common"), {}).get("emoji", "")
        price = RARITIES.get(card.get("rarity", "Common"), {}).get("price", 0)

        message = (
            f"🏪 <b>CHARACTER SHOP</b>\n\n"
            f"{rarity_emoji} <b>{safe_name(card.get('name'))}</b>\n"
            f"🎬 {safe_name(card.get('movie'))}\n"
            f"✨ {safe_name(card.get('rarity'))}\n"
            f"💰 ဈေးနှုန်း: <b>{price:,} coins</b>\n\n"
            f"📦 Card {idx+1}/{len(data['cards'])}"
        )

        buttons = [
            InlineKeyboardButton("✅ ဝယ်မယ်", callback_data=f"buy_{idx}"),
            InlineKeyboardButton("➡️ Next", callback_data=f"shop_{(idx+1)%len(data['cards'])}")
        ]
        if idx > 0:
            buttons.insert(0, InlineKeyboardButton("⬅️ Prev", callback_data=f"shop_{idx-1}"))
        reply_markup = InlineKeyboardMarkup([buttons])
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


# --------- TOPS ----------
async def tops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    keyboard = [
        [
            InlineKeyboardButton("💰 Top Coins", callback_data="tops_coins"),
            InlineKeyboardButton("🎴 Top Cards", callback_data="tops_cards"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏆 <b>LEADERBOARD</b>\n\nဘာကိုကြည့်ချင်ပါသလဲ?", reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def tops_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        top_type = query.data.split("_")[1]
    except Exception:
        top_type = "coins"

    if top_type == "coins":
        sorted_users = sorted(data["users"].items(), key=lambda x: x[1].get("coins", 0), reverse=True)[:10]
        title = "💰 <b>TOP 10 - RICHEST PLAYERS</b>"
        value_key = "coins"
        emoji = "💵"
    else:
        sorted_users = sorted(data["users"].items(), key=lambda x: len(x[1].get("harem", [])), reverse=True)[:10]
        title = "🎴 <b>TOP 10 - CARD COLLECTORS</b>"
        value_key = "harem"
        emoji = "🎴"

    message = f"{title}\n\n"
    medals = ["🥇", "🥈", "🥉"]

    for i, (user_id_str, user_data) in enumerate(sorted_users):
        try:
            user_chat = await context.bot.get_chat(int(user_id_str))
            name = user_chat.first_name or "Unknown"
        except Exception:
            name = "Unknown"
        medal = medals[i] if i < 3 else f"{i+1}."
        if value_key == "coins":
            value = int(user_data.get("coins", 0))
            message += f"{medal} <b>{safe_name(name)}</b> - {emoji} {value:,}\n"
        else:
            value = len(user_data.get("harem", []))
            message += f"{medal} <b>{safe_name(name)}</b> - {emoji} {value}\n"

    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"

    await query.edit_message_text(message, parse_mode=ParseMode.HTML)


# --------- MESSAGE COUNTER (card drops) ----------
async def message_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    if chat.type == "private":
        return

    chat_id = str(chat.id)
    if chat_id not in data["group_messages"]:
        data["group_messages"][chat_id] = 0
    data["group_messages"][chat_id] += 1

    if data["group_messages"][chat_id] >= data.get("drop_count", DROP_COUNT):
        data["group_messages"][chat_id] = 0
        if data.get("cards"):
            card = random.choice(data["cards"]).copy()
            card["id"] = f"{card['id']}_{random.randint(1000,9999)}"
            if "dropped_cards" not in data:
                data["dropped_cards"] = {}
            data["dropped_cards"][chat_id] = card
            await save_data_safe()

            rarity_emoji = RARITIES.get(card.get("rarity", "Common"), {}).get("emoji", "")
            masked = "█" * len(card.get("name", ""))
            await update.message.reply_text(
                (
                    f"🎴 <b>CARD DROP!</b>\n\n"
                    f"{rarity_emoji} <b>{masked}</b>\n"
                    f"🎬 {safe_name(card.get('movie'))}\n"
                    f"✨ {safe_name(card.get('rarity'))}\n\n"
                    f"💡 /slime &lt;character name&gt; နဲ့ယူပါ!\n"
                    f"⏰ 10 seconds cooldown"
                ),
                parse_mode=ParseMode.HTML,
            )


# ----------------- ADMIN COMMANDS -----------------
async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ သင့်မှာ ခွင့်ပြုချက်မရှိပါဘူး!")
        return

    target_msg = update.message.reply_to_message or update.message
    caption = target_msg.caption or update.message.caption
    photo_obj = None
    if target_msg.photo:
        photo_obj = target_msg.photo[-1]
    elif update.message.photo:
        photo_obj = update.message.photo[-1]

    if not caption or not photo_obj:
        await update.message.reply_text(
            "❌ အသုံးပြုနည်း:\nPhoto နဲ့ caption ပေးပို့ပါ:\n`Character Name | Movie Name | Rarity`"
        )
        return

    parts = [p.strip() for p in caption.split("|", maxsplit=2)]
    if len(parts) != 3:
        await update.message.reply_text("❌ Format မှားနေပါတယ်! အသုံးပြုနည်း: Character Name | Movie Name | Rarity")
        return

    char_name, movie_name, rarity = parts
    rarity = rarity.title()
    if rarity not in RARITIES:
        await update.message.reply_text(f"❌ Rarity မှားနေပါတယ်! ရွေးချယ်နိုင်တာများ: {', '.join(RARITIES.keys())}")
        return

    card_id = f"card_{len(data.get('cards', [])) + 1}"
    card = {"id": card_id, "name": char_name, "movie": movie_name, "rarity": rarity, "photo": photo_obj.file_id}
    data["cards"].append(card)
    await save_data_safe()

    rarity_emoji = RARITIES[rarity]["emoji"]
    await update.message.reply_text(
        (
            f"✅ <b>Card တင်ပြီးပါပြီ!</b>\n\n"
            f"{rarity_emoji} <b>{safe_name(char_name)}</b>\n"
            f"🎬 {safe_name(movie_name)}\n"
            f"🆔 <code>{safe_name(card_id)}</code>\n"
            f"✨ {safe_name(rarity)}"
        ),
        parse_mode=ParseMode.HTML,
    )


async def setdrop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ အသုံးပြုနည်း: /setdrop <number>")
        return
    count = int(context.args[0])
    if count < 1:
        await update.message.reply_text("❌ အနည်းဆုံး 1 ဖြစ်ရပါမယ်!")
        return
    data["drop_count"] = count
    await save_data_safe()
    await update.message.reply_text(f"✅ Card drop count ကို <b>{count}</b> messages သတ်မှတ်ပြီးပါပြီ!", parse_mode=ParseMode.HTML)


async def gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ အသုံးပြုနည်း: /gift coin <amount> [user_id] OR /gift card <amount> [user_id]\n"
            "သို့မဟုတ် reply to user with /gift coin <amount>"
        )
        return

    sub = context.args[0].lower()
    if sub not in ("coin", "card"):
        await update.message.reply_text("❌ Subcommand မမှန်ပါ! coin သို့မဟုတ် cardသာ ထောက်ပံ့ပါတယ်။")
        return

    target_user_id = None
    amount = None
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        if len(context.args) >= 2 and context.args[1].isdigit():
            amount = int(context.args[1])
    else:
        if len(context.args) >= 2:
            if context.args[1].isdigit():
                amount = int(context.args[1])
            if len(context.args) >= 3 and context.args[2].isdigit():
                target_user_id = int(context.args[2])

    if amount is None or (target_user_id is None):
        await update.message.reply_text("❌ Usage: /gift coin <amount> <user_id> OR reply to user with /gift coin <amount>")
        return

    if sub == "coin":
        target_user = get_user(target_user_id)
        target_user["coins"] += amount
        await save_data_safe()
        await update.message.reply_text(f"✅ <b>{amount:,} coins ပေးပြီးပါပြီ!</b>\n👤 User ID: <code>{target_user_id}</code>", parse_mode=ParseMode.HTML)
    else:
        if not data.get("cards"):
            await update.message.reply_text("❌ Card များမရှိသေးပါဘူး!")
            return
        target_user = get_user(target_user_id)
        for _ in range(amount):
            card = random.choice(data["cards"]).copy()
            card["id"] = f"{card['id']}_{random.randint(1000,9999)}"
            target_user["harem"].append(card)
        await save_data_safe()
        await update.message.reply_text(f"✅ <b>{amount} random cards ပေးပြီးပါပြီ!</b>\n👤 User ID: <code>{target_user_id}</code>", parse_mode=ParseMode.HTML)


async def edit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return

    admin_commands = (
        "🔧 <b>ADMIN COMMANDS</b>\n\n"
        "📤 /upload - Card အသစ်တင်ရန် (reply photo + caption)\n"
        "⚙️ /setdrop <number> - Card drop count သတ်မှတ်ရန်\n"
        "💰 /gift coin <amount> <user_id> - Coins ပေးရန်\n"
        "🎴 /gift card <amount> <user_id> - Cards ပေးရန်\n"
        "📢 /broadcast - Message ပို့ရန် (reply the message)\n"
        "📊 /stats - Statistics ကြည့်ရန်\n"
        "💾 /backup - Data backup လုပ်ရန်\n"
        "♻️ /restore - Data ပြန်ယူရန် (reply with file)\n"
        "🗑️ /allclear - Data အားလုံးဖျက်ရန်\n"
        "❌ /delete <card_id> - Card ဖျက်ရန်\n"
        "👑 /addsudo <user> - Sudo ထည့်ရန်\n"
        "📋 /sudolist - Sudo list ကြည့်ရန်\n"
        "🗳️ /evote - Vote စတင်ရန်\n\n"
        "━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    )
    await update.message.reply_text(admin_commands, parse_mode=ParseMode.HTML)


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return

    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text("❌ Message ထည့်ပါ! အသုံးပြုနည်း: /broadcast <message> OR reply the message")
        return

    if update.message.reply_to_message:
        msg = update.message.reply_to_message
        text = msg.text or msg.caption or ""
        photo = msg.photo[-1].file_id if msg.photo else None
    else:
        text = " ".join(context.args)
        photo = None

    success = 0
    failed = 0
    for group_id in list(data.get("groups", {}).keys()):
        try:
            if photo:
                await context.bot.send_photo(chat_id=int(group_id), photo=photo, caption=text)
            else:
                await context.bot.send_message(chat_id=int(group_id), text=text)
            success += 1
        except Exception:
            failed += 1

    await update.message.reply_text(f"📢 <b>Broadcast ပြီးပါပြီ!</b>\n\n✅ အောင်မြင်: {success}\n❌ မအောင်မြင်: {failed}", parse_mode=ParseMode.HTML)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return

    total_users = len(data.get("users", {}))
    total_groups = len(data.get("groups", {}))
    total_cards = len(data.get("cards", []))
    stats_text = (
        f"📊 <b>BOT STATISTICS</b>\n\n"
        f"👥 Total Users: <b>{total_users}</b>\n"
        f"👥 Total Groups: <b>{total_groups}</b>\n"
        f"🎴 Total Cards: <b>{total_cards}</b>\n"
        f"👑 Sudos: <b>{len(data.get('sudos', []))}</b>\n\n"
        "━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    )
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return

    await save_data_safe()
    try:
        with open(DATA_FILE, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                caption="💾 <b>Data Backup</b>\n\nBackup ပြီးပါပြီ!",
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        await update.message.reply_text("❌ Backup ဖိုင်ပေးပို့ရန် မအောင်မြင်ပါ!")


async def restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return

    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("❌ Backup file ကို reply လုပ်ပါ!")
        return

    doc = update.message.reply_to_message.document
    try:
        file = await doc.get_file()
        await file.download_to_drive(DATA_FILE)
        global data
        data = load_data()
        await update.message.reply_text("♻️ <b>Data Restore ပြီးပါပြီ!</b>", parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Restore failed")
        await update.message.reply_text("❌ Restore မအောင်မြင်ပါ!")


async def allclear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ အတည်ပြုပါတယ်", callback_data="confirm_clear"),
            InlineKeyboardButton("❌ ပယ်ဖျက်မယ်", callback_data="cancel_clear"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚠️ <b>သတိပြုပါ!</b>\n\nData အားလုံး ဖျက်မှာသေချာပါသလား?\nဒီလုပ်ငန်းကို ပြန်ပြင်လို့မရပါဘူး!",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )


async def allclear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_clear":
        global data
        data = {
            "users": {},
            "groups": {},
            "cards": [],
            "sudos": [],
            "drop_count": DROP_COUNT,
            "group_messages": {},
            "vote_options": [],
            "votes": {},
            "dropped_cards": {},
        }
        await save_data_safe()
        await query.edit_message_text("🗑️ <b>Data အားလုံး ဖျက်ပြီးပါပြီ!</b>", parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_text("❌ ပယ်ဖျက်ပါတယ်။", parse_mode=ParseMode.HTML)


async def delete_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    if not context.args:
        await update.message.reply_text("❌ Card ID ထည့်ပါ!\nအသုံးပြုနည်း: /delete <card_id>")
        return
    card_id = context.args[0]
    card = next((c for c in data.get("cards", []) if c.get("id") == card_id), None)
    if not card:
        await update.message.reply_text("❌ ဒီ Card ID မရှိပါဘူး!")
        return
    data["cards"].remove(card)
    await save_data_safe()
    await update.message.reply_text(f"✅ <b>Card ဖျက်ပြီးပါပြီ!</b>\n🆔 <code>{card_id}</code>", parse_mode=ParseMode.HTML)


async def addsudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    target_user_id = None
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
    elif context.args and context.args[0].isdigit():
        target_user_id = int(context.args[0])
    else:
        await update.message.reply_text("❌ User ID ထည့်ပါ သို့မဟုတ် reply လုပ်ပါ!")
        return
    if int(target_user_id) in [int(x) for x in data.get("sudos", [])]:
        await update.message.reply_text("❌ ဒီ user က sudo ဖြစ်နေပြီးပါပြီ!")
        return
    data["sudos"].append(int(target_user_id))
    await save_data_safe()
    await update.message.reply_text(f"✅ <b>Sudo ထည့်ပြီးပါပြီ!</b>\n👤 User ID: <code>{target_user_id}</code>", parse_mode=ParseMode.HTML)


async def sudolist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    if not data.get("sudos"):
        await update.message.reply_text("📋 Sudo list ထဲမှာ ဘယ်သူမှမရှိသေးပါဘူး!")
        return
    message = "👑 <b>SUDO LIST</b>\n\n"
    for i, sudo_id in enumerate(data.get("sudos", []), 1):
        try:
            user_chat = await context.bot.get_chat(int(sudo_id))
            name = user_chat.first_name or "Unknown"
        except Exception:
            name = "Unknown"
        message += f"{i}. <b>{safe_name(name)}</b> (<code>{sudo_id}</code>)\n"
    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)


# --------- EVOTE ----------
async def evote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    caller = update.effective_user.id
    if not is_admin(caller):
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    if not context.args:
        await update.message.reply_text("❌ ရွေးချယ်စရာများထည့်ပါ!\nဥပမာ: /evote Luffy, Naruto, Goku")
        return
    options_text = " ".join(context.args)
    options = [opt.strip() for opt in options_text.split(",") if opt.strip()]
    if len(options) < 2:
        await update.message.reply_text("❌ အနည်းဆုံး 2 ခုထည့်ရပါမယ်!")
        return
    data["vote_options"] = options
    data["votes"] = {opt: [] for opt in options}
    await save_data_safe()
    keyboard = [[InlineKeyboardButton(f"🗳️ {opt}", callback_data=f"vote_{opt}")] for opt in options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🗳️ <b>VOTING POLL</b>\n\nသင်ကြိုက်နှစ်သက်တဲ့သူကို ရွေးချယ်ပါ!", reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not data.get("vote_options"):
        await update.message.reply_text("❌ Vote မရှိသေးပါဘူး!")
        return
    message = "🗳️ <b>VOTE RESULTS</b>\n\n"
    for option in data.get("vote_options", []):
        votes = len(data.get("votes", {}).get(option, []))
        message += f"• <b>{safe_name(option)}</b>: {votes} votes\n"
    keyboard = [[InlineKeyboardButton(f"🗳️ {opt}", callback_data=f"vote_{opt}")] for opt in data.get("vote_options", [])]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    option = query.data.replace("vote_", "")
    user_id = query.from_user.id

    for opt, voters in data.get("votes", {}).items():
        if user_id in voters:
            try:
                data["votes"][opt].remove(user_id)
            except ValueError:
                pass

    if option not in data["votes"]:
        data["votes"][option] = []
    data["votes"][option].append(user_id)
    await save_data_safe()
    await query.answer(f"✅ {option} ကိုမဲပေးပြီးပါပြီ!", show_alert=True)

    message = "🗳️ <b>VOTE RESULTS</b>\n\n"
    for opt in data.get("vote_options", []):
        votes = len(data.get("votes", {}).get(opt, []))
        message += f"• <b>{safe_name(opt)}</b>: {votes} votes\n"
    keyboard = [[InlineKeyboardButton(f"🗳️ {opt}", callback_data=f"vote_{opt}")] for opt in data.get("vote_options", [])]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    try:
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


# --------- GROUP TRACKING ----------
async def track_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    chat = update.effective_chat
    if chat and chat.type in ["group", "supergroup"]:
        chat_id = str(chat.id)
        if chat_id not in data.get("groups", {}):
            data["groups"][chat_id] = {"name": chat.title, "joined": datetime.now().isoformat()}
            await save_data_safe()


# --------- ERROR HANDLER ----------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Exception while handling update: %s", context.error)


# ----------------- MAIN -----------------
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Export BOT_TOKEN environment variable and restart.")
        return

    print("🤖 Bot စတင်နေပါသည်...")

    application = Application.builder().token(BOT_TOKEN).build()

    # User commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("slime", slime))
    application.add_handler(CommandHandler("harem", harem))
    application.add_handler(CallbackQueryHandler(harem_callback, pattern="^harem_"))
    application.add_handler(CommandHandler("set", set_fav))
    application.add_handler(CommandHandler("slots", slots))
    application.add_handler(CommandHandler("basket", basket))
    application.add_handler(CommandHandler("givecoin", givecoin))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("shop", shop))
    application.add_handler(CallbackQueryHandler(shop_callback, pattern="^(shop_|buy_)"))
    application.add_handler(CommandHandler("tops", tops))
    application.add_handler(CallbackQueryHandler(tops_callback, pattern="^tops_"))

    # Admin commands
    application.add_handler(CommandHandler("upload", upload))
    application.add_handler(CommandHandler("setdrop", setdrop))
    application.add_handler(CommandHandler("gift", gift))
    application.add_handler(CommandHandler("edit", edit_admin))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("backup", backup))
    application.add_handler(CommandHandler("restore", restore))
    application.add_handler(CommandHandler("allclear", allclear))
    application.add_handler(CallbackQueryHandler(allclear_callback, pattern="^(confirm_|cancel_)clear"))
    application.add_handler(CommandHandler("delete", delete_card))
    application.add_handler(CommandHandler("addsudo", addsudo))
    application.add_handler(CommandHandler("sudolist", sudolist))
    application.add_handler(CommandHandler("evote", evote))
    application.add_handler(CommandHandler("vote", vote))
    application.add_handler(CallbackQueryHandler(vote_callback, pattern="^vote_"))

    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, track_groups))

    # Error handler
    application.add_error_handler(error_handler)

    print("✅ Bot စတင်ပြီးပါပြီ!")
    print("━━━━━━━━━━━━━━━━")
    print("Create by : @Enoch_777")
    print("━━━━━━━━━━━━━━━━")

    application.run_polling()


if __name__ == "__main__":
    main()
