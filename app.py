"""Smart Student Placement Management System - Flask backend.

All SQL goes through the q() and run() helpers, so moving to MySQL later
only means swapping the connection code in get_db()/init_db().
"""
import os
import re
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "placement_management.db")
LOGO_DIR = os.path.join(BASE_DIR, "static", "uploads", "logos")
# Resumes hold personal data, so they live outside /static and are only
# served through the permission-checked /resume/<id> route.
RESUME_DIR = os.path.join(BASE_DIR, "private_uploads", "resumes")

STATUSES = ["Applied", "Under Review", "Shortlisted",
            "Interview Scheduled", "Selected", "Rejected"]
DEPARTMENTS = ["CSE", "IT", "ECE", "EEE", "MECH", "CIVIL", "AI&DS"]
JOB_TYPES = ["Full-time", "Internship", "Part-time", "Contract"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "change-this-secret-in-production"),
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    register_number TEXT UNIQUE,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student'
);
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    department TEXT,
    year INTEGER,                 -- graduation (passing-out) year
    cgpa REAL DEFAULT 0,
    tenth_percentage REAL,
    twelfth_percentage REAL,
    backlogs INTEGER DEFAULT 0,
    address TEXT DEFAULT '',
    prog_skills TEXT DEFAULT '',
    web_skills TEXT DEFAULT '',
    db_skills TEXT DEFAULT '',
    other_skills TEXT DEFAULT '',
    soft_skills TEXT DEFAULT '',
    skills TEXT DEFAULT '',       -- combined technical skills used for eligibility
    resume TEXT
);
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    description TEXT DEFAULT '',
    website TEXT DEFAULT '',
    location TEXT DEFAULT '',
    logo TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    job_role TEXT NOT NULL,
    salary REAL DEFAULT 0,        -- in LPA
    job_type TEXT DEFAULT 'Full-time',
    minimum_cgpa REAL DEFAULT 0,
    required_department TEXT DEFAULT 'All',
    required_skills TEXT DEFAULT '',
    maximum_backlogs INTEGER DEFAULT 0,
    graduation_year INTEGER DEFAULT 0,   -- 0 = any batch
    min_percentage REAL DEFAULT 0,       -- applies to both 10th and 12th
    deadline TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    applied_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Applied',
    updated_at TEXT,
    UNIQUE (student_id, job_id)
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_read INTEGER DEFAULT 0
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def q(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def run(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    os.makedirs(RESUME_DIR, exist_ok=True)
    os.makedirs(LOGO_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    if not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        db.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,'admin')",
                   ("Placement Officer", "admin@placement.com", generate_password_hash("admin123")))
    if not db.execute("SELECT 1 FROM companies").fetchone():
        seed_demo_data(db)
    db.commit()
    db.close()


def seed_demo_data(db):
    """Demo student + sample companies so the portal is usable on first run."""
    uid = db.execute(
        "INSERT INTO users(name,register_number,email,phone,password,role) VALUES(?,?,?,?,?,'student')",
        ("Priya Sharma", "REG2026001", "student@placement.com", "9876543210",
         generate_password_hash("student123"))).lastrowid
    db.execute(
        """INSERT INTO students(user_id,department,year,cgpa,tenth_percentage,twelfth_percentage,
           backlogs,address,prog_skills,web_skills,db_skills,other_skills,soft_skills,skills)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uid, "CSE", 2026, 8.2, 91, 88, 0, "Chennai, Tamil Nadu",
         "Python, Java", "HTML, CSS, JavaScript", "SQL", "Git", "Communication, Teamwork",
         "Python, Java, HTML, CSS, JavaScript, SQL, Git"))
    companies = [
        ("ABC Technologies", "Product engineering company building SaaS tools for retail.", "https://example.com/abc", "Chennai"),
        ("XYZ Solutions", "IT services and web solutions for banking clients.", "https://example.com/xyz", "Bengaluru"),
        ("Zenith Systems", "Embedded and electronics design firm.", "https://example.com/zenith", "Hyderabad"),
    ]
    ids = [db.execute("INSERT INTO companies(company_name,description,website,location) VALUES(?,?,?,?)", c).lastrowid
           for c in companies]
    d = lambda n: (date.today() + timedelta(days=n)).isoformat()
    jobs = [
        (ids[0], "Software Developer", 5, "Full-time", 7.0, "CSE, IT", "Java, Python, SQL", 0, 2026, 60, d(30),
         "Design, build and test backend services for our retail platform."),
        (ids[1], "Web Developer", 4.5, "Full-time", 6.5, "All", "HTML, CSS, JavaScript", 1, 0, 0, d(20),
         "Build responsive front-end interfaces for internal banking tools."),
        (ids[1], "Data Analyst Intern", 3, "Internship", 8.5, "CSE, IT, AI&DS", "Python, SQL, Excel", 0, 0, 0, d(15),
         "Six-month internship working with dashboards and reporting pipelines."),
        (ids[2], "Embedded Engineer", 6, "Full-time", 7.5, "ECE, EEE", "C, Embedded C", 0, 2026, 65, d(25),
         "Firmware development for IoT products."),
    ]
    for j in jobs:
        db.execute("""INSERT INTO jobs(company_id,job_role,salary,job_type,minimum_cgpa,required_department,
                      required_skills,maximum_backlogs,graduation_year,min_percentage,deadline,description,created_at)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", j + (now(),))
    sid = db.execute("SELECT id FROM students WHERE user_id=?", (uid,)).fetchone()[0]
    db.execute("INSERT INTO notifications(student_id,title,message,created_at) VALUES(?,?,?,?)",
               (sid, "Welcome to the placement portal",
                "Complete your profile and upload your resume to start applying.", now()))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def split_csv(text):
    return [x.strip() for x in (text or "").replace(";", ",").split(",") if x.strip()]


def clean_csv(text):
    seen, out = set(), []
    for item in split_csv(text):
        if item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return ", ".join(out)


def compose_skills(prog, web, db, other):
    return clean_csv(", ".join(s for s in (prog, web, db, other) if s))


def num(form, key, label, lo, hi, errors, cast=float, required=True):
    raw = (form.get(key) or "").strip()
    if raw == "":
        if required:
            errors.append(f"{label} is required.")
        return None
    try:
        val = cast(raw)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None
    if not lo <= val <= hi:
        errors.append(f"{label} must be between {lo} and {hi}.")
        return None
    return val


def parse_academics(form, errors):
    dept = form.get("department", "").strip()
    if dept not in DEPARTMENTS:
        errors.append("Select a valid department.")
    return {
        "department": dept,
        "year": num(form, "year", "Graduation year", 2000, 2100, errors, int),
        "cgpa": num(form, "cgpa", "CGPA", 0, 10, errors),
        "tenth_percentage": num(form, "tenth_percentage", "10th percentage", 0, 100, errors, required=False),
        "twelfth_percentage": num(form, "twelfth_percentage", "12th percentage", 0, 100, errors, required=False),
        "backlogs": num(form, "backlogs", "Backlogs", 0, 50, errors, int, required=False) or 0,
    }


def valid_phone(p):
    return re.fullmatch(r"[0-9]{10}", p or "") is not None


def safe_next(default):
    nxt = request.form.get("next", "")
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else default


def save_resume(file, regno):
    if not file or not file.filename:
        return None
    if not file.filename.lower().endswith(".pdf"):
        raise ValueError("Resume must be a PDF file.")
    head = file.stream.read(5)
    file.stream.seek(0)
    if head != b"%PDF-":
        raise ValueError("The uploaded file is not a valid PDF.")
    name = f"{secure_filename(regno or 'student')}_{int(time.time())}.pdf"
    file.save(os.path.join(RESUME_DIR, name))
    return name


def remove_file(folder, name):
    if name:
        try:
            os.remove(os.path.join(folder, name))
        except OSError:
            pass


def save_logo(file):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise ValueError("Logo must be a PNG, JPG or WEBP image.")
    name = f"logo_{secrets.token_hex(6)}.{ext}"
    file.save(os.path.join(LOGO_DIR, name))
    return name


def notify(student_id, title, message):
    run("INSERT INTO notifications(student_id,title,message,created_at) VALUES(?,?,?,?)",
        (student_id, title, message, now()))


def notify_all(title, message, department=None):
    sql = "INSERT INTO notifications(student_id,title,message,created_at) SELECT id,?,?,? FROM students"
    args = [title, message, now()]
    if department:
        sql += " WHERE department=?"
        args.append(department)
    run(sql, args)


def check_eligibility(st, job):
    """Return (eligible, [reasons]) comparing a student row with a job row."""
    reasons = []
    if not job["is_active"]:
        reasons.append("This job is no longer accepting applications")
    if job["deadline"] < date.today().isoformat():
        reasons.append("The application deadline has passed")
    if (st["cgpa"] or 0) < job["minimum_cgpa"]:
        reasons.append(f"CGPA requirement not satisfied (needs {job['minimum_cgpa']:g}, you have {st['cgpa']:g})")
    depts = [d.lower() for d in split_csv(job["required_department"])]
    if depts and "all" not in depts and (st["department"] or "").lower() not in depts:
        reasons.append(f"Department not eligible (open to {job['required_department']})")
    if (st["backlogs"] or 0) > job["maximum_backlogs"]:
        reasons.append(f"Backlog limit exceeded (maximum {job['maximum_backlogs']}, you have {st['backlogs']})")
    have = {s.lower() for s in split_csv(st["skills"])}
    missing = [s for s in split_csv(job["required_skills"]) if s.lower() not in have]
    if missing:
        reasons.append("Required skill missing: " + ", ".join(missing))
    if job["graduation_year"] and st["year"] != job["graduation_year"]:
        reasons.append(f"Graduation year not eligible (open to the {job['graduation_year']} batch)")
    if job["min_percentage"]:
        tenth, twelfth = st["tenth_percentage"], st["twelfth_percentage"]
        if not tenth or not twelfth:
            reasons.append("Add your 10th and 12th percentages in your profile")
        elif min(tenth, twelfth) < job["min_percentage"]:
            reasons.append(f"Academic percentage requirement not satisfied (10th and 12th need {job['min_percentage']:g}%+)")
    return (not reasons, reasons)


def current_student():
    if "student" not in g:
        g.student = q("""SELECT s.*, u.name, u.email, u.phone, u.register_number
                         FROM students s JOIN users u ON u.id = s.user_id WHERE s.user_id=?""",
                      (session.get("user_id"),), one=True)
    return g.student


def profile_completion(st):
    checks = [st["phone"], st["address"], st["department"], st["year"], st["cgpa"],
              st["tenth_percentage"], st["twelfth_percentage"],
              st["prog_skills"] or st["web_skills"] or st["db_skills"] or st["other_skills"],
              st["soft_skills"], st["resume"]]
    return int(100 * sum(1 for c in checks if c) / len(checks))


def login_required(role):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            current = session.get("role")
            if current != role:
                if current:
                    flash("You do not have access to that page.", "danger")
                    return redirect(url_for("dashboard" if current == "student" else "admin_dashboard"))
                flash("Please log in to continue.", "warning")
                return redirect(url_for("admin_login" if role == "admin" else "login"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def start_session(user):
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["name"] = user["name"]
    session["csrf"] = secrets.token_hex(16)


# --------------------------------------------------------------------------
# Security hooks, template helpers
# --------------------------------------------------------------------------
@app.before_request
def csrf_protect():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not secrets.compare_digest(sent, session["csrf"]):
            abort(400)


@app.context_processor
def inject_globals():
    unread = 0
    if session.get("role") == "student":
        st = q("SELECT id FROM students WHERE user_id=?", (session["user_id"],), one=True)
        if st:
            unread = q("SELECT COUNT(*) c FROM notifications WHERE student_id=? AND is_read=0",
                       (st["id"],), one=True)["c"]
    return dict(
        csrf_input=Markup(f'<input type="hidden" name="csrf_token" value="{session.get("csrf", "")}">'),
        unread=unread, STATUSES=STATUSES, DEPARTMENTS=DEPARTMENTS, JOB_TYPES=JOB_TYPES,
        today=date.today().isoformat(), current_year=date.today().year)


@app.template_filter("dmy")
def dmy(value):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return value or ""


@app.template_filter("stclass")
def stclass(status):
    return "st-" + status.lower().replace(" ", "-")


@app.template_filter("lpa")
def lpa(value):
    return f"{value:g} LPA"


@app.template_filter("initials")
def initials(name):
    parts = (name or "?").split()
    return "".join(p[0] for p in parts[:2]).upper()


@app.errorhandler(400)
def bad_request(_e):
    return render_template("error.html", code=400,
                           message="Your session expired or the form was invalid. Go back, refresh and try again."), 400


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="That page does not exist."), 404


@app.errorhandler(413)
def too_large(_e):
    flash("The file is too large. The limit is 5 MB.", "danger")
    return redirect(request.referrer or url_for("index"))


# --------------------------------------------------------------------------
# Public + auth routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    years = list(range(date.today().year, date.today().year + 5))
    if request.method == "POST":
        f = {k: request.form.get(k, "").strip() for k in
             ("name", "register_number", "email", "phone", "password", "confirm",
              "department", "year", "cgpa")}
        errors = []
        if len(f["name"]) < 3:
            errors.append("Enter your full name (at least 3 characters).")
        if not re.fullmatch(r"[A-Za-z0-9\-/]{4,20}", f["register_number"]):
            errors.append("Register number must be 4-20 letters or digits.")
        if not EMAIL_RE.match(f["email"]):
            errors.append("Enter a valid email address.")
        if not valid_phone(f["phone"]):
            errors.append("Phone number must be exactly 10 digits.")
        if len(f["password"]) < 6:
            errors.append("Password must be at least 6 characters.")
        if f["password"] != f["confirm"]:
            errors.append("Passwords do not match.")
        acad = parse_academics(request.form, errors)
        if not errors:
            if q("SELECT 1 FROM users WHERE email=?", (f["email"].lower(),), one=True):
                errors.append("An account with this email already exists.")
            if q("SELECT 1 FROM users WHERE register_number=?", (f["register_number"].upper(),), one=True):
                errors.append("This register number is already registered.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=f, years=years)
        uid = run("INSERT INTO users(name,register_number,email,phone,password,role) VALUES(?,?,?,?,?,'student')",
                  (f["name"], f["register_number"].upper(), f["email"].lower(), f["phone"],
                   generate_password_hash(f["password"])))
        run("INSERT INTO students(user_id,department,year,cgpa) VALUES(?,?,?,?)",
            (uid, acad["department"], acad["year"], acad["cgpa"]))
        sid = q("SELECT id FROM students WHERE user_id=?", (uid,), one=True)["id"]
        notify(sid, "Welcome to the placement portal",
               "Complete your profile and upload your resume to start applying.")
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form={}, years=years)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("role") == "student":
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = q("SELECT * FROM users WHERE email=?", (email,), one=True)
        if user and user["role"] == "student" and check_password_hash(user["password"], request.form.get("password", "")):
            start_session(user)
            return redirect(url_for("dashboard"))
        if user and user["role"] == "admin":
            flash("Administrators must sign in from the admin login page.", "warning")
        else:
            flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = q("SELECT * FROM users WHERE email=?", (email,), one=True)
        if user and user["role"] == "admin" and check_password_hash(user["password"], request.form.get("password", "")):
            start_session(user)
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "danger")
    return render_template("admin_login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "POST":
        session.clear()
        flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# Student routes
# --------------------------------------------------------------------------
@app.route("/dashboard")
@login_required("student")
def dashboard():
    st = current_student()
    jobs = q("""SELECT j.*, c.company_name FROM jobs j JOIN companies c ON c.id=j.company_id
                WHERE j.is_active=1 AND j.deadline>=?""", (date.today().isoformat(),))
    apps = q("""SELECT a.*, j.job_role, c.company_name FROM applications a
                JOIN jobs j ON j.id=a.job_id JOIN companies c ON c.id=j.company_id
                WHERE a.student_id=? ORDER BY a.applied_date DESC, a.id DESC""", (st["id"],))
    stats = {
        "jobs": len(jobs),
        "eligible": sum(1 for j in jobs if check_eligibility(st, j)[0]),
        "applications": len(apps),
        "selected": sum(1 for a in apps if a["status"] == "Selected"),
        "pending": sum(1 for a in apps if a["status"] in ("Applied", "Under Review")),
    }
    notes = q("SELECT * FROM notifications WHERE student_id=? ORDER BY id DESC LIMIT 4", (st["id"],))
    return render_template("student_dashboard.html", st=st, stats=stats, apps=apps[:5], notes=notes,
                           completion=profile_completion(st))


@app.route("/profile", methods=["GET", "POST"])
@login_required("student")
def profile():
    st = current_student()
    if request.method == "POST":
        errors = []
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        if len(name) < 3:
            errors.append("Enter your full name (at least 3 characters).")
        if not valid_phone(phone):
            errors.append("Phone number must be exactly 10 digits.")
        acad = parse_academics(request.form, errors)
        skills = {k: clean_csv(request.form.get(k, "")) for k in
                  ("prog_skills", "web_skills", "db_skills", "other_skills", "soft_skills")}
        resume = st["resume"]
        try:
            new_resume = save_resume(request.files.get("resume"), st["register_number"])
        except ValueError as exc:
            errors.append(str(exc))
            new_resume = None
        if errors:
            for e in errors:
                flash(e, "danger")
            return redirect(url_for("profile"))
        if new_resume:
            remove_file(RESUME_DIR, resume)
            resume = new_resume
        run("UPDATE users SET name=?, phone=? WHERE id=?", (name, phone, session["user_id"]))
        run("""UPDATE students SET department=?, year=?, cgpa=?, tenth_percentage=?, twelfth_percentage=?,
               backlogs=?, address=?, prog_skills=?, web_skills=?, db_skills=?, other_skills=?,
               soft_skills=?, skills=?, resume=? WHERE id=?""",
            (acad["department"], acad["year"], acad["cgpa"], acad["tenth_percentage"],
             acad["twelfth_percentage"], acad["backlogs"], request.form.get("address", "").strip()[:250],
             skills["prog_skills"], skills["web_skills"], skills["db_skills"], skills["other_skills"],
             skills["soft_skills"],
             compose_skills(skills["prog_skills"], skills["web_skills"], skills["db_skills"], skills["other_skills"]),
             resume, st["id"]))
        session["name"] = name
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html", st=st, completion=profile_completion(st),
                           years=list(range(date.today().year - 1, date.today().year + 5)))


@app.route("/resume/<int:student_id>")
def resume(student_id):
    role = session.get("role")
    if not role:
        return redirect(url_for("login"))
    st = q("SELECT id, user_id, resume FROM students WHERE id=?", (student_id,), one=True)
    if not st or not st["resume"]:
        abort(404)
    if role == "student" and st["user_id"] != session["user_id"]:
        abort(404)
    return send_from_directory(RESUME_DIR, st["resume"], mimetype="application/pdf",
                               as_attachment=bool(request.args.get("download")))


def job_dicts(st, job_id=None):
    sql = """SELECT j.*, c.company_name, c.location, c.logo, c.website,
                    c.description AS company_description
             FROM jobs j JOIN companies c ON c.id = j.company_id WHERE j.is_active=1"""
    args = []
    if job_id:
        sql += " AND j.id=?"
        args.append(job_id)
    rows = q(sql + " ORDER BY j.deadline ASC", args)
    applied = {r["job_id"] for r in q("SELECT job_id FROM applications WHERE student_id=?", (st["id"],))}
    out = []
    for r in rows:
        ok, reasons = check_eligibility(st, r)
        d = dict(r)
        d.update(eligible=ok, reasons=reasons, applied=r["id"] in applied,
                 closed=r["deadline"] < date.today().isoformat())
        out.append(d)
    return out


@app.route("/jobs")
@login_required("student")
def jobs():
    st = current_student()
    items = job_dicts(st)
    locations = sorted({j["location"] for j in items if j["location"]})
    return render_template("jobs.html", jobs=items, locations=locations, st=st)


@app.route("/job/<int:job_id>")
@login_required("student")
def job_details(job_id):
    st = current_student()
    items = job_dicts(st, job_id)
    if not items:
        abort(404)
    return render_template("job_details.html", job=items[0], st=st)


@app.route("/api/eligibility/<int:job_id>")
@login_required("student")
def api_eligibility(job_id):
    items = job_dicts(current_student(), job_id)
    if not items:
        return jsonify(error="Job not found"), 404
    job = items[0]
    return jsonify(eligible=job["eligible"], applied=job["applied"], reasons=job["reasons"],
                   company=job["company_name"], role=job["job_role"])


@app.route("/apply/<int:job_id>", methods=["GET", "POST"])
@login_required("student")
def apply(job_id):
    if request.method == "GET":
        return redirect(url_for("job_details", job_id=job_id))
    st = current_student()
    job = q("""SELECT j.*, c.company_name FROM jobs j JOIN companies c ON c.id=j.company_id
               WHERE j.id=?""", (job_id,), one=True)
    if not job or not job["is_active"]:
        abort(404)
    if q("SELECT 1 FROM applications WHERE student_id=? AND job_id=?", (st["id"], job_id), one=True):
        flash("You have already applied for this job.", "warning")
        return redirect(url_for("applications"))
    ok, reasons = check_eligibility(st, job)
    if not ok:
        flash("You cannot apply: " + "; ".join(reasons) + ".", "danger")
        return redirect(url_for("job_details", job_id=job_id))
    if not st["resume"]:
        flash("Upload your resume in your profile before applying.", "warning")
        return redirect(url_for("profile"))
    try:
        run("INSERT INTO applications(student_id,job_id,applied_date,status,updated_at) VALUES(?,?,?,?,?)",
            (st["id"], job_id, date.today().isoformat(), "Applied", now()))
    except sqlite3.IntegrityError:
        flash("You have already applied for this job.", "warning")
        return redirect(url_for("applications"))
    notify(st["id"], "Application submitted",
           f"Your application for {job['job_role']} at {job['company_name']} was received.")
    flash("Application submitted successfully!", "success")
    return redirect(url_for("applications"))


@app.route("/applications")
@login_required("student")
def applications():
    st = current_student()
    rows = q("""SELECT a.*, j.job_role, j.salary, c.company_name FROM applications a
                JOIN jobs j ON j.id=a.job_id JOIN companies c ON c.id=j.company_id
                WHERE a.student_id=? ORDER BY a.applied_date DESC, a.id DESC""", (st["id"],))
    return render_template("applications.html", apps=rows)


@app.route("/notifications")
@login_required("student")
def notifications():
    st = current_student()
    rows = q("SELECT * FROM notifications WHERE student_id=? ORDER BY id DESC", (st["id"],))
    run("UPDATE notifications SET is_read=1 WHERE student_id=?", (st["id"],))
    return render_template("notifications.html", notes=rows)


# --------------------------------------------------------------------------
# Admin routes
# --------------------------------------------------------------------------
@app.route("/admin/dashboard")
@login_required("admin")
def admin_dashboard():
    one = lambda sql, a=(): q(sql, a, one=True)["c"]
    stats = {
        "students": one("SELECT COUNT(*) c FROM students"),
        "companies": one("SELECT COUNT(*) c FROM companies"),
        "jobs": one("SELECT COUNT(*) c FROM jobs"),
        "applications": one("SELECT COUNT(*) c FROM applications"),
        "shortlisted": one("SELECT COUNT(*) c FROM applications WHERE status='Shortlisted'"),
        "selected": one("SELECT COUNT(*) c FROM applications WHERE status='Selected'"),
        "pending": one("SELECT COUNT(*) c FROM applications WHERE status IN ('Applied','Under Review')"),
    }
    dept = q("SELECT department d, COUNT(*) c FROM students GROUP BY department ORDER BY d")
    comp = q("""SELECT c.company_name n, COUNT(a.id) c FROM companies c
                LEFT JOIN jobs j ON j.company_id=c.id LEFT JOIN applications a ON a.job_id=j.id
                GROUP BY c.id ORDER BY c.company_name""")
    applied_m = {r["m"]: r["c"] for r in q(
        "SELECT substr(applied_date,1,7) m, COUNT(*) c FROM applications GROUP BY m")}
    selected_m = {r["m"]: r["c"] for r in q(
        "SELECT substr(updated_at,1,7) m, COUNT(*) c FROM applications WHERE status='Selected' GROUP BY m")}
    months = sorted(set(applied_m) | set(selected_m))
    charts = {
        "dept": {"labels": [r["d"] or "N/A" for r in dept], "data": [r["c"] for r in dept]},
        "company": {"labels": [r["n"] for r in comp], "data": [r["c"] for r in comp]},
        "outcome": {"selected": stats["selected"],
                    "rejected": one("SELECT COUNT(*) c FROM applications WHERE status='Rejected'")},
        "monthly": {"labels": months, "applied": [applied_m.get(m, 0) for m in months],
                    "selected": [selected_m.get(m, 0) for m in months]},
    }
    recent = q("""SELECT a.*, u.name, c.company_name, j.job_role FROM applications a
                  JOIN students s ON s.id=a.student_id JOIN users u ON u.id=s.user_id
                  JOIN jobs j ON j.id=a.job_id JOIN companies c ON c.id=j.company_id
                  ORDER BY a.id DESC LIMIT 6""")
    return render_template("admin_dashboard.html", stats=stats, charts=charts, recent=recent)


# ---- students ----
@app.route("/admin/students")
@login_required("admin")
def admin_students():
    search = request.args.get("q", "").strip()
    dept = request.args.get("dept", "").strip()
    sql = """SELECT s.*, u.name, u.email, u.phone, u.register_number
             FROM students s JOIN users u ON u.id=s.user_id WHERE 1=1"""
    args = []
    if search:
        sql += " AND (u.name LIKE ? OR u.register_number LIKE ? OR u.email LIKE ?)"
        args += [f"%{search}%"] * 3
    if dept:
        sql += " AND s.department=?"
        args.append(dept)
    rows = [dict(r) for r in q(sql + " ORDER BY u.name", args)]
    return render_template("manage_students.html", students=rows, search=search, dept=dept)


@app.route("/admin/students/<int:sid>/edit", methods=["POST"])
@login_required("admin")
def admin_student_edit(sid):
    st = q("SELECT s.*, u.id AS uid FROM students s JOIN users u ON u.id=s.user_id WHERE s.id=?", (sid,), one=True)
    if not st:
        abort(404)
    f = request.form
    errors = []
    name, regno = f.get("name", "").strip(), f.get("register_number", "").strip().upper()
    email, phone = f.get("email", "").strip().lower(), f.get("phone", "").strip()
    if len(name) < 3:
        errors.append("Enter a valid name.")
    if not re.fullmatch(r"[A-Za-z0-9\-/]{4,20}", regno):
        errors.append("Register number must be 4-20 letters or digits.")
    if not EMAIL_RE.match(email):
        errors.append("Enter a valid email address.")
    if not valid_phone(phone):
        errors.append("Phone number must be exactly 10 digits.")
    acad = parse_academics(f, errors)
    if not errors and q("SELECT 1 FROM users WHERE (email=? OR register_number=?) AND id!=?",
                        (email, regno, st["uid"]), one=True):
        errors.append("Email or register number is already used by another user.")
    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(safe_next(url_for("admin_students")))
    sk = {k: clean_csv(f.get(k, "")) for k in ("prog_skills", "web_skills", "db_skills", "other_skills", "soft_skills")}
    run("UPDATE users SET name=?, register_number=?, email=?, phone=? WHERE id=?", (name, regno, email, phone, st["uid"]))
    run("""UPDATE students SET department=?, year=?, cgpa=?, tenth_percentage=?, twelfth_percentage=?, backlogs=?,
           prog_skills=?, web_skills=?, db_skills=?, other_skills=?, soft_skills=?, skills=? WHERE id=?""",
        (acad["department"], acad["year"], acad["cgpa"], acad["tenth_percentage"], acad["twelfth_percentage"],
         acad["backlogs"], sk["prog_skills"], sk["web_skills"], sk["db_skills"], sk["other_skills"], sk["soft_skills"],
         compose_skills(sk["prog_skills"], sk["web_skills"], sk["db_skills"], sk["other_skills"]), sid))
    flash("Student record updated.", "success")
    return redirect(safe_next(url_for("admin_students")))


@app.route("/admin/students/<int:sid>/delete", methods=["POST"])
@login_required("admin")
def admin_student_delete(sid):
    st = q("SELECT user_id, resume FROM students WHERE id=?", (sid,), one=True)
    if not st:
        abort(404)
    remove_file(RESUME_DIR, st["resume"])
    run("DELETE FROM users WHERE id=?", (st["user_id"],))  # cascades to student, applications, notifications
    flash("Student record deleted.", "success")
    return redirect(safe_next(url_for("admin_students")))


# ---- companies ----
def parse_company(f, errors):
    name = f.get("company_name", "").strip()
    if len(name) < 2:
        errors.append("Company name is required.")
    site = f.get("website", "").strip()
    if site and not re.match(r"^https?://", site):
        site = "https://" + site
    return {"company_name": name, "description": f.get("description", "").strip()[:1000],
            "website": site[:200], "location": f.get("location", "").strip()[:100]}


@app.route("/admin/companies")
@login_required("admin")
def admin_companies():
    rows = []
    for c in q("""SELECT c.*, (SELECT COUNT(*) FROM jobs j WHERE j.company_id=c.id) AS job_count
                  FROM companies c ORDER BY c.company_name"""):
        d = dict(c)
        d["roles"] = ", ".join(r["job_role"] for r in q("SELECT job_role FROM jobs WHERE company_id=?", (c["id"],)))
        rows.append(d)
    return render_template("manage_companies.html", companies=rows)


@app.route("/admin/companies/save", methods=["POST"])
@app.route("/admin/companies/<int:cid>/save", methods=["POST"])
@login_required("admin")
def admin_company_save(cid=None):
    errors = []
    data = parse_company(request.form, errors)
    old = q("SELECT * FROM companies WHERE id=?", (cid,), one=True) if cid else None
    if cid and not old:
        abort(404)
    logo = old["logo"] if old else None
    try:
        new_logo = save_logo(request.files.get("logo"))
    except ValueError as exc:
        errors.append(str(exc))
        new_logo = None
    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("admin_companies"))
    if new_logo:
        remove_file(LOGO_DIR, logo)
        logo = new_logo
    if cid:
        run("UPDATE companies SET company_name=?, description=?, website=?, location=?, logo=? WHERE id=?",
            (data["company_name"], data["description"], data["website"], data["location"], logo, cid))
        flash("Company updated.", "success")
    else:
        run("INSERT INTO companies(company_name,description,website,location,logo) VALUES(?,?,?,?,?)",
            (data["company_name"], data["description"], data["website"], data["location"], logo))
        flash("Company added. Now add a job for it under Jobs.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin/companies/<int:cid>/delete", methods=["POST"])
@login_required("admin")
def admin_company_delete(cid):
    c = q("SELECT logo FROM companies WHERE id=?", (cid,), one=True)
    if not c:
        abort(404)
    remove_file(LOGO_DIR, c["logo"])
    run("DELETE FROM companies WHERE id=?", (cid,))  # cascades to jobs and applications
    flash("Company and its jobs were deleted.", "success")
    return redirect(url_for("admin_companies"))


# ---- jobs ----
JOB_COLS = ["company_id", "job_role", "salary", "job_type", "minimum_cgpa", "required_department",
            "required_skills", "maximum_backlogs", "graduation_year", "min_percentage", "deadline", "description"]


def parse_job(f, errors):
    role = f.get("job_role", "").strip()
    if len(role) < 2:
        errors.append("Job role is required.")
    cid = num(f, "company_id", "Company", 1, 10 ** 9, errors, int)
    if cid and not q("SELECT 1 FROM companies WHERE id=?", (cid,), one=True):
        errors.append("Select a valid company.")
    jtype = f.get("job_type", "")
    if jtype not in JOB_TYPES:
        errors.append("Select a valid job type.")
    deadline = f.get("deadline", "").strip()
    try:
        datetime.strptime(deadline, "%Y-%m-%d")
    except ValueError:
        errors.append("Enter a valid application deadline.")
    return {
        "company_id": cid, "job_role": role, "job_type": jtype, "deadline": deadline,
        "salary": num(f, "salary", "Salary (LPA)", 0, 500, errors),
        "minimum_cgpa": num(f, "minimum_cgpa", "Minimum CGPA", 0, 10, errors),
        "required_department": clean_csv(f.get("required_department", "")) or "All",
        "required_skills": clean_csv(f.get("required_skills", "")),
        "maximum_backlogs": num(f, "maximum_backlogs", "Maximum backlogs", 0, 50, errors, int, required=False) or 0,
        "graduation_year": num(f, "graduation_year", "Graduation year", 0, 2100, errors, int, required=False) or 0,
        "min_percentage": num(f, "min_percentage", "Minimum percentage", 0, 100, errors, required=False) or 0,
        "description": f.get("description", "").strip()[:2000],
    }


@app.route("/admin/jobs")
@login_required("admin")
def admin_jobs():
    rows = [dict(r) for r in q("""SELECT j.*, c.company_name,
                (SELECT COUNT(*) FROM applications a WHERE a.job_id=j.id) AS applicants
                FROM jobs j JOIN companies c ON c.id=j.company_id ORDER BY j.id DESC""")]
    companies = q("SELECT id, company_name FROM companies ORDER BY company_name")
    return render_template("manage_jobs.html", jobs=rows, companies=companies)


@app.route("/admin/jobs/save", methods=["POST"])
@app.route("/admin/jobs/<int:jid>/save", methods=["POST"])
@login_required("admin")
def admin_job_save(jid=None):
    errors = []
    data = parse_job(request.form, errors)
    if jid and not q("SELECT 1 FROM jobs WHERE id=?", (jid,), one=True):
        abort(404)
    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("admin_jobs"))
    values = [data[c] for c in JOB_COLS]
    if jid:
        run("UPDATE jobs SET " + ", ".join(f"{c}=?" for c in JOB_COLS) + " WHERE id=?", values + [jid])
        flash("Job updated.", "success")
    else:
        run("INSERT INTO jobs(" + ",".join(JOB_COLS) + ",created_at) VALUES(" + ",".join("?" * (len(JOB_COLS) + 1)) + ")",
            values + [now()])
        company = q("SELECT company_name FROM companies WHERE id=?", (data["company_id"],), one=True)["company_name"]
        notify_all("New job posting", f"{company} is hiring for {data['job_role']}. "
                   f"Apply before {dmy(data['deadline'])}.")
        flash("Job created and students were notified.", "success")
    return redirect(url_for("admin_jobs"))


