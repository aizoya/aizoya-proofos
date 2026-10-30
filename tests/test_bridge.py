import http.client
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inference_bridge import InferenceService, guard, verify_app, GUARD_ID
from test_fixtures import seed_prior
spec=importlib.util.spec_from_file_location('owner_server',ROOT/'tools/serve_inference.py')
owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
NOW=datetime.fromisoformat(guard.bound_plan()['approved_at'])


def response():
    return {'id':'offline-test-response','model':guard.MODEL,
            'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
                'verdict':'SUPPORTED','explanation':'The saved passage states the deadline.',
                'evidence_quote':guard.PAYLOAD['quote']})}}],
            'usage':{'prompt_tokens':500,'completion_tokens':100,'total_tokens':600}}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name).resolve()/guard.RECOVERY_NAME
        seed_prior(self.path.parent)
        self.calls=[]

    def service(self,transport=None):
        def fake(*_):self.calls.append(1);return response()
        return InferenceService(test_transport=transport or fake,test_path=self.path,test_now=NOW)

    def test_locked_default_never_inspects_owner_ledger_or_calls_provider(self):
        with patch.object(guard,'fixed_ledger_path',side_effect=AssertionError('Owner ledger accessed')),patch.object(guard,'provider_request',side_effect=AssertionError('Network called')):
            self.assertFalse(InferenceService().status()['ready'])
            with self.assertRaises(PermissionError):InferenceService().run(dict(guard.PAYLOAD))
        self.assertFalse(self.path.exists())

    def test_exact_app_and_guard_id_required_even_before_expiry(self):
        clock=type('Clock',(),{'now':staticmethod(lambda *_:NOW),'fromisoformat':staticmethod(datetime.fromisoformat)})
        with patch('inference_bridge.datetime',clock):
            service=InferenceService(reviewed_app='wrong',reviewed_guard=GUARD_ID)
            self.assertIn('locked',service.status()['reason'])

    def test_changed_or_extra_input_never_reserves_or_calls(self):
        for value in ({**guard.PAYLOAD,'claim':'different'},{**guard.PAYLOAD,'extra':True},[]):
            with self.assertRaises(ValueError):self.service().run(value)
        self.assertEqual(self.calls,[]);self.assertFalse(self.path.exists())

    def test_complete_roundtrip_has_bound_test_evidence_and_persistent_record(self):
        data=self.service().run(dict(guard.PAYLOAD))
        self.assertEqual(self.calls,[1]);self.assertEqual(data['release_id'],verify_app())
        self.assertEqual(data['execution_evidence'],'TEST_DOUBLE');self.assertEqual(data['provider_calls'],0)
        self.assertEqual(data['final_status'],'NEEDS_REVIEW');self.assertFalse(data['fully_verified'])
        self.assertEqual(data['usage']['total_tokens'],600)
        self.assertEqual(data['source_review']['evidence']['input_sha256'],guard.bound_plan()['input_sha256'])
        stored=json.loads(self.path.read_text());self.assertEqual(stored['state'],'COMPLETE')
        self.assertNotIn('offline-dummy-key',json.dumps(data))

    def test_second_http_or_service_attempt_is_blocked(self):
        service=self.service();service.run(dict(guard.PAYLOAD))
        with self.assertRaises(PermissionError):service.run(dict(guard.PAYLOAD))
        self.assertEqual(self.calls,[1])

    def test_provider_failure_is_blocked_and_retained_not_fabricated(self):
        def fail(*_):self.calls.append(1);raise TimeoutError('PRIVATE ERROR CONTENT')
        data=self.service(fail).run(dict(guard.PAYLOAD))
        self.assertEqual(data['final_status'],'BLOCKED');self.assertEqual(data['run_state'],'UNCERTAIN')
        self.assertIsNone(data['model_analysis']);self.assertIsNone(data['priced_usage_usd'])
        self.assertIn('do not retry',data['recommended_next_action'])
        self.assertNotIn('PRIVATE ERROR CONTENT',json.dumps(data))
        self.assertEqual(json.loads(self.path.read_text())['state'],'UNCERTAIN')

    def test_rejected_completion_retains_response_identity(self):
        def length(*_):
            raw=response();raw['choices'][0]['finish_reason']='length';return raw
        data=self.service(length).run(dict(guard.PAYLOAD))
        self.assertEqual(data['final_status'],'BLOCKED')
        self.assertEqual(data['provider_evidence']['response_id'],'offline-test-response')
        self.assertEqual(data['response_id'],'offline-test-response')
        self.assertEqual(data['usage']['total_tokens'],600)
        self.assertEqual(data['provider_evidence']['usage']['total_tokens'],600)

    def test_source_integrity_checks_full_app_and_frozen_guard(self):
        self.assertTrue(verify_app().startswith('sha256:'))
        self.assertEqual(guard.verify_candidate(),GUARD_ID)

    def test_real_http_roundtrip_and_rejections(self):
        service=self.service()
        server=ThreadingHTTPServer(('127.0.0.1',0),BaseHTTPRequestHandler)
        origin='http://127.0.0.1:'+str(server.server_port)
        server.RequestHandlerClass=owner.make_handler(service,origin)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(payload=None,extra=None,raw=None,method='POST'):
            headers={'Content-Type':'application/json','Origin':origin,'X-ProofOS-Inference':'owner-local','Sec-Fetch-Site':'same-origin'}
            headers.update(extra or {})
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                conn.request(method,'/api/inference',raw if raw is not None else json.dumps(payload or guard.PAYLOAD) if method=='POST' else None,headers)
                result=conn.getresponse();data=json.loads(result.read());self.assertEqual(result.getheader('Cache-Control'),'no-store');return result.status,data
            finally:conn.close()
        try:
            self.assertEqual(request(method='GET')[0],200)
            self.assertEqual(request(extra={'Origin':'https://attacker.example'})[0],403)
            self.assertEqual(request(extra={'Sec-Fetch-Site':'same-site'})[0],403)
            self.assertEqual(request(extra={'X-ProofOS-Inference':''})[0],403)
            self.assertEqual(request(raw='{"claim":1,"claim":2}')[0],400)
            self.assertEqual(request(raw=' '*4097)[0],413)
            self.assertEqual(request(payload={**guard.PAYLOAD,'claim':'changed'})[0],422)
            self.assertEqual(self.calls,[])
            status,data=request();self.assertEqual(status,200)
            self.assertEqual(data['execution_evidence'],'TEST_DOUBLE')
            self.assertEqual(request()[0],409);self.assertEqual(self.calls,[1])
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

    def test_explicit_expired_clock_blocks_service(self):
        service=self.service()
        service.test_now=datetime(2026,10,30,14,tzinfo=timezone.utc)
        with patch.object(guard,'provider_request',side_effect=AssertionError('Network called')):
            with self.assertRaisesRegex(PermissionError,'expired'):service.run(dict(guard.PAYLOAD))
        self.assertFalse(self.path.exists())


if __name__=='__main__':unittest.main()
