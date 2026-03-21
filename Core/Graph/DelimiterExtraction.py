"""
Shared mixin for ENTITY_EXTRACTION-based (delimiter-delimited) entity/relationship parsing.

Used by both ERGraph (extract_two_step=False) and RKGraph to avoid code duplication.
The extraction calls the LLM with ENTITY_EXTRACTION or ENTITY_EXTRACTION_KEYWORD prompts
and parses the delimiter-separated records into Entity and Relationship objects.
"""

import json
import re
from collections import defaultdict
from typing import Any, List, Optional, Tuple

from Core.Common.Logger import logger
from Core.Common.graph_schema_guidance import (
    build_schema_guidance_text,
    resolve_entity_type_names,
    resolve_relation_type_names,
)
from Core.Common.entity_name_hygiene import classify_entity_name
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
      - self.graph_config   — graph configuration (GraphConfig or equivalent)
                              OR self.config with the relevant fields
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

    # ------------------------------------------------------------------
    # LLM call + gleaning
    # ------------------------------------------------------------------

    async def _extract_records_from_chunk(self, chunk_info: TextChunk) -> List[str]:
        """
        Call the LLM with ENTITY_EXTRACTION (or ENTITY_EXTRACTION_KEYWORD) and
        return the raw delimiter-split records list.
        """
        graph_cfg = getattr(self, "graph_config", self.config)

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
            include_relation_name=getattr(graph_cfg, "enable_edge_name", False),
            include_relation_keywords=getattr(graph_cfg, "enable_edge_keywords", False),
            schema_guidance=schema_guidance,
        )

        working_memory = Memory()
        working_memory.add(Message(content=prompt, role="user"))
        final_result = await self.llm.aask(prompt)
        working_memory.add(Message(content=final_result, role="assistant"))

        for glean_idx in range(getattr(graph_cfg, "max_gleaning", 1)):
            working_memory.add(Message(content=GraphPrompt.ENTITY_CONTINUE_EXTRACTION, role="user"))
            context_str = "\n".join(
                f"{msg.sent_from}: {msg.content}" for msg in working_memory.get()
            )
            glean_result = await self.llm.aask(context_str)
            working_memory.add(Message(content=glean_result, role="assistant"))
            final_result += glean_result
            logger.info(f"Gleaning step {glean_idx + 1}: {glean_result[:500]}...")

            if glean_idx == getattr(graph_cfg, "max_gleaning", 1) - 1:
                break

            working_memory.add(Message(content=GraphPrompt.ENTITY_IF_LOOP_EXTRACTION, role="user"))
            context_str = "\n".join(
                f"{msg.sent_from}: {msg.content}" for msg in working_memory.get()
            )
            if_loop_result = await self.llm.aask(context_str)
            if if_loop_result.strip().strip('"').strip("'").lower() != "yes":
                break

        logger.info(
            f"Raw LLM output for chunk {chunk_info.chunk_id} before splitting: >>>\n{final_result}\n<<<"
        )
        working_memory.clear()

        extracted_records = split_string_by_multi_markers(
            final_result, [DEFAULT_RECORD_DELIMITER, DEFAULT_COMPLETION_DELIMITER]
        )
        logger.info(f"Split records for chunk {chunk_info.chunk_id}: {extracted_records}")
        return extracted_records

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
            match = re.search(r"\((.*)\)", record)
            if match is None:
                continue

            record_attributes = split_string_by_multi_markers(
                match.group(1), [DEFAULT_TUPLE_DELIMITER]
            )
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

        return dict(maybe_nodes), dict(maybe_edges)

    # ------------------------------------------------------------------

    async def _handle_single_entity_extraction(
        self, record_attributes: List[str], chunk_key: str
    ) -> Optional[Entity]:
        if len(record_attributes) < 4 or record_attributes[0] != '"entity"':
            return None

        entity_name = clean_str(record_attributes[1])
        valid_entity_name, invalid_reason = classify_entity_name(entity_name)
        if not valid_entity_name:
            logger.warning(
                "Skipping invalid extracted entity. chunk_key=%s raw_entity=%r cleaned_entity=%r reason=%s",
                chunk_key,
                record_attributes[1],
                entity_name,
                invalid_reason,
            )
            return None

        graph_cfg = getattr(self, "graph_config", self.config)
        custom_ontology = getattr(graph_cfg, "loaded_custom_ontology", None)
        entity_attributes: dict = {}
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
        if len(record_attributes) < 5 or record_attributes[0] != '"relationship"':
            return None

        graph_cfg = getattr(self, "graph_config", self.config)
        custom_ontology = getattr(graph_cfg, "loaded_custom_ontology", None)
        relation_attributes: dict = {}
        enable_relation_name = getattr(graph_cfg, "enable_edge_name", False)
        enable_keywords = getattr(graph_cfg, "enable_edge_keywords", False)

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

        return Relationship(
            src_id=clean_str(record_attributes[1]),
            tgt_id=clean_str(record_attributes[2]),
            weight=float(record_attributes[weight_index]) if is_float_regex(record_attributes[weight_index]) else 1.0,
            description=clean_str(record_attributes[description_index]),
            source_id=chunk_key,
            keywords=" ".join(clean_str(record_attributes[keywords_index]).split()) if keywords_index is not None else "",
            relation_name=final_relation_name,
            attributes=relation_attributes,
        )
