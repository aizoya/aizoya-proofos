"""Review operator-supplied source text. No retrieval, model, or action execution."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('A bounded nonempty text value is required')
    if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        raise ValueError('Control characters are not allowed')
    return value.strip()


def review_source(payload: dict, *, candidate_id: str) -> dict:
    claim = _text(payload.get('claim'), 1000)
    quote = _text(payload.get('quote'), 2000)
    excerpt = _text(payload.get('excerpt'), 12000)
    url = _text(payload.get('url'), 2048)
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in url):
        raise ValueError('Use a public HTTPS source link without credentials')
    # These links are displayed only. The server never fetches user-supplied URLs.
    normalized = lambda s: re.sub(r'\s+', ' ', s).strip()
    found = normalized(quote) in normalized(excerpt)
    inputs = {'claim': claim, 'quote': quote, 'excerpt': excerpt, 'url': url}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {
        'schema': 'proofos.source-review.v1',
        'task_id': str(uuid4()), 'candidate_id': candidate_id,
        'reviewed_at': datetime.now(timezone.utc).isoformat(),
        'requested_outcome': 'Review supplied source text for a proposed claim',
        'final_status': 'NEEDS_REVIEW', 'fully_verified': False,
        'conclusion': 'Quoted passage found in supplied text' if found else 'Quoted passage missing from supplied text',
        'recommended_next_action': 'Review whether the passage actually supports the claim, then verify the original source and its date.' if found else 'Find the exact supporting passage or revise the claim before relying on it.',
        'checks': [
            {'name': 'Quotation in supplied excerpt (whitespace normalized, case sensitive)', 'outcome': 'PASS' if found else 'FAIL'},
            *[{'name': name, 'outcome': 'NOT_CHECKED'} for name in ('Claim meaning and factual truth', 'Original source authenticity and publication date', 'Contradictions across sources', 'Live NVIDIA inference through Nebius')],
        ],
        'evidence': {**inputs, 'origin': 'operator_supplied_text', 'source_fetched_by_app': False, 'source_retrieved_at': None, 'input_sha256': digest},
        'authorization': 'No external action requested or authorized',
        'actions_performed': ['Validated input', 'Compared quotation with supplied excerpt', 'Generated this review receipt'],
        'provider_calls': 0, 'external_actions': 0,
        'model': None, 'provider_cost': None,
        'cost_basis': 'No provider was called. No provider cost measurement was performed.',
    }
