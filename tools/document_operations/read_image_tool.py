from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.document_operations.vision_helper_service import VisionHelperService
from protocol_monk.tools.output_contract import build_tool_output


class ReadImageTool(BaseTool):
    """Analyze image files with an Ollama-backed vision helper model."""

    MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

    def __init__(
        self,
        settings,
        vision_helper: Optional[VisionHelperService] = None,
    ):
        super().__init__(settings)
        self._vision_helper = vision_helper

    @property
    def name(self) -> str:
        return "read_image"

    @property
    def description(self) -> str:
        return "Analyze an image file into structured description and detected text."

    @property
    def parameter_schema(self) -> Dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Image path"},
            },
            "required": ["filepath"],
        }

    async def run(self, **kwargs) -> Dict[str, object]:
        filepath = kwargs.get("filepath")
        if not filepath:
            raise ToolError(
                "Missing required parameter: 'filepath'",
                user_hint="Please provide an image filepath.",
            )

        full_path = self.path_validator.validate_path(filepath, must_exist=False)
        self._validate_file(full_path)

        try:
            from PIL import Image
        except Exception as exc:  # pragma: no cover
            raise ToolError(
                "Pillow is not installed.",
                user_hint="Install Pillow to read image files.",
                details={"error": str(exc)},
            )

        try:
            with Image.open(full_path) as image:
                width, height = image.size
                mode = image.mode
                image_format = image.format or full_path.suffix.lstrip(".").upper()
        except Exception as exc:
            raise ToolError(
                f"Failed to open image: {full_path.name}",
                user_hint=f"Could not read image '{full_path.name}'.",
                details={"path": str(full_path), "error": str(exc)},
            )

        helper_result = await self._vision.analyze_image(
            full_path,
            purpose="Describe this image faithfully and transcribe visible text.",
        )

        summary = f"Analyzed image {full_path.name} ({width}x{height})."
        return build_tool_output(
            result_type="image_read",
            summary=summary,
            data={
                "filepath": str(full_path),
                "format": str(image_format).lower(),
                "width": width,
                "height": height,
                "mode": mode,
                "analysis_method": "vision_helper",
                "description": helper_result["description"],
                "detected_text_blocks": helper_result["detected_text_blocks"],
                "observations": helper_result["observations"],
                "warnings": helper_result["warnings"],
            },
            pagination=None,
        )

    def _validate_file(self, path: Path) -> None:
        try:
            stat = path.stat()
        except FileNotFoundError:
            raise ToolError(
                f"Image not found: {path.name}",
                user_hint=f"The file '{path.name}' does not exist.",
                details={"path": str(path)},
            )
        except PermissionError:
            raise ToolError(
                f"Permission denied: {path.name}",
                user_hint=f"No permission to read '{path.name}'.",
                details={"path": str(path)},
            )

        supported = {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".bmp",
            ".gif",
            ".tiff",
            ".tif",
        }
        if path.suffix.lower() not in supported:
            raise ToolError(
                f"Unsupported image format: {path.suffix or 'unknown'}",
                user_hint=(
                    "Supported image formats are PNG, JPG, WEBP, BMP, GIF, and TIFF."
                ),
                details={"path": str(path), "suffix": path.suffix},
            )
        if stat.st_size > self.MAX_FILE_SIZE_BYTES:
            raise ToolError(
                "Image is too large to load in one call.",
                user_hint="Image is too large for the document reader.",
                details={
                    "path": str(path),
                    "actual_size_bytes": stat.st_size,
                    "max_size_bytes": self.MAX_FILE_SIZE_BYTES,
                },
            )

    @property
    def _vision(self) -> VisionHelperService:
        if self._vision_helper is None:
            self._vision_helper = VisionHelperService(self.settings)
        return self._vision_helper
