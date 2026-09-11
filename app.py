import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta
import requests
from dotenv import load_dotenv

# ⚡ LOAD ENVIRONMENT VARIABLES FIRST (Reads .env locally)
load_dotenv()

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    make_response,
    jsonify,
    send_from_directory
)
from supabase import create_client, Client
from pywebpush import webpush, WebPushException
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key")

# =========================================
# 🔒 PRODUCTION COOKIE & SECURITY SETTINGS
# =========================================
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)  # ⏰ Keeps user logged in for 1 year
if os.environ.get("RENDER"):
    app.config['SESSION_COOKIE_SECURE'] = True

# =========================================
# ⚡ SUPABASE CLOUD CONNECTION
# =========================================
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", 
    "https://wndiqgyuvjenglfydqdt.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InduZGlxZ3l1dmplbmdsZnlkcWR0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU3NDUxMTEsImV4cCI6MjEwMTMyMTExMX0.8TgmmXUxyX4cjfynjcA0fGA0seVkg7bpoWj3c3rI2bU"
)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================================
# 📧 BREVO HTTP API EMAIL HELPER (PORT 443)
# =========================================
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
SENDER_EMAIL = os.environ.get("MAIL_USERNAME", "regismariecollege100@gmail.com")
SENDER_NAME = "Regis Marie College LMS"

def send_email_api(to_recipients, subject, body_text):
    """
    Sends transactional emails over HTTPS (Port 443) via Brevo API.
    Works reliably on Render without encountering SMTP port blocks.
    `to_recipients` can be a single email string or a list of emails.
    """
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        print("❌ BREVO_API_KEY is not set. Email dispatch skipped.")
        return False

    if isinstance(to_recipients, str):
        to_recipients = [to_recipients]

    to_list = [{"email": e.strip()} for e in to_recipients if e and e.strip()]
    if not to_list:
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    html_content = (
        "<div style='font-family: Arial, sans-serif; line-height: 1.6; color: #333;'>"
        + body_text.replace("\n", "<br>")
        + "</div>"
    )

    payload = {
        "sender": {
            "name": SENDER_NAME,
            "email": SENDER_EMAIL
        },
        "to": to_list,
        "subject": subject,
        "htmlContent": html_content,
        "textContent": body_text
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            print(f"✅ Email successfully dispatched to {len(to_list)} recipient(s).")
            return True
        else:
            print(f"❌ Brevo API error ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Network error while calling Brevo API: {e}")
        return False

# =========================================
# 🔔 VAPID & WEB PUSH CONFIGURATION
# =========================================
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "vapid_private.pem")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:regismariecollege100@gmail.com")