@app.route("/admin/jobs/<int:jid>/toggle", methods=["POST"])
@login_required("admin")
def admin_job_toggle(jid):
    run("UPDATE jobs SET is_active = 1 - is_active WHERE id=?", (jid,))
    flash("Job status changed.", "success")
    return redirect(url_for("admin_jobs"))


@app.route("/admin/jobs/<int:jid>/delete", methods=["POST"])
@login_required("admin")
def admin_job_delete(jid):
    run("DELETE FROM jobs WHERE id=?", (jid,))
    flash("Job deleted.", "success")
    return redirect(url_for("admin_jobs"))


# ---- applications ----
@app.route("/admin/applications")
@login_required("admin")
def admin_applications():
    flt = {k: request.args.get(k, "").strip() for k in ("company", "role", "dept", "status", "job")}
    sql = """SELECT a.*, u.name, u.register_number, s.department, s.cgpa, s.resume,
                    c.company_name, j.job_role
             FROM applications a JOIN students s ON s.id=a.student_id JOIN users u ON u.id=s.user_id
             JOIN jobs j ON j.id=a.job_id JOIN companies c ON c.id=j.company_id WHERE 1=1"""
    args = []
    for key, col in (("company", "c.id"), ("role", "j.job_role"), ("dept", "s.department"),
                     ("status", "a.status"), ("job", "j.id")):
        if flt[key]:
            sql += f" AND {col}=?"
            args.append(flt[key])
    rows = q(sql + " ORDER BY a.id DESC", args)
    companies = q("SELECT id, company_name FROM companies ORDER BY company_name")
    roles = [r["job_role"] for r in q("SELECT DISTINCT job_role FROM jobs ORDER BY job_role")]
    return render_template("manage_applications.html", apps=rows, flt=flt, companies=companies, roles=roles)


