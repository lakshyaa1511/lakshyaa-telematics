import os
import json
import io
import csv
from functools import wraps

import requests
from flask import (
    Blueprint, render_template, session, jsonify,
    request, redirect, url_for, flash, current_app, send_file
)

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# =========================
# CONFIG
# =========================
traccar = Blueprint("traccar", __name__)

# =========================
# TRACCAR CONFIG (IP-PROOF)
# =========================

# Try to read from environment first (best practice)
TRACCAR_URL = os.environ.get("TRACCAR_URL")

# If not set, intelligently determine it
if not TRACCAR_URL:
    try:
        # If running on AWS, detect public IP
        public_ip = requests.get(
            "https://api64.ipify.org?format=text",
            timeout=5
        ).text.strip()
        TRACCAR_URL = f"http://{public_ip}:8082"
    except Exception:
        # Final fallback for local development
        TRACCAR_URL = "http://localhost:8082"

TRACCAR_USER = os.environ.get("TRACCAR_USER")
TRACCAR_PASS = os.environ.get("TRACCAR_PASS")

# =========================
# SYNC LOCAL AND TRACCAR
# =========================
def sync_traccar_device_ids():
    """
    Match local devices with Traccar devices using IMEI ↔ uniqueId
    and store traccar_device_id permanently.
    """
    from models import Device, db

    traccar_devices = get_traccar_devices()
    if not traccar_devices:
        return

    # Build lookup: uniqueId -> traccar id
    traccar_by_imei = {
        str(d.get("uniqueId")): d.get("id")
        for d in traccar_devices
        if d.get("uniqueId")
    }

    updated = 0

    for device in Device.query.filter(Device.traccar_device_id.is_(None)).all():
        traccar_id = traccar_by_imei.get(device.imei)
        if traccar_id:
            device.traccar_device_id = traccar_id
            updated += 1

    if updated:
        db.session.commit()

    current_app.logger.info(f"Traccar sync complete. Linked {updated} devices.")


# =========================
# AUTH DECORATOR
# =========================
def session_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

# =========================
# TRACCAR HELPERS
# =========================
def get_traccar_devices():
    if not TRACCAR_USER or not TRACCAR_PASS:
        current_app.logger.error(f"TRACCAR credentials missing .URL={TRACCAR_URL}")
        return []

    try:
        resp = requests.get(
            f"{TRACCAR_URL}/api/devices",
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        current_app.logger.exception("Failed to fetch Traccar devices")

    return []

# =========================
# MAP PAGES
# =========================
@traccar.route("/map")
@session_login_required
def map_all():
    sync_traccar_device_ids()
    devices = get_traccar_devices()
    return render_template(
        "map.html",
        devices=devices,
        selected_device_id=None
    )

@traccar.route("/map/<int:traccar_id>")
@session_login_required
def map_single(traccar_id):
    devices = get_traccar_devices()

    # Validate device exists in Traccar
    if not any(int(d.get("id")) == traccar_id for d in devices):
        flash("Device not found in Traccar.", "danger")
        return redirect(url_for("traccar.map_all"))

    return render_template(
        "map.html",
        devices=devices,
        selected_device_id=traccar_id
    )

# =========================
# HISTORY PAGE
# =========================
@traccar.route("/history/<int:traccar_id>")
@session_login_required
def history(traccar_id):
    devices = get_traccar_devices()

    device = next(
        (d for d in devices if int(d.get("id")) == traccar_id),
        None
    )

    if not device:
        flash("Device not found in Traccar.", "danger")
        return redirect(url_for("traccar.map_all"))

    device_obj = type("DeviceObject", (), device)

    return render_template(
        "device_history.html",
        device=device_obj
    )

# =========================
# LIVE POSITIONS API
# =========================
@traccar.route("/api/traccar/live_positions")
@session_login_required
def api_traccar_live_positions():
    try:
        devices_resp = requests.get(
            f"{TRACCAR_URL}/api/devices",
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=10
        )
        pos_resp = requests.get(
            f"{TRACCAR_URL}/api/positions",
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=10
        )

        if devices_resp.status_code != 200 or pos_resp.status_code != 200:
            return jsonify([]), 200

        devices = {d["id"]: d for d in devices_resp.json()}
        positions = pos_resp.json()

        results = []
        for p in positions:
            dev = devices.get(p.get("deviceId"))
            if not dev:
                continue

            lat, lng = p.get("latitude"), p.get("longitude")
            if not lat or not lng:
                continue

            results.append({
                "id": dev["id"],
                "name": dev["name"],
                "latitude": lat,
                "longitude": lng,
                "speed": p.get("speed", 0),
            })

        return jsonify(results), 200

    except Exception:
        current_app.logger.exception("Live position error")
        return jsonify([]), 200

# =========================
# HISTORY ROUTE API
# =========================
@traccar.route("/api/traccar/route/<int:device_id>")
@session_login_required
def api_traccar_route(device_id):
    from_time = request.args.get("from")
    to_time = request.args.get("to")

    if not from_time or not to_time:
        return jsonify([]), 200

    try:
        resp = requests.get(
            f"{TRACCAR_URL}/api/reports/route",
            params={
                "deviceId": device_id,
                "from": from_time,
                "to": to_time,
                "format": "json"
            },
            headers={"Accept": "application/json"},
            auth=(TRACCAR_USER, TRACCAR_PASS),
            timeout=20
        )

        if resp.status_code != 200:
            return jsonify([]), 200

        if "application/json" not in resp.headers.get("Content-Type", ""):
            current_app.logger.error("Non-JSON route response")
            return jsonify([]), 200

        return jsonify(resp.json()), 200

    except Exception:
        current_app.logger.exception("History route error")
        return jsonify([]), 200

# =========================
# CLEAR HISTORY (DUMMY)
# =========================
@traccar.route("/clear/history/<int:device_id>", methods=["POST"])
@session_login_required
def clear_history(device_id):
    flash("History cleared (simulated).", "warning")
    return redirect(url_for("traccar.map_single", device_id=device_id))
