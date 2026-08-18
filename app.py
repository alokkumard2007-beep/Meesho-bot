import os
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

# ================= CONFIGURATION =================
# Telegram Bot Token (@BotFather se mila hua)
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
# Render/Live app URL (Deploy hone ke baad mila URL yahan daalein ya environment variable set karein)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-app-name.onrender.com")

# ================= TELEGRAM BOT LOGIC =================
telegram_app = None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "User"
    keyboard = [
        [
            InlineKeyboardButton(
                text="🛍️ Open Meesho Store",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Namaste {user_name}! 👋\n\nTap below to open the Meesho Store Mini App:",
        reply_markup=reply_markup
    )

# Lifespan context manager jo FastAPI ke sath Bot ko background me start karega
@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    if BOT_TOKEN and BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        telegram_app.add_handler(CommandHandler("start", start_command))
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        print(" Telegram Bot started successfully!")
    yield
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()

# ================= FASTAPI APP =================
app = FastAPI(title="Meesho Mini App Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files folder mapping
app.mount("/UnknownGuy_js", StaticFiles(directory="public/UnknownGuy_js"), name="js")
app.mount("/UnknownGuy_css", StaticFiles(directory="public/UnknownGuy_css"), name="css")

@app.get("/")
async def serve_index():
    return FileResponse("public/index.html")

# In-Memory Database (Demo state)
db = {
    "accounts": [
        {"id": 1, "mobile": "9876543210", "source": "otp", "order_placed": True, "xo_exp": 1795000000},
        {"id": 2, "mobile": "9123456780", "source": "otp", "order_placed": False, "xo_exp": 1795000000}
    ],
    "active_id": 1,
    "balance": 1500,
    "fee": 0,
    "cart": {
        "items": [],
        "total_quantity": 0,
        "effective_total": 0,
        "effective_online": 0,
        "address": None,
        "price_break_up": []
    },
    "addresses": [
        {
            "id": 101,
            "name": "Alex Sharma",
            "mobile": "9876543210",
            "pin": "110001",
            "city": "New Delhi",
            "state": "Delhi",
            "address_line_1": "Flat 402, Block B, Green Heights",
            "address_line_2": "Connaught Place",
            "landmark": "Near Metro Station",
            "address_type": "Home",
            "pin_serviceable": True
        }
    ],
    "orders": [
        {
            "order_num": "OD98234120",
            "sub_order_num": "SO481023",
            "status_id": "SHIPPED",
            "status_text": "Shipped",
            "status_color": "#2F6BFF",
            "delivery_date": "2026-08-25",
            "updated_date": "2026-08-20",
            "quantity": 1,
            "size": "L",
            "carrier_name": "Shadowfax",
            "awb": "SF98124012IN",
            "tracking_url": "https://www.shadowfax.in",
            "image": "https://images.meesho.com/images/products/312019481/1_512.jpg"
        }
    ]
}

# --- 1. BOOTSTRAP & ACCOUNTS ---
@app.get("/api/bootstrap")
async def api_bootstrap():
    return {
        "accounts": db["accounts"],
        "active_id": db["active_id"],
        "balance": db["balance"],
        "per_order_price": db["fee"]
    }

@app.post("/api/accounts/select")
async def api_accounts_select(data: dict):
    db["active_id"] = int(data.get("account_id", 1))
    return {"ok": True}

@app.get("/api/accounts/order_status")
async def api_accounts_order_status():
    statuses = {str(a["id"]): a["order_placed"] for a in db["accounts"]}
    return {"statuses": statuses}

@app.get("/api/accounts/list")
async def api_accounts_list():
    return {"accounts": db["accounts"]}

@app.post("/api/accounts/refresh")
async def api_accounts_refresh(data: dict):
    return {"ok": True, "message": "Session refreshed successfully"}

# --- 2. SEARCH & PRODUCTS ---
@app.post("/api/search")
async def api_search(data: dict):
    catalogs = [
        {
            "product_id": 1001,
            "name": "Men Premium Slim Fit Casual Cotton Shirt",
            "price": 399,
            "original_price": 899,
            "discount_text": "55% OFF",
            "rating": 4.3,
            "rating_count": "12,400",
            "supplier_name": "Fashion Vibe",
            "mall_verified": True,
            "image": "https://images.meesho.com/images/products/312019481/1_512.jpg",
            "images": ["https://images.meesho.com/images/products/312019481/1_512.jpg"],
            "sizes": [
                {"variation_id": 1, "name": "M"},
                {"variation_id": 2, "name": "L"},
                {"variation_id": 3, "name": "XL"}
            ],
            "tags": ["Fast Dispatch", "Free Delivery"]
        },
        {
            "product_id": 1002,
            "name": "Embroidered Semi-Stitched Anarkali Kurti & Dupatta",
            "price": 549,
            "original_price": 1299,
            "discount_text": "57% OFF",
            "rating": 4.6,
            "rating_count": "24,800",
            "supplier_name": "Ethnic Hub",
            "mall_verified": True,
            "image": "https://images.meesho.com/images/products/298412891/1_512.jpg",
            "images": ["https://images.meesho.com/images/products/298412891/1_512.jpg"],
            "sizes": [{"variation_id": 1, "name": "Free Size"}],
            "tags": ["Trending", "Lowest Price"]
        }
    ]
    return {"catalogs": catalogs, "cursor": None, "corrected_term": None}

@app.get("/api/product")
async def api_product_detail(product_id: int):
    return {
        "product_id": product_id,
        "name": "Men Premium Slim Fit Casual Cotton Shirt",
        "price": 399,
        "mrp": 899,
        "brand": "Roadster",
        "supplier_name": "Fashion Vibe",
        "supplier_rating": 4.4,
        "supplier_rating_count": 8900,
        "mall_verified": True,
        "in_stock": True,
        "images": ["https://images.meesho.com/images/products/312019481/1_512.jpg"],
        "sizes": [
            {"variation_id": 1, "name": "M"},
            {"variation_id": 2, "name": "L"},
            {"variation_id": 3, "name": "XL"}
        ],
        "highlights": [
            {"name": "Fabric", "value": "100% Pure Cotton"},
            {"name": "Pattern", "value": "Solid"},
            {"name": "Sleeve", "value": "Full Sleeve"},
            {"name": "Fit", "value": "Slim Fit"}
        ],
        "description": "Premium breathable fabric suitable for casual daily wear and office outfits.",
        "review_sentiment": [
            {"label": "Fabric Quality", "positive_pct": 89, "total": 4200},
            {"label": "Fitting & Comfort", "positive_pct": 92, "total": 3800}
        ]
    }

@app.post("/api/variation")
async def api_variation(data: dict):
    return {
        "price": 399,
        "mrp": 899,
        "discount": "55% OFF",
        "in_stock": True,
        "cod_available": True,
        "shipping": {"charges": 0, "estimated_delivery": {"title": "Fast Delivery", "date": "Within 4-5 Days"}}
    }

# --- 3. CART & CHECKOUT ---
@app.get("/api/cart")
async def api_get_cart():
    items = db["cart"]["items"]
    subtotal = sum(i["price"] * i["quantity"] for i in items)
    db["cart"]["effective_total"] = subtotal
    db["cart"]["effective_online"] = max(0, subtotal - 25) if subtotal > 0 else 0
    db["cart"]["total_quantity"] = sum(i["quantity"] for i in items)
    db["cart"]["price_break_up"] = [
        {"type": "Item Total", "display_name": "Items Total", "value": subtotal},
        {"type": "Delivery Charges", "display_name": "Delivery", "value": 0}
    ]
    if not db["cart"]["address"] and db["addresses"]:
        db["cart"]["address"] = db["addresses"][0]
    return db["cart"]

@app.post("/api/cart/add")
async def api_cart_add(data: dict):
    item = {
        "identifier": f"{data.get('product_id')}_{data.get('variation_id')}",
        "product_id": data.get("product_id"),
        "supplier_id": data.get("supplier_id"),
        "name": "Men Premium Slim Fit Casual Cotton Shirt",
        "price": 399,
        "mrp": 899,
        "quantity": data.get("quantity", 1),
        "variation": data.get("variation", "M"),
        "variation_id": data.get("variation_id"),
        "image": "https://images.meesho.com/images/products/312019481/1_512.jpg"
    }
    db["cart"]["items"].append(item)
    total_qty = sum(i["quantity"] for i in db["cart"]["items"])
    total_val = sum(i["price"] * i["quantity"] for i in db["cart"]["items"])
    return {
        "success": True,
        "result": {
            "effective_total": total_val,
            "total_quantity": total_qty
        }
    }

@app.post("/api/cart/update")
async def api_cart_update(data: dict):
    return await api_get_cart()

@app.post("/api/cart/location")
async def api_cart_location(data: dict):
    addr_id = data.get("address_id")
    addr = next((a for a in db["addresses"] if a["id"] == addr_id), None)
    if addr:
        db["cart"]["address"] = addr
    return db["cart"]

# --- 4. ADDRESSES & GEOCODE ---
@app.get("/api/addresses")
async def api_get_addresses():
    return {"addresses": db["addresses"], "default": db["addresses"][0] if db["addresses"] else None}

@app.post("/api/addresses/create")
async def api_addresses_create(data: dict):
    new_addr = {
        "id": len(db["addresses"]) + 101,
        "name": data.get("name"),
        "mobile": data.get("mobile"),
        "pin": data.get("pin"),
        "city": data.get("city"),
        "state": data.get("state"),
        "address_line_1": data.get("address_line_1"),
        "address_line_2": data.get("address_line_2"),
        "landmark": data.get("landmark"),
        "address_type": data.get("address_type", "Home"),
        "pin_serviceable": True
    }
    db["addresses"].append(new_addr)
    return {"ok": True, "address": new_addr}

@app.get("/api/geocode")
async def api_geocode(q: Optional[str] = None, lat: Optional[float] = None, lng: Optional[float] = None):
    return {
        "results": [
            {
                "formatted": "Connaught Place, Central Delhi, Delhi - 110001",
                "city": "New Delhi",
                "state": "Delhi",
                "area": "Connaught Place",
                "pin": "110001",
                "lat": 28.6315,
                "lng": 77.2167
            }
        ]
    }

# --- 5. ORDERS & PAYMENTS ---
@app.post("/api/order/prices")
async def api_order_prices(data: dict):
    subtotal = db["cart"]["effective_total"]
    return {"cod": subtotal, "online": max(0, subtotal - 25)}

@app.post("/api/order/place_cod")
async def api_place_cod(data: dict):
    order_num = f"OD{asyncio.get_event_loop().time():.0f}"
    new_order = {
        "order_num": order_num,
        "sub_order_num": f"SO{order_num[-6:]}",
        "status_id": "ORDERED",
        "status_text": "Order Confirmed",
        "status_color": "#0EAE6E",
        "delivery_date": "2026-08-26",
        "updated_date": "2026-08-17",
        "quantity": db["cart"]["total_quantity"] or 1,
        "size": "L",
        "carrier_name": "Shadowfax Courier",
        "awb": f"SF{order_num[-8:]}IN",
        "tracking_url": "https://www.shadowfax.in",
        "image": db["cart"]["items"][0]["image"] if db["cart"]["items"] else "https://images.meesho.com/images/products/312019481/1_512.jpg"
    }
    db["orders"].insert(0, new_order)
    db["cart"]["items"] = []
    return {"ok": True, "order_num": order_num, "total": db["cart"]["effective_total"], "message": "COD Order Placed Successfully!"}

@app.get("/api/orders")
async def api_get_orders():
    return {"orders": db["orders"], "filters": [{"id": 0, "name": "All"}], "cursor": None}

@app.post("/api/orders/detail")
async def api_order_detail(data: dict):
    order_num = data.get("order_num")
    order = next((o for o in db["orders"] if o["order_num"] == order_num), db["orders"][0])
    return {
        "order_num": order["order_num"],
        "sub_order_num": order["sub_order_num"],
        "status_id": order["status_id"],
        "product": {
            "name": "Men Premium Slim Fit Casual Cotton Shirt",
            "size": order.get("size", "L"),
            "images": [order["image"]]
        },
        "tracking": {
            "title": order["status_text"],
            "delivery_by": order["delivery_date"]
        },
        "milestones": [
            {"status": "Ordered", "done": True, "date": "17 Aug"},
            {"status": "Packed", "done": True, "date": "18 Aug"},
            {"status": "Shipped", "done": True, "is_current": True, "current_text": "In Transit", "date": "20 Aug"},
            {"status": "Out for delivery", "done": False},
            {"status": "Delivered", "done": False}
        ],
        "shipment": {
            "carrier_name": order.get("carrier_name", "Shadowfax"),
            "awb": order.get("awb", "SF98124012IN"),
            "tracking_url": order.get("tracking_url", "https://www.shadowfax.in")
        },
        "address": db["addresses"][0] if db["addresses"] else None,
        "payment": {"mode": "Cash on Delivery", "total": 399}
    }

@app.get("/api/referral/stats")
async def api_referral_stats():
    return {"done": 4, "pending": 2, "rejected": 0, "earned": 600, "link": f"https://t.me/share/url?url={WEBAPP_URL}", "has_link": True}

@app.get("/api/account/fod")
async def api_fod():
    return {"offer": {"title": "FLAT ₹100 OFF", "text": "Instant Discount", "subtitle": "Valid on 1st Order"}}

@app.get("/api/wallet/history")
async def api_wallet_history():
    return {
        "balance": db["balance"],
        "txns": [
            {"amount": 500, "kind": "Recharge", "at": "2026-08-15 14:30", "note": "UPI Add Funds"},
            {"amount": -399, "kind": "Order", "at": "2026-08-17 11:20", "note": "Order #OD98234120"}
        ]
    }
