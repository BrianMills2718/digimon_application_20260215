# Plan #14: Fix llm_client / Unblock Benchmark Runner

**Status:** Complete
**Type:** implementation
**Priority:** High (blocks all empirical work)
**Blocked By:** None
**Blocks:** Plan #15, Plan #17

---

## Gap

**Current:** `eval/run_agent_benchmark.py --backend direct` times out with 0 tokens on all questions. Root cause confirmed by Codex agent: llm_client v1 has an import error (`responses_runtime` doesn't exist on current branch) and heartbeat bugs. The benchmark runner initializes differently when launched directly vs imported, masking the issue.

**Target:** Benchmark runner completes a 3-question smoke test with non-zero accuracy.

**Why:** Every empirical validation (operator consolidation verification, build attribute testing, thesis re-test) requires a working benchmark runner. This is the single highest-leverage fix.

---

## References Reviewed

- Codex agent Phase 4 assessment (2026-03-22): confirmed llm_client v1 `responses_runtime` import error
- `eval/run_agent_benchmark.py` — benchmark runner entry point
- `~/projects/llm_client/` — shared library (check current branch/version state)
- Progressive disclosure plan (`docs/plans/progressive_disclosure_ptc_validation.md`) — documents the same blocker

---

## Files Affected

- `~/projects/llm_client/` — fix or upgrade (shared library, not this repo)
- Possibly `requirements.txt` or conda env config if version pin needed

---

## Plan

### Pre-made decisions

- **Approach**: Try installing latest llm_client first. Only fall back to fixing v1 if v2 has its own issues.
- **Environment**: digimon conda env. Do NOT modify the global llm_client repo in ways that break other projects.
- **Verification model**: `openrouter/openai/gpt-5.4-mini` (the new benchmark routing model)

### Steps

1. Check current llm_client version installed in digimon conda env (`pip show llm-client`)
2. Check current llm_client repo state (`cd ~/projects/llm_client && git status && git branch`)
3. If llm_client has a stable recent commit: `pip install -e ~/projects/llm_client` in digimon env
4. If llm_client has broken imports: identify the specific `responses_runtime` error and fix or work around
5. Run smoke test: `python eval/run_agent_benchmark.py --dataset HotpotQAsmallest --num 3 --model openrouter/openai/gpt-5.4-mini --backend direct`
6. If smoke test passes with non-zero accuracy → gate passed

### Error taxonomy

| Error | Diagnosis | Fix |
|-------|-----------|-----|
| `ImportError: responses_runtime` | llm_client v1 module missing | Upgrade to latest llm_client or pin working commit |
| Heartbeat timeout | Background thread crash in llm_client | Check if fixed in latest; if not, disable heartbeat for benchmark |
| 0 tokens / timeout | Agent loop not receiving LLM responses | Check llm_client.acall_llm directly with same model; isolate agent loop vs LLM call |
| API key error | OPENROUTER_API_KEY not set | Verify `~/.secrets/api_keys.env` has the key and it's loaded |
| Model not found | gpt-5.4-mini not in registry | We just added it; verify pip install picked up the change |

### Backtracking ladder

1. Try latest llm_client (1 attempt)
2. If that fails, try pinning to a known-working git commit (check git log for recent passing CI)
3. If that fails, isolate the exact import path and patch minimally
4. If 3 attempts fail without progress → escalate (the issue may be in the agent loop, not llm_client)

---

## Required Tests

### Verification (not TDD — this is an infrastructure fix)

| Test | What It Verifies |
|------|-----------------|
| `python -c "import llm_client; print(llm_client.__version__)"` in digimon env | Clean import |
| `python eval/run_agent_benchmark.py --dataset HotpotQAsmallest --num 3 --model openrouter/openai/gpt-5.4-mini --backend direct` | End-to-end benchmark works |

---

## Acceptance Criteria

- [ ] llm_client imports cleanly in digimon conda env (no `responses_runtime` error)
- [ ] Benchmark smoke test completes 3 questions with ≥1 correct answer
- [ ] Result JSON written to `results/` with non-zero `avg_em`

---

## Budget

$0 for the fix itself. ~$0.10 for the 3-question smoke test.
