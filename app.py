"""
Dynamic QR Code Generator with Time-Based Expiration
=====================================================
Generates QR codes that point to an internal validation route.
Valid tokens redirect to TARGET_URL; expired/invalid tokens redirect to FALLBACK_URL.
Settings are managed via /admin and persisted in SQLite.
Ready for deployment on Zeabur or any cloud platform.
"""

import io
import sqlite3
import base64
import os
import time
import uuid

import qrcode
from flask import Flask, render_template, redirect, request, flash, url_for

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "qrcode-admin-secret-key")

# Database path — use /tmp for Zeabur compatibility, or local dir
DB_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DB_DIR, "qrcode.db")

# In-memory token store: { token_str: creation_timestamp }
tokens: dict[str, float] = {}

# Default configuration values
DEFAULTS = {
    "target_url": "https://ickaohsiungculinaryjourneymap.lovable.app/qrcode",
    "fallback_url": "https://ickaohsiung.com",
    "expiration_time": "1800",
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db() -> sqlite3.Connection:
    """Get a database connection, creating tables if needed."""
    db = sqlite3.connect(DB_PATH)
    db.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    db.commit()
    return db


def load_config() -> dict:
    """Load all configuration from SQLite, falling back to defaults."""
    db = get_db()
    rows = db.execute("SELECT key, value FROM config").fetchall()
    db.close()

    cfg = dict(DEFAULTS)
    for key, value in rows:
        cfg[key] = value

    # Ensure expiration_time is an integer for comparisons
    cfg["expiration_time"] = int(cfg["expiration_time"])
    return cfg


def save_config(cfg: dict) -> None:
    """Persist configuration to SQLite."""
    db = get_db()
    for key, value in cfg.items():
        db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Routes — QR Code Generator
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Generate a new token + QR code and render the generator page."""
    cfg = load_config()

    token = str(uuid.uuid4())
    tokens[token] = time.time()

    # Build the scan URL using the request host so it works on any machine
    scan_url = f"{request.scheme}://{request.host}/scan/{token}"

    # Generate QR code image in memory
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=4,
    )
    qr.add_data(scan_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Convert to base64 so we can embed directly in the HTML
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return render_template(
        "index.html",
        qr_image=qr_b64,
        token=token,
        expiration=cfg["expiration_time"],
    )


@app.route("/scan/<token>")
def scan(token: str):
    """Validate the scanned token and redirect accordingly."""
    cfg = load_config()
    creation_time = tokens.get(token)

    if creation_time is not None and (time.time() - creation_time) < cfg["expiration_time"]:
        return redirect(cfg["target_url"])

    # Invalid or expired — silently redirect to fallback
    return redirect(cfg["fallback_url"])


# ---------------------------------------------------------------------------
# Routes — Admin Backend
# ---------------------------------------------------------------------------
@app.route("/admin", methods=["GET"])
def admin_page():
    """Render the admin settings page."""
    cfg = load_config()
    return render_template("admin.html", config=cfg)


@app.route("/admin", methods=["POST"])
def admin_save():
    """Save updated settings from the admin form."""
    cfg = load_config()

    cfg["target_url"] = request.form.get("target_url", cfg["target_url"]).strip()
    cfg["fallback_url"] = request.form.get("fallback_url", cfg["fallback_url"]).strip()

    try:
        cfg["expiration_time"] = int(request.form.get("expiration_time", cfg["expiration_time"]))
    except (ValueError, TypeError):
        pass  # keep previous value

    save_config(cfg)
    flash("設定已儲存成功！", "success")
    return redirect(url_for("admin_page"))


# ---------------------------------------------------------------------------
# Entry point (local development)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
