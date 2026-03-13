"""Advice rendering boundary for provider-facing text."""

from __future__ import annotations

from .models import AdviceSnapshot


class AdviceRenderer:
    """Convert typed directives into a compact provider-facing string."""

    def render(self, snapshot: AdviceSnapshot) -> str | None:
        directives = sorted(snapshot.directives, key=lambda item: item.priority)
        if not directives:
            return None

        lines = ["[NEURALSYM ADVICE]"]
        for directive in directives:
            if directive.kind == "read_strategy":
                if directive.strategy == "narrow_first":
                    lines.append("- Prefer narrow reads before broader scans.")
                else:
                    lines.append("- Prefer broad reads before narrowing scope.")
            elif directive.kind == "edit_scope":
                if directive.mode == "minimal":
                    lines.append("- Prefer minimal edits over broad changes.")
                else:
                    lines.append("- Multi-file edits are acceptable when required.")
            elif directive.kind == "boundary_rule":
                if directive.rule == "preserve_soc":
                    lines.append("- Preserve separation of concerns across modules.")
                else:
                    lines.append("- Cross-boundary changes are acceptable when necessary.")
            elif directive.kind == "explicit_user_override":
                if directive.override_kind == "avoid_tool" and directive.target_tool_name:
                    lines.append(f"- The operator rejected `{directive.target_tool_name}` for this turn.")
                elif directive.override_kind == "prefer_narrow_reads":
                    lines.append("- The operator prefers narrower reads for this turn.")
                elif directive.override_kind == "preserve_boundaries":
                    lines.append("- The operator wants boundaries preserved for this turn.")

        if len(lines) == 1:
            return None
        return "\n".join(lines)
