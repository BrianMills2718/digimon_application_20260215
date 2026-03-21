"""Typed configuration for DIGIMON graph construction.

This model centralizes graph-build policy so build code, manifests, and agent
tools can describe the same contract. The new profile and schema fields make
entity-graph builds reproducible in terms of both attribute richness and
extraction guidance instead of inferring intent from scattered booleans alone.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field, model_validator

from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode
from Core.Utils.YamlModel import YamlModel


class GraphConfig(YamlModel):
    """Configuration surface for all DIGIMON graph builds.

    The model still supports the existing low-level toggles because the current
    builders use them directly. `graph_profile` and `schema_mode` add a higher
    level contract on top: profile selection can lock the expected graph
    richness, and schema mode controls how strongly prompts should constrain the
    extracted structure.
    """

    model_config = ConfigDict(validate_assignment=True)

    type: str = Field(
        default="er_graph",
        description="Type of graph to build, such as 'er_graph', 'rkg_graph', or 'tree_graph'.",
    )
    graph_type: str = "er_graph"

    # Build strategy
    graph_profile: GraphProfile | None = Field(
        default=None,
        description="Explicit build profile. When set for entity graphs, it locks the expected extraction richness.",
    )
    schema_mode: GraphSchemaMode = Field(
        default=GraphSchemaMode.OPEN,
        description="How strongly extraction should follow declared entity and relation types.",
    )
    schema_entity_types: list[str] = Field(
        default_factory=list,
        description="Declared entity types for guided or closed extraction modes.",
    )
    schema_relation_types: list[str] = Field(
        default_factory=list,
        description="Declared relation types for guided or closed extraction modes.",
    )
    strict_extraction_slot_discipline: bool = Field(
        default=False,
        description=(
            "Whether extraction prompts should explicitly forbid predicate phrases in "
            "entity slots and require non-placeholder entity types for typed profiles."
        ),
    )

    # Building graph
    extract_two_step: bool = False
    max_gleaning: int = 1
    force: bool = False

    # For ER graph / KG / RKG
    enable_entity_description: bool = False
    enable_entity_type: bool = False
    enable_edge_description: bool = False
    enable_edge_name: bool = False
    prior_prob: float = 0.8
    enable_edge_keywords: bool = False

    # Graph clustering
    use_community: bool = False
    graph_cluster_algorithm: str = "leiden"
    max_graph_cluster_size: int = 10
    graph_cluster_seed: int = 0xDEADBEEF
    summary_max_tokens: int = 500
    llm_model_max_token_size: int = 32768

    # For tree graph config
    build_tree_from_leaves: bool = False
    reduction_dimension: int = 5
    summarization_length: int = 100
    num_layers: int = 10
    top_k: int = 5
    threshold_cluster_num: int = 5000
    start_layer: int = 5
    graph_cluster_params: Optional[dict] = None
    selection_mode: str = "top_k"
    max_length_in_cluster: int = 3500
    threshold: float = 0.1
    cluster_metric: str = "cosine"
    verbose: bool = False
    random_seed: int = 224
    enforce_sub_communities: bool = False
    max_size_percentage: float = 0.2
    tol: float = 1e-4
    max_iter: int = 300
    size_of_clusters: int = 10

    # For custom ontology
    auto_generate_ontology: bool = False
    custom_ontology_path: Optional[str] = "Config/custom_ontology.json"
    loaded_custom_ontology: Optional[Dict[str, Any]] = None

    # Post-extraction edge enrichment
    enable_chunk_cooccurrence: bool = False

    # For graph augmentation
    similarity_threshold: float = 0.8
    similarity_top_k: int = 10
    similarity_max: float = 1.0
    string_similarity_threshold: float = 0.65
    string_similarity_min_name_length: int = 4

    @model_validator(mode="after")
    def apply_profile_contract(self) -> "GraphConfig":
        """Apply explicit profile defaults and reject topology/profile mismatches.

        Profiles are contracts, not advisory tags. If a caller sets an entity
        profile, the current extraction flags are normalized to that profile so
        the resulting manifest and build behavior stay aligned.
        """

        if self.type == "passage_graph":
            if self.graph_profile is None:
                object.__setattr__(self, "graph_profile", GraphProfile.PASSAGE)
            elif self.graph_profile is not GraphProfile.PASSAGE:
                raise ValueError("passage_graph builds must use graph_profile=PASSAGE")
            return self

        if self.type in {"tree_graph", "tree_graph_balanced"}:
            if self.graph_profile is None:
                object.__setattr__(self, "graph_profile", GraphProfile.TREE)
            elif self.graph_profile is not GraphProfile.TREE:
                raise ValueError("tree graph builds must use graph_profile=TREE")
            return self

        if self.graph_profile in {GraphProfile.PASSAGE, GraphProfile.TREE}:
            raise ValueError(
                "Entity-graph builds must not use graph_profile=PASSAGE or graph_profile=TREE"
            )

        if self.graph_profile is GraphProfile.KG:
            object.__setattr__(self, "extract_two_step", True)
            object.__setattr__(self, "enable_entity_type", False)
            object.__setattr__(self, "enable_entity_description", False)
            object.__setattr__(self, "enable_edge_name", True)
            object.__setattr__(self, "enable_edge_description", False)
            object.__setattr__(self, "enable_edge_keywords", False)
        elif self.graph_profile is GraphProfile.TKG:
            object.__setattr__(self, "extract_two_step", False)
            object.__setattr__(self, "enable_entity_type", True)
            object.__setattr__(self, "enable_entity_description", True)
            object.__setattr__(self, "enable_edge_name", True)
            object.__setattr__(self, "enable_edge_description", True)
            object.__setattr__(self, "enable_edge_keywords", False)
        elif self.graph_profile is GraphProfile.RKG:
            object.__setattr__(self, "extract_two_step", False)
            object.__setattr__(self, "enable_entity_type", True)
            object.__setattr__(self, "enable_entity_description", True)
            object.__setattr__(self, "enable_edge_name", True)
            object.__setattr__(self, "enable_edge_description", True)
            object.__setattr__(self, "enable_edge_keywords", True)

        return self
