from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pathlib import Path
from functools import wraps
from datetime import datetime
import uuid, os

BASE = Path(__file__).resolve().parent
UPLOAD_DIR = BASE / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "CHANGE_THIS_SECRET_KEY")
database_url = os.environ.get("DATABASE_URL", "sqlite:///" + str(BASE / "quick_reminder.db"))
# Render and some providers may expose postgres://; SQLAlchemy/psycopg use postgresql+psycopg://.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
db = SQLAlchemy(app)

ALLOWED = {"pdf", "png", "jpg", "jpeg", "webp"}
DOC_TYPES = [
    "Aadhaar Card", "PAN Card", "Voter ID", "Driving Licence",
    "10th Class Certificate", "Date of Birth Certificate",
    "Passport", "Ration Card", "Health Card", "Education Certificate",
    "Other Important Document"
]

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    mobile = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="user")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    people = db.relationship("Person", backref="owner", cascade="all, delete-orphan")

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    relation = db.Column(db.String(60), default="Self")
    date_of_birth = db.Column(db.String(20), default="")
    gender = db.Column(db.String(30), default="")
    mobile = db.Column(db.String(30), default="")
    email = db.Column(db.String(150), default="")
    address = db.Column(db.Text, default="")
    aadhaar_number = db.Column(db.String(50), default="")
    pan_number = db.Column(db.String(50), default="")
    voter_id = db.Column(db.String(50), default="")
    driving_licence = db.Column(db.String(80), default="")
    passport_number = db.Column(db.String(80), default="")
    ration_card = db.Column(db.String(80), default="")
    other_id = db.Column(db.String(120), default="")
    documents = db.relationship("Document", backref="person", cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey("person.id"), nullable=False)
    document_type = db.Column(db.String(100), nullable=False)
    document_number = db.Column(db.String(100), default="")
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey("person.id"), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    remind_at = db.Column(db.DateTime, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    person = db.relationship("Person")
    owner = db.relationship("User")

with app.app_context():
    db.create_all()
    # Demo admin account. Change this password before real use.
    if not User.query.filter_by(email="admin@quickreminder.local").first():
        admin = User(
            name="Administrator",
            email="admin@quickreminder.local",
            mobile="9999999999",
            password_hash=generate_password_hash("Admin@123"),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()

def current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None

@app.context_processor
def inject_user():
    return {"logged_user": current_user()}

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or user.role != "admin":
            flash("Administrator access required.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped

def owned_person(person_id):
    person = Person.query.get_or_404(person_id)
    user = current_user()
    if user.role != "admin" and person.owner_id != user.id:
        from flask import abort
        abort(403)
    return person

def owned_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    user = current_user()
    if user.role != "admin" and doc.person.owner_id != user.id:
        from flask import abort
        abort(403)
    return doc

@app.route("/")
def home():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        mobile = request.form.get("mobile","").strip()
        password = request.form.get("password","")
        confirm = request.form.get("confirm_password","")
        if not all([name, email, mobile, password]):
            flash("All fields are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email is already registered.", "error")
        elif User.query.filter_by(mobile=mobile).first():
            flash("Mobile number is already registered.", "error")
        else:
            user = User(name=name, email=email, mobile=mobile,
                        password_hash=generate_password_hash(password), role="user")
            db.session.add(user)
            db.session.commit()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        identifier = request.form.get("identifier","").strip().lower()
        password = request.form.get("password","")
        user = User.query.filter(
            (User.email == identifier) | (User.mobile == identifier)
        ).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            flash("Login successful.", "success")
            return redirect(url_for("admin_dashboard" if user.role == "admin" else "dashboard"))
        flash("Invalid email/mobile or password.", "error")
    return render_template("login.html")

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        user = User.query.filter_by(email=email, role="admin").first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            return redirect(url_for("admin_dashboard"))
        flash("Invalid administrator credentials.", "error")
    return render_template("admin_login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    # Demo/local reset flow. A production app should send an OTP/email.
    if request.method == "POST":
        identifier = request.form.get("identifier","").strip().lower()
        user = User.query.filter(
            (User.email == identifier) | (User.mobile == identifier)
        ).first()
        if not user:
            flash("No account was found.", "error")
            return render_template("forgot.html")
        session["reset_user_id"] = user.id
        return redirect(url_for("reset_password"))
    return render_template("forgot.html")

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    uid = session.get("reset_user_id")
    if not uid:
        return redirect(url_for("forgot_password"))
    user = User.query.get_or_404(uid)
    if request.method == "POST":
        password = request.form.get("password","")
        confirm = request.form.get("confirm_password","")
        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            session.pop("reset_user_id", None)
            flash("Password reset successfully.", "success")
            return redirect(url_for("login"))
    return render_template("reset.html", user=user)

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    people = Person.query.filter_by(owner_id=user.id).order_by(Person.name).all()
    documents = Document.query.join(Person).filter(Person.owner_id == user.id).count()
    pending = Reminder.query.filter_by(owner_id=user.id, completed=False).count()
    return render_template("dashboard.html", people=people, documents=documents, pending=pending)

@app.route("/person/add", methods=["GET", "POST"])
@login_required
def add_person():
    if request.method == "POST":
        p = Person(owner_id=current_user().id)
        update_person(p)
        if not p.name:
            flash("Name is required.", "error")
            return render_template("person_form.html", person=p)
        db.session.add(p)
        db.session.commit()
        flash("Family member added.", "success")
        return redirect(url_for("person_detail", person_id=p.id))
    return render_template("person_form.html", person=None)

def update_person(p):
    fields = ["name","relation","date_of_birth","gender","mobile","email","address",
              "aadhaar_number","pan_number","voter_id","driving_licence",
              "passport_number","ration_card","other_id"]
    for f in fields:
        setattr(p, f, request.form.get(f,"").strip())

@app.route("/person/<int:person_id>")
@login_required
def person_detail(person_id):
    p = owned_person(person_id)
    reminders = Reminder.query.filter_by(owner_id=current_user().id, person_id=p.id).order_by(Reminder.remind_at).all()
    return render_template("person_detail.html", person=p, doc_types=DOC_TYPES, reminders=reminders)

@app.route("/person/<int:person_id>/edit", methods=["GET","POST"])
@login_required
def edit_person(person_id):
    p = owned_person(person_id)
    if request.method == "POST":
        update_person(p)
        if not p.name:
            flash("Name is required.", "error")
            return render_template("person_form.html", person=p)
        db.session.commit()
        flash("Personal details updated.", "success")
        return redirect(url_for("person_detail", person_id=p.id))
    return render_template("person_form.html", person=p)

@app.post("/person/<int:person_id>/delete")
@login_required
def delete_person(person_id):
    p = owned_person(person_id)
    for d in p.documents:
        f = UPLOAD_DIR / d.stored_name
        if f.exists(): f.unlink()
    db.session.delete(p)
    db.session.commit()
    flash("Family member deleted.", "success")
    return redirect(url_for("dashboard"))

@app.post("/person/<int:person_id>/document/upload")
@login_required
def upload_document(person_id):
    p = owned_person(person_id)
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please choose a file.", "error")
        return redirect(url_for("person_detail", person_id=p.id))
    if "." not in file.filename or file.filename.rsplit(".",1)[1].lower() not in ALLOWED:
        flash("Allowed files: PDF, PNG, JPG, JPEG, WEBP.", "error")
        return redirect(url_for("person_detail", person_id=p.id))
    original = secure_filename(file.filename)
    stored = uuid.uuid4().hex + "_" + original
    file.save(UPLOAD_DIR / stored)
    d = Document(person_id=p.id,
                 document_type=request.form.get("document_type","Other Important Document"),
                 document_number=request.form.get("document_number","").strip(),
                 original_name=original, stored_name=stored)
    db.session.add(d)
    db.session.commit()
    flash("Document uploaded.", "success")
    return redirect(url_for("person_detail", person_id=p.id))

@app.get("/document/<int:doc_id>/download")
@login_required
def download_document(doc_id):
    d = owned_document(doc_id)
    return send_from_directory(UPLOAD_DIR, d.stored_name, as_attachment=True, download_name=d.original_name)

@app.route("/document/<int:doc_id>/edit", methods=["GET","POST"])
@login_required
def edit_document(doc_id):
    d = owned_document(doc_id)
    if request.method == "POST":
        d.document_type = request.form.get("document_type", d.document_type)
        d.document_number = request.form.get("document_number","").strip()
        db.session.commit()
        flash("Document updated.", "success")
        return redirect(url_for("person_detail", person_id=d.person_id))
    return render_template("document_edit.html", doc=d, doc_types=DOC_TYPES)

@app.post("/document/<int:doc_id>/delete")
@login_required
def delete_document(doc_id):
    d = owned_document(doc_id)
    pid = d.person_id
    f = UPLOAD_DIR / d.stored_name
    if f.exists(): f.unlink()
    db.session.delete(d)
    db.session.commit()
    flash("Document deleted.", "success")
    return redirect(url_for("person_detail", person_id=pid))

@app.route("/reminders", methods=["GET","POST"])
@login_required
def reminders():
    user = current_user()
    if request.method == "POST":
        try:
            dt = datetime.fromisoformat(request.form["remind_at"])
            pid = int(request.form["person_id"]) if request.form.get("person_id") else None
            if pid:
                owned_person(pid)
            r = Reminder(owner_id=user.id, person_id=pid,
                         title=request.form.get("title","").strip(),
                         description=request.form.get("description","").strip(),
                         remind_at=dt)
            db.session.add(r); db.session.commit()
            flash("Reminder created.", "success")
        except Exception:
            flash("Please enter valid reminder details.", "error")
        return redirect(url_for("reminders"))
    people = Person.query.filter_by(owner_id=user.id).order_by(Person.name).all()
    rs = Reminder.query.filter_by(owner_id=user.id).order_by(Reminder.completed, Reminder.remind_at).all()
    return render_template("reminders.html", reminders=rs, people=people)

@app.post("/reminder/<int:reminder_id>/toggle")
@login_required
def toggle_reminder(reminder_id):
    r = Reminder.query.get_or_404(reminder_id)
    if r.owner_id != current_user().id: return ("Forbidden", 403)
    r.completed = not r.completed
    db.session.commit()
    return redirect(url_for("reminders"))

@app.post("/reminder/<int:reminder_id>/delete")
@login_required
def delete_reminder(reminder_id):
    r = Reminder.query.get_or_404(reminder_id)
    if r.owner_id != current_user().id: return ("Forbidden", 403)
    db.session.delete(r); db.session.commit()
    return redirect(url_for("reminders"))

# ---------- ADMIN ----------
@app.route("/admin")
@admin_required
def admin_dashboard():
    users = User.query.filter_by(role="user").order_by(User.name).all()
    people = Person.query.count()
    documents = Document.query.count()
    return render_template("admin.html", users=users, people=people, documents=documents)

@app.post("/admin/user/<int:user_id>/delete")
@admin_required
def admin_delete_user(user_id):
    u = User.query.get_or_404(user_id)
    for p in u.people:
        for d in p.documents:
            f = UPLOAD_DIR / d.stored_name
            if f.exists(): f.unlink()
    db.session.delete(u)
    db.session.commit()
    flash("User account deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/user/<int:user_id>")
@admin_required
def admin_user_detail(user_id):
    u = User.query.get_or_404(user_id)
    return render_template("admin_user.html", account=u)

@app.route("/admin/people")
@admin_required
def admin_people():
    people = Person.query.order_by(Person.name).all()
    return render_template("admin_people.html", people=people)

@app.route("/admin/documents")
@admin_required
def admin_documents():
    docs = Document.query.order_by(Document.uploaded_at.desc()).all()
    return render_template("admin_documents.html", documents=docs)

if __name__ == "__main__":
    app.run(debug=True)
