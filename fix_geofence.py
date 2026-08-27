from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE geofence ADD COLUMN device_id INTEGER REFERENCES device(id)'))
        conn.commit()
    print('Done')
