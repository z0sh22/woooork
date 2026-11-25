import unittest

from safety_games.config import LLMConfig
from safety_games.llm import GenerationRequest, LLMClient, LLMError, LLMResponse, Message


class ContractAdapter(LLMClient):
    """Test fixture only: no inference and no experimental observations."""

    def generate(self, request):
        if request.seed is not None:
            raise LLMError("seed is unsupported by this test adapter")
        return LLMResponse(text=request.messages[0].content, model=request.config.model)


class LLMTests(unittest.TestCase):
    def test_base_class_requires_an_adapter(self):
        with self.assertRaises(TypeError):
            LLMClient()

    def test_same_contract_supports_api_and_local_backends(self):
        for backend in ("api", "local"):
            with self.subTest(backend=backend):
                request = GenerationRequest((Message("user", "contract-input"),), LLMConfig(backend=backend))
                response = ContractAdapter().generate(request)
                self.assertEqual(response.text, "contract-input")
                self.assertIsNone(response.input_tokens)

    def test_unsupported_setting_is_an_explicit_error(self):
        request = GenerationRequest((Message("user", "contract-input"),), LLMConfig(), seed=1)
        with self.assertRaises(LLMError):
            ContractAdapter().generate(request)

    def test_request_and_response_validation(self):
        with self.assertRaises(ValueError):
            GenerationRequest((), LLMConfig())
        with self.assertRaises(ValueError):
            Message("tool", "contract-input")
        with self.assertRaises(ValueError):
            LLMResponse("", "model", output_tokens=-1)


if __name__ == "__main__":
    unittest.main()
