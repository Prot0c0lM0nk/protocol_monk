#!/usr/bin/env python3
"""Analyze session transcripts for common event-loop anomalies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_records(session_path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line in session_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _extract_field(record: Dict[str, Any], key: str) -> Any:
    correlation = record.get("correlation")
    if isinstance(correlation, dict) and key in correlation:
        return correlation.get(key)

    payload = record.get("payload")
    if isinstance(payload, dict):
        if key in payload:
            return payload.get(key)
        if key == "turn_id" and payload.get("request_id"):
            return payload.get("request_id")
    return None


def analyze_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    anomalies: List[Dict[str, Any]] = []
    user_turns: Dict[str, int] = {}
    responses_by_turn: Dict[str, int] = {}
    anonymous_user_turns = 0
    anonymous_responses = 0
    lifecycle: Dict[Tuple[str, str, str], Dict[str, bool]] = {}

    for index, record in enumerate(records):
        event_type = record.get("event_type")
        payload = record.get("payload")
        payload_dict = payload if isinstance(payload, dict) else {}
        turn_id = str(_extract_field(record, "turn_id") or "").strip()
        pass_id = str(_extract_field(record, "pass_id") or "").strip()
        tool_call_id = str(_extract_field(record, "tool_call_id") or "").strip()

        if event_type == "user_input_submitted":
            if turn_id:
                user_turns[turn_id] = user_turns.get(turn_id, 0) + 1
            else:
                anonymous_user_turns += 1

        elif event_type == "response_complete":
            if turn_id:
                responses_by_turn[turn_id] = responses_by_turn.get(turn_id, 0) + 1
            else:
                anonymous_responses += 1

            tool_calls = payload_dict.get("tool_calls") or []
            seen_ids = set()
            for raw_tool_call in tool_calls:
                if not isinstance(raw_tool_call, dict):
                    continue
                tool_name = str(raw_tool_call.get("name") or "").strip()
                if not tool_name:
                    anomalies.append(
                        {
                            "type": "malformed_tool_call_missing_name",
                            "index": index,
                            "turn_id": turn_id or None,
                            "pass_id": pass_id or payload_dict.get("pass_id"),
                            "tool_call_id": raw_tool_call.get("id")
                            or raw_tool_call.get("call_id"),
                            "metadata": raw_tool_call.get("metadata"),
                        }
                    )
                call_id = (
                    str(raw_tool_call.get("id") or raw_tool_call.get("call_id") or "")
                    .strip()
                )
                if not call_id:
                    continue
                if call_id in seen_ids:
                    anomalies.append(
                        {
                            "type": "duplicate_tool_ids_in_pass",
                            "index": index,
                            "turn_id": turn_id or None,
                            "pass_id": pass_id or payload_dict.get("pass_id"),
                            "tool_call_id": call_id,
                        }
                    )
                seen_ids.add(call_id)

            content = str(payload_dict.get("content") or "").strip()
            has_tool_calls = bool(tool_calls)
            if not content and not has_tool_calls:
                anomalies.append(
                    {
                        "type": "empty_final_pass",
                        "index": index,
                        "turn_id": turn_id or None,
                        "pass_id": pass_id or payload_dict.get("pass_id"),
                    }
                )

        elif event_type == "stream_chunk":
            if not pass_id:
                anomalies.append(
                    {
                        "type": "stream_chunk_missing_pass_id",
                        "index": index,
                        "turn_id": turn_id or None,
                    }
                )

        elif event_type in {
            "tool_execution_start",
            "tool_result",
            "tool_execution_complete",
        }:
            if not tool_call_id:
                anomalies.append(
                    {
                        "type": "tool_lifecycle_missing_tool_call_id",
                        "index": index,
                        "event_type": event_type,
                    }
                )
                continue

            lifecycle_key = (turn_id or "", pass_id or "", tool_call_id)
            state = lifecycle.setdefault(
                lifecycle_key, {"start": False, "result": False, "complete": False}
            )
            if event_type == "tool_execution_start":
                state["start"] = True
            elif event_type == "tool_result":
                state["result"] = True
            elif event_type == "tool_execution_complete":
                state["complete"] = True

    for turn_id, count in user_turns.items():
        response_count = responses_by_turn.get(turn_id, 0)
        if response_count < count:
            anomalies.append(
                {
                    "type": "user_turn_without_response_complete",
                    "turn_id": turn_id,
                    "missing_count": count - response_count,
                }
            )

    if anonymous_user_turns > anonymous_responses:
        anomalies.append(
            {
                "type": "anonymous_turn_count_mismatch",
                "missing_count": anonymous_user_turns - anonymous_responses,
            }
        )

    for (turn_id, pass_id, tool_call_id), state in lifecycle.items():
        if state["start"] and not state["result"]:
            anomalies.append(
                {
                    "type": "tool_lifecycle_missing_result",
                    "turn_id": turn_id or None,
                    "pass_id": pass_id or None,
                    "tool_call_id": tool_call_id,
                }
            )
        if state["start"] and not state["complete"]:
            anomalies.append(
                {
                    "type": "tool_lifecycle_missing_complete",
                    "turn_id": turn_id or None,
                    "pass_id": pass_id or None,
                    "tool_call_id": tool_call_id,
                }
            )
        if (state["result"] or state["complete"]) and not state["start"]:
            anomalies.append(
                {
                    "type": "tool_lifecycle_missing_start",
                    "turn_id": turn_id or None,
                    "pass_id": pass_id or None,
                    "tool_call_id": tool_call_id,
                }
            )

    return {
        "record_count": len(records),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }


def _resolve_session_path(
    *,
    session: str | None,
    workspace: str | None,
    latest: bool,
) -> Path:
    if session:
        return Path(session).expanduser().resolve()

    workspace_root = Path(workspace or Path.cwd()).expanduser().resolve()
    sessions_dir = workspace_root / ".protocol_monk" / "sessions"
    if not sessions_dir.exists():
        raise FileNotFoundError(f"Session directory not found: {sessions_dir}")

    candidates = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No session files found in {sessions_dir}")

    if latest or not session:
        return candidates[0]
    return candidates[0]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latest", action="store_true", help="Analyze latest session file")
    parser.add_argument("--session", type=str, help="Path to a specific session JSONL file")
    parser.add_argument(
        "--workspace",
        type=str,
        help="Workspace root containing .protocol_monk/sessions",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    session_path = _resolve_session_path(
        session=args.session,
        workspace=args.workspace,
        latest=args.latest,
    )
    records = _load_records(session_path)
    result = analyze_records(records)
    result["session"] = str(session_path)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Session: {session_path}")
        print(f"Records: {result['record_count']}")
        print(f"Anomalies: {result['anomaly_count']}")
        for anomaly in result["anomalies"]:
            print(f"- {anomaly['type']}: {json.dumps(anomaly, ensure_ascii=False)}")

    return 0 if result["anomaly_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
