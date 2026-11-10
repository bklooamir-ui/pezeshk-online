from flask import Flask, render_template, request, redirect, url_for, flash, abort
from werkzeug.utils import secure_filename
from pathlib import Path
import sqlite3, json, secrets, string
from datetime import datetime

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "clinic.db"
UPLOAD_DIR = BASE / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "pdf"}

app = Flask(__name__)
app.secret_key = "CHANGE-THIS-SECRET-KEY-BEFORE-DEPLOYMENT"
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

DOCTORS = {
    "sohrabi": {
        "name": "دکتر سهرابی", "gender": "مرد", "specialty": "پزشک عمومی",
        "color": "blue", "symbol": "🩺",
        "bio": "پزشک عمومی؛ بررسی اولیه علائم و راهنمایی برای پیگیری درمان.",
        "reviews": ["توضیحات روشن و محترمانه بود.", "فرایند ثبت درخواست ساده بود."]
    },
    "moradi": {
        "name": "دکتر مرادی", "gender": "مرد", "specialty": "فیزیوتراپی",
        "color": "teal", "symbol": "🦴",
        "bio": "فیزیوتراپی؛ ارزیابی مشکلات عضلانی، مفصلی و محدودیت حرکتی.",
        "reviews": ["راهنمایی‌های تمرینی مفید بود.", "با حوصله به شرح مشکل گوش دادند."]
    },
    "mousavi": {
        "name": "دکتر موسوی", "gender": "زن", "specialty": "زنان و زایمان",
        "color": "rose", "symbol": "🌸",
        "bio": "زنان و زایمان؛ بررسی اولیه مسائل مرتبط با سلامت زنان.",
        "reviews": ["محیط گفتگو محترمانه بود.", "سؤالات فرم کامل و قابل فهم بود."]
    },
    "keramati": {
        "name": "دکتر کرامتی", "gender": "زن", "specialty": "دندان‌پزشک",
        "color": "violet", "symbol": "🦷",
        "bio": "دندان‌پزشکی؛ بررسی اولیه درد دندان و مشکلات دهان و دندان.",
        "reviews": ["امکان ارسال عکس دندان خیلی کاربردی بود.", "فرم تخصصی و ساده بود."]
    }
}

QUESTIONS = {
    "sohrabi": [
        ("age", "سن", "number"), ("sex", "جنسیت", "select"),
        ("symptoms", "علائم فعلی", "textarea"),
        ("duration", "علائم از چه زمانی شروع شده‌اند؟", "text"),
        ("temperature", "دمای بدن (در صورت اندازه‌گیری)", "text"),
        ("medicines", "داروهای مصرفی و حساسیت دارویی", "textarea"),
        ("history", "سابقه بیماری مهم", "textarea")
    ],
    "moradi": [
        ("pain_area", "محل درد یا محدودیت حرکتی", "text"),
        ("pain_level", "شدت درد از ۰ تا ۱۰", "number"),
        ("duration", "مدت زمان مشکل", "text"),
        ("injury", "آیا آسیب‌دیدگی یا ضربه داشته‌اید؟", "select"),
        ("movement", "چه حرکاتی مشکل را بیشتر می‌کنند؟", "textarea"),
        ("surgery", "سابقه جراحی یا بیماری مرتبط", "textarea")
    ],
    "mousavi": [
        ("age", "سن", "number"),
        ("pregnancy", "وضعیت بارداری (در صورت ارتباط)", "select"),
        ("last_period", "تاریخ آخرین قاعدگی (در صورت ارتباط)", "text"),
        ("symptoms", "علائم یا علت مراجعه", "textarea"),
        ("duration", "مدت زمان شروع علائم", "text"),
        ("medicines", "داروهای مصرفی و حساسیت دارویی", "textarea")
    ],
    "keramati": [
        ("tooth_area", "محل درد یا مشکل دندان", "text"),
        ("pain_level", "شدت درد از ۰ تا ۱۰", "number"),
        ("temperature_sensitivity", "حساسیت به سردی یا گرمی", "select"),
        ("swelling", "تورم صورت یا لثه", "select"),
        ("bleeding", "خونریزی لثه", "select"),
        ("duration", "مدت زمان مشکل", "text"),
        ("dental_history", "سابقه درمان دندان", "textarea")
    ]
}

