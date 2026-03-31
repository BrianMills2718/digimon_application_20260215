"""
Shared mixin for ENTITY_EXTRACTION-based (delimiter-delimited) entity/relationship parsing.

Used by both ERGraph (extract_two_step=False) and RKGraph to avoid code duplication.
The extraction calls the LLM with ENTITY_EXTRACTION or ENTITY_EXTRACTION_KEYWORD prompts
and parses the delimiter-separated records into Entity and Relationship objects.
"""

import json
import re
from collections import defaultdict
from typing import List, Optional, Tuple

from Config.GraphConfig import GraphConfig
from Core.Common.Logger import logger
from Core.Common.extraction_validation import (
    strip_extraction_field_markup,
    validate_entity_record,
    validate_relationship_record,
)
from Core.Common.graph_schema_guidance import (
    build_schema_guidance_text,
    resolve_entity_type_names,
    resolve_relation_type_names,
)
from Core.Common.entity_name_hygiene import build_identity_payload, classify_entity_name
from Core.Common.Utils import clean_str, split_string_by_multi_markers, is_float_regex
from Core.Common.Constants import (
    DEFAULT_RECORD_DELIMITER,
    DEFAULT_COMPLETION_DELIMITER,
    DEFAULT_TUPLE_DELIMITER,
)
from Core.Common.Memory import Memory
from Core.Prompt import GraphPrompt
from Core.Schema.ChunkSchema import TextChunk
from Core.Schema.EntityRelation import Entity, Relationship
from Core.Schema.Message import Message


