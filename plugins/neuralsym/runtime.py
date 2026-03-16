"""NeuralSym runtime and provider resolution."""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace
from typing import Any

from protocol_monk.exceptions.base import log_exception

from .advisor import MissionControlAdvisor, NoOpAdvisor
from .config import NeuralSymSettings
from .models import (
    AdviceSnapshot,
    Observation,
    ProviderResolutionInfo,
    RuntimeState,
    WorkspaceProfile,
)
from .renderer import AdviceRenderer
from .storage import NeuralSymStorage

logger = logging.getLogger("NeuralSymRuntime")

_STOP = object()


async def resolve_provider_info(settings: NeuralSymSettings) -> tuple[ProviderResolutionInfo, Any | None]:
    """Resolve one provider/model for the NeuralSym session."""

    candidates: list[tuple[str, str | None, bool]] = []
    explicit_provider = settings.provider

    if explicit_provider == "openrouter":
        candidates.append(("openrouter", settings.model or settings.fallback_model, False))
    elif explicit_provider == "ollama":
        candidates.append(("ollama", settings.model, False))
        if settings.allow_openrouter_fallback:
            candidates.append(("openrouter", settings.fallback_model or settings.model, True))
    elif settings.prefer_local_provider:
        candidates.append(("ollama", settings.model, False))
        if settings.allow_openrouter_fallback:
            candidates.append(("openrouter", settings.fallback_model or settings.model, True))
    else:
        if settings.allow_openrouter_fallback:
            candidates.append(("openrouter", settings.fallback_model or settings.model, False))
        candidates.append(("ollama", settings.model, False))

    for provider_name, model_name, used_fallback in candidates:
        provider = _instantiate_provider(provider_name, settings)
        if provider is None:
            continue
        try:
            available = await provider.validate_connection()
        except Exception as exc:
            log_exception(
                logger,
                logging.WARNING,
                f"NeuralSym provider validation failed for {provider_name}",
                exc,
            )
            available = False
        if available:
            return (
                ProviderResolutionInfo(
                    provider_name=provider_name,
                    model_name=model_name,
                    used_fallback=used_fallback,
                    locked=True,
                    available=True,
                ),
                provider,
            )

    return ProviderResolutionInfo(locked=True, available=False), None


def _instantiate_provider(provider_name: str, settings: NeuralSymSettings) -> Any | None:
    """Create a provider instance using a minimal settings shim."""

    if provider_name == "openrouter" and not settings.openrouter_api_key:
        return None

    provider_settings = SimpleNamespace(
        llm_provider=provider_name,
        ollama_host=settings.ollama_host,
        ollama_api_key=settings.ollama_api_key,
        openrouter_api_key=settings.openrouter_api_key,
        openrouter_base_url=settings.openrouter_base_url,
    )

    if provider_name == "openrouter":
        from protocol_monk.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(provider_settings)

    from protocol_monk.providers.ollama import OllamaProvider

    return OllamaProvider(provider_settings)


class NeuralSymRuntime:
    """Queue-backed advise-only runtime."""

    def __init__(
        self,
        settings: NeuralSymSettings,
        *,
        storage: NeuralSymStorage | None = None,
        advisor: MissionControlAdvisor | NoOpAdvisor | None = None,
        renderer: AdviceRenderer | None = None,
    ):
        self.settings = settings
        self.storage = storage or NeuralSymStorage(settings.state_dir)
        self.advisor = advisor or MissionControlAdvisor(
            advice_token_budget=settings.advice_token_budget
        )
        self.renderer = renderer or AdviceRenderer()
        self._queue: asyncio.Queue[Observation | object] = asyncio.Queue(
            maxsize=settings.max_pending_observations
        )
        self._worker_task: asyncio.Task[None] | None = None
        self._profile = WorkspaceProfile(
            workspace_id=settings.workspace_id,
            workspace_root=str(settings.workspace_root),
        )
        self._snapshot = AdviceSnapshot(workspace_id=settings.workspace_id, directives=[])
        self._state = RuntimeState(workspace_id=settings.workspace_id)
        self._provider: Any | None = None

    async def start(self) -> None:
        """Load persisted state, resolve provider, and start the worker if enabled."""

        if not self.settings.enabled:
            return

        self.storage.ensure_state_dir()
        self._profile = self.storage.load_workspace_profile() or self._profile
        self._snapshot = self.storage.load_advice_snapshot() or self._snapshot
        self._state = self.storage.load_runtime_state() or self._state
        resolution, provider = await resolve_provider_info(self.settings)
        self._provider = provider
        self._state.resolution = resolution
        self._persist_state()
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Flush queued observations and stop the worker."""

        if self._worker_task is None:
            return
        await self._queue.put(_STOP)
        await self._worker_task
        self._worker_task = None
        self._persist_state()

    async def observe(self, observation: Observation) -> None:
        """Queue an observation without blocking main agent flow."""

        if not self.settings.enabled or self._worker_task is None:
            return

        self._state.observations_received += 1
        try:
            self._queue.put_nowait(observation)
        except asyncio.QueueFull:
            dropped = self._queue.get_nowait()
            if dropped is not _STOP:
                self._state.dropped_observations += 1
            self._queue.task_done()
            self._queue.put_nowait(observation)
        self._state.queue_depth = self._queue.qsize()
        self._persist_state()

    async def get_advice_message(
        self,
        *,
        turn_id: str | None = None,
        round_index: int | None = None,
    ) -> str | None:
        """Render the current advice snapshot for the current pass."""

        if not self.settings.enabled:
            return None
        current = self._snapshot.model_copy(
            update={"turn_id": turn_id, "round_index": round_index}
        )
        return self.renderer.render(current)

    def get_runtime_state(self) -> RuntimeState:
        """Expose the current runtime state for tests and diagnostics."""

        return self._state

    async def _worker_loop(self) -> None:
        while True:
            item = await self._queue.get()
            if item is _STOP:
                self._queue.task_done()
                break

            batch: list[Observation] = [item]
            stop_requested = False
            if self.settings.batch_window_seconds > 0:
                await asyncio.sleep(self.settings.batch_window_seconds)
            while True:
                try:
                    pending = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if pending is _STOP:
                    self._queue.task_done()
                    stop_requested = True
                    break
                batch.append(pending)
            await self._process_batch(batch)
            if stop_requested:
                break

    async def _process_batch(self, batch: list[Observation]) -> None:
        if not batch:
            return
        for observation in batch:
            self.storage.append_observation(observation)
        all_observations = self.storage.load_observations()
        correlation = batch[-1].correlation
        self._profile, self._snapshot = await self.advisor.build_snapshot(
            profile=self._profile,
            observations=all_observations,
            turn_id=correlation.turn_id,
            round_index=correlation.round_index,
        )
        self._state.observations_processed += len(batch)
        self._state.queue_depth = self._queue.qsize()
        self._state.last_batch_processed_at = time.time()
        self._state.last_advice_refresh_at = self._snapshot.generated_at
        self._persist_state()
        for _ in batch:
            self._queue.task_done()

    def _persist_state(self) -> None:
        self.storage.save_workspace_profile(self._profile)
        self.storage.save_advice_snapshot(self._snapshot)
        self.storage.save_runtime_state(self._state)
