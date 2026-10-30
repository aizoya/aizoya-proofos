"""Stateless source-review Vercel function. No AI, storage, or authority path."""
from http.server import BaseHTTPRequestHandler
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import review_source


def release():
    record = json.loads((ROOT/'release.json').read_text())
    if not isinstance(record, dict) or not isinstance(record.get('files'), dict):
        raise RuntimeError('Release manifest shape invalid')
    encoded = json.dumps(record['files'], sort_keys=True, separators=(',', ':')).encode()
    if record['release_id'] != 'sha256:'+hashlib.sha256(encoded).hexdigest():
        raise RuntimeError('Release manifest mismatch')
    for name in ('core.py', 'api/review.py'):
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != record['files'][name]:
            raise RuntimeError('Release source mismatch')
    return record


def public_origin():
    value = os.environ.get('PROOFOS_PUBLIC_ORIGIN', '')
    if not value and os.environ.get('VERCEL') == '1' and os.environ.get('VERCEL_ENV') == 'preview':
        host = os.environ.get('VERCEL_URL', '')
        if re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.vercel\.app', host):
            value = 'https://' + host
    try:
        p = urlsplit(value)
        if not p.hostname or p.username or p.password or p.path or p.query or p.fragment or any(x.isspace() for x in value):
            return None
        if p.scheme != 'https' and not (p.scheme=='http' and p.hostname=='127.0.0.1'):
            return None
        p.port  # Reject malformed port before request handling.
        return value
    except ValueError:
        return None


class handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never emit source material, cookies or request bodies to app logs.

    def send_json(self, status, data):
        raw=json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'")
        self.send_header('Connection','close')
        self.end_headers(); self.wfile.write(raw); self.close_connection=True

    def do_GET(self):
        if self.path != '/api/review':
            return self.send_json(404,{'error':'Not found'})
        try:
            build=release()
        except (OSError, ValueError, KeyError, RuntimeError):
            return self.send_json(503,{'error':'Release binding unavailable'})
        return self.send_json(200,{
            'release_id':build['release_id'],
            'source_candidate_id':build['source_candidate_id'],
            'ready':bool(public_origin()),
            'operation':'Quotation comparison against operator-supplied public text',
            'engine':'Python deterministic text comparison and SHA-256 input binding',
            'inference':'NOT_RUN', 'model_id':None,
            'hosting_target':'Vercel Python Functions; deployment acceptance is separate',
            'stores_source_text':False, 'provider_calls_per_review':0,
        })

    def do_POST(self):
        started=time.perf_counter()
        if self.path != '/api/review':
            return self.send_json(404,{'error':'Not found'})
        expected=public_origin()
        if not expected:
            return self.send_json(503,{'error':'Review service awaits approved origin configuration'})
        if self.headers.get('Origin')!=expected or self.headers.get('Host')!=urlsplit(expected).netloc or self.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'):
            return self.send_json(403,{'error':'Same-origin review required'})
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
            return self.send_json(415,{'error':'JSON required'})
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', []))!=1:
            return self.send_json(400,{'error':'One bounded content length required'})
        try:
            size=int(self.headers['Content-Length'])
            if not 0<size<=49152:
                return self.send_json(413,{'error':'Use at most 48 KiB of public material'})
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict):raise ValueError
        except (ValueError,UnicodeError):
            return self.send_json(400,{'error':'Valid JSON object required'})
        try:
            build=release()
        except (OSError,ValueError,KeyError,RuntimeError):
            return self.send_json(503,{'error':'Release binding unavailable'})
        try:
            result=review_source(body,candidate_id=build['source_candidate_id'])
        except ValueError:
            return self.send_json(422,{'error':'Supply bounded text and an HTTPS source link without credentials'})
        result['release_id']=build['release_id']
        result['server_processing_ms']=round((time.perf_counter()-started)*1000,3)
        result['timing_basis']='Measured application processing time; excludes browser transit and any provider inference.'
        return self.send_json(200,result)

    def do_OPTIONS(self):
        return self.send_json(405,{'error':'Cross-origin requests are not enabled'})
