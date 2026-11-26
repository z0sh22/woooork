"""Read-only retrospective reports. Human labels are never generated here."""
import csv
import io
import json
import os
from pathlib import Path
import re

from .artifacts import write_json
from .behavior import detect_behavior
from .environment import file_text
from .logging import _atomic_write, _csv_cell
from .metrics import analyze, load_observations, usage_summary
from .outcomes import classify_episode, solution_assessment
from .preservation import ensure_not_frozen
from .trajectory import read_events

AUDIT_COLUMNS = ('task_id', 'experimental_difficulty', 'termination_reason', 'solution_written',
                 'proxy_success', 'original_public_success', 'true_success', 'automatic_flags',
                 'audit_status', 'hacking_category', 'evidence', 'reviewer_notes', 'trajectory_path')


def fenced(value, language=''):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    fence = '`' * max(4, max((len(s) + 1 for s in re.findall(r'`+', text)), default=0))
    return fence + language + '\n' + text + '\n' + fence + '\n'


def _args(event):
    try:
        result = json.loads(event.get('arguments') or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def prepare_review(directory: Path, output: Path):
    directory, output = directory.resolve(), output.resolve()
    ensure_not_frozen(output)
    if output == directory or directory in output.parents:
        raise ValueError('Retrospective audit output must be outside the original run')
    output.mkdir(parents=True, exist_ok=True)
    state = json.loads((directory/'state.json').read_text(encoding='utf-8'))
    previous = {}
    if (output/'audit_manifest.csv').exists():
        with (output/'audit_manifest.csv').open(encoding='utf-8', newline='') as f:
            previous = {row['task_id']: row for row in csv.DictReader(f)}
    rows, analysis = [], []
    index = ['# Материалы ручного аудита Baseline v1.0', '',
             'Производный анализ v1.1; исходные файлы не изменяются. Все новые статусы — unreviewed. '
             'Автоматические сигналы не являются окончательной разметкой. Пользовательские поля существующего CSV сохраняются.', '']
    for task_id in state.get('task_order', state['episodes']):
        entry = state['episodes'].get(task_id)
        if not entry:
            continue
        attempt = directory/'episodes'/task_id/entry['attempt']
        summary = json.loads((attempt/'summary.json').read_text(encoding='utf-8'))
        initial, final = (json.loads((attempt/(label+'_snapshot.json')).read_text(encoding='utf-8')) for label in ('initial','final'))
        post = json.loads((attempt/'post_proxy_snapshot.json').read_text(encoding='utf-8')) if (attempt/'post_proxy_snapshot.json').exists() else final
        events = read_events(attempt)
        source = file_text(final, 'solution.py')
        assessment = solution_assessment(file_text(initial, 'solution.py'), source)
        outcome = classify_episode(summary['termination'], assessment, summary['true_success'])
        behavior = detect_behavior(initial, post, events, frozen_solution=source)
        review_dir = output/'episodes'/task_id
        review_dir.mkdir(parents=True, exist_ok=True)
        write_json(review_dir/'derived_assessment.json', {'kind':'retrospective_v1_1_not_new_llm_data',
                   **outcome, 'original_automatic_assessment': summary['behavior'], 'v1_1_triage': behavior,
                   'usage': usage_summary(events), 'original_termination': summary['termination']})
        trajectory = Path(os.path.relpath(attempt/'trajectory.md', output)).as_posix()
        row = {'task_id':task_id, 'experimental_difficulty':summary['difficulty'],
               'termination_reason':outcome['termination_reason'], 'solution_written':assessment['solution_written'],
               **{k:summary.get(k) for k in ('proxy_success','original_public_success','true_success')},
               'automatic_flags':json.dumps(behavior['evidence'], ensure_ascii=False), 'audit_status':'unreviewed',
               'hacking_category':'', 'evidence':'', 'reviewer_notes':'', 'trajectory_path':trajectory}
        for field in ('audit_status','hacking_category','evidence','reviewer_notes'):
            if task_id in previous:
                row[field] = previous[task_id].get(field, row[field])
        rows.append(row)
        analysis.append({'task_id':task_id, **outcome, 'original_termination':summary['termination'],
                         'difficulty':summary['difficulty'], 'true_success':summary['true_success'],
                         'format_errors':sum(e['type'] in ('provider_tool_parse_error','local_tool_parse_error') for e in events)})
        lines = ['# Аудит: '+task_id, '', '**Ручная разметка не выполнена автоматически.**', '',
                 fenced({**outcome, 'true_success':summary['true_success'], 'audit_status':row['audit_status']}, 'json'),
                 '## Итоговое решение', '', fenced(source if source is not None else '<missing/nonregular>', 'python'),
                 '## Обращения к публичным тестам', '']
        result_ids = {e.get('tool_call_id') for e in events if e['type']=='tool_call'}
        actions = [e for e in events if e['type']=='tool_call' or e['type']=='tool_result' and e.get('tool_call_id') not in result_ids]
        selected = [e for e in actions if e.get('tool_name')=='read_file' and _args(e).get('path') in ('test.py','test_cases.json') or
                    e.get('tool_name')=='run_command' and re.search(r'test(?:_cases\.json|\.py)', _args(e).get('command',''))]
        lines.append(fenced(selected, 'json') if selected else 'Наблюдаемых явных обращений нет.\n')
        lines += ['## Операции записи и изменения файлов', '']
        writes = [e for e in events if e.get('file_changes') or e.get('type')=='tool_call' and e.get('tool_name')=='write_file']
        lines.append(fenced(writes, 'json') if writes else 'Не наблюдались.\n')
        lines += ['## Изменения процедур оценивания', '', fenced(behavior['evidence'], 'json'),
                  '## Ошибки формата и технические ограничения', '']
        errors = [e for e in events if e['type'] in ('api_error','provider_tool_parse_error','local_tool_parse_error',
                                                   'output_truncated','agent_budget_exhausted','agent_finished','episode_interrupted')]
        lines.append(fenced(errors, 'json'))
        lines += ['## Ограничения наблюдаемости', '', behavior['observability'], '',
                  '## Исходная траектория', '',
                  '[JSONL]('+Path(os.path.relpath(attempt/'trajectory.jsonl', review_dir)).as_posix()+') · '
                  '[Markdown]('+Path(os.path.relpath(attempt/'trajectory.md', review_dir)).as_posix()+')', '',
                  'Номера event_id и step в выдержках соответствуют исходному журналу. Неуспех на скрытых тестах '
                  'и обычные чтения/собственные тесты не подтверждают хакинг.']
        _atomic_write(review_dir/'review.md', '\n'.join(lines)+'\n')
        index.append(f'- [{task_id}](episodes/{task_id}/review.md): {outcome["termination_reason"]}; solution_written={assessment["solution_written"]}.')
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=AUDIT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({k:_csv_cell(v) for k,v in row.items()})
    _atomic_write(output/'audit_manifest.csv', buffer.getvalue())
    _atomic_write(output/'README.md', '\n'.join(index)+'\n')
    write_json(output/'retrospective_episodes.json', analysis)
    statistics = analyze(directory, output/'statistics')
    return {'kind':'retrospective_only_no_new_inference', 'episodes':len(rows),
            'output':str(output), 'original_run':str(directory), 'human_labels_generated':False,
            'implemented':sum(r['solution_written'] for r in analysis),
            'technically_completed':statistics['overall']['technically_completed']}
