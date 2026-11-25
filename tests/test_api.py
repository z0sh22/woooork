from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

from safety_games.api import BudgetExceeded, OpenAICompatibleClient, QuotaLedger, retry_delay
from safety_games.config import APIBudgetConfig, LLMConfig
from safety_games.llm import LLMError


class Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())


class Opener:
    def __init__(self, *responses):
        self.responses=list(responses);self.requests=[]
    def open(self, request, timeout):
        self.requests.append(request)
        result=self.responses.pop(0)
        if isinstance(result, Exception):raise result
        return Response(result)


def completion():
    return {'id':'unit-test-request','model':'openai/gpt-oss-20b',
            'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[]},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}


class APITests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.path=Path(self.temporary.name)/'quota.json'
        self.events=[];self.sleeps=[]
        self.config=LLMConfig(model='openai/gpt-oss-20b',max_output_tokens=32,api_key_env='GROQ_API_KEY')
    def client(self, opener):
        return OpenAICompatibleClient(self.config,QuotaLedger(self.path,APIBudgetConfig()),key='test-secret-key',
                                      opener=opener,sleep=self.sleeps.append,event=self.events.append)

    def test_function_tools_only_and_no_credentials_in_payload_or_events(self):
        opener=Opener(completion())
        turn=self.client(opener).complete([{'role':'user','content':'fixture'}],[{'type':'function','function':{'name':'fixture','parameters':{}}}])
        payload=json.loads(opener.requests[0].data)
        self.assertEqual(payload['model'],'openai/gpt-oss-20b')
        self.assertFalse(payload['parallel_tool_calls'])
        self.assertEqual(payload['reasoning_effort'],'medium')
        self.assertNotIn('reasoning_format',payload)
        self.assertNotIn('test-secret-key',json.dumps(payload)+json.dumps(self.events))
        self.assertEqual(turn.usage['total_tokens'],15)
        self.assertEqual(json.loads(self.path.read_text())['requests'][0]['tokens'],15)
        with self.assertRaises(LLMError):
            self.client(Opener()).complete([], [{'type':'browser_search'}])

    def test_429_retries_and_unknown_usage_is_retained(self):
        error=urllib.error.HTTPError('https://fixture.invalid',429,'limit',{'Retry-After':'7'},io.BytesIO(b'provider-secret'))
        client=self.client(Opener(error,completion()))
        turn=client.complete([],[])
        self.assertEqual(self.sleeps,[7])
        records=json.loads(self.path.read_text())['requests']
        self.assertEqual(len(records),2)
        self.assertFalse(records[0]['usage_known'])
        self.assertEqual(turn.charged_tokens,records[0]['tokens']+15)
        self.assertNotIn('provider-secret',json.dumps(self.events))

    def test_auth_error_is_not_retried_or_logged_verbatim(self):
        error=urllib.error.HTTPError('https://fixture.invalid',401,'key-invalid',{},io.BytesIO(b'test-secret-key'))
        with self.assertRaisesRegex(LLMError,'HTTP 401'):
            self.client(Opener(error)).complete([],[])
        self.assertEqual(self.sleeps,[])
        self.assertNotIn('test-secret-key',json.dumps(self.events))

    def test_provider_parse_failure_preserves_raw_evidence_without_fabricating_usage_or_call(self):
        raw={'error':{'code':'tool_use_failed','message':'parse error','failed_generation':'not valid JSON'}}
        error=urllib.error.HTTPError('https://fixture.invalid',400,'bad tool call',{},io.BytesIO(json.dumps(raw).encode()))
        turn=self.client(Opener(error)).complete([],[])
        self.assertEqual(turn.message,{})
        self.assertEqual(turn.usage,{})
        self.assertEqual(turn.tool_parse_error['failed_generation'],'not valid JSON')
        self.assertEqual(self.sleeps,[])

    def test_request_and_retry_budgets_are_enforced(self):
        opener=Opener(completion())
        with self.assertRaises(BudgetExceeded):
            self.client(opener).complete([],[],token_budget=1)
        self.assertEqual(opener.requests,[])

    def test_missing_usage_retains_reservation(self):
        result=completion();result.pop('usage')
        with self.assertRaises(LLMError):self.client(Opener(result)).complete([],[])
        self.assertFalse(json.loads(self.path.read_text())['requests'][0]['usage_known'])

    def test_model_probe_performs_no_completion(self):
        opener=Opener({'data':[{'id':'openai/gpt-oss-20b','active':True}]})
        self.assertFalse(self.client(opener).check_model()['inference_performed'])
        self.assertIsNone(opener.requests[0].data)

    def test_groq_workaround_is_explicit_and_keeps_only_function_definitions(self):
        opener=Opener(completion());client=self.client(opener)
        client.config=replace(client.config,groq_channel_workaround=True)
        client.complete([], [{'type':'function','function':{'name':'fixture','parameters':{}}}])
        payload=json.loads(opener.requests[0].data)
        self.assertTrue(payload['disable_tool_validation'])
        self.assertTrue(all(t['type']=='function' for t in payload['tools']))

    def test_retry_after_dates_and_excessive_wait(self):
        self.assertEqual(retry_delay('Thu, 01 Jan 1970 00:00:20 GMT',1,now=0),20)
        with self.assertRaises(BudgetExceeded):retry_delay('1000',1)

    def test_rolling_minute_and_persisted_daily_limits(self):
        now=[1000.0]
        sleeps=[]
        def sleep(delay):sleeps.append(delay);now[0]+=delay
        config=APIBudgetConfig(requests_per_minute=1,requests_per_day=2,tokens_per_minute=100,tokens_per_day=500,experiment_token_limit=500)
        ledger=QuotaLedger(self.path,config,clock=lambda:now[0],sleep=sleep)
        ledger.settle(ledger.reserve(50),10)
        ledger.reserve(50)
        self.assertGreaterEqual(sum(sleeps),60)
        with self.assertRaises(BudgetExceeded):QuotaLedger(self.path,config,clock=lambda:now[0],sleep=sleep).reserve(1)


if __name__=='__main__':unittest.main()
