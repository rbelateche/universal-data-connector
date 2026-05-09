"""SchemaMapper — calls Claude to infer field mappings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import anthropic
from anthropic.types.tool_choice_any_param import ToolChoiceAnyParam

if TYPE_CHECKING:
    from anthropic.types import ToolParam

    from udc.core.sampler import ColumnStats
from udc.mapper.models import FieldMapping, MappingResult
from udc.mapper.prompt import MAPPING_TOOL, SYSTEM_PROMPT, build_user_message

_DEFAULT_MODEL = "claude-3-5-haiku-20241022"


class SchemaMapper:
    """
    Infers how source columns map to a target canonical schema using Claude.

    Usage::

        mapper = SchemaMapper(api_key="sk-ant-...")
        result = mapper.infer(
            stats=sampler_output,
            target_schema={"customer_id": "INTEGER", "full_name": "TEXT", ...},
            source_id="pg-crm",
            target_schema_name="Contact",
        )
        for fm in result.mappings:
            print(fm.source_col, "→", fm.target_col, f"({fm.confidence:.0%})")
    """

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        # Accept an injected client for testing (avoids real API calls)
        self._client = client or anthropic.Anthropic(api_key=api_key)
        self._model = model

    def infer(
        self,
        stats: dict[str, ColumnStats],
        target_schema: dict[str, str],
        source_id: str,
        target_schema_name: str,
    ) -> MappingResult:
        """Call Claude and return a MappingResult."""
        user_msg = build_user_message(stats, target_schema, source_id, target_schema_name)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[cast("ToolParam", MAPPING_TOOL)],
            tool_choice=ToolChoiceAnyParam(type="any"),
            messages=[{"role": "user", "content": user_msg}],
        )

        tool_input = self._extract_tool_input(response)
        return self._parse_result(tool_input, source_id, target_schema_name)

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _extract_tool_input(response: anthropic.types.Message) -> dict[str, Any]:
        """Pull the tool_use block out of Claude's response."""
        for block in response.content:
            if block.type == "tool_use":
                return dict(block.input)
        raise ValueError("Claude did not call the submit_mapping tool.")

    @staticmethod
    def _parse_result(
        raw: dict[str, Any],
        source_id: str,
        target_schema_name: str,
    ) -> MappingResult:
        mappings = [
            FieldMapping(
                source_col=m["source_col"],
                target_col=m["target_col"],
                transform=m["transform"],
                confidence=float(m["confidence"]),
                reasoning=m["reasoning"],
                value_map=m.get("value_map") or {},
            )
            for m in raw.get("mappings", [])
        ]
        return MappingResult(
            source_id=source_id,
            target_schema_name=target_schema_name,
            mappings=mappings,
            unmapped_source=raw.get("unmapped_source", []),
            unmapped_target=raw.get("unmapped_target", []),
        )
