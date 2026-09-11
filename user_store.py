"""
口腔黏膜病AI诊断Agent — 用户账户与登录令牌（SQLite）

- 首次启动自动创建管理员 admin，密码 = config.ACCESS_PASSWORD（默认 20260705，密码不变）。
- 密码使用 PBKDF2-HMAC-SHA256 加盐哈希存储，不保存明文。
- 登录成功后签发不透明令牌（随机 32 字节，base64url），服务重启后仍有效。
- 普通用户仅能访问自己的会话；admin（role=admin）拥有最高权限。
"""
import os
import sqlite3
import hashlib
import secrets
import threading
import time

from config import PROJECT_ROOT, ACCESS_PASSWORD

DB_PATH = os.environ.get("OM_USERS_DB") or (PROJECT_ROOT / "data" / "users.db")
_PBKDF2_ITER = 120_000
_TOKEN_DAYS = 30  # 令牌有效期（天）
_lock = threading.Lock()


def _conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _hash_password(password: str, salt_hex: str | None = None):
    if salt_hex is None:
        salt_hex = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"),
        bytes.fromhex(salt_hex), _PBKDF2_ITER
    ).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITER}${salt_hex}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            bytes.fromhex(salt_hex), int(iters)
        ).hex()
        return secrets.compare_digest(computed, digest)
    except Exception:
        return False


def _row_to_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "display_name": row["display_name"] or "",
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"],
    }


def public_user(user: dict) -> dict:
    """对外暴露的用户信息（不含哈希）。"""
    return {k: user[k] for k in ("id", "username", "role", "display_name", "disabled", "created_at")}


def init_db():
    """初始化数据表；users 为空时创建管理员 admin（密码不变）。"""
    with _lock, _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'user',
                display_name  TEXT NOT NULL DEFAULT '',
                disabled      INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tokens (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            );
        """)
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if row["c"] == 0:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO users(username, password_hash, role, display_name, disabled, created_at)"
                " VALUES(?,?,?,?,?,?)",
                ("admin", _hash_password(ACCESS_PASSWORD), "admin", "系统管理员", 0, now),
            )
            print(f"[users] 已创建默认管理员 admin（密码 = ACCESS_PASSWORD）", flush=True)


def ensure_admin() -> dict:
    """确保 admin 存在（老库升级 / 被误删时兜底），密码始终保持 ACCESS_PASSWORD。"""
    admin = get_user("admin")
    if admin:
        return admin
    with _lock, _conn() as conn:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "INSERT OR IGNORE INTO users(username, password_hash, role, display_name, disabled, created_at)"
            " VALUES(?,?,?,?,?,?)",
            ("admin", _hash_password(ACCESS_PASSWORD), "admin", "系统管理员", 0, now),
        )
        row = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
    return _row_to_user(row)


def get_user(username: str):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_id(user_id: int):
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def create_user(username: str, password: str, role: str = "user", display_name: str = "") -> dict:
    """创建用户；用户名重复时抛出 ValueError。"""
    with _lock, _conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise ValueError("用户名已存在")
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, role, display_name, disabled, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (username, _hash_password(password), role, display_name or "", 0, now),
            )
        except sqlite3.IntegrityError:
            # 并发注册同名账号时数据库 UNIQUE 约束兜底（多进程/多实例场景）
            raise ValueError("用户名已存在")
        row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    return _row_to_user(row)


def check_login(username: str, password: str):
    """校验用户名密码；成功返回用户 dict，失败返回 None。禁用用户拒绝登录。"""
    user = get_user(username)
    if not user or user["disabled"]:
        return None
    stored = get_password_hash(user["id"])
    if stored and _verify_password(password, stored):
        return user
    return None


def get_password_hash(user_id: int):
    with _conn() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
    return row["password_hash"] if row else None


def verify_user_password(user_id: int, password: str) -> bool:
    stored = get_password_hash(user_id)
    return bool(stored) and _verify_password(password, stored)


def grant_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with _lock, _conn() as conn:
        # 清理过期令牌
        conn.execute("DELETE FROM tokens WHERE expires_at < ?", (now,))
        conn.execute(
            "INSERT INTO tokens(token, user_id, created_at, expires_at) VALUES(?,?,?,?)",
            (token, user_id, now, now + _TOKEN_DAYS * 86400),
        )
    return token


def resolve_token(token: str):
    """令牌 → 用户 dict；无效/过期/用户被禁用/已删除返回 None。"""
    if not token:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT t.user_id, t.expires_at FROM tokens t WHERE t.token=?", (token,)
        ).fetchone()
    if not row or row["expires_at"] < time.time():
        return None
    user = get_user_by_id(row["user_id"])
    if not user or user["disabled"]:
        return None
    return user


def revoke_token(token: str):
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM tokens WHERE token=?", (token,))


def revoke_user_tokens(user_id: int):
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))


def set_password(user_id: int, new_password: str):
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (_hash_password(new_password), user_id),
        )
        conn.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))


def set_disabled(user_id: int, disabled: bool):
    with _lock, _conn() as conn:
        conn.execute("UPDATE users SET disabled=? WHERE id=?", (1 if disabled else 0, user_id))
        if disabled:
            conn.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))


def list_users():
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [_row_to_user(r) for r in rows]


def delete_user(user_id: int):
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))


# 初始化（import 即建库、种子管理员）
init_db()
