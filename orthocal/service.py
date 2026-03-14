"""Orthocal workspace bundle generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request
import uuid

DEFAULT_ORTHOCAL_BASE_URL = "https://orthocal.info"
DEFAULT_ORTHOCAL_CALENDAR = "gregorian"


class OrthocalRefreshError(RuntimeError):
    """Raised when Orthocal bundle generation fails."""


@dataclass(frozen=True)
class OrthocalBundleFile:
    index: int
    title: str
    path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "title": self.title,
            "path": str(self.path),
        }


@dataclass(frozen=True)
class OrthocalRefreshResult:
    requested_date: str
    calendar: str
    source_url: str
    fetched_at: str
    summary_title: str
    feast_level_description: str
    fast_level_desc: str
    fast_exception_desc: str
    tone: int | None
    titles_count: int
    feasts_count: int
    saints_count: int
    readings_count: int
    stories_count: int
    bundle_dir: Path
    day_json_path: Path
    summary_md_path: Path
    reading_files: list[OrthocalBundleFile]
    story_files: list[OrthocalBundleFile]

    def summary_message(self) -> str:
        return (
            f"Orthocal refreshed for {self.requested_date}: {self.summary_title} "
            f"({self.readings_count} readings, {self.stories_count} stories)."
        )

    def to_command_data(self) -> dict[str, Any]:
        return {
            "requested_date": self.requested_date,
            "calendar": self.calendar,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at,
            "summary_title": self.summary_title,
            "feast_level_description": self.feast_level_description,
            "fast_level_desc": self.fast_level_desc,
            "fast_exception_desc": self.fast_exception_desc,
            "tone": self.tone,
            "titles_count": self.titles_count,
            "feasts_count": self.feasts_count,
            "saints_count": self.saints_count,
            "readings_count": self.readings_count,
            "stories_count": self.stories_count,
            "bundle_dir": str(self.bundle_dir),
            "day_json_path": str(self.day_json_path),
            "summary_md_path": str(self.summary_md_path),
            "reading_files": [item.to_dict() for item in self.reading_files],
            "story_files": [item.to_dict() for item in self.story_files],
        }


class _StoryHtmlConverter(HTMLParser):
    """Convert lightweight Orthocal story HTML to readable markdown-ish text."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._list_stack: list[dict[str, int]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _ = attrs
        if tag in {"p", "div", "section", "article"}:
            self._ensure_block_break()
        elif tag == "br":
            self._chunks.append("\n")
        elif tag == "ul":
            self._ensure_block_break()
            self._list_stack.append({"type": "ul", "index": 0})
        elif tag == "ol":
            self._ensure_block_break()
            self._list_stack.append({"type": "ol", "index": 0})
        elif tag == "li":
            self._chunks.append("\n")
            if self._list_stack:
                marker = self._list_stack[-1]
                if marker["type"] == "ol":
                    marker["index"] += 1
                    self._chunks.append(f"{marker['index']}. ")
                else:
                    self._chunks.append("- ")
            else:
                self._chunks.append("- ")
        elif tag in {"em", "i"}:
            self._chunks.append("*")
        elif tag in {"strong", "b"}:
            self._chunks.append("**")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "section", "article"}:
            self._ensure_block_break()
        elif tag in {"ul", "ol"}:
            if self._list_stack:
                self._list_stack.pop()
            self._ensure_block_break()
        elif tag == "li":
            self._chunks.append("\n")
        elif tag in {"em", "i"}:
            self._chunks.append("*")
        elif tag in {"strong", "b"}:
            self._chunks.append("**")

    def handle_data(self, data: str) -> None:
        if data:
            self._chunks.append(unescape(data))

    def render(self) -> str:
        text = "".join(self._chunks).replace("\xa0", " ")
        return _normalize_markdown_text(text)

    def _ensure_block_break(self) -> None:
        if not self._chunks:
            return
        current = "".join(self._chunks)
        if current.endswith("\n\n"):
            return
        if current.endswith("\n"):
            self._chunks.append("\n")
            return
        self._chunks.append("\n\n")


