import io,json,sys,unittest,urllib.error
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import provider_extras as p
import quota,vault

class ExtraTests(unittest.TestCase):
    def test_shared_contract_and_no_redemption_or_identity_fields(self):
        cases=json.loads((Path(__file__).parent/'fixtures/extras-usage.json').read_text(encoding='utf-8'))
        for case in cases:
            with self.subTest(provider=case['provider'],action=case['action']):
                rows=p.parse(case['provider'],case['action'],case['payload'],now=datetime(2026,11,19,tzinfo=timezone.utc))
                self.assertEqual(len(rows),case['count'])
                self.assertIn(case['value'],rows[0]['details'])
                self.assertEqual(len(rows[0]['expanded_details']),case['expanded'])
                self.assertNotIn('never-export-handle',json.dumps(rows))
                self.assertIsNone(rows[0]['used'])

    def test_missing_values_never_show_zero_or_full_quota(self):
        for name,actions in p.ACTIONS.items():
            for action,_ in actions:
                with self.subTest(name=name,action=action),self.assertRaises(quota.QueryError):p.parse(name,action,{})
        for bad in (True,-1,1.5,'2'):
            with self.assertRaises(quota.QueryError):p.parse('claude','reset',{'cedar_ember':{'eligible':True,'grants':[{'resets_left':bad,'paused':False}]}})
        with self.assertRaises(quota.QueryError):p.parse('mimo_balance','daily',{'data':[{'date':'2026-11-19','name':'model'}]})
        with self.assertRaises(quota.QueryError):p.parse('claude','reset',{'cedar_ember':{'eligible':True,'grants':[{'resets_left':1,'paused':False,'ends_at':'invalid'}]}})

    def test_zero_inventory_and_empty_records_are_explicit(self):
        self.assertEqual(p.parse('claude','reset',{'cedar_ember':{'eligible':True,'grants':[]}})[0]['value'],'0 次可用')
        self.assertEqual(p.parse('mimo_balance','bill',{'data':[]})[0]['value'],'0 条记录')

    def test_read_only_requests_and_local_date_range(self):
        profile={'secret':'test-only','secret2':'test-only','session_token':'test-only','console_token':'Bearer console-only','site':'cn'}
        for name,actions in p.ACTIONS.items():
            for action,_ in actions:
                record={k:v for k,v in profile.items() if k in ('secret','secret2','session_token')} if name=='ark_agent' else profile
                spec=p.request_spec(name,action,record,now=datetime(2026,11,18,17,tzinfo=timezone.utc))
                self.assertTrue(spec['url'].startswith('https://'))
                for prohibited in ('/use','reset-quota','purchase','create-order'):self.assertNotIn(prohibited,spec['url'])
                self.assertEqual(spec['method'],'POST' if name=='ark_agent' else 'GET')
        spec=p.request_spec('mimo_balance','daily',profile,now=datetime(2026,11,18,17,tzinfo=timezone.utc))
        self.assertIn('start_date=2026-11-13&end_date=2026-11-19',spec['url'])
        self.assertEqual(p.request_spec('glm','boost',profile)['headers']['Authorization'],'Bearer console-only')
        with self.assertRaises(quota.QueryError):p.request_spec('glm','boost',{'key':'model-key','site':'cn'})
        with self.assertRaises(quota.QueryError):p.request_spec('glm','reset',profile)

    def test_errors_do_not_echo_credentials(self):
        class Client:
            def open(self,*a,**kw):raise urllib.error.HTTPError('https://example.test',403,'test-secret',{},io.BytesIO(b'test-secret'))
        with self.assertRaises(quota.QueryError) as error:p.fetch('claude','reset',{'secret':'test-secret'},opener=Client())
        self.assertNotIn('test-secret',str(error.exception))

    def test_glm_console_token_stays_encrypted_and_sealed(self):
        data={'version':1,'source':0,'profiles':{'glm':{'site':'cn','key':'test-key','console_token':'Bearer test-console','sealed':False}}}
        blob=vault.encode(data,password='test-file-password')
        self.assertNotIn(b'test-console',blob)
        restored=vault.decode(blob,password='test-file-password')
        self.assertEqual(restored,data)
        with self.assertRaises(vault.VaultError):vault.exportable(vault.imported(restored))
