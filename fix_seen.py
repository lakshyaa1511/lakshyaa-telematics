from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE geofence_event ADD COLUMN seen BOOLEAN DEFAULT 0'))
        conn.commit()
    print('Done')
