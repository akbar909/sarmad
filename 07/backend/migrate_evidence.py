import os
from sqlalchemy import text
from database import engine

def migrate():
    with engine.connect() as conn:
        columns_to_add = [
            ("risk_level", "TEXT DEFAULT 'UNKNOWN'"),
            ("evidence", "TEXT DEFAULT '{}'"),
            ("recommendation", "TEXT DEFAULT ''"),
            ("red_flags", "TEXT DEFAULT '[]'"),
            ("positive_signs", "TEXT DEFAULT '[]'"),
        ]
        
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE detections ADD COLUMN {col_name} {col_type};"))
                conn.commit()
                print(f"Added column {col_name} to detections table.")
            except Exception as e:
                print(f"Column {col_name} already exists or error: {e}")

if __name__ == "__main__":
    migrate()
