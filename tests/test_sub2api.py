import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import http.server
import json
import threading
import unittest
import urllib.parse
import sub2api
import quota

LIVE={"plan_type":"plus","fetched_at":1794830400,"rate_limit":{"allowed":True,"limit_reached":False,
 "primary_window":{"used_percent":35,"limit_window_seconds":18000,"reset_at":1794834000},
 "secondary_window":{"used_percent":82,"limit_window_seconds":604800,"reset_at":1795003200}},
 "additional_rate_limits":[{"limit_name":"Spark","rate_limit":{"primary_window":{"used_percent":12,"limit_window_seconds":18000,"reset_after_seconds":3600}}}],
 "rate_limit_reset_credits":{"available_count":2,"credits":[{"expires_at":"2026-11-18T00:00:00Z"}]},
 "credits":{"has_credits":True,"unlimited":False,"balance":"18.40"}}
SNAPSHOT={"codex_5h_used_percent":40,"codex_7d_used_percent":90,"codex_5h_reset_at":"2026-11-16T19:00:00Z","codex_usage_updated_at":"2026-11-16T12:00:00Z","private_key":"must-not-keep"}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,data=None,status=200,reason=""):
        payload={"code":0,"data":data} if status==200 else {"code":status,"reason":reason,"message":"DO NOT DISPLAY test-password access-secret"}
        body=json.dumps(payload).encode()
        self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):self.handle_request()
    def do_POST(self):self.handle_request()
    def handle_request(self):
        route=urllib.parse.urlsplit(self.path).path
        data=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))) or b'{}')
        self.server.calls.append((self.command,self.path,dict(self.headers),data))
        mode=self.server.mode
        user={"id":1,"email":"admin@example.test","role":"user" if mode=="nonadmin" else "admin"}
        auth={"access_token":"access-secret","refresh_token":"refresh-secret","user":user}
        if route=="/api/v1/auth/login":
            if data.get("email")!="admin@example.test" or data.get("password")!="test-password":return self.respond(status=401,reason="INVALID_CREDENTIALS")
            if mode=="2fa":return self.respond({"requires_2fa":True,"temp_token":"temporary-secret"})
            return self.respond(auth)
        if route=="/api/v1/auth/login/2fa":
            if data!={"temp_token":"temporary-secret","totp_code":"123456"}:return self.respond(status=401,reason="INVALID_2FA")
            return self.respond(auth)
        if route=="/api/v1/auth/refresh":
            if data!={"refresh_token":"refresh-secret"}:return self.respond(status=401)
            return self.respond({"access_token":"refreshed-secret","refresh_token":"rotated-secret"})
        token=self.headers.get("Authorization")
        if token not in ("Bearer access-secret","Bearer refreshed-secret"):return self.respond(status=401)
        if mode=="expired" and token=="Bearer access-secret":return self.respond(status=401,reason="TOKEN_EXPIRED")
        if mode=="forbidden":return self.respond(status=403,reason="ADMIN_REQUIRED")
        if route.endswith("/quota/refresh"):
            return self.respond({**LIVE,"cache_persisted":True,"credits_cache_persisted":True})
        if route=="/api/v1/admin/accounts":
            params=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if params.get("platform")!=["openai"] or params.get("type")!=["oauth"]:return self.respond(status=400)
            page=int(params["page"][0]); rows=[{"id":20,"name":"GPT Plus","platform":"openai","type":"oauth","status":"active","credentials":{"access_token":"upstream-secret"}}]
            total=1
            if mode in ("multi","partial"):
                rows=[{"id":i,"name":"GPT "+str(i),"platform":"openai","type":"oauth","status":"active"} for i in (20,21,22)]
                total=3
            if mode=="pagination":
                rows=[{"id":page,"name":"GPT "+str(page),"platform":"openai","type":"oauth","status":"active"}] if page<=2 else []
                total=2
            return self.respond({"items":rows,"total":total,"page":page,"page_size":len(rows) or 1})
        if route in tuple("/api/v1/admin/openai/accounts/"+str(i)+"/quota" for i in (1,20,21,22)):
            if mode=="partial" and "/21/" in route:return self.respond(status=502,reason="OPENAI_QUOTA_REQUEST_FAILED")
            if mode=="old":return self.respond(status=404)
            if mode=="upstream_error":return self.respond(status=502,reason="OPENAI_QUOTA_REQUEST_FAILED")
            return self.respond(LIVE)
        if route in ("/api/v1/admin/accounts/20","/api/v1/admin/accounts/1"):
            return self.respond({"id":20,"extra":{} if mode=="empty_snapshot" else SNAPSHOT,"credentials":{"access_token":"upstream-secret"}})
        return self.respond(status=404)

def start_server(mode="live"):
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler)
    server.mode=mode;server.calls=[]
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    return server

