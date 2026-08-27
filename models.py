from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.sqlite import JSON
import secrets
import random

db = SQLAlchemy()

# 🔑 User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_verified = db.Column(db.Boolean, default=False)
    devices = db.relationship("Device", backref="user", lazy=True)

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', verified={self.is_verified})"


# 🚗 Device model
class Device(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    imei = db.Column(db.String(50), unique=True, nullable=False)
    type = db.Column(db.String(50), default="car")
    speed_limit = db.Column(db.Float, nullable=True)
    driver_id = db.Column(db.Integer,db.ForeignKey("driver.id"),nullable=True)
    # Last known position (updated by listener.py)
    last_lat = db.Column(db.Float)
    last_lng = db.Column(db.Float)
    last_update = db.Column(db.DateTime)
    last_status = db.Column(db.String(20), default="offline")
    # Relationship to historical locations (from listener.py)
    locations = db.relationship("Location", backref="device", lazy=True, order_by="Location.timestamp.desc()")

    # Optional: Traccar ID if device is linked from Traccar
    traccar_device_id = db.Column(db.Integer, unique=True, nullable=True) 

    def __repr__(self):
        return f"Device('{self.name}', '{self.imei}', User ID: {self.user_id})"

class Driver(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30))
    license_number = db.Column(db.String(50))
    notes = db.Column(db.Text)

    devices = db.relationship("Device", backref="driver", lazy=True)

    def __repr__(self):
        return f"Driver('{self.name}')"

# 📍 Historical Location model (saved from listener.py)
class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    speed = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"Location(Device {self.device_id}, Lat: {self.latitude:.4f}, Lng: {self.longitude:.4f})"


# 🔑 For password reset tokens
class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

    @staticmethod
    def generate_token():
        return secrets.token_hex(32)

    @classmethod
    def create(cls, user_id, expiry_minutes=30):
        token = cls.generate_token()
        entry = cls(
            user_id=user_id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(minutes=expiry_minutes)
        )
class Trip(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    start_lat = db.Column(db.Float, nullable=True)
    start_lng = db.Column(db.Float, nullable=True)
    end_lat = db.Column(db.Float, nullable=True)
    end_lng = db.Column(db.Float, nullable=True)
    distance_km = db.Column(db.Float, default=0)
    max_speed = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default="active")  # active / completed

    device = db.relationship("Device", backref="trips")

class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(minutes=5))
    used = db.Column(db.Boolean, default=False)

    @staticmethod
    def generate_otp(user_id):
        code = str(secrets.randbelow(999999)).zfill(6)
        otp = OTP(user_id=user_id, code=code)
        return otp

    @staticmethod
    def create_for_user(user_id, expiry_minutes=10):
        code = str(random.randint(100000, 999999))
        otp = OTP(
            user_id=user_id,
            code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=expiry_minutes),
            used=False
        )
        return otp

    def __repr__(self):
        return f"OTP(User {self.user_id}, Code: {self.code}, Used: {self.used})"


class DeviceGeofence(db.Model):
    __tablename__ = "device_geofence"

    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False)
    geofence_id = db.Column(db.Integer, db.ForeignKey("geofence.id"), nullable=False)

    # relationships
    device = db.relationship("Device", backref=db.backref("device_geofences", lazy=True))
    geofence = db.relationship("Geofence", backref=db.backref("device_geofences", lazy=True))

    def __repr__(self):
        return f"<DeviceGeofence device={self.device_id} geofence={self.geofence_id}>"

class Geofence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=True)  # None = all devices

    name = db.Column(db.String(100), nullable=False)

    # For CIRCLE geofence
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    radius_meters = db.Column(db.Integer, nullable=True)

    # For POLYGON geofence (store as JSON list of points)
    polygon_points = db.Column(JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class GeofenceEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(
        db.Integer,
        db.ForeignKey("device.id"),
        nullable=False
    )

    geofence_id = db.Column(
        db.Integer,
        db.ForeignKey("geofence.id"),
        nullable=False
    )

    event_type = db.Column(db.String(10))  # ENTER / EXIT
    seen = db.Column(db.Boolean, default=False)

    timestamp = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

class DeviceGeofenceState(db.Model):
    __tablename__ = "device_geofence_state"

    id = db.Column(db.Integer, primary_key=True)

    device_id = db.Column(
        db.Integer,
        db.ForeignKey("device.id"),
        nullable=False
    )

    geofence_id = db.Column(
        db.Integer,
        db.ForeignKey("geofence.id"),
        nullable=False
    )

    is_inside = db.Column(db.Boolean, default=False)
    last_changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    device = db.relationship("Device", backref="geofence_states")
    geofence = db.relationship("Geofence", backref="device_states")

    __table_args__ = (
        db.UniqueConstraint("device_id", "geofence_id", name="unique_device_geofence"),
    )

class DeviceShare(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("device.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    device = db.relationship("Device", backref="shares")

    @staticmethod
    def generate_token():
        return secrets.token_hex(32)

