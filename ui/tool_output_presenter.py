from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Optional


@dataclass(frozen=True)
class ToolOutputSection:
    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class ToolOutputView:
    tool_name: str
    success: bool
    is_structured: bool
    preview_text: str
    viewer_title: str
    viewer_label: str
    result_type: Optional[str]
    metadata_lines: tuple[str, ...]
    sections: tuple[ToolOutputSection, ...]
    raw_json_text: Optional[str]
    flattened_text: str
    output_chars: int
    output_lines: int


def build_tool_output_view(
    tool_name: str,
    output: Any,
    *,
    success: bool,
) -> ToolOutputView:
    if _is_tool_output_envelope(output):
        return _build_structured_view(tool_name, output, success=success)

    fallback_text = _render_fallback_text(output)
    preview = _truncate_preview(fallback_text)
    flattened = fallback_text
    return ToolOutputView(
        tool_name=tool_name,
        success=success,
        is_structured=False,
        preview_text=preview,
        viewer_title=f"Tool Output: {tool_name}",
        viewer_label=preview or tool_name,
        result_type=None,
        metadata_lines=(),
        sections=(),
        raw_json_text=fallback_text or None,
        flattened_text=flattened,
        output_chars=len(flattened),
        output_lines=_count_lines(flattened),
    )


def cap_tool_output_view(
    view: ToolOutputView,
    max_chars: int,
) -> tuple[ToolOutputView, bool, int]:
    if max_chars <= 0:
        return view, False, 0
    if len(view.flattened_text) <= max_chars:
        return view, False, 0

    if not view.is_structured:
        shown = view.flattened_text[:max_chars]
        omitted = len(view.flattened_text) - len(shown)
        capped = ToolOutputView(
            tool_name=view.tool_name,
            success=view.success,
            is_structured=False,
            preview_text=view.preview_text,
            viewer_title=view.viewer_title,
            viewer_label=view.viewer_label,
            result_type=view.result_type,
            metadata_lines=view.metadata_lines,
            sections=(),
            raw_json_text=shown,
            flattened_text=shown,
            output_chars=len(shown),
            output_lines=_count_lines(shown),
        )
        return capped, True, omitted

    remaining = max_chars
    summary = view.preview_text
    kept_summary, used = _cap_text_block(summary, remaining)
    remaining -= used
    block_count = 1 if kept_summary else 0

    metadata_lines = ()
    if view.metadata_lines and remaining > 0:
        metadata_title_cost = _block_title_cost("Common Metadata", has_previous_block=block_count > 0)
        remaining -= metadata_title_cost
        if remaining > 0:
            metadata_lines, used, _ = _cap_lines(view.metadata_lines, remaining)
            remaining -= used
            if metadata_lines:
                block_count += 1
        else:
            metadata_lines = ()

    kept_sections: list[ToolOutputSection] = []
    for section in view.sections:
        if remaining <= 0:
            break
        title_cost = _block_title_cost(section.title, has_previous_block=block_count > 0)
        remaining -= title_cost
        if remaining <= 0:
            break
        kept_lines, used, truncated = _cap_lines(section.lines, remaining)
        if kept_lines:
            kept_sections.append(ToolOutputSection(title=section.title, lines=kept_lines))
            remaining -= used
            block_count += 1
        if truncated:
            break

    flattened = _flatten_view_text(kept_summary, metadata_lines, kept_sections, raw_json_text=None)
    if len(flattened) > max_chars:
        flattened = flattened[:max_chars]
    omitted = len(view.flattened_text) - len(flattened)
    capped = ToolOutputView(
        tool_name=view.tool_name,
        success=view.success,
        is_structured=True,
        preview_text=kept_summary or view.preview_text,
        viewer_title=view.viewer_title,
        viewer_label=view.viewer_label,
        result_type=view.result_type,
        metadata_lines=metadata_lines,
        sections=tuple(kept_sections),
        raw_json_text=None,
        flattened_text=flattened,
        output_chars=len(flattened),
        output_lines=_count_lines(flattened),
    )
    return capped, True, max(0, omitted)


def _build_structured_view(
    tool_name: str,
    output: dict[str, Any],
    *,
    success: bool,
) -> ToolOutputView:
    summary = str(output.get("summary") or tool_name).strip() or tool_name
    result_type = str(output.get("result_type") or "").strip() or None
    data = output.get("data")
    pagination = output.get("pagination")
    metadata_lines = tuple(
        line
        for line in (
            _format_metadata_line("Schema", output.get("schema_version")),
            _format_metadata_line("Result Type", result_type),
        )
        if line
    )

    sections: list[ToolOutputSection] = []
    raw_json_text: Optional[str] = None

    if isinstance(data, dict):
        generic_lines = []
        for key, value in data.items():
            if key in {"lines", "stdout", "stderr"}:
                continue
            generic_lines.append(f"{key}: {_format_value(value)}")
        if generic_lines:
            sections.append(ToolOutputSection(title="Metadata", lines=tuple(generic_lines)))

        file_lines = _format_line_records(data.get("lines"))
        if file_lines:
            sections.append(ToolOutputSection(title="File Lines", lines=tuple(file_lines)))

        stdout_lines = _format_stream_section("stdout", data.get("stdout"))
        if stdout_lines:
            sections.append(ToolOutputSection(title="stdout", lines=tuple(stdout_lines)))

        stderr_lines = _format_stream_section("stderr", data.get("stderr"))
        if stderr_lines:
            sections.append(ToolOutputSection(title="stderr", lines=tuple(stderr_lines)))
    else:
        raw_json_text = _pretty_json(output)

    pagination_lines = _format_pagination_section(pagination)
    if pagination_lines:
        sections.append(ToolOutputSection(title="Pagination", lines=tuple(pagination_lines)))

    if not sections and raw_json_text is None and not isinstance(data, dict):
        raw_json_text = _pretty_json(output)

    flattened = _flatten_view_text(summary, metadata_lines, sections, raw_json_text)
    output_chars, output_lines = _measure_view(output, flattened, raw_json_text)
    viewer_title = f"Tool Output: {tool_name}"
    viewer_label = summary

    return ToolOutputView(
        tool_name=tool_name,
        success=success,
        is_structured=True,
        preview_text=summary,
        viewer_title=viewer_title,
        viewer_label=viewer_label,
        result_type=result_type,
        metadata_lines=metadata_lines,
        sections=tuple(sections),
        raw_json_text=raw_json_text,
        flattened_text=flattened,
        output_chars=output_chars,
        output_lines=output_lines,
    )


