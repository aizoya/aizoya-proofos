import unittest,os,sys,importlib.util,threading,http.client,json
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('preview_api',ROOT/'api/review.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)

class PreviewOriginTests(unittest.TestCase):
    def test_platform_preview_origin(self):
        with patch.dict(os.environ,{'VERCEL':'1','VERCEL_ENV':'preview','VERCEL_URL':'aizoya-proofos-test.vercel.app'},clear=True):
            self.assertEqual(api.public_origin(),'https://aizoya-proofos-test.vercel.app')
    def test_no_production_or_local_auto_activation(self):
        for env in ({},{'VERCEL':'1','VERCEL_ENV':'production','VERCEL_URL':'a.vercel.app'},{'VERCEL_ENV':'preview','VERCEL_URL':'a.vercel.app'}):
            with self.subTest(env=env),patch.dict(os.environ,env,clear=True):self.assertIsNone(api.public_origin())
    def test_untrusted_or_malformed_hosts_rejected(self):
        for host in ['evil.com','a.vercel.app.evil.com','https://a.vercel.app','a.vercel.app/path','a.vercel.app:443','user@a.vercel.app','a.vercel.app?x=1','-a.vercel.app','a b.vercel.app','']:
            with self.subTest(host=host),patch.dict(os.environ,{'VERCEL':'1','VERCEL_ENV':'preview','VERCEL_URL':host},clear=True):self.assertIsNone(api.public_origin())
    def test_explicit_origin_takes_precedence(self):
        with patch.dict(os.environ,{'PROOFOS_PUBLIC_ORIGIN':'https://approved.example','VERCEL':'1','VERCEL_ENV':'preview','VERCEL_URL':'a.vercel.app'},clear=True):self.assertEqual(api.public_origin(),'https://approved.example')
    def test_invalid_explicit_origin_does_not_fall_back(self):
        with patch.dict(os.environ,{'PROOFOS_PUBLIC_ORIGIN':'javascript:bad','VERCEL':'1','VERCEL_ENV':'preview','VERCEL_URL':'a.vercel.app'},clear=True):self.assertIsNone(api.public_origin())
    def test_actual_preview_http_host_and_origin_binding(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),api.handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch.dict(os.environ,{'VERCEL':'1','VERCEL_ENV':'preview','VERCEL_URL':'aizoya-proofos-test.vercel.app'},clear=True):
                def request(origin):
                    c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    data={'claim':'Public review','url':'https://example.org','quote':'A public passage','excerpt':'A public passage'}
                    c.request('POST','/api/review',json.dumps(data),{'Host':'aizoya-proofos-test.vercel.app','Origin':origin,'Content-Type':'application/json'})
                    r=c.getresponse();out=(r.status,json.loads(r.read()));c.close();return out
                status,result=request('https://aizoya-proofos-test.vercel.app');self.assertEqual(status,200);self.assertFalse(result['fully_verified']);self.assertEqual(result['provider_calls'],0)
                status,_=request('https://attacker.example');self.assertEqual(status,403)
        finally:server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
