"""Bounded Tavily Search contract. Import and preflight perform no network I/O."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

ENDPOINT = 'https://api.tavily.com/search'
HOST = 'nebiusglobalaihackathon.devpost.com'
CLAIM = 'The hackathon submission deadline is October 30, 2026 at 10 AM Pacific.'
REQUEST = {
    'query': 'Nebius NVIDIA Global AI Hackathon 2026 submission deadline October 30 10 AM Pacific',
    'topic': 'general', 'search_depth': 'basic', 'max_results': 3,
    'include_domains': [HOST], 'include_answer': False, 'include_raw_content': False,
    'include_images': False, 'auto_parameters': False, 'include_usage': True,
    'max_age_hours': 0,
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def plan():
    return {'provider': 'Tavily Search', 'endpoint': ENDPOINT, 'request': REQUEST,
            'request_sha256': digest(REQUEST), 'max_calls': 1, 'retries': 0,
            'expected_credits': 1, 'budget_basis': 'Documented Basic Search price; not a provider-enforced billing cap',
            'inference_calls': 0, 'scope': 'Retrieve organizer search excerpts for the prepared deadline claim only'}


def strict_json(raw):
    def pairs(values):
        out = {}
        for k, v in values:
            if k in out: raise ValueError('Duplicate JSON field')
            out[k] = v
        return out
    def nonfinite(_): raise ValueError('Nonfinite JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def text(value, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(c) < 32 and c not in '\n\r\t' for c in value)):
        raise ValueError('Missing or invalid bounded provider text')
    return value.strip()


def source_url(value):
    value = text(value, 2048)
    p = urlsplit(value)
    if (p.scheme != 'https' or p.hostname != HOST or p.netloc != HOST
            or p.username or p.password or any(c.isspace() for c in value)):
        raise ValueError('Result is not an allowed organizer HTTPS link')
    return value


def validate_response(raw):
    if not isinstance(raw, dict) or raw.get('query') != REQUEST['query']:
        raise ValueError('Search response query mismatch')
    request_id = text(raw.get('request_id'), 256)
    usage = raw.get('usage')
    if not isinstance(usage, dict) or type(usage.get('credits')) is not int or usage['credits'] != 1:
        raise ValueError('Reported search credits missing or outside the one-credit plan')
    rows = raw.get('results')
    if not isinstance(rows, list) or not 1 <= len(rows) <= REQUEST['max_results']:
        raise ValueError('No usable bounded search results')
    sources, seen = [], set()
    for item in rows:
        if not isinstance(item, dict): raise ValueError('Invalid search result')
        url = source_url(item.get('url'))
        if url in seen: continue
        seen.add(url)
        content = text(item.get('content'), 12000)
        title = text(item.get('title'), 1000)
        score = item.get('score')
        if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError('Invalid relevance score')
        sources.append({'title': title, 'url': url, 'excerpt': content,
                        'excerpt_sha256': hashlib.sha256(content.encode()).hexdigest(),
                        'score': score, 'provenance': 'Tavily Search excerpt; not direct page authentication',
                        'publication_date': None})
    return {'request_id': request_id, 'reported_credits': usage['credits'], 'sources': sources}


def response_evidence(body, status, raw_sha256=None):
    result = {'http_status': status, 'request_id': None, 'reported_credits': None,
              'raw_response_sha256': raw_sha256, 'response': body}
    if isinstance(body, dict):
        request_id = body.get('request_id')
        if isinstance(request_id, str): result['request_id'] = request_id[:256]
        usage = body.get('usage')
        if isinstance(usage, dict) and type(usage.get('credits')) is int:
            result['reported_credits'] = usage['credits']
    return result


class TransportFailure(RuntimeError):
    def __init__(self, evidence):
        super().__init__('Search outcome requires reconciliation; do not retry')
        self.evidence = evidence


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TransportFailure({'http_status': code, 'parse_status': 'REDIRECT_BLOCKED'})


def provider_request(request, key):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    req = Request(ENDPOINT, data=json.dumps(request, allow_nan=False).encode(), method='POST',
                  headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
    try:
        with opener.open(req, timeout=30) as response:
            status, endpoint, raw = response.status, response.geturl(), response.read(262145)
    except HTTPError as exc:
        status, endpoint = exc.code, ENDPOINT
        raw = exc.read(262145)
        exc.close()
    if len(raw) > 262144:
        raise TransportFailure({'http_status': status, 'parse_status': 'RESPONSE_TOO_LARGE'})
    raw_hash = hashlib.sha256(raw).hexdigest()
    try: body = strict_json(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise TransportFailure({'http_status': status, 'parse_status': 'INVALID_JSON', 'raw_response_sha256': raw_hash})
    return body, status, endpoint, raw_hash
