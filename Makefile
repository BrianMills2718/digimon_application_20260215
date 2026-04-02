# === META-PROCESS TARGETS ===
# Added by meta-process install.sh

# Configuration
SCRIPTS_META := scripts/meta
PLANS_DIR := docs/plans
GITHUB_ACCOUNT ?= BrianMills2718
PR_AUTO_EXPECTED_REPO ?= $(notdir $(CURDIR))

PROJECT := Digimon_for_KG_application
DAYS ?= 7
LIMIT ?= 20
DATASET ?= HotpotQAsmallest
NUM ?= 3
MODEL ?= openrouter/openai/gpt-5.4-mini
PYTHON ?= .venv/bin/python
PYTEST ?= .venv/bin/pytest
LLM_CLIENT_CLI := conda run -n digimon python -m llm_client
CORE_TESTS := \
	tests/unit/test_benchmark_tool_modes.py \
	tests/unit/test_eval_graph_manifest.py \
	tests/unit/test_graph_capabilities.py \
	tests/unit/test_operator_package_import.py \
	tests/unit/test_prebuild_graph_cli.py \
	tests/unit/test_semantic_plan_query_contract.py
CORE_PY_MODULES := \
	Core/Graph \
	Core/Operators \
	Core/Schema \
	Core/MCP/tool_consolidation.py \
	eval/benchmark.py \
	eval/graph_manifest.py \
	eval/run_agent_benchmark.py

# --- Session Start ---
.PHONY: status

status:  ## Show git status
	@git status --short --branch

