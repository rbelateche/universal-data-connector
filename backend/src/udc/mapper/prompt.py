"""Prompt builder for the schema inference Claude call."""

import json

from udc.core.sampler import ColumnStats

# The fixed vocabulary of transforms Claude is allowed to choose from.
# transform.py implements exactly these — Claude never executes code directly.
ALLOWED_TRANSFORMS = [
    "rename",  # just rename, same type
    "cast_int",  # coerce value to int
    "cast_float",  # coerce value to float
    "cast_bool",  # coerce value to bool
    "parse_date",  # parse ISO / common date strings to datetime
    "map_values",  # replace specific string values (e.g. "Y"→True)
    "drop",  # source col exists but should not appear in target
]

SYSTEM_PROMPT = """\
You are a data engineering assistant. Your job is to map columns from a source \
dataset to a target canonical schema.

For each source column you MUST decide:
1. Which target column it maps to (or "drop" if it has no place in the target).
2. Which transform is needed from this fixed list: {transforms}.
3. A confidence score 0.0–1.0 (1.0 = certain, <0.7 = needs human review).
4. A one-sentence reasoning explaining your decision.

For map_values transforms, include a "value_map" dict mapping source string \
values to their target values (e.g. {{"Y": true, "N": false}}).

Rules:
- Every target column must appear in exactly one mapping (or in unmapped_target).
- A source column mapped with "drop" must NOT appear in unmapped_source.
- Confidence < 0.7 means you are unsure — prefer lower scores over wrong mappings.
- Be conservative: if you cannot find a good match, put the target col in \
unmapped_target rather than forcing a low-quality mapping.
""".format(transforms=", ".join(ALLOWED_TRANSFORMS))


def build_user_message(
    stats: dict[str, ColumnStats],
    target_schema: dict[str, str],
    source_id: str,
    target_schema_name: str,
) -> str:
    """Compose the user turn sent to Claude."""
    source_summary = {
        col: {
            "inferred_type": s.inferred_type,
            "null_pct": round(s.null_pct, 3),
            "distinct_count": s.distinct_count,
            "sample_values": s.sample_values[:5],
            "min": s.min_value,
            "max": s.max_value,
        }
        for col, s in stats.items()
    }

    return json.dumps(
        {
            "source_id": source_id,
            "target_schema_name": target_schema_name,
            "source_columns": source_summary,
            "target_schema": target_schema,
        },
        default=str,
        indent=2,
    )


# JSON schema passed to Claude as a tool definition (forces structured output).
MAPPING_TOOL = {
    "name": "submit_mapping",
    "description": "Submit the complete field mapping result.",
    "input_schema": {
        "type": "object",
        "required": ["mappings", "unmapped_source", "unmapped_target"],
        "properties": {
            "mappings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "source_col",
                        "target_col",
                        "transform",
                        "confidence",
                        "reasoning",
                    ],
                    "properties": {
                        "source_col": {"type": "string"},
                        "target_col": {"type": "string"},
                        "transform": {
                            "type": "string",
                            "enum": ALLOWED_TRANSFORMS,
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "reasoning": {"type": "string"},
                        "value_map": {
                            "type": "object",
                            "additionalProperties": {},
                        },
                    },
                },
            },
            "unmapped_source": {
                "type": "array",
                "items": {"type": "string"},
            },
            "unmapped_target": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
}
