# === META-PROCESS TARGETS ===
# Added by meta-process install.sh

# Configuration
SCRIPTS_META := scripts/meta
PLANS_DIR := docs/plans

# --- Session Start ---
.PHONY: status

status:  ## Show git status
	@git status --short --branch

# --- During Implementation ---
.PHONY: test test-quick check

test:  ## Run pytest
	pytest tests/ -v

test-quick:  ## Run pytest (no traceback)
	pytest tests/ -q --tb=no

check:  ## Run all checks (test, mypy, lint)
	@echo "Running tests..."
	@pytest tests/ -q --tb=short
	@echo ""
	@echo "Running mypy..."
	@mypy src/ --ignore-missing-imports
	@echo ""
	@echo "All checks passed!"

# --- PR Workflow ---
.PHONY: pr-ready pr merge finish

pr-ready:  ## Rebase on main and push
	@git fetch origin main
	@git rebase origin/main
	@git push -u origin HEAD

pr:  ## Create PR (opens browser)
	@gh pr create --fill --web

merge:  ## Merge PR (PR=number required)
ifndef PR
	$(error PR is required. Usage: make merge PR=123)
endif
	@python $(SCRIPTS_META)/merge_pr.py $(PR)

finish:  ## Merge PR + cleanup branch (BRANCH=name PR=number required)
ifndef BRANCH
	$(error BRANCH is required. Usage: make finish BRANCH=plan-42-feature PR=123)
endif
ifndef PR
	$(error PR is required. Usage: make finish BRANCH=plan-42-feature PR=123)
endif
	@gh pr merge $(PR) --squash --delete-branch
	@git checkout main && git pull --ff-only
	@git branch -d $(BRANCH) 2>/dev/null || true

# --- Plans ---
.PHONY: plan-tests plan-complete

plan-tests:  ## Check plan's required tests (PLAN=N required)
ifndef PLAN
	$(error PLAN is required. Usage: make plan-tests PLAN=42)
endif
	@python $(SCRIPTS_META)/check_plan_tests.py --plan $(PLAN)

plan-complete:  ## Mark plan complete with verification (PLAN=N required)
ifndef PLAN
	$(error PLAN is required. Usage: make plan-complete PLAN=42)
endif
	@python $(SCRIPTS_META)/complete_plan.py --plan $(PLAN)

# --- Help ---
.PHONY: help-meta

help-meta:  ## Show meta-process targets
	@echo "Meta-Process Targets:"
	@echo ""
	@echo "  Session:"
	@echo "    status          Show git status"
	@echo ""
	@echo "  Development:"
	@echo "    test            Run tests"
	@echo "    check           Run all checks"
	@echo ""
	@echo "  PR Workflow:"
	@echo "    pr-ready        Rebase + push"
	@echo "    pr              Create PR"
	@echo "    merge           Merge PR (PR=number)"
	@echo "    finish          Merge + cleanup (BRANCH=name PR=number)"
	@echo ""
	@echo "  Plans:"
	@echo "    plan-tests      Check plan tests (PLAN=N)"
	@echo "    plan-complete   Complete plan (PLAN=N)"

# === META-PROCESS TARGETS ===
# Added by meta-process install.sh

# Configuration
SCRIPTS_META := scripts/meta
PLANS_DIR := docs/plans
GITHUB_ACCOUNT ?= BrianMills2718
PR_AUTO_EXPECTED_REPO ?= $(notdir $(CURDIR))

# --- Session Start ---
.PHONY: status

status:  ## Show git status
	@git status --short --branch

# --- During Implementation ---
.PHONY: test test-quick check

test:  ## Run pytest
	pytest tests/ -v

test-quick:  ## Run pytest (no traceback)
	pytest tests/ -q --tb=no

check:  ## Run all checks (test, mypy, lint)
	@echo "Running tests..."
	@pytest tests/ -q --tb=short
	@echo ""
	@echo "Running mypy..."
	@mypy src/ --ignore-missing-imports
	@echo ""
	@echo "All checks passed!"

# --- PR Workflow ---
.PHONY: pr-ready pr merge finish pr-auto-check pr-auto

pr-ready:  ## Rebase on main and push
	@git fetch origin main
	@git rebase origin/main
	@git push -u origin HEAD

pr:  ## Create PR (opens browser)
	@gh pr create --fill --web

pr-auto-check:  ## Autonomous PR preflight (branch/clean tree/origin/account)
	@python $(SCRIPTS_META)/pr_auto.py --preflight-only --expected-origin-repo $(PR_AUTO_EXPECTED_REPO) --account $(GITHUB_ACCOUNT)

