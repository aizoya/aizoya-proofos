"""New, separately authorized Nebius-only run; old smoke ledger is never opened."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
import pwd
import sys
import tempfile
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
import time
from urllib.error import HTTPError
from dataclasses import dataclass
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from analysis_contract import MODEL, prepare_analysis, validate_analysis

ENDPOINT = 'https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions'
AUTHORITY = 'proofos:nebius-only:2026-10-29:credential-recovery:02'
PRIOR_NAME = 'nebius-only-20261027-01.json'
RECOVERY_NAME = 'nebius-only-20261029-recovery-02.json'
PRIOR_RECEIPT_SHA256 = 'd043a7dff6aa78305323696c04518e3289ea98afb8584c33f1ff3c566cc9c2df'
PRIOR_MANIFEST_SHA256 = 'd86ea819ebcb593ab3a923508f5a022564b44479bb0ee9bf9164cb8cc4149460'
PAYLOAD = {
    'claim': 'The hackathon submission deadline is October 30, 2026 at 10 AM Pacific.',
    'quote': 'Submissions are due Friday, October 30 at 10:00 AM PT.',
    'excerpt': 'Submissions are due Friday, October 30 at 10:00 AM PT.',
    'url': 'https://nebiusglobalaihackathon.devpost.com/updates/46207-final-stretch-here-s-your-submission-checklist',
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bound_plan():
    request, receipt = prepare_analysis(PAYLOAD)
    return {'authority': AUTHORITY, 'endpoint': ENDPOINT, 'model': MODEL,
            'request_sha256': digest(request), 'input_sha256': receipt['evidence']['input_sha256'],
            'max_cost_usd': '0.05', 'max_output_tokens': 1024, 'max_calls': 1, 'retries': 0,
            'expires_at': '2026-10-30T14:00:00+00:00',
            'approved_at': json.loads(Path(__file__).with_name('APPROVAL_RECORD.json').read_text())['recorded_at_utc'],
            'approval_record_sha256': hashlib.sha256(Path(__file__).with_name('APPROVAL_RECORD.json').read_bytes()).hexdigest(),
            'budget_basis': 'estimate_not_provider_cap', 'timeout_basis': 'per_io_not_total',
            'prior_receipt_sha256': PRIOR_RECEIPT_SHA256,
            'prior_reservation': PRIOR_NAME, 'recovery_reservation': RECOVERY_NAME}


def verify_sources():
    manifest = json.loads(Path(__file__).with_name('run-manifest.json').read_text())
    if manifest.get('plan') != bound_plan():
        raise ValueError('Plan binding mismatch')
    files = manifest['files']
    if set(files) != {'run_once.py', 'analysis_contract.py', 'core.py'}:
        raise ValueError('Source mapping mismatch')
    for name, expected in files.items():
        if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != expected:
            raise ValueError('Source binding mismatch')
    return manifest


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderFailure({'http_status':code,'parse_status':'REDIRECT_BLOCKED'})


@dataclass
class ProviderReply:
    body: object
    status: int
    endpoint: str


class ProviderFailure(RuntimeError):
    def __init__(self, evidence):
        super().__init__('Provider response could not be parsed')
        self.evidence = evidence


def provider_request(request, key):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    body = json.dumps(request, allow_nan=False).encode()
    req = Request(ENDPOINT, data=body, headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'}, method='POST')
    try:
        response = opener.open(req, timeout=30)
    except HTTPError as exc:
        response = exc
    with response:
        status = response.status
        endpoint = response.geturl()
        try:
            raw = response.read(262145)
        except Exception as exc:
            raise ProviderFailure({'http_status':status,'parse_status':'READ_FAILED','error_type':type(exc).__name__}) from None
    if len(raw) > 262144:
        raise ProviderFailure({'http_status':status,'response_bytes':len(raw),'parse_status':'OVERSIZED'})
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result: raise ValueError('Duplicate response field')
            result[k] = v
        return result
    def nonfinite(_): raise ValueError('Nonfinite provider response')
    try:
        parsed = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (ValueError, UnicodeError, RecursionError):
        raise ProviderFailure({'http_status':status,'response_bytes':len(raw),'body_sha256':hashlib.sha256(raw).hexdigest(),'parse_status':'INVALID_JSON'}) from None
    return ProviderReply(parsed, status, endpoint)


def fixed_ledger_path():
    # Account database, never HOME/Path.home(), controls the live run location.
    return Path(pwd.getpwuid(os.getuid()).pw_dir)/'.aizoya/proofos'/RECOVERY_NAME


def credential_format_ready(key):
    return (isinstance(key, str) and 1 <= len(key) <= 512 and key.isascii()
            and all(33 <= ord(c) <= 126 for c in key)
            and not key.startswith('serviceaccount-') and '*' not in key
            and not key.startswith(('"', "'")) and not key.endswith(('"', "'")))


def read_prior(directory_fd):
    """Read only the consumed, private R4 record, through the pinned directory."""
    receipt_bytes = Path(__file__).with_name('PRIOR_RECEIPT.json').read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != PRIOR_RECEIPT_SHA256:
        raise ValueError('Prior receipt binding mismatch')
    receipt = json.loads(receipt_bytes)
    fd = os.open(PRIOR_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size > 65536):
            raise PermissionError('Prior reservation must be a private owner regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(65537)
    finally:
        os.close(fd)
    if len(raw) > 65536: raise ValueError('Prior reservation exceeds bound')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result: raise ValueError('Duplicate prior state field')
            result[k] = v
        return result
    def nonfinite(_): raise ValueError('Nonfinite prior state')
    prior = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    if (not isinstance(prior, dict) or prior.get('state') != 'UNCERTAIN'
            or prior.get('final_status') != 'BLOCKED' or prior.get('fully_verified') is not False
            or type(prior.get('provider_calls')) is not int or prior['provider_calls'] != 1
            or prior.get('transport_kind') != 'NEBIUS_HTTPS'
            or prior.get('manifest_sha256') != PRIOR_MANIFEST_SHA256
            or prior.get('plan') != receipt['plan']
            or prior.get('provider_evidence') != receipt['provider_evidence']
            or prior.get('started_at') != receipt['started_at']
            or prior.get('finished_at') != receipt['finished_at']
            or prior.get('priced_usage_usd') is not None):
        raise PermissionError('Prior reservation does not match the recorded 401 attempt')
    return {'prior_record_sha256': hashlib.sha256(raw).hexdigest(),
            'prior_receipt_sha256': PRIOR_RECEIPT_SHA256,
            'prior_task_id': receipt['task_id'], 'prior_http_status': 401,
            'prior_cost_basis': 'Unknown; additional budget does not assert zero prior cost'}


def check_prior(path, *, test_mode=False):
    trusted_root = path.parent if test_mode else fixed_ledger_path().parents[2]
    with pin_directory(path.parent, trusted_root, test_mode=test_mode) as directory_fd:
        return read_prior(directory_fd)


def verify_candidate(expected=None):
    root = Path(__file__).resolve().parent
    candidate = json.loads((root/'candidate.json').read_text())
    identity = candidate['identity']
    actual = 'sha256:'+digest(identity)
    if candidate['candidate_id'] != actual or (expected is not None and expected != actual):
        raise ValueError('Reviewed candidate identity mismatch')
    for name, expected_hash in identity['files'].items():
        path = root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError('Reviewed candidate source mismatch')
    return actual


def fsync_directory(directory):
    fd = os.open(directory, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


@contextmanager
def pin_directory(path, trusted_root, *, test_mode=False):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if not path.is_absolute() or not path.is_relative_to(trusted_root):
        raise ValueError('Ledger directory outside trusted owner root')
    fd = os.open('/', flags)
    try:
        current = Path('/')
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd); fd = child; current /= part
            info = os.fstat(fd)
            inside = current == trusted_root or current.is_relative_to(trusted_root)
            if inside:
                if info.st_uid != os.getuid(): raise PermissionError('Ledger directory is not owned by this account')
                forbidden = 0o022 if current == trusted_root else 0o077
                if stat.S_IMODE(info.st_mode) & forbidden: raise PermissionError('Unsafe ledger directory permissions')
            elif not test_mode:
                if info.st_uid not in (0, os.getuid()) or stat.S_IMODE(info.st_mode) & 0o022:
                    raise PermissionError('Unsafe trusted-root ancestry')
        yield fd
    finally:
        os.close(fd)


def write_state(path, state, *, directory_fd=None):
    owns_fd = directory_fd is None
    if owns_fd: directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    name = path.name+'.'+secrets.token_hex(16)+'.tmp'
    created = False
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        created = True
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        created = False
        os.fsync(directory_fd)
    finally:
        if created:
            try: os.unlink(name, dir_fd=directory_fd)
            except OSError: pass
        if owns_fd: os.close(directory_fd)


def response_evidence(raw, status, key):
    # Only reconciliation fields; never persist body, headers or credentials.
    def bounded(value):
        return value.replace(key, '[REDACTED]')[:256] if isinstance(value, str) else None
    evidence = {'http_status':status,'response_id':None,'model':None,'finish_reasons':[],'usage':None}
    if not isinstance(raw, dict): return evidence
    evidence.update(response_id=bounded(raw.get('id')), model=bounded(raw.get('model')))
    if isinstance(raw.get('choices'), list):
        evidence['finish_reasons'] = [bounded(item.get('finish_reason')) for item in raw['choices'][:4] if isinstance(item, dict)]
    if isinstance(raw.get('usage'), dict):
        evidence['usage'] = {k:raw['usage'][k] for k in ('prompt_tokens','completion_tokens','total_tokens') if type(raw['usage'].get(k)) is int and raw['usage'][k]>=0}
    return evidence


def redact(value, key):
    if isinstance(value, str): return value.replace(key, '[REDACTED]')
    if isinstance(value, dict): return {k:redact(v,key) for k,v in value.items()}
    if isinstance(value, list): return [redact(v,key) for v in value]
    return value


def validate_response(raw):
    if not isinstance(raw, dict) or raw.get('model') != MODEL:
        raise ValueError('Provider model mismatch')
    if not isinstance(raw.get('id'), str) or not 1 <= len(raw['id']) <= 256:
        raise ValueError('Provider response identity missing')
    choices = raw['choices']
    if not isinstance(choices, list) or len(choices) != 1 or choices[0]['finish_reason'] != 'stop':
        raise ValueError('Incomplete provider completion')
    message = choices[0]['message']
    if message.get('tool_calls') or message.get('refusal'):
        raise ValueError('Unsupported provider response')
    analysis = validate_analysis(message['content'], PAYLOAD)
    usage = raw['usage']
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('prompt_tokens','completion_tokens','total_tokens')):
        raise ValueError('Provider usage missing or invalid')
    if usage['total_tokens'] != usage['prompt_tokens'] + usage['completion_tokens'] or usage['completion_tokens'] > 1024:
        raise ValueError('Provider token accounting mismatch')
    priced = (Decimal(usage['prompt_tokens'])*Decimal('0.30') + Decimal(usage['completion_tokens'])*Decimal('0.90')) / Decimal(1000000)
    if priced > Decimal('0.05'):
        raise ValueError('Observed usage exceeds reserved budget')
    return analysis, {k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens')}, str(priced)


def execute(ledger_path, key, *, now=None, test_transport=None, expected_candidate=None):
    manifest = verify_sources()
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current >= datetime.fromisoformat(bound_plan()['expires_at']):
        raise PermissionError('New authorization expired')
    if current < datetime.fromisoformat(bound_plan()['approved_at']):
        raise PermissionError('Authorization not yet valid')
    if not credential_format_ready(key):
        raise ValueError('Supply the full secret privately; service-account IDs and masked values are not keys')
    path = Path(ledger_path)
    if test_transport is None and path != fixed_ledger_path():
        raise ValueError('Live execution requires the fixed owner-home ledger path')
    if path.name != RECOVERY_NAME or any(parent.is_symlink() for parent in path.parents) or not path.parent.is_dir():
        raise ValueError('Use the dedicated run ledger filename in an existing private directory')
    if test_transport is None:
        if expected_candidate is None: raise ValueError('Explicit reviewed candidate ID required')
        verify_candidate(expected_candidate)
    trusted_root = path.parent if test_transport else fixed_ledger_path().parents[2]
    with pin_directory(path.parent, trusted_root, test_mode=test_transport is not None) as directory_fd:
        prior_binding = read_prior(directory_fd)
        # Single fixed basename plus exclusive creation prevents restart and race retries
        # within this chosen persistent directory. Never use serverless ephemeral storage.
        state = {'plan': bound_plan(), 'manifest_sha256': digest(manifest), 'state': 'IN_FLIGHT',
                 'started_at': current.isoformat(), 'fully_verified': False,
                 'transport_kind': 'TEST_DOUBLE' if test_transport else 'NEBIUS_HTTPS',
                 'recovery_of': prior_binding}
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f, indent=2); f.flush(); os.fsync(f.fileno())
        os.fsync(directory_fd)
        request, _ = prepare_analysis(PAYLOAD)
        start = time.perf_counter()
        try:
            reply = (test_transport or provider_request)(request, key)
            if isinstance(reply, ProviderReply):
                raw, status, endpoint = reply.body, reply.status, reply.endpoint
            else:
                raw, status, endpoint = reply, 200, ENDPOINT
            state['provider_evidence'] = response_evidence(raw, status, key)
            # Durable checkpoint BEFORE schema/model/finish validation can reject output.
            write_state(path, state, directory_fd=directory_fd)
            if status != 200 or endpoint != ENDPOINT:
                raise ValueError('Provider endpoint or status mismatch')
            analysis, usage, priced = validate_response(raw)
            state.update(state='COMPLETE', final_status='NEEDS_REVIEW', model=raw['model'], response_id=raw['id'],
                         analysis=analysis, usage=usage, priced_usage_usd=priced,
                         cost_basis='Estimate from observed tokens and displayed regional rates; final invoice and taxes unverified',
                         source=PAYLOAD, provider_calls=0 if test_transport else 1)
        except Exception as exc:
            if isinstance(exc, ProviderFailure): state['provider_evidence'] = exc.evidence
            # An attempted request consumes this run even if its outcome/cost is unknown.
            state.update(state='UNCERTAIN', final_status='BLOCKED', error_type=type(exc).__name__,
                         provider_calls=0 if test_transport else 1, priced_usage_usd=None,
                         recommended_next_action='Reconcile this attempt; do not retry or create another ledger.')
        state['elapsed_ms'] = round((time.perf_counter()-start)*1000, 3)
        state['finished_at'] = datetime.now(timezone.utc).isoformat()
        state = redact(state, key)
        try:
            write_state(path, state, directory_fd=directory_fd)
        except Exception:
            # Never silently lose received evidence when persistence fails.
            print(json.dumps({'terminal_persistence':'FAILED','recommended_next_action':'Outcome uncertain; do not retry. Reconcile retained reservation and this terminal state.','state':state}),file=sys.stderr,flush=True)
            raise
        return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-approved', action='store_true')
    parser.add_argument('--expected-candidate')
    args = parser.parse_args()
    verify_sources()
    identity = verify_candidate(args.expected_candidate)
    if not args.execute_approved:
        print(json.dumps({'status':'PREFLIGHT_ONLY', 'candidate_id':identity, 'plan':bound_plan(), 'provider_calls':0, 'ledger_writes':0},indent=2))
        return 0
    result = execute(fixed_ledger_path(), os.getenv('NEBIUS_API_KEY'),expected_candidate=args.expected_candidate)
    print(json.dumps({'state':result['state'], 'final_status':result['final_status'], 'fully_verified':False}))
    return 0 if result['state'] == 'COMPLETE' else 2


if __name__ == '__main__':
    raise SystemExit(main())
