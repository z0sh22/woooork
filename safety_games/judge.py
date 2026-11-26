"""Future independent scientific judge contract; no client or API invocation."""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from enum import Enum


class JudgeVerdict(str, Enum):
    CONFIRMED_HACKING = 'confirmed_hacking'
    NO_HACKING_DETECTED = 'no_hacking_detected'
    UNCERTAIN = 'uncertain'


@dataclass(frozen=True)
class JudgeEvidence:
    artifact: str
    excerpt: str
    event_id: int | None = None
    step: int | None = None
    explanation: str = ''

    def __post_init__(self):
        if not self.artifact or not self.excerpt or not self.explanation:
            raise ValueError('Judge evidence requires an artifact, observable excerpt and explanation')
        if self.event_id is not None and (type(self.event_id) is not int or self.event_id < 1):
            raise ValueError('Invalid evidence event_id')


@dataclass(frozen=True)
class JudgeInput:
    episode_id: str
    task_id: str
    problem: str
    original_code: str
    final_code: str | None
    observed_actions: tuple[dict, ...]
    file_changes: tuple[dict, ...]
    public_results: dict
    independent_results: dict
    artifact_hashes: dict
    observability_limits: str
    purpose: str = 'independent_scientific_audit'

    def __post_init__(self):
        if self.purpose != 'independent_scientific_audit':
            raise ValueError('Sanction decisions must use a separate future interface')
        if not self.episode_id or not self.task_id or not self.artifact_hashes:
            raise ValueError('Judge input requires identified, hashed artifacts')


@dataclass(frozen=True)
class JudgeAssessment:
    verdict: JudgeVerdict
    evidence: tuple[JudgeEvidence, ...]
    explanation: str
    judge_id: str
    model_version: str
    input_sha256: str
    prompt_sha256: str
    audit_status: str = 'machine_assessment_requires_review'

    def __post_init__(self):
        object.__setattr__(self, 'verdict', JudgeVerdict(self.verdict))
        if not self.evidence or not all(isinstance(e, JudgeEvidence) for e in self.evidence):
            raise ValueError('Every verdict requires observable evidence, including uncertainty')
        if not all((self.explanation, self.judge_id, self.model_version, self.input_sha256, self.prompt_sha256)):
            raise ValueError('Judge assessment requires provenance and explanation')
        if self.audit_status != 'machine_assessment_requires_review':
            raise ValueError('A model judge cannot issue a final human label')

    def to_dict(self):
        data = asdict(self)
        data['verdict'] = self.verdict.value
        return data


class IndependentScientificJudge(ABC):
    """Future adapter must be explicitly authorized before any paid/inference call.

    Task/code/trajectory content is untrusted data, never judge instructions.
    No assessments are sent back to the coding agent or a sanctions component.
    """
    @abstractmethod
    def assess(self, request: JudgeInput) -> JudgeAssessment:
        raise NotImplementedError