pr-auto:  ## Autonomous PR create + auto-merge request (non-interactive)
	@python $(SCRIPTS_META)/pr_auto.py --expected-origin-repo $(PR_AUTO_EXPECTED_REPO) --account $(GITHUB_ACCOUNT) --fill --auto-merge

merge:  ## Merge PR (PR=number required)
ifndef PR
	$(error PR is required. Usage: make merge PR=123)
endif
	@python $(SCRIPTS_META)/merge_pr.py $(PR)

finish:  ## Merge PR + cleanup branch (BRANCH=name PR=number required)
ifndef BRANCH
	$(error BRANCH is required. Usage: make finish BRANCH=plan-42-feature PR=123)
endif
ifndef PR
	$(error PR is required. Usage: make finish BRANCH=plan-42-feature PR=123)
endif
	@gh pr merge $(PR) --squash --delete-branch
	@git checkout main && git pull --ff-only
	@git branch -d $(BRANCH) 2>/dev/null || true

# --- Plans ---
.PHONY: plan-tests plan-complete

plan-tests:  ## Check plan's required tests (PLAN=N required)
ifndef PLAN
	$(error PLAN is required. Usage: make plan-tests PLAN=42)
endif
	@python $(SCRIPTS_META)/check_plan_tests.py --plan $(PLAN)

plan-complete:  ## Mark plan complete with verification (PLAN=N required)
ifndef PLAN
	$(error PLAN is required. Usage: make plan-complete PLAN=42)
endif
	@python $(SCRIPTS_META)/complete_plan.py --plan $(PLAN)

# --- Quality ---
.PHONY: dead-code

dead-code:  ## Run dead code detection
	@python $(SCRIPTS_META)/check_dead_code.py

# --- Help ---
.PHONY: help-meta

help-meta:  ## Show meta-process targets
	@echo "Meta-Process Targets:"
	@echo ""
	@echo "  Session:"
	@echo "    status          Show git status"
	@echo ""
	@echo "  Development:"
	@echo "    test            Run tests"
	@echo "    check           Run all checks"
	@echo ""
	@echo "  PR Workflow:"
	@echo "    pr-ready        Rebase + push"
	@echo "    pr              Create PR"
	@echo "    pr-auto-check   Preflight autonomous PR flow"
	@echo "    pr-auto         Non-interactive PR + auto-merge request"
	@echo "    merge           Merge PR (PR=number)"
	@echo "    finish          Merge + cleanup (BRANCH=name PR=number)"
	@echo ""
	@echo "  Quality:"
	@echo "    dead-code       Run dead code detection"
	@echo ""
	@echo "  Plans:"
	@echo "    plan-tests      Check plan tests (PLAN=N)"
	@echo "    plan-complete   Complete plan (PLAN=N)"

# =============================================================================
# DIGIMON-SPECIFIC TARGETS
# =============================================================================

# Configuration
PROJECT := Digimon_for_KG_application
DAYS ?= 7
LIMIT ?= 20
DATASET ?= HotpotQAsmallest
NUM ?= 3
MODEL ?= openrouter/openai/gpt-5.4-mini
LLM_CLIENT_CLI := conda run -n digimon python -m llm_client

# --- Observability (shared llm_client DB) ---
.PHONY: cost cost-by-model cost-by-task errors recent summary

cost:  ## Total LLM spend (DAYS=7 default)
	@$(LLM_CLIENT_CLI) cost --project $(PROJECT) --days $(DAYS)

cost-by-model:  ## Spend per model (DAYS=7)
	@$(LLM_CLIENT_CLI) cost --project $(PROJECT) --days $(DAYS) --group-by model

cost-by-task:  ## Spend per task (DAYS=7)
	@$(LLM_CLIENT_CLI) cost --project $(PROJECT) --days $(DAYS) --group-by task

errors:  ## Error breakdown by model (DAYS=7)
	@$(LLM_CLIENT_CLI) errors --project $(PROJECT) --days $(DAYS)

recent:  ## Last N LLM calls (LIMIT=20)
	@$(LLM_CLIENT_CLI) recent --project $(PROJECT) --limit $(LIMIT)

summary:  ## Quick dashboard: spend, calls, errors, top models (DAYS=7)
	@$(LLM_CLIENT_CLI) summary --project $(PROJECT) --days $(DAYS)

# --- Benchmark ---
.PHONY: bench bench-baseline bench-musique graph-stats

