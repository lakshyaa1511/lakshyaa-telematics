from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE password_reset_token ADD COLUMN expires_at DATETIME'))
        conn.execute(text('ALTER TABLE password_reset_token ADD COLUMN used BOOLEAN DEFAULT 0'))
        conn.commit()
    print('Done')
