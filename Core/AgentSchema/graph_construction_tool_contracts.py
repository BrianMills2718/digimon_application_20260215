"""
Pydantic contracts for agent tools that construct various types of knowledge graphs.
Each tool has an input and output schema, with config overrides for graph-specific parameters.
"""
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, Field

from Core.Schema.GraphBuildTypes import GraphProfile, GraphSchemaMode

# =========================
# Base Output Schema
# =========================
class BaseGraphBuildOutputs(BaseModel):
    """Common output fields for all graph build tools."""

    graph_id: str = Field(description="Unique identifier for the built graph artifact. This ID will be used by retrieval tools and other graph operations.")
    status: str = Field(description="Status of the build operation, e.g., 'success', 'failure'.")
    message: str = Field(description="A descriptive message about the outcome of the build operation, including any errors.")
    node_count: Optional[int] = Field(default=None, description="Number of nodes in the built graph.")
    edge_count: Optional[int] = Field(default=None, description="Number of edges in the built graph (if applicable).")
    layer_count: Optional[int] = Field(default=None, description="Number of layers in the built graph (for tree graphs).")
    artifact_path: Optional[str] = Field(default=None, description="Path to the primary persisted graph artifact.")
    source_dataset_name: Optional[str] = Field(
        default=None,
        description="Dataset whose prepared corpus supplied the input chunks.",
    )
    artifact_dataset_name: Optional[str] = Field(
        default=None,
        description="Dataset namespace under which build artifacts were persisted.",
    )
    graph_instance: Optional[Any] = Field(default=None, description="The actual populated graph instance.", exclude=True)
    
    class Config:
        arbitrary_types_allowed = True  # Allow non-pydantic types like graph instances

# =========================
# ERGraph
# =========================
class ERGraphConfigOverrides(BaseModel):
    """Config overrides specific to entity-relationship graph builds."""

    graph_profile: Optional[GraphProfile] = Field(
        default=None,
        validation_alias=AliasChoices("graph_profile", "profile"),
        description="Explicit entity-graph profile such as KG, TKG, or RKG.",
    )
    schema_mode: Optional[GraphSchemaMode] = Field(
        default=None,
        validation_alias=AliasChoices("schema_mode", "extraction_schema_mode"),
        description="Schema guidance mode: open, guided, or closed.",
    )
    schema_entity_types: Optional[list[str]] = Field(
        default=None,
        validation_alias=AliasChoices("schema_entity_types", "guided_entity_types", "allowed_entity_types"),
        description="Entity types to use for guided or closed extraction.",
    )
    schema_relation_types: Optional[list[str]] = Field(
        default=None,
        validation_alias=AliasChoices("schema_relation_types", "guided_relation_types", "allowed_relation_types"),
        description="Relation types to use for guided or closed extraction.",
    )
    extract_two_step: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices('extract_two_step', 'two_step_extraction', 'extraction_strategy', 'extraction_mode'),
        description="Override default for two-step entity/relation extraction."
    )
    enable_entity_description: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices('enable_entity_description', 'include_entity_descriptions', 'entity_descriptions'),
        description="Override for enabling entity descriptions."
    )
    enable_entity_type: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices('enable_entity_type', 'include_entity_types', 'entity_types'),
        description="Override for enabling entity types."
    )
    enable_edge_description: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices('enable_edge_description', 'include_edge_descriptions', 'edge_descriptions'),
        description="Override for enabling edge descriptions."
    )
    enable_edge_name: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices('enable_edge_name', 'include_edge_names', 'edge_names'),
        description="Override for enabling edge names."
    )
    max_gleaning: Optional[int] = Field(
        default=None,
        description="Number of gleaning iterations (1=off, 2-3 recommended). Extra passes extract missed entities."
    )
    enable_chunk_cooccurrence: Optional[bool] = Field(
        default=None,
        validation_alias=AliasChoices('enable_chunk_cooccurrence', 'chunk_cooccurrence', 'cooccurrence_edges'),
        description="Add implicit edges between entities that co-occur in the same source chunk."
    )
    custom_ontology_path_override: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices('custom_ontology_path_override', 'custom_ontology_path', 'ontology_path'),
        description="Path to a custom ontology JSON file to use for this build."
    )

    class Config:
        populate_by_name = True  # Allows use of alias as field name

class BuildERGraphInputs(BaseModel):
    """Inputs for the ER graph build tool."""

    target_dataset_name: str = Field(description="Name of the dataset for input chunks and namespacing artifacts.")
    artifact_dataset_name: Optional[str] = Field(
        default=None,
        description="Optional artifact namespace. Defaults to target_dataset_name when omitted.",
    )
    force_rebuild: bool = Field(default=False, description="If True, forces a rebuild even if artifacts exist.")
    chunk_limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional cap on how many prepared chunks to include in this graph build.",
    )
    config_overrides: Optional[ERGraphConfigOverrides] = Field(default=None, description="Specific configuration overrides for ERGraph building.")

class BuildERGraphOutputs(BaseGraphBuildOutputs):
    """Outputs for the ER graph build tool."""

