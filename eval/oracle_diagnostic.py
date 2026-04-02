#!/usr/bin/env python3
"""Oracle diagnostic — automated failure analysis for DIGIMON benchmarks.

For each failing question, works backwards from the gold answer to determine:
1. Is the answer in the raw chunks? (text search)
2. Is the answer findable via VDB? (embedding similarity)
3. Is the answer reachable via graph? (entity search + path finding)
4. What was the optimal tool strategy?
5. What did the agent actually do?
6. What failure family does this belong to?

Usage:
    python eval/oracle_diagnostic.py --results results/MuSiQue_*.json
    python eval/oracle_diagnostic.py --results results/MuSiQue_*.json --question 2hop__13548_13529
    python eval/oracle_diagnostic.py --results results/MuSiQue_*.json --report investigations/digimon/diagnosis.md
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import networkx as nx

try:
    from llm_client import call_llm
    HAS_LLM = True
except ImportError:
    HAS_LLM = False

# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------

FAILURE_FAMILIES = {
    "TOOL_SELECTION": "Answer findable by simpler tool, agent used complex one",
    "QUERY_FORMULATION": "Right tool, wrong query — answer in corpus but query didn't match",
    "EXTRACTION_GAP": "Answer not in chunks or graph — data missing from corpus entirely",
    "GRAPH_REPRESENTATION": "Answer needs multi-hop graph path but graph lacks entity/edge",
    "RETRIEVAL_RANKING": "Right tool and query, answer in results but ranked too low or not selected",
    "ANSWER_SYNTHESIS": "Agent retrieved correct evidence but extracted wrong answer",
    "CONTROL_FLOW": "Atom lifecycle issue — early stopping, stagnation, repeated queries",
    "OTHER": "Doesn't fit above categories — capture details for taxonomy expansion",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_results(results_path: str) -> dict:
    """Load benchmark results JSON."""
    with open(results_path) as f:
        return json.load(f)


def load_chunks(corpus_path: str) -> list[dict]:
    """Load corpus chunks (JSONL format)."""
    chunks = []
    with open(corpus_path) as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line.strip()))
    return chunks


def load_graph(graphml_path: str) -> nx.Graph:
    """Load the NetworkX graph."""
    return nx.read_graphml(graphml_path)


def load_questions(questions_path: str) -> dict[str, dict]:
    """Load question set as id -> {question, answer} dict."""
    questions = {}
    with open(questions_path) as f:
        for line in f:
            if line.strip():
                q = json.loads(line.strip())
                questions[q["id"]] = q
    return questions


# ---------------------------------------------------------------------------
# Step 1: Chunk text search (can simple keyword search find the answer?)
# ---------------------------------------------------------------------------

def search_chunks_for_answer(chunks: list[dict], gold_answer: str) -> dict:
    """Search all chunks for the gold answer via substring matching.

    Returns info about which chunks contain the answer and how easily
    findable it is. This simulates what chunk_retrieve(text, ...) could find.
    """
    answer_lower = gold_answer.lower().strip()
    if not answer_lower:
        return {"found": False, "reason": "empty gold answer"}

    matching_chunks = []
    for i, chunk in enumerate(chunks):
        content = chunk.get("content", "").lower()
        title = chunk.get("title", "").lower()
        if answer_lower in content or answer_lower in title:
            matching_chunks.append({
                "chunk_index": i,
                "doc_id": chunk.get("doc_id", "?"),
                "title": chunk.get("title", "")[:80],
                "match_in": "content" if answer_lower in content else "title",
                "context": _extract_context(chunk.get("content", ""), gold_answer),
            })

    return {
        "found": len(matching_chunks) > 0,
        "count": len(matching_chunks),
        "chunks": matching_chunks[:5],  # top 5
    }


def _extract_context(text: str, answer: str, window: int = 100) -> str:
    """Extract a context window around the answer in the text."""
    idx = text.lower().find(answer.lower())
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(answer) + window)
    return f"...{text[start:end]}..."


# ---------------------------------------------------------------------------
# Step 2: Graph reachability (is the answer entity in the graph?)
# ---------------------------------------------------------------------------

def check_graph_reachability(
    G: nx.Graph, question: str, gold_answer: str
) -> dict:
    """Check if the gold answer entity exists in the graph and is reachable.

    Searches for gold answer as node name (fuzzy), then checks if any
    question-related entities connect to it.
    """
    answer_lower = gold_answer.lower().strip()
    question_lower = question.lower()

    # Find nodes matching the gold answer
    answer_nodes = []
    for node_id, data in G.nodes(data=True):
        node_name = str(node_id).lower()
        node_desc = str(data.get("description", "")).lower()
        if answer_lower in node_name or node_name in answer_lower:
            answer_nodes.append({"id": node_id, "match": "name"})
        elif answer_lower in node_desc:
            answer_nodes.append({"id": node_id, "match": "description"})

    # Extract likely question entities (simple NER heuristic)
    question_entities = _extract_question_entities(question_lower, G)

    # Check path existence
    paths_found = []
    if answer_nodes and question_entities:
        for q_ent in question_entities[:3]:
            for a_node in answer_nodes[:3]:
                try:
                    path = nx.shortest_path(G, q_ent["id"], a_node["id"])
                    paths_found.append({
                        "from": q_ent["id"],
                        "to": a_node["id"],
                        "hops": len(path) - 1,
                        "path": [str(n)[:40] for n in path[:6]],
                    })
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass

    return {
        "answer_in_graph": len(answer_nodes) > 0,
        "answer_nodes": answer_nodes[:5],
        "question_entities_found": len(question_entities),
        "question_entities": question_entities[:5],
        "paths_found": len(paths_found),
        "shortest_path": paths_found[0] if paths_found else None,
        "all_paths": paths_found[:3],
    }


def _extract_question_entities(question: str, G: nx.Graph) -> list[dict]:
    """Find graph nodes that match entities mentioned in the question.

    Simple approach: check each node name against the question text.
    Only returns nodes with names >= 3 chars to avoid noise.
    """
    matches = []
    question_lower = question.lower()
    for node_id, data in G.nodes(data=True):
        node_name = str(node_id).lower()
        if len(node_name) >= 3 and node_name in question_lower:
            matches.append({
                "id": node_id,
                "degree": G.degree(node_id),
            })

    # Sort by name length descending (prefer specific matches)
    matches.sort(key=lambda x: len(str(x["id"])), reverse=True)
    return matches[:10]


# ---------------------------------------------------------------------------
# Step 3: Analyze agent trace
# ---------------------------------------------------------------------------

def analyze_trace(result: dict) -> dict:
    """Analyze the agent's tool call trace for a single question.

    Extracts: tools used, search queries, entities found, whether answer
    appeared in any tool result.
    """
    tool_calls = result.get("tool_calls", [])
    tool_details = result.get("tool_details", [])
    conversation = result.get("conversation_trace", [])

    tools_used = Counter()
    queries_issued = []
    entities_found = set()
    answer_in_results = False
    gold = result.get("gold", "").lower()

    for tc in tool_calls:
        tool_name = tc if isinstance(tc, str) else tc.get("name", "?")
        tools_used[tool_name] += 1

    for td in tool_details:
        tool_name = td.get("name", "?")
        args = td.get("arguments", {})
        result_text = str(td.get("result", "")).lower()

        # Track queries
        query = args.get("query", args.get("question", args.get("text", "")))
        if query:
            queries_issued.append({"tool": tool_name, "query": str(query)[:100]})

        # Track entities
        for ent in args.get("entity_names", args.get("seed_entity_ids", [])):
            entities_found.add(str(ent))

        # Check if gold answer appeared in any tool result
        if gold and gold in result_text:
            answer_in_results = True

    # Check conversation for answer
    for msg in conversation:
        content = str(msg.get("content", "")).lower() if isinstance(msg, dict) else str(msg).lower()
        if gold and gold in content:
            answer_in_results = True

    return {
        "total_tool_calls": len(tool_calls),
        "tools_used": dict(tools_used),
        "queries_issued": queries_issued[:10],
        "entities_searched": list(entities_found)[:10],
        "answer_appeared_in_results": answer_in_results,
        "predicted": result.get("predicted", ""),
        "reasoning": str(result.get("reasoning", ""))[:200],
    }


# ---------------------------------------------------------------------------
# Step 4: Classify failure
# ---------------------------------------------------------------------------

def classify_failure(
    chunk_search: dict,
    graph_check: dict,
    trace: dict,
    question: str,
    gold_answer: str,
) -> dict:
    """Classify a failure into the taxonomy based on diagnostic results.

    Uses a decision tree:
    1. If answer not in chunks at all → EXTRACTION_GAP
    2. If answer in chunks but agent never searched for it → QUERY_FORMULATION
    3. If answer in chunks and agent searched but didn't find → RETRIEVAL_RANKING
    4. If answer appeared in agent results but wrong answer given → ANSWER_SYNTHESIS
    5. If agent used graph when text search would suffice → TOOL_SELECTION
    6. If agent repeated same searches / stopped early → CONTROL_FLOW
    7. If multi-hop needed and graph lacks path → GRAPH_REPRESENTATION
    8. Else → OTHER
    """
    answer_in_chunks = chunk_search.get("found", False)
    answer_in_graph = graph_check.get("answer_in_graph", False)
    answer_in_agent_results = trace.get("answer_appeared_in_results", False)
    predicted = trace.get("predicted", "")
    total_tools = trace.get("total_tool_calls", 0)
    tools_used = trace.get("tools_used", {})

    # Empty prediction usually means submit_answer was never called or rejected
    empty_prediction = not predicted or not predicted.strip()

    # Decision tree
    if not answer_in_chunks:
        return {
            "family": "EXTRACTION_GAP",
            "confidence": "high",
            "detail": f"Gold answer '{gold_answer}' not found in any of the {len(chunk_search.get('chunks', []))} corpus chunks via substring search. The information may not be in the corpus.",
            "fix_class": "corpus",
        }

    if answer_in_agent_results and not empty_prediction:
        return {
            "family": "ANSWER_SYNTHESIS",
            "confidence": "high",
            "detail": f"Gold answer appeared in agent's tool results but agent predicted '{predicted[:50]}' instead of '{gold_answer}'.",
            "fix_class": "prompt",
        }

    if answer_in_agent_results and empty_prediction:
        return {
            "family": "CONTROL_FLOW",
            "confidence": "high",
            "detail": "Gold answer appeared in tool results but agent submitted empty/no answer. Likely atom lifecycle or submit_answer rejection issue.",
            "fix_class": "harness",
        }

    # Answer is in chunks but NOT in agent results
    if answer_in_chunks and not answer_in_agent_results:
        # Did the agent use text search at all?
        used_text_search = any(
            "text" in str(t).lower() or "chunk" in str(t).lower()
            for t in tools_used.keys()
        )
        used_graph = any(
            "entity" in str(t).lower() or "ppr" in str(t).lower()
            or "traverse" in str(t).lower()
            for t in tools_used.keys()
        )

        chunk_count = chunk_search.get("count", 0)

        if not used_text_search and used_graph and chunk_count >= 2:
            return {
                "family": "TOOL_SELECTION",
                "confidence": "medium",
                "detail": f"Answer is in {chunk_count} chunks findable by text search, but agent only used graph tools ({list(tools_used.keys())}). Text search would have been simpler.",
                "fix_class": "prompt",
            }

        if used_text_search:
            # Agent searched but didn't find — query was wrong
            queries = trace.get("queries_issued", [])
            query_texts = [q.get("query", "") for q in queries]
            return {
                "family": "QUERY_FORMULATION",
                "confidence": "medium",
                "detail": f"Answer is in {chunk_count} chunks but agent's queries ({query_texts[:3]}) didn't surface it. The queries may not match the chunk content.",
                "fix_class": "prompt",
            }

        # Didn't search and didn't use graph effectively
        return {
            "family": "RETRIEVAL_RANKING",
            "confidence": "low",
            "detail": f"Answer is in {chunk_count} chunks. Agent used tools {list(tools_used.keys())} but answer didn't appear in results. May be a ranking or context issue.",
            "fix_class": "retrieval_config",
        }

    # Multi-hop specific
    hop_count = question.count("__")  # rough proxy from question ID
    if hop_count >= 3 and not graph_check.get("paths_found"):
        return {
            "family": "GRAPH_REPRESENTATION",
            "confidence": "medium",
            "detail": f"Multi-hop question ({hop_count}+ hops). Answer entity {'found' if answer_in_graph else 'NOT found'} in graph. No traversal path found from question entities.",
            "fix_class": "graph",
        }

    # Default
    return {
        "family": "OTHER",
        "confidence": "low",
        "detail": f"Unclassified. Chunks={answer_in_chunks}, Graph={answer_in_graph}, InResults={answer_in_agent_results}, Predicted='{predicted[:30]}', Tools={total_tools}",
        "fix_class": "investigate",
    }


# ---------------------------------------------------------------------------
# LLM-verified classification
# ---------------------------------------------------------------------------

_LLM_DIAGNOSTIC_PROMPT = """You are a retrieval system diagnostician. A multi-hop question-answering agent failed to answer correctly. Your job is to determine WHY it failed and WHAT the optimal retrieval strategy would have been.

