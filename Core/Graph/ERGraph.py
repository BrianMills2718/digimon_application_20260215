"""Entity-graph builder supporting both two-step KG extraction and richer delimiter extraction.

The class now sits on top of an explicit build contract: graph profile,
schema-guided extraction, and persisted manifest truth. The first rebuild slice
still preserves the two existing extraction strategies, but routes both through
the same schema/profile intent so later benchmarks can reproduce what was
actually built.
"""

import asyncio
import json
import os
from collections import defaultdict
from typing import Any, List
from Core.Graph.BaseGraph import BaseGraph
from Core.Graph.DelimiterExtraction import DelimiterExtractionMixin
from Core.Schema.GraphBuildTypes import GraphSchemaMode
from Core.Common.graph_schema_guidance import resolve_entity_type_names, resolve_relation_type_names
from Core.Common.entity_name_hygiene import classify_entity_name
from Core.Common.Logger import logger
from Core.Common.Utils import (
    clean_str,
    prase_json_from_response
)
from Core.Schema.ChunkSchema import TextChunk
from Core.Prompt import GraphPrompt
from Core.Schema.EntityRelation import Entity, Relationship
from Core.Storage.NetworkXStorage import NetworkXStorage


class ERGraph(DelimiterExtractionMixin, BaseGraph):
    """Build entity-relation graphs from chunks using one of two extraction modes."""

    def __init__(self, config, llm, encoder, storage_instance=None):
        """
        Args:
            config: GraphConfig
            llm: LLM instance
            encoder: encoder instance
            storage_instance: Optional[NetworkXStorage], if provided will be used as the graph storage
        """
        # BaseGraph.ENCODER must expose .encode()/.decode() for tokenization.
        # If the caller passed an embedding model instead, wrap with TokenizerWrapper.
        tokenizer = encoder
        if not hasattr(encoder, 'decode'):
            from Core.Common.TokenizerWrapper import TokenizerWrapper
            tokenizer = TokenizerWrapper()
        super().__init__(config, llm, tokenizer)
        self._graph = storage_instance if storage_instance is not None else NetworkXStorage()

    # ------------------------------------------------------------------
    # Two-step extraction (NER + OpenIE) — produces KG-level attributes
    # ------------------------------------------------------------------

    def _build_ner_guidance(self) -> str:
        """Return optional entity-type guidance text for the NER prompt."""

        entity_types = resolve_entity_type_names(self.config)
        if not entity_types:
            return ""
        return "\n\nFocus on extracting these entity types when applicable:\n" + "\n".join(
            f"- {entity_type}" for entity_type in entity_types
        )

    def _build_openie_guidance(self) -> str:
        """Return optional relation-type guidance text for the OpenIE prompt."""

        relation_types = resolve_relation_type_names(self.config)
        if not relation_types:
            return ""

        schema_mode = getattr(self.config, "schema_mode", "open")
        if GraphSchemaMode.parse(schema_mode) is GraphSchemaMode.SCHEMA_CONSTRAINED:
            intro = "IMPORTANT: Only use these relationship types:"
        else:
            intro = "IMPORTANT: Prefer these relationship types when applicable:"

        return "\n\n" + intro + "\n" + "\n".join(f"- {relation_type}" for relation_type in relation_types)

    async def _named_entity_recognition(self, passage: str):
        from Core.Common.TokenBudgetManager import TokenBudgetManager

        # Check if passage needs truncation
        if TokenBudgetManager.should_chunk_content(passage, self.llm.model, "graph_extraction"):
            logger.warning(f"Passage too long ({len(passage)} chars), truncating for NER")
            passage = passage[:3000] + "...[truncated]"

        ner_messages = GraphPrompt.NER.format(user_input=passage) + self._build_ner_guidance()
        llm_output_str = await self.llm.aask(ner_messages, format="json")

        parsed_output = None
        if isinstance(llm_output_str, str):
            parsed_output = prase_json_from_response(llm_output_str)
            if not parsed_output:
                logger.error(f"NER - Could not parse JSON from: {llm_output_str[:500]}")
                return []
        elif isinstance(llm_output_str, dict):
            parsed_output = llm_output_str
        else:
            logger.error(f"NER - Unexpected LLM output type: {type(llm_output_str)}")
            return []

        if not isinstance(parsed_output, dict) or 'named_entities' not in parsed_output or not isinstance(parsed_output.get('named_entities'), list):
            logger.warning(f"NER - 'named_entities' key missing or not a list in parsed output: {parsed_output}")
            return []

        return parsed_output['named_entities']

    async def _openie_post_ner_extract(self, chunk, entities):
        from Core.Common.TokenBudgetManager import TokenBudgetManager

        if TokenBudgetManager.should_chunk_content(chunk, self.llm.model, "graph_extraction"):
            logger.warning(f"Chunk too long ({len(chunk)} chars), truncating for OpenIE")
            chunk = chunk[:3000] + "...[truncated]"

        named_entity_json = {"named_entities": entities}

        prompt_with_ontology = GraphPrompt.OPENIE_POST_NET.format(
            passage=chunk,
            named_entity_json=json.dumps(named_entity_json)
        ) + self._build_openie_guidance()

        llm_output_str = await self.llm.aask(prompt_with_ontology, format="json")

        parsed_output = None
        if isinstance(llm_output_str, str):
            parsed_output = prase_json_from_response(llm_output_str)
            if not parsed_output:
                logger.error(f"OpenIE - Could not parse JSON from: {llm_output_str[:500]}")
                return []
        elif isinstance(llm_output_str, dict):
            parsed_output = llm_output_str
        else:
            logger.error(f"OpenIE - Unexpected LLM output type: {type(llm_output_str)}")
            return []

        logger.debug(f"OpenIE extracted response: {json.dumps(parsed_output, indent=2)[:500]}...")

        if not isinstance(parsed_output, dict) or 'triples' not in parsed_output or not isinstance(parsed_output.get('triples'), list):
            logger.warning(f"OpenIE - 'triples' key missing or not a list in parsed output: {parsed_output}")
            return []

        return parsed_output['triples']

    # ------------------------------------------------------------------
    # Dispatch: two-step vs. delimiter-based extraction
    # ------------------------------------------------------------------

    async def _extract_entity_relationship(self, chunk_key_pair: tuple[str, TextChunk]) -> Any:
        chunk_key, chunk_info = chunk_key_pair

        if self.config.extract_two_step:
            # Two-step NER + OpenIE → KG-level (entity name, relation name, edge weight)
            content = chunk_info.content
            entities = await self._named_entity_recognition(content)
            # Skip relationship extraction if configured (EcphoryRAG hypothesis:
            # co-occurrence edges may be sufficient without explicit relationships)
            if getattr(self.config, "skip_relationship_extraction", False):
                triples = []
            else:
                triples = await self._openie_post_ner_extract(content, entities)
            return await self._build_graph_from_tuples(entities, triples, chunk_key)
        else:
            # ENTITY_EXTRACTION prompt via mixin → TKG/RKG-level attributes
            # Uses ENTITY_EXTRACTION_KEYWORD when enable_edge_keywords=True (RKG)
            # Uses ENTITY_EXTRACTION otherwise (TKG)
            records = await self._extract_records_from_chunk(chunk_info)
            if getattr(self.config, "skip_relationship_extraction", False):
                # Keep only entity records, drop relationships.
                # Records are delimiter-separated strings; entity records
                # contain '"entity"' as first field, relationships don't.
                records = [r for r in records if '"entity"' in r.lower()]
            return await self._build_graph_from_records(records, chunk_key)

    # ------------------------------------------------------------------
    # Graph building orchestration
    # ------------------------------------------------------------------

    def _checkpoint_path(self) -> str | None:
        """Return path for checkpoint file, or None if no namespace set."""
        if self._graph and getattr(self._graph, 'namespace', None):
            import os
            save_dir = self._graph.namespace.get_save_path()
            return os.path.join(save_dir, "_checkpoint_processed.json")
        return None

    def _load_checkpoint(self) -> set[int]:
        """Load set of already-processed chunk indices from checkpoint file."""
        path = self._checkpoint_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return set(json.loads(f.read()))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not load checkpoint: {e}")
        return set()

    def _save_checkpoint(self, processed: set[int]) -> None:
        """Persist set of processed chunk indices."""
        path = self._checkpoint_path()
        if path:
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(json.dumps(sorted(processed)))

    def clear_checkpoint(self) -> None:
        """Remove checkpoint file (called after successful complete build)."""
        path = self._checkpoint_path()
        if path and os.path.exists(path):
            os.remove(path)
            logger.info("Cleared build checkpoint")

    async def _build_graph(self, chunk_list: List[Any]) -> bool:
        from Core.Common.TokenBudgetManager import TokenBudgetManager
        import os

        try:
            # Only generate ontology when explicitly enabled via config
            if getattr(self.config, 'auto_generate_ontology', False):
                if not hasattr(self.config, 'loaded_custom_ontology') or self.config.loaded_custom_ontology is None:
                    context_chunks = chunk_list[:min(10, len(chunk_list))]
                    context = "Content samples:\n"

                    for chunk in context_chunks:
                        chunk_content = ""
                        if hasattr(chunk, 'content'):
                            chunk_content = chunk.content
                        else:
                            chunk_content = str(chunk)

                        sample = chunk_content[:500] + "..." if len(chunk_content) > 500 else chunk_content
                        context += f"- {sample}\n"

                        if TokenBudgetManager.should_chunk_content(context, self.llm.model, "ontology_generation"):
                            logger.info(f"Context size reaching limit, using {len(context_chunks)} chunks for ontology")
                            break

                    from Core.Graph.ontology_generator import generate_custom_ontology
                    logger.info("Generating custom ontology based on corpus content...")
                    custom_ontology = await generate_custom_ontology(context, self.llm)

                    if custom_ontology:
                        self.config.loaded_custom_ontology = custom_ontology
                        logger.info(f"Successfully generated custom ontology with {len(custom_ontology.get('entities', []))} entities and {len(custom_ontology.get('relations', []))} relations")
                    else:
                        logger.warning("Failed to generate custom ontology, proceeding with generic extraction")

            # Load checkpoint — skip already-processed chunks on resume
            already_processed = self._load_checkpoint()
            if already_processed:
                logger.info(f"Resuming from checkpoint: {len(already_processed)}/{len(chunk_list)} chunks already processed")

            # Index all chunks so we can track by position
            indexed_chunks = list(enumerate(chunk_list))
            remaining = [(i, c) for i, c in indexed_chunks if i not in already_processed]

            if not remaining:
                logger.info("All chunks already processed (checkpoint), skipping extraction")
                return True

            logger.info(f"Processing {len(remaining)} chunks ({len(already_processed)} already done)")

            batch_size = 50
            total_batches = (len(remaining) + batch_size - 1) // batch_size

            for batch_start in range(0, len(remaining), batch_size):
                batch = remaining[batch_start:batch_start + batch_size]
                batch_num = batch_start // batch_size + 1
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)")

                # Per-chunk timeout prevents a single hung LLM call from blocking
                # the entire batch. 300s (5 min) is generous — typical extraction
                # takes 5-30s. Timed-out chunks are logged and skipped.
                per_chunk_timeout = 300
                results = await asyncio.gather(
                    *[asyncio.wait_for(
                        self._extract_entity_relationship(chunk),
                        timeout=per_chunk_timeout,
                    ) for _, chunk in batch],
                    return_exceptions=True,
                )

                # Separate successes from failures
                good_results = []
                batch_indices = []
                failed_count = 0
                for (idx, _chunk), result in zip(batch, results):
                    if isinstance(result, Exception):
                        failed_count += 1
                        logger.warning(f"Chunk {idx} extraction failed: {result}")
                    else:
                        good_results.append(result)
                        batch_indices.append(idx)

                if failed_count:
                    logger.warning(f"Batch {batch_num}: {failed_count} failures, {len(good_results)} successes")

                if good_results:
                    await self.__graph__(good_results)

                # Update checkpoint with successfully processed indices
                already_processed.update(batch_indices)
                self._save_checkpoint(already_processed)
                await self._persist_graph(force=True)
                logger.info(f"Checkpoint saved: {len(already_processed)}/{len(chunk_list)} chunks processed")

            # Retry failed chunks (those not in already_processed)
            all_indices = set(range(len(chunk_list)))
            failed_indices = all_indices - already_processed
            if failed_indices:
                logger.warning(f"Retrying {len(failed_indices)} failed chunks")
                retry_chunks = [(i, chunk_list[i]) for i in sorted(failed_indices)]
                for batch_start in range(0, len(retry_chunks), batch_size):
                    batch = retry_chunks[batch_start:batch_start + batch_size]
                    results = await asyncio.gather(
                        *[asyncio.wait_for(
                            self._extract_entity_relationship(chunk),
                            timeout=per_chunk_timeout,
                        ) for _, chunk in batch],
                        return_exceptions=True,
                    )
                    for (idx, _chunk), result in zip(batch, results):
                        if isinstance(result, Exception):
                            logger.error(f"Chunk {idx} failed on retry: {result}")
                        else:
                            await self.__graph__([result])
                            already_processed.add(idx)
                    self._save_checkpoint(already_processed)
                    await self._persist_graph(force=True)

            # Persist any permanently failed chunk indices
            final_failed = all_indices - already_processed
            if final_failed:
                save_dir = self._graph.namespace.get_save_path() if self._graph and getattr(self._graph, 'namespace', None) else "."
                failed_path = os.path.join(save_dir, "failed_chunks.json")
                with open(failed_path, 'w') as f:
                    f.write(json.dumps(sorted(final_failed)))
                logger.error(
                    f"Build complete with {len(final_failed)} permanently failed chunks. "
                    f"Indices saved to {failed_path}"
                )
            else:
                self.clear_checkpoint()
                logger.info("Successfully built graph — all chunks processed")
            return True
        except Exception as e:
            # Persist whatever we've built so far
            if already_processed:
                logger.warning(f"Build interrupted after {len(already_processed)}/{len(chunk_list)} chunks. Progress saved to checkpoint.")
                try:
                    await self._persist_graph(force=True)
                except Exception as persist_err:
                    logger.error(f"Failed to persist partial graph: {persist_err}")
            logger.exception(f"Error building graph: {e}")
            return False
        finally:
            logger.info("Constructing graph finished")

    # ------------------------------------------------------------------
    # Two-step helpers: tuple-based graph building (KG-level)
    # ------------------------------------------------------------------

    async def _build_graph_from_tuples(self, entities, triples, chunk_key):
        """
        Build graph nodes/edges from NER entities (strings) and OpenIE triples ([src, rel, tgt]).
        This is the KG-level path: entity name + relation name + weight only.
        """
        maybe_nodes = defaultdict(list)
        maybe_edges = defaultdict(list)

        for _entity in entities:
            entity_name = clean_str(_entity)
            valid_entity_name, invalid_reason = classify_entity_name(entity_name)
            if not valid_entity_name:
                logger.warning(
                    "Skipping invalid tuple entity. chunk_key=%s raw_entity=%r cleaned_entity=%r reason=%s",
                    chunk_key,
                    _entity,
                    entity_name,
                    invalid_reason,
                )
                continue

            entity = Entity(
                entity_name=entity_name,
                entity_type='',
                source_id=chunk_key,
            )
            maybe_nodes[entity_name].append(entity)

        for triple in triples:
            if isinstance(triple, list) and len(triple) > 0 and isinstance(triple[0], list):
                triple = triple[0]

            if len(triple) != 3:
                logger.warning(f"Triple length is not 3, triple is: {triple}, skipping.")
                continue

            src_entity = clean_str(triple[0])
            tgt_entity = clean_str(triple[2])
            relation_name = clean_str(triple[1])

            valid_src_entity, src_reason = classify_entity_name(src_entity)
            valid_tgt_entity, tgt_reason = classify_entity_name(tgt_entity)
            if not valid_src_entity or not valid_tgt_entity or relation_name == '':
                logger.warning(
                    "Skipping invalid triple. chunk_key=%s triple=%r src_entity=%r src_reason=%s tgt_entity=%r tgt_reason=%s relation_name=%r",
                    chunk_key,
                    triple,
                    src_entity,
                    src_reason,
                    tgt_entity,
                    tgt_reason,
                    relation_name,
                )
                continue

            relationship = Relationship(
                src_id=src_entity,
                tgt_id=tgt_entity,
                weight=1.0,
                source_id=chunk_key,
                relation_name=relation_name,
            )
            maybe_edges[(relationship.src_id, relationship.tgt_id)].append(relationship)

        return dict(maybe_nodes), dict(maybe_edges)
