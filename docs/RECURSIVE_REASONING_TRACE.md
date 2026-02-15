# Recursive Reasoning Trace System — Design Document

**Date**: 2026-02-15
**Status**: Requirements + Domain Model complete. Schema + implementation pending.
**Context**: Emerged from planning SOTA KG-RAG benchmark competition (Phase 12+).

---

## Motivation

DIGIMON has 24 typed, composable operators that agents (Claude Code, Codex) compose into
arbitrary retrieval DAGs via MCP. The question: can we beat StepChain GraphRAG (current
SOTA on multi-hop QA benchmarks, ~57.7 avg EM)?

StepChain decomposes questions into sub-questions, does BFS on an on-the-fly graph, synthesizes.
It's CoT-level reasoning. DIGIMON's operator pipeline is already a Graph-of-Thought architecture —
it can express arbitrary DAGs of reasoning. But nobody in KG-RAG stores or operates on the
reasoning traces themselves.

**Core insight**: The output of a DIGIMON reasoning session (sub-questions, operator calls,
retrieved evidence, partial answers, confidence levels) IS a knowledge graph. DIGIMON operates
on knowledge graphs. Therefore DIGIMON can operate on its own reasoning traces recursively.

---

## Requirements

### Use Cases

1. **Benchmark eval**: Run 500+ questions, analyze which methods/operators work for which
   question types. Identify failure patterns.

2. **Strategy learning**: Empirically discover "questions like X get good answers from
   operator chain Y" — grounded in trace data, not LLM guessing.

3. **Recursive meta-analysis**: When the trace graph is large, apply DIGIMON operators to it.
   Community detection on reasoning patterns, PPR from successful traces, etc.

4. **Progressive knowledge distillation**: For complex questions ("What causes revolutions?"),
   decompose into hundreds of sub-questions, answer each from domain KG, then re-apply the
   original question to the distilled answer graph. Each recursion level refines knowledge
   through the lens of the question.

5. **Debugging**: Trace back through decomposition → retrieval → answer to find where
   reasoning went wrong.

6. **Auto-compose improvement**: Replace LLM-guessing in method selection with evidence-based
   selection grounded in past trace data.

7. **Driver comparison**: Track which agent (Claude Code, Codex, OpenClaw) drove each step,
   compare performance across drivers.

### Constraints

- Trace graph MUST be DIGIMON-compatible (ER graph format) — otherwise recursive application
  doesn't work. Same operators, different semantics.
- Trace writing MUST NOT block the hot path — async/after-the-fact, not blocking operator calls.
- Must work regardless of orchestrator (Claude Code, Codex, OpenClaw, standalone).
- Must handle self-correction: conclusions change across rounds, assumptions get invalidated.

---

## Domain Model

Derived from requirements + real-world AoT trace analysis (see Appendix A).

### Entities

| Entity | What it is | Example |
|--------|-----------|---------|
| **Query** | Top-level question from user | "What causes revolutions?" |
| **Atom** | Decomposed sub-question | "What economic conditions preceded the French Revolution?" |
| **Assumption** | Testable claim with confidence | "PPR will outperform BFS for this question type" |
| **Evidence** | Grounded observation with provenance | Entity "French Revolution" retrieved from wiki_er, 14 chunks, score 0.92 |
| **Answer** | Current best answer to a query/atom | "Economic inequality and fiscal crisis", confidence=0.88, round=2 |
| **Contraction** | Merged group of resolved atoms → distilled statement | "Economic causes cluster separately from military causes" |
| **Round** | A pass of reasoning that may correct previous rounds | Round 1, Round 2 (after new evidence) |
| **OperatorCall** | Single invocation of a DIGIMON operator | entity_ppr(seed=["French Revolution"], graph="wiki_er") |
| **Driver** | Agent that made the decision | claude-code, codex, openclaw |
| **DomainGraph** | Source KG being queried | wiki_er, hotpotqa_er, or a previous trace graph |

### Relationships

| From | Relationship | To | Metadata |
|------|-------------|-----|----------|
| Query | decomposes_to | Atom | decomposition_level, order |
| Atom | depends_on | Atom | why (needs answer from) |
| Atom | has_evidence | Evidence | round_added |
| Atom | answered_by | Answer | round, confidence, status |
| Atom | assumes | Assumption | round |
| Answer | supersedes | Answer | reason (correction from new evidence) |
| Answer | supports | Answer | strength |
| Answer | contradicts | Answer | strength, evidence |
| Assumption | verified_by | Evidence | round, result (confirmed/invalidated/revised) |
| Contraction | merges | Atom[] | round |
| Contraction | simplifies_to | Answer | the distilled higher-level statement |
| OperatorCall | executed_for | Atom | timestamp, latency_ms, token_cost |
| OperatorCall | retrieved | Evidence | score, rank |
| OperatorCall | used_graph | DomainGraph | |
| OperatorCall | driven_by | Driver | |
| Query | applied_at_level | int | recursion depth (0=domain, 1=trace, 2=meta-trace) |

### Status Lifecycle (for Atoms and Assumptions)

