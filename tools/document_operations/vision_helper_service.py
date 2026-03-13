from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ollama import AsyncClient

from protocol_monk.config.settings import Settings
from protocol_monk.exceptions.tools import ToolError

logger = logging.getLogger(__name__)


class VisionHelperService:
    """Ollama-backed helper for image understanding and OCR-like extraction."""

    def __init__(self, settings: Settings, client: Optional[AsyncClient] = None):
        self._settings = settings
        headers: Dict[str, str] = {}
        api_key = getattr(settings, "ollama_api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or AsyncClient(host=settings.ollama_host, headers=headers)

    async def analyze_image(
        self,
        image_path: Path,
        *,
        purpose: str,
    ) -> Dict[str, Any]:
        if not getattr(self._settings, "document_vision_enabled", True):
            raise ToolError(
                "Document vision helper is disabled.",
                user_hint="Set DOCUMENT_VISION_ENABLED=1 to analyze images.",
            )

        model_name = self._resolve_model_name()

        encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        prompt = self._build_analysis_prompt(purpose)
        raw_response = await self._request_json_with_image(
            model_name=model_name,
            prompt=prompt,
            encoded_image=encoded_image,
        )
        parsed = self._parse_json_payload(raw_response)
        if parsed is None:
            repaired = await self._repair_json_response(
                model_name=model_name,
                raw_response=raw_response,
            )
            parsed = self._parse_json_payload(repaired)
            if parsed is None:
                raise ToolError(
                    "Vision helper returned invalid JSON.",
                    user_hint=(
                        "The configured vision model did not return machine-readable JSON."
                    ),
                    details={"raw_response": raw_response[:1000]},
                )

        return self._normalize_payload(parsed)

    def _resolve_model_name(self) -> str:
        explicit_model = str(
            getattr(self._settings, "document_vision_model", "") or ""
        ).strip()
        if explicit_model:
            return explicit_model

        provider = str(getattr(self._settings, "llm_provider", "") or "").strip().lower()
        active_model_name = str(
            getattr(self._settings, "active_model_name", "") or ""
        ).strip()
        active_model_config = self._get_active_model_config()
        if (
            provider == "ollama"
            and active_model_name
            and self._model_supports_vision(active_model_config)
        ):
            logger.info(
                "Using active Ollama vision model '%s' for document analysis.",
                active_model_name,
            )
            return active_model_name

        raise ToolError(
            "Document vision helper model is not configured.",
            user_hint=self._build_missing_model_hint(
                provider=provider,
                active_model_name=active_model_name,
                active_model_config=active_model_config,
            ),
        )

    async def _request_json_with_image(
        self,
        *,
        model_name: str,
        prompt: str,
        encoded_image: str,
    ) -> str:
        response = await self._client.chat(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [encoded_image],
                }
            ],
            options={"temperature": 0},
            stream=False,
            format="json",
        )
        return self._extract_message_content(response)

    async def _repair_json_response(
        self,
        *,
        model_name: str,
        raw_response: str,
    ) -> str:
        repair_prompt = (
            "Convert the following response into valid JSON only. "
            "Use this schema: "
            '{"description": string, "detected_text_blocks": [{"text": string}], '
            '"observations": [string], "warnings": [string]}. '
            "Do not wrap the JSON in markdown.\n\n"
            f"Response:\n{raw_response}"
        )
        response = await self._client.chat(
            model=model_name,
            messages=[{"role": "user", "content": repair_prompt}],
            options={"temperature": 0},
            stream=False,
            format="json",
        )
        return self._extract_message_content(response)

    def _extract_message_content(self, response: Any) -> str:
        if isinstance(response, dict):
            message = response.get("message") or {}
            content = message.get("content")
            return str(content or "")

        message = getattr(response, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if content is not None:
                return str(content)

        content = getattr(response, "content", None)
        if content is not None:
            return str(content)

        return ""

    def _build_analysis_prompt(self, purpose: str) -> str:
        return (
            "Analyze this image and return JSON only. "
            "Use this schema exactly: "
            '{"description": string, "detected_text_blocks": [{"text": string}], '
            '"observations": [string], "warnings": [string]}. '
            "Focus on faithful visible details and readable text. "
            "Do not invent unreadable text. "
            f"Context: {purpose}"
        )

    def _get_active_model_config(self) -> Dict[str, Any]:
        config = getattr(self._settings, "active_model_config", None)
        if isinstance(config, dict):
            return config

        private_config = getattr(self._settings, "_active_model_config", None)
        if isinstance(private_config, dict):
            return private_config

        return {}

    def _model_supports_vision(self, config: Dict[str, Any]) -> bool:
        raw_capabilities = config.get("capabilities")
        capabilities: list[str] = []
        if isinstance(raw_capabilities, str):
            capabilities = [
                part.strip().lower()
                for part in raw_capabilities.split(",")
                if part.strip()
            ]
        elif isinstance(raw_capabilities, list):
            capabilities = [
                str(part).strip().lower()
                for part in raw_capabilities
                if str(part).strip()
            ]

        return "vision" in capabilities

    def _build_missing_model_hint(
        self,
        *,
        provider: str,
        active_model_name: str,
        active_model_config: Dict[str, Any],
    ) -> str:
        base_hint = (
            "Set DOCUMENT_VISION_MODEL to an Ollama vision-capable model, "
            "including cloud-served models such as qwen3.5:397b-cloud."
        )
        if provider and provider != "ollama":
            return (
                f"{base_hint} The document vision helper only uses Ollama models, "
                f"but LLM_PROVIDER is '{provider}'."
            )

        if active_model_name:
            if not active_model_config:
                return (
                    f"{base_hint} Active Ollama model '{active_model_name}' does not "
                    "have capability metadata, so Monk will not assume it supports vision."
                )
            return (
                f"{base_hint} Active Ollama model '{active_model_name}' does not "
                "advertise vision."
            )

        return base_hint

    def _parse_json_payload(self, raw_response: str) -> Optional[Dict[str, Any]]:
        text = str(raw_response or "").strip()
        if not text:
            return None

        candidates = [text]
        extracted = self._extract_bracketed_json(text)
        if extracted and extracted not in candidates:
            candidates.append(extracted)

        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value

        return None

    def _extract_bracketed_json(self, text: str) -> Optional[str]:
        for opener, closer in (("{", "}"), ("[", "]")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end != -1 and end > start:
                return text[start : end + 1]
        return None

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        description = str(
            payload.get("description") or payload.get("summary") or ""
        ).strip()
        detected_text_blocks = self._normalize_text_blocks(
            payload.get("detected_text_blocks") or payload.get("detected_text")
        )
        observations = self._normalize_strings(payload.get("observations"))
        warnings = self._normalize_strings(payload.get("warnings"))

        return {
            "description": description,
            "detected_text_blocks": detected_text_blocks,
            "observations": observations,
            "warnings": warnings,
        }

    def _normalize_text_blocks(self, value: Any) -> list[Dict[str, Any]]:
        blocks: list[Dict[str, Any]] = []
        if isinstance(value, str):
            text = value.strip()
            if text:
                blocks.append({"text": text})
            return blocks
        if not isinstance(value, list):
            return blocks

        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    blocks.append({"text": text})
                continue
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("value") or "").strip()
            if not text:
                continue
            block: Dict[str, Any] = {"text": text}
            confidence = item.get("confidence")
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                block["confidence"] = float(confidence)
            blocks.append(block)

        return blocks

    def _normalize_strings(self, value: Any) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if not isinstance(value, list):
            return []

        items: list[str] = []
        for entry in value:
            text = str(entry or "").strip()
            if text:
                items.append(text)
        return items
