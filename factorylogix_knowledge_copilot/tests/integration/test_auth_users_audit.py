"""Autenticación, usuarios, RBAC y auditoría."""
import sqlite3
from datetime import timedelta

import pytest

from core.errors import AccountLocked, AuthenticationError, PermissionDenied, ValidationError
from core.utils import utcnow
from security.rbac import ROLE_PERMISSIONS
from tests.conftest import user_for


def _create(c, username, role="Operator"):
    admin = user_for(c, "Administrator", "root")
    temp = c.users.create(admin, username, username, role)
    return admin, temp


def test_initial_admin_is_secure(container):
    c = container
    row = c.auth.users.get_by_username("admin")
    assert row["must_change_password"] == 1 and row["password_hash"].startswith("scrypt$")
    assert c.users.first_run_file().is_file()
    assert c.bootstrap_password and c.bootstrap_password not in row["password_hash"]


def test_login_change_password_and_generic_errors(container):
    c = container
    admin, temp = _create(c, "jperez")
    user = c.auth.authenticate("jperez", temp)
    assert user.must_change_password
    with pytest.raises(ValidationError):
        c.auth.change_password(user, temp, "debil", "debil")
    c.auth.change_password(user, temp, "Planta-Segura-2026", "Planta-Segura-2026")
    assert not c.auth.authenticate("jperez", "Planta-Segura-2026").must_change_password
    with pytest.raises(AuthenticationError) as wrong:
        c.auth.authenticate("jperez", "incorrecta")
    with pytest.raises(AuthenticationError) as unknown:
        c.auth.authenticate("no_existe", "incorrecta")
    assert wrong.value.user_message == unknown.value.user_message  # sin enumeración de usuarios


def test_lockout_after_failed_attempts(container):
    c = container
    _, temp = _create(c, "lock_me")
    for _ in range(int(c.settings.get("security.max_failed_logins"))):
        with pytest.raises(AuthenticationError):
            c.auth.authenticate("lock_me", "mala-clave")
    with pytest.raises(AccountLocked):
        c.auth.authenticate("lock_me", temp)
    assert c.audit_repo.list(action="auth.login", result="denied")


def test_sql_injection_login_fails(container):
    with pytest.raises(AuthenticationError):
        container.auth.authenticate("admin' OR '1'='1", "x' OR '1'='1")


def test_idle_expiration_and_disabled_user(container):
    c = container
    assert c.auth.is_idle_expired(utcnow() - timedelta(minutes=31))
    assert not c.auth.is_idle_expired(utcnow() - timedelta(minutes=5))
    admin, temp = _create(c, "baja1")
    uid = c.auth.users.get_by_username("baja1")["id"]
    c.users.set_active(admin, uid, False)
    assert c.auth.refresh(uid) is None
    with pytest.raises(AuthenticationError):
        c.auth.authenticate("baja1", temp)


def test_role_change_audited_and_last_admin_protected(container):
    c = container
    admin, _ = _create(c, "sup1")
    uid = c.auth.users.get_by_username("sup1")["id"]
    c.users.change_role(admin, uid, "Supervisor", "promoción")
    assert c.auth.users.get(uid)["role"] == "Supervisor"
    assert c.audit_repo.list(action="user.role_change")
    for row in c.auth.users.list_all():
        if row["role"] == "Administrator" and row["username"] != "admin":
            c.users.set_active(admin, row["id"], False)
    admin_id = c.auth.users.get_by_username("admin")["id"]
    with pytest.raises(ValidationError):
        c.users.change_role(admin, admin_id, "Operator", "quitar")
    with pytest.raises(PermissionDenied):
        c.users.create(user_for(c, "Supervisor"), "x_user", "x", "Operator")


def test_rbac_matrix_principles():
    op, auditor = ROLE_PERMISSIONS["Operator"], ROLE_PERMISSIONS["Auditor"]
    assert "chat.query" in op and not {"knowledge.upload", "users.manage", "audit.view"} & op
    assert "audit.view" in auditor
    assert not {p for p in auditor if p.startswith(("knowledge.", "users.", "settings.", "documents."))}
    assert "knowledge.publish" in ROLE_PERMISSIONS["Knowledge Manager"]
    assert "governance.manage" in ROLE_PERMISSIONS["Data Steward"]
    assert "users.manage" in ROLE_PERMISSIONS["Administrator"]
    assert "incident.create" in ROLE_PERMISSIONS["Supervisor"] and "analytics.view" in ROLE_PERMISSIONS["Supervisor"]


def test_audit_log_is_append_only_and_tamper_evident(container):
    c = container
    c.audit_repo.append(username="t", role="r", action="test.event", object_type="x", object_id="1", result="success")
    ok, count, _ = c.audit_repo.verify_chain()
    assert ok and count >= 2
    conn = sqlite3.connect(c.db.path)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE audit_log SET result = 'hacked'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM audit_log")
    conn.execute("DROP TRIGGER audit_no_update")  # simulación de manipulación directa de la BD
    conn.execute("UPDATE audit_log SET result = 'hacked' WHERE action = 'test.event'")
    conn.commit()
    conn.close()
    ok, _, broken = c.audit_repo.verify_chain()
    assert not ok and broken


def test_audit_event_fields(container):
    row = container.audit_repo.list(limit=1)[0]
    for field in ("id", "ts", "username", "action", "object_id", "result", "reason", "correlation_id"):
        assert field in row
