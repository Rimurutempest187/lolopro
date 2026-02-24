#!/usr/bin/env python3
# coding: utf-8
# Single-file Telegram bot (run-ready)

import os, json, random, logging, asyncio
from datetime import datetime, timedelta
from html import escape
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
DATA_FILE = os.getenv("DATA_FILE", "bot_data.json")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    level=logging.DEBUG if DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

data_lock = asyncio.Lock()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except Exception:
            obj = {}
    else:
        obj = {}
    defaults = {
        "users": {}, "groups": {}, "cards": [], "sudos": [],
        "drop_count": int(os.getenv("DROP_COUNT", 10)),
        "group_messages": {}, "vote_options": [], "votes": {}, "dropped_cards": {}
    }
    for k, v in defaults.items():
        obj.setdefault(k, v)
    obj["sudos"] = [int(x) for x in obj.get("sudos", []) if str(x).isdigit()]
    return obj

data = load_data()

async def save_data_safe():
    async with data_lock:
        tmp = DATA_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception:
            logger.exception("save failed")
            if os.path.exists(tmp): os.remove(tmp)

RARITIES = {
    "Common": {"emoji": "🟤", "price": 5000},
    "Rare": {"emoji": "🟡", "price": 15000},
    "Epic": {"emoji": "🔮", "price": 35000},
    "Legendary": {"emoji": "⚡", "price": 75000},
    "Mythic": {"emoji": "👑", "price": 150000},
}

def uid_str(uid): return str(int(uid))
def get_user(uid):
    k = uid_str(uid)
    if k not in data["users"]:
        data["users"][k] = {"coins": 10000, "harem": [], "fav_card": None, "last_daily": None, "last_slime": None}
    return data["users"][k]
def is_admin(uid):
    try:
        return int(uid) in ADMIN_IDS or int(uid) in [int(x) for x in data.get("sudos", [])]
    except Exception:
        return False
def safe(s): return escape(str(s))
def check_cooldown(uid, action, cd):
    user = get_user(uid)
    lt = user.get(f"last_{action}")
    if lt:
        try:
            last = datetime.fromisoformat(lt)
            rem = cd - (datetime.now() - last).total_seconds()
            if rem > 0: return False, int(rem)
        except Exception:
            pass
    return True, 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    get_user(u.id)
    await save_data_safe()
    txt = (f"👋 <b>ကြိုဆိုပါတယ် {safe(u.first_name)}!</b>\n\n"
           "Commands: /slime /harem /shop /daily /slots /basket /givecoin /balance")
    if update.message: await update.message.reply_text(txt, parse_mode=ParseMode.HTML)

async def slime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    uid = update.effective_user.id
    ok, rem = check_cooldown(uid, "slime", 10)
    if not ok:
        await update.message.reply_text(f"⏰ ခဏစောင့်ပါ! {rem} စက္ကန့်ကျန်")
        return
    cid = str(update.effective_chat.id)
    dropped = data.get("dropped_cards", {})
    if cid not in dropped:
        await update.message.reply_text("❌ card ကျထားမှု မရှိပါ")
        return
    card = dropped[cid]
    if not context.args:
        await update.message.reply_text("❌ အမည်ရေးပါ: /slime <name>")
        return
    guess = " ".join(context.args).strip()
    if guess.lower() != card["name"].lower():
        await update.message.reply_text("❌ မှားတယ်")
        return
    user = get_user(uid)
    new = card.copy()
    new["id"] = f"{card['id']}_{random.randint(1000,9999)}"
    user["harem"].append(new)
    user["last_slime"] = datetime.now().isoformat()
    data["dropped_cards"].pop(cid, None)
    await save_data_safe()
    await update.message.reply_text(
        f"🎉 <b>ရရှိပါပြီ {safe(update.effective_user.first_name)}!</b>\n{RARITIES[card['rarity']]['emoji']} <b>{safe(card['name'])}</b>",
        parse_mode=ParseMode.HTML)

