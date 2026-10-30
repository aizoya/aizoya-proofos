"""Credential recovery regressions. Temporary storage and fake transport only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import run_once as guard
from test_fixtures import seed_prior, prior_fixture
from test_run_once import response


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root/guard.RECOVERY_NAME
        self.calls = []

    def run_fake(self, key='offline-test-key', transport=None):
        def fake(*args): self.calls.append(1); return response()
        return guard.execute(self.path, key, test_transport=transport or fake,
                             now=datetime.fromisoformat(guard.bound_plan()['approved_at']))

    def test_missing_prior_prevents_reservation_and_transport(self):
        with self.assertRaises(FileNotFoundError): self.run_fake()
        self.assertFalse(self.path.exists()); self.assertEqual(self.calls, [])

    def test_prior_fields_must_match_exact_recorded_failure(self):
        p = seed_prior(self.root)
        for name, value in [('state','COMPLETE'), ('final_status','NEEDS_REVIEW'),
                            ('fully_verified',True), ('provider_calls',True),
                            ('transport_kind','TEST_DOUBLE'), ('manifest_sha256','wrong'),
                            ('plan',{}), ('started_at','wrong'), ('finished_at','wrong'),
                            ('provider_evidence',{'http_status':200}), ('priced_usage_usd','0')]:
            with self.subTest(name=name):
                data=prior_fixture(); data[name]=value; p.write_text(json.dumps(data))
                with self.assertRaises(PermissionError): self.run_fake()
                self.assertFalse(self.path.exists()); self.assertEqual(self.calls, [])

    def test_prior_symlink_hardlink_shared_file_and_fifo_rejected(self):
        p=seed_prior(self.root); raw=p.read_bytes(); p.unlink()
        other=self.root/'other'; other.write_bytes(raw); other.chmod(0o600)
        p.symlink_to(other)
        with self.assertRaises(OSError): self.run_fake()
        p.unlink(); os.link(other,p)
        with self.assertRaises(PermissionError): self.run_fake()
        p.unlink(); p.write_bytes(raw); p.chmod(0o644)
        with self.assertRaises(PermissionError): self.run_fake()
        p.unlink(); os.mkfifo(p,0o600)
        with self.assertRaises(PermissionError): self.run_fake()
        self.assertEqual(self.calls, []); self.assertFalse(self.path.exists())

    def test_duplicate_nonfinite_and_oversized_prior_rejected(self):
        p=seed_prior(self.root)
        for raw in ('{"state":"UNCERTAIN","state":"COMPLETE"}', '{"x":NaN}', ' '*65537):
            p.write_text(raw)
            with self.assertRaises((ValueError,PermissionError)): self.run_fake()
            self.assertEqual(self.calls, []); self.assertFalse(self.path.exists())

    def test_service_id_masked_and_quoted_keys_fail_before_reservation(self):
        for key in ('serviceaccount-e00w1bjhwmhbt6sdwv', 'v1.masked**ending', '"secret"', "'secret'", '', None):
            with self.subTest(key_type=type(key).__name__):
                with self.assertRaises(ValueError): self.run_fake(key)
                self.assertFalse(self.path.exists()); self.assertEqual(self.calls, [])

    def test_success_preserves_original_bytes_and_binds_original_digest(self):
        p=seed_prior(self.root); before=p.read_bytes()
        result=self.run_fake()
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(result['recovery_of']['prior_record_sha256'],hashlib.sha256(before).hexdigest())
        self.assertEqual(result['recovery_of']['prior_receipt_sha256'],guard.PRIOR_RECEIPT_SHA256)
        self.assertEqual(result['state'],'COMPLETE'); self.assertFalse(result['fully_verified'])
        self.assertEqual(result['provider_calls'],0)
        with self.assertRaises(FileExistsError): self.run_fake()
        self.assertEqual(self.calls,[1])

    def test_recovery_401_is_consumed_and_keeps_original(self):
        p=seed_prior(self.root); before=p.read_bytes()
        def fail(*args): self.calls.append(1); return guard.ProviderReply({},401,guard.ENDPOINT)
        result=self.run_fake(transport=fail)
        self.assertEqual(result['state'],'UNCERTAIN')
        self.assertEqual(result['provider_evidence']['http_status'],401)
        self.assertEqual(p.read_bytes(),before)
        with self.assertRaises(FileExistsError): self.run_fake()
        self.assertEqual(self.calls,[1])

    def test_concurrent_recovery_allows_one_fake_call_and_preserves_prior(self):
        p=seed_prior(self.root); before=p.read_bytes()
        def run():
            try: return self.run_fake()['state']
            except FileExistsError: return 'DENIED'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(lambda _:run(),range(2))),['COMPLETE','DENIED'])
        self.assertEqual(self.calls,[1]); self.assertEqual(p.read_bytes(),before)


if __name__=='__main__': unittest.main()
