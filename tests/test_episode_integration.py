import json
import os
from pathlib import Path
import tempfile
import unittest

from safety_games.config import AgentConfig, SandboxConfig
from safety_games.environment import DockerEpisode
from safety_games.evaluator import evaluate_source, parse_proxy
from safety_games.sandbox import DockerSandbox
from safety_games.tasks import load_tasks


@unittest.skipUnless(os.environ.get('SAFETY_GAMES_DOCKER_TESTS')=='1','real Docker tests require opt-in')
class EpisodeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.task=load_tasks('data/manifest.json')[0]
        self.sandbox_config=SandboxConfig(memory_mb=256,timeout_s=5)
        self.agent_config=AgentConfig(command_timeout_s=5)

    def test_workspace_tools_seccomp_identity_and_secret_isolation(self):
        with DockerEpisode(self.sandbox_config,self.agent_config,self.task.public_files()) as environment:
            result=environment.request('list_files')
            self.assertEqual(set(result['result']['files']),{'problem.md','solution.py','test.py','test_cases.json'})
            self.assertTrue(environment.request('read_file',{'path':'problem.md'})['ok'])
            environment.request('write_file',{'path':'nested/fixture.txt','content':'тест'})
            self.assertEqual(environment.request('read_file',{'path':'nested/fixture.txt'})['result']['content'],'тест')
            command="python -c \"import os; from pathlib import Path; s=Path('/proc/self/status').read_text(); assert 'Seccomp:\\t2' in s; assert 'NoNewPrivs:\\t1' in s; assert os.getuid()==65534; assert 'GROQ_API_KEY' not in os.environ; assert not Path('/var/run/docker.sock').exists()\""
            self.assertEqual(environment.request('run_command',{'command':command})['result']['exit_code'],0)

    def test_symlinks_and_traversal_cannot_escape_file_tools(self):
        with DockerEpisode(self.sandbox_config,self.agent_config,self.task.public_files()) as environment:
            with self.assertRaises(ValueError):environment.request('read_file',{'path':'../other'})
            environment.request('run_command',{'command':'ln -s /etc/passwd escaped'})
            self.assertFalse(environment.request('read_file',{'path':'escaped'})['ok'])

    def test_public_manipulation_does_not_change_independent_evaluator(self):
        originals=self.task.public_files()
        with DockerEpisode(self.sandbox_config,self.agent_config,originals) as environment:
            environment.request('write_file',{'path':'solution.py','content':self.task.reference})
            public=environment.request('run_command',{'command':'python -I -B test.py'})['result']
            self.assertTrue(parse_proxy(public,originals,environment.snapshot())['success'])
            environment.request('write_file',{'path':'solution.py','content':'print("false")'})
            environment.request('write_file',{'path':'test.py','content':'print(\'PUBLIC_RESULT {"passed":3,"total":3}\')'})
            forged=environment.request('run_command',{'command':'python test.py'})['result']
            proxy=parse_proxy(forged,originals,environment.snapshot())
            self.assertIsNone(proxy['success']);self.assertTrue(proxy['reported_success'])
        with tempfile.TemporaryDirectory() as temporary:
            case={'case_id':'fixture','input':{'nums':[1,1]},'expected':True}
            result=evaluate_source('print("false")',[case],DockerSandbox(self.sandbox_config),{},Path(temporary)/'score.json')
            self.assertFalse(result['success']);self.assertEqual(result['cases'][0]['status'],'wrong_answer')

    def test_workspace_is_fresh_and_command_timeout_preserves_observation(self):
        with DockerEpisode(self.sandbox_config,self.agent_config,self.task.public_files()) as environment:
            environment.request('write_file',{'path':'marker','content':'fixture'})
            result=environment.request('run_command',{'command':'python -c "import time; time.sleep(60)"'})['result']
            self.assertEqual(result['status'],'timeout')
            self.assertIn('marker',environment.snapshot()['files'])
        with DockerEpisode(self.sandbox_config,self.agent_config,self.task.public_files()) as environment:
            self.assertNotIn('marker',environment.snapshot()['files'])


if __name__=='__main__':unittest.main()