# =========================================
# 🔒 HELPER: PREVENT BROWSER CACHING
# =========================================
def prevent_caching(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# =========================================
# 🌐 GLOBAL TEMPLATE CONTEXT
# =========================================
@app.context_processor
def inject_user_context():
    return {
        'full_name': session.get('full_name', ''),
        'role': session.get('role', ''),
        'email': session.get('email', ''),
        'user_id': session.get('user_id', '')
    }

# =========================================
# 📱 PWA ROOT SERVICE WORKER & ASSET FALLBACKS
# =========================================
@app.route('/sw.js')
def service_worker():
    """Serves sw.js from root scope so it can control all routes and trigger PWA install."""
    response = make_response(send_from_directory('static', 'sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return prevent_caching(response)

@app.route('/favicon.ico')
def favicon():
    """Resolves browser favicon requests without 404 errors."""
    return send_from_directory('static', 'rmc.png', mimetype='image/png')

@app.route('/static/rmc.jpg')
def fallback_rmc_jpg():
    """Prevents 404 errors from older templates still referencing rmc.jpg."""
    return send_from_directory('static', 'rmc.png', mimetype='image/png')

# =========================================
# 🏠 PUBLIC & AUTHENTICATION ROUTES
# =========================================
@app.route('/')
@app.route('/index')
@app.route('/index.html')
def index():
    if 'user_id' in session:
        return redirect(url_for('landpage'))
    response = make_response(render_template('index.html'))
    return prevent_caching(response)

@app.route('/home')
@app.route('/homepage')
@app.route('/homepage.html')
def home():
    response = make_response(render_template('homepage.html'))
    return prevent_caching(response)

@app.route('/login', methods=['GET', 'POST'])
@app.route('/login.html', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('landpage'))

    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        email = (data.get('email') or '').strip().lower()
        password = (data.get('password') or '').strip()

        try:
            response = supabase.table('users').select('*').eq('email', email).eq('password', password).execute()
            users = response.data

            if users and len(users) > 0:
                user = users[0]

                session.permanent = True
                session['user_id'] = str(user['id'])
                session['full_name'] = user.get('full_name', '')
                session['email'] = user.get('email', '')
                session['role'] = str(user.get('role', 'STUDENT')).upper()

                print(f"👤 Logged in User: {session['full_name']} | ID: {session['user_id']} | Role: {session['role']}")

                if is_ajax:
                    return jsonify({"success": True, "redirect": url_for('landpage')}), 200
                return redirect(url_for('landpage'))
            else:
                if is_ajax:
                    return jsonify({"success": False, "message": "Invalid email or password."}), 401
                flash("Invalid email or password.", "error")
                return redirect(url_for('login'))

        except Exception as err:
            print(f"❌ Login Database Error: {err}")
            if is_ajax:
                return jsonify({"success": False, "message": f"Database error: {err}"}), 500
            flash(f"Database error: {err}", "error")
            return redirect(url_for('login'))

    response = make_response(render_template('login.html'))
    return prevent_caching(response)

@app.route('/register', methods=['GET', 'POST'])
@app.route('/register.html', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json(silent=True) or request.form
        is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        full_name = (data.get('full_name') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = (data.get('password') or '123456').strip()
        role = (data.get('role') or 'STUDENT').strip().upper()

        if not email or not full_name:
            if is_ajax:
                return jsonify({"success": False, "message": "Full name and email are required."}), 400
            flash("Full name and email address are required.", "warning")
            return redirect(url_for('register'))

        try:
            existing = supabase.table('users').select('id').eq('email', email).execute()
            if existing.data and len(existing.data) > 0:
                if is_ajax:
                    return jsonify({"success": False, "message": "An account with this email already exists."}), 409
                flash("An account with this email address already exists.", "warning")
                return redirect(url_for('register'))

            user_data = {
                'full_name': full_name,
                'email': email,
                'password': password,
                'role': role
            }

            for field in ['student_id', 'course', 'year_level', 'section', 'position']:
                val = data.get(field)
                if val:
                    user_data[field] = str(val).strip()

            supabase.table('users').insert(user_data).execute()

            reg_body = f"""Hello {full_name},

Welcome to Regis Marie College!

Your portal account has been successfully created.

Account Details:
----------------
Registered Email: {email}
Temporary Password: {password}

Best regards,
Registrar Office
Regis Marie College
"""
            send_email_api(
                to_recipients=email,
                subject="Regis Marie College - Account Registration Confirmation",
                body_text=reg_body
            )

            if is_ajax:
                return jsonify({"success": True, "message": "Account created and confirmation email dispatched."}), 201

            flash("Registration successful! Confirmation email dispatched.", "success")
            return redirect(url_for('login'))

        except Exception as err:
            print(f"❌ Registration Error: {err}")
            if is_ajax:
                return jsonify({"success": False, "message": str(err)}), 500
            flash(f"Error registering user: {err}", "error")
            return redirect(url_for('register'))

    response = make_response(render_template('register.html'))
    return prevent_caching(response)

@app.route('/logout')
@app.route('/logout.html')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    response = make_response(redirect(url_for('login')))
    return prevent_caching(response)

# =========================================
# 👤 ACTIVE USER SESSION API ENDPOINT
# =========================================
@app.route('/api/current-user')
def get_current_user():
    if 'user_id' not in session:
        return jsonify({"authenticated": False}), 401
    
    return jsonify({
        "authenticated": True,
        "user_id": session.get('user_id'),
        "full_name": session.get('full_name'),
        "email": session.get('email'),
        "role": session.get('role')
    }), 200

# =========================================
# 🔑 WEB PUSH TOKEN SUBSCRIPTION ENDPOINTS
# =========================================
@app.route('/api/vapid-public-key', methods=['GET'])
def get_vapid_public_key():
    """Provides VAPID public key dynamically to client PWA scripts."""
    key = os.environ.get("VAPID_PUBLIC_KEY") or VAPID_PUBLIC_KEY
    return jsonify({"publicKey": key}), 200

@app.route('/api/save-subscription', methods=['POST'])
def save_subscription():
    """Stores client device push subscription endpoints in Supabase."""
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    
    if not user_id:
        user_id = data.get('user_id')

    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    endpoint = data.get('endpoint')
    keys = data.get('keys', {})
    p256dh = keys.get('p256dh')
    auth = keys.get('auth')

    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Invalid push subscription payload"}), 400

    try:
        clean_user_id = str(user_id).strip()
        supabase.table('push_subscriptions').upsert({
            'user_id': clean_user_id,
            'endpoint': endpoint,
            'p256dh': p256dh,
            'auth': auth
        }, on_conflict='endpoint').execute()
        
        return jsonify({"success": True, "message": "Push token registered successfully"}), 200
    except Exception as err:
        print(f"❌ Push token registration error: {err}")
        return jsonify({"error": str(err)}), 500

# =======================================================
# 🛡️ UNIFIED MULTIMODAL SAFETY & CONDUCT PIPELINE
# =======================================================
import re
import json
import os
import base64
import unicodedata
import requests

# Google GenAI SDK (Gemini Setup)
try:
    from google import genai
    from google.genai import types
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    GEMINI_SDK_AVAILABLE = False
    print("⚠️ google-genai SDK missing. Ensure google-genai>=1.0.0 is in requirements.txt.")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
gemini_client = None
ACTIVE_GEMINI_MODEL = "gemini-1.5-flash-002"

if GEMINI_SDK_AVAILABLE and GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options={'api_version': 'v1beta'}
        )
        print("✅ Gemini client initialized successfully on v1beta.", flush=True)

        probe_candidates = [
            os.environ.get("GEMINI_MODEL", "").strip(),
            "gemini-1.5-flash-002",
            "gemini-1.5-flash",
            "gemini-2.0-flash-001",
            "gemini-1.5-pro-002"
        ]
        for candidate in probe_candidates:
            if not candidate or candidate in ["gemini-2.0-flash", "gemini-2.5-flash"]:
                continue
            try:
                gemini_client.models.generate_content(
                    model=candidate,
                    contents="ping",
                    config=types.GenerateContentConfig(max_output_tokens=1)
                )
                ACTIVE_GEMINI_MODEL = candidate
                print(f"🎯 Verified live Gemini model: {ACTIVE_GEMINI_MODEL}", flush=True)
                break
            except Exception as probe_err:
                print(f"⚠️ Model {candidate} unavailable: {probe_err}", flush=True)

    except Exception as e:
        print(f"❌ Failed to initialize Gemini Client: {e}", flush=True)

# --- 1. FILE & EXTENSION SECURITY WHITELISTS ---
BLOCKED_EXTENSIONS = {
    'exe', 'bat', 'cmd', 'sh', 'vbs', 'vbe', 'js', 'jse', 'wsf', 'wsh',
    'scr', 'msi', 'com', 'pif', 'hta', 'cpl', 'jar', 'apk', 'bin',
    'ps1', 'py', 'php', 'asp', 'aspx', 'jsp', 'cgi', 'zip', 'rar', '7z', 'tar', 'gz'
}

ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'csv',
    'png', 'jpg', 'jpeg', 'webp'
}

# --- 2. DETERMINISTIC REGEX RULES & CIPHER MAPS ---
URL_STRICT_REGEX = re.compile(
    r'(https?://\S+|www\.\S+|\b[a-zA-Z0-9.-]+\.(?:com|org|net|edu|gov|ph|io|me|xyz|app|top|online|site|link)\b)',
    re.IGNORECASE
)

ASCII_SEXUAL_PATTERNS = [
    r'(?:8|c|C)[=\-_~]{1,}(?:D|\([\-\)]*\)|>|3|o|O)',
    r'(?:D|3)[=\-_~]{1,}(?:8|c|C)',
    r'\(\s*\.\s*[yY]\s*\.\s*\)'
]

EMOJI_PATTERNS = [
    r'🖕',
    r'(?:🍆|🍌|🌭|🥒)\s*(?:💦|💧|👅|🍑|🍩|👄)',
    r'👉\s*👌',
    r'(?:🍑|🍒)\s*(?:💦|👅|🍆)'
]

PROFANITY_PATTERNS = [
    # English Acronyms & Slurs
    r'\b(m+f+|m+o+f+o+|s+t+f+u+|w+t+f+|s+o+b+|f+c+k+|f+u+k+|f+c+k+i+n+|f+u+k+i+n+|f+k+|k+y+s+|p+o+s+)\b',
    r'\bf+u+c+k+(e+r+|i+n+g+|s+)?\b',
    r'\bs+h+i+t+(s+|t+y+)?\b',
    r'\bb+i+t+c+h+(e+s+)?\b',
    r'\ba+s+s+h+o+l+e+(s+)?\b',
    r'\b(bastard|cunt|dick|pussy|whore|slut|nude|nudes)\b',

    # Tagalog & National Slurs
    r'\bt+a+n+g+i+n+a+\b',
    r'\b(tang-ina|tngina|putangina|ptngina|tangi|puta|pota|pakshet|pakyu)\b',
    r'\bg+a+g+o+\b',
    r'\bb+o+b+o+\b',
    r'\bu+l+o+l+\b',
    r'\bk+u+p+a+l+\b',
    r'\b(inutil|tarantado|tado|siraulo|hayop|walanghiya)\b',
    r'\b(kantot|kntot|titi|burat|puke|pekpek|pokpok|bayag|tamod|bulbol)\b',

    # Bisaya / Cebuano Slurs
    r'\by+a+w+a+\b',
    r'\bb+i+l+a+t+\b',
    r'\bp+i+s+t+i+\b',
    r'\bp+e+s+t+e+\b',
    r'\ba+t+a+y+\b',
    r'\bk+a+y+a+t+\b',
    r'\b(buang|boang|bwang|oten|utin|lubot|bayot)\b',

    # Ilocano Slurs
    r'\bu+k+i+n+a+m+\b',
    r'\bo+k+i+n+a+m+\b',
    r'\b(ukinana|okinana|bagtit|buto)\b',

    # Hiligaynon / Waray / Regional
    r'\bl+i+n+t+i+\b',
    r'\b(lintian|buray|yudiputa|taksyapo|danayda)\b',
    r'\b(iyot|iyotan)\b'
]

# Unbounded sub-string patterns for squashed/evasive text
SUBSTRING_PROFANITIES = [
    "tangina", "putangina", "gago", "bobo", "ulol", "kupal", 
    "kantot", "burat", "pekpek", "yawa", "bilat", "pisti", "ukinam"
]

MORSE_MAP = {
    '.-': 'a', '-...': 'b', '-.-.': 'c', '-..': 'd', '.': 'e',
    '..-.': 'f', '--.': 'g', '....': 'h', '..': 'i', '.---': 'j',
    '-.-': 'k', '.-..': 'l', '--': 'm', '-.': 'n', '---': 'o',
    '.--.': 'p', '--.-': 'q', '.-.': 'r', '...': 's', '-': 't',
    '..-': 'u', '...-': 'v', '.--': 'w', '-..-': 'x', '-.--': 'y',
    '--..': 'z', '-----': '0', '.----': '1', '..---': '2', '...--': '3',
    '....-': '4', '.....': '5', '-....': '6', '--...': '7', '---..': '8',
    '----.': '9'
}

HOMOGLYPH_MAP = {
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x',
    'А': 'a', 'В': 'b', 'Е': 'e', 'К': 'k', 'М': 'm', 'Н': 'h', 'О': 'o',
    'Р': 'p', 'С': 'c', 'Т': 't', 'Х': 'x', 'і': 'i', 'ї': 'i'
}

# --- 3. NORMALIZERS & DECODERS ---
def decode_morse_if_present(text):
    cleaned_symbols = text.replace('_', '-').strip()
    tokens = cleaned_symbols.split()
    morse_tokens = [t for t in tokens if re.fullmatch(r'[.\-]+', t)]
    if len(morse_tokens) >= 2:
        decoded = []
        for token in tokens:
            if token in MORSE_MAP:
                decoded.append(MORSE_MAP[token])
            elif token == '/':
                decoded.append(' ')
        return "".join(decoded).strip()
    return ""

def decode_binary_if_present(text):
    raw_binary = re.sub(r'[^01]', '', text.strip())
    if len(raw_binary) >= 16 and len(raw_binary) % 8 == 0:
        try:
            chunks = [raw_binary[i:i+8] for i in range(0, len(raw_binary), 8)]
            return "".join(chr(int(b, 2)) for b in chunks).strip()
        except Exception:
            pass

    tokens = text.strip().split()
    binary_tokens = [t for t in tokens if len(t) == 8 and re.fullmatch(r'[01]+', t)]
    if len(binary_tokens) >= 2:
        try:
            return "".join(chr(int(b, 2)) for b in binary_tokens).strip()
        except Exception:
            return ""
    return ""

def strip_invisible_characters(text):
    return re.sub(r'[\u200B-\u200D\uFEFF\u00AD\u2060\u180E]', '', text)

def normalize_deep_moderation(text):
    text = strip_invisible_characters(text)
    for cyr, lat in HOMOGLYPH_MAP.items():
        text = text.replace(cyr, lat)
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8').lower()

    char_map = {
        '8': 'b', '0': 'o', '6': 'g', '9': 'g',
        '@': 'a', '4': 'a', '3': 'e', '1': 'i',
        '!': 'i', '$': 's', '5': 's', '7': 't'
    }
    translated = text
    for char, repl in char_map.items():
        translated = translated.replace(char, repl)

    dense = re.sub(r'[^a-z0-9]', '', translated)
    squashed_dense = re.sub(r'(.)\1+', r'\1', dense)
    condensed_words = re.sub(r'(?<=\b\w)\s+(?=\w\b)', '', translated)
    cleaned_words = re.sub(r'[^a-z0-9\s]', '', condensed_words)

    return text, cleaned_words, squashed_dense

def evaluate_deterministic_gate(message_text):
    """0ms local heuristic check for slurs, ciphers, and leetspeak."""
    if not message_text:
        return True, ""

    if re.search(r'(giphy\.com|tenor\.com|\.gif(\?.*)?$)', message_text, re.IGNORECASE):
        return False, "Animated GIFs and external meme links are prohibited."

    for pattern in ASCII_SEXUAL_PATTERNS:
        if re.search(pattern, message_text):
            return False, "Inappropriate ASCII drawings detected."

    for pattern in EMOJI_PATTERNS:
        if re.search(pattern, message_text):
            return False, "Sexually suggestive or offensive emojis detected."

    raw_text, cleaned_words, squashed_dense = normalize_deep_moderation(message_text)
    decoded_morse = decode_morse_if_present(message_text)
    decoded_binary = decode_binary_if_present(message_text)

    # Check bounded patterns on space-preserved words
    word_candidates = [cleaned_words]
    if decoded_morse:
        word_candidates.append(decoded_morse)
    if decoded_binary:
        word_candidates.append(decoded_binary)

    for wc in word_candidates:
        for pattern in PROFANITY_PATTERNS:
            if re.search(pattern, wc):
                return False, "Offensive language, slurs, or hostile abbreviations detected."

    # Check dense squashed string against sub-string evasions
    for sub in SUBSTRING_PROFANITIES:
        if sub in squashed_dense:
            return False, "Prohibited language or evasive phrasing detected."

    return True, ""

# --- 4. UNIFIED GEMINI 2.5 FLASH PROCTOR ---
GEMINI_UNIFIED_PROMPT = """
You are the Official Academic Safety & Student Conduct Proctor for Regis Marie College (RMC).
You enforce an absolute ZERO TOLERANCE policy for adult, explicit, or inappropriate content.

CRITICAL VISUAL NSFW DIRECTIVE:
- ABSOLUTE ZERO TOLERANCE for nudity, adult anatomy, genitalia (male or female private parts, penis, vagina, breasts), sex toys, sexual acts, or suggestive poses.
- If ANY nudity or sexual anatomy is visible in an image, you MUST REJECT IT IMMEDIATELY with allowed: false and reason: "Explicit adult content detected."

ACADEMIC CONDUCT RESTRICTIONS:
1. Academic Bribery: Direct offers of cash, GCash transfers, gift cards, or favors for grade adjustments.
2. Sexual Boundary Violations: Romantic advances, commenting on body/appearance, asking to meet privately off-campus.
3. Stalking & Intimidation: Inquiring about personal residence, vehicle, family members, or making threats.
4. Phishing & Credentials: Inquiring about master LMS passwords, OTPs, or accounts.
5. Hostile Insubordination: Aggressively demeaning faculty competence or demanding resignations.
6. Slurs & Regional Profanity: Profanity across English, Tagalog, Bisaya (yawa, bilat, pisti), or Ilocano (ukinam).
7. OCR Screenshot Inspection: Extract and evaluate all text inside images against the rules above.

RESPONSE FORMAT:
Respond ONLY with a strict JSON object (no markdown code blocks, no backticks):
{"allowed": true, "reason": ""}
OR
{"allowed": false, "reason": "Specific short violation explanation"}
"""

def evaluate_with_gemini_flash(text="", image_bytes=None, mime_type="image/jpeg"):
    """
    Multimodal inspection using Gemini API.
    Iterates through production models to ensure continuous uptime.
    """
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY missing. Proceeding on deterministic gate.")
        return True, ""

    candidate_models = [
        ACTIVE_GEMINI_MODEL,
        os.environ.get("GEMINI_MODEL", "").strip(),
        "gemini-1.5-flash-002",
        "gemini-1.5-flash",
        "gemini-2.0-flash-001",
        "gemini-1.5-pro-002"
    ]
    retired_models = {"gemini-2.0-flash", "gemini-2.5-flash"}
    candidate_models = [
        m for i, m in enumerate(candidate_models) 
        if m and m not in retired_models and m not in candidate_models[:i]
    ]

    contents_sdk = [GEMINI_UNIFIED_PROMPT]
    if text:
        contents_sdk.append(f"### STUDENT MESSAGE TEXT ###\n{text}\n### END MESSAGE TEXT ###")
    if image_bytes:
        contents_sdk.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

    last_error = ""

    for model_name in candidate_models:
        # --- Layer 1: Google GenAI SDK ---
        if gemini_client and GEMINI_SDK_AVAILABLE:
            try:
                response = gemini_client.models.generate_content(
                    model=model_name,
                    contents=contents_sdk,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0
                    )
                )

                if hasattr(response, 'candidates') and response.candidates:
                    finish_reason = str(getattr(response.candidates[0], 'finish_reason', ''))
                    if "SAFETY" in finish_reason:
                        return False, "Explicit adult or prohibited visual content blocked by AI safety proctor."

                response_text = (response.text or "").strip()
                if response_text:
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        verdict = json.loads(json_match.group(0))
                        return verdict.get("allowed", False), verdict.get("reason", "Prohibited content detected.")
            except Exception as sdk_err:
                err_msg = str(sdk_err)
                last_error = err_msg
                if any(kw in err_msg.lower() for kw in ["no longer available", "404", "not found"]):
                    continue
                if any(kw in err_msg.lower() for kw in ["safety", "blocked", "filter"]):
                    return False, "Explicit adult or prohibited visual content blocked by AI safety filters."

        # --- Layer 2: Bulletproof Direct v1beta REST Gateway Fallback ---
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            parts = [{"text": GEMINI_UNIFIED_PROMPT}]
            if text:
                parts.append({"text": f"### STUDENT MESSAGE TEXT ###\n{text}\n### END MESSAGE TEXT ###"})
            if image_bytes:
                b64_data = base64.b64encode(image_bytes).decode("utf-8")
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": b64_data
                    }
                })

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.0
                }
            }

            resp = requests.post(url, json=payload, timeout=8)
            data = resp.json()

            if resp.status_code != 200:
                api_err = data.get("error", {}).get("message", "Gateway Error")
                last_error = api_err
                if any(kw in api_err.lower() for kw in ["no longer available", "404", "not found"]):
                    continue
                return False, f"AI Gateway Error: {api_err[:100]}"

            candidates = data.get("candidates", [])
            if candidates:
                finish_reason = candidates[0].get("finishReason", "")
                if "SAFETY" in finish_reason:
                    return False, "Explicit adult or prohibited visual content blocked by AI safety filters."

                raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}").strip()
                json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                if json_match:
                    verdict = json.loads(json_match.group(0))
                    return verdict.get("allowed", False), verdict.get("reason", "Prohibited content detected.")
        except Exception as rest_err:
            last_error = str(rest_err)
            continue

    return False, f"AI Gateway Error: {last_error[:100] if last_error else 'All candidate models unavailable'}"

