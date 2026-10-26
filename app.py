import os
from functools import wraps
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

from models import db, Slide, PresentationState
import slide_service

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "insecure-dev-secret-key-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 15}}
app.config["MAX_CONTENT_LENGTH"] = 150 * 1024 * 1024

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

db.init_app(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    ping_interval=25,
    ping_timeout=60
)

with app.app_context():
    db.create_all()
    PresentationState.get_current()
    slide_service.init_storage()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def get_state_payload():
    slides = Slide.query.order_by(Slide.order_index).all()
    total = len(slides)
    state = PresentationState.get_current()
    idx = state.current_slide_index

    if total == 0:
        return {
            "current_index": 0,
            "total_slides": 0,
            "current_slide": None
        }

    if idx < 1:
        idx = 1
        state.current_slide_index = 1
        db.session.commit()
    elif idx > total:
        idx = total
        state.current_slide_index = total
        db.session.commit()

    current_slide = next((s for s in slides if s.order_index == idx), None)
    if not current_slide and slides:
        current_slide = slides[0]
        idx = current_slide.order_index
        state.current_slide_index = idx
        db.session.commit()

    return {
        "current_index": idx,
        "total_slides": total,
        "current_slide": current_slide.to_dict() if current_slide else None
    }


def broadcast_state():
    payload = get_state_payload()
    socketio.emit("slide_state", payload)
    return payload


# --- Маршруты ---

@app.route("/")
def index():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("presentation_view"))


@app.route("/presentation")
def presentation_view():
    payload = get_state_payload()
    return render_template("presentation.html", state=payload)


@app.route("/api/state")
def api_state():
    return jsonify(get_state_payload())


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["is_admin"] = True
            session.permanent = True
            next_url = request.args.get("next") or url_for("admin_dashboard")
            return redirect(next_url)
        flash("Неверный пароль администратора", "error")

    return render_template("login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    slides = Slide.query.order_by(Slide.order_index).all()
    state = PresentationState.get_current()
    return render_template("admin.html", slides=slides, current_index=state.current_slide_index)


@app.route("/admin/control")
@login_required
def admin_control():
    payload = get_state_payload()
    return render_template("control.html", state=payload)


@app.route("/admin/api/upload", methods=["POST"])
@login_required
def admin_upload_slides():
    files = request.files.getlist("slides")
    target_pos = request.form.get("target_position")
    pos = int(target_pos) if target_pos and target_pos.isdigit() else None

    try:
        created = slide_service.add_slides_from_files(files, target_position=pos)
        flash(f"Успешно добавлено слайдов: {len(created)}", "success")
        broadcast_state()
    except Exception as e:
        flash(f"Ошибка при загрузке: {str(e)}", "error")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/api/delete/<int:slide_id>", methods=["POST"])
@login_required
def admin_delete_slide(slide_id):
    if slide_service.delete_slide(slide_id):
        flash("Слайд удалён", "success")
        broadcast_state()
    else:
        flash("Слайд не найден", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/api/clear", methods=["POST"])
@login_required
def admin_clear_all():
    slide_service.clear_all_slides()
    flash("Все слайды презентации удалены", "success")
    broadcast_state()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/api/control/<action>", methods=["POST"])
@login_required
def admin_control_action(action):
    slides_count = Slide.query.count()
    is_ajax = (request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json)

    if slides_count == 0:
        if is_ajax:
            return jsonify({"success": False, "error": "Нет слайдов"}), 400
        flash("Нет слайдов для показа", "error")
        return redirect(url_for("admin_dashboard"))

    state = PresentationState.get_current()
    if action == "next":
        if state.current_slide_index < slides_count:
            state.current_slide_index += 1
            db.session.commit()
    elif action == "prev":
        if state.current_slide_index > 1:
            state.current_slide_index -= 1
            db.session.commit()
    elif action == "goto":
        idx = request.json.get("index") if request.is_json else request.form.get("index")
        if idx and 1 <= int(idx) <= slides_count:
            state.current_slide_index = int(idx)
            db.session.commit()

    payload = broadcast_state()
    if is_ajax:
        return jsonify({"success": True, "state": payload})
    return redirect(url_for("admin_dashboard"))


# --- WebSocket события ---

@socketio.on("connect")
def handle_connect():
    emit("slide_state", get_state_payload())


@socketio.on("admin_next")
def handle_admin_next():
    if not session.get("is_admin"):
        return
    slides_count = Slide.query.count()
    state = PresentationState.get_current()
    if state.current_slide_index < slides_count:
        state.current_slide_index += 1
        db.session.commit()
        broadcast_state()


@socketio.on("admin_prev")
def handle_admin_prev():
    if not session.get("is_admin"):
        return
    state = PresentationState.get_current()
    if state.current_slide_index > 1:
        state.current_slide_index -= 1
        db.session.commit()
        broadcast_state()


@socketio.on("admin_goto")
def handle_admin_goto(data):
    if not session.get("is_admin"):
        return
    idx = data.get("index")
    slides_count = Slide.query.count()
    if idx and 1 <= int(idx) <= slides_count:
        state = PresentationState.get_current()
        state.current_slide_index = int(idx)
        db.session.commit()
        broadcast_state()


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5004))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)
