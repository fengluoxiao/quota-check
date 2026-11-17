import copy
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import kimi
import quota
import vault
CASES=json.loads((Path(__file__).parent/'fixtures/kimi-usage.json').read_text(encoding='utf-8'))

class KimiTests(unittest.TestCase):
    def test_shared_contract(self):
        for case in CASES:
            with self.subTest(name=case['name']):
                cards=kimi.quota_cards(case['payload'])
                self.assertEqual(len(cards),len(case['expected']))
                for card,expected in zip(cards,case['expected']):
                    for key in ('used','remaining'):self.assertEqual(card[key],expected[key])
                    self.assertEqual(card['title'],'Kimi · '+expected['title'])
                    for part in expected['parts']:self.assertIn(part,card['details'])
                    if expected.get('reset'):self.assertTrue('重置' in card['details'])
    def test_missing_malformed_and_error_payloads_rejected(self):
        for payload in (None,[],{}, {'error':{'message':'secret'}},{'usage':{'used':True}},{'limits':'bad'},{'limits':[None]},{'limits':[{'detail':[]}]}):
            with self.subTest(payload=payload),self.assertRaises(quota.QueryError):kimi.quota_cards(payload)
    def test_request_uses_only_official_usage_endpoint(self):
        class Client:
            def open(self,request,timeout):
                self.request=request;self.timeout=timeout
                return io.BytesIO(json.dumps(CASES[0]['payload']).encode())
        client=Client();kimi.fetch_quota(' Bearer test-only-key ',opener=client)
        self.assertEqual(client.request.full_url,'https://api.kimi.com/coding/v1/usages')
        self.assertEqual(client.request.get_header('Authorization'),'Bearer test-only-key')
        self.assertEqual(client.request.get_method(),'GET');self.assertIsNone(client.request.data)
    def test_bad_keys_do_not_send_network_requests(self):
        for key in ('','x y','x\ny','中文'):
            with self.subTest(key=key),self.assertRaises(quota.QueryError):kimi.fetch_quota(key)
    def test_http_errors_never_display_server_secrets(self):
        for code in (401,403,404,429,500):
            class Client:
                def open(self,*a,**kw):raise urllib.error.HTTPError(kimi.ENDPOINT,code,'secret-test-key',{},io.BytesIO(b'secret-test-key'))
            with self.assertRaises(quota.QueryError) as error:kimi.fetch_quota('secret-test-key',opener=Client())
            self.assertNotIn('secret-test-key',str(error.exception))
    def test_oversized_and_non_json_responses_rejected(self):
        for body in (b'x'*(kimi.MAX_BYTES+1),b'<html>error</html>'):
            class Client:
                def open(self,*a,**kw):return io.BytesIO(body)
            with self.assertRaises(quota.QueryError):kimi.fetch_quota('test-key',opener=Client())
    def test_kimi_vault_roundtrip_sealing_and_legacy_compatibility(self):
        data={'version':1,'source':2,'profiles':{'kimi':{'key':'private-kimi-test-key','sealed':False}}}
        password='kimi-test-file-password'
        blob=vault.encode(data,password=password)
        self.assertNotIn(b'private-kimi-test-key',blob)
        self.assertEqual(vault.decode(blob,password=password),data)
        imported=vault.imported(data)
        self.assertTrue(imported['profiles']['kimi']['sealed'])
        self.assertEqual(imported['source'],2)
        with self.assertRaises(vault.VaultError):vault.exportable(imported)
        legacy={'version':1,'source':1,'profiles':{}}
        self.assertEqual(vault.validate(legacy),legacy)
    def test_invalid_kimi_vault_fields_rejected(self):
        for record in ({'key':''},{'key':'x\ny'},{'key':'test-key','url':'https://example.test'}):
            with self.assertRaises(vault.VaultError):vault.validate({'version':1,'source':2,'profiles':{'kimi':record}})

if __name__=='__main__':unittest.main()
