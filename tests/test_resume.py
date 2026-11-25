from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from safety_games.artifacts import SecretRedactor, write_json
from safety_games.config import ExperimentConfig, LLMConfig
from safety_games.experiment import run_experiment
from safety_games.trajectory import TrajectoryLogger, read_events
from tests.test_observation import snapshot


class MemoryEnvironment:
    def __init__(self, sandbox, agent, files):self.files=files
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def snapshot(self):return snapshot(self.files)
    def request(self,action,args):
        return {'ok':True,'result':{'status':'ok','exit_code':0,'stdout':'PUBLIC_RESULT {"passed":3,"total":3}','stderr':'','duration_s':0}}


class ResumeTests(unittest.TestCase):
    def test_interrupted_evaluation_resumes_without_reissuing_agent_or_completed_episodes(self):
        with tempfile.TemporaryDirectory() as temporary:
            config=ExperimentConfig(output_dir=Path(temporary),llm=LLMConfig(model='openai/gpt-oss-20b'),
                                    task_manifest=Path('data/manifest.json').resolve(),prompt_path=Path('prompts/coding_agent_v1.txt').resolve())
            sandbox=Mock();sandbox.prepare.return_value='sha256:'+64*'a';sandbox.image_id=sandbox.prepare.return_value
            client=Mock();client.redactor=SecretRedactor()
            def validate(tasks,executor,path):write_json(path,{'success':True,'image_id':sandbox.image_id,'tasks':[{}]*15})
            def agent(task,environment,client,logger,config,prompt,**kwargs):
                state=environment.snapshot();logger.save_snapshot('initial',state);logger.save_snapshot('final',state)
                return {'termination':'test_fixture_only','tool_calls':0,'token_usage':0,'charged_tokens':0,'duration_s':0,'snapshot':state}
            complete={'proxy_success':True,'true_success':True,'token_usage':0,'behavior':{'automated_status':'no_hacking_detected'}}
            with patch('safety_games.experiment.DockerSandbox',return_value=sandbox),patch('safety_games.experiment.DockerEpisode',MemoryEnvironment),\
                 patch('safety_games.experiment.OpenAICompatibleClient',return_value=client),patch('safety_games.experiment.validate_references',side_effect=validate),\
                 patch('safety_games.experiment.run_agent',side_effect=agent) as run,patch('safety_games.experiment.analyze'),redirect_stdout(io.StringIO()):
                with patch('safety_games.experiment._finish_episode',side_effect=RuntimeError('fixture interruption')):
                    with self.assertRaises(RuntimeError):run_experiment(config,'fixture',stage='smoke')
                self.assertEqual(run.call_count,1)
                with patch('safety_games.experiment._finish_episode',return_value=complete):
                    run_experiment(config,'fixture',stage='smoke',resume=True)
                    self.assertEqual(run.call_count,3)
                    run_experiment(config,'fixture',stage='smoke',resume=True)
                    self.assertEqual(run.call_count,3)
                counts={}
                for call in run.call_args_list:
                    task_id=call.args[0].task_id;counts[task_id]=counts.get(task_id,0)+1
                self.assertEqual(counts,{'lc217':1,'lc4':1,'abc389_e':1})
                with self.assertRaises(FileExistsError):run_experiment(config,'fixture')
                changed=replace(config,llm=replace(config.llm,temperature=0.8))
                with self.assertRaisesRegex(ValueError,'Protocol/code/image changed'):
                    run_experiment(changed,'fixture',resume=True)

    def logger(self,path):
        return TrajectoryLogger(path,experiment_id='test',run_id='test',episode_id='test',task_id='test')

    def test_torn_final_jsonl_record_is_preserved_and_repaired_on_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);logger=self.logger(path)
            logger.emit({'type':'fixture','result':'complete'})
            with (path/'trajectory.jsonl').open('a',encoding='utf-8') as stream:stream.write('{"type":"torn')
            resumed=self.logger(path)
            resumed.emit({'type':'after_resume'})
            events=read_events(path)
            self.assertEqual([e['type'] for e in events],['fixture','trajectory_tail_recovered','after_resume'])
            self.assertTrue((path/'rejected_tail_2.json').exists())
            self.assertIn('after_resume',(path/'trajectory.md').read_text(encoding='utf-8'))

    def test_corruption_before_final_record_is_not_silently_discarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);path.joinpath('trajectory.jsonl').write_text('not-json\n{"event_id":2}\n',encoding='utf-8')
            with self.assertRaises(ValueError):self.logger(path)

    def test_snapshot_redaction_covers_base64_file_content(self):
        state=snapshot({'fixture.txt':'actual-unit-test-secret'})
        cleaned=SecretRedactor(('actual-unit-test-secret',)).clean(state)
        import base64
        item=cleaned['files']['fixture.txt']
        self.assertEqual(base64.b64decode(item['content']),b'[REDACTED]')
        self.assertTrue(item['content_redacted'])


if __name__=='__main__':unittest.main()
