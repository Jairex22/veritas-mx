"""Repositorio de usuarios y sesiones."""
from __future__ import annotations

from typing import Any

from core.utils import new_id, now_iso
from repositories.base import BaseRepository


class UserRepository(BaseRepository):
    table = "users"
    updatable = frozenset({
        "display_name", "role", "password_hash", "must_change_password", "is_active", "failed_attempts",
        "locked_until", "preferred_language", "updated_at", "last_login_at", "password_changed_at",
    })

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM users WHERE username = ?", (username.strip(),))

    def get(self, user_id: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))

    def list_all(self) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT id, username, display_name, role, is_active, must_change_password, failed_attempts, "
            "locked_until, auth_source, is_demo, created_at, last_login_at FROM users ORDER BY username")

    def create(self, *, username: str, display_name: str, role: str, password_hash: str,
               must_change_password: bool = True, is_demo: bool = False, language: str = "es") -> str:
        user_id = new_id("usr-")
        ts = now_iso()
        self.db.execute(
            "INSERT INTO users (id, username, display_name, role, password_hash, must_change_password, "
            "is_active, failed_attempts, auth_source, preferred_language, is_demo, created_at, updated_at, "
            "password_changed_at) VALUES (?, ?, ?, ?, ?, ?, 1, 0, 'local', ?, ?, ?, ?, ?)",
            (user_id, username.strip(), display_name.strip(), role, password_hash, int(must_change_password),
             language, int(is_demo), ts, ts, ts),
        )
        return user_id

    def update(self, user_id: str, **fields: Any) -> None:
        fields["updated_at"] = now_iso()
        self._update(user_id, fields)

    def count_active_admins(self) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM users WHERE role = 'Administrator' AND is_active = 1", default=0))

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM users", default=0))

    # --- sesiones ---
    def start_session(self, user_id: str) -> str:
        session_id = new_id("ses-")
        ts = now_iso()
        self.db.execute("INSERT INTO sessions (id, user_id, started_at, last_seen_at) VALUES (?, ?, ?, ?)",
                        (session_id, user_id, ts, ts))
        return session_id

    def touch_session(self, session_id: str) -> None:
        self.db.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ? AND ended_at IS NULL",
                        (now_iso(), session_id))

    def end_session(self, session_id: str, reason: str) -> None:
        self.db.execute("UPDATE sessions SET ended_at = ?, end_reason = ? WHERE id = ? AND ended_at IS NULL",
                        (now_iso(), reason, session_id))

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