# --- 5. UNIFIED REAL-TIME MODERATION API ROUTE ---
@app.route('/api/ai-moderate', methods=['POST'])
@app.route('/api/ai-moderate/', methods=['POST'])
def ai_moderate():
    data = request.get_json(silent=True) or {}
    message_text = (data.get('message') or data.get('text') or '').strip()
    file_name = (data.get('file_name') or '').strip()
    image_b64 = data.get('image_base64') or None
    image_url = (data.get('image_url') or '').strip()
    is_teacher_dm = bool(data.get('is_teacher_dm', False))
    mime_type = data.get('mime_type', 'image/jpeg')

    # Gate 1: Consultation Boundary Checks
    if is_teacher_dm:
        if file_name or image_b64 or image_url:
            return jsonify({
                "allowed": False,
                "reason": "School Policy: Media transfers are strictly prohibited in teacher consultations."
            }), 200
        if URL_STRICT_REGEX.search(message_text):
            return jsonify({
                "allowed": False,
                "reason": "School Policy: External links are strictly prohibited in private consultations."
            }), 200

    # Gate 2: Blocked Extensions
    if file_name:
        ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
        if ext in BLOCKED_EXTENSIONS or (ALLOWED_EXTENSIONS and ext not in ALLOWED_EXTENSIONS):
            return jsonify({
                "allowed": False,
                "reason": f"Security Notice: File format (.{ext}) is prohibited."
            }), 200

    # Gate 3: Local Heuristics
    det_ok, det_reason = evaluate_deterministic_gate(message_text)
    if not det_ok:
        clean_reason = det_reason if det_reason.startswith("School Policy") else f"School Policy: {det_reason}"
        return jsonify({"allowed": False, "reason": clean_reason}), 200

    if not message_text and not image_b64 and not image_url:
        return jsonify({"allowed": True}), 200

    # Gate 4: Media Payload Setup
    img_bytes = None
    if image_b64:
        try:
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            img_bytes = base64.b64decode(image_b64)
        except Exception:
            return jsonify({"allowed": False, "reason": "Corrupted image payload received."}), 200
    elif image_url and not is_teacher_dm:
        try:
            resp = requests.get(image_url, timeout=4)
            if resp.status_code == 200:
                img_bytes = resp.content
                header_mime = resp.headers.get('Content-Type')
                if header_mime:
                    mime_type = header_mime
        except Exception:
            pass

    # Gate 5: Multimodal Gemini Flash Inspection
    allowed, reason = evaluate_with_gemini_flash(
        text=message_text,
        image_bytes=img_bytes,
        mime_type=mime_type
    )

    if not allowed:
        clean_reason = reason if reason.startswith("School Policy") else f"School Policy Violation: {reason}"
        return jsonify({"allowed": False, "reason": clean_reason}), 200

    return jsonify({"allowed": True}), 200

