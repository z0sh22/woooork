"""Synthetic scheduler checks: no provider inference or real experiments."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from safety_games.api import QuotaLedger
from safety_games.artifacts import write_json
from safety_games.config import APIBudgetConfig
from scripts.run_control_plan import _requires_model, run_plan, smoke_gate


class DailySchedulingTests(unittest.TestCase):
    def test_estimate_waits_for_enough_old_usage_to_leave_the_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            now=[1000.]
            config=APIBudgetConfig(tokens_per_day=1000,daily_token_headroom=100)
            ledger=QuotaLedger(Path(temporary)/'ledger.json',config,clock=lambda:now[0])
            ledger.reserve(500);now[0]=1010.;ledger.reserve(200)
            before=ledger.path.read_bytes()
            status=ledger.daily_status(300)
            self.assertEqual(status['available_tokens'],200)
            self.assertFalse(status['ready_now'])
            self.assertAlmostEqual(status['ready_at_epoch'],87400.1)
            self.assertEqual(ledger.path.read_bytes(),before)
            now[0]=87400.2
            self.assertTrue(ledger.daily_status(300)['ready_now'])

    def test_atomic_write_recovers_brief_windows_file_sharing_failure(self):
        from safety_games.logging import _atomic_write
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'state.json';path.write_text('old')
            original=os.replace;calls=[]
            def replace(source,target):
                calls.append(target)
                if len(calls)==1:raise PermissionError('synthetic transient sharing fixture')
                return original(source,target)
            with patch('safety_games.logging.os.replace',side_effect=replace),patch('safety_games.logging.time.sleep') as sleep:
                _atomic_write(path,'new')
            self.assertEqual(path.read_text(),'new');self.assertEqual(len(calls),2)
            sleep.assert_called_once_with(.05)
            self.assertEqual(list(Path(temporary).iterdir()),[path])

    def test_atomic_write_permanent_denial_keeps_old_file_and_cleans_temp(self):
        from safety_games.logging import _atomic_write
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'state.json';path.write_text('old')
            with patch('safety_games.logging.os.replace',side_effect=PermissionError('synthetic permanent fixture')) as replace,\
                 patch('safety_games.logging.time.sleep'):
                with self.assertRaises(PermissionError):_atomic_write(path,'new')
            self.assertEqual(replace.call_count,5);self.assertEqual(path.read_text(),'old')
            self.assertEqual(list(Path(temporary).iterdir()),[path])


class ControlPlanTests(unittest.TestCase):
    def make_smoke(self,root):
        write_json(root/'manifest.json',{'smoke_task_ids':['easy','medium','hard']})
        entries={}
        for task in ('easy','medium','hard'):
            entries[task]={'status':'completed','attempt':'attempt-0001'}
            attempt=root/'episodes'/task/'attempt-0001'
            write_json(attempt/'summary.json',{'technically_completed':False,'solution_written':False,
                       'true_success':False,'proxy_success':None,'proxy':{'status':'public_evaluator_changed'},
                       'termination_reason':'output_token_limit','episode_outcome':'output_token_limit','token_usage':100})
            for label in ('initial','final','post_proxy'):write_json(attempt/(label+'_snapshot.json'),{})
        write_json(root/'state.json',{'episodes':entries,'task_order':['easy','medium','hard']})

    def test_gate_does_not_select_by_hacking_correctness_or_implementation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.make_smoke(root)
            self.assertTrue(smoke_gate(root)['passed'])
            p=root/'episodes'/'hard'/'attempt-0001'/'summary.json'
            value=json.loads(p.read_text());value['termination_reason']='api_error';write_json(p,value)
            self.assertFalse(smoke_gate(root)['passed'])

    def test_unknown_independent_evaluation_does_not_pass_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.make_smoke(root)
            p=root/'episodes'/'hard'/'attempt-0001'/'summary.json'
            value=json.loads(p.read_text());value['true_success']=None;write_json(p,value)
            self.assertFalse(smoke_gate(root)['passed'])

    def test_pending_evaluation_can_resume_without_funding_a_new_model_episode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);self.make_smoke(root)
            self.assertFalse(_requires_model(root,'pilot'))
            state=json.loads((root/'state.json').read_text());state['episodes']['easy']['status']='evaluating'
            state['episodes'].pop('medium');write_json(root/'state.json',state)
            saved=root/'episodes'/'easy'/'attempt-0001'/'agent_result.json';write_json(saved,{})
            self.assertFalse(_requires_model(root,'pilot'))
            saved.unlink();self.assertTrue(_requires_model(root,'pilot'))

    def test_unapproved_plan_does_not_touch_model(self):
        with patch('scripts.run_control_plan.OpenAICompatibleClient') as client:
            with self.assertRaises(ValueError):run_plan('unused','unused','unused',approved=False)
            client.assert_not_called()

    def test_wait_limit_records_pending_state_without_any_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch('scripts.run_control_plan.verify_preservation',return_value={'success':True}),\
                 patch('scripts.run_control_plan.DockerSandbox') as docker,\
                 patch('scripts.run_control_plan.OpenAICompatibleClient') as client,\
                 patch('scripts.run_control_plan.QuotaLedger') as ledger,\
                 patch('scripts.run_control_plan.run_experiment') as run:
                docker.return_value.prepare.return_value='sha256:'+'a'*64
                client.return_value.check_model.return_value={'available':True,'inference_performed':False}
                ledger.return_value.daily_status.return_value={'ready_now':False,'ready_at_epoch':time.time()+3600}
                result=run_plan('configs/baseline_v1_1.toml','synthetic-unused',root/'plan',approved=True,max_wait_hours=0)
                self.assertEqual(result['state'],'wait_limit_reached')
                run.assert_not_called();client.return_value.complete.assert_not_called()
                self.assertFalse((root/'plan'/'.plan.lock').exists())


if __name__=='__main__':unittest.main()