## Available tools the agent could have used
- **chunk_retrieve(text, query)**: keyword/BM25 search over raw document chunks
- **chunk_retrieve(semantic, query)**: VDB embedding similarity search over chunks
- **entity_search(semantic, query)**: find entities in the knowledge graph by name similarity
- **entity_traverse(ppr, seeds)**: PersonalizedPageRank from seed entities to find related entities
- **entity_traverse(onehop, entity)**: get direct graph neighbors
- **entity_info(profile, entity)**: get entity description and relationships
- **relationship_search(graph, entity)**: get relationships for an entity
- **reason(decompose, question)**: break multi-hop question into sub-questions
- **reason(answer, context)**: generate answer from retrieved evidence

The agent can combine any of these. For simple factoid questions, chunk_retrieve(text) alone might suffice. For multi-hop questions requiring connecting facts across documents, graph traversal or question decomposition helps.

## Question
{question}

## Gold answer
{gold_answer}

## Where the gold answer exists in the corpus
{chunk_evidence}

## Graph reachability
{graph_evidence}

## Agent's actual tool trace
{agent_trace}

## Heuristic pre-classification
{heuristic_classification}

## Your task

Analyze the failure by reasoning through these questions:
1. What is the optimal retrieval path to this answer? (decompose the question, identify what tools/queries would find each hop)
2. Where exactly did the agent's path diverge from optimal? (which tool call went wrong, and why?)
3. Is this a problem with the agent's search strategy, the prompt guiding it, the graph data, the control flow, or something else?
4. What specific, actionable fix would address this failure family (not just this question)?

