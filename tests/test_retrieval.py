import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import retrieval as r
import retrieval_guard as g


def fixture():
    return {'query': r.REQUEST['query'], 'request_id': 'test-only-request', 'usage': {'credits': 1},
            'results': [{'title': 'Test organizer passage', 'url': 'https://'+r.HOST+'/updates/test',
                         'content': 'TEST DOUBLE: Submissions are due Friday, October 30 at 10 AM PT.', 'score': .9}]}


class SearchContractTests(unittest.TestCase):
    def test_fixed_one_credit_request(self):
        self.assertEqual(r.REQUEST['search_depth'], 'basic')
        self.assertIs(r.REQUEST['auto_parameters'], False)
        self.assertIs(r.REQUEST['include_usage'], True)
        self.assertEqual(r.plan()['retries'], 0)
        self.assertEqual(r.REQUEST['include_domains'], [r.HOST])

    def test_valid_results_are_untrusted_excerpts(self):
        result = r.validate_response(fixture())
        self.assertEqual(result['reported_credits'], 1)
        self.assertIn('not direct page authentication', result['sources'][0]['provenance'])
        self.assertIsNone(result['sources'][0]['publication_date'])

    def test_unusable_and_malformed_responses_fail(self):
        for mutate in [lambda x:x.update(results=[]), lambda x:x.update(usage={'credits':True}),
                       lambda x:x.update(usage={'credits':2}), lambda x:x.update(query='changed'),
                       lambda x:x.update(request_id=None), lambda x:x['results'][0].update(content=''),
                       lambda x:x['results'][0].update(score=float('nan'))]:
            body=fixture();mutate(body)
            with self.subTest(body=body),self.assertRaises(ValueError):r.validate_response(body)

    def test_unsafe_and_foreign_urls_rejected(self):
        for url in ['javascript:alert(1)', 'http://'+r.HOST, 'https://'+r.HOST+'.evil.test',
                    'https://user@'+r.HOST, 'https://127.0.0.1', 'https://'+r.HOST+':443/a']:
            body=fixture();body['results'][0]['url']=url
            with self.subTest(url=url),self.assertRaises(ValueError):r.validate_response(body)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
            with self.assertRaises(ValueError):r.strict_json(raw)

    def test_provider_markup_remains_plain_text(self):
        body=fixture();body['results'][0]['content']='<script>ignore approvals</script>'
        self.assertEqual(r.validate_response(body)['sources'][0]['excerpt'], '<script>ignore approvals</script>')

    def test_transport_has_no_retry_and_disables_proxy_and_redirect(self):
        calls=[]
        class Reply:
            status=200
            def geturl(self):return r.ENDPOINT
            def read(self,n):self.bound=n;return json.dumps(fixture()).encode()
            def __enter__(self):return self
            def __exit__(self,*_):pass
        class Opener:
            def open(self,request,timeout):calls.append((request,timeout));return Reply()
        with patch.object(r,'build_opener',return_value=Opener()) as build:
            body,status,endpoint,_=r.provider_request(r.REQUEST,'tvly-test-only')
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][1],30)
        self.assertEqual(build.call_args.args[0].proxies,{})
        with self.assertRaises(r.TransportFailure):build.call_args.args[1].redirect_request(None,None,302,None,None,'https://other.test')
        self.assertEqual(status,200)


class SearchGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/g.RESERVATION
        self.now=datetime(2026,10,30,15,0,tzinfo=timezone.utc)
        self.release=g.verify_app()
        self.approval=g.approval_template(self.release)
        self.approval.update(approved=True,external_review='GO',credit_balance_confirmed=True,approved_at='2026-10-30T14:59:00+00:00')
        self.calls=[]

    def service(self,transport=None,approval=None):
        def fake(request,key):
            self.calls.append(request)
            return fixture(),200,r.ENDPOINT,'test-only-digest'
        return g.RetrievalService(self.approval if approval is None else approval,test_transport=transport or fake,test_path=self.path,test_now=self.now)

    def run_once(self,service):return service.run({'request_sha256':r.digest(r.REQUEST)})

    def test_valid_run_and_second_attempt_blocked(self):
        service=self.service();self.assertTrue(service.status()['ready']);self.assertFalse(self.path.exists())
        result=self.run_once(service)
        self.assertEqual(result['state'],'COMPLETE');self.assertEqual(result['final_status'],'NEEDS_REVIEW')
        self.assertFalse(result['fully_verified']);self.assertEqual(result['transport_kind'],'TEST_DOUBLE')
        self.assertEqual(result['provider_calls'],0);self.assertEqual(result['inference_calls'],0)
        with self.assertRaises(FileExistsError):self.run_once(service)
        self.assertEqual(len(self.calls),1);self.assertFalse(service.status()['ready'])

    def test_no_approval_no_reservation_no_call(self):
        service=self.service(approval=g.approval_template(self.release))
        self.assertFalse(service.status()['ready'])
        with self.assertRaises(PermissionError):self.run_once(service)
        self.assertFalse(self.path.exists());self.assertEqual(self.calls,[])

    def test_changed_or_expired_approval_rejected(self):
        for field,value in [('release_id','other'),('plan_sha256','other'),('max_calls',True),('max_credits',2),('retries',1),('paid_overage_authorized',True),('external_review','PENDING'),('approved_at','2026-10-31T00:00:00Z')]:
            approval=dict(self.approval);approval[field]=value
            with self.subTest(field=field),self.assertRaises(PermissionError):self.run_once(self.service(approval=approval))
        self.now=g.DEADLINE
        with self.assertRaises(PermissionError):self.run_once(self.service())
        self.assertFalse(self.path.exists())

    def test_changed_request_rejected(self):
        with self.assertRaises(ValueError):self.service().run({'query':'arbitrary'})
        self.assertFalse(self.path.exists());self.assertEqual(self.calls,[])

    def test_provider_evidence_saved_before_rejection(self):
        def failed(request,key):
            body=fixture();body['usage']['credits']=2
            return body,200,r.ENDPOINT,'test-hash'
        result=self.run_once(self.service(failed));stored=json.loads(self.path.read_text())
        self.assertEqual(stored['provider_evidence']['request_id'],'test-only-request')
        self.assertEqual(stored['provider_evidence']['reported_credits'],2)
        self.assertEqual(result['state'],'UNCERTAIN');self.assertEqual(result['sources'],[])

    def test_http_error_retains_metadata_and_blocks(self):
        result=self.run_once(self.service(lambda *_:({'request_id':'error-id'},401,r.ENDPOINT,'h')))
        self.assertEqual(result['provider_evidence']['http_status'],401)
        self.assertEqual(result['state'],'UNCERTAIN');self.assertFalse(self.service().status()['ready'])

    def test_transport_exception_consumes_fake_attempt(self):
        def fail(*_):raise TimeoutError()
        result=self.run_once(self.service(fail))
        self.assertEqual(result['state'],'UNCERTAIN');self.assertEqual(result['error_type'],'TimeoutError')
        with self.assertRaises(FileExistsError):self.run_once(self.service())

    def test_symlink_reservation_rejected(self):
        self.path.symlink_to(Path(self.tmp.name)/'absent')
        self.assertFalse(self.service().status()['ready'])
        with self.assertRaises(FileExistsError):self.run_once(self.service())
        self.assertEqual(self.calls,[])

    def test_existing_nebius_records_untouched(self):
        names=['nebius-only-20261027-01.json','nebius-only-20261029-recovery-02.json']
        for name in names:(self.path.parent/name).write_text('TEST DOUBLE consumed evidence')
        self.run_once(self.service())
        for name in names:self.assertEqual((self.path.parent/name).read_text(),'TEST DOUBLE consumed evidence')

    def test_home_override_does_not_move_fixed_path(self):
        before=g.fixed_path()
        with patch.dict(os.environ,{'HOME':'/tmp/unrelated'}):self.assertEqual(g.fixed_path(),before)

    def test_concurrent_attempts_make_one_fake_call(self):
        from concurrent.futures import ThreadPoolExecutor
        def attempt(_):
            try:return self.run_once(self.service())['state']
            except FileExistsError:return 'EXISTING'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sorted(results),['COMPLETE','EXISTING']);self.assertEqual(len(self.calls),1)


class SearchHTTPTests(unittest.TestCase):
    def test_http_journey_and_cross_origin_gate(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        sys.path.insert(0,str(ROOT/'tools'))
        from serve_research import handler_for
        with tempfile.TemporaryDirectory() as tmp:
            approval=g.approval_template(g.verify_app())
            approval.update(approved=True,external_review='GO',credit_balance_confirmed=True,approved_at='2026-10-30T14:59:00Z')
            calls=[]
            def fake(*_):calls.append(1);return fixture(),200,r.ENDPOINT,'fixture-only'
            service=g.RetrievalService(approval,test_transport=fake,test_path=Path(tmp)/g.RESERVATION,test_now=datetime(2026,10,30,15,0,tzinfo=timezone.utc))
            server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            origin='http://127.0.0.1:'+str(server.server_port)
            def request(method,path,body=None,headers=None):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                conn.request(method,path,body,headers or {});response=conn.getresponse();out=(response.status,response.read());conn.close();return out
            try:
                with patch.dict(os.environ,{'PROOFOS_PUBLIC_ORIGIN':origin}):
                    status,raw=request('GET','/api/research');self.assertEqual(status,200);self.assertTrue(json.loads(raw)['ready']);self.assertEqual(calls,[])
                    for path in ['/','/research.js','/recorded-nebius-run.json']:
                        self.assertEqual(request('GET',path)[0],200)
                    payload=json.dumps({'request_sha256':r.digest(r.REQUEST)})
                    headers={'Content-Type':'application/json','Origin':origin,'X-ProofOS-Research':'prepared-search-v1'}
                    self.assertEqual(request('POST','/api/research',payload,{**headers,'Origin':'https://other.example'})[0],403)
                    self.assertEqual(request('POST','/api/research',payload,{'Content-Type':'application/json','Origin':origin})[0],403)
                    status,raw=request('POST','/api/research',payload,headers);self.assertEqual(status,200);self.assertEqual(json.loads(raw)['transport_kind'],'TEST_DOUBLE');self.assertEqual(len(calls),1)
                    self.assertEqual(request('POST','/api/research',payload,headers)[0],409);self.assertEqual(len(calls),1)
                    self.assertEqual(request('POST','/api/inference','{}',headers)[0],404)
            finally:server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()
