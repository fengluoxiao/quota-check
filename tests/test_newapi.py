import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import base64
import http.server
import json
import threading
import unittest
import urllib.parse
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding,rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import newapi

class URLTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(newapi.normalize_url(" https://example.com/prefix/api/ "),"https://example.com/prefix")
        self.assertEqual(newapi.normalize_url("http://127.0.0.1:8080"),"http://127.0.0.1:8080")
    def test_reject_bad_urls(self):
        for value in ("example.com","file:///x","https://u:p@example.com","https://example.com?q=secret","https://example.com/#x","https://example.com\n/api","https://example.com:abc"):
            with self.subTest(value=value),self.assertRaises(newapi.NewAPIError): newapi.normalize_url(value)

class EncryptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.data={"kid":"test-key-id","public_key":cls.private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
    def test_rsa_password_envelope(self):
        fields=newapi.encrypt_password("test-password",self.data)
        p=padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None)
        self.assertEqual(self.private.decrypt(base64.b64decode(fields["password_encrypted"]),p),b"test-password")
        self.assertEqual(fields["encryption_key_id"],"test-key-id")
        self.assertNotIn("password",fields)
    def test_long_password_envelope(self):
        password="长密码"*100
        fields=newapi.encrypt_password(password,self.data)
        version,wrapped,nonce,content=fields["password_encrypted"].split(".")
        self.assertEqual(version,"v2")
        secret=self.private.decrypt(base64.b64decode(wrapped),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=b"password-v2"))
        raw=AESGCM(secret).decrypt(base64.b64decode(nonce),base64.b64decode(content),b"password-v2:test-key-id")
        self.assertEqual(raw.decode(),password)
    def test_bad_public_key(self):
        with self.assertRaises(newapi.NewAPIError):newapi.encrypt_password("x",{"kid":"x","public_key":"broken"})

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version="HTTP/1.0"
    def log_message(self,*args): pass
    def respond(self,payload,status=200,cookie=None):
        body=json.dumps(payload).encode()
        self.send_response(status);self.send_header("Content-Type","application/json")
        if cookie:self.send_header("Set-Cookie",cookie)
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def handle_request(self):
        data=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))) or b'{}')
        self.server.calls.append((self.command,self.path,dict(self.headers),data))
        mode=self.server.mode
        path=urllib.parse.urlsplit(self.path).path
        ok=lambda d:{"success":True,"data":d}
        user={"id":1,"username":"test-root","role":100}
        if path=="/api/status":return self.respond(ok({"turnstile_check":mode=="captcha"}))
        if path=="/api/user/login":
            if data.get("password")!="test-password":return self.respond({"success":False,"message":"echo test-password"})
            if mode=="modern2fa":return self.respond(ok({"require_verification":True,"flow_token":"test-flow","methods":[{"method":"2fa","available":True}]}))
            if mode=="legacy2fa":return self.respond(ok({"require_2fa":True}),cookie="session=pending; Path=/")
            if mode=="legacy":return self.respond(ok(user),cookie="session=loggedin; Path=/")
            if mode=="nonroot": user["role"]=10
            return self.respond(ok({"access_token":"test-session-token","user":user}))
        if path=="/api/user/login/verify":
            if data.get("flow_token")!="test-flow" or data.get("code")!="123456":return self.respond({"success":False})
            return self.respond(ok({"access_token":"test-session-token","user":user}))
        if path=="/api/user/login/2fa":
            if "session=pending" not in self.headers.get("Cookie",""):return self.respond({"success":False})
            return self.respond(ok(user),cookie="session=loggedin; Path=/")
        auth=self.headers.get("Authorization")=="Bearer test-session-token" or any(v in self.headers.get("Cookie","") for v in ("session=loggedin","session=verified"))
        if not auth:return self.respond({"success":False},401)
        if self.headers.get("New-Api-User")!="1":return self.respond({"success":False},403)
        if path=="/api/channel/":
            page=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)["p"][0]
            rows=[{"id":10,"name":"Other","models":"gpt"}] if page=="1" else [{"id":20,"name":"GLM","base_url":"https://open.bigmodel.cn","key":"must-not-store"}]
            return self.respond(ok({"items":rows,"total":2}))
        if path=="/api/verify":
            if data.get("code")!="654321":return self.respond({"success":False,"code":"SECURITY_VERIFICATION_FAILED"})
            if mode in ("legacy","legacy2fa"):return self.respond(ok(None),cookie="session=verified; Path=/")
            if data.get("scope")!="channel.key.read" or data.get("context")!={"channel_id":20}:return self.respond({"success":False})
            return self.respond(ok({"proof_token":"test-proof"}))
        if path=="/api/channel/20/key":
            proof=self.headers.get("X-Security-Proof")=="test-proof" or "session=verified" in self.headers.get("Cookie","")
            if not proof:return self.respond({"success":False,"code":"SECURITY_PROOF_REQUIRED"},403)
            raw="{\"plugin\":true}" if mode=="redacted" else "test-glm-key-A\ntest-glm-key-B\ntest-glm-key-A"
            return self.respond(ok({"key":raw}))
        return self.respond({"success":False},404)

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.server.mode="modern";cls.server.calls=[]
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url="http://127.0.0.1:"+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def setUp(self):self.server.mode="modern";self.server.calls=[];self.client=newapi.NewAPIClient(self.url)
    def login(self):return self.client.login("test-root","test-password")
    def test_modern_login_and_key_proof(self):
        self.login();keys=self.client.channel_keys(20,"654321")
        self.assertEqual(keys,["test-glm-key-A","test-glm-key-B"])
        self.assertEqual(self.server.calls[-1][0],"POST")
        self.assertEqual(self.server.calls[-1][2].get("X-Security-Proof"),"test-proof")
    def test_modern_login_second_factor(self):
        self.server.mode="modern2fa"
        with self.assertRaises(newapi.LoginCodeRequired):self.login()
        self.assertIsNotNone(self.client.pending)
        self.assertEqual(self.client.complete_login("123456")["id"],1)
        self.assertIsNone(self.client.pending)
    def test_legacy_cookie_session_and_verification(self):
        self.server.mode="legacy";self.login()
        self.assertEqual(len(self.client.channel_keys(20,"654321")),2)
    def test_legacy_second_factor_keeps_cookie(self):
        self.server.mode="legacy2fa"
        with self.assertRaises(newapi.LoginCodeRequired):self.login()
        self.client.complete_login("123456")
        self.assertEqual(len(self.client.channel_keys(20,"654321")),2)
    def test_pagination_priority_and_key_exclusion(self):
        self.login();rows=self.client.list_channels()
        self.assertEqual([r["id"] for r in rows],[20,10])
        self.assertTrue(all("key" not in r for r in rows))
    def test_nonroot_blocked(self):
        self.server.mode="nonroot";self.login()
        count=len(self.server.calls)
        with self.assertRaises(newapi.NewAPIError):self.client.channel_keys(20)
        self.assertEqual(len(self.server.calls),count)
    def test_missing_proof_and_bad_code(self):
        self.login()
        with self.assertRaises(newapi.NewAPIError) as e:self.client.channel_keys(20)
        self.assertEqual(e.exception.code,"SECURITY_PROOF_REQUIRED")
        with self.assertRaises(newapi.NewAPIError) as e:self.client.channel_keys(20,"000000")
        self.assertEqual(e.exception.code,"SECURITY_VERIFICATION_FAILED")
    def test_redacted_or_structured_credential_rejected(self):
        self.server.mode="redacted";self.login()
        with self.assertRaises(newapi.NewAPIError):self.client.channel_keys(20,"654321")
    def test_password_never_echoed_in_errors(self):
        with self.assertRaises(newapi.NewAPIError) as e:self.client.login("test-root","wrong-password")
        self.assertNotIn("password",str(e.exception))
    def test_captcha_requirement_stops_before_login(self):
        self.server.mode="captcha"
        with self.assertRaises(newapi.NewAPIError):self.login()
        self.assertEqual(len(self.server.calls),1)

if __name__=="__main__":unittest.main(verbosity=2)
