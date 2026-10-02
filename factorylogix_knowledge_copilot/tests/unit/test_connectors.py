import pytest
import requests

from connectors.base import (CircuitBreaker, ConnectorAuthError, ConnectorDisabled, ConnectorForbidden,
                             ConnectorNotFound, ConnectorRateLimited, ConnectorServerError, ConnectorTimeout,
                             ConnectorUnavailable, TTLCache)
from connectors.odata import ODataConnector, XTendConnector
from connectors.simulator import SimulatedResponse, SimulatedSession
from core.errors import ValidationError

ENTITIES = {"WIP": {"key_fields": ["WorkOrderNumber"], "select": ["WorkOrderNumber", "Status"]}}


def make(session, **kw):
    params = dict(enabled=True, base_url="https://fl.intra.local/odata", entities=ENTITIES,
                  allowed_hosts=["fl.intra.local"], max_retries=2, backoff=0, session=session, sleep=lambda s: None)
    params.update(kw)
    return ODataConnector(**params)


class Sequence:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.trust_env = False

    def get(self, url, **kw):
        self.calls.append((url, kw))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_disabled_by_default():
    with pytest.raises(ConnectorDisabled):
        make(SimulatedSession(), enabled=False).query("WIP", "WorkOrderNumber", "WO1")


def test_success_sanitizes_and_caches():
    session = Sequence(SimulatedResponse(200, {"value": [{"WorkOrderNumber": "WO1", "Status": "Open",
                                                          "Secret": "x", "@odata.etag": "y"}]}))
    conn = make(session)
    first = conn.query("WIP", "WorkOrderNumber", "WO1")
    assert first.rows == [{"WorkOrderNumber": "WO1", "Status": "Open"}] and not first.from_cache
    assert conn.query("WIP", "WorkOrderNumber", "WO1").from_cache
    url, kw = session.calls[0]
    assert kw["params"]["$filter"] == "WorkOrderNumber eq 'WO1'" and kw["timeout"] == 10


@pytest.mark.parametrize("status,exc,calls", [(401, ConnectorAuthError, 1), (403, ConnectorForbidden, 1),
                                              (404, ConnectorNotFound, 1), (429, ConnectorRateLimited, 3),
                                              (500, ConnectorServerError, 3)])
def test_http_errors(status, exc, calls):
    session = SimulatedSession(status)
    with pytest.raises(exc):
        make(session, failure_threshold=10).query("WIP", "WorkOrderNumber", "WO1")
    assert session.calls == calls


def test_timeout_and_offline_with_retries():
    for mode, exc in (("timeout", ConnectorTimeout), ("offline", ConnectorUnavailable)):
        session = SimulatedSession(mode)
        with pytest.raises(exc):
            make(session, failure_threshold=10).query("WIP", "WorkOrderNumber", "WO1")
        assert session.calls == 3


def test_retry_then_success():
    session = Sequence(requests.Timeout(), SimulatedResponse(200, {"value": []}))
    assert make(session).query("WIP", "WorkOrderNumber", "WO1").rows == []


def test_circuit_breaker_opens():
    session = SimulatedSession(500)
    conn = make(session, max_retries=0, failure_threshold=2)
    for _ in range(2):
        with pytest.raises(ConnectorServerError):
            conn.query("WIP", "WorkOrderNumber", f"WO{_}")
    with pytest.raises(ConnectorUnavailable):
        conn.query("WIP", "WorkOrderNumber", "WO9")
    assert conn.status()["circuit"] == "open"


def test_input_validation_and_allowlists():
    conn = make(SimulatedSession())
    with pytest.raises(ValidationError):
        conn.query("Users", "WorkOrderNumber", "WO1")
    with pytest.raises(ValidationError):
        conn.query("WIP", "Password", "WO1")
    with pytest.raises(ValidationError):
        conn.query("WIP", "WorkOrderNumber", "WO1' or 1 eq 1")
    with pytest.raises(ValidationError):
        make(SimulatedSession(), base_url="https://evil.example.com/odata").query("WIP", "WorkOrderNumber", "WO1")


def test_read_only_surface():
    session = SimulatedSession()
    make(session).query("WIP", "WorkOrderNumber", "WO1")
    assert set(session.methods) == {"GET"}
    forbidden = {"post", "put", "patch", "delete", "proceed", "unproceed", "reroute"}
    assert not forbidden & {m.lower() for m in dir(ODataConnector)}
    with pytest.raises(ConnectorDisabled):
        XTendConnector().query()


def test_cache_and_breaker_primitives():
    now = [0.0]
    cache = TTLCache(10, clock=lambda: now[0])
    cache.set("k", 1)
    assert cache.get("k") == 1
    now[0] = 11
    assert cache.get("k") is None
    breaker = CircuitBreaker(1, 5, clock=lambda: now[0])
    breaker.record_failure()
    assert breaker.state == "open"
    now[0] = 17
    assert breaker.state == "half-open"
