import os
import re
import sqlite3
from datetime import timedelta

from flask import Blueprint, request, jsonify, current_app
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

auth = Blueprint("auth", __name__, url_prefix="/api/auth")
bcrypt = Bcrypt()


def get_auth_connection():
    db_path = os.path.join(current_app.root_path, "users.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    """Create the users table and migrate older databases to include email."""
    with get_auth_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT
            )
        """)

        # Safe migration for users.db created by the earlier username-only version.
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "email" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
            ON users(email)
            WHERE email IS NOT NULL AND email != ''
        """)

def get_user_email(user_id):
    """Return the registered email address for a user."""
    if user_id is None:
        return None

    with get_auth_connection() as conn:
        row = conn.execute(
            "SELECT email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if row is None:
        return None

    email = (row[0] or "").strip()
    return email or None
def get_user_username(user_id):
    """Return the registered username for a user ID."""
    if user_id is None:
        return None

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    with get_auth_connection() as conn:
        row = conn.execute(
            "SELECT username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    return row["username"] if row else None

@auth.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not username or not email or not password:
        return jsonify({
            "error": "Username, email, and password are required"
        }), 400

    if len(username) > 80:
        return jsonify({"error": "Username must be 80 characters or fewer"}), 400

    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "Enter a valid email address"}), 400

    if len(password) < 12:
        return jsonify({"error": "Password must be at least 12 characters"}), 400

    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    try:
        with get_auth_connection() as conn:
            conn.execute(
                """
                INSERT INTO users (username, email, password_hash)
                VALUES (?, ?, ?)
                """,
                (username, email, password_hash),
            )
    except sqlite3.IntegrityError:
        return jsonify({
            "error": "That username or email is already registered"
        }), 409

    return jsonify({"message": "Registration successful"}), 201


@auth.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    with get_auth_connection() as conn:
        user = conn.execute(
            """
            SELECT id, username, email, password_hash
            FROM users
            WHERE username = ?
            """,
            (username,),
        ).fetchone()

    if user is None or not bcrypt.check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    token = create_access_token(
        identity=str(user["id"]),
        expires_delta=timedelta(minutes=30),
    )

    return jsonify({
        "message": "Login successful",
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 1800,
    }), 200


@auth.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()

    with get_auth_connection() as conn:
        user = conn.execute(
            "SELECT id, username, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if user is None:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
    }), 200
