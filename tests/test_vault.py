import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
import vault

DATA={"version":1,"source":1,"profiles":{
 "glm":{"site":"cn","key":"private-glm-key-123","sealed":False},
 "sub2api":{"url":"https://sub.example.test","email":"private-admin@example.test","password":"private-login-password","access_token":"private-access-token","refresh_token":"private-refresh-token","user":{"id":1,"email":"private-admin@example.test","role":"admin"},"cached":False,"sealed":False},
 "newapi":{"url":"https://new.example.test","username":"private-root","password":"private-new-password","sealed":False}}}
PASSWORD="portable-file-password-2026"

class VaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local=vault.encode(DATA);cls.portable=vault.encode(DATA,password=PASSWORD)
    def test_dpapi_container_roundtrip(self):
        self.assertEqual(vault.inspect(self.local),vault.LOCAL)
        self.assertEqual(vault.decode(self.local),DATA)
    def test_portable_container_roundtrip(self):
        self.assertEqual(vault.inspect(self.portable),vault.PORTABLE)
        self.assertEqual(vault.decode(self.portable,password=PASSWORD),DATA)
    def test_no_plaintext_credentials_or_server_names(self):
        for blob in (self.local,self.portable):
            for secret in ("private-glm-key-123","private-admin@example.test","private-login-password","private-access-token","private-refresh-token","private-root","private-new-password","sub.example.test"):
                self.assertNotIn(secret.encode(),blob)
            self.assertFalse(blob.startswith(b'{'))
    def test_fresh_nonce_for_each_export(self):
        self.assertNotEqual(self.local,vault.encode(DATA))
        self.assertNotEqual(self.portable,vault.encode(DATA,password=PASSWORD))
    def test_wrong_password_is_rejected(self):
        with self.assertRaises(vault.VaultError):vault.decode(self.portable,password="a-wrong-password-123")
    def test_short_password_rejected(self):
        with self.assertRaises(vault.VaultError):vault.encode(DATA,password="123456")
    def test_ciphertext_tampering_rejected(self):
        blob=bytearray(self.portable);blob[-1]^=1
        with self.assertRaises(vault.VaultError):vault.decode(bytes(blob),password=PASSWORD)
    def test_authenticated_header_tampering_rejected(self):
        blob=bytearray(self.portable);blob[14]^=1
        with self.assertRaises(vault.VaultError):vault.decode(bytes(blob),password=PASSWORD)
    def test_wrong_user_dpapi_is_rejected(self):
        with patch.object(vault.settings,"crypt",side_effect=OSError("should-not-leak private-login-password")):
            with self.assertRaises(vault.VaultError) as e:vault.decode(self.local)
        self.assertNotIn("private-login-password",str(e.exception))
    def test_truncated_appended_and_random_files_rejected(self):
        for blob in (b"",b"not a vault",self.local[:-1],self.portable+b"extra",self.portable[:20]):
            with self.subTest(size=len(blob)),self.assertRaises(vault.VaultError):vault.decode(blob,password=PASSWORD)
    def test_oversized_file_rejected(self):
        with self.assertRaises(vault.VaultError):vault.inspect(b'x'*(vault.MAX_SIZE+1))
    def test_unknown_mode_and_version_rejected(self):
        for index in (8,9):
            blob=bytearray(self.portable);blob[index]=99
            with self.assertRaises(vault.VaultError):vault.inspect(bytes(blob))
    def test_imports_are_always_sealed(self):
        result=vault.imported(DATA)
        self.assertTrue(all(v["sealed"] for v in result["profiles"].values()))
        self.assertFalse(DATA["profiles"]["glm"]["sealed"])
    def test_imported_profiles_cannot_be_reexported(self):
        with self.assertRaises(vault.VaultError):vault.exportable(vault.imported(DATA))
    def test_mixed_export_excludes_imported_credentials(self):
        data=copy.deepcopy(DATA);data["profiles"]["sub2api"]["sealed"]=True
        result=vault.exportable(data)
        self.assertNotIn("sub2api",result["profiles"])
        self.assertIn("glm",result["profiles"])
    def test_url_and_unknown_fields_validation(self):
        for url in ("https://user:pass@sub.example.test","https://sub.example.test?q=secret","file:///tmp/x"):
            data=copy.deepcopy(DATA);data["profiles"]["sub2api"]["url"]=url
            with self.assertRaises(vault.VaultError):vault.validate(data)
        data=copy.deepcopy(DATA);data["profiles"]["glm"]["execute"]="anything"
        with self.assertRaises(vault.VaultError):vault.validate(data)
    def test_invalid_user_session_types_rejected(self):
        data=copy.deepcopy(DATA);data["profiles"]["sub2api"]["user"]["role"]={"bad":"shape"}
        with self.assertRaises(vault.VaultError):vault.validate(data)
    def test_atomic_local_persistence(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"connections.sqv"
            with patch.object(vault,"local_path",return_value=p):
                vault.save_local(DATA);self.assertEqual(vault.load_local(),DATA)
                self.assertNotIn(b'private-login-password',p.read_bytes())
                self.assertEqual(len(list(Path(temp).iterdir())),1)
    def test_legacy_key_migration(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(vault,"local_path",return_value=Path(temp)/"connections.sqv"),patch.object(vault.settings,"load",return_value={"site":"cn","key":"legacy-key"}):
                result=vault.load_local()
                self.assertEqual(result["profiles"]["glm"]["key"],"legacy-key")
    def test_no_json_pickle_or_executable_deserialization(self):
        with self.assertRaises(vault.VaultError):vault.decode(json.dumps(DATA).encode())

if __name__=="__main__":unittest.main(verbosity=2)
