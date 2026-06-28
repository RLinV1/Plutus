"""Shared agent result type."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentResult:
    """Outcome of one agent run.

    answer:     the final natural-language response.
    tool_calls: ordered [{name, input, output}] for every tool the agent used —
                consumed by the eval harness to check tool selection.
    """

    answer: str
    tool_calls: list[dict] = field(default_factory=list)

    def tool_names(self) -> list[str]:
        return [c["name"] for c in self.tool_calls]
