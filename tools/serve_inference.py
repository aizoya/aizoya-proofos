"""Same app, loopback owner runtime. No provider request at startup. Default locked."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inference_bridge import InferenceService, verify_app
spec=importlib.util.spec_from_file_location('local_preview_server', ROOT/'tools/serve.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def make_handler(service, origin):
    class OwnerHandler(base.LocalHandler):
        def do_GET(self):
            if self.path!='/api/inference':return super().do_GET()
            try:return self.send_json(200,service.status())
            except Exception:return self.send_json(503,{'ready':False,'reason':'Inference source binding unavailable.'})

        def do_POST(self):
            if self.path!='/api/inference':return super().do_POST()
            if (self.headers.get('Host')!=origin.removeprefix('http://') or self.headers.get('Origin')!=origin
                or self.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none')
                or self.headers.get('X-ProofOS-Inference')!='owner-local'):
                return self.send_json(403,{'error':'Owner-local same-origin request required.'})
            if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
                return self.send_json(415,{'error':'JSON required.'})
            try:
                if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:
                    raise ValueError
                size=int(self.headers['Content-Length'])
                if not 0<size<=4096:return self.send_json(413,{'error':'One bounded sample required.'})
                def unique(pairs):
                    value={}
                    for key,item in pairs:
                        if key in value:raise ValueError
                        value[key]=item
                    return value
                payload=json.loads(self.rfile.read(size),object_pairs_hook=unique)
            except (ValueError,UnicodeError):return self.send_json(400,{'error':'Valid bounded JSON required.'})
            try:result=service.run(payload)
            except PermissionError as exc:return self.send_json(409,{'error':str(exc),'fully_verified':False})
            except FileExistsError:return self.send_json(409,{'error':'Reservation exists. Reconcile; do not retry.','fully_verified':False})
            except ValueError:return self.send_json(422,{'error':'Bound sample or source validation failed.','fully_verified':False})
            except Exception:return self.send_json(500,{'error':'Outcome uncertain. Reconcile the existing run; do not retry.','fully_verified':False})
            return self.send_json(200,result)
    return OwnerHandler


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--port',type=int,default=8766)
    p.add_argument('--reviewed-app')
    p.add_argument('--reviewed-guard')
    args=p.parse_args()
    identity=verify_app()
    service=InferenceService(reviewed_app=args.reviewed_app,reviewed_guard=args.reviewed_guard)
    origin='http://127.0.0.1:'+str(args.port)
    os.environ['PROOFOS_PUBLIC_ORIGIN']=origin
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(service,origin))
    print(json.dumps({'url':origin,'release_id':identity,'inference':service.status(),'startup_provider_calls':0}),flush=True)
    try:server.serve_forever()
    finally:server.server_close()