class OrthocalWorkspaceService:
    """Fetch Orthocal data and refresh the local current bundle."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        base_url: str = DEFAULT_ORTHOCAL_BASE_URL,
        calendar: str = DEFAULT_ORTHOCAL_CALENDAR,
        fetcher: Callable[[str], dict[str, Any]] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root).expanduser().resolve(strict=False)
        self._base_url = str(base_url or DEFAULT_ORTHOCAL_BASE_URL).rstrip("/")
        self._calendar = str(calendar or DEFAULT_ORTHOCAL_CALENDAR).strip().lower()
        self._fetcher = fetcher or self._fetch_json
        self._now_provider = now_provider or (lambda: datetime.now().astimezone())

    def refresh_bundle(self, requested_date: str | None = None) -> OrthocalRefreshResult:
        current_dt = self._resolve_now()
        target_date = (
            date.fromisoformat(requested_date)
            if requested_date
            else current_dt.date()
        )
        fetched_at = current_dt.isoformat()
        source_url = self._build_day_url(target_date)
        parent_dir = self._workspace_root / ".protocol_monk" / "orthocal"
        current_dir = parent_dir / "current"
        staging_dir = parent_dir / f".current.tmp-{uuid.uuid4().hex}"

        try:
            payload = self._fetcher(source_url)
            normalized_day = self._normalize_day_payload(payload)
            parent_dir.mkdir(parents=True, exist_ok=True)
            manifest = self._write_bundle_files(
                staging_dir=staging_dir,
                normalized_day=normalized_day,
                requested_date=target_date.isoformat(),
                fetched_at=fetched_at,
                source_url=source_url,
            )
            self._promote_bundle(staging_dir=staging_dir, current_dir=current_dir)
        except OrthocalRefreshError:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
        except ValueError as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise OrthocalRefreshError("Invalid Orthocal date. Use YYYY-MM-DD.") from exc
        except Exception as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise OrthocalRefreshError(f"Orthocal refresh failed: {exc}") from exc

        return OrthocalRefreshResult(
            requested_date=target_date.isoformat(),
            calendar=self._calendar,
            source_url=source_url,
            fetched_at=fetched_at,
            summary_title=str(normalized_day.get("summary_title", "") or "Orthocal Day"),
            feast_level_description=str(
                normalized_day.get("feast_level_description", "") or ""
            ),
            fast_level_desc=str(normalized_day.get("fast_level_desc", "") or ""),
            fast_exception_desc=str(
                normalized_day.get("fast_exception_desc", "") or ""
            ),
            tone=_coerce_int(normalized_day.get("tone")),
            titles_count=len(normalized_day.get("titles", [])),
            feasts_count=len(normalized_day.get("feasts", [])),
            saints_count=len(normalized_day.get("saints", [])),
            readings_count=len(manifest["reading_files"]),
            stories_count=len(manifest["story_files"]),
            bundle_dir=current_dir,
            day_json_path=current_dir / "day.json",
            summary_md_path=current_dir / "summary.md",
            reading_files=[
                OrthocalBundleFile(
                    index=item["index"],
                    title=item["title"],
                    path=current_dir / "readings" / item["filename"],
                )
                for item in manifest["reading_files"]
            ],
            story_files=[
                OrthocalBundleFile(
                    index=item["index"],
                    title=item["title"],
                    path=current_dir / "stories" / item["filename"],
                )
                for item in manifest["story_files"]
            ],
        )

    def _resolve_now(self) -> datetime:
        current = self._now_provider()
        if not isinstance(current, datetime):
            raise OrthocalRefreshError("Orthocal clock provider returned an invalid value.")
        return current.astimezone()

    def _build_day_url(self, target_date: date) -> str:
        return (
            f"{self._base_url}/api/{self._calendar}/"
            f"{target_date.year}/{target_date.month}/{target_date.day}/"
        )

    def _fetch_json(self, url: str) -> dict[str, Any]:
        request = urllib_request.Request(
            url,
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib_request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OrthocalRefreshError(
                f"Orthocal request failed ({exc.code}): {body}"
            ) from exc
        except urllib_error.URLError as exc:
            raise OrthocalRefreshError(
                f"Orthocal request failed: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise OrthocalRefreshError(
                f"Orthocal response is not valid JSON: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise OrthocalRefreshError("Orthocal response was not a JSON object.")
        return payload

    def _normalize_day_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = dict(payload)
        for key in (
            "titles",
            "feasts",
            "saints",
            "service_notes",
            "abbreviated_reading_indices",
            "readings",
            "stories",
        ):
            normalized[key] = list(payload.get(key) or [])

        readings: list[dict[str, Any]] = []
        for reading in normalized["readings"]:
            if not isinstance(reading, dict):
                continue
            reading_copy = dict(reading)
            reading_copy["passage"] = list(reading.get("passage") or [])
            readings.append(reading_copy)
        normalized["readings"] = readings

        stories: list[dict[str, Any]] = []
        for story in normalized["stories"]:
            if not isinstance(story, dict):
                continue
            stories.append(dict(story))
        normalized["stories"] = stories

        return normalized

    def _write_bundle_files(
        self,
        *,
        staging_dir: Path,
        normalized_day: dict[str, Any],
        requested_date: str,
        fetched_at: str,
        source_url: str,
    ) -> dict[str, list[dict[str, Any]]]:
        readings_dir = staging_dir / "readings"
        stories_dir = staging_dir / "stories"
        staging_dir.mkdir(parents=True, exist_ok=False)
        readings_dir.mkdir()
        stories_dir.mkdir()

        reading_files = self._write_reading_files(
            readings_dir,
            normalized_day.get("readings", []),
        )
        story_files = self._write_story_files(
            stories_dir,
            normalized_day.get("stories", []),
        )

        day_payload = {
            "requested_date": requested_date,
            "calendar": self._calendar,
            "source_url": source_url,
            "fetched_at": fetched_at,
            "day": normalized_day,
        }
        (staging_dir / "day.json").write_text(
            json.dumps(day_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (staging_dir / "summary.md").write_text(
            self._build_summary_markdown(
                normalized_day=normalized_day,
                requested_date=requested_date,
                fetched_at=fetched_at,
                source_url=source_url,
                reading_files=reading_files,
                story_files=story_files,
            ),
            encoding="utf-8",
        )

        return {
            "reading_files": reading_files,
            "story_files": story_files,
        }

    def _write_reading_files(
        self,
        readings_dir: Path,
        readings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        manifest: list[dict[str, Any]] = []
        for index, reading in enumerate(readings, start=1):
            title = str(
                reading.get("display")
                or reading.get("description")
                or reading.get("short_display")
                or f"Reading {index}"
            )
            filename = f"{index:02d}-{_slugify(title)}.md"
            content = self._build_reading_markdown(title=title, reading=reading)
            (readings_dir / filename).write_text(content, encoding="utf-8")
            manifest.append(
                {
                    "index": index,
                    "title": title,
                    "filename": filename,
                }
            )
        return manifest

    def _write_story_files(
        self,
        stories_dir: Path,
        stories: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        manifest: list[dict[str, Any]] = []
        for index, story in enumerate(stories, start=1):
            title = str(story.get("title") or f"Story {index}")
            filename = f"{index:02d}-{_slugify(title)}.md"
            content = self._build_story_markdown(title=title, story=story)
            (stories_dir / filename).write_text(content, encoding="utf-8")
            manifest.append(
                {
                    "index": index,
                    "title": title,
                    "filename": filename,
                }
            )
        return manifest

    def _build_summary_markdown(
        self,
        *,
        normalized_day: dict[str, Any],
        requested_date: str,
        fetched_at: str,
        source_url: str,
        reading_files: list[dict[str, Any]],
        story_files: list[dict[str, Any]],
    ) -> str:
        lines = [
            f"# {str(normalized_day.get('summary_title') or 'Orthocal Day')}",
            "",
            f"- Requested date: {requested_date}",
            f"- Calendar: {self._calendar}",
            f"- Source URL: `{source_url}`",
            f"- Fetched at: {fetched_at}",
            f"- Weekday: {normalized_day.get('weekday', '')}",
            f"- Tone: {normalized_day.get('tone', '')}",
            f"- Feast level: {normalized_day.get('feast_level_description', '')}",
            "- Fast: "
            f"{normalized_day.get('fast_level_desc', '')}"
            + (
                f"; {normalized_day.get('fast_exception_desc', '')}"
                if normalized_day.get("fast_exception_desc")
                else ""
            ),
            "",
        ]

        lines.extend(self._render_index_section("Titles", normalized_day.get("titles", [])))
        lines.extend(self._render_index_section("Feasts", normalized_day.get("feasts", [])))
        lines.extend(self._render_index_section("Saints", normalized_day.get("saints", [])))
        lines.extend(
            self._render_index_section(
                "Service Notes",
                normalized_day.get("service_notes", []),
            )
        )
        lines.extend(self._render_file_section("Readings", "readings", reading_files))
        lines.extend(self._render_file_section("Stories", "stories", story_files))
        return "\n".join(lines).strip() + "\n"

    def _render_index_section(self, title: str, values: list[Any]) -> list[str]:
        lines = [f"## {title}"]
        if not values:
            lines.extend(["", "_None._", ""])
            return lines
        lines.append("")
        for index, value in enumerate(values, start=1):
            lines.append(f"{index}. {value}")
        lines.append("")
        return lines

    def _render_file_section(
        self,
        title: str,
        folder_name: str,
        items: list[dict[str, Any]],
    ) -> list[str]:
        lines = [f"## {title}", ""]
        if not items:
            lines.extend(["_None._", ""])
            return lines
        for item in items:
            lines.append(
                f"{item['index']}. `{folder_name}/{item['filename']}` - {item['title']}"
            )
        lines.append("")
        return lines

    def _build_reading_markdown(self, *, title: str, reading: dict[str, Any]) -> str:
        lines = [f"# {title}", ""]
        metadata_pairs = [
            ("Source", reading.get("source")),
            ("Book", reading.get("book")),
            ("Description", reading.get("description")),
            ("Reference", reading.get("display")),
            ("Short Reference", reading.get("short_display")),
        ]
        for label, value in metadata_pairs:
            if value:
                lines.append(f"- {label}: {value}")
        lines.extend(
            [
                "",
                "## Passage",
                "",
                _render_passage_text(reading.get("passage") or []),
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def _build_story_markdown(self, *, title: str, story: dict[str, Any]) -> str:
        converter = _StoryHtmlConverter()
        converter.feed(str(story.get("story") or ""))
        converter.close()
        body = converter.render() or "_Story text was not provided by Orthocal._"
        return "\n".join([f"# {title}", "", body]).strip() + "\n"

    def _promote_bundle(self, *, staging_dir: Path, current_dir: Path) -> None:
        backup_dir = current_dir.parent / f".current.backup-{uuid.uuid4().hex}"
        if current_dir.exists() and not current_dir.is_dir():
            raise OrthocalRefreshError("Orthocal current path is not a directory.")
        try:
            if current_dir.exists():
                os.replace(current_dir, backup_dir)
            os.replace(staging_dir, current_dir)
        except Exception as exc:
            if backup_dir.exists() and not current_dir.exists():
                os.replace(backup_dir, current_dir)
            raise OrthocalRefreshError(
                f"Failed to replace Orthocal current bundle: {exc}"
            ) from exc
        else:
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)


def _render_passage_text(passage: list[dict[str, Any]]) -> str:
    if not passage:
        return "_Passage text was not provided by Orthocal._"

    paragraphs: list[str] = []
    current: list[str] = []
    for verse in passage:
        if not isinstance(verse, dict):
            continue
        book = str(verse.get("book") or "").strip()
        chapter = verse.get("chapter")
        verse_number = verse.get("verse")
        content = str(verse.get("content") or "").strip()
        prefix = " ".join(
            part
            for part in [
                book,
                f"{chapter}:{verse_number}"
                if chapter is not None and verse_number is not None
                else "",
            ]
            if part
        ).strip()
        segment = f"{prefix} {content}".strip()
        if verse.get("paragraph_start") and current:
            paragraphs.append(" ".join(current).strip())
            current = [segment]
        else:
            current.append(segment)
    if current:
        paragraphs.append(" ".join(current).strip())
    return (
        "\n\n".join(item for item in paragraphs if item).strip()
        or "_Passage text was not provided by Orthocal._"
    )


def _normalize_markdown_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    normalized: list[str] = []
    blank_run = 0
    for line in lines:
        if not line:
            blank_run += 1
            if blank_run <= 1:
                normalized.append("")
            continue
        blank_run = 0
        normalized.append(line)
    return "\n".join(normalized).strip()


def _slugify(value: str) -> str:
    normalized = unescape(str(value or "")).strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or "entry"


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