```
Atom:       pending → in_progress → answered → corrected → invalidated
Assumption: proposed → testing → confirmed → invalidated
Answer:     current → superseded
```

### The Recursive Structure

**Level 0**: Domain KG (Wikipedia, corpus documents). Standard DIGIMON operations.

**Level 1**: Reasoning trace graph from Level 0 queries. Atoms are entities, dependency
edges are relationships. Contractions from Level 0 become first-class entities.

**Level 2**: Apply DIGIMON operators TO the Level 1 trace graph. Community detection finds
clusters of reasoning patterns. PPR from successful traces finds effective strategies.
VDB search finds similar past sub-questions.

**Level N**: Each level's output is a valid DIGIMON ER graph. Same operators, different
semantic content. Termination when: convergence (Level N answer ≈ Level N-1), confidence
threshold met, or budget exhausted.

**Key property**: Contractions at Level N become entities at Level N+1. This is how
knowledge gets distilled upward. A contraction like "Economic causes of revolutions
cluster into inequality, fiscal crisis, and trade disruption" becomes a single entity
that can be retrieved, linked, and reasoned about at the next level.

---

## Progressive Knowledge Distillation (Complex Questions)

For questions with thousands of interlinked sub-questions:

1. **Decompose** "What causes revolutions?" into a thought DAG (potentially hundreds of atoms)
2. **Fan out**: Each atom retrieves from domain KG independently (parallelizable)
3. **Fan in**: Answers flow back through dependency edges
4. **Contract**: Groups of resolved atoms merge into contractions (distilled knowledge)
5. **Build Level 1 graph**: Contractions + remaining open atoms form a new ER graph
6. **Re-apply original question** to Level 1 graph — now operating on structured,
   question-relevant knowledge instead of raw Wikipedia
7. **Repeat** until convergence or budget

This is NOT just meta-reasoning about strategy. It's using the recursive process to
progressively distill a massive knowledge space into question-relevant structured knowledge.

---

## Relationship to Existing DIGIMON Architecture

### What Already Exists

- **Mode 1 (agent-driven composition)**: Claude Code/Codex already composes operators
  dynamically. The agent IS the reasoning graph — no fixed plan needed.
- **PipelineExecutor**: Supports LoopConfig, ConditionalBranch for Mode 2/3 fixed plans.
- **OperatorContext**: Carries graph, VDBs, LLM, config through pipeline execution.
- **ER graph format**: The standard graph type. Trace graphs must match this format.
- **`agentic_model: "claude-code"`**: Mid-pipeline LLM calls route through Agent SDK.
- **`set_agentic_model`**: Switch to cheaper models (gemini-flash, gpt-4o-mini) for bulk runs.

### What Needs to Be Built

| Component | Description | Complexity |
|-----------|-------------|------------|
| **`meta.decompose_question`** operator | LLM decomposes query into atom DAG | ~50 lines + prompt template |
| **`meta.synthesize_answers`** operator | LLM merges partial answers into final | ~50 lines + prompt template |
| **`meta.contract`** operator | Merge resolved atoms into contraction | ~50 lines + prompt template |
| **Trace writer** | Hook/decorator that emits trace events per operator call | ~100 lines |
| **Trace-to-graph converter** | Converts trace events into DIGIMON ER graph format | ~150 lines |
| **Eval harness** | Run N questions, score EM/F1, store traces | ~200 lines |
| **Benchmark data pipeline** | Download HotPotQA/MuSiQue/2Wiki, build corpora + KGs | ~150 lines |

### Execution Model

For benchmark runs: **Codex as orchestrator** (cheaper), calling DIGIMON operators via MCP,
with `agentic_model` set to gemini-flash for bulk mid-pipeline LLM calls.

For interactive use: **Claude Code as orchestrator**, `agentic_model: "claude-code"`.

The trace writer captures what happened regardless of who drove it.

---

## Uncertainties

### High Confidence

- The domain model (entities + relationships) captures what's needed for recursive application.
  Validated against a real 23-atom AoT trace with 6 rounds of self-correction.
- DIGIMON's existing ER graph operators can operate on a trace graph if the schema is right.
- The two new operators (decompose, synthesize) are straightforward LLM prompt templates.
- Mode 1 (agent-driven composition) already supports dynamic operator sequencing.

### Medium Confidence — Needs Validation

- **ER graph compatibility**: Can the trace schema (atoms, assumptions, contractions with
  their metadata) fit cleanly into DIGIMON's ER graph format? The ER graph has entities
  with types/descriptions and relationships with source_ids. Need to verify the trace
  entities map to this without losing critical metadata (confidence, round, status).

- **Contraction quality**: The `meta.contract` operator depends on LLM ability to meaningfully
  merge resolved atoms. If contractions are lossy (drop important nuance), the recursive
  application degrades. Need prompt engineering + eval.

- **Convergence behavior**: Will re-applying the original question to a trace graph actually
  produce better answers? Or will it just rephrase Level 0 answers? Need empirical testing.

- **Scale of thought DAGs**: "What causes revolutions?" might decompose into 500+ atoms.
  At $0.01/operator call with claude-code, that's $5+ per question. With gemini-flash
  it's much cheaper but quality may suffer for reasoning-heavy atoms.

