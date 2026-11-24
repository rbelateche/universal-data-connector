"""Data models for field mappings and mapping results."""

from dataclasses import dataclass, field

# Mappings proposed below this confidence need a human decision.
REVIEW_THRESHOLD = 0.7

# Review lifecycle of one field mapping:
#   proposed  — as inferred by the LLM, untouched by a human
#   accepted  — a human confirmed the proposal
#   rejected  — a human discarded it (the source column is not mapped)
#   edited    — a human changed the target and/or transform
MAPPING_STATUSES: tuple[str, ...] = ("proposed", "accepted", "rejected", "edited")


@dataclass
class FieldMapping:
    """Describes how one source column maps to one target column."""

    source_col: str
    target_col: str
    # One of the transforms in udc.mapper.prompt.ALLOWED_TRANSFORMS
    transform: str
    confidence: float  # 0.0 – 1.0; below REVIEW_THRESHOLD flagged for human review
    reasoning: str  # Claude's explanation, persisted for audit trail
    # For map_values: {"Y": True, "N": False}
    value_map: dict[str, object] = field(default_factory=dict)
    status: str = "proposed"  # one of MAPPING_STATUSES


@dataclass
class MappingResult:
    """Full result of a schema mapping inference run."""

    source_id: str
    target_schema_name: str
    mappings: list[FieldMapping]
    unmapped_source: list[str]  # source cols Claude couldn't map
    unmapped_target: list[str]  # target cols that have no source

    @property
    def low_confidence(self) -> list[FieldMapping]:
        """Fields with confidence below REVIEW_THRESHOLD — flagged for human review."""
        return [m for m in self.mappings if m.confidence < REVIEW_THRESHOLD]

    @property
    def needs_review(self) -> bool:
        return bool(self.low_confidence or self.unmapped_target)
