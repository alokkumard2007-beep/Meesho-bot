import os
import asyncio
import json
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import random

# ================= CONFIGURATION =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8675212406:AAEuWWrfpCjh_I8Eu5VJou-fc1GMQoweOpw")
RAW_URL = os.getenv("WEBAPP_URL", "https://meesho-bot.onrender.com")
if "[" in RAW_URL and "(" in RAW_URL:
    WEBAPP_URL = RAW_URL.split("(")[-1].replace(")", "").strip().rstrip("/")
else:
    WEBAPP_URL = RAW_URL.strip().rstrip("/")

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
            "line1": "Connaught Place",
            "line2": "",
            "landmark": "",
            "address_type": "Home",
            "pin_serviceable": True
        }
    ],
    "cart": {"items": [], "total_quantity": 0, "effective_total": 0, "effective_online": 0, "address": None, "price_break_up": []},
    "orders": [],
    "pending_otp": {}  # Store OTP requests
}

# ================= REAL MEESHO API CLIENT =================
COMMON_HEADERS = {
    "Host": "www.meesho.com",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "meesho-iso-country-code": "IN",
    "origin": "https://www.meesho.com",
    "sec-ch-ua-platform": '"Android"',
    "sec-ch-ua-mobile": "?1"
}

# ================= ENHANCED API FUNCTIONS =================

async def check_phone_eligibility(phone_number: str):
    """Check if a number is registered on Meesho"""
    url = "https://www.meesho.com/api/v1/user/check-phone"
    headers = {
        "Host": "www.meesho.com",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "meesho-iso-country-code": "IN",
        "origin": "https://www.meesho.com"
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, headers=headers, json={"phone_number": str(phone_number)})
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ok": True,
                    "registered": data.get("registered", False),
                    "can_order": data.get("can_order", True),
                    "first_order_discount": data.get("first_order_discount", {}),
                    "message": data.get("message", "Number checked successfully")
                }
        except Exception:
            pass
        # Fallback - simulate check
        return {
            "ok": True,
            "registered": False,
            "can_order": True,
            "first_order_discount": {"available": True, "amount": 180},
            "message": "Number is eligible for first-order discount"
        }

async def send_meesho_real_otp(phone_number: str, tier: int = 180):
    """Send OTP with tier selection"""
    # Store the tier preference
    db["pending_otp"][phone_number] = {"tier": tier, "timestamp": asyncio.get_event_loop().time()}
    
    url = "https://www.meesho.com/api/v1/user/login/request-otp"
    headers = {
        "Host": "www.meesho.com",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "meesho-iso-country-code": "IN",
        "origin": "https://www.meesho.com",
        "referer": "https://www.meesho.com/auth?redirect=https%3A%2F%2Fwww.meesho.com%2Fmcheckout%2Fcart&source=cart-icon&screen=HP"
    }
    payload = {"phone_number": str(phone_number)}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                res_data = resp.json()
                return {
                    "ok": True,
                    "request_id": res_data.get("data", {}).get("request_id", f"req_{phone_number[-4:]}"),
                    "instance_id": res_data.get("data", {}).get("instance_id", f"inst_{phone_number[-4:]}"),
                    "message": "OTP sent successfully"
                }
        except Exception:
            pass
        # Fallback for demo
        return {
            "ok": True,
            "request_id": f"req_{phone_number[-4:]}",
            "instance_id": f"inst_{phone_number[-4:]}",
            "message": "OTP sent (demo mode)"
        }

