# Набор задач Baseline v1.0

Активный набор — ровно 15 записей manifest.json. В каждом task.json находятся
метаданные, условие, ограничения, JSON-интерфейс, 3 публичных и 13 скрытых
собственных тестов. reference.py — самостоятельный эталон. Полные task.json и
reference.py доступны только контроллеру; агент получает четыре публичных файла.

| task_id | Название | Исходный уровень | Экспериментальный уровень | Категория | Источник |
| --- | --- | --- | --- | --- | --- |
| lc217 | Contains Duplicate | Easy | easy | hashing / arrays | [source](https://leetcode.com/problems/contains-duplicate/) |
| lc3 | Longest Substring Without Repeating Characters | Medium | easy | sliding window / strings | [source](https://leetcode.com/problems/longest-substring-without-repeating-characters/) |
| lc33 | Search in Rotated Sorted Array | Medium | easy | binary search | [source](https://leetcode.com/problems/search-in-rotated-sorted-array/) |
| lc200 | Number of Islands | Medium | easy | graphs / flood fill | [source](https://leetcode.com/problems/number-of-islands/) |
| lc322 | Coin Change | Medium | easy | dynamic programming | [source](https://leetcode.com/problems/coin-change/) |
| lc4 | Median of Two Sorted Arrays | Hard | medium | binary search / order statistics | [source](https://leetcode.com/problems/median-of-two-sorted-arrays/) |
| lc32 | Longest Valid Parentheses | Hard | medium | stack / strings | [source](https://leetcode.com/problems/longest-valid-parentheses/) |
| lc42 | Trapping Rain Water | Hard | medium | two pointers / arrays | [source](https://leetcode.com/problems/trapping-rain-water/) |
| lc10 | Regular Expression Matching | Hard | medium | dynamic programming / strings | [source](https://leetcode.com/problems/regular-expression-matching/) |
| lc329 | Longest Increasing Path in a Matrix | Hard | medium | DAG / dynamic programming | [source](https://leetcode.com/problems/longest-increasing-path-in-a-matrix/) |
| abc389_e | Square Price | Hard (LiveCodeBench) | hard | parametric search / convex allocation | [source](https://atcoder.jp/contests/abc389/tasks/abc389_e) |
| abc390_e | Vitamin Balance | Hard (LiveCodeBench) | hard | knapsack / binary search | [source](https://atcoder.jp/contests/abc390/tasks/abc390_e) |
| abc391_f | K | Hard (LiveCodeBench) | hard | heap / best-first search | [source](https://atcoder.jp/contests/abc391/tasks/abc391_f) |
| abc391_e | Hierarchical Majority Vote | Hard (LiveCodeBench) | hard | tree dynamic programming | [source](https://atcoder.jp/contests/abc391/tasks/abc391_e) |
| abc392_f | Insert | Hard (LiveCodeBench) | hard | Fenwick tree / order statistics | [source](https://atcoder.jp/contests/abc392/tasks/abc392_f) |

## Происхождение и адаптация

Формулировки, интерфейсные адаптации, тесты и эталоны написаны для проекта.
Доступ к закрытым платформенным тестам не заявляется. Увеличенные случаи
проверяют отдельные ресурсные ошибки, но не полностью покрывают исходные
максимальные ограничения и требования асимптотики. True Success относится
только к подготовленному независимому набору.

Генератор: scripts/build_tasks.py, seed 20261125. При перегенерации обновляются
task/reference SHA-256 в manifest.json; изменение набора требует нового
experiment ID. .gitattributes фиксирует LF для устойчивых байтовых хешей.
Используются альтернативные малые oracle и Docker-проверка эталонов.

Для пяти AtCoder-задач Hard — метаданные LiveCodeBench release_v6/test6.jsonl,
не приписанная AtCoder шкала. У abc391_f сохранено название K из dataset;
текущая первичная страница называет её K-th Largest Triplet.

[Карточка LiveCodeBench](https://huggingface.co/datasets/livecodebench/code_generation_lite)
не указывает конкретный вариант CC. Проверенный test6.jsonl имеет опубликованный
LFS SHA-256 bb4c364f71921c4495a6ad15abe1a927350b720009f4933e2e71f8af0f6fd1f5.
Получен только ограниченный фрагмент 16 MiB, без запуска loader и unpickle
приватных данных. Корпус и оригинальные приватные тесты не включены в проект.

LeetCode 72 исключена после проверки уровня Medium; включена LeetCode 10 Hard.
Техническая ревизия r1 хранится отдельно. Платформенные тексты/данные не
перелицензируются: см. docs/literature_review.md и third_party/NOTICE.md.
Онлайн-системы оценки и реальные аккаунты платформ не используются.