class DelimiterExtractionMixin:
    """
    Mixin that provides ENTITY_EXTRACTION prompt-based extraction and
    delimiter-based record parsing for building knowledge graphs.

    Requirements on the host class:
      - self.llm            — LLM instance with .aask()
      - self.graph_config   — typed GraphConfig
                              OR self.config pointing to the same GraphConfig
    """

    # ------------------------------------------------------------------
    # Context builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context_for_entity_extraction(content: str) -> dict[str, str]:
        """Return the common delimiter/context values used by extraction prompts."""

        return dict(
            tuple_delimiter=DEFAULT_TUPLE_DELIMITER,
            record_delimiter=DEFAULT_RECORD_DELIMITER,
            completion_delimiter=DEFAULT_COMPLETION_DELIMITER,
            input_text=content,
        )

    def _graph_config(self) -> GraphConfig:
        """Return the typed graph config from the host graph builder.

        The extraction path depends on a first-class `GraphConfig` contract so
        prompt variants, manifests, and parser behavior stay aligned. This
        helper fails loudly if a host class wires an incompatible config object.
        """

        graph_cfg = getattr(self, "graph_config", getattr(self, "config", None))
        if not isinstance(graph_cfg, GraphConfig):
            raise TypeError(
                "DelimiterExtractionMixin requires a GraphConfig on self.graph_config or self.config."
            )
        return graph_cfg

    @staticmethod
    def _parse_record_attributes(record: str) -> list[str] | None:
        """Parse one delimited extraction tuple into normalized attributes.

        The delimiter-based extraction path is intentionally lightweight, but we
        still need one shared parser so the one-pass and two-pass paths apply
        the same markup stripping and tuple splitting rules.
        """

        match = re.search(r"\((.*)\)", record)
        if match is None:
            return None

        record_attributes = split_string_by_multi_markers(
            match.group(1), [DEFAULT_TUPLE_DELIMITER]
        )
        return [
            strip_extraction_field_markup(attribute)
            for attribute in record_attributes
        ]

    @staticmethod
    def _quote_extraction_value(value: str) -> str:
        """Return one extraction field quoted for a synthetic tuple record."""

        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'

    def _serialize_entity_record(self, entity: Entity) -> str:
        """Serialize one validated entity back into the delimiter tuple format.

        The two-pass proof reuses the existing graph builder, which already
        consumes raw extraction tuples. Serializing the validated first-pass
        entities avoids introducing a separate record format into the current
        build path.
        """

        tuple_delimiter = DEFAULT_TUPLE_DELIMITER
        return (
            f"({self._quote_extraction_value('entity')}"
            f"{tuple_delimiter}{self._quote_extraction_value(entity.entity_name)}"
            f"{tuple_delimiter}{self._quote_extraction_value(entity.entity_type)}"
            f"{tuple_delimiter}{self._quote_extraction_value(entity.description)})"
        )

    def _entity_inventory_text(self, entities: list[Entity]) -> str:
        """Render a compact validated entity inventory for relationship pass prompts."""

        inventory_lines = []
        for entity in entities:
            inventory_lines.append(
                f'- "{entity.entity_name}" | type="{entity.entity_type}" | '
                f'description="{entity.description}"'
            )
        return "\n".join(inventory_lines)

    async def _run_delimited_extraction_prompt(
        self,
        *,
        prompt: str,
        continue_prompt: str,
        if_loop_prompt: str,
        log_label: str,
        chunk_id: str,
    ) -> list[str]:
        """Run one delimiter-extraction prompt with the existing gleaning loop.

        Both the legacy one-pass path and the new two-pass proof use the same
        working-memory conversation pattern so any observed quality delta comes
        from prompt structure rather than orchestration drift.
        """

        graph_cfg = self._graph_config()

        working_memory = Memory()
        working_memory.add(Message(content=prompt, role="user"))
        final_result = await self.llm.aask(prompt)
        working_memory.add(Message(content=final_result, role="assistant"))

        for glean_idx in range(graph_cfg.max_gleaning):
            working_memory.add(Message(content=continue_prompt, role="user"))
            context_str = "\n".join(
                f"{msg.sent_from}: {msg.content}" for msg in working_memory.get()
            )
            glean_result = await self.llm.aask(context_str)
            working_memory.add(Message(content=glean_result, role="assistant"))
            final_result += glean_result
            logger.info(
                f"{log_label} gleaning step {glean_idx + 1} for chunk {chunk_id}: "
                f"{glean_result[:500]}..."
            )

            if glean_idx == graph_cfg.max_gleaning - 1:
                break

            working_memory.add(Message(content=if_loop_prompt, role="user"))
            context_str = "\n".join(
                f"{msg.sent_from}: {msg.content}" for msg in working_memory.get()
            )
            if_loop_result = await self.llm.aask(context_str)
            if if_loop_result.strip().strip('"').strip("'").lower() != "yes":
                break

        logger.info(
            f"{log_label} raw LLM output for chunk {chunk_id} before splitting: "
            f">>>\n{final_result}\n<<<"
        )
        working_memory.clear()

        extracted_records = split_string_by_multi_markers(
            final_result, [DEFAULT_RECORD_DELIMITER, DEFAULT_COMPLETION_DELIMITER]
        )
        logger.info(f"{log_label} split records for chunk {chunk_id}: {extracted_records}")
        return extracted_records

    async def _collect_valid_entities_from_records(
        self,
        records: list[str],
        *,
        chunk_key: str,
    ) -> list[Entity]:
        """Validate and deduplicate entity records emitted by the first extraction pass."""

        entities_by_name: dict[str, Entity] = {}
        for record in records:
            record_attributes = self._parse_record_attributes(record)
            if record_attributes is None:
                continue
            entity = await self._handle_single_entity_extraction(record_attributes, chunk_key)
            if entity is None:
                continue

            existing = entities_by_name.get(entity.entity_name)
            if existing is None or len(entity.description) > len(existing.description):
                entities_by_name[entity.entity_name] = entity

        return list(entities_by_name.values())

    # ------------------------------------------------------------------
    # LLM call + gleaning
    # ------------------------------------------------------------------

    async def _extract_records_from_chunk(self, chunk_info: TextChunk) -> List[str]:
        """
        Extract raw delimiter tuples for one chunk using the configured prompt strategy.
        """
        graph_cfg = self._graph_config()
        if graph_cfg.two_pass_extraction:
            return await self._extract_two_pass_records_from_chunk(chunk_info)
        return await self._extract_one_pass_records_from_chunk(chunk_info)

    async def _extract_one_pass_records_from_chunk(self, chunk_info: TextChunk) -> List[str]:
        """Run the legacy single-pass delimiter extraction flow."""

        graph_cfg = self._graph_config()

        context = self._build_context_for_entity_extraction(chunk_info.content)
        entity_types = resolve_entity_type_names(graph_cfg)
        relation_types = resolve_relation_type_names(graph_cfg)
        schema_guidance = build_schema_guidance_text(
            graph_config=graph_cfg,
            entity_types=entity_types,
            relation_types=relation_types,
        )
        prompt = GraphPrompt.build_entity_extraction_prompt(
            input_text=context["input_text"],
            entity_types=entity_types,
            relation_types=relation_types,
            tuple_delimiter=context["tuple_delimiter"],
            record_delimiter=context["record_delimiter"],
            completion_delimiter=context["completion_delimiter"],
            include_relation_name=graph_cfg.enable_edge_name,
            include_relation_keywords=graph_cfg.enable_edge_keywords,
            include_slot_discipline=graph_cfg.strict_extraction_slot_discipline,
            include_grounded_entity_preference=graph_cfg.prefer_grounded_named_entities,
            schema_guidance=schema_guidance,
        )
        return await self._run_delimited_extraction_prompt(
            prompt=prompt,
            continue_prompt=GraphPrompt.ENTITY_CONTINUE_EXTRACTION,
            if_loop_prompt=GraphPrompt.ENTITY_IF_LOOP_EXTRACTION,
            log_label="One-pass extraction",
            chunk_id=chunk_info.chunk_id,
        )

    async def _extract_two_pass_records_from_chunk(self, chunk_info: TextChunk) -> List[str]:
        """Run entity-only extraction first, then relationship-only extraction.

        The second pass is constrained to the validated entity inventory from
        pass one. If the first pass yields no valid entities, this method fails
        closed and returns no records instead of allowing unconstrained
        relationship tuples into the graph.
        """

        graph_cfg = self._graph_config()
        context = self._build_context_for_entity_extraction(chunk_info.content)
        entity_types = resolve_entity_type_names(graph_cfg)
        relation_types = resolve_relation_type_names(graph_cfg)
        schema_guidance = build_schema_guidance_text(
            graph_config=graph_cfg,
            entity_types=entity_types,
            relation_types=relation_types,
        )
        entity_prompt = GraphPrompt.build_entity_inventory_extraction_prompt(
            input_text=context["input_text"],
            entity_types=entity_types,
            tuple_delimiter=context["tuple_delimiter"],
            record_delimiter=context["record_delimiter"],
            completion_delimiter=context["completion_delimiter"],
            include_slot_discipline=graph_cfg.strict_extraction_slot_discipline,
            include_grounded_entity_preference=graph_cfg.prefer_grounded_named_entities,
            schema_guidance=schema_guidance,
        )
        entity_records = await self._run_delimited_extraction_prompt(
            prompt=entity_prompt,
            continue_prompt=GraphPrompt.ENTITY_CONTINUE_EXTRACTION,
            if_loop_prompt=GraphPrompt.ENTITY_IF_LOOP_EXTRACTION,
            log_label="Two-pass entity extraction",
            chunk_id=chunk_info.chunk_id,
        )
        entities = await self._collect_valid_entities_from_records(
            entity_records,
            chunk_key=chunk_info.chunk_id,
        )
        if not entities:
            logger.warning(
                f"Two-pass extraction found no valid entities for chunk {chunk_info.chunk_id}; "
                "skipping relationship pass."
            )
            return []

        relationship_prompt = GraphPrompt.build_relationship_extraction_prompt(
            input_text=context["input_text"],
            entity_inventory_text=self._entity_inventory_text(entities),
            relation_types=relation_types,
            tuple_delimiter=context["tuple_delimiter"],
            record_delimiter=context["record_delimiter"],
            completion_delimiter=context["completion_delimiter"],
            include_relation_name=graph_cfg.enable_edge_name,
            include_relation_keywords=graph_cfg.enable_edge_keywords,
        )
        relationship_records = await self._run_delimited_extraction_prompt(
            prompt=relationship_prompt,
            continue_prompt=GraphPrompt.RELATIONSHIP_CONTINUE_EXTRACTION,
            if_loop_prompt=GraphPrompt.RELATIONSHIP_IF_LOOP_EXTRACTION,
            log_label="Two-pass relationship extraction",
            chunk_id=chunk_info.chunk_id,
        )
        entity_tuple_records = [
            self._serialize_entity_record(entity)
            for entity in entities
        ]
        return entity_tuple_records + relationship_records

    # ------------------------------------------------------------------
    # Record → Entity / Relationship parsing
    # ------------------------------------------------------------------

    async def _build_graph_from_records(
        self, records: List[str], chunk_key: str
    ) -> Tuple[dict, dict]:
        maybe_nodes: dict[str, list] = defaultdict(list)
        maybe_edges: dict[tuple, list] = defaultdict(list)

        for record in records:
            logger.info(f"Processing record: '{record}'")
            record_attributes = self._parse_record_attributes(record)
            if record_attributes is None:
                continue

            logger.info(f"Record attributes after splitting: {record_attributes}")

            entity = await self._handle_single_entity_extraction(record_attributes, chunk_key)
            if entity is not None:
                logger.info(f"Extracted entity: {json.dumps(entity.as_dict, indent=2)}")
                maybe_nodes[entity.entity_name].append(entity)
                continue

            relationship = await self._handle_single_relationship_extraction(
                record_attributes, chunk_key
            )
            if relationship is not None:
                logger.info(f"Extracted relationship: {json.dumps(relationship.as_dict, indent=2)}")
                maybe_edges[(relationship.src_id, relationship.tgt_id)].append(relationship)

        entity_names = set(maybe_nodes)
        filtered_edges: dict[tuple[str, str], list] = {}
        for edge_key, relationships in maybe_edges.items():
            src_id, tgt_id = edge_key
            if src_id in entity_names and tgt_id in entity_names:
                filtered_edges[edge_key] = relationships
                continue
            for relationship in relationships:
                logger.warning(
                    "Skipping extracted relationship without entity-backed endpoints. chunk_key={} src={!r} tgt={!r} reason={}",
                    chunk_key,
                    relationship.src_id,
                    relationship.tgt_id,
                    "relationship_endpoint_missing_entity_record",
                )

        return dict(maybe_nodes), filtered_edges

    # ------------------------------------------------------------------

    async def _handle_single_entity_extraction(
        self, record_attributes: List[str], chunk_key: str
    ) -> Optional[Entity]:
        record_attributes = [
            strip_extraction_field_markup(attribute)
            for attribute in record_attributes
        ]
        if len(record_attributes) < 4 or record_attributes[0] != '"entity"':
            return None

        entity_name = clean_str(record_attributes[1])
        valid_entity_name, invalid_reason = classify_entity_name(entity_name)
        if not valid_entity_name:
            logger.warning(
                "Skipping invalid extracted entity. "
                f"chunk_key={chunk_key} raw_entity={record_attributes[1]!r} "
                f"cleaned_entity={entity_name!r} reason={invalid_reason}"
            )
            return None

        graph_cfg = self._graph_config()
        custom_ontology = graph_cfg.loaded_custom_ontology
        entity_attributes: dict = build_identity_payload(
            [record_attributes[1]],
            fallback_entity_name=entity_name,
            include_aliases=getattr(graph_cfg, "enable_entity_alias_metadata", True),
        )
        final_entity_type = clean_str(record_attributes[2])

        if custom_ontology and custom_ontology.get("entities"):
            for entity_def in custom_ontology["entities"]:
                if entity_def.get("name") == final_entity_type:
                    final_entity_type = entity_def["name"]
                    if "properties" in entity_def:
                        for prop_def in entity_def["properties"]:
                            prop_name = prop_def.get("name")
                            if prop_name in record_attributes:
                                idx = record_attributes.index(prop_name)
                                if idx + 1 < len(record_attributes):
                                    entity_attributes[prop_name] = record_attributes[idx + 1]
                    break

        is_valid_entity_record, invalid_entity_reason = validate_entity_record(
            entity_name,
            final_entity_type,
            entity_description=record_attributes[3],
            require_typed_entities=graph_cfg.enable_entity_type,
        )
        if not is_valid_entity_record:
            logger.warning(
                "Skipping invalid extracted entity record. "
                f"chunk_key={chunk_key} entity={entity_name!r} "
                f"entity_type={final_entity_type!r} reason={invalid_entity_reason}"
            )
            return None

        return Entity(
            entity_name=entity_name,
            entity_type=final_entity_type,
            description=clean_str(record_attributes[3]),
            source_id=chunk_key,
            attributes=entity_attributes,
        )

    # ------------------------------------------------------------------

    async def _handle_single_relationship_extraction(
        self, record_attributes: List[str], chunk_key: str
    ) -> Optional[Relationship]:
        record_attributes = [
            strip_extraction_field_markup(attribute)
            for attribute in record_attributes
        ]
        if len(record_attributes) < 5 or record_attributes[0] != '"relationship"':
            return None

        graph_cfg = self._graph_config()
        custom_ontology = graph_cfg.loaded_custom_ontology
        relation_attributes: dict = {}
        enable_relation_name = graph_cfg.enable_edge_name
        enable_keywords = graph_cfg.enable_edge_keywords

        relation_name = ""
        description_index = 3
        keywords_index: int | None = None
        weight_index = len(record_attributes) - 1

        if enable_relation_name:
            if len(record_attributes) < 6:
                return None
            relation_name = clean_str(record_attributes[3])
            description_index = 4
            if enable_keywords:
                if len(record_attributes) < 7:
                    return None
                keywords_index = 5
        elif enable_keywords:
            if len(record_attributes) < 6:
                return None
            keywords_index = 4

        final_relation_name = relation_name

        if custom_ontology and custom_ontology.get("relations"):
            for relation_def in custom_ontology["relations"]:
                if relation_def.get("name", "").lower() == final_relation_name.lower():
                    final_relation_name = relation_def["name"]
                    if "properties" in relation_def:
                        for prop_def in relation_def["properties"]:
                            prop_name = prop_def.get("name")
                            if prop_name in record_attributes:
                                idx = record_attributes.index(prop_name)
                                if idx + 1 < len(record_attributes):
                                    relation_attributes[prop_name] = record_attributes[idx + 1]
                    break

        src_id = clean_str(record_attributes[1])
        tgt_id = clean_str(record_attributes[2])
        is_valid_relationship_record, invalid_relationship_reason = validate_relationship_record(
            src_id,
            tgt_id,
            final_relation_name,
            require_relation_name=enable_relation_name,
        )
        if not is_valid_relationship_record:
            logger.warning(
                "Skipping invalid extracted relationship record. "
                f"chunk_key={chunk_key} src={src_id!r} tgt={tgt_id!r} "
                f"relation_name={final_relation_name!r} reason={invalid_relationship_reason}"
            )
            return None

        return Relationship(
            src_id=src_id,
            tgt_id=tgt_id,
            weight=float(record_attributes[weight_index]) if is_float_regex(record_attributes[weight_index]) else 1.0,
            description=clean_str(record_attributes[description_index]),
            source_id=chunk_key,
            keywords=" ".join(clean_str(record_attributes[keywords_index]).split()) if keywords_index is not None else "",
            relation_name=final_relation_name,
            attributes=relation_attributes,
        )
