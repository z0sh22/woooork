"""Inventory requested implementation files; exclude secrets/user papers/results."""
from pathlib import Path

original={
    'pyproject.toml','.gitignore','README.md','.github/workflows/tests.yml','configs/baseline.toml',
    'safety_games/__init__.py','safety_games/__main__.py','safety_games/config.py','safety_games/llm.py',
    'safety_games/results.py','safety_games/logging.py','safety_games/sandbox.py','sandbox/Dockerfile',
    'sandbox/.dockerignore','sandbox/execute.py','tests/__init__.py','tests/test_cli.py','tests/test_config.py',
    'tests/test_llm.py','tests/test_logging.py','tests/test_sandbox.py','tests/test_sandbox_integration.py',
    'docs/architecture.md','docs/sandbox.md'}
modified={
    'pyproject.toml','.gitignore','README.md','.github/workflows/tests.yml','safety_games/__init__.py',
    'safety_games/__main__.py','safety_games/config.py','safety_games/sandbox.py','sandbox/Dockerfile',
    'sandbox/.dockerignore','sandbox/execute.py','docs/architecture.md','docs/sandbox.md'}
files=[]
for base in ('safety_games','sandbox','tests','configs','prompts','data','docs','scripts','third_party','.github'):
    for path in Path(base).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':files.append(path.as_posix())
files.extend(p for p in ('pyproject.toml','requirements.txt','.env.example','.gitignore','.gitattributes','README.md') if Path(p).exists())
files=sorted(set(files)|{'docs/implementation_inventory.md'})
lines=['# Созданные и изменённые файлы','',
       'Пользовательские PDF и .env не изменялись. .venv, .research_tools, .research_cache и результаты находятся отдельно и в этот список реализации не включены.','',
       '| Файл | Статус относительно исходного каркаса |','| --- | --- |']
for name in files:
    status='изменён' if name in modified else 'сохранён' if name in original else 'создан'
    lines.append(f'| `{name}` | {status} |')
Path('docs/implementation_inventory.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
print('implementation_files',len(files),'new',sum(f not in original for f in files),'modified',len(modified))
