import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode
import random
import json
import os
from datetime import datetime, timedelta
import asyncio

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
ADMIN_IDS = [1812962224]  # Replace with your admin Telegram ID
BOT_TOKEN = "7981415281:AAHH7_pKjf1DY-jqCvQnjwP0hRtP3yPaKwk"  # Replace with your bot token

# ===================== DATA STORAGE =====================
DATA_FILE = "bot_data.json"

def load_data():
    """Load data from JSON file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "users": {},
        "groups": {},
        "cards": [],
        "sudos": [],
        "drop_count": 10,
        "group_messages": {},
        "vote_options": [],
        "votes": {}
    }

def save_data(data):
    """Save data to JSON file"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load_data()

# ===================== RARITY SYSTEM =====================
RARITIES = {
    "Common": {"emoji": "🟤", "price": 5000},
    "Rare": {"emoji": "🟡", "price": 15000},
    "Epic": {"emoji": "🔮", "price": 35000},
    "Legendary": {"emoji": "⚡", "price": 75000},
    "Mythic": {"emoji": "👑", "price": 150000}
}

# ===================== HELPER FUNCTIONS =====================
def get_user(user_id):
    """Get or create user data"""
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "coins": 10000,
            "cards": [],
            "harem": [],
            "fav_card": None,
            "last_daily": None,
            "last_slime": None
        }
        save_data(data)
    return data["users"][user_id]

def get_rarity_weight():
    """Get weighted random rarity"""
    weights = {
        "Common": 50,
        "Rare": 30,
        "Epic": 12,
        "Legendary": 6,
        "Mythic": 2
    }
    rarities = list(weights.keys())
    weights_list = list(weights.values())
    return random.choices(rarities, weights=weights_list)[0]

def format_card_display(card):
    """Format card for display"""
    rarity_emoji = RARITIES[card["rarity"]]["emoji"]
    return (
        f"{rarity_emoji} **{card['name']}**\n"
        f"🎬 {card['movie']}\n"
        f"🆔 `{card['id']}`\n"
        f"✨ {card['rarity']}"
    )

def check_cooldown(user_id, action, cooldown_seconds):
    """Check if user is on cooldown"""
    user = get_user(user_id)
    last_time = user.get(f"last_{action}")
    
    if last_time:
        last_dt = datetime.fromisoformat(last_time)
        if datetime.now() - last_dt < timedelta(seconds=cooldown_seconds):
            remaining = cooldown_seconds - (datetime.now() - last_dt).seconds
            return False, remaining
    
    return True, 0

