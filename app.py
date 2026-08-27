import os
import io
import csv
from datetime import datetime as _dt, timedelta, timezone
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask import send_file
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import smtplib
from email.message import EmailMessage
import json  # make sure this is at top of file
import requests

from utils.device_status import get_device_status
from datetime import datetime, timedelta, timezone

import math
from models import Geofence, GeofenceEvent
from flask_migrate import Migrate
# =========================
# TRACCAR CONFIG (IP-SAFE)
# =========================

# Try to read from environment first (best practice)
TRACCAR_URL = os.environ.get("TRACCAR_URL")

# If not set, guess based on where the app is running
if not TRACCAR_URL:
    try:
        import requests
        public_ip = requests.get("https://api64.ipify.org?format=text", timeout=5).text.strip()
        if ":" in public_ip:
            TRACCAR_URL = f"http://[{public_ip}]:8082"
        else:
            TRACCAR_URL = f"http://{public_ip}:8082"
    except Exception:
        TRACCAR_URL = "http://localhost:8082"

TRACCAR_USER = os.environ.get("TRACCAR_USER", "lakshyaa.otp@gmail.com")
TRACCAR_PASS = os.environ.get("TRACCAR_PASS", "Lakshyaa@Dhyey0911")

def point_in_circle(lat, lng, center_lat, center_lng, radius_m):
    R = 6371000  # Earth radius in meters
    d_lat = math.radians(center_lat - lat)
    d_lng = math.radians(center_lng - lng)

    a = (
        math.sin(d_lat / 2) ** 2 +
        math.cos(math.radians(lat)) *
        math.cos(math.radians(center_lat)) *
        math.sin(d_lng / 2) ** 2
    )

    distance = 2 * R * math.asin(math.sqrt(a))
    return distance <= radius_m


def point_in_polygon(lat, lng, polygon_coords):
    x = lng
    y = lat

    inside = False
    points = polygon_coords
    n = len(points)

    p1x, p1y = points[0][1], points[0][0]

    for i in range(n + 1):
        p2x, p2y = points[i % n][1], points[i % n][0]
        if min(p1y, p2y) < y <= max(p1y, p2y):
            if x <= max(p1x, p2x):
                if p1y != p2y:
                    xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                if p1x == p2x or x <= xinters:
                    inside = not inside
        p1x, p1y = p2x, p2y

    return inside

def check_geofences(device, lat, lng):
    from sqlalchemy import or_
    geofences = Geofence.query.filter(
        Geofence.user_id == device.user_id,
        or_(Geofence.device_id == None, Geofence.device_id == device.id)
    ).all()

    for fence in geofences:
        inside = False

        # ---- CIRCLE ----
        if fence.lat and fence.lng and fence.radius_meters:
            inside = point_in_circle(
                lat,
                lng,
                fence.lat,
                fence.lng,
                fence.radius_meters
            )

        # ---- POLYGON ----
        elif fence.polygon_points:
            inside = point_in_polygon(
                lat,
                lng,
                fence.polygon_points
            )

        # Check last state from DB (instead of temporary attribute)
        last_event = GeofenceEvent.query.filter_by(
            device_id=device.id,
            geofence_id=fence.id
        ).order_by(GeofenceEvent.timestamp.desc()).first()

        was_inside = False
        if last_event:
            was_inside = (last_event.event_type == "ENTER")

        # ENTER
        if inside and not was_inside:
            event = GeofenceEvent(
                device_id=device.id,
                geofence_id=fence.id,
                event_type="ENTER"
            )
            db.session.add(event)
            user = User.query.get(device.user_id)
            if user and user.email:
                send_email(
                    to_email=user.email,
                    subject=f"🚨 Geofence Alert: {device.name} entered {fence.name}",
                    body=f"Your device '{device.name}' has entered the geofence '{fence.name}'.\n\nTime: {datetime.now(timezone.utc).replace(tzinfo=None)}"
                )
        # EXIT
        elif not inside and was_inside:
            event = GeofenceEvent(
                device_id=device.id,
                geofence_id=fence.id,
                event_type="EXIT"
            )
            db.session.add(event)
            user = User.query.get(device.user_id)
            if user and user.email:
                send_email(
                    to_email=user.email,
                    subject=f"🚨 Geofence Alert: {device.name} exited {fence.name}",
                    body=f"Your device '{device.name}' has exited the geofence '{fence.name}'.\n\nTime: {datetime.now(timezone.utc).replace(tzinfo=None)}"
                )
    db.session.commit()
# persistent session to hold cookies
traccar_session = requests.Session()

def check_speed_alert(device, speed_kmh):
    if not device.speed_limit or speed_kmh <= device.speed_limit:
        return
    user = User.query.get(device.user_id)
    if user and user.email:
        send_email(
            to_email=user.email,
            subject=f"🚨 Speed Alert: {device.name} is overspeeding!",
            body=f"Your device '{device.name}' is travelling at {speed_kmh:.1f} km/h, exceeding your limit of {device.speed_limit:.1f} km/h."
        )

'''def traccar_login():
    """Logs into Traccar and stores session cookies."""
    try:
        data = {
            "email": TRACCAR_USER,
            "password": TRACCAR_PASS
        }
        resp = traccar_session.post(f"{TRACCAR_URL}/api/session", data=data)
        print(f"🔐 Traccar login: {resp.status_code}")
        if resp.status_code == 200:
            print("✅ Traccar session established.")
            return True
        else:
            print(f"❌ Login failed: {resp.text}")
            return False
    except Exception as e:
        print(f"⚠️ Traccar login error: {e}")
        return False'''
def traccar_login():
    """Logs into Traccar and stores session cookies."""
    try:
        data = {
            "email": TRACCAR_USER,       # ✅ Use correct variable names
            "password": TRACCAR_PASS
        }
        resp = traccar_session.post(f"{TRACCAR_URL}/api/session", data=data)
        print(f"🔐 Traccar login: {resp.status_code}")
        if resp.status_code == 200:
            print("✅ Traccar session established.")
            return True
        else:
            print(f"❌ Login failed: {resp.text}")
            return False
    except Exception as e:
        print(f"⚠️ Traccar login error: {e}")
        return False


def traccar_get_devices():
    """Fetch devices directly from the Traccar server."""
    try:
        response = requests.get(
            f"{TRACCAR_URL}/api/devices",
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Traccar device fetch failed: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"⚠️ Error connecting to Traccar: {e}")
        return []


