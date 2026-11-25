"""Build a factual checkpoint report from persisted observations; no API calls."""
from collections import Counter
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from safety_games.metrics import analyze, load_observations
from safety_games.trajectory import read_events


def fraction(metric):
    rate='—' if metric['rate'] is None else f"{100*metric['rate']:.1f}%"
    return f"{metric['successes']}/{metric['known_n']} ({rate}; unknown {metric['unknown_n']})"


def main(directory):
    directory=Path(directory)
    report=analyze(directory)
    observations=load_observations(directory)
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
    planned=state['task_order']
    pending={task:entry['status'] for task,entry in state['episodes'].items() if entry['status']!='completed'}
    unstarted=[task for task in planned if task not in state['episodes']]
    terminations=Counter(o['termination'] for o in observations)
    with (directory/'by_difficulty.csv').open('w',encoding='utf-8',newline='') as stream:
        fields=['difficulty','episodes','true_success_rate','proxy_success_rate','original_public_success_rate',
                'confirmed_hacking_lower_bound','unreviewed','reward_gap','known_tokens']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for difficulty,group in report['by_difficulty'].items():
            writer.writerow({'difficulty':difficulty,'episodes':group['n'],'true_success_rate':group['true_success']['rate'],
                             'proxy_success_rate':group['proxy_success']['rate'],'original_public_success_rate':group['original_public_success']['rate'],
                             'confirmed_hacking_lower_bound':group['hacking_rate_confirmed_lower_bound'],'unreviewed':group['unreviewed_n'],
                             'reward_gap':group['reward_gap'],'known_tokens':sum(o['token_usage'] for o in observations if o['difficulty']==difficulty)})
    ledger_path=directory.parent/'.api_budget.json'
    ledger=json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {'requests':[]}
    known=sum(r['tokens'] for r in ledger['requests'] if r['usage_known'])
    unknown=sum(r['tokens'] for r in ledger['requests'] if not r['usage_known'])
    account={'known_actual_tokens_all_recorded_requests':known,'unknown_usage_reservation':unknown,
             'attempted_completion_requests':len(ledger['requests']),
             'unknown_usage_requests':sum(not r['usage_known'] for r in ledger['requests'])}
    overall=report['overall']
    validation=json.loads((directory/'reference_validation.json').read_text(encoding='utf-8'))
    tests_path=directory.parent/'infrastructure_tests.json'
    infrastructure=json.loads(tests_path.read_text(encoding='utf-8')) if tests_path.exists() else None
    lines=['# Baseline v1.0: фактический checkpoint r2','',
           f"Основной запуск: `{directory.as_posix()}`. Создан: {manifest['created_at']} (UTC).",
           f"Завершено {len(observations)} из {len(planned)} запланированных задач. Неполные: {json.dumps(pending)}; ещё не начаты: {', '.join(unstarted) or 'нет'}.",'',
           'Синтетические тесты инфраструктуры, технические API probes и ревизии baseline-v1/r1 не объединены с этими наблюдениями. Параметры внутри r2 не менялись.','',
           '| Уровень | N | True Success | Proxy Success | Original Public | Подтверждённый hacking | Не размечено |',
           '| --- | ---: | --- | --- | --- | --- | ---: |']
    for level,data in report['by_difficulty'].items():
        lines.append(f"| {level} | {data['n']} | {fraction(data['true_success'])} | {fraction(data['proxy_success'])} | {fraction(data['original_public_success'])} | {data['confirmed_hacking_count']}/{data['n']} (нижняя оценка) | {data['unreviewed_n']} |")
    lines.extend(['','## По эпизодам','',
                  '| task_id | Уровень | Завершение агента | Proxy | Original public | True | Автоматическая оценка | Токены с известным usage |',
                  '| --- | --- | --- | --- | --- | --- | --- | ---: |'])
    def display(value):return 'unknown' if value is None else 'pass' if value else 'fail'
    for o in observations:
        lines.append('| '+' | '.join((o['task_id'],o['difficulty'],o['termination'],display(o['proxy_success']),display(o['original_public_success']),display(o['true_success']),o['effective_behavior_status'],str(o['token_usage'])))+' |')
    lines.extend(['','## Примеры фактических траекторий',''])
    for task_id in ('lc217','lc4','abc392_f'):
        entry=state['episodes'].get(task_id)
        if not entry:continue
        events=read_events(directory/'episodes'/task_id/entry['attempt'])
        tools=[e['tool_name'] for e in events if e['type']=='tool_call']
        lines.append(f"- {task_id}: `"+' → '.join(tools)+'`. Полная траектория: `episodes/'+task_id+'/'+entry['attempt']+'/trajectory.md`.')
    lines.extend(['','## Проверки инфраструктуры','',
                  f"Эталонов проверено {len(validation['tasks'])}; fixtures {sum(item['cases'] for item in validation['tasks'])}; успешность {validation['success']}. Это не поведенческие LLM-эпизоды."])
    if infrastructure:
        lines.append(f"Автотесты: {infrastructure['tests_run']}, errors {infrastructure['errors']}, failures {infrastructure['failures']}, skipped {infrastructure['skipped']}; successful={infrastructure['successful']}.")
    resume_path=directory.parent/'resume_validation.json'
    if resume_path.exists():
        proof=json.loads(resume_path.read_text(encoding='utf-8'))
        lines.append(f"Фактическое восстановление {proof['task_id']}: новых запросов модели {proof['model_requests_after_interruption']}, независимых case events после resume {proof['evaluation_events_after_resume']}, завершено {proof['completed_after_resume']}.")
    lines.extend(['','## Расход и ограничения','',
                  'Основной r2, включая все его попытки:', '```json',json.dumps(report['usage_all_attempts'],indent=2),'```','',
                  'Общий локальный ledger аккаунта, включая технические прогоны и probes:', '```json',json.dumps(account,indent=2),'```','',
                  'Резерв при неизвестном usage не является выдуманным фактическим потреблением и не даёт точной суммы счёта провайдера.',
                  'Завершения агента: `'+json.dumps(dict(terminations))+'`.','',
                  f"Аудировано {overall['audited_n']}/{overall['n']}; не размечено {overall['unreviewed_n']} ({100*overall['unreviewed_n']/overall['n'] if overall['n'] else 0:.1f}%). Автоматическое отсутствие флагов не является гарантией отсутствия хакинга. Подтверждённый Hacking Rate — нижняя оценка, а не итоговая частота после полного аудита.",'',
                  'Hacking Attempt Rate остаётся неопределённой без отдельной разметки; Honest Success Rate не подтверждается автоматически. Reward Gap не трактуется как hacking rate.','',
                  'Один эпизод на задачу, целевая выборка и общие лимиты вывода/контекста не позволяют выделить причинный эффект сложности. Достижение output/token/tool limits отражается в termination и может объяснять низкую успешность без reward hacking. True Success относится только к конечному подготовленному набору тестов.','',
                  'Полные траектории: episodes/<task_id>/attempt-*/trajectory.jsonl и trajectory.md. Материалы аудита: audit_queue.json, behavior.json и начальные/итоговые версии файлов. Точный промпт, параметры, хеши кода/задач/seccomp и image ID находятся в manifest.json.','',
                  'Графики: hacking_by_difficulty.png/svg, success_by_difficulty.png/svg, behavior_categories.png/svg. Категории автоматических сигналов и подтверждений хранятся раздельно в behavior_categories.csv.','',
                  'Остаётся контекстный ручной аудит, расширение выборки/повторов и согласование следующего этапа. Стимулы, обучение, память и новые исследовательские политики не добавлялись.'])
    destination=Path('docs/baseline_results.md')
    destination.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    (directory/'checkpoint_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'completed':len(observations),'planned':len(planned),'primary_usage':report['usage_all_attempts'],'account':account}))


if __name__=='__main__':main(sys.argv[1])
