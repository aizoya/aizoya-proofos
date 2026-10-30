"""Owner-local app bridge to the review-bound R5 recovery guard. Disabled by default."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
GUARD_ROOT = ROOT/'runtime/one-shot-r5'
GUARD_ID = 'sha256:49aff9f118883edfe9f34067cd548f92bc7f1aa848653b0d10263065f9af5e2f'
sys.path.insert(0, str(GUARD_ROOT))
spec = importlib.util.spec_from_file_location('proofos_frozen_guard', GUARD_ROOT/'run_once.py')
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


def verify_app():
    record = json.loads((ROOT/'release.json').read_text())
    files = record['files']
    actual = 'sha256:'+guard.digest(files)
    if record['release_id'] != actual:
        raise ValueError('App identity mismatch')
    for name, expected in files.items():
        path = ROOT/name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('App source mismatch')
    guard.verify_sources()
    guard.verify_candidate(GUARD_ID)
    return actual


class InferenceService:
    def __init__(self, *, reviewed_app=None, reviewed_guard=None, test_transport=None, test_path=None, test_now=None):
        # Test injection is Python-only. The CLI exposes no fake transport, clock or path override.
        self.reviewed_app = reviewed_app
        self.reviewed_guard = reviewed_guard
        self.test_transport = test_transport
        self.test_path = test_path
        self.test_now = test_now

    def status(self):
        app_id = verify_app()
        now = self.test_now if self.test_transport is not None else datetime.now(timezone.utc)
        plan = guard.bound_plan()
        reason = None
        if now is None or now.tzinfo is None or now >= datetime.fromisoformat(plan['expires_at']):
            reason = 'Authorization expired. A fresh reviewed candidate and owner approval are required.'
        elif now < datetime.fromisoformat(plan['approved_at']):
            reason = 'Authorization is not yet valid.'
        elif self.test_transport is None and (self.reviewed_app!=app_id or self.reviewed_guard!=GUARD_ID):
            reason = 'Owner-local inference is locked pending exact-candidate external review.'
        elif self.test_transport is None and not guard.credential_format_ready(os.environ.get('NEBIUS_API_KEY')):
            reason = 'Full provider secret is missing or has an invalid format; do not use a service-account ID or masked value.'
        else:
            path = self.test_path if self.test_transport is not None else guard.fixed_ledger_path()
            if path is None or not path.parent.is_dir():
                reason = 'Persistent run directory is unavailable. Do not create a replacement ledger.'
            elif os.path.lexists(path):
                reason = 'A run reservation already exists. Reconcile it; do not retry.'
            else:
                try: guard.check_prior(path, test_mode=self.test_transport is not None)
                except (OSError, ValueError, TypeError, KeyError):
                    reason = 'Retained prior 401 reservation is missing, unsafe, or inconsistent. Stop; do not replace it.'
        return {
            'ready':reason is None,'reason':reason,'release_id':app_id,'guard_candidate_id':GUARD_ID,
            'provider':'Nebius Token Factory','model_id':guard.MODEL,'plan':plan,
            'mode':'TEST_DOUBLE' if self.test_transport is not None else 'OWNER_LOCAL',
            'scope':'One fixed published sample; no retrieval or external business action.',
            'required_input':dict(guard.PAYLOAD),'fully_verified':False,
        }

    def run(self, payload):
        # Bind exactly what the app shows to the one approved request. Never send arbitrary form input.
        if not isinstance(payload,dict) or payload!=guard.PAYLOAD:
            raise ValueError('Only the unchanged published sample is bound to this request.')
        state = self.status()
        if not state['ready']:
            raise PermissionError(state['reason'])
        fake = self.test_transport is not None
        path = self.test_path if fake else guard.fixed_ledger_path()
        result = guard.execute(path, 'offline-dummy-key' if fake else os.environ.get('NEBIUS_API_KEY'),
                               now=self.test_now if fake else None,
                               test_transport=self.test_transport,expected_candidate=GUARD_ID)
        # R5 result has been persisted before it reaches the UI. A second request hits its O_EXCL gate.
        _, source = guard.prepare_analysis(payload)
        complete = result.get('state')=='COMPLETE'
        live = complete and result.get('transport_kind')=='NEBIUS_HTTPS' and result.get('provider_calls')==1
        evidence = result.get('provider_evidence', {})
        return {
            'schema':'proofos.model-review.v1','task_id':source['task_id'],
            'recovery_of':result.get('recovery_of'),
            'release_id':state['release_id'],'guard_candidate_id':GUARD_ID,
            'requested_model':guard.MODEL,'provider':'Nebius Token Factory','plan':guard.bound_plan(),
            'execution_evidence':'TEST_DOUBLE' if fake else 'OBSERVED_RESPONSE' if live else 'UNCONFIRMED',
            'final_status':'NEEDS_REVIEW' if complete else 'BLOCKED','fully_verified':False,
            'source_review':source,'model_analysis':result.get('analysis'),
            'provider_evidence':evidence,'provider_calls':result.get('provider_calls',0),
            'reported_model':result.get('model') or evidence.get('model'),
            'response_id':result.get('response_id') or evidence.get('response_id'),
            'usage':result.get('usage') or evidence.get('usage'),'priced_usage_usd':result.get('priced_usage_usd'),
            'cost_basis':result.get('cost_basis','Cost unknown. Do not interpret missing usage as zero cost.'),
            'elapsed_ms':result.get('elapsed_ms'),'timing_basis':'Guard elapsed time, including evidence persistence; not pure model latency.',
            'started_at':result.get('started_at'),'finished_at':result.get('finished_at'),
            'run_state':result.get('state'),'retries':0,'source_fetched_by_app':False,
            'recommended_next_action':result.get('recommended_next_action','Review the model assessment against the original source. This attempt cannot be repeated.'),
            'incomplete_checks':['Original source authenticity and publication date','Factual truth beyond supplied text','Contradictions across sources','Business outcome verification'],
        }