async def harem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user = get_user(update.effective_user.id)
    if not user["harem"]:
        await update.message.reply_text("📭 ကဒ် မရှိသေးပါ")
        return
    page = 0
    if context.args and context.args[0].isdigit(): page = max(0, int(context.args[0])-1)
    per = 5
    total = (len(user["harem"]) + per - 1)//per
    page = min(max(page,0), max(total-1,0))
    s = page*per; e = min(s+per, len(user["harem"]))
    msg = f"🎴 <b>{safe(update.effective_user.first_name)}'s Collection</b>\n\nTotal: {len(user['harem'])}\n\n"
    for c in user["harem"][s:e]:
        msg += f"{RARITIES[c['rarity']]['emoji']} <b>{safe(c['name'])}</b>\n🎬 {safe(c['movie'])}\n🆔 <code>{safe(c['id'])}</code>\n\n"
    kb = []
    nav = []
    if page>0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"harem_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total}", callback_data="page_info"))
    if page<total-1: nav.append(InlineKeyboardButton("➡️", callback_data=f"harem_{page+1}"))
    kb.append(nav)
    await update.message.reply_text(msg + "\nCreate by : @Enoch_777", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def harem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data=="page_info": return
    try: page = int(q.data.split("_")[1])
    except: page = 0
    uid = q.from_user.id; user = get_user(uid)
    per=5; total=(len(user["harem"])+per-1)//per or 1
    page = min(max(page,0), max(total-1,0))
    s=page*per; e=min(s+per, len(user["harem"]))
    msg = f"🎴 <b>{safe(q.from_user.first_name)}'s Collection</b>\n\nTotal: {len(user['harem'])}\n\n"
    for c in user["harem"][s:e]:
        msg += f"{RARITIES[c['rarity']]['emoji']} <b>{safe(c['name'])}</b>\n🎬 {safe(c['movie'])}\n🆔 <code>{safe(c['id'])}</code>\n\n"
    kb=[]; nav=[]
    if page>0: nav.append(InlineKeyboardButton("⬅️", callback_data=f"harem_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total}", callback_data="page_info"))
    if page<total-1: nav.append(InlineKeyboardButton("➡️", callback_data=f"harem_{page+1}"))
    kb.append(nav)
    await q.edit_message_text(msg + "\nCreate by : @Enoch_777", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def set_fav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user = get_user(update.effective_user.id)
    if not context.args: 
        await update.message.reply_text("❌ /set <card_id>")
        return
    cid = context.args[0]
    if not any(c.get("id")==cid for c in user["harem"]):
        await update.message.reply_text("❌ မရှိပါ")
        return
    user["fav_card"]=cid
    await save_data_safe()
    await update.message.reply_text("⭐ Favorite set", parse_mode=ParseMode.HTML)

async def slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user = get_user(update.effective_user.id)
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("❌ /slots <amount>")
        return
    bet=int(context.args[0])
    if bet<100 or user["coins"]<bet:
        await update.message.reply_text("❌ Invalid bet or insufficient coins")
        return
    user["coins"] -= bet
    symbols=["🍒","🍋","🍊","🍇","⭐","💎"]
    res=[random.choice(symbols) for _ in range(3)]
    mult=3 if res[0]==res[1]==res[2]=="💎" else (2 if res[0]==res[1]==res[2] else 0)
    if mult>0:
        winnings=bet*mult; user["coins"]+=winnings
        msg=f"🎰 {''.join(res)}\n🎉 +{winnings} (×{mult})\n💵 {user['coins']}"
    else:
        msg=f"🎰 {''.join(res)}\n😢 -{bet}\n💵 {user['coins']}"
    await save_data_safe(); await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def basket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    user=get_user(update.effective_user.id)
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("❌ /basket <amount>"); return
    bet=int(context.args[0])
    if bet<100 or user["coins"]<bet: await update.message.reply_text("❌ Invalid bet or insufficient"); return
    user["coins"]-=bet
    dice = await update.message.reply_dice(emoji="🏀")
    await asyncio.sleep(1.2)
    try: val=dice.dice.value
    except: val=random.randint(1,6)
    if val in [4,5]:
        mult = 3 if val==5 else 2
        win=bet*mult; user["coins"]+=win
        msg=f"🏀 Win +{win} (×{mult})\n💵 {user['coins']}"
    else:
        msg=f"🏀 Miss -{bet}\n💵 {user['coins']}"
    await save_data_safe(); await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def givecoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    sender=get_user(update.effective_user.id)
    target=None; amount=None
    if update.message.reply_to_message:
        target=update.message.reply_to_message.from_user.id
        amount=int(context.args[0]) if context.args and context.args[0].isdigit() else None
    else:
        if len(context.args)>=2 and context.args[0].isdigit() and context.args[1].isdigit():
            target=int(context.args[0]); amount=int(context.args[1])
    if not target or amount is None or amount<1 or sender["coins"]<amount:
        await update.message.reply_text("❌ Usage/Insufficient")
        return
    if int(target)==int(update.effective_user.id): await update.message.reply_text("❌ Cannot send to self"); return
    recv=get_user(target); sender["coins"]-=amount; recv["coins"]+=amount
    await save_data_safe(); await update.message.reply_text("✅ Sent", parse_mode=ParseMode.HTML)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u=get_user(update.effective_user.id)
    await update.message.reply_text(f"💵 Coins: <b>{u['coins']:,}</b>\n🎴 Cards: <b>{len(u['harem'])}</b>", parse_mode=ParseMode.HTML)

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u=get_user(update.effective_user.id)
    last=u.get("last_daily")
    if last:
        try:
            ld=datetime.fromisoformat(last)
            if datetime.now().date()==ld.date():
                await update.message.reply_text("⏰ Daily already claimed"); return
        except: pass
    bonus=random.randint(5000,50000); u["coins"]+=bonus; u["last_daily"]=datetime.now().isoformat()
    await save_data_safe(); await update.message.reply_text(f"🎁 +{bonus:,} coins", parse_mode=ParseMode.HTML)

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not data.get("cards"): await update.message.reply_text("❌ No cards"); return
    idx=0; card=data["cards"][idx]; price=RARITIES.get(card.get("rarity","Common"),{}).get("price",0)
    msg=(f"🏪 <b>{safe(card['name'])}</b>\n🎬 {safe(card['movie'])}\n✨ {safe(card['rarity'])}\n💰 {price:,} coins")
    kb=[[InlineKeyboardButton("✅ Buy", callback_data=f"buy_{idx}"), InlineKeyboardButton("➡️", callback_data=f"shop_{(idx+1)%len(data['cards'])}")]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    try: action, idx = q.data.split("_"); idx=int(idx)
    except: await q.answer("Invalid"); return
    if action=="buy":
        user=get_user(q.from_user.id)
        if idx<0 or idx>=len(data["cards"]): await q.answer("Not found", show_alert=True); return
        card=data["cards"][idx]; price=RARITIES.get(card.get("rarity","Common"),{}).get("price",0)
        if user["coins"]<price: await q.answer(f"Not enough ({price:,})", show_alert=True); return
        new=card.copy(); new["id"]=f"{card['id']}_{random.randint(1000,9999)}"
        user["coins"]-=price; user["harem"].append(new); await save_data_safe()
        await q.edit_message_text(f"✅ Bought {safe(card['name'])}\n💰 {user['coins']:,}", parse_mode=ParseMode.HTML)
    elif action=="shop":
        if not data.get("cards"): await q.answer("Empty"); return
        idx = idx % len(data["cards"])
        card=data["cards"][idx]; price=RARITIES.get(card.get("rarity","Common"),{}).get("price",0)
        msg=(f"🏪 <b>{safe(card['name'])}</b>\n🎬 {safe(card['movie'])}\n✨ {safe(card['rarity'])}\n💰 {price:,} coins")
        buttons=[InlineKeyboardButton("✅ Buy", callback_data=f"buy_{idx}"), InlineKeyboardButton("➡️", callback_data=f"shop_{(idx+1)%len(data['cards'])}")]
        if idx>0: buttons.insert(0, InlineKeyboardButton("⬅️", callback_data=f"shop_{idx-1}"))
        await q.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([buttons]), parse_mode=ParseMode.HTML)

async def tops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb=[[InlineKeyboardButton("💰 Top Coins", callback_data="tops_coins"), InlineKeyboardButton("🎴 Top Cards", callback_data="tops_cards")]]
    await update.message.reply_text("🏆 Choose", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def tops_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    typ = q.data.split("_")[1] if "_" in q.data else "coins"
    if typ=="coins":
        sorted_users = sorted(data["users"].items(), key=lambda x: x[1].get("coins",0), reverse=True)[:10]
        msg="💰 TOP COINS\n"
        for i,(uid,u) in enumerate(sorted_users,1):
            try: chat = await context.bot.get_chat(int(uid)); name=chat.first_name
            except: name="Unknown"
            msg+=f"{i}. {safe(name)} - {u.get('coins',0):,}\n"
    else:
        sorted_users = sorted(data["users"].items(), key=lambda x: len(x[1].get("harem",[])), reverse=True)[:10]
        msg="🎴 TOP CARDS\n"
        for i,(uid,u) in enumerate(sorted_users,1):
            try: chat = await context.bot.get_chat(int(uid)); name=chat.first_name
            except: name="Unknown"
            msg+=f"{i}. {safe(name)} - {len(u.get('harem',[]))}\n"
    await q.edit_message_text(msg + "\nCreate by : @Enoch_777", parse_mode=ParseMode.HTML)

async def message_counter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if update.effective_chat.type == "private": return
    cid=str(update.effective_chat.id)
    data["group_messages"].setdefault(cid,0)
    data["group_messages"][cid]+=1
    if data["group_messages"][cid] >= data.get("drop_count",10):
        data["group_messages"][cid]=0
        if data.get("cards"):
            card=random.choice(data["cards"]).copy()
            card["id"]=f"{card['id']}_{random.randint(1000,9999)}"
            data.setdefault("dropped_cards", {})[cid]=card
            await save_data_safe()
            masked="█"*len(card.get("name",""))
            await update.message.reply_text(f"🎴 CARD DROP!\n{RARITIES.get(card.get('rarity','Common'))['emoji']} {masked}\n/ slime <name>", parse_mode=ParseMode.HTML)

# Admin subset (upload, setdrop, gift, broadcast, stats, backup, restore, allclear, delete, addsudo, sudolist, evote, vote)
async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ No permission"); return
    msg = update.message.reply_to_message or update.message
    caption = msg.caption or update.message.caption
    photo = (msg.photo or update.message.photo or [])
    if not caption or not photo:
        await update.message.reply_text("❌ Reply photo with caption: Name | Movie | Rarity"); return
    parts=[p.strip() for p in caption.split("|",2)]
    if len(parts)!=3: await update.message.reply_text("❌ Format"); return
    name,movie,rarity = parts; rarity=rarity.title()
    if rarity not in RARITIES: await update.message.reply_text("❌ Invalid rarity"); return
    card_id=f"card_{len(data.get('cards',[]))+1}"
    card={"id":card_id,"name":name,"movie":movie,"rarity":rarity,"photo":photo[-1].file_id}
    data["cards"].append(card); await save_data_safe()
    await update.message.reply_text(f"✅ Card added: {safe(name)}", parse_mode=ParseMode.HTML)

async def setdrop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    if not context.args or not context.args[0].isdigit(): await update.message.reply_text("❌ /setdrop <n>"); return
    data["drop_count"]=int(context.args[0]); await save_data_safe(); await update.message.reply_text("✅ drop_count set", parse_mode=ParseMode.HTML)

async def gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    if not context.args: await update.message.reply_text("❌ /gift coin|card <amount> [user_id]"); return
    sub=context.args[0].lower()
    target=None; amount=None
    if update.message.reply_to_message:
        target=update.message.reply_to_message.from_user.id
        if len(context.args)>=2 and context.args[1].isdigit(): amount=int(context.args[1])
    else:
        if len(context.args)>=2 and context.args[1].isdigit(): amount=int(context.args[1])
        if len(context.args)>=3 and context.args[2].isdigit(): target=int(context.args[2])
    if not target or amount is None: await update.message.reply_text("❌ Usage"); return
    if sub=="coin":
        t=get_user(target); t["coins"]+=amount; await save_data_safe(); await update.message.reply_text("✅ coins given", parse_mode=ParseMode.HTML)
    elif sub=="card":
        if not data.get("cards"): await update.message.reply_text("❌ no cards"); return
        t=get_user(target)
        for _ in range(amount):
            c=random.choice(data["cards"]).copy(); c["id"]=f"{c['id']}_{random.randint(1000,9999)}"; t["harem"].append(c)
        await save_data_safe(); await update.message.reply_text("✅ cards given", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ sub must be coin or card")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    if not context.args and not update.message.reply_to_message: await update.message.reply_text("❌ message or reply"); return
    if update.message.reply_to_message:
        msg=update.message.reply_to_message; text=msg.text or msg.caption or ""; photo=(msg.photo and msg.photo[-1].file_id)
    else:
        text=" ".join(context.args); photo=None
    success=failed=0
    for gid in list(data.get("groups",{}).keys()):
        try:
            if photo: await context.bot.send_photo(chat_id=int(gid), photo=photo, caption=text)
            else: await context.bot.send_message(chat_id=int(gid), text=text)
            success+=1
        except: failed+=1
    await update.message.reply_text(f"✅ {success} / ❌ {failed}", parse_mode=ParseMode.HTML)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    await update.message.reply_text(f"Users: {len(data.get('users',{}))}\nGroups: {len(data.get('groups',{}))}\nCards: {len(data.get('cards',[]))}", parse_mode=ParseMode.HTML)

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    await save_data_safe()
    try:
        with open(DATA_FILE, "rb") as f:
            await update.message.reply_document(document=f, filename=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    except: await update.message.reply_text("❌ backup failed")

async def restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    if not update.message.reply_to_message or not update.message.reply_to_message.document: await update.message.reply_text("❌ reply with file"); return
    try:
        doc=update.message.reply_to_message.document; file=await doc.get_file(); await file.download_to_drive(DATA_FILE)
        global data; data=load_data(); await update.message.reply_text("♻️ restored")
    except: await update.message.reply_text("❌ restore failed")

async def allclear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    kb=[[InlineKeyboardButton("✅", callback_data="confirm_clear"), InlineKeyboardButton("❌", callback_data="cancel_clear")]]
    await update.message.reply_text("Confirm clear?", reply_markup=InlineKeyboardMarkup(kb))

async def allclear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="confirm_clear":
        global data; data={"users":{},"groups":{},"cards":[],"sudos":[],"drop_count":int(os.getenv("DROP_COUNT",10)),"group_messages":{},"vote_options":[],"votes":{},"dropped_cards":{}}
        await save_data_safe(); await q.edit_message_text("Cleared")
    else:
        await q.edit_message_text("Cancelled")

async def delete_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    if not context.args: await update.message.reply_text("❌ /delete <card_id>"); return
    cid=context.args[0]; card=next((c for c in data.get("cards",[]) if c.get("id")==cid), None)
    if not card: await update.message.reply_text("❌ not found"); return
    data["cards"].remove(card); await save_data_safe(); await update.message.reply_text("✅ deleted")

async def addsudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    target = update.message.reply_to_message.from_user.id if update.message.reply_to_message else (int(context.args[0]) if context.args and context.args[0].isdigit() else None)
    if not target: await update.message.reply_text("❌ user id"); return
    if int(target) in [int(x) for x in data.get("sudos",[])]: await update.message.reply_text("❌ already sudo"); return
    data.setdefault("sudos",[]).append(int(target)); await save_data_safe(); await update.message.reply_text("✅ sudo added")

async def sudolist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    s="SUDOS:\n"
    for i,uid in enumerate(data.get("sudos",[]),1):
        try: chat=await context.bot.get_chat(int(uid)); name=chat.first_name
        except: name="Unknown"
        s+=f"{i}. {safe(name)} ({uid})\n"
    await update.message.reply_text(s, parse_mode=ParseMode.HTML)

async def evote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not is_admin(update.effective_user.id): await update.message.reply_text("❌ Admin only"); return
    if not context.args: await update.message.reply_text("❌ /evote opt1, opt2"); return
    opts=[o.strip() for o in " ".join(context.args).split(",") if o.strip()]
    if len(opts)<2: await update.message.reply_text("❌ min 2"); return
    data["vote_options"]=opts; data["votes"]={o:[] for o in opts}; await save_data_safe()
    kb=[[InlineKeyboardButton(f"🗳️ {o}", callback_data=f"vote_{o}")] for o in opts]
    await update.message.reply_text("Vote:", reply_markup=InlineKeyboardMarkup(kb))

async def vote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    if not data.get("vote_options"): await update.message.reply_text("❌ no vote"); return
    msg="Results:\n"
    for o in data["vote_options"]: msg+=f"{o}: {len(data['votes'].get(o,[]))}\n"
    kb=[[InlineKeyboardButton(f"🗳️ {o}", callback_data=f"vote_{o}")] for o in data["vote_options"]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))

async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    opt=q.data.replace("vote_",""); uid=q.from_user.id
    for o,voters in data.get("votes",{}).items():
        if uid in voters:
            try: data["votes"][o].remove(uid)
            except: pass
    data.setdefault("votes",{}).setdefault(opt,[]).append(uid)
    await save_data_safe(); await q.answer(f"Voted {opt}", show_alert=True)
    try:
        msg="Results:\n"
        for o in data.get("vote_options",[]): msg+=f"{o}: {len(data['votes'].get(o,[]))}\n"
        kb=[[InlineKeyboardButton(f"🗳️ {o}", callback_data=f"vote_{o}")] for o in data.get("vote_options",[])]
        await q.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))
    except:
        await q.message.reply_text("Updated results")

async def track_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    chat=update.effective_chat
    if chat and chat.type in ["group","supergroup"]:
        cid=str(chat.id)
        if cid not in data.get("groups",{}):
            data["groups"][cid]={"name":chat.title,"joined":datetime.now().isoformat()}
            await save_data_safe()

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Error: %s", context.error)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN missing")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    # user
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("slime", slime))
    app.add_handler(CommandHandler("harem", harem))
    app.add_handler(CallbackQueryHandler(harem_callback, pattern="^harem_"))
    app.add_handler(CommandHandler("set", set_fav))
    app.add_handler(CommandHandler("slots", slots))
    app.add_handler(CommandHandler("basket", basket))
    app.add_handler(CommandHandler("givecoin", givecoin))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CallbackQueryHandler(shop_callback, pattern="^(shop_|buy_)"))
    app.add_handler(CommandHandler("tops", tops))
    app.add_handler(CallbackQueryHandler(tops_callback, pattern="^tops_"))
    # admin
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CommandHandler("setdrop", setdrop))
    app.add_handler(CommandHandler("gift", gift))
    app.add_handler(CommandHandler("edit", edit_admin))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("restore", restore))
    app.add_handler(CommandHandler("allclear", allclear))
    app.add_handler(CallbackQueryHandler(allclear_callback, pattern="^(confirm_|cancel_)clear"))
    app.add_handler(CommandHandler("delete", delete_card))
    app.add_handler(CommandHandler("addsudo", addsudo))
    app.add_handler(CommandHandler("sudolist", sudolist))
    app.add_handler(CommandHandler("evote", evote))
    app.add_handler(CommandHandler("vote", vote))
    app.add_handler(CallbackQueryHandler(vote_callback, pattern="^vote_"))
    # generic
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_counter))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, track_groups))
    app.add_error_handler(error_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
