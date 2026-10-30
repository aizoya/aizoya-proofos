from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import os
import io
import stat
from types import SimpleNamespace
from contextlib import redirect_stderr
from urllib.error import HTTPError
from run_once import execute as guard_execute, MODEL, bound_plan, verify_sources, fixed_ledger_path, ProviderReply, ENDPOINT, provider_request, ProviderFailure, write_state, verify_candidate, pin_directory

from test_fixtures import seed_prior
from run_once import RECOVERY_NAME

def execute(path, *args, **kwargs):
    if path.parent.is_dir() and not path.parent.is_symlink(): seed_prior(path.parent)
    return guard_execute(path, *args, **kwargs)

NOW = datetime.fromisoformat(bound_plan()['approved_at'])


def response():
    return {'id':'test-response-only', 'model':MODEL, 'choices':[{'finish_reason':'stop', 'message':{'content':json.dumps({'verdict':'SUPPORTED','explanation':'The supplied passage states the deadline.','evidence_quote':'Submissions are due Friday, October 30 at 10:00 AM PT.'})}}], 'usage':{'prompt_tokens':500,'completion_tokens':100,'total_tokens':600}}


class RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve()/RECOVERY_NAME

    def run_fake(self, transport=None, **kw):
        return execute(self.path,'test-key-not-a-secret',now=NOW,test_transport=transport or (lambda *args:response()),**kw)

    def test_completion_is_explicitly_test_double(self):
        value = self.run_fake()
        self.assertEqual(value['state'],'COMPLETE')
        self.assertEqual(value['final_status'],'NEEDS_REVIEW')
        self.assertEqual(value['transport_kind'],'TEST_DOUBLE')
        self.assertEqual(value['provider_calls'],0)
        self.assertFalse(value['fully_verified'])
        self.assertEqual(value['usage']['total_tokens'],600)
        self.assertNotIn('test-key-not-a-secret',self.path.read_text())

    def test_second_instance_cannot_repeat(self):
        self.run_fake()
        with self.assertRaises(FileExistsError):self.run_fake()

    def test_race_permits_only_one_transport(self):
        calls=[]
        def transport(*args):calls.append(1);return response()
        def run():
            try:return self.run_fake(transport)['state']
            except FileExistsError:return 'DENIED'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:run(),range(2)))
        self.assertCountEqual(results,['COMPLETE','DENIED'])
        self.assertEqual(len(calls),1)

    def test_uncertain_transport_consumes_run(self):
        def failed(*args):raise TimeoutError('SECRET_MUST_NOT_BE_LOGGED')
        value=self.run_fake(failed)
        self.assertEqual(value['state'],'UNCERTAIN')
        self.assertNotIn('SECRET_MUST_NOT_BE_LOGGED',self.path.read_text())
        with self.assertRaises(FileExistsError):self.run_fake()

    def test_invalid_responses_are_terminal(self):
        for field,value in [('model','wrong'),('usage',{}),('choices',[]),('id','')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                raw=response();raw[field]=value
                result=execute(Path(directory).resolve()/self.path.name,'test-key',now=NOW,test_transport=lambda *args:raw)
                self.assertEqual(result['state'],'UNCERTAIN')

    def test_no_reservation_for_invalid_key_or_expired_authority(self):
        with self.assertRaises(ValueError):execute(self.path,None,now=NOW)
        self.assertFalse(self.path.exists())
        with self.assertRaises(PermissionError):execute(self.path,'test-key',now=datetime(2026,10,30,14,tzinfo=timezone.utc))
        self.assertFalse(self.path.exists())

    def test_renewal_cannot_be_used_before_recorded_owner_approval(self):
        from datetime import timedelta
        calls=[]
        with self.assertRaisesRegex(PermissionError,'not yet valid'):
            execute(self.path,'test-key',now=NOW-timedelta(microseconds=1),test_transport=lambda *a:calls.append(1))
        self.assertFalse(self.path.exists())
        self.assertEqual(calls,[])

    def test_recovery_binds_limits_and_fixed_new_authority_basename(self):
        plan=bound_plan()
        self.assertEqual(plan['expires_at'],'2026-10-30T14:00:00+00:00')
        self.assertEqual(plan['budget_basis'],'estimate_not_provider_cap')
        self.assertEqual(plan['timeout_basis'],'per_io_not_total')
        self.assertEqual(len(plan['approval_record_sha256']),64)
        self.assertEqual(fixed_ledger_path().name,RECOVERY_NAME)

    def test_stale_inflight_blocks_restart(self):
        self.path.write_text('{"state":"IN_FLIGHT"}')
        with self.assertRaises(FileExistsError):self.run_fake()

    def test_symlink_and_wrong_basename_rejected(self):
        target=Path(self.temp.name)/'target';target.write_text('untouched')
        self.path.symlink_to(target)
        with self.assertRaises(FileExistsError):self.run_fake()
        self.assertEqual(target.read_text(),'untouched')
        with self.assertRaises(ValueError):execute(target,'test-key',now=NOW,test_transport=lambda *args:response())

    def test_manifest_plan_matches_bounded_current_authority(self):
        self.assertEqual(verify_sources()['plan'],bound_plan())
        self.assertEqual(bound_plan()['max_calls'],1)
        self.assertEqual(bound_plan()['retries'],0)
        self.assertEqual(bound_plan()['max_cost_usd'],'0.05')

    def test_production_path_cannot_be_reset_by_directory(self):
        with self.assertRaisesRegex(ValueError,'fixed owner-home'):
            execute(self.path,'test-key',now=NOW)
        self.assertFalse(self.path.exists())

    def test_truncated_and_over_budget_responses_are_uncertain(self):
        for kind in ('truncated','budget','tokens','schema'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                raw=response()
                if kind=='truncated': raw['choices'][0]['finish_reason']='length'
                if kind=='budget': raw['usage']={'prompt_tokens':200000,'completion_tokens':100,'total_tokens':200100}
                if kind=='tokens': raw['usage']={'prompt_tokens':1,'completion_tokens':1025,'total_tokens':1026}
                if kind=='schema': raw['choices'][0]['message']['content']='{"fully_verified":true}'
                result=execute(Path(directory).resolve()/self.path.name,'test-key',now=NOW,test_transport=lambda *args:raw)
                self.assertEqual(result['state'],'UNCERTAIN')

    def test_home_override_does_not_change_account_path(self):
        before=fixed_ledger_path()
        with patch.dict(os.environ,{'HOME':self.temp.name}):
            self.assertEqual(fixed_ledger_path(),before)

    def test_symlinked_ancestor_rejected_before_transport(self):
        root=Path(self.temp.name).resolve();real=root/'real';real.mkdir();(real/'proofos').mkdir()
        alias=root/'alias';alias.symlink_to(real,target_is_directory=True)
        calls=[]
        with self.assertRaises(ValueError):execute(alias/'proofos'/self.path.name,'test-key',now=NOW,test_transport=lambda *a:calls.append(1))
        self.assertEqual(calls,[])

    def test_rejected_output_keeps_metadata_in_checkpoint(self):
        raw=response();raw['choices'][0]['finish_reason']='length'
        import run_once
        original=run_once.validate_response
        def validate(value):
            saved=json.loads(self.path.read_text())
            self.assertEqual(saved['state'],'IN_FLIGHT')
            self.assertEqual(saved['provider_evidence']['response_id'],'test-response-only')
            self.assertEqual(saved['provider_evidence']['usage']['total_tokens'],600)
            return original(value)
        with patch('run_once.validate_response',side_effect=validate):result=self.run_fake(lambda *a:raw)
        self.assertEqual(result['state'],'UNCERTAIN')
        self.assertEqual(result['provider_evidence']['finish_reasons'],['length'])
        self.assertEqual(result['provider_evidence']['http_status'],200)

    def test_model_mismatch_keeps_actual_model_and_usage(self):
        raw=response();raw['model']='different-model'
        result=self.run_fake(lambda *a:raw)
        self.assertEqual(result['state'],'UNCERTAIN')
        self.assertEqual(result['provider_evidence']['model'],'different-model')
        self.assertEqual(result['provider_evidence']['usage']['total_tokens'],600)

    def test_leftover_legacy_temporary_does_not_collide(self):
        old=self.path.with_suffix('.terminal.tmp');old.write_text('leave untouched')
        result=self.run_fake()
        self.assertEqual(result['state'],'COMPLETE')
        self.assertEqual(old.read_text(),'leave untouched')
        self.assertEqual(json.loads(self.path.read_text())['state'],'COMPLETE')

    def test_persist_failure_prints_terminal_reconciliation_to_stderr(self):
        output=io.StringIO()
        with patch('run_once.write_state',side_effect=OSError('test')),redirect_stderr(output),self.assertRaises(OSError):self.run_fake()
        fallback=json.loads(output.getvalue())
        self.assertEqual(fallback['state']['state'],'UNCERTAIN')
        self.assertEqual(fallback['state']['provider_evidence']['response_id'],'test-response-only')
        self.assertNotIn('test-key-not-a-secret',output.getvalue())
        self.assertEqual(json.loads(self.path.read_text())['state'],'IN_FLIGHT')

    def test_terminal_write_failure_preserves_completed_result_in_stderr(self):
        original=write_state;output=io.StringIO();calls=[]
        def write(path,state,**kwargs):
            calls.append(state['state'])
            if len(calls)==2:raise OSError('terminal write test')
            original(path,state,**kwargs)
        with patch('run_once.write_state',side_effect=write),redirect_stderr(output),self.assertRaises(OSError):self.run_fake()
        self.assertEqual(json.loads(output.getvalue())['state']['state'],'COMPLETE')
        self.assertEqual(json.loads(self.path.read_text())['provider_evidence']['response_id'],'test-response-only')

    def test_http_error_status_and_body_identity_retained(self):
        error=HTTPError(ENDPOINT,429,'test',{},io.BytesIO(json.dumps({'id':'rejected-request','model':MODEL,'usage':{'prompt_tokens':10}}).encode()))
        with patch('run_once.build_opener') as opener:
            opener.return_value.open.side_effect=error
            reply=provider_request({},'test-key')
        result=self.run_fake(lambda *a:reply)
        self.assertEqual(result['state'],'UNCERTAIN')
        self.assertEqual(result['provider_evidence']['http_status'],429)
        self.assertEqual(result['provider_evidence']['response_id'],'rejected-request')

    def test_invalid_http_error_body_keeps_status(self):
        error=HTTPError(ENDPOINT,503,'test',{},io.BytesIO(b'not-json'))
        with patch('run_once.build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(ProviderFailure) as caught:provider_request({},'test-key')
        def failed(*a):raise caught.exception
        result=self.run_fake(failed)
        self.assertEqual(result['provider_evidence']['http_status'],503)
        self.assertEqual(result['state'],'UNCERTAIN')

    def test_directory_fsync_after_replace(self):
        events=[]
        import run_once
        original_replace=run_once.os.replace; original_sync=run_once.os.fsync
        def replace(*a,**kw):events.append('replace');return original_replace(*a,**kw)
        def sync(fd):events.append('sync');return original_sync(fd)
        with patch('run_once.os.replace',side_effect=replace),patch('run_once.os.fsync',side_effect=sync):
            write_state(self.path,{'state':'TEST'})
        self.assertEqual(events,['sync','replace','sync'])

    def test_candidate_verification_rejects_wrong_external_identity(self):
        with self.assertRaises(ValueError):verify_candidate('sha256:'+'0'*64)

    def test_evidence_redacts_credential_shaped_response_id(self):
        raw=response();raw['id']='test-key-not-a-secret'
        result=self.run_fake(lambda *a:raw)
        self.assertEqual(result['provider_evidence']['response_id'],'[REDACTED]')
        self.assertNotIn('test-key-not-a-secret',self.path.read_text())

    def test_private_chain_rejects_shared_permissions(self):
        root=Path(self.temp.name).resolve();a=root/'.aizoya';a.mkdir(mode=0o700);leaf=a/'proofos';leaf.mkdir(mode=0o700)
        for directory in (a,leaf):
            for mode in (0o755,0o770,0o777):
                with self.subTest(directory=directory.name,mode=mode):
                    directory.chmod(mode)
                    with self.assertRaises(PermissionError):
                        with pin_directory(leaf,root,test_mode=True):pass
                    directory.chmod(0o700)

    def test_private_chain_rejects_nonowner(self):
        root=Path(self.temp.name).resolve()
        import run_once
        original=run_once.os.fstat
        def wrong(fd):
            info=original(fd)
            return SimpleNamespace(st_uid=os.getuid()+1,st_mode=info.st_mode)
        with patch('run_once.os.fstat',side_effect=wrong),self.assertRaises(PermissionError):
            with pin_directory(root,root,test_mode=True):pass

    def test_descriptor_writes_stay_in_pinned_directory_after_rename(self):
        root=Path(self.temp.name).resolve();leaf=root/'private';leaf.mkdir(mode=0o700)
        path=leaf/self.path.name;old=root/'retained'
        with pin_directory(leaf,root,test_mode=True) as fd:
            leaf.rename(old);leaf.mkdir(mode=0o700)
            write_state(path,{'state':'PINNED'},directory_fd=fd)
        self.assertFalse(path.exists())
        self.assertEqual(json.loads((old/self.path.name).read_text())['state'],'PINNED')

    def test_terminal_faults_preserve_reservation_and_report(self):
        import run_once
        for operation in ('create','serialize','sync','replace'):
            with self.subTest(operation=operation),tempfile.TemporaryDirectory() as directory:
                path=Path(directory).resolve()/self.path.name;path.write_text('{"state":"IN_FLIGHT"}')
                if operation=='create':target='run_once.os.open'
                elif operation=='serialize':target='run_once.json.dump'
                elif operation=='sync':target='run_once.os.fsync'
                else:target='run_once.os.replace'
                with pin_directory(path.parent,path.parent,test_mode=True) as fd:
                    with patch(target,side_effect=OSError('fault')),self.assertRaises(OSError):
                        write_state(path,{'state':'COMPLETE'},directory_fd=fd)
                self.assertEqual(json.loads(path.read_text())['state'],'IN_FLIGHT')

    def test_per_io_timeout_does_not_claim_overall_deadline(self):
        # Virtual slow response documents the retained limitation, without sleeps.
        clock=[0]
        class Reply:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def geturl(self):return ENDPOINT
            def read(self,limit):clock[0]+=45;return json.dumps(response()).encode()
        with patch('run_once.build_opener') as opener:
            opener.return_value.open.return_value=Reply()
            value=provider_request({},'test-key')
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],30)
        self.assertEqual(value.status,200)
        self.assertGreater(clock[0],30)


if __name__=='__main__':unittest.main()
