import os
import sqlite3

from flask import Flask, g

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "kubera.db")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            trust_score INTEGER,
            route TEXT,
            integrity_score REAL,
            stability_score REAL,
            policy_alignment REAL,
            evidence_consistency REAL,
            payload_json TEXT
        )
    """)
    conn.commit()
    conn.close()


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload cap
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_db()

    from .routes import bp
    app.register_blueprint(bp)

    @app.teardown_appcontext
    def close_db(exception=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    return app