### Low Confidence — Open Questions

- **Optimal recursion depth**: Is Level 2 sufficient? Does Level 3+ add value or just noise?
  No theoretical basis for predicting this — purely empirical.

- **Cross-question trace reuse**: Can traces from question A help answer question B?
  Intuitively yes (similar sub-questions), but the mechanism isn't designed yet.
  This is where VDB search on the trace graph would help.

- **Benchmark competitiveness**: We don't have baseline numbers yet for DIGIMON's operators
  on standard benchmarks. The recursive trace system might not be needed to beat StepChain —
  an existing operator composition might already be competitive. Need eval harness first.

- **Contradiction detection automation**: The real AoT trace required 6 rounds of human-driven
  correction to find contradictions. Can DIGIMON operators (community detection, PPR) surface
  contradictions automatically? Speculative — needs experimentation.

---

## Competitive Landscape (KG-RAG SOTA, Feb 2026)

### Standard Benchmarks
Three multi-hop QA datasets: HotPotQA, MuSiQue, 2WikiMultiHopQA. Metrics: EM and F1.

### Current SOTA

| System | Avg EM | Avg F1 | Key Technique | Code? |
|--------|--------|--------|---------------|-------|
| StepChain | 57.7 | 68.5 | Decompose → BFS per sub-Q → synthesize | No |
| HopRAG | 55.1 | 66.4 | Retrieve-reason-prune cycle | ? |
| RAPTOR | 49.4 | 61.2 | Hierarchical clustering + summaries | Yes |
| LinearRAG | ~64 CA | ~67 GA | Entity graph, no relation extraction | ? |
| GFM-RAG | 56.0 EM | 71.8 F1 | Graph foundation model (8M GNN) | Yes |
| MS GraphRAG | 22.1 | 30.2 | Community summaries (BAD at multi-hop) | Yes |

CA = Contain-Accuracy, GA = GPT-Accuracy (different metrics, not directly comparable to EM/F1).

### No Standardized Leaderboard
GraphRAG-Bench (ICLR 2026) is the closest — purpose-built, 4 task types, 16 disciplines.
New enough that getting good numbers there would be meaningful.

### What Separates SOTA
1. Iterative LLM-guided traversal (not single-shot retrieval)
2. Hybrid graph + embedding retrieval
3. PPR for subgraph extraction
4. Question decomposition (biggest single lift: +14 EM in StepChain ablation)

DIGIMON already has all four capabilities. The gap is composition + evaluation.

---

## Next Steps (Priority Order)

1. **Build eval harness** — Benchmark operator compositions on HotPotQA/MuSiQue/2Wiki.
   Test the 10 reference pipelines as baselines, then novel operator chains.
   This tells us if we even need the recursive system to compete,
   or if an existing composition is already close.

2. **Add decompose + synthesize operators** — Two LLM prompt templates. Unlocks AoT-style
   reasoning regardless of whether we build the full trace system.

3. **Design trace ER graph schema** — Map the domain model above to DIGIMON's actual ER
   graph format (entity types, relationship types, source_ids, descriptions).

4. **Build trace writer** — Instrument operator calls to emit trace events.

5. **Build trace-to-graph converter** — Produce DIGIMON-compatible ER graph from traces.

6. **Test recursive application** — Run Level 1 traces, build as graph, query with DIGIMON.
   Does Level 2 produce better answers?

7. **Benchmark the full system** — Compare recursive trace approach vs flat methods vs SOTA.

---

## Appendix A: Real-World AoT Trace Reference

The domain model was validated against a real 23-atom Atom-of-Thoughts debugging trace
(Pasos iOS app "Hang tight" bug). Key observations from that trace:

- **Atoms have rich lifecycle**: pending → answered → corrected → invalidated
- **Assumptions are first-class**: 17 explicit assumptions, 5 invalidated across 6 rounds
- **Self-correction is the most valuable pattern**: Round 6 found that Bug 3 (identified
  in round 4) was misidentified — the key prop was on the wrong React layer
- **Contractions are the distilled knowledge**: 8 contractions reduced 23 atoms to
  actionable statements
- **Evidence provenance matters**: Specific file:line references enabled re-verification
  when assumptions were challenged
- **DAG structure is explicit**: Dependencies between atoms are tracked and visible

Full trace stored separately (steno.ai production codebase, not in this repo).

---

## Appendix B: Reading List

- **Atom of Thoughts** (AoT): DAG-based question decomposition with Markov property.
  `~/projects/project-meta/research_texts/agentic_thought/atoms_of_thoughts.txt`
- **Chain/Tree/Graph of Thought comparison**:
  `~/projects/project-meta/research_texts/agentic_thought/chain_tree_graph_thought.txt`
- **StepChain GraphRAG** (arXiv 2510.02827): Current SOTA, decompose → BFS → synthesize.
- **GraphRAG-Bench** (ICLR 2026): Purpose-built KG-RAG benchmark.
- **Epistemic Engine Design** (Brian's):
  `~/projects/project-meta/post_thesis/EPISTEMIC_ENGINE_DESIGN.md`
