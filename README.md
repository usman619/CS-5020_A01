# IncidentZero Starter Repository

**Assignment 1 - Agentic Artificial Intelligence (Fall 2026)**  
**Domain:** bounded autonomous SRE / production-incident response  
**Mode:** individual assignment, plain Python + Groq SDK, no agent framework

This repository deliberately gives you a **working simulated production environment** and an **incomplete agent runtime**. Your job is not to build an API or a dashboard. Your job is to turn the baseline loop into a reliable agent that can observe, plan, act, verify, re-plan, recover from failures, respect human approval, and stop correctly under a strict budget.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows CMD
# cp .env.example .env   # Linux/macOS
```

Put your own key in `.env` or set `GROQ_API_KEY` in the shell. **Never submit the key.**

Generate your deterministic public scenarios (public-a, public-b and public-c) each time for the specific scenario you want to test on before running the main command:<br>

**For public-a:**
```bash
python scripts/generate_student_scenario.py --student-id 25I-7605 --scenario public-a
```

**For public-b:**
```bash
python scripts/generate_student_scenario.py --student-id 25I-7605 --scenario public-b
```

**For public-c:**
```bash
python scripts/generate_student_scenario.py --student-id 25I-7605 --scenario public-c
```

Validate the protected infrastructure (does not call Groq):

```bash
pytest -q tests/public -m infrastructure
python scripts/check_banned_imports.py
python scripts/check_protected_integrity.py
```

Run the full public test suite while developing:

```bash
pytest -q tests/public
```

Several student-requirement tests are expected to fail in the untouched starter. They are specifications, not bugs in the simulator.

The additional 10 test cases are located inside the `tests/public/test_student_requirements.py` file.
Live run with Groq:

**For public-a:**
```bash
python -m incidentzero.cli run --student-id 25I-7605 --scenario public-a --model openai/gpt-oss-20b
```

**For public-b:**
```bash
python -m incidentzero.cli run --student-id 25I-7605 --scenario public-b --model openai/gpt-oss-20b
```

**For public-c:**
```bash
python -m incidentzero.cli run --student-id 25I-7605 --scenario public-c --model openai/gpt-oss-20b
```
After running each scenario you can find its traces in  `traces/`folder.


## Report and AI Usage
The Assignment Report and AI Usage are available in the `docs/` folder.

## Stable contract

Read `docs/CONTRACTS.md` before editing. Hidden grading assumes those public interfaces still exist. You may refactor internally, but do not delete or rename required public classes/functions.

## Protected areas

Do not modify the simulator to make scenarios easier. The grader uses clean copies and additional hidden scenarios. In particular, do not depend on private fields or anything named `_oracle`, `_root_cause`, or `_scenario_spec`.

The point is to build a robust **controller**, not to reverse-engineer the answer from the simulator source.