# >>> META-PROCESS WORKTREE TARGETS >>>
WORKTREE_CREATE_SCRIPT := scripts/meta/worktree-coordination/create_worktree.py
WORKTREE_REMOVE_SCRIPT := scripts/meta/worktree-coordination/safe_worktree_remove.py
WORKTREE_CLAIMS_SCRIPT := scripts/meta/worktree-coordination/check_claims.py
WORKTREE_DIR ?= $(shell python "$(WORKTREE_CREATE_SCRIPT)" --repo-root . --print-default-worktree-dir)
WORKTREE_DEFAULT_REMOTE_REF ?= $(shell git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/@@')
WORKTREE_START_POINT ?= $(if $(WORKTREE_DEFAULT_REMOTE_REF),$(WORKTREE_DEFAULT_REMOTE_REF),HEAD)

.PHONY: worktree worktree-list worktree-remove

worktree:  ## Create claimed worktree (BRANCH=name TASK="..." [PLAN=N])
ifndef BRANCH
	$(error BRANCH is required. Usage: make worktree BRANCH=plan-42-feature TASK="Describe the task")
endif
ifndef TASK
	$(error TASK is required. Usage: make worktree BRANCH=plan-42-feature TASK="Describe the task")
endif
	@if [ ! -f "$(WORKTREE_CREATE_SCRIPT)" ]; then \
		echo "Missing worktree coordination module: $(WORKTREE_CREATE_SCRIPT)"; \
		echo "Install the full meta-process worktree-coordination module before using make worktree."; \
		exit 1; \
	fi
	@if [ ! -f "$(WORKTREE_CLAIMS_SCRIPT)" ]; then \
		echo "Missing worktree coordination module: $(WORKTREE_CLAIMS_SCRIPT)"; \
		echo "Install the full meta-process worktree-coordination module before using make worktree."; \
		exit 1; \
	fi
	@python "$(WORKTREE_CLAIMS_SCRIPT)" --claim --id "$(BRANCH)" --task "$(TASK)" $(if $(PLAN),--plan $(PLAN),)
	@mkdir -p "$(WORKTREE_DIR)"
	@if ! python "$(WORKTREE_CREATE_SCRIPT)" --repo-root . --path "$(WORKTREE_DIR)/$(BRANCH)" --branch "$(BRANCH)" --start-point "$(WORKTREE_START_POINT)"; then \
		python "$(WORKTREE_CLAIMS_SCRIPT)" --release --id "$(BRANCH)" --force >/dev/null 2>&1 || true; \
		exit 1; \
	fi
	@echo ""
	@echo "Worktree created at $(WORKTREE_DIR)/$(BRANCH)"
	@echo "Claim created for branch $(BRANCH)"

worktree-list:  ## Show claimed worktree coordination status
	@if [ ! -f "$(WORKTREE_CLAIMS_SCRIPT)" ]; then \
		echo "Missing worktree coordination module: $(WORKTREE_CLAIMS_SCRIPT)"; \
		echo "Install the full meta-process worktree-coordination module before using make worktree-list."; \
		exit 1; \
	fi
	@python "$(WORKTREE_CLAIMS_SCRIPT)" --list

worktree-remove:  ## Safely remove worktree for BRANCH=name
ifndef BRANCH
	$(error BRANCH is required. Usage: make worktree-remove BRANCH=plan-42-feature)
endif
	@if [ ! -f "$(WORKTREE_REMOVE_SCRIPT)" ]; then \
		echo "Missing worktree coordination module: $(WORKTREE_REMOVE_SCRIPT)"; \
		echo "Install the full meta-process worktree-coordination module before using make worktree-remove."; \
		exit 1; \
	fi
	@python "$(WORKTREE_REMOVE_SCRIPT)" "$(WORKTREE_DIR)/$(BRANCH)"
	@python "$(WORKTREE_CLAIMS_SCRIPT)" --release --id "$(BRANCH)" --force >/dev/null 2>&1 || true
# <<< META-PROCESS WORKTREE TARGETS <<<

# --- During Implementation ---
.PHONY: test test-quick check test-core check-core test-experimental test-historical

test:  ## Run the full pytest suite
	$(PYTEST) tests/ -v

test-quick:  ## Run the full pytest suite (concise output)
	$(PYTEST) tests/ -q --tb=no

check:  ## Run the legacy all-repo check entrypoint
	@echo "Running full test suite..."
	@$(PYTEST) tests/ -q --tb=short
	@echo ""
	@echo "Compiling Python sources..."
	@$(PYTHON) -m compileall Core eval >/dev/null
	@echo ""
	@echo "All checks passed!"

test-core:  ## Run the maintained core-thesis tests
	$(PYTEST) $(CORE_TESTS) -q

check-core:  ## Run the maintained core-thesis verification
	@echo "Running core thesis tests..."
	@$(PYTEST) $(CORE_TESTS) -q
	@echo ""
	@echo "Compiling core thesis modules..."
	@$(PYTHON) -m compileall $(CORE_PY_MODULES) >/dev/null
	@echo ""
	@echo "Core checks passed!"

test-experimental:  ## Run preserved experimental tests (excluding historical)
	$(PYTEST) tests/integration tests/e2e -m "not historical" -q

test-historical:  ## Run historical tests that are preserved but not portable-by-default
	$(PYTEST) -m historical -q

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
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "relocated" \
		--dataset $(DATASET) --num $(NUM) \
		--model $(MODEL) --backend direct \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "agent_spec relocated"

bench-baseline:  ## Run baseline (no graph) benchmark
	conda run -n digimon python eval/run_agent_benchmark.py \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "relocated" \
		--dataset $(DATASET) --num $(NUM) \
		--model $(MODEL) --backend direct --mode baseline \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "agent_spec relocated"

bench-musique:  ## Run MuSiQue 19q diagnostic set
	conda run -n digimon python eval/run_agent_benchmark.py \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "relocated" \
		--dataset MuSiQue \
		--questions-file eval/fixtures/musique_19q_diagnostic_ids.txt \
		--model $(MODEL) --backend direct \
		--agent-spec none --allow-missing-agent-spec --missing-agent-spec-reason "relocated" \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "agent_spec relocated"

graph-stats:  ## Show graph node/edge counts for a dataset
	@conda run -n digimon python -c "import networkx as nx; G=nx.read_graphml('results/$(DATASET)/er_graph/nx_data.graphml'); print(f'Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}')"

# --- Graph Build ---
.PHONY: build-progress enrich add-passages add-passages-dry

build-progress:  ## Check graph build checkpoint progress
	@conda run -n digimon python -c "import json; d=json.load(open('results/$(DATASET)/er_graph/_checkpoint_processed.json')); print(f'{len(d)} chunks processed')" 2>/dev/null || echo "No checkpoint found"

enrich:  ## Run post-build enrichment (synonym edges + centrality)
	conda run -n digimon python scripts/post_build_enrichment.py --dataset $(DATASET)

add-passages:  ## Add passage nodes to existing graph (no rebuild, $0 cost)
	conda run -n digimon python scripts/add_passage_nodes.py --dataset $(DATASET)

add-passages-dry:  ## Preview passage node additions
	conda run -n digimon python scripts/add_passage_nodes.py --dataset $(DATASET) --dry-run

# --- Diagnosis ---
.PHONY: diagnose diagnose-failures linearization-check check-rules

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

.PHONY: sentinel
sentinel:  ## Run sentinel set — regression check on known-passing questions (~$0.10)
	conda run -n digimon python eval/run_agent_benchmark.py \
		--agent-spec none --allow-missing-agent-spec \
		--missing-agent-spec-reason "relocated" \
		--dataset MuSiQue \
		--questions-file eval/fixtures/sentinel_set.txt \
		--model $(MODEL) --backend direct \
		--agent-spec none --allow-missing-agent-spec --missing-agent-spec-reason "relocated"

.PHONY: oracle
oracle:  ## Run LLM-verified oracle diagnostic on latest MuSiQue failures (writes report)
	@LATEST=$$(ls -t results/MuSiQue_gpt-5-4-mini_consolidated_*.json 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then echo "No MuSiQue results found. Run make bench-musique first."; exit 1; fi; \
	echo "Diagnosing failures from $$LATEST"; \
	conda run -n digimon python eval/oracle_diagnostic.py \
		--results "$$LATEST" \
		--report investigations/digimon/$$(date +%Y-%m-%d)-oracle-diagnosis.md

.PHONY: oracle-fast
oracle-fast:  ## Run heuristic-only oracle diagnostic (no LLM cost)
	@LATEST=$$(ls -t results/MuSiQue_gpt-5-4-mini_consolidated_*.json 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then echo "No MuSiQue results found. Run make bench-musique first."; exit 1; fi; \
	echo "Diagnosing failures from $$LATEST (heuristic only)"; \
	conda run -n digimon python eval/oracle_diagnostic.py \
		--results "$$LATEST" --no-llm \
		--report investigations/digimon/$$(date +%Y-%m-%d)-oracle-diagnosis-heuristic.md

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

# --- Help ---
.PHONY: help help-meta

help-meta:  ## Show meta-process targets
	@echo "Meta-Process Targets:"
	@echo ""
	@echo "  Session:"
	@echo "    status          Show git status"
	@echo ""
	@echo "  Development:"
	@echo "    test            Run tests"
	@echo "    check           Run all checks"
	@echo "    test-core       Run maintained core-thesis tests"
	@echo "    check-core      Run maintained core-thesis verification"
	@echo "    test-experimental Run preserved experimental tests"
	@echo "    test-historical Run historical tests"
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

help:  ## Show all targets
	@echo "DIGIMON — adaptive GraphRAG research system"
	@echo ""
	@echo "Core Thesis Lane:"
	@echo "  make test-core           Run maintained core-thesis tests"
	@echo "  make check-core          Run maintained core-thesis verification"
	@echo "  make bench               Run adaptive benchmark"
	@echo "  make bench-baseline      Run non-graph baseline benchmark"
	@echo "  make bench-musique       Run MuSiQue diagnostic benchmark"
	@echo ""
	@echo "Experimental And Historical:"
	@echo "  make test-experimental   Run preserved experimental tests"
	@echo "  make test-historical     Run historical tests"
	@echo ""
	@echo "Observability:"
	@grep -E '^(cost|cost-by-model|cost-by-task|errors|recent|summary):.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-20s %s\n", $$1, $$2}'
	@echo ""
	@echo "Graph And Diagnosis:"
	@grep -E '^(graph-stats|build-progress|enrich|add-passages|add-passages-dry|diagnose|diagnose-failures|linearization-check|check-rules):.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-20s %s\n", $$1, $$2}'
	@echo ""
	@echo "Options: DAYS=7 DATASET=HotpotQAsmallest NUM=3 MODEL=openrouter/openai/gpt-5.4-mini LIMIT=20"