Then classify into exactly ONE primary failure family:
- TOOL_SELECTION: agent used complex tools when simpler ones would work
- QUERY_FORMULATION: right tools but queries/search terms didn't match the content
- EXTRACTION_GAP: answer genuinely not in the corpus or graph
- GRAPH_REPRESENTATION: multi-hop path needed but graph is missing connections
- RETRIEVAL_RANKING: right query returned results but answer ranked too low
- ANSWER_SYNTHESIS: agent found the answer but picked the wrong fact
- CONTROL_FLOW: atom lifecycle issue — agent found evidence but couldn't submit
- INTERMEDIATE_ENTITY_ERROR: agent resolved an intermediate entity incorrectly, cascading wrong searches
- OTHER: doesn't fit above — describe what new category is needed

Respond in this exact JSON format:
{{
    "optimal_path": "step-by-step description of how to get the answer",
    "divergence_point": "which tool call # and what went wrong",
    "root_cause": "one sentence explaining the fundamental issue",
    "family": "FAMILY_NAME",
    "fix_class": "prompt|harness|graph|corpus|retrieval_config|routing",
    "fix_detail": "specific actionable fix that would help this AND similar questions",
    "confidence": "high|medium|low"
}}"""


def classify_with_llm(
    question: str,
    gold_answer: str,
    chunk_search: dict,
    graph_check: dict,
    trace: dict,
    heuristic: dict,
    result: dict,
) -> dict:
    """Use an LLM to produce a nuanced failure classification.

    Sends the full diagnostic context (question, chunk matches, graph state,
    agent trace) to an LLM for expert classification. Costs ~$0.01/question.
    """
    if not HAS_LLM:
        return heuristic

    # Build chunk evidence summary
    chunk_lines = []
    if chunk_search.get("found"):
        chunk_lines.append(f"Answer '{gold_answer}' found in {chunk_search['count']} chunks:")
        for c in chunk_search.get("chunks", [])[:3]:
            chunk_lines.append(f"  - {c['title']} (in {c['match_in']}): {c.get('context', '')[:150]}")
    else:
        chunk_lines.append(f"Answer '{gold_answer}' NOT found in any corpus chunk via substring match.")

    # Build graph evidence summary
    graph_lines = []
    gr = graph_check
    if gr.get("answer_in_graph"):
        graph_lines.append(f"Answer entity found in graph: {gr['answer_nodes'][:3]}")
    else:
        graph_lines.append("Answer entity NOT found as a graph node.")
    graph_lines.append(f"Question entities in graph: {gr['question_entities'][:3]}")
    if gr.get("shortest_path"):
        sp = gr["shortest_path"]
        graph_lines.append(f"Shortest path ({sp['hops']} hops): {' → '.join(sp['path'])}")
    else:
        graph_lines.append("No graph path found between question entities and answer.")

    # Build agent trace summary — includes full conversation trace
    trace_lines = []

    # Tool-level trace (structured)
    trace_lines.append("### Tool calls (structured)")
    for i, td in enumerate(result.get("tool_details", [])):
        tool = td.get("tool", "?")
        args = {k: str(v)[:80] for k, v in td.get("arguments", {}).items()
                if k not in ("dataset_name", "graph_reference_id", "vdb_reference_id", "candidate_entity_ids")
                and v}
        reasoning = (td.get("tool_reasoning") or "")[:120]
        result_preview = (td.get("result_preview") or "")[:200]
        trace_lines.append(f"[{i+1}] {tool}({args})")
        if reasoning:
            trace_lines.append(f"     reason: {reasoning}")
        if result_preview:
            trace_lines.append(f"     result: {result_preview}")

    # Conversation trace (full agent reasoning)
    conversation = result.get("conversation_trace", [])
    if conversation:
        trace_lines.append("")
        trace_lines.append("### Full conversation trace (agent reasoning between tool calls)")
        for i, entry in enumerate(conversation):
            if isinstance(entry, dict):
                role = entry.get("role", "?")
                content = str(entry.get("content", ""))[:300]
                if content.strip():
                    trace_lines.append(f"[{i}] {role}: {content}")
            else:
                trace_lines.append(f"[{i}] {str(entry)[:300]}")

    prompt = _LLM_DIAGNOSTIC_PROMPT.format(
        question=question,
        gold_answer=gold_answer,
        chunk_evidence="\n".join(chunk_lines),
        graph_evidence="\n".join(graph_lines),
        agent_trace="\n".join(trace_lines),
        heuristic_classification=f"{heuristic['family']}: {heuristic['detail']}",
    )

    try:
        import uuid
        llm_result = call_llm(
            "gemini/gemini-2.5-flash-lite",
            [{"role": "user", "content": prompt}],
            task="digimon.oracle_diagnostic",
            trace_id=f"oracle-diag-{uuid.uuid4().hex[:8]}",
            max_budget=0.05,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(llm_result.content)

        # Validate the response has required fields
        required = {"family", "fix_class", "confidence"}
        if not required.issubset(parsed.keys()):
            parsed["_warning"] = f"Missing fields: {required - parsed.keys()}"

        # Add INTERMEDIATE_ENTITY_ERROR to valid families if LLM suggests it
        valid_families = set(FAILURE_FAMILIES.keys()) | {"INTERMEDIATE_ENTITY_ERROR"}
        if parsed.get("family") not in valid_families:
            parsed["_original_family"] = parsed["family"]
            parsed["family"] = "OTHER"

        parsed["source"] = "llm"
        return parsed

    except Exception as e:
        # Fall back to heuristic on any LLM failure
        heuristic["_llm_error"] = str(e)
        heuristic["source"] = "heuristic_fallback"
        return heuristic


# ---------------------------------------------------------------------------
# Full diagnosis for one question
# ---------------------------------------------------------------------------

def diagnose_question(
    result: dict,
    chunks: list[dict],
    G: nx.Graph,
    questions: dict[str, dict],
    use_llm: bool = True,
) -> dict:
    """Run full oracle diagnosis on a single failing question.

    Two-stage classification:
    1. Fast heuristic (free, instant) — substring matching, trace inspection
    2. LLM verification (optional, ~$0.01/q) — reads full context, produces
       nuanced classification with optimal retrieval path analysis
    """
    qid = result["id"]
    gold = result.get("gold", "")
    question_text = questions.get(qid, {}).get("question", result.get("question", ""))

    # Step 1: Chunk search
    chunk_search = search_chunks_for_answer(chunks, gold)

    # Step 2: Graph reachability
    graph_check = check_graph_reachability(G, question_text, gold)

    # Step 3: Trace analysis
    trace = analyze_trace(result)

    # Step 4a: Heuristic classification (fast, free)
    heuristic = classify_failure(
        chunk_search, graph_check, trace, question_text, gold,
    )

    # Step 4b: LLM verification (nuanced, ~$0.01/q)
    if use_llm and HAS_LLM:
        classification = classify_with_llm(
            question_text, gold, chunk_search, graph_check,
            trace, heuristic, result,
        )
        classification["heuristic_family"] = heuristic["family"]
    else:
        classification = heuristic
        classification["source"] = "heuristic"

    # Determine optimal strategy
    optimal = "UNKNOWN"
    if chunk_search["found"] and chunk_search["count"] >= 2:
        optimal = "text_search"
    elif chunk_search["found"]:
        optimal = "vdb_search"
    elif graph_check["answer_in_graph"] and graph_check["paths_found"]:
        optimal = "graph_traversal"
    else:
        optimal = "answer_not_available"

    return {
        "question_id": qid,
        "question": question_text,
        "gold_answer": gold,
        "predicted": result.get("predicted", ""),
        "chunk_search": chunk_search,
        "graph_reachability": graph_check,
        "agent_trace": trace,
        "classification": classification,
        "optimal_strategy": optimal,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(diagnoses: list[dict]) -> str:
    """Generate a markdown diagnostic report."""
    lines = [
        "# Oracle Diagnostic Report",
        "",
        f"**Date**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Questions analyzed**: {len(diagnoses)}",
        "",
    ]

    # Summary by family
    families = Counter(d["classification"]["family"] for d in diagnoses)
    lines.append("## Failure Family Summary")
    lines.append("")
    lines.append("| Family | Count | Fix Class | Description |")
    lines.append("|--------|-------|-----------|-------------|")
    for family, count in families.most_common():
        desc = FAILURE_FAMILIES.get(family, "Unknown")
        fix_classes = set(
            d["classification"]["fix_class"]
            for d in diagnoses
            if d["classification"]["family"] == family
        )
        lines.append(f"| **{family}** | {count} | {', '.join(fix_classes)} | {desc} |")
    lines.append("")

    # Optimal strategy summary
    strategies = Counter(d["optimal_strategy"] for d in diagnoses)
    lines.append("## Optimal Strategy Summary")
    lines.append("")
    for strat, count in strategies.most_common():
        lines.append(f"- **{strat}**: {count} questions")
    lines.append("")

    # Per-question detail
    lines.append("## Per-Question Diagnosis")
    lines.append("")

    for d in diagnoses:
        qid = d["question_id"]
        cls = d["classification"]
        lines.append(f"### {qid}")
        lines.append("")
        lines.append(f"**Question**: {d['question']}")
        lines.append(f"**Gold**: {d['gold_answer']}")
        lines.append(f"**Predicted**: {d['predicted'] or '(empty)'}")
        lines.append(f"**Family**: `{cls['family']}` ({cls.get('confidence', '?')}) — source: {cls.get('source', '?')}")
        if cls.get("heuristic_family") and cls["heuristic_family"] != cls["family"]:
            lines.append(f"**Heuristic said**: `{cls['heuristic_family']}` (LLM overrode)")
        lines.append(f"**Optimal strategy**: {d['optimal_strategy']}")
        if cls.get("optimal_path"):
            lines.append(f"**Optimal path**: {cls['optimal_path']}")
        if cls.get("divergence_point"):
            lines.append(f"**Divergence**: {cls['divergence_point']}")
        if cls.get("root_cause"):
            lines.append(f"**Root cause**: {cls['root_cause']}")
        lines.append(f"**Fix**: [{cls.get('fix_class', '?')}] {cls.get('fix_detail', cls.get('detail', ''))}")
        lines.append("")

        # Chunk search results
        cs = d["chunk_search"]
        lines.append(f"- **Chunk search**: {'FOUND' if cs['found'] else 'NOT FOUND'} in {cs['count']} chunks")
        if cs["chunks"]:
            for c in cs["chunks"][:2]:
                lines.append(f"  - Chunk: {c['title']} ({c['match_in']})")

        # Graph reachability
        gr = d["graph_reachability"]
        lines.append(f"- **Graph**: answer {'IN graph' if gr['answer_in_graph'] else 'NOT in graph'}, "
                      f"{gr['question_entities_found']} question entities found, "
                      f"{gr['paths_found']} paths")
        if gr["shortest_path"]:
            sp = gr["shortest_path"]
            lines.append(f"  - Shortest path ({sp['hops']} hops): {' → '.join(sp['path'][:5])}")

        # Agent trace
        at = d["agent_trace"]
        lines.append(f"- **Agent**: {at['total_tool_calls']} tool calls, "
                      f"answer {'in results' if at['answer_appeared_in_results'] else 'NOT in results'}")
        lines.append(f"  - Tools: {at['tools_used']}")
        if at["queries_issued"]:
            lines.append(f"  - Queries: {[q['query'][:50] for q in at['queries_issued'][:3]]}")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Oracle diagnostic for DIGIMON benchmark failures")
    parser.add_argument("--results", required=True, help="Path to benchmark results JSON")
    parser.add_argument("--question", help="Diagnose a single question ID")
    parser.add_argument("--report", help="Write markdown report to this path")
    parser.add_argument("--dataset", default="MuSiQue", help="Dataset name")
    parser.add_argument("--working-dir", default=".", help="DIGIMON working directory")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM verification (heuristic only)")
    args = parser.parse_args()

    wd = Path(args.working_dir)

    print("Loading benchmark results...")
    data = load_results(args.results)
    results = data.get("results", [])

    # Filter to failing questions
    failing = [r for r in results if not r.get("em")]
    if args.question:
        failing = [r for r in failing if r["id"] == args.question]
        if not failing:
            # Maybe they want to diagnose a passing question too
            failing = [r for r in results if r["id"] == args.question]

    print(f"Failing questions to diagnose: {len(failing)}")

    print("Loading corpus chunks...")
    corpus_path = wd / "results" / args.dataset / "corpus" / "Corpus.json"
    chunks = load_chunks(str(corpus_path))
    print(f"  Loaded {len(chunks)} chunks")

    print("Loading graph...")
    graph_path = wd / "results" / args.dataset / "er_graph" / "nx_data.graphml"
    G = load_graph(str(graph_path))
    print(f"  Loaded {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    print("Loading questions...")
    questions_path = wd / "Data" / args.dataset / "Question.json"
    questions = load_questions(str(questions_path))
    print(f"  Loaded {len(questions)} questions")

    # Run diagnostics
    use_llm = not args.no_llm
    if use_llm and HAS_LLM:
        print("LLM verification: ENABLED (gemini-2.5-flash-lite, ~$0.01/question)")
    else:
        print("LLM verification: DISABLED (heuristic only)")

    diagnoses = []
    for i, result in enumerate(failing):
        qid = result["id"]
        print(f"  [{i+1}/{len(failing)}] Diagnosing {qid}...")
        diag = diagnose_question(result, chunks, G, questions, use_llm=use_llm)
        diagnoses.append(diag)

        # Print summary line
        cls = diag["classification"]
        detail = cls.get('detail') or cls.get('root_cause') or cls.get('fix_detail') or '(no detail)'
        print(f"    → {cls['family']} ({cls.get('confidence', '?')}): {str(detail)[:80]}")

    # Summary
    print()
    families = Counter(d["classification"]["family"] for d in diagnoses)
    print("=== FAILURE FAMILY SUMMARY ===")
    for family, count in families.most_common():
        print(f"  {family}: {count}")

    # Generate report
    report = generate_report(diagnoses)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report)
        print(f"\nReport written to {args.report}")
    else:
        print()
        print(report)

    # Also write JSON diagnostics for machine consumption
    json_path = Path(args.results).with_suffix(".diagnostics.json")
    with open(json_path, "w") as f:
        json.dump(diagnoses, f, indent=2, default=str)
    print(f"JSON diagnostics written to {json_path}")


if __name__ == "__main__":
    main()
