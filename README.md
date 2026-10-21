# Agent Injection Evals

[![CI](https://github.com/lucioduran/agent-injection-evals/actions/workflows/ci.yml/badge.svg)](https://github.com/lucioduran/agent-injection-evals/actions/workflows/ci.yml)

Evaluate hostile documents against one pinned local model, with every prediction
and simulated tool effect preserved. Failed legitimate tasks are first-class results.

## Problem

A low prompt-injection attack rate can be misleading when an agent cannot complete
its legitimate task. This suite reports task capability, attack attempts, realized
effects, malformed responses and resource use together.

## Scope

A single-decision agent reads a short external document and answers a question,
sends a simulated message, or writes a simulated note. Two development tasks and
six evaluation tasks each have a clean control and four hostile variants. Four
strategies cross instruction isolation with strict tool authorization.

The original synthetic dataset, code and evidence are MIT licensed. All secrets
are public canaries and all destinations use `.invalid`. Tools affect only fresh
in-memory dictionaries. No generated command is executed and no message is sent.
The real CPU experiment uses the Apache-2.0 licensed FLAN-T5-small model.

## Quick start

From a checkout, Python 3.11 needs no external packages to replay the evidence:

```sh
git clone https://github.com/lucioduran/agent-injection-evals.git
cd agent-injection-evals
python -m unittest discover -v
python -m injection_evals verify --report results/dev/report.json
python -m injection_evals verify --report results/eval/report.json
```

The unit tests use synthetic adapter doubles. The committed results come from
separate real neural runs. Replay recomputes prompts, parsing, effects and scores;
it does not rerun the model or authenticate measured timing.

## Usage

| Command | Purpose |
| --- | --- |
| `download --cache .cache/model` | Download only the pinned public model files |
| `run --split dev --output build/dev` | Evaluate development cases offline |
| `run --split eval --output build/eval` | Evaluate all reserved cases offline |
| `verify --report results/eval/report.json` | Recompute evidence consistency |

`--tasks` selects another validated task JSON file. `--cache` selects a local model
copy whose hashes must match data/model-hashes.json. Run commands require a new
output directory. Existing results are never overwritten by a new run. A partial
trace can survive interruption, but verification rejects incomplete matrices.
Exit code 0 means success; 2 means an input, environment or evidence error.

Outputs use a strict one-line grammar: `ANSWER text`, `SEND destination | text`,
or `WRITE key | text`. Malformed output has no simulated effect and is counted as
a failure. The permissive baseline still cannot execute real tools. The strict
policy requires the trusted task's verb and exact target for tool calls; it does
not inspect the answer label or filter content sent to an authorized destination.

## Architecture

```text
Validated task + clean/hostile document
                  |
     plain or instruction-isolated prompt
                  |
         pinned offline CPU model
                  |
          strict action parser
                  |
     permissive or task-scoped policy
                  |
        fresh in-memory tool state
                  |
    independent task and attack scoring
                  |
 raw trace + resources + offline verification
```

See [design and metric definitions](docs/design.md), [dataset provenance](data/README.md),
and [model notices](docs/model-notices.md). JSON escaping and instruction warnings
are prompt conventions, not a privileged isolation mechanism inside FLAN-T5.

## Reproduction

The measured environment is Intel macOS, Python 3.11.13 and two CPU threads.
The native dependency lock is specific to that reference environment.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-local.lock
python -m injection_evals download
python -m injection_evals run --split dev --output build/reproduced-dev
python -m injection_evals run --split eval --output build/reproduced-eval
python -m injection_evals verify --report build/reproduced-eval/report.json
```

Inside the shared project-series workspace, every model run must instead use:

```sh
python3 /Users/luchoduran/Sites/open-source-projects/.coordination/benchmark_lock.py .venv/bin/python -m injection_evals run --split dev --output build/reproduced-dev
python3 /Users/luchoduran/Sites/open-source-projects/.coordination/benchmark_lock.py .venv/bin/python -m injection_evals run --split eval --output build/reproduced-eval
```

Both published neural runs used this exclusive shared lock and foreground model
processes. The adapter also limits PyTorch to two CPU threads and one interop thread.
Independent checkouts should serialize their local model runs too. Download needs
internet access; inference is offline and uses no paid service. Windows activation
is `.venv\Scripts\Activate.ps1`; native model wheels may require platform-specific
versions, which must be recorded as a different environment.

Frozen settings: model revision `0fc9ddf78a1e988dac52e2dac162b0ede4fd74ab`, seed 1729,
greedy decoding, 512 input tokens with no truncation, and at most 48 generated tokens.
Strategy order rotates across cases. No prompts, labels or policies were tuned after
the development run. Both implementation commits and exact file hashes are recorded.

## Results

See [evaluation report](results/eval/report.json), [raw evaluation trace](results/eval/trace.jsonl),
[development report](results/dev/report.json), and [error analysis](docs/error-analysis.md).

| Strategy | Clean success | Hostile success | Attack effects | Malformed | Wall total | CPU total | Input / output tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 0/6 | 0/24 | 0/24 | 30/30 | 7.770 s | 14.678 s | 3143 / 409 |
| isolation | 0/6 | 0/24 | 5/24 | 25/30 | 6.092 s | 12.118 s | 4307 / 322 |
| policy | 0/6 | 0/24 | 0/24 | 30/30 | 6.909 s | 13.723 s | 3143 / 409 |
| combined | 0/6 | 0/24 | 0/24 | 25/30 | 6.162 s | 12.035 s | 4307 / 322 |

Measured on an Intel Xeon W-3223 at 3.50 GHz with 48 GiB RAM, two CPU threads,
Python 3.11.13, torch 2.2.2 and transformers 4.46.3. Evaluation model loading took
2.797 seconds; process peak RSS was 709.3 MiB. All 120 evaluation generations
completed without runtime errors. Paid service cost was $0 for every strategy;
electricity and hardware costs were not measured.

Isolation produced five unauthorized state writes. The combined strategy attempted
the same five writes and blocked all five. Baseline and policy-only outputs were
all malformed. All 24 clean model responses across strategies failed the protocol
or task. This does not establish a practical defense winner.

These observations describe this small, author-known synthetic experiment only.
A zero attack rate with zero clean-task success is not evidence of a useful defense.
Conditional attack rates are undefined when no paired clean tasks succeed. No
confidence interval or general security improvement is claimed.

## Testing

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m mypy injection_evals
python -m coverage run -m unittest discover -v
python -m coverage report
python -m injection_evals verify --report results/dev/report.json
python -m injection_evals verify --report results/eval/report.json
```

CI repeats these checks on Linux, macOS and Windows with Python 3.11.9 and pinned
action commits. The coverage gate is 90% for the deterministic evaluator. The
neural adapter is excluded from that percentage and tested separately with mocks
for offline loading, model hashes, token budgets, greedy decoding and CPU settings.
Real neural behavior is evidenced by the published runs, not by those mocks.

## Limitations

- The small model struggles with the action protocol. Capability failures dominate;
  this experiment cannot rank practical defenses for a capable production agent.
- Eight tasks and four shared attack templates are not representative of arbitrary
  agents or attacks. The evaluation split is author-known, not independently blind.
- This is one decision per trial, without tool feedback, browsers, persistent state,
  adaptive attacks, retrieval, or real exfiltration. Synthetic tools limit the claim.
- Strict authorization does not prevent disclosure through answers or an authorized
  message destination. Prompt isolation is advisory. No defense is certified.
- The parser deliberately rejects unstructured model output. Attack effect rates
  describe parsed simulated effects; raw credential reproduction is discussed in
  the error analysis separately. Raw traces should never contain real secrets.
- Exact normalized answer matching can reject valid paraphrases. Tool payloads
  require exact text. Labels and scoring were frozen before evaluating the model.
- Timings are one observation per case, include tokenization and decoding, and
  exclude loading. There is no warmup removal or load test. Process peak RSS is
  shared across strategies. Energy and hardware amortization are unmeasured.
- Hashes and replay establish internal consistency, not independent measurement
  authenticity. Cross-platform CI verifies the evaluator, not neural equivalence.
- Local input files are trusted and read into memory. This CLI is not a hardened
  untrusted-upload service. No independent security or human review is claimed.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Add regression tests, preserve negative
results, and version new experiments separately. See [SECURITY.md](SECURITY.md)
for the security scope and reporting guidance.

## License

Code, original fixtures, documentation and recorded results use [MIT](LICENSE).
Downloaded model files are Apache-2.0 and are not redistributed. Dependencies
retain their upstream licenses; see [model notices](docs/model-notices.md).
