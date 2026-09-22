from app.core.database import init_db, engine
from sqlalchemy import text

init_db()

import app.core.database as db
with db.engine.connect() as conn:
    try:
        conn.execute(text('ALTER TABLE review_sessions ADD COLUMN language VARCHAR(64)'))
    except Exception as e:
        print(e)
    try:
        conn.execute(text('ALTER TABLE review_sessions ADD COLUMN framework VARCHAR(64)'))
    except Exception as e:
        print(e)
    conn.commit()
    print("Database altered successfully")