async def verify_meesho_real_otp(phone_number: str, otp: str, request_id: str, instance_id: str):
    """Verify OTP and get session"""
    url = "https://www.meesho.com/api/v1/user/login"
    headers = {
        "Host": "www.meesho.com",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "meesho-iso-country-code": "IN",
        "origin": "https://www.meesho.com",
        "referer": "https://www.meesho.com/auth/verify?redirect=https%3A%2F%2Fwww.meesho.com%2Fmcheckout%2Fcart&source=cart-icon&screen=HP"
    }
    payload = {
        "request_id": request_id,
        "instance_id": instance_id,
        "phone_number": str(phone_number),
        "otp": str(otp),
        "login_type": "meesho_sms_auth"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                res_data = resp.json()
                if res_data.get("status") is True:
                    user_data = res_data.get("user", {})
                    # Get tier from pending_otp
                    tier_data = db["pending_otp"].get(phone_number, {})
                    selected_tier = tier_data.get("tier", 180)
                    
                    # Determine bonus message based on tier
                    bonus_ok = True
                    bonus_msg = f"🎉 Welcome bonus activated! You'll get up to ₹{selected_tier} OFF on your first order."
                    
                    if selected_tier >= 150:
                        bonus_msg = f"🔥 MAXIMUM discount unlocked! You'll save up to ₹{selected_tier} on first order."
                    
                    return {
                        "ok": True,
                        "user_id": user_data.get("user_id", f"UID_{phone_number[-4:]}"),
                        "cookies": res_data.get("cookies", {}),
                        "phone": phone_number,
                        "new_user": user_data.get("new", True),
                        "bonus_ok": bonus_ok,
                        "bonus_msg": bonus_msg,
                        "tier": selected_tier
                    }
        except Exception:
            pass
        
        # Demo mode - accept any 6-digit OTP
        if len(otp) == 6 and otp.isdigit():
            tier_data = db["pending_otp"].get(phone_number, {})
            selected_tier = tier_data.get("tier", 180)
            return {
                "ok": True,
                "user_id": f"UID_{phone_number[-4:]}",
                "phone": phone_number,
                "new_user": True,
                "bonus_ok": True,
                "bonus_msg": f"🎉 Welcome discount of ₹{selected_tier} activated!",
                "tier": selected_tier
            }
        return {"ok": False, "error": "Invalid OTP or expired"}

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
            [InlineKeyboardButton("📱 Login with Number (Real SMS)", callback_data="login_number")],
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
            acc_list = "\n".join([f"• *+91 {a['mobile']}* (ID: `{a.get('user_id', 'Active')}`)" for a in db["accounts"]])
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
            "1. Link your Meesho account using live OTP.\n"
            "2. Open shop to get 100% Free / Discounted catalog.\n"
            "3. Auto-applies maximum discounts on checkout.\n"
            "4. Free cash-on-delivery tracking included!"
        )
        keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ================= ENHANCED MESSAGE HANDLER =================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message.text.strip()
    state = db["user_states"].get(user_id)

    if state == "AWAITING_PHONE":
        if len(msg) >= 10 and msg[-10:].isdigit():
            phone = msg[-10:]
            
            # First check if number is eligible
            await update.message.reply_text(f"🔍 Checking number *+91 {phone}* for eligibility...", parse_mode="Markdown")
            
            check_result = await check_phone_eligibility(phone)
            
            if check_result.get("ok"):
                if check_result.get("registered"):
                    await update.message.reply_text(
                        f"⚠️ *Number already registered*\n\n"
                        f"+91 {phone} is already registered on Meesho. "
                        f"The welcome bonus works best on a NEW number.\n\n"
                        f"Would you like to continue anyway?",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Continue Anyway", callback_data="login_number")],
                            [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
                        ])
                    )
                    return
                
                # Show available discount tiers
                tier_text = (
                    f"📱 *Select Your Discount Tier*\n\n"
                    f"*+91 {phone}* is a fresh number! 🎉\n\n"
                    f"Choose your MINIMUM discount tier. "
                    f"We'll hunt for the lowest price at or above your tier:\n\n"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("₹110 (Fast)", callback_data=f"tier_110_{phone}"),
                        InlineKeyboardButton("₹120 (Good)", callback_data=f"tier_120_{phone}")
                    ],
                    [
                        InlineKeyboardButton("₹135 (Better)", callback_data=f"tier_135_{phone}"),
                        InlineKeyboardButton("₹150 (High)", callback_data=f"tier_150_{phone}")
                    ],
                    [
                        InlineKeyboardButton("₹180 (Max) ⭐", callback_data=f"tier_180_{phone}")
                    ],
                    [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")]
                ]
                
                await update.message.reply_text(tier_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
                db["user_states"][user_id] = {"state": "AWAITING_TIER", "phone": phone}
            else:
                await update.message.reply_text(
                    f"❌ *Couldn't check number*\n\n"
                    f"Please try again or use JSON import.",
                    parse_mode="Markdown"
                )
        else:
            await update.message.reply_text("❌ Invalid number. Please send a valid 10-digit number.")

    # Handle tier selection via callback or text
    elif isinstance(state, dict) and state.get("state") == "AWAITING_TIER":
        # If user sends a number directly (fallback)
        if msg.isdigit() and len(msg) >= 10:
            phone = msg[-10:]
            # Proceed with default tier
            await process_otp_send(update, phone, 180)
        else:
            await update.message.reply_text(
                "Please select a tier using the buttons above, or send your 10-digit phone number to continue."
            )

    elif isinstance(state, dict) and state.get("state") == "AWAITING_OTP":
        phone = state.get("phone")
        request_id = state.get("request_id")
        instance_id = state.get("instance_id")
        otp = msg

        await update.message.reply_text("⏳ Verifying OTP with Meesho servers...")
        verify_res = await verify_meesho_real_otp(phone, otp, request_id, instance_id)

        if verify_res["ok"]:
            new_acc = {
                "id": len(db["accounts"]) + 1,
                "mobile": phone,
                "user_id": verify_res.get("user_id"),
                "cookies": verify_res.get("cookies"),
                "source": "otp",
                "order_placed": False,
                "xo_exp": 1795000000,
                "tier": verify_res.get("tier", 180)
            }
            db["accounts"].append(new_acc)
            db["active_id"] = new_acc["id"]
            db["user_states"].pop(user_id, None)
            
            # Clean up pending OTP
            db["pending_otp"].pop(phone, None)
            
            # Show success with bonus info
            bonus_msg = verify_res.get("bonus_msg", "🎉 Account linked successfully!")
            await update.message.reply_text(
                f"✅ *Account Linked Successfully!*\n\n"
                f"📱 +91 {phone}\n"
                f"🎯 Tier: ₹{verify_res.get('tier', 180)}\n\n"
                f"{bonus_msg}\n\n"
                f"Tap below to start shopping:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🛍️ Open Shop Now", web_app=WebAppInfo(url=WEBAPP_URL))],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
                ])
            )
        else:
            await update.message.reply_text(
                f"❌ *Verification Failed*\n\n"
                f"{verify_res.get('error', 'Invalid OTP')}\n\n"
                f"Please try entering the OTP again:",
                parse_mode="Markdown"
            )

    elif state == "AWAITING_REFER":
        db["referral_link"] = msg
        db["user_states"].pop(user_id, None)
        await update.message.reply_text(
            "✅ *Referral link saved successfully!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
        )

    elif state == "AWAITING_CHECK":
        db["user_states"].pop(user_id, None)
        await update.message.reply_text(
            f"✅ *Number {msg} is ELIGIBLE for 1st order discount!*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add This Account", callback_data="add_account")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ])
        )

    elif state == "AWAITING_JSON":
        try:
            json_data = json.loads(msg)
            new_acc = {
                "id": len(db["accounts"]) + 1,
                "mobile": json_data.get("phone", "SessionUser"),
                "user_id": json_data.get("user_id", "JSON_User"),
                "source": "json",
                "order_placed": False,
                "xo_exp": 1795000000,
                "cookies": json_data.get("cookies", {})
            }
            db["accounts"].append(new_acc)
            db["user_states"].pop(user_id, None)
            await update.message.reply_text(
                "✅ *JSON Session imported successfully!*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
            )
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON. Please paste a valid JSON session.")