class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.server=start_server();cls.url="http://127.0.0.1:"+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def setUp(self):self.server.mode="live";self.server.calls=[];self.client=sub2api.Sub2APIClient(self.url)
    def login(self):return self.client.login("admin@example.test","test-password")
    def test_login_list_and_read_only_live_quota(self):
        self.login();rows=self.client.list_accounts();payload=self.client.fetch_usage(rows[0])
        self.assertEqual(payload["source"],"live");self.assertEqual(len(sub2api.usage_cards(payload)),3)
        self.assertNotIn("credentials",rows[0])
        self.assertEqual(self.server.calls[-1][0],"GET")
        self.assertTrue(self.server.calls[-1][1].endswith("/openai/accounts/20/quota"))
        self.assertFalse(any("/reset-quota" in call[1] or "/responses" in call[1] or "/usage" in call[1] for call in self.server.calls))
    def test_optional_login_2fa(self):
        self.server.mode="2fa"
        with self.assertRaises(sub2api.LoginCodeRequired):self.login()
        self.assertIsNotNone(self.client.pending)
        self.assertEqual(self.client.complete_login("123456")["role"],"admin")
        self.assertIsNone(self.client.pending)
    def test_card_buttons_read_reset_credits_and_points_without_reset(self):
        self.login();account={"id":20,"name":"GPT Plus"}
        reset=self.client.query_reset_credits(account);points=self.client.query_credits(account)
        self.assertIn("可用重置卡次数：2",reset["details"])
        self.assertIn("最近到期：",reset["details"])
        self.assertNotIn("接口返回到期明细",reset["details"])
        self.assertEqual(len(reset["expanded_details"]),1)
        self.assertRegex(reset["expanded_details"][0],"^#1 · 到期：2026-11-18")
        self.assertIn("点数余额：18.40",points["details"])
        quota_calls=[call for call in self.server.calls if call[1].endswith("/quota")]
        self.assertEqual(len(quota_calls),2);self.assertTrue(all(call[0]=="GET" for call in quota_calls))
        self.assertFalse(any("/reset-quota" in call[1] for call in self.server.calls))
    def test_refresh_updates_usage_without_consuming_reset_credit(self):
        self.login();payload=self.client.refresh_usage({"id":20})
        self.assertTrue(payload["refreshed"]);self.assertEqual(len(sub2api.usage_cards(payload)),3)
        refresh=[call for call in self.server.calls if call[1].endswith("/quota/refresh")]
        self.assertEqual(len(refresh),1);self.assertEqual(refresh[0][0],"POST")
        self.assertFalse(any("/reset-quota" in call[1] for call in self.server.calls))
    def test_invalid_otp_does_not_request(self):
        self.client.pending="temporary-secret";n=len(self.server.calls)
        for value in ("", "123", "１２３４５６", "12345a"):
            with self.assertRaises(sub2api.LoginCodeRequired):self.client.complete_login(value)
        self.assertEqual(n,len(self.server.calls))
    def test_nonadmin_rejected(self):
        self.server.mode="nonadmin"
        with self.assertRaises(sub2api.Sub2APIError):self.login()
        self.assertFalse(self.client.access_token)
    def test_login_error_does_not_echo_secrets(self):
        with self.assertRaises(sub2api.Sub2APIError) as e:self.client.login("admin@example.test","wrong")
        self.assertNotIn("test-password",str(e.exception));self.assertNotIn("access-secret",str(e.exception))
    def test_login_session_refresh(self):
        self.login();self.server.mode="expired";self.assertEqual(len(self.client.list_accounts()),1)
        self.assertEqual(self.client.access_token,"refreshed-secret")
        self.assertEqual(self.client.refresh_token,"rotated-secret")
        self.assertEqual(sum(c[1].endswith("/auth/refresh") for c in self.server.calls),1)
    def test_old_server_falls_back_to_labelled_snapshot(self):
        self.login();self.server.mode="old";payload=self.client.fetch_usage({"id":20,"name":"GPT"})
        self.assertEqual(payload["source"],"snapshot");self.assertTrue(payload["fallback"])
        self.assertNotIn("private_key",payload["extra"])
        self.assertNotIn("credentials",payload)
    def test_explicit_snapshot_does_not_call_live_quota(self):
        self.login();payload=self.client.fetch_usage({"id":20},cached=True)
        self.assertEqual(payload["source"],"snapshot")
        self.assertFalse(any(c[1].endswith("/quota") for c in self.server.calls))
    def test_empty_snapshot_is_not_invented(self):
        self.login();self.server.mode="empty_snapshot"
        with self.assertRaises(sub2api.Sub2APIError):self.client.fetch_usage({"id":20},cached=True)
    def test_upstream_failure_does_not_silently_show_cache(self):
        self.login();self.server.mode="upstream_error"
        with self.assertRaises(sub2api.Sub2APIError) as e:self.client.fetch_usage({"id":20})
        self.assertEqual(e.exception.status,502)
        self.assertFalse(any(c[1]=="/api/v1/admin/accounts/20" for c in self.server.calls))
    def test_permission_failure_does_not_use_snapshot(self):
        self.login();self.server.mode="forbidden"
        with self.assertRaises(sub2api.Sub2APIError) as e:self.client.fetch_usage({"id":20})
        self.assertEqual(e.exception.status,403)
    def test_pagination(self):
        self.login();self.server.mode="pagination"
        self.assertEqual(len(self.client.list_accounts()),2)