def _flatten_view_text(
    summary: str,
    metadata_lines: Iterable[str],
    sections: Iterable[ToolOutputSection],
    raw_json_text: Optional[str],
) -> str:
    blocks: list[str] = []
    if summary:
        blocks.append(summary)
    metadata = "\n".join(metadata_lines)
    if metadata:
        blocks.append("Common Metadata\n" + metadata)
    for section in sections:
        body = "\n".join(section.lines)
        if body:
            blocks.append(f"{section.title}\n{body}")
    if raw_json_text:
        blocks.append("Raw JSON\n" + raw_json_text)
    return "\n\n".join(blocks)


def _is_tool_output_envelope(output: Any) -> bool:
    return (
        isinstance(output, dict)
        and str(output.get("schema_version") or "") == "tool_output.v1"
        and "data" in output
    )


def _render_fallback_text(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, (dict, list, tuple)):
        return _pretty_json(output)
    return str(output)


def _pretty_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return str(value)


def _truncate_preview(text: str, limit: int = 160) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + f"... ({len(compact)} chars)"


def _format_metadata_line(label: str, value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return f"{label}: {value}"


def _format_value(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return json.dumps(value, ensure_ascii=False) if value is None else str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _format_line_records(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        number = item.get("line_number")
        text = str(item.get("text", ""))
        if number is None:
            lines.append(text)
        else:
            lines.append(f"{int(number):>4}│ {text}")
    return lines


def _format_stream_section(name: str, stream: Any) -> list[str]:
    if not isinstance(stream, dict):
        return []
    returned_lines = int(stream.get("returned_line_count", 0) or 0)
    total_lines = int(stream.get("line_count", 0) or 0)
    returned_chars = int(stream.get("returned_char_count", 0) or 0)
    total_chars = int(stream.get("char_count", 0) or 0)

    lines = [
        (
            f"Returned {returned_lines}/{total_lines} lines, "
            f"{returned_chars}/{total_chars} chars"
        )
    ]
    if bool(stream.get("truncated", False)):
        omitted = int(stream.get("omitted_char_count", 0) or 0)
        lines.append(f"Truncated: omitted {omitted} chars")
    lines.extend(_format_line_records(stream.get("lines")))
    if len(lines) == 1 and lines[0].startswith("Returned 0/0"):
        return []
    return lines


def _format_pagination_section(pagination: Any) -> list[str]:
    if not isinstance(pagination, dict) or not pagination:
        return []
    lines: list[str] = []
    mode = pagination.get("mode")
    if mode:
        lines.append(f"Mode: {mode}")

    returned_range = pagination.get("returned_range")
    total_lines = pagination.get("total_lines")
    if isinstance(returned_range, dict):
        start = returned_range.get("line_start")
        end = returned_range.get("line_end")
        if start is not None and end is not None and total_lines is not None:
            lines.append(f"Current Range: {start}-{end} of {total_lines}")

    if pagination.get("previous_page") is not None:
        lines.append(
            f"Previous Args: {_format_value(pagination.get('previous_page'))}"
        )
    if pagination.get("next_page") is not None:
        lines.append(f"Next Args: {_format_value(pagination.get('next_page'))}")
    return lines


def _measure_view(
    output: dict[str, Any],
    flattened: str,
    raw_json_text: Optional[str],
) -> tuple[int, int]:
    char_candidates = [len(flattened)]
    line_candidates = [_count_lines(flattened)]

    data = output.get("data")
    if isinstance(data, dict):
        line_records = data.get("lines")
        if isinstance(line_records, list):
            char_candidates.append(
                sum(len(str(item.get("text", ""))) for item in line_records if isinstance(item, dict))
            )
            line_candidates.append(len(line_records))

        for key in ("stdout", "stderr"):
            stream = data.get(key)
            if isinstance(stream, dict):
                char_candidates.append(int(stream.get("char_count", 0) or 0))
                line_candidates.append(int(stream.get("line_count", 0) or 0))

    if raw_json_text:
        char_candidates.append(len(raw_json_text))
    return max(char_candidates), max(line_candidates)


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def _cap_text_block(text: str, max_chars: int) -> tuple[str, int]:
    if max_chars <= 0:
        return "", 0
    shown = text[:max_chars]
    return shown, len(shown)


def _cap_lines(lines: Iterable[str], max_chars: int) -> tuple[tuple[str, ...], int, bool]:
    if max_chars <= 0:
        return (), 0, True

    kept: list[str] = []
    used = 0
    for raw_line in lines:
        line = str(raw_line)
        prefix = 1 if kept else 0
        available = max_chars - used - prefix
        if available <= 0:
            return tuple(kept), used, True
        if len(line) <= available:
            kept.append(line)
            used += prefix + len(line)
            continue
        kept.append(line[:available])
        used += prefix + available
        return tuple(kept), used, True

    return tuple(kept), used, False


def _block_title_cost(title: str, *, has_previous_block: bool) -> int:
    prefix = 2 if has_previous_block else 0
    return prefix + len(title) + 1