# =========================
# RKGraph
# =========================
class RKGraphConfigOverrides(BaseModel):
    """Config overrides specific to rich-keyword graph builds."""

    graph_profile: Optional[GraphProfile] = Field(
        default=None,
        description="Explicit entity-graph profile such as TKG or RKG.",
    )
    schema_mode: Optional[GraphSchemaMode] = Field(
        default=None,
        description="Schema guidance mode: open, guided, or closed.",
    )
    schema_entity_types: Optional[list[str]] = Field(
        default=None,
        description="Entity types to use for guided or closed extraction.",
    )
    schema_relation_types: Optional[list[str]] = Field(
        default=None,
        description="Relation types to use for guided or closed extraction.",
    )
    enable_edge_keywords: Optional[bool] = Field(default=None, description="Selects between ENTITY_EXTRACTION and ENTITY_EXTRACTION_KEYWORD prompts.")
    max_gleaning: Optional[int] = Field(default=None, description="Maximum number of gleaning iterations or items.")
    enable_chunk_cooccurrence: Optional[bool] = Field(default=None, description="Add implicit edges between entities that co-occur in the same source chunk.")
    custom_ontology_path_override: Optional[str] = Field(default=None, description="Path to a custom ontology JSON file to use for this build.")
    enable_entity_description: Optional[bool] = Field(default=None, description="Override for enabling entity descriptions (if applicable).")

class BuildRKGraphInputs(BaseModel):
    """Inputs for the RK graph build tool."""

    target_dataset_name: str = Field(description="Name of the dataset for input chunks and namespacing artifacts.")
    force_rebuild: bool = Field(default=False, description="If True, forces a rebuild even if artifacts exist.")
    config_overrides: Optional[RKGraphConfigOverrides] = Field(default=None, description="Specific configuration overrides for RKGraph building.")

class BuildRKGraphOutputs(BaseGraphBuildOutputs):
    """Outputs for the RK graph build tool."""

# =========================
# TreeGraph
# =========================
class TreeGraphConfigOverrides(BaseModel):
    """Config overrides specific to hierarchical tree graph builds."""

    build_tree_from_leaves: Optional[bool] = Field(default=None, description="If True, build tree from leaves upward.")
    num_layers: Optional[int] = Field(default=None, description="Number of layers in the tree.")
    reduction_dimension: Optional[int] = Field(default=None, description="UMAP reduction dimension.")
    threshold: Optional[float] = Field(default=None, description="GMM clustering threshold.")
    summarization_length: Optional[int] = Field(default=None, description="Max tokens for LLM summary.")
    max_length_in_cluster: Optional[int] = Field(default=None, description="Max items per cluster for recursive clustering.")
    cluster_metric: Optional[str] = Field(default=None, description="Clustering metric, e.g., 'cosine'.")
    random_seed: Optional[int] = Field(default=None, description="Random seed for reproducibility.")

class BuildTreeGraphInputs(BaseModel):
    """Inputs for the tree graph build tool."""

    target_dataset_name: str = Field(description="Name of the dataset for input chunks and namespacing artifacts.")
    force_rebuild: bool = Field(default=False, description="If True, forces a rebuild even if artifacts exist.")
    config_overrides: Optional[TreeGraphConfigOverrides] = Field(default=None, description="Specific configuration overrides for TreeGraph building.")

class BuildTreeGraphOutputs(BaseGraphBuildOutputs):
    """Outputs for the tree graph build tool."""

# =========================
# TreeGraphBalanced
# =========================
class TreeGraphBalancedConfigOverrides(BaseModel):
    """Config overrides specific to balanced tree graph builds."""

    build_tree_from_leaves: Optional[bool] = Field(default=None, description="If True, build tree from leaves upward.")
    num_layers: Optional[int] = Field(default=None, description="Number of layers in the tree.")
    summarization_length: Optional[int] = Field(default=None, description="Max tokens for LLM summary.")
    size_of_clusters: Optional[int] = Field(default=None, description="Target items per cluster for balanced K-Means.")
    max_size_percentage: Optional[float] = Field(default=None, description="Allowed deviation for cluster balancing.")
    max_iter: Optional[int] = Field(default=None, description="K-Means max iterations.")
    tol: Optional[float] = Field(default=None, description="K-Means tolerance.")
    random_seed: Optional[int] = Field(default=None, description="Random seed for reproducibility.")

class BuildTreeGraphBalancedInputs(BaseModel):
    """Inputs for the balanced tree graph build tool."""

    target_dataset_name: str = Field(description="Name of the dataset for input chunks and namespacing artifacts.")
    force_rebuild: bool = Field(default=False, description="If True, forces a rebuild even if artifacts exist.")
    config_overrides: Optional[TreeGraphBalancedConfigOverrides] = Field(default=None, description="Specific configuration overrides for TreeGraphBalanced building.")

class BuildTreeGraphBalancedOutputs(BaseGraphBuildOutputs):
    """Outputs for the balanced tree graph build tool."""

# =========================
# PassageGraph
# =========================
class PassageGraphConfigOverrides(BaseModel):
    """Config overrides specific to passage graph builds."""

    prior_prob: Optional[float] = Field(default=None, description="Threshold for WAT entity annotations.")
    custom_ontology_path_override: Optional[str] = Field(default=None, description="Path to a custom ontology JSON file to use for this build.")

class BuildPassageGraphInputs(BaseModel):
    """Inputs for the passage graph build tool."""

    target_dataset_name: str = Field(description="Name of the dataset for input chunks and namespacing artifacts.")
    force_rebuild: bool = Field(default=False, description="If True, forces a rebuild even if artifacts exist.")
    config_overrides: Optional[PassageGraphConfigOverrides] = Field(default=None, description="Specific configuration overrides for PassageGraph building.")

class BuildPassageGraphOutputs(BaseGraphBuildOutputs):
    """Outputs for the passage graph build tool."""