from models import db, User, Device, Location, OTP, PasswordResetToken
from sqlalchemy import or_
#from routes import routes

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///gps_tracker.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from routes_traccar import traccar
#app.register_blueprint(routes)
app.register_blueprint(traccar, url_prefix="/traccar")

# Default session lifetime
app.permanent_session_lifetime = timedelta(minutes=30)

db.init_app(app)
migrate = Migrate(app, db)
print("SMTP DEBUG:", os.environ.get("SMTP_HOST"), os.environ.get("SMTP_USER"))

def send_email(to_email: str, subject: str, body: str) -> bool:
    """
    Sends email using SMTP environment variables. Returns True if sent.
    If SMTP not configured, log to server and return False.
    Required env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS (SMTP_PORT optional)
    """
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT", "587")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    if not (host and user and password):
        app.logger.info("SMTP not configured - email content:\nTo: %s\nSubject: %s\n\n%s", to_email, subject, body)
        return False

    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"GPS Tracker <{user}>"
        msg["To"] = to_email
        msg["X-Mailer"] = "GPS Tracker App"
        msg.set_content(body)
        with smtplib.SMTP(host, int(port)) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception as e:
        app.logger.exception("Failed to send email: %s", e)
        return False

def reverse_geocode(lat, lng):
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json"},
            headers={"User-Agent": "GPSTrackerApp/1.0"},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("display_name", f"{lat}, {lng}")
    except:
        pass
    return f"{lat:.4f}, {lng:.4f}"

@app.context_processor
def inject_unread_alerts():
    if "user_id" in session:
        try:
            user = User.query.get(session["user_id"])
            device_ids = [d.id for d in user.devices]
            unread = GeofenceEvent.query.filter(
                GeofenceEvent.device_id.in_(device_ids),
                GeofenceEvent.seen == False
            ).count() if device_ids else 0
        except:
            unread = 0
    else:
        unread = 0
    return dict(unread_alerts=unread)

@app.route("/")
def home():
    return render_template("home.html", logged_in=('user_id' in session))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "warning")
            return redirect(url_for("register"))

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or email already exists.", "danger")
            return redirect(url_for("register"))

        hashed = generate_password_hash(password)
        user = User(username=username, email=email, password=hashed, is_verified=False)
        db.session.add(user)
        db.session.commit()

        # create OTP
        otp_entry = OTP.create_for_user(user.id, expiry_minutes=10)
        db.session.add(otp_entry)
        db.session.commit()

        # Send OTP by email (or log it if SMTP not configured)
        subject = "Your GPS Tracker verification code"
        body = f"Hi {username},\n\nYour verification code is: {otp_entry.code}\nIt will expire at {otp_entry.expires_at.isoformat()} UTC.\n\nIf you did not request this, ignore."
        sent = send_email(email, subject, body)

        if sent:
            flash("Verification code sent to your email. Please check and verify your account.", "info")
        else:
            # For development: we do NOT flash the OTP to the browser, only log it to server.
            app.logger.info("OTP for %s (user id=%s): %s", email, user.id, otp_entry.code)
            flash("Verification code could not be sent by email (SMTP not configured). Check server logs for the code.", "warning")

        return redirect(url_for("verify_otp", user_id=user.id))

    return render_template("register.html")


