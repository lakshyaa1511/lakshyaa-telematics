from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS trip (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL REFERENCES device(id),
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                start_lat FLOAT,
                start_lng FLOAT,
                end_lat FLOAT,
                end_lng FLOAT,
                distance_km FLOAT DEFAULT 0,
                max_speed FLOAT DEFAULT 0,
                status VARCHAR(20) DEFAULT "active"
            )
        '''))
        conn.commit()
    print('Done')
