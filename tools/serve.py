"""Local test adapter for the exact function and static assets; no Vercel emulation."""
import argparse
import importlib.util
from http.server import ThreadingHTTPServer
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('review_api',ROOT/'api/review.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)


class LocalHandler(api.handler):
    def do_GET(self):
        static={'/':'index.html','/evidence':'index.html','/style.css':'style.css','/workspace.css':'workspace.css','/workspace.js':'workspace.js','/inference.js':'inference.js','/recorded.js':'recorded.js','/recorded-nebius-run.json':'recorded-nebius-run.json'}
        if self.path not in static:return super().do_GET()
        file=ROOT/'public'/static[self.path]
        mime='application/json' if file.suffix=='.json' else 'text/html' if file.suffix=='.html' else 'text/css' if file.suffix=='.css' else 'application/javascript'
        data=file.read_bytes();self.send_response(200)
        self.send_header('Content-Type',mime+'; charset=utf-8');self.send_header('Content-Length',str(len(data)))
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8766);args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),LocalHandler)
    os.environ['PROOFOS_PUBLIC_ORIGIN']='http://127.0.0.1:'+str(server.server_port)
    print('ProofOS source review: '+os.environ['PROOFOS_PUBLIC_ORIGIN'],flush=True)
    try:server.serve_forever()
    finally:server.server_close()