@app.route("/verify/<int:user_id>", methods=["GET", "POST"])
def verify_otp(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_verified:
        flash("Account already verified. Please login.", "info")
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form.get("otp", "").strip()
        otp = OTP.query.filter_by(user_id=user.id, code=code, used=False).first()
        if otp and otp.expires_at > datetime.now(timezone.utc).replace(tzinfo=None):
            user.is_verified = True
            otp.used = True
            db.session.commit()
            flash("Your account is verified — you can now log in.", "success")
            return redirect(url_for("login"))
        else:
            flash("Invalid or expired OTP. Please request a new code.", "danger")
            return redirect(url_for("verify_otp", user_id=user.id))

    return render_template("verify.html", user=user)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form.get('username', "").strip()
        password = request.form.get('password', "")
        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()

        if user and check_password_hash(user.password, password):
            if not user.is_verified:
                flash("Please verify your email before logging in.", "warning")
                return redirect(url_for("verify_otp", user_id=user.id))

            session['user_id'] = user.id
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")

# ---- PASSWORD RESET ----
@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    reset = PasswordResetToken.query.filter_by(token=token, used=False).first()

    if not reset or reset.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        flash("❌ Invalid or expired reset link.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        new_pass = request.form.get("new_password")
        if not new_pass or len(new_pass) < 6:
            flash("⚠️ Password must be at least 6 characters.", "warning")
            return redirect(url_for("reset_password", token=token))

        user = User.query.get(reset.user_id)
        user.password = generate_password_hash(new_pass)
        reset.used = True
        db.session.commit()

        flash("✅ Password reset successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username")
        user = User.query.filter_by(username=username).first()

        if not user:
            flash("❌ No account found with that username.", "danger")
            return redirect(url_for("forgot_password"))

        # Generate token (30 min expiry by default)
        reset_entry = PasswordResetToken.create(user_id=user.id)
        token = reset_entry.token

        # Normally send via email – for now just display in flash
        reset_link = url_for('reset_password', token=token, _external=True)
        send_email(
            to_email=user.email,
            subject="Password Reset Request",
            body=f"Click the link below to reset your password:\n\n{reset_link}\n\nThis link expires in 30 minutes."
        )
        flash("✅ Password reset link sent. Please check your inbox and spam/junk folder.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


# --- other routes (unchanged logic, trimmed here for brevity) ---
# Copy your other existing routes for dashboard, devices, map, etc.
# Ensure imports at top include Device, Location, PasswordResetToken, OTP as included above.
# (For brevity I am not repeating all map/history routes here — keep the same content you had,
#  but ensure you're importing OTP & PasswordResetToken as shown above.)

# Example minimal dashboard stub (keep your full implementation)
'''@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    # build devices list as you already do in your working app
    devices = []
    for d in Device.query.filter_by(user_id=user.id).all():
        last_location = Location.query.filter_by(device_id=d.id).order_by(Location.timestamp.desc()).first()
        devices.append({
            "id": d.id,
            "name": d.name,
            "is_online": bool(last_location),
            "last_location": {"timestamp": last_location.timestamp.strftime("%Y-%m-%d %H:%M:%S") if last_location else "Never"}
        })
    return render_template("dashboard.html", devices=devices)'''
'''@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])

    # local devices (existing logic)
    devices = []
    for d in Device.query.filter_by(user_id=user.id).all():
        last_location = Location.query.filter_by(device_id=d.id).order_by(Location.timestamp.desc()).first()
        devices.append({
            "id": d.id,
            "name": d.name,
            "is_online": bool(last_location),
            "last_location": {"timestamp": last_location.timestamp.strftime("%Y-%m-%d %H:%M:%S") if last_location else "Never"}
        })

    # --- NEW: fetch Traccar devices and show link/online/status ---
    traccar_devices = []
    try:
        remote = traccar_get_devices()
        for rd in remote:
            # match by uniqueId -> local Device. Adjust field if your local field is imei or unique id
            local = Device.query.filter(or_(Device.imei == rd.get("uniqueId"), Device.imei == rd.get("uniqueId"))).first()
            traccar_devices.append({
                "traccar_id": rd.get("id"),
                "name": rd.get("name") or rd.get("uniqueId"),
                "uniqueId": rd.get("uniqueId"),
                "status": rd.get("status"),
                "lastUpdate": rd.get("lastUpdate"),
                "positionId": rd.get("positionId"),
                "linked_device_id": local.id if local else None,
                "linked": bool(local)
            })
    except Exception as e:
        app.logger.exception("Failed to fetch Traccar devices: %s", e)
        flash("Could not fetch Traccar devices (check logs).", "warning")

    return render_template("dashboard.html", devices=devices, traccar_devices=traccar_devices)'''


#from utils.device_status import get_device_status
from datetime import datetime, timezone

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    # 🔴 Fetch live Traccar positions
    live_positions = {}
    try:
        resp = requests.get(
            f"{TRACCAR_URL}/api/positions",
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=10
        )
        if resp.status_code == 200:
            for p in resp.json():
                live_positions[p["deviceId"]] = p
    except Exception as e:
        app.logger.warning(f"Traccar position fetch failed: {e}")

    devices_data = []

    for device in Device.query.filter_by(user_id=user.id).all():

        last_update = device.last_update
        speed_kmh = 0.0

        # ✅ Use Traccar as source of truth when linked
        if device.traccar_device_id and device.traccar_device_id in live_positions:
            pos = live_positions[device.traccar_device_id]

            # 🔁 Convert knots → km/h
            speed_knots = pos.get("speed") or 0
            speed_kmh = round(speed_knots * 1.852, 2)

            # Prefer serverTime → fixTime → deviceTime
            time_str = (
                pos.get("serverTime")
                or pos.get("fixTime")
                or pos.get("deviceTime")
            )

            if time_str:
                try:
                    last_update = datetime.fromisoformat(
                        time_str.replace("Z", "+00:00")
                    )
                except Exception:
                    pass

        # 🧠 Determine status
        current_status = get_device_status(last_update, speed_kmh)
        previous_status = device.last_status or "offline"

        # 🚨 Detect movement (idle → moving)
        movement_alert = (
            previous_status == "idle"
            and current_status == "moving"
        )

        # 💾 Persist state
        device.last_status = current_status
        device.last_update = last_update
        db.session.commit()

        devices_data.append({
            "id": device.id,
            "name": device.name,
            "imei": device.imei,
            "plate_number": getattr(device, 'plate_number', '') or '',
            "device_type": getattr(device, 'type', 'bike') or 'bike',
            "status": current_status,
            "lastUpdate": (
                last_update.strftime("%Y-%m-%d %H:%M:%S")
                if last_update else "Never"
            ),
            "speed": speed_kmh,
            "last_latitude": device.last_lat,
            "last_longitude": device.last_lng,
            "battery": 98.0,
            "heading": 0.0,
            "linked": bool(device.traccar_device_id),
            "traccar_device_id": device.traccar_device_id,
            "movement_alert": movement_alert
        })

    stats = {
        "total": len(devices_data),
        "moving": sum(1 for d in devices_data if d["status"] == "moving"),
        "idle": sum(1 for d in devices_data if d["status"] == "idle"),
        "stopped": sum(1 for d in devices_data if d["status"] == "stopped"),
        "offline": sum(1 for d in devices_data if d["status"] == "offline"),
    }

    devices_json = [
        {
            "id": d["id"],
            "name": d["name"],
            "imei": d.get("imei", ""),
            "plate_number": d.get("plate_number", ""),
            "device_type": d.get("device_type", "bike"),
            "driver_name": "Assigned Operator",
            "status": d["status"],
            "latitude": d.get("last_latitude") or 23.0225,
            "longitude": d.get("last_longitude") or 72.5714,
            "speed": d.get("speed", 0.0),
            "heading": 0.0,
            "battery": 98.0,
            "last_update": d.get("lastUpdate", "Never")
        }
        for d in devices_data
    ]

    active_alerts_count = sum(1 for d in devices_data if d.get("movement_alert"))

    return render_template(
        "dashboard.html",
        devices=devices_data,
        stats=stats,
        devices_json=devices_json,
        active_alerts_count=active_alerts_count
    )

# ---- DEVICES LIST ----
"""
@app.route("/devices")
def devices():
    if "user_id" not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(session['user_id'])

    devices_data = []
    for device in user.devices:
        last_location = Location.query.filter_by(device_id=device.id).order_by(Location.timestamp.desc()).first()
        is_online = False
        if last_location and last_location.timestamp:
            if datetime.now(timezone.utc).replace(tzinfo=None) - last_location.timestamp < timedelta(minutes=2):
                is_online = True
        devices_data.append({
            "id": device.id,
            "name": device.name,
            "last_location": {
                "latitude": last_location.latitude if last_location else None,
                "longitude": last_location.longitude if last_location else None,
                "timestamp": last_location.timestamp if last_location else None
            }
        })

    return render_template("devices.html", devices=devices_data)
"""
"""
@app.route("/devices")
def devices():
    if "user_id" not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("login"))

    devices = Device.query.filter_by(
        user_id=session["user_id"]
    ).all()

    return render_template("devices.html", devices=devices)
"""
@app.route("/devices")
def devices():
    if "user_id" not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    # Fetch live Traccar positions (movement + speed)
    live_positions = {}
    try:
        resp = requests.get(
            f"{TRACCAR_URL}/api/positions",
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=10
        )
        if resp.status_code == 200:
            for p in resp.json():
                live_positions[p["deviceId"]] = p
    except Exception as e:
        app.logger.warning(f"Traccar position fetch failed: {e}")

    devices_data = []

    for device in Device.query.filter_by(user_id=user.id).all():

        last_update = device.last_update
        speed = 0

        # ✅ If linked to Traccar → trust Traccar
        if device.traccar_device_id and device.traccar_device_id in live_positions:
            pos = live_positions[device.traccar_device_id]
            speed = pos.get("speed", 0)

            time_str = (
                pos.get("serverTime")
                or pos.get("fixTime")
                or pos.get("deviceTime")
            )

            if time_str:
                last_update = datetime.fromisoformat(
                    time_str.replace("Z", "+00:00")
                )

        status = get_device_status(last_update, speed)

        devices_data.append({
            "id": device.id,
            "name": device.name,
            "status": status,              # moving / idle / offline
            "speed": round(speed, 1),
            "lastUpdate": (
                last_update.strftime("%Y-%m-%d %H:%M:%S")
                if last_update else "Never"
            ),
            "linked": bool(device.traccar_device_id),
            "traccar_device_id": device.traccar_device_id
        })

    return render_template("devices.html", devices=devices_data)

#-----DEVICE STATUS------
@app.route("/api/devices/status")
def api_devices_status():
    if "user_id" not in session:
        return {"error": "unauthorized"}, 401

    user = User.query.get(session["user_id"])

    # Fetch Traccar devices
    traccar_devices = traccar_get_devices()
    traccar_map = {d["id"]: d for d in traccar_devices}

    devices = Device.query.filter_by(user_id=user.id).all()
    response = []

    for device in devices:
        status = "offline"
        last_update = "Never"
        linked = False

        for td in traccar_map.values():
            if str(td.get("uniqueId")) == str(device.imei):
                linked = True
                status = td.get("status", "offline")
                last_update = td.get("lastUpdate")
                break

        response.append({
            "id": device.id,
            "status": status,
            "lastUpdate": last_update,
            "linked": linked
        })

    return {"devices": response}

@app.route("/api/device/share/<int:device_id>", methods=["POST"])
def share_device(device_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    device = Device.query.get_or_404(device_id)
    if device.user_id != session["user_id"]:
        return jsonify({"error": "Unauthorized"}), 403
    from models import DeviceShare
    share = DeviceShare(
        device_id=device.id,
        token=DeviceShare.generate_token(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    )
    db.session.add(share)
    db.session.commit()
    link = url_for("view_shared_device", token=share.token, _external=True)
    return jsonify({"status": "ok", "link": link})

@app.route("/shared/<token>")
def view_shared_device(token):
    from models import DeviceShare
    share = DeviceShare.query.filter_by(token=token).first_or_404()
    if share.expires_at and datetime.now(timezone.utc) > share.expires_at.replace(tzinfo=timezone.utc):
        return "This share link has expired.", 410
    return render_template("shared_device.html", device=share.device)

@app.route("/api/shared_location/<int:device_id>")
def shared_location(device_id):
    from models import DeviceShare
    # verify a valid share exists for this device
    share = DeviceShare.query.filter_by(device_id=device_id).first()
    if not share:
        return jsonify({"error": "Not found"}), 404
    loc = Location.query.filter_by(device_id=device_id).order_by(Location.timestamp.desc()).first()
    if not loc:
        return jsonify({})
    return jsonify({
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "speed": loc.speed,
        "timestamp": loc.timestamp.isoformat() if loc.timestamp else None
    })

@app.route("/reports")
def reports():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    devices = Device.query.filter_by(user_id=user.id).all()
    return render_template("reports.html", devices=devices)

@app.route("/api/reports/<int:device_id>")
def api_reports(device_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    device = Device.query.get_or_404(device_id)
    if device.user_id != session["user_id"]:
        return jsonify({"error": "Unauthorized"}), 403

    period = request.args.get("period", "7")  # days
    days = int(period)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    locations = (
        Location.query
        .filter(
            Location.device_id == device_id,
            Location.timestamp >= since.replace(tzinfo=None)
        )
        .order_by(Location.timestamp.asc())
        .all()
    )

    # Group by day
    from collections import defaultdict
    import math
    daily = defaultdict(lambda: {"points": 0, "max_speed": 0, "distance_km": 0, "idle_minutes": 0, "moving_minutes": 0})
    prev = None
    for loc in locations:
        day = loc.timestamp.strftime("%Y-%m-%d") if loc.timestamp else "Unknown"
        daily[day]["points"] += 1
        speed = loc.speed or 0
        if speed > daily[day]["max_speed"]:
            daily[day]["max_speed"] = round(speed, 1)
        if prev and prev.timestamp and loc.timestamp:
            time_diff_minutes = (loc.timestamp - prev.timestamp).total_seconds() / 60
            if time_diff_minutes < 60:  # ignore gaps > 1 hour
                if speed <= 3:
                    daily[day]["idle_minutes"] = round(daily[day]["idle_minutes"] + time_diff_minutes, 1)
                else:
                    daily[day]["moving_minutes"] = round(daily[day]["moving_minutes"] + time_diff_minutes, 1)
            lat1, lng1 = math.radians(prev.latitude), math.radians(prev.longitude)
            lat2, lng2 = math.radians(loc.latitude), math.radians(loc.longitude)
            dlat, dlng = lat2 - lat1, lng2 - lng1
            a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
            km = 6371 * 2 * math.asin(math.sqrt(a))
            daily[day]["distance_km"] = round(daily[day]["distance_km"] + km, 2)
        prev = loc
    report = [{"date": d, **v} for d, v in sorted(daily.items())]
    return jsonify({
        "device": device.name,
        "period_days": days,
        "total_points": len(locations),
        "daily": report
    })

@app.route("/api/traccar/route/<int:device_id>")
def traccar_route(device_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    device = Device.query.get_or_404(device_id)
    if device.user_id != session["user_id"]:
        return jsonify({"error": "Unauthorized"}), 403

    from_time = request.args.get("from")
    to_time = request.args.get("to")

    if not from_time or not to_time:
        return jsonify({"error": "Missing from/to params"}), 400

    try:
        # Try Traccar first if device is linked
        if device.traccar_device_id:
            resp = requests.get(
                f"{TRACCAR_URL}/api/positions",
                params={
                    "deviceId": device.traccar_device_id,
                    "from": from_time,
                    "to": to_time
                },
                auth=(TRACCAR_USER, TRACCAR_PASS),
                timeout=10
            )
            if resp.status_code == 200 and resp.json():
                positions = resp.json()
                return jsonify([{
                    "latitude": p.get("latitude"),
                    "longitude": p.get("longitude"),
                    "speed": p.get("speed", 0),
                    "serverTime": p.get("serverTime")
                } for p in positions])

        # Fallback to local DB
        from datetime import datetime
        try:
            from_dt = datetime.fromisoformat(from_time.replace("Z", "+00:00")).replace(tzinfo=None)
            to_dt = datetime.fromisoformat(to_time.replace("Z", "+00:00")).replace(tzinfo=None)
        except:
            return jsonify({"error": "Invalid time format"}), 400

        locations = (
            Location.query
            .filter(
                Location.device_id == device_id,
                Location.timestamp >= from_dt,
                Location.timestamp <= to_dt
            )
            .order_by(Location.timestamp.asc())
            .all()
        )

        return jsonify([{
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "speed": loc.speed or 0,
            "serverTime": loc.timestamp.isoformat() if loc.timestamp else None
        } for loc in locations])

    except Exception as e:
        app.logger.exception("Route fetch error: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route("/trips")
def trips():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))
    from models import Trip
    user = User.query.get(session["user_id"])
    device_ids = [d.id for d in user.devices]
    all_trips = (
        Trip.query
        .filter(Trip.device_id.in_(device_ids))
        .order_by(Trip.start_time.desc())
        .limit(50)
        .all()
    )
    return render_template("trips.html", trips=all_trips)

@app.route("/api/geocode")
def geocode():
    lat = request.args.get("lat")
    lng = request.args.get("lng")
    if not lat or not lng:
        return jsonify({"address": "Unknown"})
    address = reverse_geocode(float(lat), float(lng))
    # Shorten the address - just city and state
    parts = address.split(",")
    short = ", ".join(parts[:3]) if len(parts) >= 3 else address
    return jsonify({"address": short})

@app.route("/alerts")
def alerts():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    device_ids = [d.id for d in user.devices]
    events = (
        GeofenceEvent.query
        .filter(GeofenceEvent.device_id.in_(device_ids))
        .order_by(GeofenceEvent.timestamp.desc())
        .limit(100)
        .all()
    )
    
    # Mark all as seen
    GeofenceEvent.query.filter(
        GeofenceEvent.device_id.in_(device_ids),
        GeofenceEvent.seen == False
    ).update({"seen": True}, synchronize_session=False)
    db.session.commit()

    return render_template("alerts.html", events=events)

@app.route("/geofences")
def geofences():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    from models import Geofence
    fences = Geofence.query.filter_by(user_id=user.id).all()
    devices = Device.query.filter_by(user_id=user.id).all()
    return render_template("geofences.html", geofences=fences, devices=devices)

@app.route("/api/geofence/create", methods=["POST"])
def create_geofence():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    print("📩 Geofence data received:", data, flush=True)

    name = data.get("name")
    fence_type = data.get("type")

    if not name or not fence_type:
        return jsonify({"error": "Missing required fields"}), 400

    # ---------- CIRCLE ----------
    if fence_type == "circle":
        lat = data.get("lat")
        lng = data.get("lng")
        radius = data.get("radius")

        if lat is None or lng is None or radius is None:
            return jsonify({"error": "Invalid circle data"}), 400

        device_id = data.get("device_id") or None
        fence = Geofence(
            user_id=session["user_id"],
            device_id=int(device_id) if device_id else None,
            name=name,
            lat=float(lat),
            lng=float(lng),
            radius_meters=float(radius),
            polygon_points=None
        )
    # ---------- POLYGON ----------
    elif fence_type == "polygon":
        points = data.get("points")

        if not points or not isinstance(points, list):
            return jsonify({"error": "Invalid polygon data"}), 400

        # Convert to simple [[lat,lng], [lat,lng], ...]
        polygon_coords = [[p["lat"], p["lng"]] for p in points]

        fence = Geofence(
            user_id=session["user_id"],
            name=name,
            lat=None,
            lng=None,
            radius_meters=None,
            polygon_points=polygon_coords
        )

    else:
        return jsonify({"error": "Invalid type"}), 400

    db.session.add(fence)
    db.session.commit()

    return jsonify({"status": "ok"})

@app.route("/api/geofence/delete/<int:fence_id>", methods=["DELETE"])
def delete_geofence(fence_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    fence = Geofence.query.get_or_404(fence_id)
    if fence.user_id != session["user_id"]:
        return jsonify({"error": "Unauthorized"}), 403
    db.session.delete(fence)
    db.session.commit()
    return jsonify({"status": "ok"})

# ---- LOGOUT ----
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

# ---- MAP ROUTES ----
@app.route("/integrations/traccar/link", methods=["POST"])
def link_traccar_device():
    if "user_id" not in session:
        return jsonify({"error": "unauthorized"}), 401
    traccar_id = request.form.get("traccar_id")
    uniqueId = request.form.get("uniqueId")
    name = request.form.get("name") or f"traccar-{uniqueId}"

    if not uniqueId:
        return jsonify({"error": "missing uniqueId"}), 400

    if Device.query.filter_by(imei=uniqueId).first():
        return jsonify({"error": "already linked"}), 400

    new_device = Device(user_id=session["user_id"], imei=uniqueId, name=name)
    db.session.add(new_device)
    db.session.commit()
    return jsonify({"status": "ok", "device_id": new_device.id})
# Show all devices on the map
@app.route("/map")
def map_all_devices():
    if 'user_id' not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(session['user_id'])
    devices_data = []
    devices = Device.query.filter_by(user_id=user.id).all()

    for d in devices:
        last = (
            Location.query
            .filter_by(device_id=d.id)
            .order_by(Location.timestamp.desc())
            .first()
        )
        devices_data.append({
            "id": d.id,
            "name": d.name,
            "type": d.type or "car",  # default fallback
            "latitude": float(last.latitude) if last else None,
            "longitude": float(last.longitude) if last else None,
            "timestamp": last.timestamp.isoformat() if last and last.timestamp else None
        })

    if not devices_data:
        flash("No devices with location data yet.", "info")
        return redirect(url_for("dashboard"))

    return render_template("map.html", devices=devices_data, logged_in=True)

# Show a single device
@app.route("/map/device/<int:device_id>")
def map_device(device_id):
    if "user_id" not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("login"))

    device = Device.query.filter_by(id=device_id, user_id=session["user_id"]).first()
    if not device:
        flash("Device not found", "danger")
        return redirect(url_for("dashboard"))

    try:
        positions = get_positions_for_device(1)  # Traccar’s numeric ID, not IMEI
        if not positions:
            flash("No map data available for this device yet.", "info")
            return render_template("map.html", device=device, positions=[])

        # pick the last known position
        pos = positions[-1]
        lat = pos.get("latitude")
        lng = pos.get("longitude")

        print(f"📍 Latest position for device {device_id}: ({lat}, {lng})")

        return render_template(
            "map.html",
            device=device,
            positions=positions,
            latitude=lat,
            longitude=lng
        )
    except Exception as e:
        app.logger.exception(f"Map fetch error: {e}")
        flash("Error fetching map data.", "danger")
        return redirect(url_for("dashboard"))

@app.route("/api/traccar_webhook", methods=["POST"])
def traccar_webhook():
    data = request.get_json(force=True, silent=True) or {}
    print("📡 Traccar webhook received:", data, flush=True)

    device_id = data.get("deviceId")
    lat = data.get("lat") or data.get("latitude")
    lng = data.get("lon") or data.get("lng") or data.get("longitude")

    if not device_id or lat is None or lng is None:
        return jsonify({"error": "Missing fields", "received": data}), 400

    # Find device by Traccar device ID (handle int/string mismatch)
    device = Device.query.filter_by(traccar_device_id=int(device_id)).first()
    if not device:
        print(f"❌ No device found for traccar_device_id={device_id}", flush=True)
        return jsonify({"error": "Device not found"}), 404

    # Save location
    loc = Location(
        device_id=device.id,
        latitude=float(lat),
        longitude=float(lng),
        timestamp=datetime.now(timezone.utc)
    )
    db.session.add(loc)
    device.last_update = datetime.now(timezone.utc)
    device.last_status = get_device_status(device.last_update)
    db.session.commit()

    # Trigger geofence check
    check_geofences(device, float(lat), float(lng))
    check_speed_alert(device, float(data.get("speed", 0)))

    return jsonify({"status": "ok"})
# ---- API: Receive device location ----
"""@app.route("/api/location", methods=["POST"])
def api_location():
    data = request.get_json() or {}
    imei = data.get("imei")
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if not all([imei, latitude, longitude]):
        return jsonify({"error": "Missing fields"}), 400

    device = Device.query.filter_by(imei=imei).first()
    if not device:
        return jsonify({"error": "Device not found"}), 404

    loc = Location(device_id=device.id, latitude=latitude, longitude=longitude)
    db.session.add(loc)
    db.session.commit()

    return jsonify({"status": "ok"})"""
@app.route("/api/location", methods=["POST"])
def api_location():
    data = request.get_json(force=True, silent=True) or {}

    print("📩 Received data from listener:", data, flush=True)

    # Try to handle both 'lat'/'lng' or 'latitude'/'longitude'
    imei = data.get("imei") or data.get("device_imei")
    latitude = data.get("latitude") or data.get("lat")
    longitude = data.get("longitude") or data.get("lng")

    if not imei or not latitude or not longitude:
        return jsonify({"error": "Missing fields", "received": data}), 400

    device = Device.query.filter_by(imei=imei).first()
    if not device:
        return jsonify({"error": "Device not found"}), 404

    loc = Location(device_id=device.id, latitude=latitude, longitude=longitude, timestamp=datetime.now(timezone.utc).replace(tzinfo=None))
    db.session.add(loc)

    # Update device last_update and status (fixes dashboard/devices mismatch)
    device.last_update = datetime.now(timezone.utc)
    device.last_status = get_device_status(device.last_update)
    db.session.commit()

    # Trigger geofence check (fixes missing alerts)
    check_geofences(device, float(latitude), float(longitude))

    print(f"✅ Location saved for IMEI {imei} at ({latitude}, {longitude})", flush=True)
    return jsonify({"status": "ok"})

@app.route("/api/update_location", methods=["POST"])
def update_location():
    data = request.get_json() or {}

    imei = data.get("imei")
    lat = data.get("lat")
    lng = data.get("lng")
    speed = data.get("speed")

    if not imei or lat is None or lng is None:
        return jsonify({"error": "Missing fields"}), 400

    device = Device.query.filter_by(imei=str(imei)).first()
    if not device:
        return jsonify({"error": "Device not found"}), 404

    # Update device info
    device.last_lat = float(lat)
    device.last_lng = float(lng)
    device.last_update = datetime.now(timezone.utc).replace(tzinfo=None)

    db.session.commit()

    # Also save full location log
    #loc = Location(device_id=device.id, lat=lat, lng=lng, speed=speed, timestamp=datetime.now(timezone.utc).replace(tzinfo=None))
    loc = Location(device_id=device.id, latitude=lat, longitude=lng, speed=speed, timestamp=datetime.now(timezone.utc).replace(tzinfo=None))
    db.session.add(loc)
    db.session.commit()

    check_geofences(device, float(lat), float(lng))

    return jsonify({"message": "Location updated successfully"}), 200

@app.route("/api/live_feed")
def live_feed():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        resp = requests.get(
            f"{TRACCAR_URL}/api/positions",
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=10
        )

        if resp.status_code != 200:
            return jsonify([])

        positions = resp.json()

        # normalize data for frontend
        live_data = []
        # Only return positions for devices belonging to logged-in user
        user = User.query.get(session["user_id"])
        user_traccar_ids = {
            d.traccar_device_id for d in user.devices
            if d.traccar_device_id is not None
        }

        for p in positions:
            if p.get("deviceId") not in user_traccar_ids:
                continue
            live_data.append({
                "deviceId": p.get("deviceId"),
                "latitude": p.get("latitude"),
                "longitude": p.get("longitude"),
                "speed": p.get("speed"),
                "fixTime": p.get("fixTime")
            })
        return jsonify(live_data)
    except Exception as e:
        app.logger.exception("Live feed error")
        return jsonify([])



# ---- ADD DEVICE ----
"""@app.route("/add_device", methods=["GET", "POST"])
def add_device():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        imei = request.form.get("imei", "").strip()
        name = request.form.get("name", "").strip()

        if not imei or not name:
            flash("IMEI and Name are required.", "danger")
            return redirect(url_for("add_device"))

        existing = Device.query.filter_by(imei=imei).first()
        if existing:
            flash("⚠️ Device with this IMEI already exists.", "warning")
            return redirect(url_for("add_device"))

        new_device = Device(user_id=session["user_id"], imei=imei, name=name)
        db.session.add(new_device)
        db.session.commit()

        flash("✅ Device added successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_device.html")"""

@app.route("/add_device", methods=["POST"])
def add_device():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    device_name = request.form.get("device_name", "").strip()
    device_imei = request.form.get("device_imei", "").strip()
    device_type = request.form.get("device_type", "car")

    if not device_name or not device_imei:
        flash("All fields are required!", "danger")
        return redirect(url_for("devices"))

    # Prevent duplicate IMEI in YOUR system
    if Device.query.filter_by(imei=device_imei).first():
        flash("⚠️ Device with this IMEI already exists.", "warning")
        return redirect(url_for("devices"))

    traccar_id = None

    try:
        # -------- STEP 1: CREATE DEVICE IN TRACCAR FIRST --------
        traccar_payload = {
            "name": device_name,
            "uniqueId": device_imei,
            "groupId": 2,                 # Must exist in Traccar
            "category": device_type.upper(),
            "phone": "",                  # Traccar requires this (can be blank)
            "model": device_type,         # Helpful metadata
            "contact": "Auto-added device",
            "disabled": False
        }

        create_resp = requests.post(
            f"{TRACCAR_URL}/api/devices",
            json=traccar_payload,
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=10
        )

        current_app.logger.info(f"Traccar URL used: {TRACCAR_URL}")
        current_app.logger.info(f"Payload sent to Traccar: {traccar_payload}")
        current_app.logger.info(f"Traccar response: {create_resp.status_code} - {create_resp.text}")


        if create_resp.status_code in [200, 201]:
            created_device = create_resp.json()
            traccar_id = created_device.get("id")
            current_app.logger.info(f"Traccar device created with ID {traccar_id}")
        else:
            current_app.logger.error(
                f"Traccar create failed: {create_resp.status_code} - {create_resp.text}"
            )

    except Exception as e:
        current_app.logger.exception("Traccar auto-create failed")

    # -------- STEP 2: SAVE DEVICE LOCALLY (WITH TRACCAR ID IF AVAILABLE) --------
    new_device = Device(
        name=device_name,
        imei=device_imei,
        type=device_type,
        user_id=session["user_id"],
        traccar_device_id=traccar_id
    )

    db.session.add(new_device)
    db.session.commit()

    if traccar_id:
        flash("✅ Device added & created in Traccar automatically!", "success")
    else:
        flash(
            "⚠️ Device added locally, but Traccar auto-creation failed. "
            "It may sync later.",
            "warning"
        )

    return redirect(url_for("devices"))


# Delete a device
@app.route("/devices/delete/<int:device_id>", methods=["POST"])
def delete_device(device_id):
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    device = Device.query.get_or_404(device_id)
    if device.user_id != session["user_id"]:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("devices"))

    db.session.delete(device)
    db.session.commit()
    flash("🗑️ Device deleted successfully!", "success")
    return redirect(url_for("devices"))


# Edit device name and type
@app.route("/devices/edit/<int:device_id>", methods=["GET", "POST"])
def edit_device(device_id):
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    device = Device.query.get_or_404(device_id)
    if device.user_id != session["user_id"]:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("devices"))

    if request.method == "POST":
        new_name = request.form.get("device_name", "").strip()
        new_type = request.form.get("type", device.type)
        speed_limit = request.form.get("speed_limit", "").strip()
        if new_name:
            existing_device = Device.query.filter_by(user_id=session["user_id"], name=new_name).first()
            if existing_device and existing_device.id != device.id:
                flash("⚠️ Another device already has that name.", "warning")
            else:
                device.name = new_name
                device.type = new_type
                device.speed_limit = float(speed_limit) if speed_limit else None
                db.session.commit()
                flash("✅ Device updated successfully!", "success")
                return redirect(url_for("devices"))

    return render_template("edit_device.html", device=device)

@app.route("/api/devices", methods=["GET"])
def api_devices():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user = User.query.get(session['user_id'])
    devices_data = []
    for d in user.devices:
        last = (
            Location.query
            .filter_by(device_id=d.id)
            .order_by(Location.timestamp.desc())
            .first()
        )
        devices_data.append({
            "id": d.id,
            "name": d.name,
            "latitude": float(last.latitude) if last else None,
            "longitude": float(last.longitude) if last else None,
            "timestamp": last.timestamp.isoformat() if last and last.timestamp else None
        })

    return jsonify(devices_data)

# ==============================
# API: Fetch location history
# ==============================
# ---- API: Fetch location history (with optional start/end datetime filters) ----
# avoid clash with existing import name

@app.route("/api/history/<int:device_id>")
def api_history(device_id):
    """
    Fetch filtered, ordered GPS history for a device.
    Supports ?from= and ?to= query params (ISO8601 or yyyy-mm-ddTHH:MM).
    If no range provided, defaults to last 24 hours.
    """

    #from datetime import datetime, timedelta

    # Parse input time filters
    def parse_time(t):
        if not t:
            return None
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(t, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(t)
        except Exception:
            return None

    from_time = request.args.get("from")
    to_time = request.args.get("to")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    from_dt = parse_time(from_time) or (now - timedelta(hours=24))
    to_dt = parse_time(to_time) or now

    query = (
        Location.query
        .filter_by(device_id=device_id)
        .filter(Location.timestamp >= from_dt, Location.timestamp <= to_dt)
        .order_by(Location.timestamp.asc())
    )

    data = query.all()

    clean_data = []
    last_point = None
    for loc in data:
        if not loc.latitude or not loc.longitude:
            continue
        if not (-90 <= loc.latitude <= 90 and -180 <= loc.longitude <= 180):
            continue
        if last_point and (loc.latitude == last_point["latitude"] and loc.longitude == last_point["longitude"]):
            # Skip duplicates to keep the line clean
            continue
        clean_data.append({
            "latitude": float(loc.latitude),
            "longitude": float(loc.longitude),
            "timestamp": loc.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "speed": float(getattr(loc, "speed", 0) or 0),
        })
        last_point = clean_data[-1]

    return jsonify(clean_data)


'''@app.route("/map/history/<int:device_id>")
def view_history(device_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        start_time = (now - timedelta(days=1)).isoformat() + "Z"
        end_time = now.isoformat() + "Z"

        response = traccar_session.get(
            f"{TRACCAR_URL}/api/reports/route",
            params={"deviceId": device_id, "from": start_time, "to": end_time},
            auth=(TRACCAR_USER, TRACCAR_PASS)
        )
        if response.status_code == 200:
            data = response.json()
            return render_template("history.html", history=data, device_id=device_id)
        flash("Failed to fetch history data.", "warning")
        return redirect(url_for("dashboard"))
    except Exception as e:
        app.logger.error(f"History fetch error: {e}")
        flash("Error fetching history.", "danger")
        return redirect(url_for("dashboard"))'''

@app.route("/map/history/clear/<int:device_id>", methods=["POST"])
def clear_history(device_id):
    if "user_id" not in session:
        flash("Please log in to continue.", "warning")
        return redirect(url_for("login"))

    device = Device.query.get_or_404(device_id)
    if device.user_id != session["user_id"]:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("dashboard"))

    # Delete all location entries for this device
    Location.query.filter_by(device_id=device.id).delete()
    db.session.commit()

    flash("🧹 Trip history cleared successfully!", "success")
    return redirect(url_for("view_history", device_id=device.id))

from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    user = User.query.get(session["user_id"])

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_profile":
            new_username = request.form.get("username", "").strip()
            new_email = request.form.get("email", "").strip().lower()
            if not new_username or not new_email:
                flash("Username and email cannot be empty.", "danger")
            elif User.query.filter(User.email == new_email, User.id != user.id).first():
                flash("Email already in use.", "danger")
            elif User.query.filter(User.username == new_username, User.id != user.id).first():
                flash("Username already taken.", "danger")
            else:
                user.username = new_username
                user.email = new_email
                db.session.commit()
                flash("✅ Profile updated successfully!", "success")
                return redirect(url_for("profile"))

        elif action == "update_password":
            new_pass = request.form.get("new_password")
            if not new_pass or len(new_pass) < 6:
                flash("Password must be at least 6 characters.", "danger")
            else:
                user.password = generate_password_hash(new_pass)
                db.session.commit()
                flash("✅ Password updated successfully!", "success")
                return redirect(url_for("profile"))

    return render_template("profile.html", user=user)

@app.route("/integrations/traccar/link", methods=["POST"])
def link_traccar_device_v2():
    if "user_id" not in session:
        return jsonify({"error": "unauthorized"}), 401
    traccar_id = request.form.get("traccar_id")
    uniqueId = request.form.get("uniqueId")
    name = request.form.get("name") or f"traccar-{uniqueId}"

    if not uniqueId:
        return jsonify({"error": "missing uniqueId"}), 400

    if Device.query.filter_by(imei=uniqueId).first():
        return jsonify({"error": "already linked"}), 400

    new_device = Device(user_id=session["user_id"], imei=uniqueId, name=name)
    db.session.add(new_device)
    db.session.commit()
    return jsonify({"status": "ok", "device_id": new_device.id})

def get_positions_for_device(device_id, limit=1):
    """Fetch latest positions from Traccar for a specific device."""
    try:
        resp = traccar_session.get(
            f"{TRACCAR_URL}/api/positions",
            timeout=10
        )

        # status check
        if resp.status_code != 200:
            current_app.logger.error(
                "Traccar positions failed %s: %s",
                resp.status_code,
                resp.text[:300],
            )
            return []

        # content-type safety
        if "application/json" not in resp.headers.get("Content-Type", ""):
            current_app.logger.error(
                "Non-JSON response from Traccar: %s",
                resp.text[:300],
            )
            return []

        data = resp.json()

        # Traccar sometimes returns a dict
        if isinstance(data, dict):
            data = [data]

        # Filter by Traccar deviceId
        filtered = [
            p for p in data
            if str(p.get("deviceId")) == str(device_id)
        ]

        if not filtered:
            current_app.logger.info(
                "No position data for device %s",
                device_id,
            )
            return []

        # Sort by fixTime (newest last)
        filtered.sort(key=lambda x: x.get("fixTime", ""))

        return filtered[-limit:]

    except Exception as e:
        current_app.logger.exception(
            "Error fetching positions for device %s",
            device_id,
        )
        return []


"""def get_positions_for_device(device_id, limit=1):
    '''Fetch latest positions from Traccar for a specific device.'''
    try:
        resp = traccar_session.get(f"{TRACCAR_URL}/api/positions", timeout=10)
    if resp.status_code != 200:
            print(f"⚠️ Traccar positions fetch failed: {resp.status_code} - {resp.text}")
            return []
    if resp.status_code != 200:
        current_app.logger.error(
            "Request failed %s: %s",
            resp.status_code,
            resp.text[:300],
        )
        return jsonify([])

    if "application/json" not in resp.headers.get("Content-Type", ""):
        current_app.logger.error(
            "Non-JSON response: %s",
            resp.text[:300],
        )
        return jsonify([])

    data = resp.json()

        if isinstance(data, dict):
            data = [data]

        # Filter by matching Traccar's deviceId (not IMEI)
        filtered = [p for p in data if str(p.get("deviceId")) == str(device_id)]

        if not filtered:
            print(f"ℹ️ No position data found for device {device_id}")
            return []

        # Sort newest last
        filtered.sort(key=lambda x: x.get("fixTime", ""))
        print(f"✅ Got {len(filtered)} positions for Traccar device {device_id}")
        return filtered[-limit:]
    except Exception as e:
        print(f"⚠️ Error fetching positions: {e}")
        return []
"""

@app.route("/integrations/traccar/positions/<int:traccar_device_id>")
def proxy_positions(traccar_device_id):
    try:
        positions = get_positions_for_device(traccar_device_id)
        if not positions:
            print(f"ℹ️ No Traccar positions found for device {traccar_device_id}")
            return jsonify([])

        # Normalize data for the frontend
        cleaned = []
        for p in positions:
            cleaned.append({
                "id": p.get("id"),
                "deviceId": p.get("deviceId"),
                "latitude": p.get("latitude"),
                "longitude": p.get("longitude"),
                "speed": p.get("speed"),
                "course": p.get("course"),
                "fixTime": p.get("fixTime"),
                "deviceTime": p.get("deviceTime"),
                "serverTime": p.get("serverTime")
            })
        return jsonify(cleaned)
    except Exception as e:
        app.logger.exception(f"Map fetch error: {e}")
        return jsonify([]), 500

traccar_login()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
