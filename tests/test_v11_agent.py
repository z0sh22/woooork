"""Controlled infrastructure fixtures; never behavioral LLM observations."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from safety_games.agent import run_agent
from safety_games.api import APIRequestError, BudgetExceeded, ChatTurn, ToolCallingClient, output_allowance, token_breakdown
from safety_games.config import APIBudgetConfig, AgentConfig, ExperimentConfig, LLMConfig, load_config
from safety_games.experiment import run_experiment
from safety_games.outcomes import classify_episode, solution_assessment
from safety_games.tasks import load_tasks
from safety_games.tools import ToolFormatError, validate_tool_arguments, validate_tool_calls
from safety_games.trajectory import TrajectoryLogger, read_events
from tests.test_observation import snapshot


class SequenceClient(ToolCallingClient):
    def __init__(self, config, turns):self.config,self.turns,self.calls=config,list(turns),[]
    def complete(self,messages,tools,**kwargs):
        self.calls.append((json.loads(json.dumps(messages)),kwargs))
        turn=self.turns.pop(0)
        if isinstance(turn,Exception):raise turn
        return turn


class Workspace:
    def __init__(self,files):self.files=dict(files);self.requests=[]
    def snapshot(self):return snapshot(self.files)
    def request(self,name,args):
        self.requests.append((name,args))
        if name=='write_file':self.files[args['path']]=args['content']
        return {'ok':True,'result':{'status':'ok'}}


def turn(calls=None,*,finish='tool_calls',content=None):
    return ChatTurn({'role':'assistant','content':content,'tool_calls':calls},
                    {'prompt_tokens':10,'completion_tokens':20,'total_tokens':30,
                     'completion_tokens_details':{'reasoning_tokens':12}},'openai/gpt-oss-20b','fixture',finish,30)


def call(name='finish_task',arguments='{"summary":"done"}',identifier='fixture'):
    return {'id':identifier,'type':'function','function':{'name':name,'arguments':arguments}}


class AgentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.config=load_config('configs/baseline_v1_1.toml')
        self.task=load_tasks('data/manifest.json')[0]

    def run_fixture(self,turns,config=None):
        config=config or self.config
        environment=Workspace(self.task.public_files())
        client=SequenceClient(config.llm,turns)
        with tempfile.TemporaryDirectory() as temporary:
            logger=TrajectoryLogger(Path(temporary),experiment_id='synthetic',run_id='synthetic',episode_id='synthetic',task_id=self.task.task_id)
            result=run_agent(self.task,environment,client,logger,config,'neutral fixture prompt')
            events=read_events(Path(temporary))
        return result,events,environment,client

    def test_truncated_function_call_is_not_executed_and_later_valid_call_runs(self):
        incomplete=turn([call('write_file','{"path":"solution.py","content":"partial')],finish='length')
        valid=turn([call('write_file',json.dumps({'path':'solution.py','content':'print(true)'}))])
        result,events,environment,client=self.run_fixture([incomplete,valid,turn([call()])])
        self.assertEqual(result['termination'],'finish_task')
        self.assertEqual(result['output_continuations'],1)
        self.assertEqual(len(environment.requests),1)
        self.assertEqual(environment.files['solution.py'],'print(true)')
        self.assertEqual(sum(e['type']=='model_response' for e in events),3)
        self.assertFalse(any(m.get('tool_calls') for m in client.calls[1][0]))
        self.assertEqual(result['reasoning_tokens_known'],36)

    def test_reasoning_only_length_has_bounded_continuation(self):
        result,events,environment,client=self.run_fixture([turn(None,finish='length') for _ in range(3)])
        self.assertEqual(result['termination'],'output_token_limit')
        self.assertEqual(result['output_continuations'],2)
        self.assertEqual(len(client.calls),3)
        self.assertEqual(environment.requests,[])

    def test_invalid_batch_is_atomic_no_valid_prefix_executed(self):
        bad=turn([call('write_file','{"path":"solution.py","content":"bad"}','one'),call('run_command','{"command":','two')])
        result,events,environment,client=self.run_fixture([bad,turn([call()])])
        self.assertEqual(environment.requests,[])
        self.assertEqual(result['tool_parse_errors'],1)
        self.assertTrue(any(e['type']=='local_tool_parse_error' and e['raw_message']==bad.message for e in events))
        self.assertFalse(any(m.get('tool_calls') for m in client.calls[1][0]))

    def test_nonarray_calls_and_unknown_tool_are_recoverable(self):
        for calls in ({'function':{}},[None],[{'type':'function','id':'x','function':None}],[call('internet_search','{}')]):
            with self.subTest(calls=calls):
                result,events,environment,client=self.run_fixture([turn(calls),turn([call()])])
                self.assertEqual(result['termination'],'finish_task')
                self.assertEqual(result['tool_parse_errors'],1)
                self.assertFalse(environment.requests)

    def test_provider_rejection_is_logged_and_model_retries_without_fabrication(self):
        failed=ChatTurn({}, {},self.config.llm.model,None,'tool_parse_error',100,{'failed_generation':'fixture invalid'})
        result,events,environment,client=self.run_fixture([failed,turn([call()])])
        self.assertEqual(result['charged_tokens'],130)
        self.assertEqual(result['token_usage'],30)
        self.assertEqual(sum(e['type']=='model_response' for e in events),1)
        self.assertIn('No tool',client.calls[1][0][-1]['content'])

    def test_fatal_api_error_preserves_final_workspace_and_charged_reservation(self):
        result,events,environment,client=self.run_fixture([APIRequestError('fixture',charged_tokens=123)])
        self.assertEqual(result['termination'],'api_error')
        self.assertEqual(result['charged_tokens'],123)
        self.assertEqual(result['snapshot'],environment.snapshot())

    def test_context_and_deadline_fail_before_any_request(self):
        config=replace(self.config,agent=replace(self.config.agent,max_input_estimate=1))
        result,events,environment,client=self.run_fixture([],config)
        self.assertEqual(result['termination_detail'],'input_context_limit')
        self.assertFalse(client.calls)
        with patch('safety_games.agent.time.monotonic',side_effect=[0,2000,2000]):
            result,events,environment,client=self.run_fixture([])
        self.assertEqual(result['termination'],'time_limit')

    def test_run_requires_stage_approval_before_docker_or_api(self):
        with patch('safety_games.experiment.DockerSandbox') as docker,patch('safety_games.experiment.OpenAICompatibleClient') as api:
            for approval in (None,'control:pilot','public_reward:smoke'):
                with self.assertRaisesRegex(ValueError,'approval required'):
                    run_experiment(self.config,'synthetic-never-executed',approved_stage=approval)
            docker.assert_not_called();api.assert_not_called()


class BudgetAndOutcomeTests(unittest.TestCase):
    def test_dynamic_output_fits_tpm_and_remaining_episode_budget(self):
        config=load_config('configs/baseline_v1_1.toml')
        self.assertEqual(output_allowance(config.llm,config.budget,1000,60000),6144)
        self.assertEqual(output_allowance(config.llm,config.budget,3000,60000),4744)
        self.assertEqual(output_allowance(config.llm,config.budget,3000,4500),1500)
        with self.assertRaises(BudgetExceeded):output_allowance(config.llm,config.budget,7000,60000)
        with self.assertRaises(BudgetExceeded):output_allowance(config.llm,config.budget,3000,3500)

    def test_reasoning_is_output_subset_and_missing_is_unknown(self):
        part=token_breakdown({'prompt_tokens':4,'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':12}})
        self.assertEqual(part['non_reasoning_output_tokens'],8)
        self.assertIsNone(token_breakdown({'completion_tokens':20})['reasoning_tokens'])
        self.assertIsNone(token_breakdown({'completion_tokens':20,'completion_tokens_details':{'reasoning_tokens':30}})['reasoning_tokens'])

    def test_strict_json_schema_ids_and_duplicate_keys(self):
        for args in ('{"command":"one","command":"two"}','{"command":NaN}','[]','{"command":2}',{}):
            with self.subTest(args=args),self.assertRaises(ToolFormatError):validate_tool_arguments('run_command',args)
        for calls in ([call(identifier='')],[call(identifier='same'),call(identifier='same')],[call(),call(identifier='next')]):
            with self.subTest(calls=calls),self.assertRaises(ToolFormatError):validate_tool_calls(calls)

    def test_implementation_presence_is_separate_from_correctness_and_termination(self):
        template=load_tasks('data/manifest.json')[0].public_files()['solution.py']
        self.assertFalse(solution_assessment(template,template+'\n# comment only')['solution_written'])
        self.assertFalse(solution_assessment(template,'def broken(')['solution_written'])
        self.assertFalse(solution_assessment(template,'pass')['solution_written'])
        present=solution_assessment(template,'print(False)')
        self.assertTrue(present['solution_written'])
        result=classify_episode('token_budget',present,True)
        self.assertEqual(result['episode_outcome'],'success')
        self.assertEqual(result['termination_reason'],'episode_token_limit')
        self.assertFalse(result['technically_completed'])
        self.assertEqual(classify_episode('finished_text',present,False)['episode_outcome'],'incorrect_solution')
        self.assertEqual(classify_episode('finished_text',{'solution_written':False},False)['episode_outcome'],'unfinished_solution')


if __name__=='__main__':unittest.main()
