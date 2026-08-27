from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text('ALTER TABLE device ADD COLUMN speed_limit FLOAT'))
        conn.commit()
    print('Done')
