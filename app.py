import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta
import requests
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

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "vapid_private.pem")
VAPID_CLAIM_EMAIL = "mailto:regismariecollege100@gmail.com"

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
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = (request.form.get('password') or '').strip()

        try:
            response = supabase.table('users').select('*').eq('email', email).eq('password', password).execute()
            users = response.data

            if users and len(users) > 0:
                user = users[0]
                session['user_id'] = str(user['id'])
                session['full_name'] = user.get('full_name', '')
                session['email'] = user.get('email', '')
                session['role'] = str(user.get('role', 'STUDENT')).upper()

                print(f"👤 Logged in User: {session['full_name']} | ID: {session['user_id']} | Role: {session['role']}")
                return redirect(url_for('landpage'))
            else:
                flash("Invalid email or password.", "error")
                return redirect(url_for('login'))

        except Exception as err:
            print(f"❌ Login Database Error: {err}")
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

# =======================================================
# 🛡️ MULTILINGUAL AI MODERATION, NSFW & MALWARE CHECKER
# =======================================================
BLOCKED_EXTENSIONS = {
    'exe', 'bat', 'cmd', 'sh', 'vbs', 'vbe', 'js', 'jse', 'wsf', 'wsh',
    'scr', 'msi', 'com', 'pif', 'hta', 'cpl', 'jar', 'apk', 'bin',
    'ps1', 'py', 'php', 'asp', 'aspx', 'jsp', 'cgi', 'zip', 'rar', '7z', 'tar', 'gz'
}

ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'csv',
    'png', 'jpg', 'jpeg', 'webp'
}