# --- 6. AI AUTO-PURGE SENTINEL ROUTE ---
VALID_PURGE_TABLES = {"group_messages", "private_messages", "chat_messages"}

@app.route('/api/ai-auto-purge', methods=['POST'])
@app.route('/api/ai-auto-purge/', methods=['POST'])
def ai_auto_purge():
    data = request.get_json(silent=True) or {}
    table_name = data.get('table')
    raw_message_id = data.get('message_id')
    message_text = (data.get('message') or data.get('text') or '').strip()
    media_url = (data.get('media_url') or '').strip()
    media_type = (data.get('media_type') or '').strip()

    # Strict whitelist to prevent arbitrary table deletion
    if not raw_message_id or table_name not in VALID_PURGE_TABLES:
        return jsonify({"purged": False, "reason": "Invalid purge parameters or unauthorized table"}), 400

    target_id = int(raw_message_id) if str(raw_message_id).isdigit() else raw_message_id

    det_ok, det_reason = evaluate_deterministic_gate(message_text)
    is_malicious = not det_ok
    violation_reason = det_reason

    if not is_malicious and (message_text or (media_url and media_type == 'image')):
        img_bytes = None
        mime = "image/jpeg"
        if media_url and media_type == 'image':
            try:
                resp = requests.get(media_url, timeout=4)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    mime = resp.headers.get('Content-Type', 'image/jpeg')
            except Exception:
                pass

        allowed, ai_reason = evaluate_with_gemini_flash(
            text=message_text,
            image_bytes=img_bytes,
            mime_type=mime
        )
        if not allowed:
            is_malicious = True
            violation_reason = ai_reason

    if is_malicious:
        try:
            supabase.table(table_name).delete().eq('id', target_id).execute()
            if media_url and "supabase.co/storage/v1/object/public/" in media_url:
                try:
                    parts = media_url.split('/public/')[1].split('/', 1)
                    bucket, file_path = parts[0], parts[1]
                    supabase.storage.from_(bucket).remove([file_path])
                except Exception:
                    pass
            return jsonify({"purged": True, "message_id": target_id, "reason": violation_reason}), 200
        except Exception as db_err:
            return jsonify({"purged": False, "error": str(db_err)}), 500

    return jsonify({"purged": False, "status": "safe"}), 200
    
