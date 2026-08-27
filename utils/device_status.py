from datetime import datetime, timezone, timedelta

OFFLINE_THRESHOLD_MINUTES = 5
IDLE_SPEED_KMH = 3   # below this = idle

def get_device_status(last_update, speed_kmh=0):
    if not last_update:
        return "offline"

    now = datetime.now(timezone.utc)

    # Ensure datetime
    if isinstance(last_update, str):
        try:
            last_update = datetime.fromisoformat(
                last_update.replace("Z", "+00:00")
            )
        except Exception:
            return "offline"

    if last_update.tzinfo is None:
        last_update = last_update.replace(tzinfo=timezone.utc)

    delta = now - last_update

    if delta > timedelta(minutes=OFFLINE_THRESHOLD_MINUTES):
        return "offline"

    if speed_kmh <= IDLE_SPEED_KMH:
        return "idle"

    return "moving"
