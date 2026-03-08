import logging
import asyncio
import json
import os
import time
import uuid
from typing import Any, Dict, List, Tuple

from protocol_monk.agent.context import logic as context_logic
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.protocol.command_dispatcher import (
    COMPACT_PROMPT_TEMPLATE_FILENAME,
    load_prompt_template,
    parse_slash_command,
)
from protocol_monk.agent.structs import (
    AgentResponse,
    UserRequest,
    AgentStatus,
    ConfirmationResponse,
    ToolResult,
    ToolRequest,
    Message,
    ContextStats,
)
from protocol_monk.agent.context.coordinator import ContextCoordinator
from protocol_monk.agent.core.state_machine import StateMachine, AgentState
from protocol_monk.tools.registry import ToolRegistry
from protocol_monk.config.settings import Settings
from protocol_monk.agent.usage_ledger import (
    UsageLedger,
    build_request_payload_for_provider,
)
from protocol_monk.skill_runtime import SkillRuntime

# [NEW] Import Execution components
from protocol_monk.agent.core.execution import ToolExecutor
from protocol_monk.agent.loops import run_thinking_loop, run_action_loop


class AgentService:
    """
    The Main Agent Loop.

    Responsibility:
    1. Listen for USER_INPUT.
    2. Manage Agent State (Idle -> Thinking -> Acting).
    3. Update Context (via Coordinator).
    4. Call LLM (Thinking Loop).
    5. Execute Tools (Action Loop).
    """

    def __init__(
        self,
        bus: EventBus,
        coordinator: ContextCoordinator,
        registry: ToolRegistry,
        provider: Any,
        settings: Settings,
        skill_runtime: SkillRuntime | None = None,
    ):
        self._bus = bus
        self._context = coordinator
        self._registry = registry
        self._provider = provider
        self._settings = settings
        self._state = StateMachine()
        self._logger = logging.getLogger("AgentService")

        # [FIX] Initialize the Executor (The Hands)
        self._executor = ToolExecutor(timeout_seconds=settings.tool_timeout)

        # Track pending confirmation futures by tool_call_id.
        self._pending_confirmations: Dict[str, asyncio.Future] = {}
        self._auto_confirm = bool(getattr(settings, "auto_confirm", False))
        self._request_lock = asyncio.Lock()
        self._skill_runtime = skill_runtime
        self._usage_ledger = UsageLedger(
            model_name=str(getattr(settings, "active_model_name", "") or "")
        )

    async def start(self) -> None:
        """
        Bootstraps the agent listeners.
        """
        await self._bus.subscribe(
            EventTypes.USER_INPUT_SUBMITTED, self._handle_user_input
        )
        await self._bus.subscribe(
            EventTypes.TOOL_CONFIRMATION_SUBMITTED, self._handle_tool_confirmation
        )
        await self._bus.subscribe(
            EventTypes.SYSTEM_COMMAND_ISSUED, self._handle_system_command
        )
        self._logger.info("Agent Service started and listening.")

    def _assistant_tool_call_payload(self, req: ToolRequest) -> Dict[str, Any]:
        return {
            "id": req.call_id,
            "type": "function",
            "function": {
                "name": req.name,
                "arguments": req.parameters,
            },
        }

    async def _emit_skill_runtime_warnings(
        self,
        warnings: List[str],
        *,
        turn_id: str | None = None,
        round_index: int | None = None,
    ) -> None:
        for warning in warnings:
            payload: Dict[str, Any] = {
                "message": "Skill runtime warning",
                "details": warning,
            }
            if turn_id:
                payload["turn_id"] = turn_id
            if round_index is not None:
                payload["round_index"] = round_index
            await self._bus.emit(EventTypes.WARNING, payload)

    @staticmethod
    def _compose_history_with_system_injection(
        history: List[Message],
        injected: Message | None,
    ) -> List[Message]:
        if injected is None:
            return list(history)
        if history and history[0].role == "system":
            return [history[0], injected, *history[1:]]
        return [injected, *history]

    async def _build_active_skill_injection(
        self,
        *,
        turn_id: str | None = None,
        round_index: int | None = None,
        emit_warnings: bool = True,
    ) -> Message | None:
        if self._skill_runtime is None:
            return None

        skill_message, warnings = self._skill_runtime.build_active_skill_system_message()
        if emit_warnings:
            await self._emit_skill_runtime_warnings(
                warnings,
                turn_id=turn_id,
                round_index=round_index,
            )
        if not skill_message:
            return None

        return Message(
            role="system",
            content=skill_message,
            timestamp=time.time(),
            metadata={
                "id": str(uuid.uuid4()),
                "source": "session_skills",
                "active_skills": (
                    self._skill_runtime.active_skill_names()
                    if self._skill_runtime is not None
                    else []
                ),
            },
        )

    async def _augment_history_with_active_skills(
        self,
        history: List[Message],
        *,
        turn_id: str,
        round_index: int,
    ) -> List[Message]:
        injected = await self._build_active_skill_injection(
            turn_id=turn_id,
            round_index=round_index,
            emit_warnings=True,
        )
        return self._compose_history_with_system_injection(history, injected)

    async def _resolve_skill_catalog(
        self,
    ) -> tuple[bool, List[Dict[str, Any]], List[str], str]:
        if self._skill_runtime is None:
            return False, [], [], "Skill runtime is not configured."

        skills, warnings = self._skill_runtime.list_skills()
        active = set(self._skill_runtime.active_skill_names())
        payload_skills = [
            {
                "name": skill.name,
                "description": skill.description,
                "source_dir": str(skill.source_dir),
                "active": skill.name in active,
            }
            for skill in skills
        ]
        if not payload_skills:
            message = (
                f"No skills found in {self._skill_runtime.skills_root}"
            )
        else:
            lines = ["Available skills:"]
            for skill in payload_skills:
                status = "active" if skill["active"] else "inactive"
                lines.append(
                    f"- {skill['name']} [{status}]: {skill['description']}"
                )
            message = "\n".join(lines)
        return True, payload_skills, warnings, message

    async def _persist_assistant_response(
        self,
        response: AgentResponse,
        *,
        turn_id: str,
        round_index: int,
    ) -> ContextStats:
        valid_tool_calls, malformed_tool_calls = self._split_tool_calls(
            list(response.tool_calls or [])
        )
        if malformed_tool_calls:
            await self._emit_malformed_tool_call_warning(
                turn_id=turn_id,
                pass_id=response.pass_id,
                round_index=round_index,
                malformed_tool_calls=malformed_tool_calls,
                stage="context_persist_filter",
            )
        stats = await self._context.add_assistant_pass(
            content=response.content,
            thinking=response.thinking,
            pass_id=response.pass_id,
            tokens=response.tokens,
            tool_call_count=len(valid_tool_calls),
            tool_calls=[
                self._assistant_tool_call_payload(req) for req in valid_tool_calls
            ],
        )
        await self._emit_context_update(
            stats,
            turn_id=turn_id,
            pass_id=response.pass_id,
            round_index=round_index,
        )
        return stats

    async def _estimate_request_metrics(
        self,
        history: List[Message],
    ) -> Dict[str, Any]:
        request_payload = build_request_payload_for_provider(
            self._provider,
            history,
            str(getattr(self._settings, "active_model_name", "") or ""),
            tools=self._registry.get_openai_tools(),
            options=getattr(self._settings, "model_parameters", {}) or {},
        )
        return await self._usage_ledger.estimate_request(
            request_payload=request_payload,
            context_limit=int(getattr(self._settings, "context_window_limit", 0) or 0),
        )

    async def _prepare_history_for_model_call(
        self,
        *,
        base_history: List[Message],
        full_history: List[Message],
        turn_id: str,
        round_index: int,
        persist_pruned_history: bool,
    ) -> tuple[List[Message], Dict[str, Any]]:
        current_history = list(full_history)
        base_ids = {id(message) for message in base_history}
        estimate = await self._estimate_request_metrics(current_history)
        pruned_chunks = 0

        while not estimate.get("within_limit", True):
            pruned_history = context_logic.drop_oldest_turn_chunk(current_history)
            if len(pruned_history) == len(current_history):
                break
            current_history = pruned_history
            pruned_chunks += 1
            estimate = await self._estimate_request_metrics(current_history)

        if pruned_chunks > 0:
            await self._bus.emit(
                EventTypes.INFO,
                {
                    "message": "Preflight pruning applied",
                    "data": {
                        "pruned_turn_chunks": pruned_chunks,
                        "estimated_next_request_tokens": estimate.get(
                            "estimated_next_request_tokens"
                        ),
                        "reserved_completion_tokens": estimate.get(
                            "reserved_completion_tokens"
                        ),
                        "context_limit": estimate.get("context_limit"),
                    },
                    "turn_id": turn_id,
                    "round_index": round_index,
                },
            )

            if persist_pruned_history:
                pruned_base_history = [
                    message for message in current_history if id(message) in base_ids
                ]
                stats = self._context.replace_history(pruned_base_history)
                await self._emit_context_update(
                    stats,
                    turn_id=turn_id,
                    round_index=round_index,
                )

        if not estimate.get("within_limit", True):
            await self._bus.emit(
                EventTypes.WARNING,
                {
                    "message": "Context may overflow model window",
                    "details": (
                        f"estimated_next_request_tokens={estimate.get('estimated_next_request_tokens', 0)} "
                        f"reserved_completion_tokens={estimate.get('reserved_completion_tokens', 0)} "
                        f"limit={estimate.get('context_limit', 0)}"
                    ),
                    "data": estimate,
                    "turn_id": turn_id,
                    "round_index": round_index,
                },
            )

        return current_history, estimate

    async def _record_usage_metrics(
        self,
        *,
        turn_id: str,
        round_index: int,
        response: AgentResponse,
        request_estimate: Dict[str, Any],
    ) -> Dict[str, Any]:
        record = self._usage_ledger.record_usage(
            turn_id=turn_id,
            pass_id=response.pass_id,
            round_index=round_index,
            raw_metrics=response.provider_metrics,
            request_estimate=request_estimate,
        )
        await self._bus.emit(
            EventTypes.METRICS_UPDATED,
            {
                "turn_id": turn_id,
                "pass_id": response.pass_id,
                "round_index": round_index,
                "record": record,
                "raw_provider_metrics": record.get("raw_provider_metrics", {}),
            },
        )
        return record

    async def _run_model_pass(
        self,
        *,
        base_history: List[Message],
        full_history: List[Message],
        turn_id: str,
        round_index: int,
        persist_pruned_history: bool,
    ) -> AgentResponse:
        prepared_history, request_estimate = await self._prepare_history_for_model_call(
            base_history=base_history,
            full_history=full_history,
            turn_id=turn_id,
            round_index=round_index,
            persist_pruned_history=persist_pruned_history,
        )
        response = await run_thinking_loop(
            context_history=prepared_history,
            provider=self._provider,
            bus=self._bus,
            registry=self._registry,
            settings=self._settings,
            turn_id=turn_id,
            round_index=round_index,
            preflight_metrics=request_estimate,
        )
        await self._record_usage_metrics(
            turn_id=turn_id,
            round_index=round_index,
            response=response,
            request_estimate=request_estimate,
        )
        return response

    @staticmethod
    def _split_tool_calls(
        tool_calls: List[ToolRequest],
    ) -> Tuple[List[ToolRequest], List[ToolRequest]]:
        valid: List[ToolRequest] = []
        malformed: List[ToolRequest] = []
        for req in tool_calls:
            req.name = str(getattr(req, "name", "") or "").strip()
            if req.name:
                valid.append(req)
            else:
                malformed.append(req)
        return valid, malformed

    def _build_tool_call_repair_prompt(
        self, malformed_tool_calls: List[ToolRequest]
    ) -> str:
        malformed_samples = [
            {
                "call_id": req.call_id,
                "name": req.name,
                "parameters": req.parameters,
                "provider": (req.metadata or {}).get("provider"),
                "malformed_reason": (req.metadata or {}).get("malformed_reason"),
            }
            for req in malformed_tool_calls
        ]
        allowed_tools = ", ".join(self._registry.list_tool_names())
        return (
            "Tool-call repair request.\n"
            "Your previous assistant pass produced malformed tool calls with empty function names.\n"
            f"Allowed tool names (exact): {allowed_tools}\n"
            "Re-emit your intended tool calls now using this strict contract:\n"
            "- Every tool call MUST include a non-empty `name`.\n"
            "- `parameters` MUST be a JSON object.\n"
            "- Do not emit empty objects `{}` as tool calls.\n"
            "- If no tool is required, return normal assistant text with zero tool calls.\n"
            f"Malformed calls observed: {json.dumps(malformed_samples, ensure_ascii=False, default=str)}"
        )

    async def _emit_malformed_tool_call_warning(
        self,
        *,
        turn_id: str,
        pass_id: str,
        round_index: int,
        malformed_tool_calls: List[ToolRequest],
        stage: str,
    ) -> None:
        samples = [
            {
                "call_id": req.call_id,
                "name": req.name,
                "parameters": req.parameters,
                "metadata": req.metadata,
            }
            for req in malformed_tool_calls[:3]
        ]
        await self._bus.emit(
            EventTypes.WARNING,
            {
                "message": "Malformed tool calls detected",
                "details": (
                    f"{stage}: {len(malformed_tool_calls)} call(s) missing tool name."
                ),
                "data": {
                    "malformed_count": len(malformed_tool_calls),
                    "samples": samples,
                },
                "turn_id": turn_id,
                "pass_id": pass_id,
                "round_index": round_index,
            },
        )

    async def _request_tool_call_repair_pass(
        self,
        *,
        turn_id: str,
        round_index: int,
        malformed_tool_calls: List[ToolRequest],
    ) -> AgentResponse:
        # Only transition to THINKING if not already there (avoid state machine violation)
        if self._state.current != AgentState.THINKING:
            await self._set_status(
                AgentState.THINKING,
                "Repairing malformed tool calls...",
                turn_id=turn_id,
                round_index=round_index,
            )
        history = self._context.get_full_history()
        repair_prompt = self._build_tool_call_repair_prompt(malformed_tool_calls)
        augmented_history = [
            *history,
            Message(role="system", content=repair_prompt, timestamp=time.time()),
        ]
        response = await self._run_model_pass(
            base_history=history,
            full_history=augmented_history,
            turn_id=turn_id,
            round_index=round_index,
            persist_pruned_history=True,
        )
        await self._persist_assistant_response(
            response,
            turn_id=turn_id,
            round_index=round_index,
        )
        return response

    async def _handle_user_input(self, payload: UserRequest) -> None:
        """
        Main Handler: User speaks -> Agent processes.
        """
        async with self._request_lock:
            try:
                turn_id = str(getattr(payload, "request_id", "") or uuid.uuid4())

                # 1. State: IDLE -> THINKING
                await self._set_status(
                    AgentState.THINKING,
                    "Processing user input...",
                    turn_id=turn_id,
                    round_index=0,
                )

                # 2. Logic: Update Context
                stats = await self._context.add_user_message(payload.text)

                # 3. Emit Verification
                await self._emit_context_update(stats, turn_id=turn_id, round_index=0)

                # 4. Trigger LLM Thinking Loop (THE BRAIN)
                history = self._context.get_full_history()
                full_history = await self._augment_history_with_active_skills(
                    history,
                    turn_id=turn_id,
                    round_index=0,
                )
                self._logger.info("Entering Thinking Loop...")

                response = await self._run_model_pass(
                    base_history=history,
                    full_history=full_history,
                    turn_id=turn_id,
                    round_index=0,
                    persist_pruned_history=True,
                )
                await self._persist_assistant_response(
                    response,
                    turn_id=turn_id,
                    round_index=0,
                )

                # 5. Think/Act loop: tool results are added back to context,
                # then the model gets another pass to produce a final answer.
                # We cap rounds to prevent runaway loops.
                max_tool_rounds = 400
                rounds = 0
                stopped_by_rejection = False
                stopped_by_malformed = False
                tool_repair_attempted = False
                while response.tool_calls and rounds < max_tool_rounds:
                    valid_tool_calls, malformed_tool_calls = self._split_tool_calls(
                        response.tool_calls
                    )
                    if malformed_tool_calls:
                        await self._emit_malformed_tool_call_warning(
                            turn_id=turn_id,
                            pass_id=response.pass_id,
                            round_index=rounds,
                            malformed_tool_calls=malformed_tool_calls,
                            stage="pre_execution",
                        )
                        if not tool_repair_attempted:
                            tool_repair_attempted = True
                            response = await self._request_tool_call_repair_pass(
                                turn_id=turn_id,
                                round_index=rounds,
                                malformed_tool_calls=malformed_tool_calls,
                            )
                            continue

                        stopped_by_malformed = True
                        await self._bus.emit(
                            EventTypes.WARNING,
                            {
                                "message": "Malformed tool calls persisted after repair",
                                "details": (
                                    f"Stopping turn after {len(malformed_tool_calls)} malformed tool call(s)."
                                ),
                                "turn_id": turn_id,
                                "pass_id": response.pass_id,
                                "round_index": rounds,
                            },
                        )
                        break

                    rounds += 1
                    await self._set_status(
                        AgentState.EXECUTING,
                        f"Executing {len(valid_tool_calls)} tools...",
                        turn_id=turn_id,
                        pass_id=response.pass_id,
                        round_index=rounds,
                    )

                    user_rejected = False
                    for tool_index, tool_req in enumerate(valid_tool_calls):
                        tool_def = self._registry.get_tool(tool_req.name)
                        requires_confirmation = bool(
                            tool_def and tool_def.requires_confirmation
                        )
                        # Always trust local tool policy over provider payload.
                        tool_req.requires_confirmation = requires_confirmation

                        # Create a confirmation future if the tool requires confirmation
                        confirmation_future = None
                        if requires_confirmation and not self._auto_confirm:
                            self._logger.info(
                                f"Creating confirmation future for tool: {tool_req.name}"
                            )
                            confirmation_future = asyncio.Future()
                            self._pending_confirmations[tool_req.call_id] = (
                                confirmation_future
                            )

                        # Execute the tool with the confirmation future
                        try:
                            result = await run_action_loop(
                                tool_req=tool_req,
                                registry=self._registry,
                                bus=self._bus,
                                executor=self._executor,
                                turn_id=turn_id,
                                pass_id=response.pass_id,
                                round_index=rounds,
                                tool_index=tool_index,
                                confirmation_future=confirmation_future,
                                auto_approve=self._auto_confirm,
                                set_status=self._set_status,
                            )
                        finally:
                            self._pending_confirmations.pop(tool_req.call_id, None)

                        # Persist every tool outcome so the next turn/model pass can reason over it.
                        stats = await self._context.add_tool_result(result)
                        await self._emit_context_update(
                            stats,
                            turn_id=turn_id,
                            pass_id=response.pass_id,
                            round_index=rounds,
                            tool_call_id=result.call_id,
                            tool_index=tool_index,
                        )

                        if result.error_code == "user_rejected":
                            # Close the current tool-call batch in-order. The provider expects
                            # each assistant tool_call id to eventually receive a terminal tool
                            # result, even when we stop the turn on rejection.
                            for skipped_offset, skipped_req in enumerate(
                                valid_tool_calls[tool_index + 1 :], start=1
                            ):
                                stats = await self._context.add_tool_result(
                                    ToolResult(
                                        tool_name=skipped_req.name,
                                        call_id=skipped_req.call_id,
                                        success=False,
                                        output=None,
                                        duration=0,
                                        error=(
                                            "Skipped because an earlier tool call in this batch "
                                            "was rejected."
                                        ),
                                        error_code="skipped_due_to_rejection",
                                        output_kind="none",
                                        error_details={
                                            "blocked_by_tool_call_id": tool_req.call_id
                                        },
                                        request_parameters=skipped_req.parameters,
                                    )
                                )
                                await self._emit_context_update(
                                    stats,
                                    turn_id=turn_id,
                                    pass_id=response.pass_id,
                                    round_index=rounds,
                                    tool_call_id=skipped_req.call_id,
                                    tool_index=tool_index + skipped_offset,
                                )
                            user_rejected = True
                            stopped_by_rejection = True
                            await self._bus.emit(
                                EventTypes.INFO,
                                {
                                    "message": (
                                        "Tool execution rejected. Skipping follow-up model pass for this turn."
                                    ),
                                    "turn_id": turn_id,
                                    "pass_id": response.pass_id,
                                    "round_index": rounds,
                                },
                            )
                            break

                    if user_rejected:
                        break

                    await self._set_status(
                        AgentState.THINKING,
                        "Processing tool results...",
                        turn_id=turn_id,
                        round_index=rounds,
                    )
                    history = self._context.get_full_history()
                    full_history = await self._augment_history_with_active_skills(
                        history,
                        turn_id=turn_id,
                        round_index=rounds,
                    )
                    response = await self._run_model_pass(
                        base_history=history,
                        full_history=full_history,
                        turn_id=turn_id,
                        round_index=rounds,
                        persist_pruned_history=True,
                    )
                    await self._persist_assistant_response(
                        response,
                        turn_id=turn_id,
                        round_index=rounds,
                    )

                if (
                    response.tool_calls
                    and rounds >= max_tool_rounds
                    and not stopped_by_rejection
                    and not stopped_by_malformed
                ):
                    await self._bus.emit(
                        EventTypes.WARNING,
                        {
                            "message": "Tool loop limit reached",
                            "details": f"Stopped after {max_tool_rounds} tool rounds",
                            "turn_id": turn_id,
                            "pass_id": response.pass_id,
                            "round_index": rounds,
                        },
                    )

                # 6. State: -> IDLE
                await self._set_status(
                    AgentState.IDLE,
                    "Ready",
                    turn_id=turn_id,
                    round_index=rounds,
                )

            except Exception as e:
                self._logger.error(f"Error in main loop: {e}", exc_info=True)
                await self._set_status(AgentState.ERROR, f"System Error: {str(e)}")

    async def _emit_context_update(
        self,
        stats: ContextStats,
        *,
        turn_id: str | None = None,
        pass_id: str | None = None,
        round_index: int | None = None,
        tool_call_id: str | None = None,
        tool_index: int | None = None,
    ) -> None:
        context_limit = int(getattr(self._settings, "context_window_limit", 0) or 0)
        correlation: Dict[str, Any] = {}
        if turn_id:
            correlation["turn_id"] = turn_id
        if pass_id:
            correlation["pass_id"] = pass_id
        if round_index is not None:
            correlation["round_index"] = round_index
        if tool_call_id:
            correlation["tool_call_id"] = tool_call_id
        if tool_index is not None:
            correlation["tool_index"] = tool_index

        payload: Dict[str, Any] = {
            "message": "Context updated",
            "data": {
                "total_tokens": stats.total_tokens,
                "stored_history_tokens": stats.total_tokens,
                "message_count": stats.message_count,
                "loaded_files_count": stats.loaded_files_count,
                "context_limit": context_limit,
            },
        }
        if correlation:
            payload["data"]["correlation"] = correlation
            payload.update(correlation)

        await self._bus.emit(
            EventTypes.INFO,
            payload,
        )

    async def _resolve_context_stats(self) -> ContextStats:
        get_stats = getattr(self._context, "get_stats", None)
        if callable(get_stats):
            maybe_stats = get_stats()
            if asyncio.iscoroutine(maybe_stats):
                maybe_stats = await maybe_stats
            if isinstance(maybe_stats, ContextStats):
                return maybe_stats

        history = self._context._store.get_full_history()
        total_tokens = 0
        for message in history:
            total_tokens += len((message.content or "")) // 4
            if getattr(message, "tool_call_id", None):
                total_tokens += len(str(message.tool_call_id)) // 4
            if getattr(message, "name", None):
                total_tokens += len(str(message.name)) // 4
            if getattr(message, "tool_calls", None):
                total_tokens += len(str(message.tool_calls)) // 4
        return ContextStats(
            total_tokens=total_tokens,
            message_count=len(history),
            loaded_files_count=0,
        )

    async def _emit_command_result(
        self,
        command: str,
        ok: bool,
        message: str,
        data: Dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "command": str(command or "").strip().lower(),
            "ok": bool(ok),
            "message": str(message or ""),
            "data": data or {},
        }
        await self._bus.emit(EventTypes.COMMAND_RESULT, payload)

    def _resolve_working_directory(self) -> str:
        workspace_root = getattr(self._settings, "workspace_root", None)
        if workspace_root is None:
            workspace_root = getattr(self._settings, "workspace", None)
        return str(workspace_root) if workspace_root is not None else os.getcwd()

    async def _build_runtime_snapshot(self) -> Dict[str, Any]:
        stats = await self._resolve_context_stats()
        state = getattr(self._state.current, "value", str(self._state.current))
        history = self._context.get_full_history()
        active_skill_injection = await self._build_active_skill_injection(
            emit_warnings=False
        )
        full_history = self._compose_history_with_system_injection(
            history,
            active_skill_injection,
        )
        estimate = await self._estimate_request_metrics(full_history)
        return self._usage_ledger.build_snapshot(
            stored_history_tokens=int(getattr(stats, "total_tokens", 0) or 0),
            message_count=int(getattr(stats, "message_count", 0) or 0),
            loaded_files_count=int(getattr(stats, "loaded_files_count", 0) or 0),
            context_limit=int(getattr(self._settings, "context_window_limit", 0) or 0),
            provider_name=str(getattr(self._settings, "llm_provider", "")),
            model_name=str(getattr(self._settings, "active_model_name", "")),
            working_directory=self._resolve_working_directory(),
            state=str(state),
            auto_confirm=bool(self._auto_confirm),
            request_estimate=estimate,
        )

    async def _emit_status_snapshot(self) -> Dict[str, Any]:
        return await self._build_runtime_snapshot()

    async def _emit_metrics_snapshot(self) -> Dict[str, Any]:
        return await self._build_runtime_snapshot()

    def _build_compact_history(
        self,
        history: List[Message],
        compact_system_prompt: str,
    ) -> List[Message]:
        compact_system = Message(
            role="system",
            content=str(compact_system_prompt or "").strip(),
            timestamp=time.time(),
            metadata={"id": str(uuid.uuid4()), "mode": "compact"},
        )
        conversation_only = [msg for msg in history if msg.role != "system"]
        return [compact_system, *conversation_only]

    async def _set_status(
        self,
        state: AgentState,
        message: str,
        *,
        turn_id: str | None = None,
        pass_id: str | None = None,
        round_index: int | None = None,
        tool_call_id: str | None = None,
        tool_index: int | None = None,
    ) -> None:
        """
        Helper to update internal state and emit event in one go.
        """
        try:
            self._state.transition_to(state)
            status_payload = AgentStatus(
                status=state.value,
                message=message,
                turn_id=turn_id,
                pass_id=pass_id,
                round_index=round_index,
                tool_call_id=tool_call_id,
                tool_index=tool_index,
            )
            await self._bus.emit(EventTypes.STATUS_CHANGED, status_payload)
        except ValueError as e:
            self._logger.critical(f"State Machine Violation: {e}")
            self._logger.info("Attempting recovery by resetting to IDLE state")
            # Force reset to IDLE for recovery
            self._state._current_state = AgentState.IDLE
            await self._bus.emit(
                EventTypes.ERROR,
                {
                    "message": "State machine violation (recovered)",
                    "details": str(e),
                    "recovered": True,
                },
            )

    async def _handle_tool_confirmation(self, payload: ConfirmationResponse) -> None:
        """
        Handle TOOL_CONFIRMATION_SUBMITTED events to resolve pending confirmation futures.
        """
        try:
            self._logger.info(
                f"Received tool confirmation for call_id: {payload.tool_call_id}"
            )

            # Validate payload
            if not hasattr(payload, "tool_call_id") or not payload.tool_call_id:
                self._logger.error("Invalid confirmation payload: missing tool_call_id")
                await self._bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Invalid confirmation payload",
                        "details": "Missing tool_call_id",
                    },
                )
                return

            if not hasattr(payload, "decision") or payload.decision not in [
                "approved",
                "rejected",
            ]:
                self._logger.error(f"Invalid confirmation decision: {payload.decision}")
                await self._bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Invalid confirmation decision",
                        "details": f"Decision must be approved or rejected, got {payload.decision}",
                    },
                )
                return

            future = self._pending_confirmations.get(payload.tool_call_id)
            # Resolve the pending confirmation future if it exists.
            if future and not future.done():
                self._logger.info(
                    f"Resolving confirmation future for call_id: {payload.tool_call_id}"
                )
                future.set_result(payload)
            else:
                self._logger.warning(
                    f"No pending confirmation found for call_id: {payload.tool_call_id}"
                )
                await self._bus.emit(
                    EventTypes.WARNING,
                    {
                        "message": "No pending confirmation found",
                        "details": f"Tool call ID {payload.tool_call_id} not found",
                    },
                )

        except Exception as e:
            self._logger.error(f"Error handling tool confirmation: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error processing tool confirmation", "details": str(e)},
            )

    async def _handle_system_command(self, payload: dict) -> None:
        """
        Handle SYSTEM_COMMAND_ISSUED events to process system-level commands.
        """
        try:
            self._logger.info(f"Received system command: {payload}")

            # Validate payload
            if not isinstance(payload, dict):
                self._logger.error("Invalid system command payload: not a dictionary")
                await self._bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Invalid system command payload",
                        "details": "Payload must be a dictionary",
                    },
                )
                return

            command = payload.get("command")
            if not command:
                self._logger.error(
                    "Invalid system command payload: missing 'command' field"
                )
                await self._bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Invalid system command payload",
                        "details": "Missing 'command' field",
                    },
                )
                return

            # Process different system commands
            if command == "cancel_current_task":
                await self._handle_cancel_task()
            elif command == "dispatch_slash":
                await self._handle_slash_dispatch(str(payload.get("text", "") or ""))
            elif command == "reset_context":
                await self._handle_reset_context()
            elif command == "refresh_status":
                await self._handle_refresh_status()
            elif command == "toggle_auto_confirm":
                auto_confirm = payload.get("auto_confirm", True)
                await self._handle_toggle_auto_confirm(auto_confirm)
            else:
                self._logger.warning(f"Unknown system command: {command}")
                await self._bus.emit(
                    EventTypes.WARNING,
                    {
                        "message": "Unknown system command",
                        "details": f"Command '{command}' is not recognized",
                    },
                )
                await self._emit_command_result(
                    "system",
                    False,
                    f"Unknown system command: {command}",
                    {"command": command},
                )

        except Exception as e:
            self._logger.error(f"Error handling system command: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error processing system command", "details": str(e)},
            )
            await self._emit_command_result(
                "system",
                False,
                "Error processing system command",
                {"details": str(e)},
            )

    async def _handle_slash_dispatch(self, text: str) -> None:
        parsed = parse_slash_command(text)
        if not parsed.ok:
            await self._emit_command_result(
                "slash",
                False,
                parsed.error or "Invalid slash command.",
                {"input": text},
            )
            return

        command_name = str(parsed.command)
        if command_name == "toggle_auto_confirm":
            mode = parsed.arguments.get("mode")
            if mode == "set":
                target = bool(parsed.arguments.get("value", False))
            else:
                target = not self._auto_confirm
            ok = await self._handle_toggle_auto_confirm(target)
            await self._emit_command_result(
                "auto_confirm",
                ok,
                (
                    f"Auto-confirm {'enabled' if target else 'disabled'}"
                    if ok
                    else "Failed to update auto-confirm"
                ),
                {"auto_confirm": bool(target)},
            )
            return

        if command_name == "reset_context":
            ok = await self._handle_reset_context()
            await self._emit_command_result(
                "reset",
                ok,
                "Context reset successfully" if ok else "Context reset failed",
            )
            return

        if command_name == "status":
            try:
                snapshot = await self._emit_status_snapshot()
                await self._emit_command_result(
                    "status",
                    True,
                    "Status snapshot",
                    snapshot,
                )
            except Exception as exc:
                await self._emit_command_result(
                    "status",
                    False,
                    "Failed to capture status",
                    {"details": str(exc)},
                )
            return

        if command_name == "metrics":
            try:
                snapshot = await self._emit_metrics_snapshot()
                await self._emit_command_result(
                    "metrics",
                    True,
                    "Metrics snapshot",
                    snapshot,
                )
            except Exception as exc:
                await self._emit_command_result(
                    "metrics",
                    False,
                    "Failed to capture metrics",
                    {"details": str(exc)},
                )
            return

        if command_name == "skills":
            ok, payload_skills, warnings, message = await self._resolve_skill_catalog()
            await self._emit_skill_runtime_warnings(warnings)
            active_skills = (
                self._skill_runtime.active_skill_names()
                if self._skill_runtime is not None
                else []
            )
            await self._emit_command_result(
                "skills",
                ok,
                message,
                {
                    "skills": payload_skills,
                    "active_skills": active_skills,
                },
            )
            return

        if command_name == "activate_skill":
            if self._skill_runtime is None:
                await self._emit_command_result(
                    "activate_skill",
                    False,
                    "Skill runtime is not configured.",
                )
                return
            ok, message, warnings = self._skill_runtime.activate(
                str(parsed.arguments.get("name", "") or "")
            )
            await self._emit_skill_runtime_warnings(warnings)
            await self._emit_command_result(
                "activate_skill",
                ok,
                message,
                {"active_skills": self._skill_runtime.active_skill_names()},
            )
            return

        if command_name == "deactivate_skill":
            if self._skill_runtime is None:
                await self._emit_command_result(
                    "deactivate_skill",
                    False,
                    "Skill runtime is not configured.",
                )
                return
            ok, message, warnings = self._skill_runtime.deactivate(
                str(parsed.arguments.get("name", "") or "")
            )
            await self._emit_skill_runtime_warnings(warnings)
            await self._emit_command_result(
                "deactivate_skill",
                ok,
                message,
                {"active_skills": self._skill_runtime.active_skill_names()},
            )
            return

        if command_name == "compact":
            await self._handle_compact_command()
            return

        await self._emit_command_result(
            "slash",
            False,
            f"Unsupported slash command: {command_name}",
        )

    async def _handle_compact_command(self) -> None:
        async with self._request_lock:
            turn_id = f"compact-{uuid.uuid4()}"
            try:
                history = self._context.get_full_history()
                if len(history) <= 1:
                    await self._emit_command_result(
                        "compact",
                        False,
                        "No conversation history to compact.",
                    )
                    return

                compact_prompt = load_prompt_template(COMPACT_PROMPT_TEMPLATE_FILENAME)
                compact_history = self._build_compact_history(history, compact_prompt)

                await self._set_status(
                    AgentState.THINKING,
                    "Compacting context...",
                    turn_id=turn_id,
                    round_index=0,
                )
                response = await self._run_model_pass(
                    base_history=history,
                    full_history=compact_history,
                    turn_id=turn_id,
                    round_index=0,
                    persist_pruned_history=False,
                )
                summary = str(response.content or "").strip()
                if not summary:
                    await self._set_status(
                        AgentState.IDLE,
                        "Ready",
                        turn_id=turn_id,
                        round_index=0,
                    )
                    await self._emit_command_result(
                        "compact",
                        False,
                        "Compaction produced an empty summary. Context unchanged.",
                    )
                    return

                await self._context.reset()
                normal_system_prompt = str(getattr(self._settings, "system_prompt", "")).strip()
                if not normal_system_prompt:
                    current_system = self._context.get_system_prompt()
                    normal_system_prompt = str(
                        getattr(current_system, "content", "") or ""
                    ).strip()
                if normal_system_prompt:
                    await self._context.set_system_prompt_text(normal_system_prompt)

                stats = await self._context.add_assistant_pass(
                    content=summary,
                    thinking="",
                    pass_id=f"compact-{response.pass_id or uuid.uuid4()}",
                    tokens=max(1, int(response.tokens or 0)),
                    tool_call_count=0,
                    tool_calls=[],
                )
                await self._emit_context_update(stats, turn_id=turn_id, round_index=1)
                await self._set_status(
                    AgentState.IDLE,
                    "Ready",
                    turn_id=turn_id,
                    round_index=1,
                )
                await self._emit_command_result(
                    "compact",
                    True,
                    "Context compacted and reset successfully.",
                    {
                        "summary_chars": len(summary),
                        "summary_tokens": max(1, int(response.tokens or 0)),
                        "message_count": stats.message_count,
                        "total_tokens": stats.total_tokens,
                    },
                )
            except Exception as exc:
                if self._state.current != AgentState.IDLE:
                    await self._set_status(
                        AgentState.IDLE,
                        "Ready",
                        turn_id=turn_id,
                        round_index=0,
                    )
                self._logger.error("Error compacting context: %s", exc, exc_info=True)
                await self._emit_command_result(
                    "compact",
                    False,
                    "Compaction failed. Context unchanged.",
                    {"details": str(exc)},
                )

    async def _handle_cancel_task(self) -> None:
        """
        Handle task cancellation command.
        """
        try:
            active_futures = [
                future
                for future in self._pending_confirmations.values()
                if not future.done()
            ]
            if active_futures:
                self._logger.info(
                    "Cancelling %d pending confirmation task(s)", len(active_futures)
                )
                for future in active_futures:
                    future.cancel()
                self._pending_confirmations.clear()
                await self._set_status(AgentState.IDLE, "Task cancelled by user")
                await self._bus.emit(
                    EventTypes.INFO, {"message": "Task cancelled successfully"}
                )
            else:
                self._logger.info("No active task to cancel")
                await self._bus.emit(
                    EventTypes.INFO, {"message": "No active task to cancel"}
                )
        except Exception as e:
            self._logger.error(f"Error cancelling task: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error cancelling task", "details": str(e)},
            )

    async def _handle_reset_context(self) -> bool:
        """
        Handle context reset command.
        """
        try:
            # Reset the context coordinator
            await self._context.reset()
            stats = await self._resolve_context_stats()
            await self._emit_context_update(stats)
            self._logger.info("Context reset successfully")
            await self._bus.emit(
                EventTypes.INFO, {"message": "Context reset successfully"}
            )

            # Only set status to IDLE if we're not already idle
            current_state = self._state.current
            if current_state != AgentState.IDLE:
                await self._set_status(AgentState.IDLE, "Context reset")
            else:
                # Just emit a status update without changing state
                status_payload = AgentStatus(
                    status=AgentState.IDLE.value, message="Context reset"
                )
                await self._bus.emit(EventTypes.STATUS_CHANGED, status_payload)
            return True

        except Exception as e:
            self._logger.error(f"Error resetting context: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error resetting context", "details": str(e)},
            )
            return False

    async def _handle_refresh_status(self) -> bool:
        """
        Emit a status-bar refresh payload without going through user input.
        """
        try:
            stats = await self._resolve_context_stats()
            await self._emit_context_update(stats)
            return True
        except Exception as e:
            self._logger.error(f"Error refreshing status: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error refreshing status", "details": str(e)},
            )
            return False

    async def _handle_toggle_auto_confirm(self, auto_confirm: bool) -> bool:
        """
        Handle auto-confirm toggle command.
        """
        try:
            # Update settings or configuration
            self._logger.info(f"Toggling auto-confirm to: {auto_confirm}")
            self._auto_confirm = bool(auto_confirm)
            await self._bus.emit(
                EventTypes.AUTO_CONFIRM_CHANGED, {"auto_confirm": self._auto_confirm}
            )
            await self._bus.emit(
                EventTypes.INFO,
                {
                    "message": f"Auto-confirm {'enabled' if self._auto_confirm else 'disabled'}"
                },
            )
            return True
        except Exception as e:
            self._logger.error(f"Error toggling auto-confirm: {e}", exc_info=True)
            await self._bus.emit(
                EventTypes.ERROR,
                {"message": "Error toggling auto-confirm", "details": str(e)},
            )
            return False