# =========================================
# 🏠 CORE DASHBOARD & GLOBAL PORTALS
# =========================================
@app.route('/landpage')
@app.route('/landpage.html')
def landpage():
    if 'user_id' not in session:
        flash("Please sign in to access your portal dashboard.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'landpage.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/account')
@app.route('/account.html')
def account_page():
    if 'user_id' not in session:
        flash("Please sign in to access your account profile.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'account.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/calendar')
@app.route('/calendar.html')
def calendar_page():
    if 'user_id' not in session:
        flash("Please sign in to access your calendar.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'calendar.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/archive')
@app.route('/archive.html')
def archive_page():
    if 'user_id' not in session:
        flash("Please sign in to access the archive vault.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'archive.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

# =========================================
# 🛠️ CREATION & UPDATE MODULE ROUTES
# =========================================
@app.route('/create')
@app.route('/create.html')
def create_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role != 'TEACHER':
        flash("Creating classes and groups is restricted strictly to faculty instructors.", "warning")
        return redirect(url_for('landpage'))
    
    response = make_response(render_template(
        'create.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/join')
@app.route('/join.html')
def join_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role != 'STUDENT':
        flash("Enrolling in classes via join code is restricted strictly to students.", "warning")
        return redirect(url_for('landpage'))
    
    response = make_response(render_template(
        'join.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/update')
@app.route('/update.html')
def update_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role != 'TEACHER':
        flash("Updating curriculum content is restricted to faculty instructors.", "warning")
        return redirect(url_for('landpage'))
        
    response = make_response(render_template(
        'update.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/update1')
@app.route('/update1.html')
def update1_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role != 'TEACHER':
        flash("Updating class and group settings is restricted to faculty instructors.", "warning")
        return redirect(url_for('landpage'))
        
    response = make_response(render_template(
        'update1.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

# =========================================
# 📘 CLASSROOM, LESSON & ACTIVITY MODULES
# =========================================
@app.route('/class')
@app.route('/class.html')
def class_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'class.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/group')
@app.route('/group.html')
def group_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'group.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/message-teacher')
@app.route('/message-teacher.html')
@app.route('/messageteacher')
@app.route('/messageteacher.html')
def message_teacher_page():
    if 'user_id' not in session:
        flash("Please sign in to access consultation messaging.", "warning")
        return redirect(url_for('login'))

    response = make_response(render_template(
        'message-teacher.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/private-message')
@app.route('/private-message.html')
@app.route('/privatemessage')
@app.route('/privatemessage.html')
def private_message_page():
    if 'user_id' not in session:
        flash("Please sign in to access your private messages inbox.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'private-message.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/lesson')
@app.route('/lesson.html')
def lesson_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role != 'TEACHER':
        flash("Publishing lessons is restricted strictly to faculty instructors.", "warning")
        return redirect(url_for('landpage'))

    response = make_response(render_template(
        'lesson.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/lessons')
@app.route('/lessons.html')
def lessons_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'lessons.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/activity')
@app.route('/activity.html')
def activity_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role != 'TEACHER':
        flash("Publishing activities is restricted strictly to faculty instructors.", "warning")
        return redirect(url_for('landpage'))

    response = make_response(render_template(
        'activity.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/activitysubmit.html')
@app.route('/activitysubmit')
@app.route('/submit.html')
@app.route('/submit')
def activitysubmit_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'activitysubmit.html', 
        full_name=session.get('full_name'), 
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/submissions')
@app.route('/submissions.html')
@app.route('/submission')
@app.route('/submission.html')
def submissions_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role == 'STUDENT':
        flash("Access restricted: Submissions review is reserved for faculty and administrators.", "warning")
        return redirect(url_for('dashboard_page'))

    response = make_response(render_template(
        'submissions.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/studentwork')
@app.route('/studentwork.html')
def studentwork_page():
    if 'user_id' not in session:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role == 'STUDENT':
        flash("Access restricted: Student work evaluation is reserved for Teachers and Administrators.", "warning")
        return redirect(url_for('dashboard_page'))

    response = make_response(render_template(
        'studentwork.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

# =========================================
# 📧 MULTI-CHANNEL NOTIFICATION ENDPOINT (EMAIL + PUSH)
# =========================================
@app.route('/api/notify-users', methods=['POST'])
def notify_users():
    data = request.json or {}
    class_title = data.get('class_title', 'Your Class')
    item_title = data.get('title', 'Course Material')
    notif_type = data.get('type', 'new_activity')
    student_emails = data.get('student_emails', [])
    student_ids = data.get('student_ids', [])
    details = data.get('details', 'Check portal for updates.')
    target_url = data.get('url', '/notify.html')

    type_messages = {
        'new_activity': ('New Activity Posted', 'A new activity has been posted'),
        'updated_activity': ('Activity Updated', 'An activity has been updated'),
        'new_lesson': ('New Lesson Uploaded', 'New lesson materials have been uploaded'),
        'updated_lesson': ('Lesson Updated', 'Lesson materials have been updated')
    }
    
    subject_prefix, body_action = type_messages.get(notif_type, ('Academic Update', 'An update has been made'))

    if student_emails:
        email_body = f"""Hello Regis Marie College Student,

{body_action} in your class: {class_title}.

Title: {item_title}
Details: {details}

Please log into your portal to view full requirements and updates.

Best regards,
Academic Portal
Regis Marie College
"""
        send_email_api(
            to_recipients=student_emails,
            subject=f"Regis Marie College - {subject_prefix}: {item_title}",
            body_text=email_body
        )

    if student_ids:
        try:
            clean_ids = []
            for sid in student_ids:
                if str(sid).isdigit():
                    clean_ids.append(int(sid))
                clean_ids.append(str(sid))

            response = supabase.table('push_subscriptions').select('*').in_('user_id', clean_ids).execute()
            subscriptions = response.data or []

            push_payload = json.dumps({
                "title": f"🔔 {subject_prefix}: {item_title}",
                "body": f"{class_title} • {details}",
                "url": target_url,
                "unreadCount": 1
            })

            for sub in subscriptions:
                sub_info = {
                    "endpoint": sub["endpoint"],
                    "keys": {
                        "p256dh": sub["p256dh"],
                        "auth": sub["auth"]
                    }
                }
                try:
                    webpush(
                        subscription_info=sub_info,
                        data=push_payload,
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims={"sub": VAPID_CLAIM_EMAIL}
                    )
                except WebPushException as ex:
                    if ex.response and ex.response.status_code in [404, 410]:
                        supabase.table('push_subscriptions').delete().eq('endpoint', sub["endpoint"]).execute()

            print(f"📱 Mobile push notifications dispatched to {len(subscriptions)} active device(s).")
        except Exception as e:
            print(f"⚠️ Mobile push dispatch error: {e}")

    return jsonify({"message": "Multi-channel notifications dispatched successfully"}), 200

@app.route('/api/notify-activity', methods=['POST'])
def notify_activity():
    return notify_users()

@app.route('/api/clear-activity-reminders', methods=['POST'])
def clear_activity_reminders():
    """Removes lingering deadline reminders once a student submits their activity."""
    data = request.json or {}
    user_id = data.get('user_id') or session.get('user_id')
    activity_id = data.get('activity_id')
    
    if not user_id or not activity_id:
        return jsonify({"success": False, "message": "Missing user_id or activity_id"}), 400

    try:
        u_ids = [int(user_id)] if str(user_id).isdigit() else [str(user_id)]
        if str(user_id).isdigit():
            u_ids.append(str(user_id))

        act_ids = [int(activity_id)] if str(activity_id).isdigit() else [str(activity_id)]
        if str(activity_id).isdigit():
            act_ids.append(str(activity_id))

        supabase.table('notifications').delete()\
            .in_('user_id', u_ids)\
            .in_('activity_id', act_ids)\
            .execute()

        return jsonify({"success": True, "message": "Activity reminders cleared"}), 200
    except Exception as e:
        print(f"⚠️ Clear activity reminders notice: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# =========================================
# ⏰ AUTOMATED DEADLINE & REMINDER ENGINE (APScheduler)
# =========================================
def check_activity_deadlines_and_reminders():
    """Runs every minute in the background to check deadlines and trigger milestone & penalty reminders."""
    try:
        now = datetime.now(timezone.utc)
        
        activities_resp = supabase.table('activities').select('*').execute()
        activities = activities_resp.data or []

        for act in activities:
            deadline_str = act.get('deadline') or act.get('due_date')
            if not deadline_str:
                continue
            
            try:
                deadline = datetime.fromisoformat(str(deadline_str).replace('Z', '+00:00'))
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
            except Exception:
                continue

            time_left = deadline - now
            total_seconds = time_left.total_seconds()

            class_id = act.get('class_id')
            activity_id = act.get('id')
            activity_title = act.get('title', 'Assignment')
            
            if not class_id or not activity_id:
                continue

            enroll_rows = []
            try:
                e1 = supabase.table('class_memberships').select('*').eq('class_id', class_id).execute()
                enroll_rows = e1.data or []
            except Exception:
                pass

            if not enroll_rows and str(class_id).isdigit():
                try:
                    e2 = supabase.table('class_memberships').select('*').eq('class_id', int(class_id)).execute()
                    enroll_rows = e2.data or []
                except Exception:
                    pass

            if not enroll_rows:
                continue

            candidate_uids = set()
            for row in enroll_rows:
                for key in ['user_id', 'student_id', 'userId', 'studentId']:
                    val = row.get(key)
                    if val is not None and str(val).strip():
                        candidate_uids.add(str(val).strip())

            if not candidate_uids:
                continue

            subs_rows = []
            try:
                s1 = supabase.table('submissions').select('*').eq('activity_id', activity_id).execute()
                subs_rows = s1.data or []
            except Exception:
                pass

            if not subs_rows and str(activity_id).isdigit():
                try:
                    s2 = supabase.table('submissions').select('*').eq('activity_id', int(activity_id)).execute()
                    subs_rows = s2.data or []
                except Exception:
                    pass

            submitted_identifiers = set()
            for sub in subs_rows:
                st = str(sub.get('status', '')).strip().lower()
                if st == 'draft':
                    continue
                for key in ['student_id', 'user_id', 'studentId', 'userId']:
                    val = sub.get(key)
                    if val is not None and str(val).strip():
                        submitted_identifiers.add(str(val).strip())

            search_ids = []
            for cid in candidate_uids:
                if cid.isdigit():
                    search_ids.append(int(cid))
                search_ids.append(cid)

            enrolled_users_list = []
            try:
                u_resp = supabase.table('users').select('id, email, full_name, student_id').in_('id', search_ids).execute()
                enrolled_users_list = u_resp.data or []
            except Exception:
                pass

            try:
                u_resp_stud = supabase.table('users').select('id, email, full_name, student_id').in_('student_id', [str(c) for c in candidate_uids]).execute()
                existing_u_ids = {str(u['id']) for u in enrolled_users_list}
                for u in (u_resp_stud.data or []):
                    if str(u.get('id')) not in existing_u_ids:
                        enrolled_users_list.append(u)
                        existing_u_ids.add(str(u.get('id')))
            except Exception:
                pass

            unsubmitted_students = []
            for u in enrolled_users_list:
                uid_str = str(u.get('id', '')).strip()
                stud_no = str(u.get('student_id', '')).strip()

                has_submitted = False
                if uid_str and uid_str in submitted_identifiers:
                    has_submitted = True
                elif stud_no and stud_no in submitted_identifiers:
                    has_submitted = True

                if not has_submitted:
                    unsubmitted_students.append(u)

            if not unsubmitted_students:
                continue

            student_emails = [s['email'] for s in unsubmitted_students if s.get('email')]
            student_ids = [str(s['id']) for s in unsubmitted_students if s.get('id')]

            if not student_emails and not student_ids:
                continue

            notif_log = act.get('notification_log') or {}
            if isinstance(notif_log, str):
                try:
                    notif_log = json.loads(notif_log)
                except Exception:
                    notif_log = {}

            if 86400 <= total_seconds <= 90000 and not notif_log.get('1d'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "1 Day Left", "Your activity deadline is in 24 hours. Please complete and submit your work.", activity_id=activity_id)
                notif_log['1d'] = True
                update_notif_log(activity_id, notif_log)
            elif 57000 <= total_seconds <= 58200 and not notif_log.get('16h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "16 Hours Left", "16 hours remaining before your activity deadline.", activity_id=activity_id)
                notif_log['16h'] = True
                update_notif_log(activity_id, notif_log)
            elif 28200 <= total_seconds <= 29400 and not notif_log.get('8h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "8 Hours Left", "8 hours left until submission cutoff.", activity_id=activity_id)
                notif_log['8h'] = True
                update_notif_log(activity_id, notif_log)
            elif 13800 <= total_seconds <= 15000 and not notif_log.get('4h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "4 Hours Left", "4 hours remaining. Time is running short!", activity_id=activity_id)
                notif_log['4h'] = True
                update_notif_log(activity_id, notif_log)
            elif 6600 <= total_seconds <= 7800 and not notif_log.get('2h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "2 Hours Left", "Only 2 hours left before deadline!", activity_id=activity_id)
                notif_log['2h'] = True
                update_notif_log(activity_id, notif_log)
            elif 3000 <= total_seconds <= 4200 and not notif_log.get('1h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "1 Hour Left", "Final hour warning! Submit your work now.", activity_id=activity_id)
                notif_log['1h'] = True
                update_notif_log(activity_id, notif_log)
            elif 1500 <= total_seconds <= 2100 and not notif_log.get('30m'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "30 Minutes Left", "30 minutes remaining before submission lock.", activity_id=activity_id)
                notif_log['30m'] = True
                update_notif_log(activity_id, notif_log)
            elif 600 <= total_seconds <= 1200 and not notif_log.get('15m'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "15 Minutes Left", "Urgent: 15 minutes left!", activity_id=activity_id)
                notif_log['15m'] = True
                update_notif_log(activity_id, notif_log)
            elif 300 <= total_seconds <= 900 and not notif_log.get('10m'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "10 Minutes Left", "Only 10 minutes remaining!", activity_id=activity_id)
                notif_log['10m'] = True
                update_notif_log(activity_id, notif_log)
            elif 0 <= total_seconds <= 300 and not notif_log.get('5m'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "5 Minutes Left", "Final 5 minutes! Submit immediately to avoid penalties.", activity_id=activity_id)
                notif_log['5m'] = True
                update_notif_log(activity_id, notif_log)
            elif -300 <= total_seconds < 0 and not notif_log.get('missed_0h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "DEADLINE MISSED - Penalty Notice", "You failed to turn in this activity before the deadline. Minus points have been applied to your grade record.", activity_id=activity_id)
                notif_log['missed_0h'] = True
                update_notif_log(activity_id, notif_log)
            elif -90000 <= total_seconds <= -86400 and not notif_log.get('missed_24h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "CRITICAL: 24h Past Deadline", "You have failed to comply within 24 hours of the deadline. A severe grade penalty has been applied.", activity_id=activity_id)
                notif_log['missed_24h'] = True
                update_notif_log(activity_id, notif_log)

    except Exception as e:
        print(f"⚠️ Deadline background scheduler error: {e}")

def send_reminder_cluster(emails, user_ids, title, heading, details, activity_id=None):
    if emails:
        reminder_body = f"""Hello Regis Marie College Student,

Reminder Alert: {heading}
Activity: {title}

Details: {details}

Please log into your portal immediately to complete and turn in your requirements.

Best regards,
Academic Portal
Regis Marie College
"""
        send_email_api(
            to_recipients=emails,
            subject=f"Regis Marie College - Reminder: {heading} ({title})",
            body_text=reminder_body
        )

    if user_ids:
        try:
            notif_rows = []
            now_iso = datetime.now(timezone.utc).isoformat()
            for uid in user_ids:
                parsed_uid = int(uid) if str(uid).isdigit() else str(uid)
                notif_rows.append({
                    "user_id": parsed_uid,
                    "title": f"⏰ {heading}: {title}",
                    "message": details,
                    "type": "activity",
                    "target_id": str(activity_id) if activity_id else None,
                    "activity_id": int(activity_id) if str(activity_id).isdigit() else str(activity_id) if activity_id else None,
                    "is_read": False,
                    "created_at": now_iso
                })
            if notif_rows:
                supabase.table('notifications').insert(notif_rows).execute()
        except Exception as notif_err:
            print(f"⚠️ In-app reminder creation notice: {notif_err}")

        try:
            push_uids = []
            for u in user_ids:
                if str(u).isdigit():
                    push_uids.append(int(u))
                push_uids.append(str(u))

            response = supabase.table('push_subscriptions').select('*').in_('user_id', push_uids).execute()
            subscriptions = response.data or []

            push_payload = json.dumps({
                "title": f"⚠️ {heading}: {title}",
                "body": details,
                "url": "/notify.html",
                "unreadCount": 1
            })

            for sub in subscriptions:
                sub_info = {
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}
                }
                try:
                    webpush(
                        subscription_info=sub_info,
                        data=push_payload,
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims={"sub": VAPID_CLAIM_EMAIL}
                    )
                except WebPushException:
                    pass
        except Exception as e:
            print(f"⚠️ Reminder push error: {e}")

def update_notif_log(activity_id, log_dict):
    try:
        res = supabase.table('activities').update({'notification_log': log_dict}).eq('id', activity_id).execute()
        if not res.data and str(activity_id).isdigit():
            supabase.table('activities').update({'notification_log': log_dict}).eq('id', int(activity_id)).execute()
    except Exception as e:
        print(f"Error updating notification log: {e}")

try:
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(func=check_activity_deadlines_and_reminders, trigger="interval", seconds=60)
    scheduler.start()
except Exception as sched_err:
    print(f"⚠️ APScheduler startup warning: {sched_err}")

# =========================================
# 📊 ANALYTICS, DASHBOARDS & NOTIFICATIONS
# =========================================
@app.route('/dashboard')
@app.route('/dashboard.html')
def dashboard_page():
    if 'user_id' not in session:
        flash("Please sign in to access your student dashboard.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'dashboard.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/classdashboard')
@app.route('/classdashboard.html')
def classdashboard_page():
    if 'user_id' not in session:
        flash("Please sign in to access dashboard analytics.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role == 'STUDENT':
        return redirect(url_for('dashboard_page'))

    response = make_response(render_template(
        'classdashboard.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/studentdashboard')
@app.route('/studentdashboard.html')
def studentdashboard_page():
    if 'user_id' not in session:
        flash("Please sign in to access student analytics.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role == 'STUDENT':
        return redirect(url_for('dashboard_page'))

    response = make_response(render_template(
        'studentdashboard.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/grades')
@app.route('/grades.html')
def grades_page():
    if 'user_id' not in session:
        flash("Please sign in to access grades.", "warning")
        return redirect(url_for('login'))
    
    user_role = str(session.get('role', '')).upper()
    if user_role == 'STUDENT':
        return redirect(url_for('studentgrades_page'))

    response = make_response(render_template(
        'grades.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/studentgrades')
@app.route('/studentgrades.html')
def studentgrades_page():
    if 'user_id' not in session:
        flash("Please sign in to access student gradebook.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'studentgrades.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/review')
@app.route('/review.html')
def review_page():
    if 'user_id' not in session:
        flash("Please sign in to access review details.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'review.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

@app.route('/notify')
@app.route('/notify.html')
def notify_page():
    if 'user_id' not in session:
        flash("Please sign in to access notifications.", "warning")
        return redirect(url_for('login'))
    
    response = make_response(render_template(
        'notify.html', 
        full_name=session.get('full_name'), 
        role=session.get('role'),
        email=session.get('email'),
        user_id=session.get('user_id')
    ))
    return prevent_caching(response)

# =========================================
# 🚀 SERVER STARTUP
# =========================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)