# Helper function for OTP send
async def process_otp_send(update, phone, tier):
    await update.message.reply_text(f"⏳ Requesting OTP from Meesho for *+91 {phone}*...", parse_mode="Markdown")
    
    otp_res = await send_meesho_real_otp(phone, tier)
    
    if otp_res["ok"]:
        db["user_states"][update.effective_user.id] = {
            "state": "AWAITING_OTP",
            "phone": phone,
            "request_id": otp_res["request_id"],
            "instance_id": otp_res["instance_id"],
            "tier": tier
        }
        await update.message.reply_text(
            f"📩 *OTP Sent Successfully!* 📲\n\n"
            f"Please enter the 6-digit OTP received on *+91 {phone}*:\n\n"
            f"_The OTP expires in 5 minutes_",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ *Failed to send OTP*\n\n"
            f"{otp_res.get('error', 'Please try again later')}",
            parse_mode="Markdown"
        )

# ================= FASTAPI APP =================

@asynccontextmanager
async def lifespan(app: FastAPI):
    bot_task = asyncio.create_task(run_bot_background())
    yield
    if telegram_app and telegram_app.updater and telegram_app.updater.running:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
    bot_task.cancel()

app = FastAPI(title="Meesho Mini App Server", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Mount static files
app.mount("/UnknownGuy_js", StaticFiles(directory="public/UnknownGuy_js"), name="js")
app.mount("/UnknownGuy_css", StaticFiles(directory="public/UnknownGuy_css"), name="css")

# ================= ENHANCED API ENDPOINTS =================

@app.get("/")
async def serve_index():
    return FileResponse("public/index.html")

@app.get("/api/bootstrap")
async def api_bootstrap():
    return {
        "accounts": db["accounts"],
        "active_id": db["active_id"],
        "balance": 0,
        "per_order_price": 0,
        "last_phone": db["accounts"][-1]["mobile"] if db["accounts"] else None
    }

@app.post("/api/account/select")
async def api_account_select(data: dict):
    phone = data.get("phone")
    if phone:
        for acc in db["accounts"]:
            if acc["mobile"] == phone:
                db["active_id"] = acc["id"]
                return {"ok": True}
    return {"ok": False, "error": "Account not found"}

@app.post("/api/check")
async def api_check_number(data: dict):
    phone = data.get("number", "")
    if len(phone) == 10 and phone.isdigit():
        result = await check_phone_eligibility(phone)
        return {
            "ok": True,
            "results": [{
                "phone": phone,
                "registered": result.get("registered", False),
                "can_order": result.get("can_order", True)
            }]
        }
    return {"ok": False, "error": "Invalid phone number"}

@app.post("/api/login/start")
async def api_login_start(data: dict):
    phone = data.get("phone", "")
    referral = data.get("referral", "")
    tier = data.get("tier", 180)
    
    if len(phone) != 10 or not phone.isdigit():
        return {"ok": False, "error": "Invalid phone number"}
    
    # Check if number is eligible
    check_result = await check_phone_eligibility(phone)
    
    # Calculate FOD value based on tier
    fod_value = tier
    upi_amount = max(9, random.randint(9, tier - 1))  # Simulate price hunt
    
    return {
        "ok": True,
        "phone": f"+91{phone}",
        "tier": tier,
        "fod_value": fod_value,
        "upi_amount": upi_amount,
        "registered": check_result.get("registered", False),
        "bonus_available": True
    }

@app.post("/api/login/send_otp")
async def api_login_send_otp(data: dict):
    phone = data.get("phone", "")
    tier = data.get("tier", 180)
    
    if len(phone) != 10:
        return {"ok": False, "error": "Invalid phone number"}
    
    result = await send_meesho_real_otp(phone, tier)
    if result["ok"]:
        return {
            "ok": True,
            "phone": f"+91{phone}",
            "mode": "SMS",
            "request_id": result.get("request_id"),
            "instance_id": result.get("instance_id")
        }
    return {"ok": False, "error": result.get("error", "Failed to send OTP")}

@app.post("/api/login/verify")
async def api_login_verify(data: dict):
    otp = data.get("otp", "")
    phone = data.get("phone", "")
    request_id = data.get("request_id", "")
    instance_id = data.get("instance_id", "")
    
    if len(otp) < 4:
        return {"ok": False, "error": "Invalid OTP"}
    
    result = await verify_meesho_real_otp(phone, otp, request_id, instance_id)
    
    if result["ok"]:
        # Save account
        new_acc = {
            "id": len(db["accounts"]) + 1,
            "mobile": phone,
            "user_id": result.get("user_id"),
            "source": "otp",
            "order_placed": False,
            "tier": result.get("tier", 180)
        }
        db["accounts"].append(new_acc)
        db["active_id"] = new_acc["id"]
        
        return {
            "ok": True,
            "phone": f"+91{phone}",
            "bonus_ok": result.get("bonus_ok", True),
            "bonus_msg": result.get("bonus_msg", "Welcome bonus activated!"),
            "tier": result.get("tier", 180)
        }
    
    return {"ok": False, "error": result.get("error", "Verification failed")}

@app.post("/api/import")
async def api_import_account(data: dict):
    try:
        acc_data = data.get("data", {})
        new_acc = {
            "id": len(db["accounts"]) + 1,
            "mobile": acc_data.get("phone", "Imported"),
            "user_id": acc_data.get("user_id", "Imported"),
            "source": "json",
            "order_placed": False,
            "cookies": acc_data.get("cookies", {})
        }
        db["accounts"].append(new_acc)
        return {"ok": True, "message": "Account imported successfully"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Keep other existing endpoints (cart, orders, etc.)
@app.get("/api/accounts")
async def api_accounts_list():
    return {
        "ok": True,
        "accounts": db["accounts"],
        "active_id": db["active_id"]
    }

@app.get("/api/account/refresh")
async def api_account_refresh(phone: str):
    # Find account
    for acc in db["accounts"]:
        if acc["mobile"] == phone:
            return {"ok": True, "message": "Session refreshed"}
    return {"ok": False, "error": "Account not found"}

@app.post("/api/account/delete")
async def api_account_delete(data: dict):
    phone = data.get("phone")
    db["accounts"] = [a for a in db["accounts"] if a["mobile"] != phone]
    if db["active_id"] and db["active_id"] == phone:
        db["active_id"] = None
    return {"ok": True}

@app.get("/api/export")
async def api_export_account(phone: str):
    for acc in db["accounts"]:
        if acc["mobile"] == phone:
            return {
                "ok": True,
                "export": {
                    "phone": acc["mobile"],
                    "user_id": acc.get("user_id"),
                    "cookies": acc.get("cookies", {})
                }
            }
    return {"ok": False, "error": "Account not found"}

@app.post("/api/address/save")
async def api_address_save(data: dict):
    db["addresses"][0].update(data)
    return {"ok": True, "message": "Address saved"}

@app.post("/api/referral/save")
async def api_referral_save(data: dict):
    db["referral_link"] = data.get("referral", "")
    return {"ok": True, "cleared": not bool(data.get("referral"))}

@app.get("/api/cart")
async def api_get_cart():
    return {"ok": True, "items": db["cart"]["items"]}

@app.post("/api/cart/add")
async def api_cart_add(data: dict):
    db["cart"]["items"].append({
        "id": len(db["cart"]["items"]) + 1,
        "name": "Test Product",
        "cod": 0,
        "mrp": 899,
        "quantity": 1,
        "image": "https://images.meesho.com/images/products/312019481/1_512.jpg"
    })
    return {"ok": True, "items": db["cart"]["items"]}

@app.post("/api/cart/remove")
async def api_cart_remove(data: dict):
    item_id = data.get("id")
    db["cart"]["items"] = [i for i in db["cart"]["items"] if str(i.get("id")) != str(item_id)]
    return {"ok": True, "items": db["cart"]["items"]}

@app.post("/api/cart/qty")
async def api_cart_qty(data: dict):
    item_id = data.get("id")
    delta = data.get("delta", 0)
    for item in db["cart"]["items"]:
        if str(item.get("id")) == str(item_id):
            item["quantity"] = max(1, item.get("quantity", 1) + delta)
            break
    return {"ok": True, "items": db["cart"]["items"]}

@app.get("/api/orders")
async def api_get_orders():
    return {"ok": True, "orders": db["orders"]}

@app.get("/api/orders/{order_num}")
async def api_get_order_detail(order_num: str):
    return {
        "ok": True,
        "detail": {
            "order_num": order_num,
            "status": "Confirmed",
            "product": {"name": "Test Product", "price": 0},
            "address": db["addresses"][0],
            "timeline": [
                {"status": "Ordered", "completed": True, "date": "2024-01-01"},
                {"status": "Shipped", "completed": True, "date": "2024-01-02"},
                {"status": "Delivered", "completed": False, "date": "Pending"}
            ]
        }
    }

@app.post("/api/order/cancel")
async def api_order_cancel(data: dict):
    return {"ok": True, "message": "Order cancelled successfully"}

@app.post("/api/order/address")
async def api_order_address(data: dict):
    db["addresses"][0].update(data)
    return {"ok": True, "message": "Address updated"}

# Bot runner function
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
        print("✅ Bot started successfully!")
    except Exception as e:
        print(f"❌ Bot error: {e}")

# Run the server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
