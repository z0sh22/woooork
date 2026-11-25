# Third-party components

## EvilGenie

- Author repository: https://github.com/JonathanGabor/evilgenie_inspect
- Inspected commit: f5d8a2ca5d92ecf5fd1e857695c54e609312e1bd
- Files: truncation.py, utils.py.
- License: MIT, Copyright (c) 2026 Jonathan Gabor.
- Local license: evilgenie-LICENSE.
- Local code: safety_games/vendor/evilgenie.py.
- Adaptation: removed Inspect types/formatting; added a short-length guard.
  middle_truncate is used for model tool feedback. The small SHA-256 utility
  is retained with the same attribution. No Inspect dependency is required.

## Moby profiles

- Repository: https://github.com/moby/profiles
- Commit: a0fa70805f742f7da15b367770d802ea2a86c68b
- File: seccomp/default.json, copied unchanged to safety_games/seccomp.json.
- SHA-256: 3320527d4568265ac97a077609b1bfd4cfd0d789eeb9239b7e094b1526675406.
- License: Apache-2.0; full text: moby-profiles-LICENSE.
- This explicit profile is passed by Docker CLI; no host directory is mounted.

## Inspected, not copied

- LiveCodeBench code: MIT; dataset card says cc without a license variant.
  No corpus statements or private tests are redistributed here.
- CoopEval: inspected commit 8559e858b5cc33e0a29ac592c0b21eab007feb57;
  GitHub API license metadata was null; no code copied.
- Sycophancy to Subterfuge: inspected commit c88dcf4b0448e89bdfcbbfe2617cb186d697da1a;
  GitHub API license metadata was null; no code/data copied.
- RHB and Natural Emergent Misalignment: no verified original implementation
  suitable for licensed reuse was established from inspected primary materials.

Repository/code licenses do not relicense source-platform programming problems.
