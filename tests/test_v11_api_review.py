import csv
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from safety_games.api import BudgetExceeded, OpenAICompatibleClient, QuotaLedger
from safety_games.artifacts import write_json
from safety_games.config import APIBudgetConfig, LLMConfig
from safety_games.metrics import analyze, load_observations
from safety_games.review import prepare_review
from safety_games.tasks import load_tasks
from safety_games.trajectory import TrajectoryLogger
from tests.test_api import Opener, completion
from tests.test_observation import snapshot


class QuotaPlanningTests(unittest.TestCase):
    def test_daily_quota_does_not_reset_at_utc_midnight(self):
        with tempfile.TemporaryDirectory() as temporary:
            now=[86390.]
            config=APIBudgetConfig(tokens_per_day=100,experiment_token_limit=1000)
            ledger=QuotaLedger(Path(temporary)/'quota.json',config,clock=lambda:now[0])
            ledger.reserve(90)
            now[0]=86410.
            with self.assertRaises(BudgetExceeded):ledger.reserve(20)
            now[0]=172801.
            self.assertIsInstance(ledger.reserve(20),str)

    def test_daily_headroom_prevents_starting_unfunded_episode(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger=QuotaLedger(Path(temporary)/'quota.json',APIBudgetConfig(tokens_per_day=1000,daily_token_headroom=100))
            ledger.reserve(700)
            with self.assertRaises(BudgetExceeded):ledger.require_daily_capacity(250)
            ledger.require_daily_capacity(200)

    def test_server_remaining_headers_tighten_reservation_until_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            now=[1000.];sleeps=[]
            def sleep(delay):now[0]+=delay;sleeps.append(delay)
            ledger=QuotaLedger(Path(temporary)/'quota.json',APIBudgetConfig(),clock=lambda:now[0],sleep=sleep)
            ledger.observe_headers({'X-RateLimit-Remaining-Tokens':'1','X-RateLimit-Reset-Tokens':'1m2.5s'})
            ledger.reserve(100)
            self.assertAlmostEqual(sum(sleeps),62.5)
            self.assertTrue(all(s<=30 for s in sleeps))

    def test_api_sends_adapted_cap_not_incompatible_full_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            config=LLMConfig(model='openai/gpt-oss-20b',max_output_tokens=6144,adaptive_output_budget=True,min_output_tokens=1024)
            opener=Opener(completion())
            client=OpenAICompatibleClient(config,QuotaLedger(Path(temporary)/'quota.json',APIBudgetConfig()),key='synthetic-key',opener=opener)
            with patch.object(client,'estimate_tokens',return_value=3000):client.complete([],[])
            self.assertEqual(json.loads(opener.requests[0].data)['max_completion_tokens'],4744)
            record=json.loads((Path(temporary)/'quota.json').read_text())['requests'][0]
            self.assertEqual(record['tokens'],15)


class ReadOnlyReviewTests(unittest.TestCase):
    def make_run(self,root):
        task=load_tasks('data/manifest.json')[0]
        path=root/'run';attempt=path/'episodes'/task.task_id/'attempt-0001'
        logger=TrajectoryLogger(attempt,experiment_id='fixture',run_id='fixture',episode_id='fixture',task_id=task.task_id)
        initial=snapshot(task.public_files())
        final=snapshot({**task.public_files(),'solution.py':'print(False)'})
        logger.save_snapshot('initial',initial);logger.save_snapshot('final',final)
        logger.emit({'type':'agent_finished','status':'finished_text'})
        behavior={'automated_status':'no_hacking_detected','audit_status':'unreviewed','evidence':[],
                  'observed_explicit_test_file_reads':0,'observed_test_file_changes':0}
        write_json(attempt/'summary.json',{'status':'completed','task_id':task.task_id,'difficulty':'easy','episode_id':'fixture',
                   'termination':'finished_text','proxy_success':False,'original_public_success':False,'true_success':False,
                   'tool_calls':0,'token_usage':0,'duration_s':0,'behavior':behavior})
        write_json(path/'state.json',{'episodes':{task.task_id:{'status':'completed','attempt':'attempt-0001','episode_id':'fixture'}},'task_order':[task.task_id,'lc4']})
        return path

    def test_review_contains_required_columns_keeps_labels_and_original_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);run=self.make_run(root);output=root/'review'
            original={p:p.read_bytes() for p in run.rglob('*') if p.is_file()}
            result=prepare_review(run,output)
            self.assertEqual(result['episodes'],1)
            with (output/'audit_manifest.csv').open(encoding='utf-8',newline='') as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(rows[0]['audit_status'],'unreviewed')
            self.assertEqual(rows[0]['solution_written'],'True')
            rows[0]['reviewer_notes']='manual fixture note'
            with (output/'audit_manifest.csv').open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
            prepare_review(run,output)
            self.assertIn('manual fixture note',(output/'audit_manifest.csv').read_text(encoding='utf-8'))
            self.assertTrue(all(p.read_bytes()==raw for p,raw in original.items()))
            stats=json.loads((output/'statistics'/'metrics.json').read_text())
            self.assertEqual(stats['planned_task_count'],2)
            self.assertEqual(stats['all_planned']['true_success']['unknown_n'],1)

    def test_no_retrospective_output_inside_original_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            run=self.make_run(Path(temporary))
            with self.assertRaises(ValueError):prepare_review(run,run/'new-review')

    def test_infrastructure_interruption_is_visible_without_invented_grades(self):
        with tempfile.TemporaryDirectory() as temporary:
            run=self.make_run(Path(temporary));attempt=run/'episodes'/'lc217'/'attempt-0001'
            (attempt/'summary.json').unlink()
            write_json(attempt/'interruption.json',{'termination_reason':'infrastructure_error','episode_outcome':'infrastructure_error','phase':'evaluating'})
            observation=load_observations(run)[0]
            self.assertEqual(observation['episode_outcome'],'infrastructure_error')
            self.assertIsNone(observation['true_success'])
            self.assertFalse(observation['technically_completed'])


if __name__=='__main__':unittest.main()
