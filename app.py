import os
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://meesho-bot.onrender.com")

# ================= DATABASE / STATE =================
db = {
    "accounts": [],
    "active_id": None,
    "user_states": {},
    "referral_link": "",
    "addresses": [
        {
            "id": 101,
            "name": "User Demo",
            "mobile": "9876543210",
            "pin": "110001",
            "city": "New Delhi",
            "state": "Delhi",
            "address_line_1": "Connaught Place",
            "address_line_2": "",
            "landmark": "",
            "address_type": "Home",
            "pin_serviceable": True
        }
    ],
    "cart": {"items": [], "total_quantity": 0, "effective_total": 0, "effective_online": 0, "address": None, "price_break_up": []},
    "orders": []
}

# ================= TELEGRAM BOT LOGIC =================
telegram_app = None

def get_main_menu():
    acc_count = len(db["accounts"])
    text = (
        "🛍️ *PRIMES Meesho*\n"
        "_Your personal Meesho shopping concierge_\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ *Service fee* — *FREE (₹0.00)*\n"
        f"👤 *Accounts* · {f'{acc_count} linked' if acc_count > 0 else 'none linked yet — tap ➕ Add Account'}\n\n"
        "Pick an option below to get started 👇"
    )
    keyboard = [
        [InlineKeyboardButton("🛍️ Open Shop", web_app=WebAppInfo(url=WEBAPP_URL))],
        [
            InlineKeyboardButton("➕ Add Account", callback_data="add_account"),
            InlineKeyboardButton("👤 My Accounts", callback_data="my_accounts")
        ],
        [
            InlineKeyboardButton("🔍 Check Number", callback_data="check_number"),
            InlineKeyboardButton("🔗 Set Refer Link", callback_data="set_refer_link")
        ],
        [InlineKeyboardButton("🎁 How Offer Works", callback_data="how_offer_works")],
        [
            InlineKeyboardButton("🗂️ Manage Accounts", web_app=WebAppInfo(url=f"{WEBAPP_URL}#accounts")),
            InlineKeyboardButton("🏷️ Check Price", web_app=WebAppInfo(url=f"{WEBAPP_URL}#check-price"))
        ]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, reply_markup = get_main_menu()
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "main_menu":
        text, reply_markup = get_main_menu()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    elif data == "add_account":
        text = "➕ *Add Account*\n━━━━━━━━━━━━━━━━━━━━\n\nHow would you like to link your Meesho account?"
        keyboard = [
            [InlineKeyboardButton("📱 Login with Number", callback_data="login_number")],
            [InlineKeyboardButton("📋 Import JSON session", callback_data="import_json")],
            [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "login_number":
        db["user_states"][user_id] = "AWAITING_PHONE"
        text = "📱 *Enter Phone Number*\n\nPlease enter your 10-digit Meesho registered phone number:"
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "import_json":
        db["user_states"][user_id] = "AWAITING_JSON"
        text = "📋 *Import JSON Session*\n\nPlease paste your Meesho session JSON below:"
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "set_refer_link":
        db["user_states"][user_id] = "AWAITING_REFER"
        ref_text = f"Current Link: `{db['referral_link']}`\n\n" if db["referral_link"] else "You haven't saved a referral link yet.\n\n"
        text = (
            f"🔗 *Set Refer Link*\n\n"
            f"{ref_text}"
            "Paste your Meesho *referral link* once and I'll use it automatically every time you add an account:\n\n"
            "_e.g. https://app.meesho.com/..._"
        )
        keyboard = [
            [InlineKeyboardButton("🚫 I don't have a refer code", callback_data="no_refer_code")],
            [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "no_refer_code":
        db["referral_link"] = ""
        await query.edit_message_text("✅ Referral skipped.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]))

    elif data == "my_accounts":
        if not db["accounts"]:
            text = "👤 *My Accounts*\n\nNo accounts linked yet. Tap below to add."
            keyboard = [[InlineKeyboardButton("➕ Add Account", callback_data="add_account")], [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        else:
            acc_list = "\n".join([f"• *+91 {a['mobile']}* (Active)" for a in db["accounts"]])
            text = f"👤 *My Accounts*\n\n{acc_list}"
            keyboard = [[InlineKeyboardButton("➕ Add More", callback_data="add_account")], [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "check_number":
        db["user_states"][user_id] = "AWAITING_CHECK"
        text = "🔍 *Check Number Eligibility*\n\nEnter a 10-digit number to check first-order discount eligibility:"
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "how_offer_works":
        text = (
            "🎁 *How Meesho Offer Works*\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "1. Link your un-used or new Meesho accounts.\n"
            "2. Open the shop to claim *100% Free / Discounted items*.\n"
            "3. Auto-applies maximum discounts on checkout.\n"
            "4. Free cash-on-delivery tracking included!"
        )
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message.text.strip()
    state = db["user_states"].get(user_id)

    if state == "AWAITING_PHONE":
        if len(msg) >= 10 and msg[-10:].isdigit():
            phone = msg[-10:]
            db["user_states"][user_id] = {"state": "AWAITING_OTP", "phone": phone}
            await update.message.reply_text(f"📩 OTP has been requested for *+91 {phone}*.\n\nPlease enter the 6-digit OTP received via SMS:", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Invalid number. Please send a valid 10-digit number.")

    elif isinstance(state, dict) and state.get("state") == "AWAITING_OTP":
        phone = state.get("phone")
        new_acc = {"id": len(db["accounts"]) + 1, "mobile": phone, "source": "otp", "order_placed": False, "xo_exp": 1795000000}
        db["accounts"].append(new_acc)
        db["active_id"] = new_acc["id"]
        db["user_states"].pop(user_id, None)
        text, reply_markup = get_main_menu()
        await update.message.reply_text(f"✅ *Account +91 {phone} linked successfully!*\n\nYou can now open the shop.", parse_mode="Markdown", reply_markup=reply_markup)

    elif state == "AWAITING_REFER":
        db["referral_link"] = msg
        db["user_states"].pop(user_id, None)
        await update.message.reply_text("✅ *Referral link saved successfully!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]))

    elif state == "AWAITING_CHECK":
        db["user_states"].pop(user_id, None)
        await update.message.reply_text(f"✅ *Number {msg} is ELIGIBLE for 1st order discount!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add This Account", callback_data="add_account")], [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]))

    elif state == "AWAITING_JSON":
        new_acc = {"id": len(db["accounts"]) + 1, "mobile": "SessionUser", "source": "json", "order_placed": False, "xo_exp": 1795000000}
        db["accounts"].append(new_acc)
        db["user_states"].pop(user_id, None)
        await update.message.reply_text("✅ *JSON Session imported successfully!*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]))

async def run_bot_background():
    global telegram_app
    if not BOT_TOKEN:
        return
    try:
        telegram_app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
        telegram_app.add_handler(CommandHandler("start", start_command))
        telegram_app.add_handler(CallbackQueryHandler(callback_handler))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
    except Exception as e:
        print(f"Bot error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    bot_task = asyncio.create_task(run_bot_background())
    yield
    if telegram_app and telegram_app.updater and telegram_app.updater.running:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
    bot_task.cancel()

# ================= FASTAPI APP =================
app = FastAPI(title="Meesho Mini App Server", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.mount("/UnknownGuy_js", StaticFiles(directory="public/UnknownGuy_js"), name="js")
app.mount("/UnknownGuy_css", StaticFiles(directory="public/UnknownGuy_css"), name="css")

@app.get("/")
async def serve_index():
    return FileResponse("public/index.html")

@app.get("/api/bootstrap")
async def api_bootstrap():
    return {"accounts": db["accounts"], "active_id": db["active_id"], "balance": 0, "per_order_price": 0}

@app.post("/api/accounts/select")
async def api_accounts_select(data: dict):
    db["active_id"] = int(data.get("account_id", 1))
    return {"ok": True}

@app.get("/api/accounts/order_status")
async def api_accounts_order_status():
    return {"statuses": {str(a["id"]): a["order_placed"] for a in db["accounts"]}}

@app.get("/api/accounts/list")
async def api_accounts_list():
    return {"accounts": db["accounts"]}

@app.post("/api/search")
async def api_search(data: dict):
    catalogs = [
        {
            "product_id": 1001,
            "name": "Men Premium Slim Fit Casual Cotton Shirt",
            "price": 0,
            "original_price": 899,
            "discount_text": "100% OFF (FREE)",
            "rating": 4.5,
            "rating_count": "14,200",
            "supplier_name": "Fashion Vibe",
            "mall_verified": True,
            "image": "https://images.meesho.com/images/products/312019481/1_512.jpg",
            "images": ["https://images.meesho.com/images/products/312019481/1_512.jpg"],
            "sizes": [{"variation_id": 1, "name": "M"}, {"variation_id": 2, "name": "L"}],
            "tags": ["Free Order", "Fast Dispatch"]
        }
    ]
    return {"catalogs": catalogs, "cursor": None, "corrected_term": None}

@app.get("/api/product")
async def api_product_detail(product_id: int):
    return {
        "product_id": product_id,
        "name": "Men Premium Slim Fit Casual Cotton Shirt",
        "price": 0,
        "mrp": 899,
        "brand": "Roadster",
        "supplier_name": "Fashion Vibe",
        "supplier_rating": 4.5,
        "supplier_rating_count": 8900,
        "mall_verified": True,
        "in_stock": True,
        "images": ["https://images.meesho.com/images/products/312019481/1_512.jpg"],
        "sizes": [{"variation_id": 1, "name": "M"}, {"variation_id": 2, "name": "L"}],
        "highlights": [{"name": "Fabric", "value": "100% Cotton"}],
        "description": "Free first order loot product.",
        "review_sentiment": [{"label": "Fabric Quality", "positive_pct": 94, "total": 4200}]
    }

@app.post("/api/variation")
async def api_variation(data: dict):
    return {"price": 0, "mrp": 899, "discount": "100% OFF", "in_stock": True, "cod_available": True, "shipping": {"charges": 0, "estimated_delivery": {"title": "Free Delivery", "date": "Within 3 Days"}}}

@app.get("/api/cart")
async def api_get_cart():
    return db["cart"]

@app.post("/api/cart/add")
async def api_cart_add(data: dict):
    return {"success": True, "result": {"effective_total": 0, "total_quantity": 1}}

@app.get("/api/addresses")
async def api_get_addresses():
    return {"addresses": db["addresses"], "default": db["addresses"][0]}

@app.get("/api/geocode")
async def api_geocode(q: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None):
    return {"results": [{"formatted": "Connaught Place, New Delhi - 110001", "city": "New Delhi", "state": "Delhi", "area": "Connaught Place", "pin": "110001", "lat": 28.6315, "lng": 77.2167}]}

@app.post("/api/order/prices")
async def api_order_prices(data: dict):
    return {"cod": 0, "online": 0}

@app.post("/api/order/place_cod")
async def api_place_cod(data: dict):
    return {"ok": True, "order_num": "OD98234120", "total": 0, "message": "Free Order Placed Successfully!"}

@app.get("/api/orders")
async def api_get_orders():
    return {"orders": db["orders"], "filters": [{"id": 0, "name": "All"}], "cursor": None}

@app.get("/api/referral/stats")
async def api_referral_stats():
    return {"done": 5, "pending": 0, "rejected": 0, "earned": 0, "link": db["referral_link"], "has_link": bool(db["referral_link"])}

@app.get("/api/account/fod")
async def api_fod():
    return {"offer": {"title": "FREE ORDER", "text": "100% Free", "subtitle": "First Order Discount"}}

@app.get("/api/wallet/history")
async def api_wallet_history():
    return {"balance": 0, "txns": []}
    