@app.route("/admin/applications/<int:aid>/status", methods=["POST"])
@login_required("admin")
def admin_application_status(aid):
    status = request.form.get("status", "")
    app_row = q("""SELECT a.student_id, j.job_role, c.company_name FROM applications a
                   JOIN jobs j ON j.id=a.job_id JOIN companies c ON c.id=j.company_id
                   WHERE a.id=?""", (aid,), one=True)
    if not app_row:
        abort(404)
    if status not in STATUSES:
        flash("Choose a valid status.", "danger")
        return redirect(safe_next(url_for("admin_applications")))
    run("UPDATE applications SET status=?, updated_at=? WHERE id=?", (status, now(), aid))
    note = request.form.get("note", "").strip()[:300]
    message = f"Your application for {app_row['job_role']} at {app_row['company_name']} is now: {status}."
    if note:
        message += f" Note from placement cell: {note}"
    notify(app_row["student_id"], f"Application update: {status}", message)
    flash(f"Status updated to {status}. The student has been notified.", "success")
    return redirect(safe_next(url_for("admin_applications")))


# ---- notifications ----
@app.route("/admin/notifications")
@login_required("admin")
def admin_notifications():
    rows = q("""SELECT n.*, u.name FROM notifications n JOIN students s ON s.id=n.student_id
                JOIN users u ON u.id=s.user_id ORDER BY n.id DESC LIMIT 40""")
    return render_template("admin_notifications.html", notes=rows)


@app.route("/admin/notifications/send", methods=["POST"])
@login_required("admin")
def admin_notification_send():
    title = request.form.get("title", "").strip()
    message = request.form.get("message", "").strip()
    dept = request.form.get("department", "").strip()
    if not title or not message:
        flash("Enter both a title and a message.", "danger")
    elif dept and dept not in DEPARTMENTS:
        flash("Select a valid department.", "danger")
    else:
        notify_all(title[:120], message[:500], dept or None)
        flash("Announcement sent.", "success")
    return redirect(url_for("admin_notifications"))


@app.route("/admin/notifications/<int:nid>/delete", methods=["POST"])
@login_required("admin")
def admin_notification_delete(nid):
    run("DELETE FROM notifications WHERE id=?", (nid,))
    flash("Notification deleted.", "success")
    return redirect(url_for("admin_notifications"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