class ParsingTests(unittest.TestCase):
    def test_live_windows_and_model_specific_limits(self):
        cards=sub2api.usage_cards(LIVE)
        self.assertEqual([c["remaining"] for c in cards],[65,18,88])
        self.assertIn("5 小时",cards[0]["title"]);self.assertIn("7 天",cards[1]["title"])
        self.assertIn("Spark",cards[2]["title"])
        self.assertIn("重置时间",cards[0]["details"])
    def test_primary_window_can_be_weekly(self):
        cards=sub2api.usage_cards({"rate_limit":{"primary_window":{"used_percent":70,"limit_window_seconds":604800}}})
        self.assertIn("7 天",cards[0]["title"])
    def test_missing_percent_not_invented(self):
        for value in (None,"NaN",-1,True):
            card=sub2api.usage_cards({"rate_limit":{"primary_window":{"used_percent":value}}})[0]
            self.assertIsNone(card["remaining"])
    def test_over_100_percent_keeps_actual_used_and_clamps_remaining(self):
        card=sub2api.usage_cards({"rate_limit":{"primary_window":{"used_percent":110}}})[0]
        self.assertEqual(card["used"],110);self.assertEqual(card["remaining"],0)
    def test_cache_prefers_canonical_fields_and_preserves_zero(self):
        extra={**SNAPSHOT,"codex_5h_used_percent":0,"codex_primary_used_percent":99}
        cards=sub2api.snapshot_cards(extra)
        self.assertEqual(len(cards),2);self.assertEqual(cards[0]["remaining"],100)
    def test_legacy_window_duration(self):
        cards=sub2api.snapshot_cards({"codex_primary_used_percent":75,"codex_primary_window_minutes":10080})
        self.assertIn("7 天",cards[0]["title"])
    def test_url_and_subpath(self):
        self.assertEqual(sub2api.normalize_url("https://example.test/sub/api/v1/"),"https://example.test/sub")
        for value in ("example.test","https://u:p@example.test","https://example.test?secret=x","https://example.test/#x"):
            with self.assertRaises(sub2api.Sub2APIError):sub2api.normalize_url(value)
    def test_generic_usage_shape_and_null_windows(self):
        cards=sub2api.usage_cards({"five_hour":{"utilization":25,"resets_at":"2026-11-16T12:00:00Z"},"seven_day":None})
        self.assertEqual(len(cards),1);self.assertEqual(cards[0]["remaining"],75)
        self.assertEqual(sub2api.usage_cards({"rate_limit":None}),[])
    def test_missing_card_values_are_not_invented(self):
        with self.assertRaises(sub2api.Sub2APIError):sub2api.reset_credit_card({"rate_limit":{}})
        with self.assertRaises(sub2api.Sub2APIError):sub2api.codex_credit_card({"credits":{"has_credits":True,"unlimited":False,"balance":None}})
        self.assertIn("不限量",sub2api.codex_credit_card({"credits":{"has_credits":True,"unlimited":True,"balance":None}})["details"])
    def test_many_reset_credits_use_summary_and_expanded_details(self):
        payload={"rate_limit_reset_credits":{"available_count":7,"credits":[{"expires_at":"2026-12-01T00:00:00Z"},{"expires_at":"2026-12-02T00:00:00Z"},{"expires_at":"2026-12-03T00:00:00Z"},{"expires_at":"2026-12-04T00:00:00Z"},{"expires_at":"2026-12-05T00:00:00Z"},{"expires_at":"2026-12-06T00:00:00Z"},{"expires_at":"2026-12-07T00:00:00Z"}]}}
        card=sub2api.reset_credit_card(payload)
        self.assertIn("最近到期：",card["details"]);self.assertIn("2026-12-01",card["details"]);self.assertIn("明细较多，展开查看。",card["details"])
        self.assertNotIn("接口返回到期明细",card["details"])
        self.assertEqual(len(card["expanded_details"]),7);self.assertNotIn("#1 · 到期：2026-12-01",card["details"])
    def test_raw_credential_redaction(self):
        raw=quota.redact_payload({"access_token":"a","refresh_token":"b","credentials":{"session_key":"c"},"totalTokens":123})
        self.assertEqual(raw["access_token"],"[已隐藏]");self.assertEqual(raw["refresh_token"],"[已隐藏]")
        self.assertEqual(raw["credentials"],"[已隐藏]");self.assertEqual(raw["totalTokens"],123)

if __name__=="__main__":unittest.main(verbosity=2)