# ===================== START COMMAND =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - Welcome message"""
    user = update.effective_user
    get_user(user.id)  # Initialize user
    
    welcome_text = f"""
👋 **ကြိုဆိုပါတယ် {user.first_name}!**

🎴 **Character Collection Game Bot မှကြိုဆိုပါတယ်!**

🎮 **ဂိမ်းနည်းလမ်း:**
• `/slime` - ကဒ်များကောက်ယူပါ
• `/harem` - သင့်ကောက်ရှင်ကြည့်ပါ
• `/shop` - ကဒ်များဝယ်ယူပါ
• `/daily` - နေ့စဉ်ဆုလာဘ်ယူပါ

💰 **ဂိမ်းများ:**
• `/slots <amount>` - စလော့ဂိမ်းကစားပါ
• `/basket <amount>` - ဘတ်စကက်ဘောဂိမ်းကစားပါ

🌟 **Rarity System:**
🟤 Common | 🟡 Rare | 🔮 Epic | ⚡ Legendary | 👑 Mythic

📝 အသေးစိတ်ကြည့်ရန် commands များရိုက်ထည့်ကြည့်ပါ!

━━━━━━━━━━━━━━━━
Create by : @Enoch_777
    """
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== SLIME COMMAND (Card Drop) =====================
async def slime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Slime command - Claim dropped card"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Check cooldown
    can_use, remaining = check_cooldown(user_id, "slime", 10)
    if not can_use:
        await update.message.reply_text(
            f"⏰ ခဏစောင့်ပါ! {remaining} စက္ကန့်ကျန်ပါသေးတယ်။"
        )
        return
    
    # Check if there's a dropped card in this chat
    chat_id = str(update.effective_chat.id)
    if chat_id not in data.get("dropped_cards", {}):
        await update.message.reply_text("❌ လောလောဆယ် card ကျထားတာမရှိပါဘူး!")
        return
    
    dropped_card = data["dropped_cards"][chat_id]
    
    # Check if user provided character name
    if not context.args:
        await update.message.reply_text(
            "❌ Character အမည်ရေးပါ!\n"
            f"ဥပမာ: `/slime {dropped_card['name']}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    guess_name = " ".join(context.args)
    
    # Check if name matches
    if guess_name.lower() != dropped_card["name"].lower():
        await update.message.reply_text(
            f"❌ မှားပါတယ်! {update.effective_user.first_name}"
        )
        return
    
    # Add card to user's harem
    user["harem"].append(dropped_card)
    user["last_slime"] = datetime.now().isoformat()
    
    # Remove dropped card
    del data["dropped_cards"][chat_id]
    save_data(data)
    
    rarity_emoji = RARITIES[dropped_card["rarity"]]["emoji"]
    await update.message.reply_text(
        f"🎉 **အめွေးကျေ {update.effective_user.first_name}!**\n\n"
        f"{rarity_emoji} **{dropped_card['name']}**\n"
        f"🎬 {dropped_card['movie']}\n"
        f"🆔 `{dropped_card['id']}`\n"
        f"✨ {dropped_card['rarity']}\n\n"
        f"သင့် harem ထဲသို့ ထည့်ပြီးပါပြီ! ✨",
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== HAREM COMMAND =====================
async def harem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's card collection"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user["harem"]:
        await update.message.reply_text(
            "📭 သင့်မှာ card တစ်ခုမှမရှိသေးပါဘူး!\n"
            "💡 `/slime` နဲ့ card များကောက်ယူပါ!"
        )
        return
    
    # Group cards by movie
    movies = {}
    for card in user["harem"]:
        movie = card["movie"]
        if movie not in movies:
            movies[movie] = []
        movies[movie].append(card)
    
    # Pagination
    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0]) - 1
    
    cards_per_page = 5
    all_cards = user["harem"]
    total_pages = (len(all_cards) + cards_per_page - 1) // cards_per_page
    
    if page < 0 or page >= total_pages:
        page = 0
    
    start_idx = page * cards_per_page
    end_idx = min(start_idx + cards_per_page, len(all_cards))
    
    # Build message
    message = f"🎴 **{update.effective_user.first_name} ရဲ့ Collection**\n\n"
    message += f"💎 Total Cards: {len(all_cards)}\n\n"
    
    for card in all_cards[start_idx:end_idx]:
        rarity_emoji = RARITIES[card["rarity"]]["emoji"]
        
        # Count owned cards from same movie
        movie_cards = [c for c in all_cards if c["movie"] == card["movie"]]
        total_movie_cards = len([c for c in data["cards"] if c["movie"] == card["movie"]])
        
        message += (
            f"{rarity_emoji} **{card['name']}**\n"
            f"🎬 {card['movie']} (own: {len(movie_cards)}/{total_movie_cards})\n"
            f"🆔 `{card['id']}`\n\n"
        )
    
    # Pagination buttons
    keyboard = []
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"harem_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="page_info"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"harem_{page+1}"))
    
    keyboard.append(nav_buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message += f"\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== HAREM PAGINATION CALLBACK =====================
async def harem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle harem pagination"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "page_info":
        return
    
    page = int(query.data.split("_")[1])
    user_id = query.from_user.id
    user = get_user(user_id)
    
    cards_per_page = 5
    all_cards = user["harem"]
    total_pages = (len(all_cards) + cards_per_page - 1) // cards_per_page
    
    start_idx = page * cards_per_page
    end_idx = min(start_idx + cards_per_page, len(all_cards))
    
    # Build message
    message = f"🎴 **{query.from_user.first_name} ရဲ့ Collection**\n\n"
    message += f"💎 Total Cards: {len(all_cards)}\n\n"
    
    for card in all_cards[start_idx:end_idx]:
        rarity_emoji = RARITIES[card["rarity"]]["emoji"]
        movie_cards = [c for c in all_cards if c["movie"] == card["movie"]]
        total_movie_cards = len([c for c in data["cards"] if c["movie"] == card["movie"]])
        
        message += (
            f"{rarity_emoji} **{card['name']}**\n"
            f"🎬 {card['movie']} (own: {len(movie_cards)}/{total_movie_cards})\n"
            f"🆔 `{card['id']}`\n\n"
        )
    
    # Pagination buttons
    keyboard = []
    nav_buttons = []
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"harem_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="page_info"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"harem_{page+1}"))
    
    keyboard.append(nav_buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message += f"\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== SET FAVORITE CARD =====================
async def set_fav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set favorite card"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not context.args:
        await update.message.reply_text(
            "❌ Card ID ထည့်ပါ!\n"
            "ဥပမာ: `/set card123`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    card_id = context.args[0]
    
    # Find card in user's harem
    card = next((c for c in user["harem"] if c["id"] == card_id), None)
    
    if not card:
        await update.message.reply_text("❌ သင့် harem မှာ ဒီ card မရှိပါဘူး!")
        return
    
    user["fav_card"] = card_id
    save_data(data)
    
    rarity_emoji = RARITIES[card["rarity"]]["emoji"]
    await update.message.reply_text(
        f"⭐ **Favorite Card သတ်မှတ်ပြီးပါပြီ!**\n\n"
        f"{rarity_emoji} **{card['name']}**\n"
        f"🎬 {card['movie']}",
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== SLOTS GAME =====================
async def slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Slot machine game"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "❌ Bet ပမာဏထည့်ပါ!\n"
            "ဥပမာ: `/slots 1000`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    bet = int(context.args[0])
    
    if bet < 100:
        await update.message.reply_text("❌ အနည်းဆုံး 100 coins bet ထားရပါမယ်!")
        return
    
    if user["coins"] < bet:
        await update.message.reply_text(
            f"❌ Coins မလောက်ပါဘူး!\n"
            f"💰 လက်ကျန်: {user['coins']} coins"
        )
        return
    
    # Slot symbols
    symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎"]
    result = [random.choice(symbols) for _ in range(3)]
    
    # Check win
    multiplier = 0
    if result[0] == result[1] == result[2]:
        if result[0] == "💎":
            multiplier = 3
        else:
            multiplier = 2
    
    # Calculate winnings
    if multiplier > 0:
        winnings = bet * multiplier
        user["coins"] += winnings
        message = (
            f"🎰 **SLOT MACHINE** 🎰\n\n"
            f"{''.join(result)}\n\n"
            f"🎉 **သင်နိုင်ပါတယ်!**\n"
            f"💰 +{winnings} coins (×{multiplier})\n"
            f"💵 လက်ကျန်: {user['coins']} coins"
        )
    else:
        user["coins"] -= bet
        message = (
            f"🎰 **SLOT MACHINE** 🎰\n\n"
            f"{''.join(result)}\n\n"
            f"😢 **သင်ရှုံးပါတယ်!**\n"
            f"💸 -{bet} coins\n"
            f"💵 လက်ကျန်: {user['coins']} coins"
        )
    
    save_data(data)
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

# ===================== BASKETBALL GAME =====================
async def basket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Basketball game"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "❌ Bet ပမာဏထည့်ပါ!\n"
            "ဥပမာ: `/basket 1000`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    bet = int(context.args[0])
    
    if bet < 100:
        await update.message.reply_text("❌ အနည်းဆုံး 100 coins bet ထားရပါမယ်!")
        return
    
    if user["coins"] < bet:
        await update.message.reply_text(
            f"❌ Coins မလောက်ပါဘူး!\n"
            f"💰 လက်ကျန်: {user['coins']} coins"
        )
        return
    
    # Send basketball animation
    dice = await update.message.reply_dice(emoji="🏀")
    
    # Wait for animation
    await asyncio.sleep(4)
    
    # Check result (4-5 = win)
    if dice.dice.value in [4, 5]:
        multiplier = 3 if dice.dice.value == 5 else 2
        winnings = bet * multiplier
        user["coins"] += winnings
        message = (
            f"🏀 **BASKETBALL GAME** 🏀\n\n"
            f"🎯 **ဝင်ပါတယ်!**\n"
            f"💰 +{winnings} coins (×{multiplier})\n"
            f"💵 လက်ကျန်: {user['coins']} coins"
        )
    else:
        user["coins"] -= bet
        message = (
            f"🏀 **BASKETBALL GAME** 🏀\n\n"
            f"😢 **လွဲသွားပါတယ်!**\n"
            f"💸 -{bet} coins\n"
            f"💵 လက်ကျန်: {user['coins']} coins"
        )
    
    save_data(data)
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

# ===================== GIVE COIN =====================
async def givecoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transfer coins to another user"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Get target user
    target_user_id = None
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
    elif context.args and context.args[0].isdigit():
        target_user_id = int(context.args[0])
        context.args.pop(0)
    
    if not target_user_id or not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "❌ အသုံးပြုနည်း:\n"
            "Reply လုပ်ပြီး: `/givecoin <amount>`\n"
            "သို့မဟုတ်: `/givecoin <user_id> <amount>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    amount = int(context.args[0])
    
    if amount < 1:
        await update.message.reply_text("❌ အနည်းဆုံး 1 coin ပို့ရပါမယ်!")
        return
    
    if user["coins"] < amount:
        await update.message.reply_text(
            f"❌ Coins မလောက်ပါဘူး!\n"
            f"💰 လက်ကျန်: {user['coins']} coins"
        )
        return
    
    if target_user_id == user_id:
        await update.message.reply_text("❌ မိမိကိုယ်ကို coins မပို့နိုင်ပါဘူး!")
        return
    
    # Transfer coins
    target_user = get_user(target_user_id)
    user["coins"] -= amount
    target_user["coins"] += amount
    save_data(data)
    
    await update.message.reply_text(
        f"✅ **အောင်မြင်ပါတယ်!**\n\n"
        f"💸 {amount} coins ပို့ပြီးပါပြီ!\n"
        f"💰 သင့်လက်ကျန်: {user['coins']} coins",
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== BALANCE =====================
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user balance"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    await update.message.reply_text(
        f"💰 **{update.effective_user.first_name} ရဲ့ Balance**\n\n"
        f"💵 Coins: **{user['coins']:,}**\n"
        f"🎴 Cards: **{len(user['harem'])}**",
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== DAILY BONUS =====================
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Daily bonus"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Check if already claimed today
    last_daily = user.get("last_daily")
    if last_daily:
        last_dt = datetime.fromisoformat(last_daily)
        if datetime.now().date() == last_dt.date():
            next_time = (last_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0)
            remaining = next_time - datetime.now()
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            
            await update.message.reply_text(
                f"⏰ နေ့စဉ်ဆုလာဘ် ယူပြီးပါပြီ!\n"
                f"⏳ နောက်တစ်ခါယူရန် {hours}နာရီ {minutes}မိနစ်ကျန်ပါသေးတယ်။"
            )
            return
    
    # Give random bonus
    bonus = random.randint(5000, 50000)
    user["coins"] += bonus
    user["last_daily"] = datetime.now().isoformat()
    save_data(data)
    
    await update.message.reply_text(
        f"🎁 **နေ့စဉ်ဆုလာဘ်!**\n\n"
        f"💰 +{bonus:,} coins\n"
        f"💵 လက်ကျန်: {user['coins']:,} coins\n\n"
        f"🔄 နောက်တစ်ခါ 24 နာရီအကြာယူနိုင်ပါမယ်!",
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== SHOP =====================
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Card shop"""
    if not data["cards"]:
        await update.message.reply_text("❌ ဆိုင်မှာ card များမရှိသေးပါဘူး!")
        return
    
    # Show first card
    card = data["cards"][0]
    rarity_emoji = RARITIES[card["rarity"]]["emoji"]
    price = RARITIES[card["rarity"]]["price"]
    
    message = (
        f"🏪 **CHARACTER SHOP**\n\n"
        f"{rarity_emoji} **{card['name']}**\n"
        f"🎬 {card['movie']}\n"
        f"✨ {card['rarity']}\n"
        f"💰 ဈေးနှုန်း: **{price:,} coins**\n\n"
        f"📦 Card {1}/{len(data['cards'])}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ ဝယ်မယ်", callback_data=f"buy_0"),
            InlineKeyboardButton("➡️ Next", callback_data=f"shop_1")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== SHOP CALLBACK =====================
async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shop navigation and purchase"""
    query = update.callback_query
    await query.answer()
    
    action, idx = query.data.split("_")
    idx = int(idx)
    
    if action == "buy":
        # Purchase card
        user_id = query.from_user.id
        user = get_user(user_id)
        card = data["cards"][idx]
        price = RARITIES[card["rarity"]]["price"]
        
        if user["coins"] < price:
            await query.answer(
                f"❌ Coins မလောက်ပါဘူး! လိုအပ်တာ: {price:,} coins",
                show_alert=True
            )
            return
        
        # Create new card instance with unique ID
        new_card = card.copy()
        new_card["id"] = f"{card['id']}_{random.randint(1000, 9999)}"
        
        user["coins"] -= price
        user["harem"].append(new_card)
        save_data(data)
        
        rarity_emoji = RARITIES[card["rarity"]]["emoji"]
        await query.edit_message_text(
            f"🎉 **ဝယ်ယူမှုအောင်မြင်ပါတယ်!**\n\n"
            f"{rarity_emoji} **{card['name']}**\n"
            f"🎬 {card['movie']}\n"
            f"💸 -{price:,} coins\n"
            f"💰 လက်ကျန်: {user['coins']:,} coins",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    elif action == "shop":
        # Navigate shop
        if idx < 0 or idx >= len(data["cards"]):
            idx = 0
        
        card = data["cards"][idx]
        rarity_emoji = RARITIES[card["rarity"]]["emoji"]
        price = RARITIES[card["rarity"]]["price"]
        
        message = (
            f"🏪 **CHARACTER SHOP**\n\n"
            f"{rarity_emoji} **{card['name']}**\n"
            f"🎬 {card['movie']}\n"
            f"✨ {card['rarity']}\n"
            f"💰 ဈေးနှုန်း: **{price:,} coins**\n\n"
            f"📦 Card {idx+1}/{len(data['cards'])}"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ ဝယ်မယ်", callback_data=f"buy_{idx}"),
                InlineKeyboardButton("➡️ Next", callback_data=f"shop_{(idx+1)%len(data['cards'])}")
            ]
        ]
        
        if idx > 0:
            keyboard[0].insert(0, InlineKeyboardButton("⬅️ Prev", callback_data=f"shop_{idx-1}"))
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

# ===================== TOPS =====================
async def tops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top 10 leaderboard"""
    keyboard = [
        [
            InlineKeyboardButton("💰 Top Coins", callback_data="tops_coins"),
            InlineKeyboardButton("🎴 Top Cards", callback_data="tops_cards")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🏆 **LEADERBOARD**\n\n"
        "ဘာကိုကြည့်ချင်ပါသလဲ?",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== TOPS CALLBACK =====================
async def tops_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle leaderboard display"""
    query = update.callback_query
    await query.answer()
    
    top_type = query.data.split("_")[1]
    
    # Sort users
    if top_type == "coins":
        sorted_users = sorted(
            data["users"].items(),
            key=lambda x: x[1]["coins"],
            reverse=True
        )[:10]
        title = "💰 **TOP 10 - RICHEST PLAYERS**"
        value_key = "coins"
        emoji = "💵"
    else:
        sorted_users = sorted(
            data["users"].items(),
            key=lambda x: len(x[1]["harem"]),
            reverse=True
        )[:10]
        title = "🎴 **TOP 10 - CARD COLLECTORS**"
        value_key = "harem"
        emoji = "🎴"
    
    message = f"{title}\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, (user_id, user_data) in enumerate(sorted_users):
        try:
            user = await context.bot.get_chat(int(user_id))
            name = user.first_name
        except:
            name = "Unknown User"
        
        medal = medals[i] if i < 3 else f"{i+1}."
        value = user_data[value_key] if value_key == "coins" else len(user_data[value_key])
        
        if value_key == "coins":
            message += f"{medal} **{name}** - {emoji} {value:,}\n"
        else:
            message += f"{medal} **{name}** - {emoji} {value}\n"
    
    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== MESSAGE COUNTER (for card drops) =====================
async def message_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Count messages for card drops"""
    if update.effective_chat.type == "private":
        return
    
    chat_id = str(update.effective_chat.id)
    
    # Initialize counter
    if chat_id not in data["group_messages"]:
        data["group_messages"][chat_id] = 0
    
    data["group_messages"][chat_id] += 1
    
    # Check if should drop card
    if data["group_messages"][chat_id] >= data["drop_count"]:
        data["group_messages"][chat_id] = 0
        
        if data["cards"]:
            # Drop random card
            card = random.choice(data["cards"]).copy()
            card["id"] = f"{card['id']}_{random.randint(1000, 9999)}"
            
            # Store dropped card
            if "dropped_cards" not in data:
                data["dropped_cards"] = {}
            data["dropped_cards"][chat_id] = card
            
            save_data(data)
            
            rarity_emoji = RARITIES[card["rarity"]]["emoji"]
            
            # Send card with blurred name
            await update.message.reply_text(
                f"🎴 **CARD DROP!**\n\n"
                f"{rarity_emoji} **{'█' * len(card['name'])}**\n"
                f"🎬 {card['movie']}\n"
                f"✨ {card['rarity']}\n\n"
                f"💡 `/slime <character name>` နဲ့ယူပါ!\n"
                f"⏰ 10 seconds cooldown",
                parse_mode=ParseMode.MARKDOWN
            )

# ===================== ADMIN COMMANDS =====================

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Upload new card (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS and user_id not in data["sudos"]:
        await update.message.reply_text("❌ သင့်မှာ ခွင့်ပြုချက်မရှိပါဘူး!")
        return
    
    # Check if replying to photo with caption
    if update.message.reply_to_message and update.message.reply_to_message.photo:
        caption = update.message.reply_to_message.caption
        photo = update.message.reply_to_message.photo[-1].file_id
    elif update.message.photo and update.message.caption:
        caption = update.message.caption
        photo = update.message.photo[-1].file_id
    else:
        await update.message.reply_text(
            "❌ အသုံးပြုနည်း:\n"
            "Photo နဲ့ caption ပေးပို့ပါ:\n"
            "`Character Name | Movie Name | Rarity`\n\n"
            "ဥပမာ: `Luffy | One Piece | Legendary`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Parse caption
    try:
        parts = [p.strip() for p in caption.split("|")]
        if len(parts) != 3:
            raise ValueError
        
        char_name, movie_name, rarity = parts
        
        if rarity not in RARITIES:
            await update.message.reply_text(
                f"❌ Rarity မှားနေပါတယ်!\n"
                f"ရွေးချယ်နိုင်တာများ: {', '.join(RARITIES.keys())}"
            )
            return
        
        # Create card
        card_id = f"card_{len(data['cards']) + 1}"
        card = {
            "id": card_id,
            "name": char_name,
            "movie": movie_name,
            "rarity": rarity,
            "photo": photo
        }
        
        data["cards"].append(card)
        save_data(data)
        
        rarity_emoji = RARITIES[rarity]["emoji"]
        await update.message.reply_text(
            f"✅ **Card တင်ပြီးပါပြီ!**\n\n"
            f"{rarity_emoji} **{char_name}**\n"
            f"🎬 {movie_name}\n"
            f"🆔 `{card_id}`\n"
            f"✨ {rarity}",
            parse_mode=ParseMode.MARKDOWN
        )
        
    except:
        await update.message.reply_text(
            "❌ Format မှားနေပါတယ်!\n"
            "အသုံးပြုနည်း: `Character Name | Movie Name | Rarity`",
            parse_mode=ParseMode.MARKDOWN
        )

async def setdrop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set card drop message count (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "❌ အသုံးပြုနည်း: `/setdrop <number>`\n"
            "ဥပမာ: `/setdrop 10`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    count = int(context.args[0])
    
    if count < 1:
        await update.message.reply_text("❌ အနည်းဆုံး 1 ဖြစ်ရပါမယ်!")
        return
    
    data["drop_count"] = count
    save_data(data)
    
    await update.message.reply_text(
        f"✅ Card drop count ကို **{count}** messages သတ်မှတ်ပြီးပါပြီ!",
        parse_mode=ParseMode.MARKDOWN
    )

async def gift_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gift coins to user (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    # Get target user
    target_user_id = None
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        args = context.args
    elif len(context.args) >= 2:
        target_user_id = int(context.args[1])
        args = [context.args[0]]
    else:
        await update.message.reply_text(
            "❌ အသုံးပြုနည်း:\n"
            "Reply: `/gift coin <amount>`\n"
            "သို့: `/gift coin <amount> <user_id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    amount = int(args[0])
    target_user = get_user(target_user_id)
    target_user["coins"] += amount
    save_data(data)
    
    await update.message.reply_text(
        f"✅ **{amount:,} coins ပေးပြီးပါပြီ!**\n"
        f"👤 User ID: `{target_user_id}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def gift_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gift random cards to user (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    if not data["cards"]:
        await update.message.reply_text("❌ Card များမရှိသေးပါဘူး!")
        return
    
    # Get target user
    target_user_id = None
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        args = context.args
    elif len(context.args) >= 2:
        target_user_id = int(context.args[1])
        args = [context.args[0]]
    else:
        await update.message.reply_text(
            "❌ အသုံးပြုနည်း:\n"
            "Reply: `/gift card <amount>`\n"
            "သို့: `/gift card <amount> <user_id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    amount = int(args[0])
    target_user = get_user(target_user_id)
    
    # Give random cards
    for _ in range(amount):
        card = random.choice(data["cards"]).copy()
        card["id"] = f"{card['id']}_{random.randint(1000, 9999)}"
        target_user["harem"].append(card)
    
    save_data(data)
    
    await update.message.reply_text(
        f"✅ **{amount} random cards ပေးပြီးပါပြီ!**\n"
        f"👤 User ID: `{target_user_id}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def edit_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin commands (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    admin_commands = """
🔧 **ADMIN COMMANDS**

📤 `/upload` - Card အသစ်တင်ရန်
⚙️ `/setdrop <number>` - Card drop count သတ်မှတ်ရန်
💰 `/gift coin <amount> <user>` - Coins ပေးရန်
🎴 `/gift card <amount> <user>` - Cards ပေးရန်
📢 `/broadcast` - Message ပို့ရန်
📊 `/stats` - Statistics ကြည့်ရန်
💾 `/backup` - Data backup လုပ်ရန်
♻️ `/restore` - Data ပြန်ယူရန်
🗑️ `/allclear` - Data အားလုံးဖျက်ရန်
❌ `/delete <card_id>` - Card ဖျက်ရန်
👑 `/addsudo <user>` - Sudo ထည့်ရန်
📋 `/sudolist` - Sudo list ကြည့်ရန်
🗳️ `/evote` - Vote စတင်ရန်

━━━━━━━━━━━━━━━━
Create by : @Enoch_777
    """
    
    await update.message.reply_text(admin_commands, parse_mode=ParseMode.MARKDOWN)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all groups (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Message ထည့်ပါ!\n"
            "အသုံးပြုနည်း: `/broadcast <message>`\n"
            "သို့မဟုတ် message ကို reply လုပ်ပါ",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Get broadcast message
    if update.message.reply_to_message:
        broadcast_msg = update.message.reply_to_message
    else:
        text = " ".join(context.args)
        broadcast_msg = await update.message.reply_text(text)
    
    # Send to all groups
    success = 0
    failed = 0
    
    for group_id in data["groups"]:
        try:
            if broadcast_msg.photo:
                await context.bot.send_photo(
                    chat_id=int(group_id),
                    photo=broadcast_msg.photo[-1].file_id,
                    caption=broadcast_msg.caption
                )
            else:
                await context.bot.send_message(
                    chat_id=int(group_id),
                    text=broadcast_msg.text
                )
            success += 1
        except:
            failed += 1
    
    await update.message.reply_text(
        f"📢 **Broadcast ပြီးပါပြီ!**\n\n"
        f"✅ အောင်မြင်: {success}\n"
        f"❌ မအောင်မြင်: {failed}",
        parse_mode=ParseMode.MARKDOWN
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    total_users = len(data["users"])
    total_groups = len(data["groups"])
    total_cards = len(data["cards"])
    
    stats_text = f"""
📊 **BOT STATISTICS**

👥 Total Users: **{total_users}**
👥 Total Groups: **{total_groups}**
🎴 Total Cards: **{total_cards}**
👑 Sudos: **{len(data["sudos"])}**

━━━━━━━━━━━━━━━━
Create by : @Enoch_777
    """
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Backup bot data (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    # Send backup file
    with open(DATA_FILE, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            caption="💾 **Data Backup**\n\nBackup ပြီးပါပြီ!",
            parse_mode=ParseMode.MARKDOWN
        )

async def restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restore bot data (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text(
            "❌ Backup file ကို reply လုပ်ပါ!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Download and restore file
    file = await update.message.reply_to_message.document.get_file()
    await file.download_to_drive(DATA_FILE)
    
    global data
    data = load_data()
    
    await update.message.reply_text(
        "♻️ **Data Restore**\n\nပြန်ယူပြီးပါပြီ!",
        parse_mode=ParseMode.MARKDOWN
    )

async def allclear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all data (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ အတည်ပြုပါတယ်", callback_data="confirm_clear"),
            InlineKeyboardButton("❌ ပယ်ဖျက်မယ်", callback_data="cancel_clear")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚠️ **သတိပြုပါ!**\n\n"
        "Data အားလုံး ဖျက်မှာသေချာပါသလား?\n"
        "ဒီလုပ်ငန်းကို ပြန်ပြင်လို့မရပါဘူး!",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def allclear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle allclear confirmation"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_clear":
        global data
        data = {
            "users": {},
            "groups": {},
            "cards": [],
            "sudos": [],
            "drop_count": 10,
            "group_messages": {},
            "vote_options": [],
            "votes": {}
        }
        save_data(data)
        
        await query.edit_message_text(
            "🗑️ **Data အားလုံး ဖျက်ပြီးပါပြီ!**",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.edit_message_text(
            "❌ ပယ်ဖျက်ပါတယ်။",
            parse_mode=ParseMode.MARKDOWN
        )

async def delete_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a card (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Card ID ထည့်ပါ!\n"
            "အသုံးပြုနည်း: `/delete <card_id>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    card_id = context.args[0]
    
    # Find and remove card
    card = next((c for c in data["cards"] if c["id"] == card_id), None)
    
    if not card:
        await update.message.reply_text("❌ ဒီ Card ID မရှိပါဘူး!")
        return
    
    data["cards"].remove(card)
    save_data(data)
    
    await update.message.reply_text(
        f"✅ **Card ဖျက်ပြီးပါပြီ!**\n"
        f"🆔 `{card_id}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def addsudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add sudo user (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    # Get target user
    target_user_id = None
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
    elif context.args and context.args[0].isdigit():
        target_user_id = int(context.args[0])
    else:
        await update.message.reply_text(
            "❌ User ID ထည့်ပါ သို့မဟုတ် reply လုပ်ပါ!",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if target_user_id in data["sudos"]:
        await update.message.reply_text("❌ ဒီ user က sudo ဖြစ်နေပြီးပါပြီ!")
        return
    
    data["sudos"].append(target_user_id)
    save_data(data)
    
    await update.message.reply_text(
        f"✅ **Sudo ထည့်ပြီးပါပြီ!**\n"
        f"👤 User ID: `{target_user_id}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def sudolist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show sudo list (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    if not data["sudos"]:
        await update.message.reply_text("📋 Sudo list ထဲမှာ ဘယ်သူမှမရှိသေးပါဘူး!")
        return
    
    message = "👑 **SUDO LIST**\n\n"
    
    for i, sudo_id in enumerate(data["sudos"], 1):
        try:
            user = await context.bot.get_chat(sudo_id)
            name = user.first_name
        except:
            name = "Unknown User"
        
        message += f"{i}. **{name}** (`{sudo_id}`)\n"
    
    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def evote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create vote poll (Admin only)"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Admin ဖြစ်မှသာ အသုံးပြုနိုင်ပါတယ်!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ ရွေးချယ်စရာများထည့်ပါ!\n"
            "ဥပမာ: `/evote Luffy, Naruto, Goku`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Parse options
    options_text = " ".join(context.args)
    options = [opt.strip() for opt in options_text.split(",")]
    
    if len(options) < 2:
        await update.message.reply_text("❌ အနည်းဆုံး 2 ခုထည့်ရပါမယ်!")
        return
    
    # Create vote
    data["vote_options"] = options
    data["votes"] = {opt: [] for opt in options}
    save_data(data)
    
    # Create buttons
    keyboard = []
    for opt in options:
        keyboard.append([InlineKeyboardButton(f"🗳️ {opt}", callback_data=f"vote_{opt}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🗳️ **VOTING POLL**\n\n"
        "သင်ကြိုက်နှစ်သက်တဲ့သူကို ရွေးချယ်ပါ!",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current vote results"""
    if not data["vote_options"]:
        await update.message.reply_text("❌ Vote မရှိသေးပါဘူး!")
        return
    
    message = "🗳️ **VOTE RESULTS**\n\n"
    
    for option in data["vote_options"]:
        votes = len(data["votes"].get(option, []))
        message += f"• **{option}**: {votes} votes\n"
    
    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    
    # Create buttons
    keyboard = []
    for opt in data["vote_options"]:
        keyboard.append([InlineKeyboardButton(f"🗳️ {opt}", callback_data=f"vote_{opt}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voting"""
    query = update.callback_query
    
    option = query.data.replace("vote_", "")
    user_id = query.from_user.id
    
    # Check if already voted
    for opt, voters in data["votes"].items():
        if user_id in voters:
            # Remove old vote
            data["votes"][opt].remove(user_id)
    
    # Add new vote
    if option not in data["votes"]:
        data["votes"][option] = []
    
    data["votes"][option].append(user_id)
    save_data(data)
    
    await query.answer(f"✅ {option} ကိုမဲပေးပြီးပါပြီ!", show_alert=True)
    
    # Update message with results
    message = "🗳️ **VOTE RESULTS**\n\n"
    
    for opt in data["vote_options"]:
        votes = len(data["votes"].get(opt, []))
        message += f"• **{opt}**: {votes} votes\n"
    
    message += "\n━━━━━━━━━━━━━━━━\nCreate by : @Enoch_777"
    
    # Create buttons
    keyboard = []
    for opt in data["vote_options"]:
        keyboard.append([InlineKeyboardButton(f"🗳️ {opt}", callback_data=f"vote_{opt}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

# ===================== GROUP TRACKING =====================
async def track_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track groups bot is added to"""
    chat = update.effective_chat
    
    if chat.type in ["group", "supergroup"]:
        chat_id = str(chat.id)
        if chat_id not in data["groups"]:
            data["groups"][chat_id] = {
                "name": chat.title,
                "joined": datetime.now().isoformat()
            }
            save_data(data)

# ===================== ERROR HANDLER =====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

# ===================== MAIN =====================
def main():
    """Start the bot"""
    print("🤖 Bot စတင်နေပါသည်...")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("slime", slime))
    application.add_handler(CommandHandler("harem", harem))
    application.add_handler(CommandHandler("set", set_fav))
    application.add_handler(CommandHandler("slots", slots))
    application.add_handler(CommandHandler("basket", basket))
    application.add_handler(CommandHandler("givecoin", givecoin))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("shop", shop))
    application.add_handler(CommandHandler("tops", tops))
    
    # Admin commands
    application.add_handler(CommandHandler("upload", upload))
    application.add_handler(CommandHandler("setdrop", setdrop))
    application.add_handler(CommandHandler("gift", gift_coin))
    application.add_handler(CommandHandler("edit", edit_admin))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("backup", backup))
    application.add_handler(CommandHandler("restore", restore))
    application.add_handler(CommandHandler("allclear", allclear))
    application.add_handler(CommandHandler("delete", delete_card))
    application.add_handler(CommandHandler("addsudo", addsudo))
    application.add_handler(CommandHandler("sudolist", sudolist))
    application.add_handler(CommandHandler("evote", evote))
    application.add_handler(CommandHandler("vote", vote))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(harem_callback, pattern="^harem_"))
    application.add_handler(CallbackQueryHandler(shop_callback, pattern="^(shop_|buy_)"))
    application.add_handler(CallbackQueryHandler(tops_callback, pattern="^tops_"))
    application.add_handler(CallbackQueryHandler(allclear_callback, pattern="^(confirm_|cancel_)clear"))
    application.add_handler(CallbackQueryHandler(vote_callback, pattern="^vote_"))
    
    # Message handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        message_counter
    ))
    
    # Group tracking
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        track_groups
    ))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    # Start bot
    print("✅ Bot စတင်ပြီးပါပြီ!")
    print("━━━━━━━━━━━━━━━━")
    print("Create by : @Enoch_777")
    print("━━━━━━━━━━━━━━━━")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