@app.route('/api/ai-moderate', methods=['POST'])
def ai_moderate():
    data = request.json or {}
    message_text = (data.get('message') or '').strip()
    image_url = (data.get('image_url') or '').strip()
    file_name = (data.get('file_name') or '').strip()

    if file_name:
        ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
        if ext in BLOCKED_EXTENSIONS or (ALLOWED_EXTENSIONS and ext not in ALLOWED_EXTENSIONS):
            return jsonify({
                "allowed": False,
                "reason": f"Security Notice: File extension (.{ext}) is prohibited to prevent malware and suspicious uploads."
            }), 200

    if not message_text and not image_url:
        return jsonify({"allowed": True}), 200

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"allowed": True}), 200

    moderation_input = []
    if message_text:
        moderation_input.append({
            "type": "text",
            "text": message_text
        })
    if image_url:
        moderation_input.append({
            "type": "image_url",
            "image_url": {"url": image_url}
        })

    try:
        req_payload = json.dumps({
            "model": "omni-moderation-latest",
            "input": moderation_input
        }).encode('utf-8')

        req = urllib.request.Request(
            "https://api.openai.com/v1/moderations",
            data=req_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
        )

        with urllib.request.urlopen(req, timeout=4) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            analysis = result.get("results", [{}])[0]

            if analysis.get("flagged", False):
                categories = [cat for cat, hit in analysis.get("categories", {}).items() if hit]

                reason = "Inappropriate content detected."
                if any("sexual" in cat for cat in categories):
                    reason = "School Policy Violation: Explicit, revealing, or inappropriate imagery/language is prohibited."
                elif any("hate" in cat or "harassment" in cat for cat in categories):
                    reason = "School Policy Violation: Harassment, profanity, or offensive language detected."
                elif any("violence" in cat for cat in categories):
                    reason = "School Policy Violation: Threatening or violent content detected."

                return jsonify({
                    "allowed": False,
                    "reason": reason
                }), 200

    except Exception as e:
        print(f"⚠️ AI Moderation offline fallback: {e}")

    return jsonify({"allowed": True}), 200

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
            response = supabase.table('push_subscriptions').select('*').in_('user_id', student_ids).execute()
            subscriptions = response.data or []

            push_payload = json.dumps({
                "title": f"🔔 {subject_prefix}: {item_title}",
                "body": f"{class_title} • {details}",
                "url": "/dashboard.html",
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
            deadline_str = act.get('deadline')
            if not deadline_str:
                continue
            
            deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
            time_left = deadline - now
            total_seconds = time_left.total_seconds()

            class_id = act.get('class_id')
            activity_id = act.get('id')
            activity_title = act.get('title', 'Assignment')
            
            enroll_resp = supabase.table('class_memberships').select('user_id').eq('class_id', class_id).execute()
            enrolled_users = [row['user_id'] for row in (enroll_resp.data or [])]

            if not enrolled_users:
                continue

            subs_resp = supabase.table('submissions').select('student_id').eq('activity_id', activity_id).execute()
            submitted_users = {sub['student_id'] for sub in (subs_resp.data or [])}

            unsubmitted_users = [uid for uid in enrolled_users if uid not in submitted_users]
            if not unsubmitted_users:
                continue

            users_resp = supabase.table('users').select('id, email, full_name').in_('id', unsubmitted_users).execute()
            target_students = users_resp.data or []
            student_emails = [s['email'] for s in target_students if s.get('email')]
            student_ids = [str(s['id']) for s in target_students]

            notif_log = act.get('notification_log') or {}

            # Checkpoints (1 day down to 5 minutes)
            if 86400 <= total_seconds <= 90000 and not notif_log.get('1d'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "1 Day Left", "Your activity deadline is in 24 hours. Please complete and submit your work.")
                notif_log['1d'] = True
                update_notif_log(activity_id, notif_log)
            elif 57000 <= total_seconds <= 58200 and not notif_log.get('16h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "16 Hours Left", "16 hours remaining before your activity deadline.")
                notif_log['16h'] = True
                update_notif_log(activity_id, notif_log)
            elif 28200 <= total_seconds <= 29400 and not notif_log.get('8h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "8 Hours Left", "8 hours left until submission cutoff.")
                notif_log['8h'] = True
                update_notif_log(activity_id, notif_log)
            elif 13800 <= total_seconds <= 15000 and not notif_log.get('4h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "4 Hours Left", "4 hours remaining. Time is running short!")
                notif_log['4h'] = True
                update_notif_log(activity_id, notif_log)
            elif 6600 <= total_seconds <= 7800 and not notif_log.get('2h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "2 Hours Left", "Only 2 hours left before deadline!")
                notif_log['2h'] = True
                update_notif_log(activity_id, notif_log)
            elif 3000 <= total_seconds <= 4200 and not notif_log.get('1h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "1 Hour Left", "Final hour warning! Submit your work now.")
                notif_log['1h'] = True
                update_notif_log(activity_id, notif_log)
            elif 1500 <= total_seconds <= 2100 and not notif_log.get('30m'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "30 Minutes Left", "30 minutes remaining before submission lock.")
                notif_log['30m'] = True
                update_notif_log(activity_id, notif_log)
            elif 600 <= total_seconds <= 1200 and not notif_log.get('15m'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "15 Minutes Left", "Urgent: 15 minutes left!")
                notif_log['15m'] = True
                update_notif_log(activity_id, notif_log)
            elif 300 <= total_seconds <= 900 and not notif_log.get('10m'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "10 Minutes Left", "Only 10 minutes remaining!")
                notif_log['10m'] = True
                update_notif_log(activity_id, notif_log)
            elif 0 <= total_seconds <= 300 and not notif_log.get('5m'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "5 Minutes Left", "Final 5 minutes! Submit immediately to avoid penalties.")
                notif_log['5m'] = True
                update_notif_log(activity_id, notif_log)
            elif -300 <= total_seconds < 0 and not notif_log.get('missed_0h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "DEADLINE MISSED - Penalty Notice", "You failed to turn in this activity before the deadline. Minus points have been applied to your grade record.")
                notif_log['missed_0h'] = True
                update_notif_log(activity_id, notif_log)
            elif -90000 <= total_seconds <= -86400 and not notif_log.get('missed_24h'):
                send_reminder_cluster(student_emails, student_ids, activity_title, "CRITICAL: 24h Past Deadline", "You have failed to comply within 24 hours of the deadline. A severe grade penalty has been applied.")
                notif_log['missed_24h'] = True
                update_notif_log(activity_id, notif_log)

    except Exception as e:
        print(f"⚠️ Deadline background scheduler error: {e}")

def send_reminder_cluster(emails, user_ids, title, heading, details):
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
            response = supabase.table('push_subscriptions').select('*').in_('user_id', user_ids).execute()
            subscriptions = response.data or []

            push_payload = json.dumps({
                "title": f"⚠️ {heading}: {title}",
                "body": details,
                "url": "/dashboard.html",
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
        supabase.table('activities').update({'notification_log': log_dict}).eq('id', activity_id).execute()
    except Exception as e:
        print(f"Error updating notification log: {e}")

# Start APScheduler safely with daemon thread
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