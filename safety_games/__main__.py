"""Infrastructure checks; deliberately no experiment runner or agent prompts."""

import argparse
from dataclasses import asdict
import json
import sys

from .config import ConfigError, load_config
from .sandbox import DockerSandbox, ExecutionStatus, SandboxError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Safety experiment infrastructure checks")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("check-config", "sandbox-check", "api-check", "validate-tasks", "run"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--config", default="configs/baseline.toml" if command in ('check-config','sandbox-check') else "configs/baseline_v1.toml")
        if command=='run':
            subparser.add_argument('--experiment-id',required=True)
            subparser.add_argument('--stage',choices=('smoke','pilot'),default='smoke')
            subparser.add_argument('--resume',action='store_true')
    analyze_parser=commands.add_parser('analyze')
    analyze_parser.add_argument('directory')
    audit_parser=commands.add_parser('audit')
    audit_parser.add_argument('episode_directory')
    audit_parser.add_argument('--status',required=True)
    audit_parser.add_argument('--reviewer',required=True)
    audit_parser.add_argument('--note',required=True)
    audit_parser.add_argument('--evidence-events',nargs='*',type=int,default=[])
    audit_parser.add_argument('--categories',nargs='*',default=[])
    audit_parser.add_argument('--honest-reviewed',action='store_true')
    arguments = parser.parse_args(argv)
    try:
        from pathlib import Path
        from .api import LLMError
        if arguments.command=='analyze':
            from .metrics import analyze
            print(json.dumps(analyze(arguments.directory),ensure_ascii=False,indent=2));return 0
        if arguments.command=='audit':
            from .audit import add_annotation
            add_annotation(Path(arguments.episode_directory),status=arguments.status,reviewer=arguments.reviewer,note=arguments.note,
                           evidence_events=arguments.evidence_events,categories=arguments.categories,honest_reviewed=arguments.honest_reviewed)
            return 0
        config = load_config(arguments.config)
        if arguments.command == "check-config":
            print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if arguments.command=='api-check':
            from .api import OpenAICompatibleClient,QuotaLedger
            from .experiment import enforce_baseline
            enforce_baseline(config)
            client=OpenAICompatibleClient(config.llm,QuotaLedger(config.output_dir/'.api_budget.json',config.budget))
            print(json.dumps(client.check_model()));return 0
        if arguments.command=='validate-tasks':
            from .tasks import load_tasks
            from .evaluator import validate_references
            validate_references(load_tasks(config.task_manifest),DockerSandbox(config.sandbox),config.output_dir/'reference_validation.json')
            return 0
        if arguments.command=='run':
            from .experiment import run_experiment
            print(run_experiment(config,arguments.experiment_id,stage=arguments.stage,resume=arguments.resume));return 0
        result = DockerSandbox(config.sandbox).run('print("sandbox-ok")')
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0 if result.status is ExecutionStatus.OK and result.stdout == "sandbox-ok\n" else 1
    except (ConfigError, OSError, SandboxError, LLMError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
