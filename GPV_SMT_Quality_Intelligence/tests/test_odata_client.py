"""Cliente OData contra un servidor HTTP falso (sin red real)."""
import io
import logging
import unittest

from tests.helpers import FakeODataServer, live_config, load_fixture, metadata_bytes
from backend.credentials import Credential
from backend.logging_setup import SanitizingFilter
from models.query import Filter, QuerySpec
from models.results import ODataStatus
from services.odata_client import FactoryLogixODataClient

SPEC = QuerySpec("SMT", [Filter("Identifier", "eq", "W07632100028")], orderby=[("EventDate", "asc")], top=50)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.srv = FakeODataServer()
        self.srv.behaviors["$metadata"] = [{"status": 200, "body": metadata_bytes()}]
        self.results = []

    def tearDown(self):
        self.srv.close()

    def client(self, cred=None, **odata):
        return FactoryLogixODataClient(live_config(self.srv.base_url, **odata),
                                       credential_provider=lambda c: cred, on_result=self.results.append)

    def entity_requests(self, name="SMT"):
        return [r for r in self.srv.requests if f"/{name}?" in r["path"]]

    def test_ok_with_rows(self):
        self.srv.behaviors["SMT"] = [{"status": 200, "body": {"value": load_fixture("mirion_W07632100028_smt.json")}}]
        r = self.client().execute(SPEC)
        self.assertEqual(r.status, ODataStatus.OK)
        self.assertEqual(len(r.rows), 4)
        self.assertEqual(r.http_status, 200)
        self.assertGreater(r.elapsed_ms, 0)
        self.assertIn("wait_headers_ms", r.timings)
        self.assertIn("parse_ms", r.timings)

    def test_empty_is_distinct_from_error(self):
        self.srv.behaviors["SMT"] = [{"status": 200, "body": {"value": []}}]
        r = self.client().execute(SPEC)
        self.assertEqual(r.status, ODataStatus.EMPTY)
        self.assertTrue(r.ok)

    def test_401_not_retried(self):
        self.srv.behaviors["SMT"] = [{"status": 401, "body": b""}]
        r = self.client(max_retries=2).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.AUTH_ERROR)
        self.assertEqual(len(self.entity_requests()), 1)
        self.assertFalse(r.ok)

    def test_403_not_retried(self):
        self.srv.behaviors["SMT"] = [{"status": 403, "body": b""}]
        r = self.client(max_retries=2).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.FORBIDDEN)
        self.assertEqual(len(self.entity_requests()), 1)

    def test_404(self):
        self.srv.behaviors["SMT"] = [{"status": 404, "body": b""}]
        self.assertEqual(self.client().execute(SPEC).status, ODataStatus.NOT_FOUND)

    def test_500_retried_with_backoff_then_fails(self):
        self.srv.behaviors["SMT"] = [{"status": 500, "body": b"boom"}]
        r = self.client(max_retries=1).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.SERVER_ERROR)
        self.assertEqual(len(self.entity_requests()), 2)
        self.assertEqual(r.attempts, 2)
        self.assertEqual(r.rows, [])

    def test_503_then_success(self):
        self.srv.behaviors["SMT"] = [{"status": 503, "body": b""}, {"status": 200, "body": {"value": [{"Identifier": "X"}]}}]
        r = self.client(max_retries=1).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.OK)
        self.assertEqual(r.attempts, 2)

    def test_429(self):
        self.srv.behaviors["SMT"] = [{"status": 429, "body": b"", "headers": {"Retry-After": "0"}}]
        self.assertEqual(self.client(max_retries=0).execute(SPEC).status, ODataStatus.RATE_LIMITED)

    def test_timeout_not_retried(self):
        self.srv.behaviors["SMT"] = [{"status": 200, "body": {"value": []}, "delay": 1.5}]
        r = self.client(timeout_seconds=0.4, max_retries=2).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.TIMEOUT)
        self.assertEqual(r.attempts, 1)
        self.assertFalse(r.ok)

    def test_connection_refused(self):
        port = self.srv.port
        self.srv.close()
        c = FactoryLogixODataClient(live_config(f"http://127.0.0.1:{port}/odata/"), credential_provider=lambda c: None)
        r = c.execute(SPEC)
        self.assertEqual(r.status, ODataStatus.CONNECTION_ERROR)
        self.srv = FakeODataServer()  # para tearDown

    def test_dns_failure(self):
        c = FactoryLogixODataClient(live_config("http://nonexistent-host.invalid:6065/odata/"),
                                    credential_provider=lambda c: None)
        self.assertEqual(c.execute(SPEC).status, ODataStatus.CONNECTION_ERROR)

    def test_invalid_json_and_structure(self):
        for body in (b"<html>500</html>", b'{"items": []}', b'{"value": "x"}'):
            with self.subTest(body=body):
                self.srv.behaviors["SMT"] = [{"status": 200, "body": body}]
                r = self.client().execute(SPEC)
                self.assertEqual(r.status, ODataStatus.INVALID_RESPONSE)
                self.assertEqual(r.rows, [])

    def test_redirect_not_followed(self):
        self.srv.behaviors["SMT"] = [{"status": 302, "body": b"", "headers": {"Location": "http://evil.invalid/"}}]
        r = self.client().execute(SPEC)
        self.assertEqual(r.status, ODataStatus.HTTP_ERROR)

    def test_policy_blocks(self):
        cfg = live_config(self.srv.base_url)
        cfg["security"]["live_mode_approved"] = False
        r = FactoryLogixODataClient(cfg).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.BLOCKED_BY_POLICY)
        cfg = live_config(self.srv.base_url, auth_method="basic")
        r = FactoryLogixODataClient(cfg, credential_provider=lambda c: Credential("u", "p")).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.BLOCKED_BY_POLICY)
        cfg["mode"] = "demo"
        self.assertEqual(FactoryLogixODataClient(cfg).execute(SPEC).status, ODataStatus.BLOCKED_BY_POLICY)
        self.assertEqual(self.entity_requests(), [])

    def test_missing_credentials(self):
        cfg = live_config(self.srv.base_url, auth_method="basic")
        cfg["security"]["allow_basic_auth_over_http"] = True
        r = FactoryLogixODataClient(cfg, credential_provider=lambda c: None).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.NOT_CONFIGURED)

    def test_basic_auth_header_sent_and_not_logged(self):
        self.srv.behaviors["SMT"] = [{"status": 200, "body": {"value": []}}]
        cfg = live_config(self.srv.base_url, auth_method="basic")
        cfg["security"]["allow_basic_auth_over_http"] = True
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(SanitizingFilter())
        logger = logging.getLogger("gpv")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            cred = Credential("42178", "S3cr3t!")
            r = FactoryLogixODataClient(cfg, credential_provider=lambda c: cred).execute(SPEC)
        finally:
            logger.removeHandler(handler)
        self.assertEqual(r.status, ODataStatus.EMPTY)
        self.assertTrue(self.entity_requests()[0]["headers"]["Authorization"].startswith("Basic "))
        self.assertNotIn("S3cr3t!", stream.getvalue())
        self.assertNotIn("Authorization", stream.getvalue())
        self.assertNotIn("S3cr3t", repr(cred))

    def test_no_auth_header_when_none(self):
        self.srv.behaviors["SMT"] = [{"status": 200, "body": {"value": []}}]
        self.client().execute(SPEC)
        self.assertNotIn("Authorization", self.entity_requests()[0]["headers"])

    def test_entity_missing_in_metadata(self):
        xml = metadata_bytes().replace(b'<EntitySet Name="SMT"', b'<EntitySet Name="SMTX"')
        self.srv.behaviors["$metadata"] = [{"status": 200, "body": xml}]
        self.assertEqual(self.client().execute(SPEC).status, ODataStatus.NOT_FOUND)

    def test_metadata_failure_falls_back_and_marks_unverified(self):
        self.srv.behaviors["$metadata"] = [{"status": 500, "body": b""}]
        self.srv.behaviors["SMT"] = [{"status": 200, "body": {"value": []}}]
        r = self.client(max_retries=0).execute(SPEC)
        self.assertEqual(r.status, ODataStatus.EMPTY)
        self.assertIn("tipos no verificados", r.query_description)

    def test_pagination_same_origin(self):
        nxt = self.srv.base_url + "SMT?$skiptoken=2"
        self.srv.behaviors["SMT"] = [{"status": 200, "body": {"value": [{"Identifier": "A"}], "@odata.nextLink": nxt}},
                                     {"status": 200, "body": {"value": [{"Identifier": "B"}]}}]
        r = self.client().execute(SPEC)
        self.assertEqual([x["Identifier"] for x in r.rows], ["A", "B"])

    def test_pagination_foreign_origin_ignored(self):
        self.srv.behaviors["SMT"] = [{"status": 200, "body": {"value": [{"Identifier": "A"}],
                                                              "@odata.nextLink": "http://evil.invalid/SMT"}}]
        r = self.client().execute(SPEC)
        self.assertEqual(len(r.rows), 1)
        self.assertTrue(r.truncated)

    def test_results_emitted_for_audit(self):
        self.srv.behaviors["SMT"] = [{"status": 500, "body": b""}]
        self.client(max_retries=0).execute(SPEC)
        self.assertTrue(any(x.entity == "SMT" and x.status == ODataStatus.SERVER_ERROR for x in self.results))


if __name__ == "__main__":
    unittest.main()
