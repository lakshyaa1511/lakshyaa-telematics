from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS device_share (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL REFERENCES device(id),
                token VARCHAR(64) UNIQUE NOT NULL,
                created_at DATETIME,
                expires_at DATETIME
            )
        '''))
        conn.commit()
    print('Done')
