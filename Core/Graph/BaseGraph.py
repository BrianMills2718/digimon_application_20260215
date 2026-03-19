import asyncio
from abc import ABC, abstractmethod
from collections import defaultdict
import igraph as ig
import numpy as np
from lazy_object_proxy.utils import await_
from scipy.sparse import csr_matrix

from Core.Common.Logger import logger
from Core.Common.entity_name_hygiene import classify_entity_name
from typing import List
from Core.Common.Constants import GRAPH_FIELD_SEP
from Core.Common.Memory import Memory
from Core.Prompt import GraphPrompt
from Core.Schema.ChunkSchema import TextChunk
from Core.Schema.EntityRelation import Entity, Relationship
from Core.Common.Utils import (clean_str, build_data_for_merge, csr_from_indices, csr_from_indices_list)
from Core.Storage.NetworkXStorage import NetworkXStorage
from Core.Utils.MergeER import MergeEntity, MergeRelationship


class BaseGraph(ABC):

    @property
    def capabilities(self):
        """Return set of GraphCapability flags derived from config."""
        from Core.Schema.GraphCapabilities import GraphCapability
        caps = set()
        # All graphs support basic subgraph operations
        caps.add(GraphCapability.SUPPORTS_SUBGRAPH)
        # Check config flags for capabilities
        cfg = self.config if self.config else None
        if cfg:
            if getattr(cfg, "enable_entity_types", False) or getattr(cfg, "extract_two_step", True) is False:
                caps.add(GraphCapability.HAS_ENTITY_TYPES)
            if getattr(cfg, "enable_edge_keywords", False):
                caps.add(GraphCapability.HAS_EDGE_KEYWORDS)
        # All non-tree graphs have descriptions and support PPR
        if not getattr(self, "_is_tree_graph", False):
            caps.add(GraphCapability.HAS_DESCRIPTIONS)
            caps.add(GraphCapability.HAS_EDGE_DESCRIPTIONS)
            caps.add(GraphCapability.SUPPORTS_PPR)
        else:
            caps.add(GraphCapability.HAS_TREE_LAYERS)
        if getattr(self, "_has_communities", False):
            caps.add(GraphCapability.HAS_COMMUNITIES)
        if getattr(self, "_is_passage_graph", False):
            caps.add(GraphCapability.HAS_PASSAGES)
        return caps

    async def load_persisted_graph(self, force: bool = False) -> bool:
        """
        Public method to explicitly load the graph from persisted storage.
        This method calls the load_graph method of the underlying storage object (self._graph).
        Returns True if loading was successful, False otherwise.
        """
        if self._graph is None:
            logger.error("Graph storage object (_graph) is not initialized in BaseGraph.")
            return False
        logger.info(f"Attempting to load persisted graph via {self._graph.__class__.__name__}.load_graph(force={force})")
        return await self._graph.load_graph(force)


    def __init__(self, config, llm, encoder):
        self.working_memory: Memory = Memory()  # Working memory
        self.config = config  # Build graph config
        self.llm = llm  # LLM instance
        self.ENCODER = encoder  # Encoder
        self._graph = None

    async def build_graph(self, chunks, force: bool = False) -> bool:
        """
        Builds or loads a graph based on the input chunks.

        Args:
            chunks: The input data chunks used to build the graph.
            force: Whether to re-build the graph
        Returns:
            Boolean indicating success (True) or failure (False) of the graph building process.
        """
        # Try to load the graph
        logger.info("Starting build graph for the given documents")
        build_successful = False

        is_exist = await self._load_graph(force)
        if force or not is_exist:
            # Check if a checkpoint exists — if so, we're resuming a partial build.
            # Don't clear the graph in that case; the checkpoint tracks what's done.
            has_checkpoint = hasattr(self, '_load_checkpoint') and self._load_checkpoint()
            if has_checkpoint:
                logger.info("Checkpoint found — resuming partial build (skipping graph clear)")
                # Load the partially-built graph from disk
                await self._load_graph(force=False)
            else:
                await self._clear()
            # Build the graph based on the input chunks
            build_successful = await self._build_graph(chunks)
            if build_successful:
                # Persist the graph into file only if build was successful
                await self._persist_graph(force)
                logger.info("Graph built successfully and persisted.")
            else:
                logger.error("Graph building failed in _build_graph, skipping persistence.")
        else:
            logger.info("Graph loaded from existing artifacts, build not forced.")
            build_successful = True  # Loading existing graph is a form of success

        if build_successful:
            logger.info("Finished the graph building stage successfully.")
        else:
            logger.error("Finished the graph building stage with errors.")

        return build_successful

    async def _load_graph(self, force: bool = False):
        """
        Try to load the graph from the file
        """
        return await self._graph.load_graph(force)

    @property
    def namespace(self):
        return None

    # TODO: Try to rewrite here, not now
    @namespace.setter
    def namespace(self, namespace):
        self._graph.namespace = namespace

    @property
    def entity_metakey(self):
        # For almost of graph, entity_metakey is "entity_name"
        return "entity_name"

    async def _merge_nodes_then_upsert(self, entity_name: str, nodes_data: List[Entity]):
        import asyncio
        from Core.Common.Logger import logger
        valid_entity_name, invalid_reason = classify_entity_name(entity_name)
        if not valid_entity_name:
            logger.error(
                "Rejecting invalid entity merge/upsert. entity_name=%r reason=%s",
                entity_name,
                invalid_reason,
            )
            raise ValueError(
                f"Invalid entity name for graph upsert: {entity_name!r} (reason={invalid_reason})"
            )
        existing_node = await self._graph.get_node(entity_name)

        existing_data = build_data_for_merge(existing_node) if existing_node else defaultdict(list)
        # Groups node properties by their keys for upsert operation.
        upsert_nodes_data = defaultdict(list)
        for node in nodes_data:
            for node_key, node_value in node.as_dict.items():
                upsert_nodes_data[node_key].append(node_value)

        merge_description = (MergeEntity.merge_descriptions(existing_data["description"],
                                                            upsert_nodes_data[
                                                                "description"]) if getattr(self.config, 'enable_entity_description', True) else None)

        description = (
            await self._handle_entity_relation_summary(entity_name, merge_description)
            if merge_description
            else ""
        )
        source_id = (MergeEntity.merge_source_ids(existing_data["source_id"],
                                                  upsert_nodes_data["source_id"]))

        new_entity_type = (MergeEntity.merge_types(existing_data["entity_type"], upsert_nodes_data[
            "entity_type"]) if getattr(self.config, 'enable_entity_type', True) else "")

        node_data = dict(source_id=source_id, entity_name=entity_name, entity_type=new_entity_type,
                         description=description)

        # Upsert the node with the merged data
        await self._graph.upsert_node(entity_name, node_data=node_data)

    async def _merge_edges_then_upsert(self, src_id: str, tgt_id: str, edges_data: List[Relationship]) -> None:
        import asyncio
        from Core.Common.Logger import logger
        # Check if the edge exists and fetch existing data
        existing_edge = await self._graph.get_edge(src_id, tgt_id) if await self._graph.has_edge(src_id,
                                                                                                 tgt_id) else None

        existing_edge_data = build_data_for_merge(existing_edge) if existing_edge else defaultdict(list)

        # Groups node properties by their keys for upsert operation.
        upsert_edge_data = defaultdict(list)
        for edge in edges_data:
            for edge_key, edge_value in edge.as_dict.items():
                upsert_edge_data[edge_key].append(edge_value)

        source_id = (MergeRelationship.merge_source_ids(existing_edge_data["source_id"],
                                                        upsert_edge_data["source_id"]))

        total_weight = (MergeRelationship.merge_weight(existing_edge_data["weight"],
                                                       upsert_edge_data["weight"]))
        merge_description = (MergeRelationship.merge_descriptions(existing_edge_data["description"],
                                                                  upsert_edge_data[
                                                                      "description"]) if getattr(self.config, 'enable_edge_description', True) else "")

        description = (
            await self._handle_entity_relation_summary((src_id, tgt_id), merge_description)
            if getattr(self.config, 'enable_edge_description', True)
            else ""
        )

        keywords = (MergeRelationship.merge_keywords(existing_edge_data["keywords"],
                                                     upsert_edge_data[
                                                         "keywords"]) if getattr(self.config, 'enable_edge_keywords', True) else "")

        relation_name = (MergeRelationship.merge_relation_name(existing_edge_data["relation_name"],
                                                               upsert_edge_data[
                                                                   "relation_name"]) if getattr(self.config, 'enable_edge_name', True) else "")
        # Ensure src_id and tgt_id nodes exist
        for node_id in (src_id, tgt_id):
            if not await self._graph.has_node(node_id):
                # Upsert node with source_id and entity_name
                await self._graph.upsert_node(
                    node_id,
                    node_data=dict(source_id=source_id, entity_name=node_id, entity_type="", description="")
                )

        # Create edge_data with merged data
        edge_data = dict(weight=total_weight, source_id=source_id,
                         relation_name=relation_name, keywords=keywords, description=description, src_id=src_id,
                         tgt_id=tgt_id)
        # Upsert the edge with the merged data
        await self._graph.upsert_edge(src_id, tgt_id, edge_data=edge_data)

    @abstractmethod
    def _extract_entity_relationship(self, chunk_key_pair: tuple[str, TextChunk]):
        """
        Abstract method to extract entities and the relationships between their in the graph.

        This method should be implemented by subclasses to define how node relationships are extracted.
        """
        pass

    @abstractmethod
    def _build_graph(self, chunks):
        """
        Abstract method to build the graph based on the input chunks.

        Args:
            chunks: The input data chunks used to build the graph.

        This method should be implemented by subclasses to define how the graph is built from the input chunks.
        """
        pass

    async def augment_graph_by_similarity_search(self, entity_vdb, duplicate=False):
        logger.info("Starting augment the existing graph with similariy edges")



        ranking  = {}
        failed_nodes = []
        import tqdm
        for node in tqdm.tqdm(await self._graph.nodes(), total=len(await self._graph.nodes())):
            try:
                ranking[node] = await entity_vdb.retrieval(query=node, top_k=self.config.similarity_top_k)
            except Exception as e:
                failed_nodes.append(node)
                logger.warning(f"Vector similarity: skipping node {node!r}: {e}")
        if failed_nodes:
            logger.warning(f"Vector similarity: {len(failed_nodes)} nodes failed embedding")
        # For FAISS index, it uses L2-distance 
        is_euclidean_distance = False
        kb_similarity = defaultdict(list)
        for key, rank in ranking.items():
            if not rank:
                continue
            max_score = max(ns_item.score for ns_item in rank)  # find the max score
            if max_score == 0:
                continue
            for idx, ns_item in enumerate(rank):
                entity_name = ns_item.metadata.get('entity_name') if ns_item.metadata else None
                if not entity_name:
                    continue
                score = ns_item.score
                if idx == 0 and score == 0:
                    # L1 or L2 distance
                    is_euclidean_distance = True
                if not duplicate and idx == 0:
                    continue
                if is_euclidean_distance:
                    kb_similarity[key].append((entity_name, 1 - score / max_score))
                else:
                    kb_similarity[key].append((entity_name,  score / max_score))
        maybe_edges = defaultdict(list)
        # Refactored second part using dictionary iteration and enumerate
        for src_id, nns in kb_similarity.items():
    
            for idx, (nn, score) in enumerate(nns):
       
                if score < self.config.similarity_threshold or idx >= self.config.similarity_top_k:
                    break
                if nn == src_id:
                    continue
                tgt_id = nn

                # No need source_id for this type of edges
                relationship = Relationship(src_id=clean_str(src_id),
                                            tgt_id=clean_str(tgt_id),
                                            source_id="N/A",
                                            weight=self.config.similarity_max * score, relation_name="similarity")
                maybe_edges[(relationship.src_id, relationship.tgt_id)].append(relationship)

        # Merge the edges
        maybe_edges_aug = defaultdict(list)
        for k, v in maybe_edges.items():
            maybe_edges_aug[tuple(sorted(k))].extend(v)
        logger.info(f"Augmenting graph with {len(maybe_edges_aug)} edges")
     
        await asyncio.gather(*[self._merge_edges_then_upsert(k[0], k[1], v) for k, v in maybe_edges.items()])
        await self._persist_graph(force=True)
        logger.info("✅ Finished augment the existing graph with similariy edges")

    async def augment_graph_by_string_similarity(self) -> int:
        """Add name_similarity edges between entities with similar names.

        Uses an inverted token index for candidate generation, then scores
        with difflib.SequenceMatcher. Returns the number of edges added.
        """
        import re
        from difflib import SequenceMatcher

        STOP_WORDS = frozenset({
            "the", "a", "an", "of", "in", "on", "at", "to", "for", "and",
            "or", "is", "was", "are", "were", "be", "been", "with", "from",
            "by", "as", "it", "its", "this", "that", "not", "but", "has",
            "had", "have", "do", "does", "did", "will", "would", "can",
            "could", "should", "may", "might",
        })
        MIN_TOKEN_LEN = 3

        threshold = getattr(self.config, "string_similarity_threshold", 0.65)
        min_name_len = getattr(self.config, "string_similarity_min_name_length", 4)

        all_nodes = await self._graph.nodes()
        logger.info(f"String similarity: scanning {len(all_nodes)} nodes (threshold={threshold})")

        # Filter out short / purely numeric names
        _numeric_re = re.compile(r"^[\d\s\-/]+$")
        valid_nodes = [n for n in all_nodes if len(n) >= min_name_len and not _numeric_re.match(n)]
        logger.info(f"String similarity: {len(valid_nodes)} nodes after filtering")

        # Build inverted token index
        token_to_nodes: dict[str, list[str]] = defaultdict(list)
        for node in valid_nodes:
            tokens = node.lower().split()
            for tok in tokens:
                if len(tok) >= MIN_TOKEN_LEN and tok not in STOP_WORDS:
                    token_to_nodes[tok].append(node)

        # Generate candidate pairs (share at least one token)
        candidate_pairs: set[tuple[str, str]] = set()
        for tok, nodes_with_tok in token_to_nodes.items():
            if len(nodes_with_tok) > 500:
                # Skip extremely common tokens to avoid quadratic blow-up
                continue
            for i in range(len(nodes_with_tok)):
                for j in range(i + 1, len(nodes_with_tok)):
                    pair = tuple(sorted((nodes_with_tok[i], nodes_with_tok[j])))
                    candidate_pairs.add(pair)

        logger.info(f"String similarity: {len(candidate_pairs)} candidate pairs from inverted index")

        # Score candidates
        maybe_edges: dict[tuple[str, str], list] = defaultdict(list)
        for a, b in candidate_pairs:
            # Skip if edge already exists
            if await self._graph.has_edge(a, b) or await self._graph.has_edge(b, a):
                continue
            score = SequenceMatcher(None, a.lower(), b.lower()).ratio()
            if score >= threshold:
                relationship = Relationship(
                    src_id=clean_str(a),
                    tgt_id=clean_str(b),
                    source_id="N/A",
                    weight=score,
                    relation_name="name_similarity",
                )
                maybe_edges[(relationship.src_id, relationship.tgt_id)].append(relationship)

        logger.info(f"String similarity: adding {len(maybe_edges)} name_similarity edges")

        if maybe_edges:
            await asyncio.gather(
                *[self._merge_edges_then_upsert(k[0], k[1], v) for k, v in maybe_edges.items()]
            )
            await self._persist_graph(force=True)

        logger.info(f"✅ Finished string similarity augmentation ({len(maybe_edges)} edges)")
        return len(maybe_edges)

    async def augment_graph_by_chunk_cooccurrence(self, weight: float = 0.5) -> int:
        """Add chunk_cooccurrence edges between entities sharing a source chunk.

        Reads all nodes, groups by source_id chunks, and creates edges for
        entity pairs that co-occur in the same chunk but lack an explicit edge.
        Can be run on an existing graph without rebuilding.

        Returns the number of edges added.
        """
        from itertools import combinations

        all_node_data = await self._graph.get_nodes_data()
        logger.info(f"Chunk co-occurrence: scanning {len(all_node_data)} nodes")

        # Group entity names by chunk
        chunk_to_entities: dict[str, list[str]] = defaultdict(list)
        for node in all_node_data:
            name = node.get("entity_name", node.get("id", ""))
            source_id = node.get("source_id", "")
            for chunk_id in source_id.split(GRAPH_FIELD_SEP):
                if chunk_id:
                    chunk_to_entities[chunk_id].append(name)

        # Create edges for co-occurring pairs without existing edges
        maybe_edges: dict[tuple[str, str], list] = defaultdict(list)
        for chunk_id, entities in chunk_to_entities.items():
            unique = list(set(entities))
            for a, b in combinations(unique, 2):
                pair = tuple(sorted((a, b)))
                if pair in maybe_edges:
                    continue
                if await self._graph.has_edge(a, b) or await self._graph.has_edge(b, a):
                    continue
                maybe_edges[pair].append(Relationship(
                    src_id=a,
                    tgt_id=b,
                    source_id=chunk_id,
                    relation_name="chunk_cooccurrence",
                    weight=weight,
                    description="",
                ))

        logger.info(f"Chunk co-occurrence: adding {len(maybe_edges)} edges")

        if maybe_edges:
            await asyncio.gather(
                *[self._merge_edges_then_upsert(k[0], k[1], v) for k, v in maybe_edges.items()]
            )
            await self._persist_graph(force=True)

        logger.info(f"✅ Finished chunk co-occurrence augmentation ({len(maybe_edges)} edges)")
        return len(maybe_edges)

    async def augment_graph_with_centrality(self) -> dict:
        """Compute centrality metrics and store as node attributes.

        Computes PageRank, degree centrality, and betweenness centrality,
        then stores them directly on each node. These persist with the graph.

        Returns dict with metric names and value ranges.
        """
        import networkx as nx

        G = self._graph._graph  # underlying NetworkX graph

        if len(G) == 0:
            logger.warning("Centrality: graph is empty, nothing to compute")
            return {"nodes": 0}

        pagerank = nx.pagerank(G, weight="weight")
        degree_cent = nx.degree_centrality(G)
        # betweenness is O(VE) — skip for very large graphs
        if len(G) <= 5000:
            betweenness = nx.betweenness_centrality(G, weight="weight")
        else:
            logger.info(f"Centrality: skipping betweenness for {len(G)}-node graph (too large)")
            betweenness = {}

        for node_id in G.nodes():
            G.nodes[node_id]["pagerank"] = pagerank.get(node_id, 0.0)
            G.nodes[node_id]["degree_centrality"] = degree_cent.get(node_id, 0.0)
            if betweenness:
                G.nodes[node_id]["betweenness"] = betweenness.get(node_id, 0.0)

        await self._persist_graph(force=True)

        stats = {
            "nodes_updated": len(G),
            "pagerank_max": max(pagerank.values()) if pagerank else 0,
            "degree_centrality_max": max(degree_cent.values()) if degree_cent else 0,
        }
        if betweenness:
            stats["betweenness_max"] = max(betweenness.values())
        logger.info(f"✅ Centrality metrics stored on {len(G)} nodes: {stats}")
        return stats

    async def augment_graph_by_synonym_detection(
        self, entity_vdb, threshold: float = 0.92, max_per_entity: int = 3
    ) -> int:
        """Detect near-duplicate entities via VDB embedding similarity and add SYNONYM edges.

        Entities above the similarity threshold that don't already share an edge
        get a 'synonym' edge. This helps entity linking at query time.

        Args:
            entity_vdb: Built entity VDB (FaissIndex) with .retrieval()
            threshold: Cosine similarity threshold (default 0.92 — very high to avoid false positives)
            max_per_entity: Max synonym candidates per entity

        Returns the number of synonym edges added.
        """
        nodes = await self._graph.nodes()
        if not nodes:
            return 0

        added = 0
        seen_pairs: set[tuple[str, str]] = set()

        for node_name in nodes:
            try:
                results = await entity_vdb.retrieval(query=node_name, top_k=max_per_entity + 1)
            except Exception as e:
                logger.debug(f"Synonym search failed for '{node_name}': {e}")
                continue

            if not results:
                continue

            # Normalize scores (same logic as augment_graph_by_similarity_search)
            max_score = max(ns.score for ns in results)
            if max_score == 0:
                continue
            is_euclidean = results[0].score == 0

            for i, ns in enumerate(results):
                match_name = ns.metadata.get("entity_name") if ns.metadata else None
                if not match_name or match_name == node_name:
                    continue
                score = (1 - ns.score / max_score) if is_euclidean else (ns.score / max_score)
                if score < threshold:
                    continue

                pair = tuple(sorted((node_name, match_name)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                if await self._graph.has_edge(node_name, match_name) or await self._graph.has_edge(match_name, node_name):
                    continue

                await self._graph.upsert_edge(
                    node_name, match_name,
                    edge_data=dict(
                        weight=score,
                        source_id="",
                        relation_name="synonym",
                        keywords="",
                        description=f"Embedding similarity {score:.3f}",
                        src_id=node_name,
                        tgt_id=match_name,
                    ),
                )
                added += 1

        if added:
            await self._persist_graph(force=True)
        logger.info(f"✅ Synonym detection: added {added} edges (threshold={threshold})")
        return added

    async def __graph__(self, elements: list):
        """
        Build the graph based on the input elements.
        """
        import asyncio
        from itertools import combinations
        from Core.Common.Logger import logger
        from Core.Schema.EntityRelation import Relationship

        # Initialize dictionaries to hold aggregated node and edge information
        maybe_nodes, maybe_edges = defaultdict(list), defaultdict(list)

        # Iterate through each tuple of nodes and edges in the input elements
        for m_nodes, m_edges in elements:
            # Aggregate node information
            for k, v in m_nodes.items():
                maybe_nodes[k].extend(v)

            # Aggregate edge information
            for k, v in m_edges.items():
                maybe_edges[tuple(sorted(k))].extend(v)

        # Add co-occurrence edges if enabled in config
        if getattr(self.config, "enable_chunk_cooccurrence", False):
            chunk_to_entities: dict[str, list[str]] = defaultdict(list)
            for entity_name, entity_list in maybe_nodes.items():
                for entity in entity_list:
                    for chunk_id in entity.source_id.split(GRAPH_FIELD_SEP):
                        if chunk_id:
                            chunk_to_entities[chunk_id].append(entity_name)

            cooccur_count = 0
            for chunk_id, entities in chunk_to_entities.items():
                unique_entities = list(set(entities))
                for a, b in combinations(unique_entities, 2):
                    edge_key = tuple(sorted((a, b)))
                    if edge_key not in maybe_edges:
                        maybe_edges[edge_key].append(Relationship(
                            src_id=a,
                            tgt_id=b,
                            source_id=chunk_id,
                            relation_name="chunk_cooccurrence",
                            weight=0.5,
                            description="",
                        ))
                        cooccur_count += 1

            if cooccur_count:
                logger.info(f"Added {cooccur_count} chunk co-occurrence edges")

        # Asynchronously merge and upsert nodes
        await asyncio.gather(*[self._merge_nodes_then_upsert(k, v) for k, v in maybe_nodes.items()])

        # Asynchronously merge and upsert edges
        await asyncio.gather(*[self._merge_edges_then_upsert(k[0], k[1], v) for k, v in maybe_edges.items()])

    async def _handle_entity_relation_summary(self, entity_or_relation_name: str, description: str) -> str:
        """
           Generate a summary for an entity or relationship.

           Args:
               entity_or_relation_name (str): The name of the entity or relationship.
               description (str): The detailed description of the entity or relationship.

           Returns:
               str: The generated summary.
        """

        # Encode the description into tokens
        tokens = self.ENCODER.encode(description)

        # Check if the token length is within the maximum allowed tokens for summarization
        summary_max_tokens = getattr(self.config, 'summary_max_tokens', None)
        if summary_max_tokens is None:
            # Try to get from graph config
            summary_max_tokens = getattr(self.config.graph, 'summary_max_tokens', 500) if hasattr(self.config, 'graph') else 500
        
        if len(tokens) < summary_max_tokens:
            return description
        # Truncate the description to fit within the maximum token limit
        llm_model_max_token_size = getattr(self.config, 'llm_model_max_token_size', None)
        if llm_model_max_token_size is None:
            # Try to get from graph config
            llm_model_max_token_size = getattr(self.config.graph, 'llm_model_max_token_size', 32768) if hasattr(self.config, 'graph') else 32768
        
        use_description = self.ENCODER.decode(tokens[:llm_model_max_token_size])

        # Construct the context base for the prompt
        context_base = dict(
            entity_name=entity_or_relation_name,
            description_list=use_description.split(GRAPH_FIELD_SEP)
        )
        use_prompt = GraphPrompt.SUMMARIZE_ENTITY_DESCRIPTIONS.format(**context_base)
        logger.debug(f"Trigger summary: {entity_or_relation_name}")

        # Asynchronously generate the summary using the language model
        max_tokens = getattr(self.config, 'summary_max_tokens', 256)  # Default to 256 if not set
        return await self.llm.aask(use_prompt, max_tokens=max_tokens)

    async def _persist_graph(self, force = False):
        await self._graph.persist(force)

    async def nodes_data(self):
        return await self._graph.get_nodes_data()

    async def edges_data(self, need_content=True):
        return await self._graph.get_edges_data(need_content)

    async def subgraphs_data(self):
        return await self._graph.get_subgraph_from_same_chunk()

    async def node_metadata(self):
        return await self._graph.get_node_metadata()

    async def edge_metadata(self):
        return await self._graph.get_edge_metadata()

    async def subgraph_metadata(self):
        return await self._graph.get_subgraph_metadata()

    async def stable_largest_cc(self):
        if isinstance(self._graph, NetworkXStorage):
            return await self._graph.get_stable_largest_cc()
        else:
            logger.exception("**Only NETWORKX is supported for finding the largest connected component.** ")
            return None

    async def cluster_data_to_subgraphs(self, cluster_data: dict):
        if isinstance(self._graph, NetworkXStorage):

            await self._graph.cluster_data_to_subgraphs(cluster_data)
        else:
            logger.exception("**Only NETWORKX is supported for constructing the cluster <-> node mapping.** ")
            return None

    async def community_schema(self):
        return await self._graph.get_community_schema()

    async def get_node(self, node_id):
        return await self._graph.get_node(node_id)

    async def get_node_by_index(self, index):
        return await self._graph.get_node_by_index(index)

    async def get_edge_by_index(self, index):
        return await self._graph.get_edge_by_index(index)

    async def get_node_by_indices(self, node_idxs):
        return await asyncio.gather(
            *[self.get_node_by_index(node_idx) for node_idx in node_idxs]
        )

    async def get_edge_by_indices(self, edge_idxs):
        return await asyncio.gather(
            *[self.get_edge_by_index(edge_idx) for edge_idx in edge_idxs]
        )

    async def get_edge(self, src, tgt):
        return await self._graph.get_edge(src, tgt)

    async def nodes(self):
        return await self._graph.nodes()

    async def edges(self):
        return await self._graph.edges()

    async def node_degree(self, node_id):
        return await self._graph.node_degree(node_id)

    async def edge_degree(self, src_id: str, tgt_id: str):
        return await self._graph.edge_degree(src_id, tgt_id)

    async def get_node_edges(self, source_node_id: str):
        return await self._graph.get_node_edges(source_node_id)

    @property
    def node_num(self):
        return self._graph.get_node_num()

    @property
    def edge_num(self):
        return self._graph.get_edge_num()

    def get_induced_subgraph(self, nodes: list[str]):
        return self._graph.get_induced_subgraph(nodes)

    async def get_entities_to_relationships_map(self, is_directed=False):
        if self.node_num == 0:
            return csr_matrix((0, 0))

        node_neighbors = {node: list(await self._graph.neighbors(node)) for node in await self._graph.nodes()}

        # Construct the row and column indices for the CSR matrix
        data = []
        for node, neighbors in node_neighbors.items():
            for neighbor in neighbors:
                # Get the edge index (assuming edge indices are unique)
                edge_index = self._graph.get_edge_index(node, neighbor)
                if edge_index == -1: continue
                node_index = await self._graph.get_node_index(node)
                data.append([node_index, edge_index])
                if not is_directed:
                    neighbor_index = await self._graph.get_node_index(neighbor)
                    data.append([neighbor_index, edge_index])

        # Get the number of nodes and edges
        node_count = self.node_num
        edge_count = self.edge_num
        # Construct the CSR matrix
        return csr_from_indices(data, shape=(node_count, edge_count))

    async def get_relationships_attrs(self, key):
        if self.edge_num == 0:
            return []
        lists_of_attrs = []
        for edge in await self.edges_data(False):
            lists_of_attrs.append(edge[key])
        return lists_of_attrs

    async def get_relationships_to_chunks_map(self, doc_chunk):
        raw_relationships_to_chunks = await self.get_relationships_attrs(key="source_id")
        # Map Chunk IDs to indices

        raw_relationships_to_chunks = [
            [i for i in await doc_chunk.get_index_by_merge_key(chunk_ids) if i is not None]
            for chunk_ids in raw_relationships_to_chunks
        ]
        return csr_from_indices_list(
            raw_relationships_to_chunks, shape=(len(raw_relationships_to_chunks), await doc_chunk.size)
        )

    async def get_edge_weight(self, src_id: str, tgt_id: str):
        return await self._graph.get_edge_weight(src_id, tgt_id)

    async def get_node_index(self, node_key):
        return await self._graph.get_node_index(node_key)

    async def get_node_indices(self, node_keys):
        return await asyncio.gather(
            *[self.get_node_index(node_key) for node_key in node_keys]
        )

    async def personalized_pagerank(self, reset_prob_chunk, damping: float = 0.1):
        pageranked_probabilities = []
        igraph_ = ig.Graph.from_networkx(self._graph.graph)
        igraph_.es['weight'] = [await self.get_edge_weight(edge[0], edge[1]) for edge in list(await self.edges())]

        for reset_prob in reset_prob_chunk:
            pageranked_probs = igraph_.personalized_pagerank(vertices=range(self.node_num), damping=damping,
                                                             directed=False,
                                                             weights='weight', reset=reset_prob,
                                                             implementation='prpack')

            pageranked_probabilities.append(np.array(pageranked_probs))
        pageranked_probabilities = np.array(pageranked_probabilities)

        return pageranked_probabilities[0]

    async def get_neighbors(self, node_id: str):
        return await self._graph.neighbors(node_id)

    async def get_nodes(self):
        return await self._graph.nodes()

    async def find_k_hop_neighbors_batch(self, start_nodes: list[str], k: int):
        return await self._graph.find_k_hop_neighbors_batch(start_nodes=start_nodes, k=k)  # set

    async def get_edge_relation_name_batch(self, edges: list[tuple[str, str]]):
        return await self._graph.get_edge_relation_name_batch(edges=edges)

    async def get_neighbors_from_sources(self, start_nodes: list[str]):
        return await self._graph.get_neighbors_from_sources(start_nodes=start_nodes)

    async def get_paths_from_sources(self, start_nodes: list[str], cutoff: int = 5) -> list[tuple[str, str, str]]:
        return await self._graph.get_paths_from_sources(start_nodes=start_nodes)

    async def _clear(self):
        self._graph.clear()
