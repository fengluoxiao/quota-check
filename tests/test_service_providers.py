import copy,io,json,sys,unittest,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
import service_providers as p
import quota,vault
CASES=json.loads((Path(__file__).parent/'fixtures/providers-usage.json').read_text(encoding='utf-8'))
def profile(id):
    return {f['key']:('ssoSessionId=test-only; tenantToken=test-only' if p.BY_ID[id]['auth']=='cookie' and f['key']=='secret' else 'test-only-secret') for f in p.BY_ID[id]['fields']}|{'sealed':False}
class ProviderTests(unittest.TestCase):
    def test_shared_vendor_contracts(self):
        for case in CASES:
            with self.subTest(id=case['id']):
                rows=p.parse_usage(case['id'],case['payload']);self.assertEqual(len(rows),len(case['expect']))
                for row,e in zip(rows,case['expect']):
                    self.assertEqual(row['used'],e['used']);self.assertEqual(row['remaining'],e['remaining']);self.assertIn(e['title'],row['title'])
                    if e.get('contains'):self.assertIn(e['contains'],row['details'])
    def test_console_secret_fields_never_leave_the_parser(self):
        for case in CASES:
            rows=p.parse_usage(case['id'],case['payload'],sealed=True);text=json.dumps(rows)
            for secret in ('must-not-be-exposed-key','must-not-be-exposed-secret','private-seat-name','private-user-phone'):
                self.assertNotIn(secret,text)
    def test_missing_usage_and_auth_errors_are_not_zero(self):
        for case in CASES:
            with self.subTest(id=case['id']),self.assertRaises(quota.QueryError):p.parse_usage(case['id'],{})
        for bad in ({'success':False},{'error':{'message':'test-secret'}},{'ResponseMetadata':{'Error':{'Code':'AccessDenied'}}}):
            with self.assertRaises(quota.QueryError) as error:p.parse_usage('ark_agent',bad)
            self.assertNotIn('test-secret',str(error.exception))
        rows=p.parse_usage('ark_agent',{'Result':{'AFPFiveHour':{'Quota':100}}})
        self.assertIsNone(rows[0]['used']);self.assertIsNone(rows[0]['remaining'])
    def test_nested_console_failures_are_rejected(self):
        for failure in ({'successResponse':False},{'failed':True},{'ret':['FAIL_SYS_SESSION_EXPIRED::expired']}):
            payload={'data':{'DataV2':{**failure,'data':{'data':{'per1MonthPercentage':0}}}}}
            with self.assertRaises(quota.QueryError):p.parse_usage('aliyun_token',payload)
    def test_negative_balance_is_preserved(self):
        rows=p.parse_usage('deepseek',{'balance_infos':[{'currency':'CNY','total_balance':'-1.25'}]})
        self.assertIn('-1.25 CNY',rows[0]['details']);self.assertIsNone(rows[0]['used'])
    def test_requests_only_target_fixed_read_actions(self):
        for spec in p.CATALOG:
            id=spec['id'];request=p.request_spec(id,profile(id),timestamp='20261117T010203Z')
            self.assertTrue(request['url'].startswith('https://'));self.assertNotIn('/messages',request['url']);self.assertNotIn('/completions',request['url'])
            self.assertNotIn('purchase',request['url']);self.assertNotIn('refresh-key',request['url'])
            if id.startswith('aliyun'):
                from urllib.parse import parse_qs
                body=parse_qs(request['body']);params=json.loads(body['params'][0]);self.assertIn('cornerstoneParam',params['Data']);self.assertEqual(request['headers']['Authorization'],'Bearer test-only-secret')
            if spec['auth']=='cookie':self.assertEqual(request['headers']['Cookie'],profile(id)['secret'])
        self.assertIn('GetAFPUsage',p.request_spec('ark_agent',profile('ark_agent'))['url'])
    def test_signature_is_deterministic_and_preserves_sts(self):
        headers=p.sign_volc('AKIDEXAMPLE','test-only-secret-key','test-only-session',timestamp='20261117T010203Z')
        self.assertEqual(headers['X-Security-Token'],'test-only-session')
        expected=json.loads((Path(__file__).parent/'fixtures/volc-signature.json').read_text())
        self.assertEqual(headers,expected['headers'])
        self.assertNotEqual(headers['Authorization'],p.sign_volc('AKIDEXAMPLE','different-test-key','test-only-session',timestamp='20261117T010203Z')['Authorization'])
    def test_generic_profiles_roundtrip_without_plaintext_and_seal_all(self):
        data={'version':1,'source':9,'profiles':{s['id']:profile(s['id']) for s in p.CATALOG}}
        encoded=vault.encode(data,password='provider-test-password')
        self.assertNotIn(b'test-only-secret',encoded);self.assertEqual(vault.decode(encoded,password='provider-test-password'),data)
        locked=vault.imported(data);self.assertTrue(all(x['sealed'] for x in locked['profiles'].values()))
        with self.assertRaises(vault.VaultError):vault.exportable(locked)
    def test_credential_injection_and_unexpected_fields_rejected(self):
        for spec in p.CATALOG:
            bad=profile(spec['id']);bad['secret']='test\r\nAuthorization: injected'
            with self.assertRaises(quota.QueryError):p.validate_profile(spec['id'],bad)
            bad=profile(spec['id']);bad['url']='https://attacker.invalid'
            with self.assertRaises(quota.QueryError):p.validate_profile(spec['id'],bad)
    def test_http_errors_never_echo_backend_bodies(self):
        class Client:
            def open(self,*a,**kw):raise urllib.error.HTTPError('https://example.invalid',403,'test-secret',{},io.BytesIO(b'test-secret'))
        with self.assertRaises(quota.QueryError) as error:p.fetch_usage('deepseek',profile('deepseek'),opener=Client())
        self.assertNotIn('test-secret',str(error.exception))
    def test_seat_pagination_returns_all_records_and_handles_empty_final_page(self):
        class Client:
            calls=[]
            def open(self,r,timeout):
                self.calls.append(r.full_url);rows=[{'id':i,'usage':{'usedPoints':i,'totalAuthorizedPoints':1000}} for i in range(100)] if len(self.calls)==1 else []
                return io.BytesIO(json.dumps({'code':0,'data':{'seats':rows}}).encode())
        client=Client();rows=p.fetch_usage('astron',profile('astron'),opener=client)['cards']
        self.assertEqual(len(rows),100);self.assertEqual(len(client.calls),2);self.assertIn('page=0',client.calls[0]);self.assertIn('page=1',client.calls[1])
if __name__=='__main__':unittest.main()
