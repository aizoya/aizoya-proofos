"""Separate Tavily authority. Existing Nebius reservations are never opened or reset."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import sys
import time
from uuid import uuid4
from inference_bridge import guard, verify_app
import retrieval

AUTHORITY = 'proofos:tavily-search:2026-10-30:01'
RESERVATION = 'tavily-search-20261030-01.json'
DEADLINE = datetime.fromisoformat('2026-10-30T17:00:00+00:00')


def fixed_path():
    return Path(pwd.getpwuid(os.getuid()).pw_dir)/'.aizoya/proofos'/RESERVATION


def approval_template(release_id):
    return {'approved': False, 'authority': AUTHORITY, 'release_id': release_id,
            'plan_sha256': retrieval.digest(retrieval.plan()), 'max_calls': 1, 'max_credits': 1,
            'retries': 0, 'approved_at': None, 'expires_at': DEADLINE.isoformat(),
            'external_review': 'PENDING', 'credit_balance_confirmed': False,
            'paid_overage_authorized': False}


def check_approval(record, release_id, now):
    if not isinstance(record, dict): raise PermissionError('A fresh owner approval is required')
    expected = approval_template(release_id)
    for name in ('authority', 'release_id', 'plan_sha256', 'max_calls', 'max_credits', 'retries', 'expires_at'):
        if type(record.get(name)) is not type(expected[name]) or record[name] != expected[name]:
            raise PermissionError('Approval does not match this exact retrieval plan')
    if (record.get('approved') is not True or record.get('credit_balance_confirmed') is not True
            or record.get('paid_overage_authorized') is not False or record.get('external_review') != 'GO'):
        raise PermissionError('Owner credit-only approval and exact-candidate review remain required')
    try: start = datetime.fromisoformat(record['approved_at'])
    except (ValueError, TypeError, KeyError): raise PermissionError('Approval time missing')
    if start.tzinfo is None or now.tzinfo is None or not start <= now < DEADLINE:
        raise PermissionError('Retrieval approval is outside its execution window')


class RetrievalService:
    def __init__(self, approval=None, *, test_transport=None, test_path=None, test_now=None):
        self.approval = approval
        self.test_transport = test_transport
        self.test_path = test_path
        self.test_now = test_now

    def context(self):
        release_id = verify_app()
        now = self.test_now if self.test_transport is not None else datetime.now(timezone.utc)
        check_approval(self.approval, release_id, now)
        key = os.getenv('TAVILY_API_KEY', '')
        if self.test_transport is None and (not key.startswith('tvly-') or not guard.credential_format_ready(key)):
            raise PermissionError('Set the full Tavily API secret privately in this shell')
        path = self.test_path if self.test_transport is not None else fixed_path()
        trusted = path.parent if self.test_transport is not None else Path(pwd.getpwuid(os.getuid()).pw_dir)
        return release_id, now, key, path, trusted

    def status(self):
        reason = None
        try:
            release_id, _, _, path, trusted = self.context()
            with guard.pin_directory(path.parent, trusted, test_mode=self.test_transport is not None) as directory_fd:
                try: os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
                except FileNotFoundError: pass
                else: raise PermissionError('This retrieval attempt is reserved or consumed. Do not retry.')
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            reason = str(exc)
            release_id = None
        return {'ready': reason is None, 'reason': reason, 'release_id': release_id,
                'plan': retrieval.plan(), 'mode': 'TEST_DOUBLE' if self.test_transport is not None else 'OWNER_LOCAL',
                'provider_calls': 0, 'fully_verified': False}

    def run(self, payload):
        if payload != {'request_sha256': retrieval.digest(retrieval.REQUEST)}:
            raise ValueError('Only the exact prepared organizer search is eligible')
        release_id, now, key, path, trusted = self.context()
        if path.name != RESERVATION: raise PermissionError('Fixed retrieval reservation required')
        with guard.pin_directory(path.parent, trusted, test_mode=self.test_transport is not None) as directory_fd:
            state = {'schema': 'proofos.retrieval.v1', 'task_id': str(uuid4()), 'release_id': release_id,
                     'authority': AUTHORITY, 'plan': retrieval.plan(), 'claim': retrieval.CLAIM,
                     'state': 'IN_FLIGHT', 'final_status': 'BLOCKED', 'fully_verified': False,
                     'started_at': now.isoformat(), 'sources': [], 'provider_calls': 0,
                     'transport_kind': 'TEST_DOUBLE' if self.test_transport is not None else 'TAVILY_HTTPS',
                     'inference_calls': 0, 'model': None, 'retries': 0,
                     'approval_sha256': retrieval.digest(self.approval),
                     'recommended_next_action': 'Reconcile this reservation; do not retry.'}
            fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream); stream.flush(); os.fsync(stream.fileno())
            os.fsync(directory_fd)
            started = time.perf_counter()
            try:
                state['provider_calls'] = 0 if self.test_transport is not None else 1
                body, status, endpoint, raw_hash = (self.test_transport or retrieval.provider_request)(retrieval.REQUEST, key)
                body = guard.redact(body, key) if key else body
                state['provider_evidence'] = retrieval.response_evidence(body, status, raw_hash)
                # Checkpoint all bounded parsed evidence BEFORE validation can reject it.
                guard.write_state(path, state, directory_fd=directory_fd)
                if status != 200 or endpoint != retrieval.ENDPOINT: raise ValueError('Provider HTTP failure or endpoint mismatch')
                parsed = retrieval.validate_response(body)
                state.update(parsed, state='COMPLETE', final_status='NEEDS_REVIEW',
                             retrieved_at=datetime.now(timezone.utc).isoformat(),
                             recommended_next_action='Inspect an original source, choose a relevant passage, then check it. New model analysis has not run.',
                             cost_usd=None, cost_basis='Provider-reported API credits; dollar billing and remaining account balance unverified',
                             source_authenticity='NOT_CHECKED', publication_date='NOT_CHECKED', contradictions='NOT_CHECKED')
            except Exception as exc:
                if isinstance(exc, retrieval.TransportFailure): state['provider_evidence'] = exc.evidence
                state.update(state='UNCERTAIN', final_status='BLOCKED', error_type=type(exc).__name__, sources=[],
                             recommended_next_action='Reconcile the retained attempt and provider usage; do not retry or delete the reservation.')
            state.update(finished_at=datetime.now(timezone.utc).isoformat(), elapsed_ms=round((time.perf_counter()-started)*1000, 3),
                         timing_basis='Transport plus response checkpoint and validation; excludes reservation and final terminal write')
            state = guard.redact(state, key) if key else state
            try: guard.write_state(path, state, directory_fd=directory_fd)
            except Exception:
                print(json.dumps({'terminal_persistence': 'FAILED', 'state': state}), file=sys.stderr, flush=True)
                raise
            return state