bench:  ## Run benchmark (DATASET=HotpotQAsmallest NUM=3 MODEL=gpt-5.4-mini)
	conda run -n digimon python eval/run_agent_benchmark.py \
		--dataset $(DATASET) --num $(NUM) \
		--model $(MODEL) --backend direct \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "agent_spec relocated"

bench-baseline:  ## Run baseline (no graph) benchmark
	conda run -n digimon python eval/run_agent_benchmark.py \
		--dataset $(DATASET) --num $(NUM) \
		--model $(MODEL) --backend direct --mode baseline \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "agent_spec relocated"

bench-musique:  ## Run MuSiQue 19q diagnostic set
	conda run -n digimon python eval/run_agent_benchmark.py \
		--dataset MuSiQue \
		--questions-file eval/fixtures/musique_19q_diagnostic_ids.txt \
		--model $(MODEL) --backend direct \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "agent_spec relocated"

graph-stats:  ## Show graph node/edge counts for a dataset
	@conda run -n digimon python -c "import networkx as nx; G=nx.read_graphml('results/$(DATASET)/er_graph/nx_data.graphml'); print(f'Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}')"

# --- Graph Build ---
.PHONY: build-progress enrich

build-progress:  ## Check graph build checkpoint progress
	@conda run -n digimon python -c "import json; d=json.load(open('results/$(DATASET)/er_graph/_checkpoint_processed.json')); print(f'{len(d)} chunks processed')" 2>/dev/null || echo "No checkpoint found"

enrich:  ## Run post-build enrichment (synonym edges + centrality)
	conda run -n digimon python scripts/post_build_enrichment.py --dataset $(DATASET)

# --- Help ---
.PHONY: help

help:  ## Show all targets
	@echo "DIGIMON — composable GraphRAG retrieval engine"
	@echo ""
	@echo "Observability:"
	@grep -E '^(cost|errors|recent|summary).*:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-20s %s\n", $$1, $$2}'
	@echo ""
	@echo "Benchmark:"
	@grep -E '^bench.*:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-20s %s\n", $$1, $$2}'
	@echo ""
	@echo "Graph:"
	@grep -E '^(graph|build|enrich).*:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-20s %s\n", $$1, $$2}'
	@echo ""
	@echo "Options: DAYS=7 DATASET=HotpotQAsmallest NUM=3 MODEL=openrouter/openai/gpt-5.4-mini LIMIT=20"

# --- Diagnosis ---
.PHONY: diagnose diagnose-failures

diagnose:  ## Diagnose a specific question (FILE= QID= required)
ifndef FILE
	@conda run -n digimon python scripts/diagnose_question.py
else
	@conda run -n digimon python scripts/diagnose_question.py $(FILE) $(QID)
endif

diagnose-failures:  ## Diagnose all failures in latest MuSiQue run
	@conda run -n digimon python -c "\
	import json, glob, subprocess, sys; \
	files = sorted(glob.glob('results/MuSiQue_gpt-5-4-mini_consolidated_*.json')); \
	latest = files[-1]; \
	data = json.load(open(latest)); \
	fails = [q['id'] for q in data['results'] if q.get('llm_em', 0) == 0]; \
	print(f'Diagnosing {len(fails)} failures from {latest}'); \
	[subprocess.run([sys.executable, 'scripts/diagnose_question.py', latest, qid]) for qid in fails]"

linearization-check:  ## Check for linearization data loss warnings
	@echo "=== Linearization Data Loss Warnings ==="
	@grep '"data_loss_warning": true' results/.linearization_log.jsonl 2>/dev/null | \
		conda run -n digimon python -c "import sys,json; lines=[json.loads(l) for l in sys.stdin]; print(f'{len(lines)} data loss warnings'); [print(f'  {l[\"tool\"]}({l[\"method\"]}): raw={l[\"raw_len\"]}b → summary={l[\"summary_len\"]}b') for l in lines[-10:]]" \
		|| echo "  No warnings (or no log file yet)"
	@echo ""
	@echo "=== Compression Stats ==="
	@cat results/.linearization_log.jsonl 2>/dev/null | \
		conda run -n digimon python -c "import sys,json; lines=[json.loads(l) for l in sys.stdin]; print(f'{len(lines)} total linearizations, avg compression={sum(l[\"compression\"] for l in lines)/max(len(lines),1):.1%}')" \
		|| echo "  No log file yet"

check-rules:  ## Check CLAUDE.md rule violations (json_object, hardcoded paths, except:pass)
	@~/projects/.claude/scripts/check-rules.sh . || true
