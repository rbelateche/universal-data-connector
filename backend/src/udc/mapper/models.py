"""Data models for field mappings and mapping results."""

from dataclasses import dataclass, field


@dataclass
class FieldMapping:
    """Describes how one source column maps to one target column."""

    source_col: str
    target_col: str
    # One of: rename | cast_int | cast_float | cast_bool | parse_date | map_values | drop
    transform: str
    confidence: float  # 0.0 – 1.0; below 0.7 flagged for human review
    reasoning: str  # Claude's explanation, persisted for audit trail
    # For map_values: {"Y": True, "N": False}
    value_map: dict[str, object] = field(default_factory=dict)


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
        """Fields with confidence < 0.7 — flagged for human review."""
        return [m for m in self.mappings if m.confidence < 0.7]

    @property
    def needs_review(self) -> bool:
        return bool(self.low_confidence or self.unmapped_target)
