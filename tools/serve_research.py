"""Owner-local Tavily bridge. No approval file means no live provider capability."""
import argparse
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrieval_guard import RetrievalService, approval_template
from inference_bridge import verify_app
from retrieval import strict_json, plan
from serve import LocalHandler


def handler_for(service):
    class Handler(LocalHandler):
        def do_GET(self):
            if self.path == '/api/research': return self.send_json(200, service.status())
            return super().do_GET()

        def do_POST(self):
            if self.path != '/api/research': return super().do_POST()
            expected = os.getenv('PROOFOS_PUBLIC_ORIGIN')
            if (not expected or self.headers.get('Origin') != expected
                    or self.headers.get('Host') != urlsplit(expected).netloc
                    or self.headers.get('Sec-Fetch-Site') not in (None, 'none', 'same-origin')
                    or self.headers.get('X-ProofOS-Research') != 'prepared-search-v1'):
                return self.send_json(403, {'error': 'Same-origin prepared search required'})
            if (self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json'
                    or self.headers.get('Transfer-Encoding')
                    or len(self.headers.get_all('Content-Length', [])) != 1):
                return self.send_json(400, {'error': 'One bounded JSON request required'})
            try:
                size = int(self.headers['Content-Length'])
                if not 0 < size <= 256: raise ValueError('Request too large')
                payload = strict_json(self.rfile.read(size))
                result = service.run(payload)
            except (PermissionError, FileExistsError):
                return self.send_json(409, {'error': 'Search is locked or consumed. Reconcile; do not retry.'})
            except (ValueError, TypeError, UnicodeError):
                return self.send_json(422, {'error': 'Only the exact approved prepared search is allowed'})
            except Exception:
                return self.send_json(500, {'error': 'Outcome uncertain. Preserve terminal evidence and reservation; do not retry.'})
            return self.send_json(200, result)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--approval-file', type=Path)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    release_id = verify_app()
    if args.preflight:
        print(json.dumps({'status': 'PREFLIGHT_ONLY', 'release_id': release_id,
                          'plan': plan(), 'approval_template': approval_template(release_id),
                          'provider_calls': 0, 'ledger_writes': 0}, indent=2))
    else:
        approval = strict_json(args.approval_file.read_bytes()) if args.approval_file else None
        service = RetrievalService(approval)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(service))
        os.environ['PROOFOS_PUBLIC_ORIGIN'] = 'http://127.0.0.1:'+str(server.server_port)
        print(json.dumps({'url': os.environ['PROOFOS_PUBLIC_ORIGIN'], 'inference_calls': 0,
                          'startup_provider_calls': 0, 'retrieval': service.status()}), flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