YES_NO = {"بله", "خیر", "مطمئن نیستم"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            patient_phone TEXT NOT NULL,
            answers TEXT NOT NULL,
            history TEXT,
            upload_name TEXT,
            triage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'در انتظار بررسی پزشک',
            prescription_code TEXT,
            prescription_note TEXT,
            created_at TEXT NOT NULL
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id INTEGER NOT NULL,
            sender TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(consultation_id) REFERENCES consultations(id)
        )""")

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def triage_screen(doctor_id, answers, history):
    """A conservative demo screen only; not a diagnostic or prescribing algorithm."""
    text = " ".join([str(v) for v in answers.values()] + [history or ""]).lower()
    danger_terms = [
        "تنگی نفس", "نفس نمی", "درد قفسه سینه", "بیهوش", "غش",
        "خونریزی شدید", "تشنج", "ضعف ناگهانی", "اختلال تکلم",
        "تورم شدید صورت", "مشکل بلع", "تب خیلی بالا"
    ]
    if any(term in text for term in danger_terms):
        return "نیازمند ارزیابی فوری حضوری/اورژانسی"
    if doctor_id == "mousavi" and ("باردار" in text or answers.get("pregnancy") == "بله"):
        return "نیازمند بررسی پزشک؛ در صورت درد شدید یا خونریزی، مراجعه فوری"
    return "نیازمند بررسی پزشک؛ این سامانه تشخیص خودکار نمی‌دهد"

def make_code():
    alphabet = string.ascii_uppercase + string.digits
    return "RX-" + "".join(secrets.choice(alphabet) for _ in range(8))

@app.route("/")
def index():
    return render_template("index.html", doctors=DOCTORS)

@app.route("/doctor/<doctor_id>")
def doctor(doctor_id):
    item = DOCTORS.get(doctor_id)
    if not item:
        abort(404)
    return render_template("doctor.html", doctor=item, doctor_id=doctor_id)

@app.route("/visit/<doctor_id>", methods=["GET", "POST"])
def visit(doctor_id):
    item = DOCTORS.get(doctor_id)
    if not item:
        abort(404)
    questions = QUESTIONS[doctor_id]
    if request.method == "POST":
        patient_name = request.form.get("patient_name", "").strip()
        patient_phone = request.form.get("patient_phone", "").strip()
        if not patient_name or not patient_phone:
            flash("نام و شماره تماس الزامی است.")
            return render_template("visit.html", doctor=item, doctor_id=doctor_id, questions=questions)
        answers = {key: request.form.get(key, "").strip() for key, _, _ in questions}
        history = request.form.get("history_free", "").strip()
        upload_name = None
        uploaded = request.files.get("attachment")
        if uploaded and uploaded.filename:
            if not allowed_file(uploaded.filename):
                flash("فرمت فایل مجاز نیست. PNG، JPG، WEBP یا PDF ارسال کنید.")
                return render_template("visit.html", doctor=item, doctor_id=doctor_id, questions=questions)
            safe = secure_filename(uploaded.filename)
            stored = f"{secrets.token_hex(8)}_{safe}"
            uploaded.save(UPLOAD_DIR / stored)
            upload_name = stored
        triage = triage_screen(doctor_id, answers, history)
        with db() as con:
            cur = con.execute("""
                INSERT INTO consultations
                (doctor_id, patient_name, patient_phone, answers, history, upload_name, triage, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (doctor_id, patient_name, patient_phone, json.dumps(answers, ensure_ascii=False),
                  history, upload_name, triage, datetime.now().isoformat(timespec="minutes")))
            cid = cur.lastrowid
        return redirect(url_for("result", consultation_id=cid))
    return render_template("visit.html", doctor=item, doctor_id=doctor_id, questions=questions)

@app.route("/result/<int:consultation_id>")
def result(consultation_id):
    with db() as con:
        record = con.execute("SELECT * FROM consultations WHERE id=?", (consultation_id,)).fetchone()
    if not record:
        abort(404)
    return render_template("result.html", record=record, doctor=DOCTORS[record["doctor_id"]])

# DEMO clinician workspace. Protect this route with real authentication before deployment.
@app.route("/clinician")
def clinician():
    with db() as con:
        records = con.execute("SELECT * FROM consultations ORDER BY id DESC").fetchall()
    return render_template("clinician.html", records=records, doctors=DOCTORS)

@app.route("/clinician/<int:consultation_id>/approve", methods=["POST"])
def approve(consultation_id):
    note = request.form.get("note", "").strip()
    # A code is generated only after an explicit clinician action in this demo.
    with db() as con:
        row = con.execute("SELECT * FROM consultations WHERE id=?", (consultation_id,)).fetchone()
        if not row:
            abort(404)
        code = row["prescription_code"] or make_code()
        con.execute("""UPDATE consultations SET status=?, prescription_code=?, prescription_note=?
                       WHERE id=?""",
                    ("نسخه ثبت‌شده توسط پزشک (دموی محلی)", code, note, consultation_id))
    flash("کد نمایشی ایجاد شد. این کد به هیچ داروخانه‌ای متصل نیست.")
    return redirect(url_for("result", consultation_id=consultation_id))

@app.route("/chat/<int:consultation_id>", methods=["GET", "POST"])
def chat(consultation_id):
    with db() as con:
        record = con.execute("SELECT * FROM consultations WHERE id=?", (consultation_id,)).fetchone()
        if not record:
            abort(404)
        if not record["prescription_code"]:
            flash("گفت‌وگو پس از تأیید پزشک در این نمونه فعال می‌شود.")
            return redirect(url_for("result", consultation_id=consultation_id))
        if request.method == "POST":
            body = request.form.get("body", "").strip()
            sender = request.form.get("sender", "بیمار")
            if body:
                con.execute("INSERT INTO messages (consultation_id, sender, body, created_at) VALUES (?, ?, ?, ?)",
                            (consultation_id, sender, body, datetime.now().strftime("%Y-%m-%d %H:%M")))
        messages = con.execute("SELECT * FROM messages WHERE consultation_id=? ORDER BY id",
                               (consultation_id,)).fetchall()
    return render_template("chat.html", record=record, messages=messages, doctor=DOCTORS[record["doctor_id"]])

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    # Demo only. In production, require authenticated access and check ownership/permissions.
    from flask import send_from_directory
    return send_from_directory(UPLOAD_DIR, filename)

init_db()  # initialize the demo database for both local and hosted execution\n\nif __name__ == "__main__":\n    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", 5000)), debug=False)
