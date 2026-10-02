import pytest

from core.errors import ValidationError, WorkflowError
from governance.lifecycle import check_transition
from security.passwords import hash_password, validate_password_policy, verify_password
from security.rate_limit import RateLimiter


def test_password_hash_roundtrip_and_salt():
    h1, h2 = hash_password("Segura12345X"), hash_password("Segura12345X")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert verify_password("Segura12345X", h1)
    assert not verify_password("segura12345x", h1)
    assert not verify_password("x", "formato-invalido")


@pytest.mark.parametrize("pwd", ["corta1A", "sinnumerosAAAAA", "SINMINUSCULAS123", "password"])
def test_password_policy_rejects_weak(pwd):
    with pytest.raises(ValidationError):
        validate_password_policy(pwd, "juan")


def test_password_policy_rejects_username():
    with pytest.raises(ValidationError):
        validate_password_policy("Juanperez2026X", "juanperez")
    validate_password_policy("Turno-Planta-2026", "juan")


def test_rate_limiter_window():
    now = [0.0]
    limiter = RateLimiter(2, 60, clock=lambda: now[0])
    assert limiter.allow("u") and limiter.allow("u")
    assert not limiter.allow("u")
    now[0] = 61
    assert limiter.allow("u")


def test_lifecycle_transitions():
    check_transition("Draft", "Under Review")
    check_transition("Under Review", "Approved")
    check_transition("Archived", "Approved", ever_approved=True)
    with pytest.raises(WorkflowError):
        check_transition("Draft", "Approved")
    with pytest.raises(WorkflowError):
        check_transition("Archived", "Approved", ever_approved=False)
    with pytest.raises(WorkflowError):
        check_transition("Rejected", "Approved")
