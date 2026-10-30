"""Offline-only synthetic prior ledger shaped from the supplied 401 receipt.

Never call this on owner storage. No production code imports this module.
"""
import json
import os
from pathlib import Path


def prior_fixture():
    receipt = json.loads(Path(__file__).with_name('PRIOR_RECEIPT.json').read_text())
    return {'plan': receipt['plan'], 'state': 'UNCERTAIN', 'final_status': 'BLOCKED',
            'fully_verified': False, 'transport_kind': 'NEBIUS_HTTPS',
            'manifest_sha256': 'd86ea819ebcb593ab3a923508f5a022564b44479bb0ee9bf9164cb8cc4149460',
            'started_at': receipt['started_at'], 'finished_at': receipt['finished_at'],
            'provider_evidence': receipt['provider_evidence'], 'provider_calls': 1,
            'priced_usage_usd': None}


def seed_prior(directory):
    path = directory/'nebius-only-20261027-01.json'
    if not os.path.lexists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream: json.dump(prior_fixture(), stream)
    return path
