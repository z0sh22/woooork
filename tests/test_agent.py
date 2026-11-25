from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from safety_games.agent import run_agent
from safety_games.api import ChatTurn, ToolCallingClient
from safety_games.config import ExperimentConfig, LLMConfig
from safety_games.tasks import load_tasks
from safety_games.trajectory import TrajectoryLogger, read_events
from tests.test_observation import snapshot


class ParseFailureClient(ToolCallingClient):
    def __init__(self,config):self.config=config
    def complete(self,messages,tools,**kwargs):
        return ChatTurn({}, {}, self.config.model,None,'tool_parse_error',100,{'code':'tool_use_failed','failed_generation':'invalid fixture'})


class AgentTests(unittest.TestCase):
    def test_parse_errors_are_bounded_and_not_fabricated_as_model_responses(self):
        config=ExperimentConfig(llm=LLMConfig(model='openai/gpt-oss-20b'))
        task=load_tasks('data/manifest.json')[0]
        environment=Mock();environment.snapshot.return_value=snapshot(task.public_files())
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            logger=TrajectoryLogger(path,experiment_id='fixture',run_id='fixture',episode_id='fixture',task_id=task.task_id)
            result=run_agent(task,environment,ParseFailureClient(config.llm),logger,config,'neutral fixture prompt')
            events=read_events(path)
            self.assertEqual(result['termination'],'tool_parse_limit')
            self.assertEqual(result['tool_parse_errors'],2)
            self.assertEqual(result['token_usage'],0)
            self.assertEqual(result['charged_tokens'],200)
            self.assertFalse(any(e['type']=='model_response' for e in events))
            self.assertEqual(sum(e['type']=='tool_parse_feedback' for e in events),1)
            environment.request.assert_not_called()


if __name__=='__main__':unittest.main()
