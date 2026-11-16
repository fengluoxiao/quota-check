import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io
import json
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
import quota
import settings

class ClientTests(unittest.TestCase):
    def test_request_uses_exact_endpoint_and_raw_key(self):
        class Client:
            def open(self, request, timeout):
                self.request, self.timeout = request, timeout
                return io.BytesIO(b'{"code":200,"data":{"limits":[]}}')
        client=Client()
        quota.fetch_quota(" Bearer test-key ", "global", opener=client)
        self.assertEqual(client.request.full_url, quota.ENDPOINTS["global"])
        self.assertEqual(client.request.get_header("Authorization"), "test-key")
        self.assertEqual(client.request.get_method(), "GET")
        self.assertEqual(client.timeout, 20)

    def test_rejects_invalid_keys_without_network(self):
        for key in ("", "  ", "x\ny", "x y", "中文"):
            with self.subTest(key=key), self.assertRaises(quota.QueryError): quota.validate_key(key)

    def test_http_errors_do_not_leak_response_or_key(self):
        for code in (401,403,429,500):
            class Client:
                def open(self, *a, **k): raise urllib.error.HTTPError("https://example.invalid", code, "secret-key", {}, None)
            with self.assertRaises(quota.QueryError) as exc: quota.fetch_quota("secret-key",opener=Client())
            self.assertNotIn("secret-key",str(exc.exception))

    def test_timeout_and_bad_json(self):
        class TimeoutClient:
            def open(self,*a,**k): raise TimeoutError()
        class BadClient:
            def open(self,*a,**k): return io.BytesIO(b'not json')
        for client in (TimeoutClient(),BadClient()):
            with self.assertRaises(quota.QueryError): quota.fetch_quota("test-key",opener=client)

    def test_schema_and_business_failures(self):
        for data in ([],{}, {"code":401,"data":{"limits":[]}}, {"success":False,"data":{"limits":[]}}, {"data":{"limits":[None]}}):
            with self.subTest(data=data), self.assertRaises(quota.QueryError): quota.parse_response(data)

    def test_remaining_counts_and_period(self):
        payload={"data":{"limits":[{"type":"TOKENS_LIMIT","unit":3,"number":5,"percentage":34},
          {"type":"TIME_LIMIT","unit":5,"number":1,"percentage":12,"currentValue":120,"usage":1000},
          {"type":"TOKENS_LIMIT","unit":6,"percentage":72}]}}
        a,b,c=quota.quota_cards(payload)
        self.assertEqual(a["remaining"],66)
        self.assertIn("5 小时",a["title"])
        self.assertIn("880",b["details"])
        self.assertIn("每周",c["title"])

    def test_missing_and_invalid_percent_is_not_fabricated(self):
        for p in (None,"NaN",float("inf"),-1,101,True):
            card=quota.quota_cards({"limits":[{"type":"NEW","percentage":p}]})[0]
            self.assertIsNone(card["remaining"])
            self.assertIsNone(card["used"])
            self.assertEqual(card["title"],"NEW")

    def test_unknown_fields_and_reset_preserved(self):
        payload={"limits":[{"type":"NEW","percentage":0,"resetTime":1700000000000,"usageDetails":42}]}
        card=quota.quota_cards(payload)[0]
        self.assertEqual(card["remaining"],100)
        self.assertIn("2023-11",card["details"])

    def test_redacts_keys_without_hiding_token_usage(self):
        data=quota.redact_payload({"api_key":"secret", "note":"key secret", "totalTokens":123},"secret")
        self.assertEqual(data["api_key"],"[已隐藏]")
        self.assertNotIn("secret",data["note"])
        self.assertEqual(data["totalTokens"],123)

    def test_no_redirect(self):
        with self.assertRaises(quota.QueryError): quota.NoRedirect().redirect_request(None,None,302,"",{},"https://example.invalid")

class SettingsTests(unittest.TestCase):
    def test_dpapi_round_trip(self):
        encoded=settings.crypt(b"test-only-key")
        self.assertNotIn(b"test-only-key",encoded)
        self.assertEqual(settings.crypt(encoded,decrypt=True),b"test-only-key")

    def test_opt_in_store_and_forget(self):
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/"settings.json"
            with patch.object(settings,"config_path",return_value=config):
                settings.save("cn","test-only-key")
                self.assertNotIn("test-only-key",config.read_text())
                self.assertEqual(settings.load()["key"],"test-only-key")
                settings.save("global")
                self.assertEqual(settings.load(),{"site":"global","key":""})
                self.assertNotIn('"key"',config.read_text())
                config.write_text("broken")
                self.assertEqual(settings.load()["key"],"")

if __name__ == "__main__": unittest.main(verbosity=2)
