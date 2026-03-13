from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from protocol_monk.exceptions.tools import ToolError
from protocol_monk.tools.base import BaseTool
from protocol_monk.tools.document_operations.vision_helper_service import VisionHelperService
from protocol_monk.tools.output_contract import build_range_pagination, build_tool_output


class ReadPdfTool(BaseTool):
    """Read PDFs with text-first extraction and vision fallback for sparse pages."""

    MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
    DEFAULT_PAGE_LIMIT = 3
    SPARSE_TEXT_THRESHOLD = 30

    def __init__(
        self,
        settings,
        vision_helper: Optional[VisionHelperService] = None,
    ):
        super().__init__(settings)
        self._vision_helper = vision_helper

    @property
    def name(self) -> str:
        return "read_pdf"

    @property
    def description(self) -> str:
        return (
            "Read PDF pages as structured text blocks. "
            "Uses a vision helper for scanned or sparse pages."
        )

    @property
    def parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "PDF path"},
                "page_start": {
                    "type": "integer",
                    "description": "Starting page number (1-based, inclusive)",
                    "default": 1,
                },
                "page_limit": {
                    "type": "integer",
                    "description": "Maximum number of pages to return",
                    "default": self.DEFAULT_PAGE_LIMIT,
                },
            },
            "required": ["filepath"],
        }

    async def run(self, **kwargs) -> Dict[str, Any]:
        filepath = kwargs.get("filepath")
        if not filepath:
            raise ToolError(
                "Missing required parameter: 'filepath'",
                user_hint="Please provide a PDF filepath.",
            )

        page_start = int(kwargs.get("page_start", 1) or 1)
        page_limit = int(
            kwargs.get("page_limit", self.DEFAULT_PAGE_LIMIT) or self.DEFAULT_PAGE_LIMIT
        )
        if page_start < 1:
            raise ToolError(
                "page_start must be >= 1",
                user_hint="PDF page_start must be 1 or greater.",
            )
        if page_limit < 1:
            raise ToolError(
                "page_limit must be >= 1",
                user_hint="PDF page_limit must be 1 or greater.",
            )

        full_path = self.path_validator.validate_path(filepath, must_exist=False)
        self._validate_file(full_path)

        try:
            import fitz
        except Exception as exc:  # pragma: no cover
            raise ToolError(
                "PyMuPDF is not installed.",
                user_hint="Install PyMuPDF to read PDF files.",
                details={"error": str(exc)},
            )

        document = fitz.open(full_path)
        try:
            page_count = len(document)
            if page_count == 0:
                return build_tool_output(
                    result_type="pdf_read",
                    summary=f"Read 0 pages from {full_path.name}.",
                    data={
                        "filepath": str(full_path),
                        "page_count": 0,
                        "document_metadata": {},
                        "used_vision_helper": False,
                        "pages": [],
                    },
                    pagination=None,
                )

            if page_start > page_count:
                raise ToolError(
                    f"Requested page_start {page_start} exceeds total pages {page_count}.",
                    user_hint=f"Requested page_start {page_start} is beyond the PDF length.",
                    details={"page_start": page_start, "page_count": page_count},
                )

            actual_end = min(page_count, page_start + page_limit - 1)
            pages: List[Dict[str, Any]] = []
            used_vision_helper = False

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_root = Path(temp_dir)
                for page_number in range(page_start, actual_end + 1):
                    page = document.load_page(page_number - 1)
                    native_blocks = self._extract_text_blocks(page)
                    native_text = " ".join(block["text"] for block in native_blocks).strip()

                    if not native_blocks:
                        page_record = await self._analyze_page_with_vision(
                            page,
                            page_number=page_number,
                            temp_root=temp_root,
                            fallback_warning="No native text layer detected.",
                        )
                        if page_record["extraction_method"] == "vision_helper":
                            used_vision_helper = True
                        pages.append(page_record)
                        continue

                    if self._is_sparse_text(native_text):
                        page_record = await self._analyze_page_with_vision(
                            page,
                            page_number=page_number,
                            temp_root=temp_root,
                            fallback_warning="Native text was sparse.",
                            native_blocks=native_blocks,
                        )
                        if page_record["extraction_method"] in {"vision_helper", "mixed"}:
                            used_vision_helper = True
                        pages.append(page_record)
                        continue

                    pages.append(
                        {
                            "page_number": page_number,
                            "extraction_method": "text_layer",
                            "text_blocks": native_blocks,
                            "warnings": [],
                        }
                    )

            pagination = build_range_pagination(
                mode="page_range",
                total_items=page_count,
                returned_start=page_start,
                returned_end=actual_end,
                page_size=max(1, page_limit),
                start_key="page_start",
                end_key="page_end",
                total_key="page_count",
            )
            summary = f"Read pages {page_start}-{actual_end} from {full_path.name}."
            return build_tool_output(
                result_type="pdf_read",
                summary=summary,
                data={
                    "filepath": str(full_path),
                    "page_count": page_count,
                    "document_metadata": self._extract_document_metadata(document.metadata),
                    "used_vision_helper": used_vision_helper,
                    "pages": pages,
                },
                pagination=pagination,
            )
        finally:
            document.close()

    def _validate_file(self, path: Path) -> None:
        try:
            stat = path.stat()
        except FileNotFoundError:
            raise ToolError(
                f"PDF not found: {path.name}",
                user_hint=f"The file '{path.name}' does not exist.",
                details={"path": str(path)},
            )
        except PermissionError:
            raise ToolError(
                f"Permission denied: {path.name}",
                user_hint=f"No permission to read '{path.name}'.",
                details={"path": str(path)},
            )

        if path.suffix.lower() != ".pdf":
            raise ToolError(
                "Unsupported file type for read_pdf.",
                user_hint="read_pdf only supports .pdf files.",
                details={"path": str(path), "suffix": path.suffix},
            )
        if stat.st_size > self.MAX_FILE_SIZE_BYTES:
            raise ToolError(
                "PDF is too large to load in one call.",
                user_hint="PDF is too large for the document reader.",
                details={
                    "path": str(path),
                    "actual_size_bytes": stat.st_size,
                    "max_size_bytes": self.MAX_FILE_SIZE_BYTES,
                },
            )

    def _extract_text_blocks(self, page: Any) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        for index, block in enumerate(page.get_text("blocks"), start=1):
            text = str(block[4] or "").strip()
            if not text:
                continue
            blocks.append({"block_number": index, "text": text})
        return blocks

    def _is_sparse_text(self, text: str) -> bool:
        compact = "".join(ch for ch in str(text or "") if not ch.isspace())
        return len(compact) < self.SPARSE_TEXT_THRESHOLD

    async def _analyze_page_with_vision(
        self,
        page: Any,
        *,
        page_number: int,
        temp_root: Path,
        fallback_warning: str,
        native_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        warnings = [fallback_warning]
        rendered_path = temp_root / f"page_{page_number}.png"
        pixmap = page.get_pixmap(alpha=False)
        pixmap.save(rendered_path)

        try:
            helper_result = await self._vision.analyze_image(
                rendered_path,
                purpose=(
                    "Analyze this rasterized PDF page. Focus on readable text and "
                    "salient structure."
                ),
            )
        except ToolError as exc:
            warnings.append(exc.user_hint)
            return {
                "page_number": page_number,
                "extraction_method": "text_layer" if native_blocks else "unavailable",
                "text_blocks": native_blocks or [],
                "warnings": warnings,
            }

        vision_blocks = [
            {"block_number": index + 1, "text": block["text"]}
            for index, block in enumerate(helper_result["detected_text_blocks"])
            if block.get("text")
        ]
        warnings.extend(helper_result["warnings"])

        if native_blocks:
            combined_blocks = list(native_blocks)
            offset = len(combined_blocks)
            for index, block in enumerate(vision_blocks, start=1):
                combined_blocks.append(
                    {"block_number": offset + index, "text": block["text"]}
                )
            return {
                "page_number": page_number,
                "extraction_method": "mixed",
                "text_blocks": combined_blocks,
                "warnings": warnings,
            }

        return {
            "page_number": page_number,
            "extraction_method": "vision_helper",
            "text_blocks": vision_blocks,
            "warnings": warnings,
        }

    def _extract_document_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        interesting_keys = (
            "title",
            "author",
            "subject",
            "keywords",
            "creator",
            "producer",
            "creationDate",
            "modDate",
        )
        return {
            key: str(metadata.get(key))
            for key in interesting_keys
            if metadata.get(key) not in (None, "")
        }

    @property
    def _vision(self) -> VisionHelperService:
        if self._vision_helper is None:
            self._vision_helper = VisionHelperService(self.settings)
        return self._vision_helper
