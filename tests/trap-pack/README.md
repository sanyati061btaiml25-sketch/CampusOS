# CampusOS Trap Pack Grader

This directory contains the offline grader for the official **Agentware 2026 Trap Pack** (20 hostile and control test cases).

## Isolation Rule
- `EXPECTED.md` and `manifest.json` are kept strictly outside `src/campusos/` and are **never** imported or read by agent code.
- The agent runner writes per-case trace records to `tests/trap-pack/traces/case_<file-stem>.json`, and `grader.py` scores them independently.

## Usage
```bash
python tests/trap-pack/grader.py \
  --manifest /path/to/manifest.json \
  --cases tests/trap-pack/traces \
  --out tests/trap-pack
```

This generates:
- `tests/trap-pack/results.json` (served by `GET /api/trap-pack`)
- `tests/trap-pack/RESULTS.md`

## Attribution
Based on the **Agentware 2026 Trap Pack, Hackathon Raptors** (CC BY 4.0).
