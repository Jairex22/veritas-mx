"""SQLite cache, expiration, retention and reuse (requirements 4, 5)."""
import unittest
from datetime import timedelta

from _support import TempDirMixin
from database import Database, signature_for
from timeutil import utc_now

SID_A = "a" * 24
SID_B = "b" * 24


class DatabaseCacheTests(TempDirMixin, unittest.TestCase):
    def put(self, db, sig="s1", ttl=300, now=None, records=None):
        return db.put_cache(signature=sig, query_params={"start": "2026-01-01", "end": "2026-01-01"},
                            relative_url="ProductivityOverTime?$top=1", records=records or [{"A": 1}],
                            ttl_seconds=ttl, more_available=False, validation_state="tested_filters",
                            schema_hash="h", now=now)

    def test_store_and_read(self):
        db = self.database()
        self.put(db)
        entry = db.get_cache("s1")
        self.assertTrue(entry["is_fresh"])
        self.assertEqual(entry["records"], [{"A": 1}])
        self.assertEqual(entry["data_mode"], "demo")
        self.assertEqual(len(entry["response_hash"]), 32)

    def test_expiration(self):
        db = self.database()
        self.put(db, ttl=300, now=utc_now() - timedelta(seconds=301))
        entry = db.get_cache("s1")
        self.assertIsNotNone(entry)          # kept as stored data
        self.assertFalse(entry["is_fresh"])  # but no longer fresh

    def test_only_three_snapshots_per_signature(self):
        db = self.database()
        for i in range(6):
            self.put(db, now=utc_now() - timedelta(minutes=10 - i))
        self.assertEqual(db.stats()["cache_entries"], 3)

    def test_retention_cleanup(self):
        db = self.database()
        self.put(db, sig="old", now=utc_now() - timedelta(days=10))
        self.put(db, sig="new")
        db.add_history(kind="query", query_text="x", result_status="ok", cache_status="miss",
                       now=utc_now() - timedelta(days=40))
        removed = db.cleanup(cache_retention_days=7, history_retention_days=30, report_retention_days=90, max_db_size_mb=200)
        self.assertEqual(removed["cache"], 1)
        self.assertEqual(removed["history"], 1)
        self.assertIsNone(db.get_cache("old"))
        self.assertIsNotNone(db.get_cache("new"))

    def test_size_limit_trims_oldest(self):
        db = self.database()
        big = [{"payload": "x" * 5000} for _ in range(50)]
        for i in range(12):
            self.put(db, sig=f"s{i}", records=big, now=utc_now() - timedelta(minutes=60 - i))
        removed = db.cleanup(cache_retention_days=7, history_retention_days=30, report_retention_days=90, max_db_size_mb=1)
        self.assertGreater(removed["size_trim"], 0)
        self.assertLessEqual(db.size_bytes(), 1024 * 1024)
        self.assertIsNotNone(db.get_cache("s11"))  # newest kept

    def test_demo_and_live_never_mix(self):
        path = self.tmp / "data" / "shared.db"
        db = Database(path, "demo")
        db.close()
        with self.assertRaises(RuntimeError):
            Database(path, "live")

    def test_signature_stable(self):
        self.assertEqual(signature_for({"a": 1, "b": 2}), signature_for({"b": 2, "a": 1}))
        self.assertNotEqual(signature_for({"a": 1}), signature_for({"a": 2}))

    def test_no_credentials_columns(self):
        db = self.database()
        cols = [r[1].lower() for t in ("odata_cache", "query_history", "saved_reports", "application_settings")
                for r in db._conn.execute(f"PRAGMA table_info({t})")]
        for forbidden in ("password", "token", "authorization", "credential", "secret"):
            self.assertFalse(any(forbidden in c for c in cols))


class ServiceCacheTests(TempDirMixin, unittest.TestCase):
    def body(self, **kw):
        today = utc_now().date().isoformat()
        return dict({"start": today, "end": today, "line": "SMT-L01", "interval": "hour"}, **kw)

    def test_second_query_served_from_cache_for_any_session(self):
        svc = self.service()
        first = svc.run_query(self.body(), SID_A)
        sent = len(svc.client.request_log)
        second = svc.run_query(self.body(), SID_B)   # another local user
        self.assertEqual(first["source"], "odata")
        self.assertEqual(second["source"], "cache")
        self.assertEqual(len(svc.client.request_log), sent)

    def test_interval_change_does_not_requery(self):
        svc = self.service()
        svc.run_query(self.body(), SID_A)
        sent = len(svc.client.request_log)
        result = svc.run_query(self.body(interval="day"), SID_A)
        self.assertEqual(result["source"], "cache")
        self.assertEqual(len(svc.client.request_log), sent)

    def test_force_refresh_respects_min_interval(self):
        svc = self.service()
        svc.run_query(self.body(), SID_A)
        sent = len(svc.client.request_log)
        result = svc.run_query(self.body(force_refresh=True), SID_A)
        self.assertEqual(result["source"], "cache")
        self.assertIn("Podrás forzar", result["notice"])
        self.assertEqual(len(svc.client.request_log), sent)

    def test_expired_cache_triggers_one_request(self):
        svc = self.service(limits={"CACHE_TTL_SECONDS": 0})
        svc.run_query(self.body(), SID_A)
        sent = len(svc.client.request_log)
        result = svc.run_query(self.body(), SID_A)
        self.assertEqual(result["source"], "odata")
        self.assertEqual(len(svc.client.request_log), sent + 1)

    def test_last_query_never_contacts_server(self):
        svc = self.service()
        svc.run_query(self.body(), SID_A)
        sent = len(svc.client.request_log)
        last = svc.last_query()
        self.assertTrue(last["ok"])
        self.assertEqual(len(svc.client.request_log), sent)


if __name__ == "__main__":
    unittest.main()
