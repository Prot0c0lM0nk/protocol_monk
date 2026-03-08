from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class SkillReference:
    path: Path
    content: str


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    source_dir: Path
    skill_file: Path
    body: str
    references: List[SkillReference]


class SkillRuntime:
    """Discover repo-local skills and track which ones are active this session."""

    def __init__(self, skills_root: Path):
        self._skills_root = Path(skills_root)
        self._catalog: Dict[str, SkillDefinition] = {}
        self._catalog_by_lower_name: Dict[str, SkillDefinition] = {}
        self._active_skill_names: set[str] = set()

    @property
    def skills_root(self) -> Path:
        return self._skills_root

    def refresh_catalog(self) -> List[str]:
        warnings: List[str] = []
        catalog: Dict[str, SkillDefinition] = {}
        catalog_by_lower_name: Dict[str, SkillDefinition] = {}

        if self._skills_root.exists() and self._skills_root.is_dir():
            for child in sorted(self._skills_root.iterdir(), key=lambda item: item.name.lower()):
                if not child.is_dir():
                    continue
                skill_file = child / "SKILL.md"
                if not skill_file.is_file():
                    continue

                parsed = self._load_skill_definition(skill_file)
                if parsed is None:
                    warnings.append(
                        f"Skipped invalid skill at '{child}': missing valid frontmatter."
                    )
                    continue

                lower_name = parsed.name.lower()
                if lower_name in catalog_by_lower_name:
                    warnings.append(
                        f"Skipped duplicate skill name '{parsed.name}' from '{child}'."
                    )
                    continue

                catalog[parsed.name] = parsed
                catalog_by_lower_name[lower_name] = parsed

        removed_active = sorted(
            name for name in self._active_skill_names if name not in catalog
        )
        for name in removed_active:
            self._active_skill_names.discard(name)
            warnings.append(
                f"Active skill '{name}' is no longer available and was deactivated."
            )

        self._catalog = catalog
        self._catalog_by_lower_name = catalog_by_lower_name
        return warnings

    def list_skills(self) -> tuple[List[SkillDefinition], List[str]]:
        warnings = self.refresh_catalog()
        skills = sorted(self._catalog.values(), key=lambda skill: skill.name.lower())
        return skills, warnings

    def active_skill_names(self) -> List[str]:
        return sorted(self._active_skill_names, key=str.lower)

    def activate(self, requested_name: str) -> tuple[bool, str, List[str]]:
        warnings = self.refresh_catalog()
        skill = self._resolve_skill(requested_name)
        if skill is None:
            return False, f"Skill not found: {requested_name}", warnings
        if skill.name in self._active_skill_names:
            return True, f"Skill already active: {skill.name}", warnings
        self._active_skill_names.add(skill.name)
        return True, f"Activated skill: {skill.name}", warnings

    def deactivate(self, requested_name: str) -> tuple[bool, str, List[str]]:
        warnings = self.refresh_catalog()
        skill = self._resolve_skill(requested_name)
        if skill is None:
            return False, f"Skill not found: {requested_name}", warnings
        if skill.name not in self._active_skill_names:
            return True, f"Skill already inactive: {skill.name}", warnings
        self._active_skill_names.discard(skill.name)
        return True, f"Deactivated skill: {skill.name}", warnings

    def build_active_skill_system_message(self) -> tuple[str | None, List[str]]:
        warnings = self.refresh_catalog()
        active_names = self.active_skill_names()
        if not active_names:
            return None, warnings

        sections = [
            (
                "Session skill instructions.\n"
                "Use the following active skills only when they are relevant to the "
                "user's request. Do not claim to have reviewed references or assets "
                "unless you actually read them."
            )
        ]
        for name in active_names:
            skill = self._catalog.get(name)
            if skill is None:
                continue
            body = skill.body.strip()
            skill_sections = [
                "\n".join(
                    [
                        f"## Skill: {skill.name}",
                        f"Description: {skill.description}",
                        f"Source directory: {skill.source_dir}",
                        "",
                        body,
                    ]
                ).strip()
            ]
            for reference in skill.references:
                relative_path = reference.path.relative_to(skill.source_dir)
                skill_sections.append(
                    "\n".join(
                        [
                            f"### Reference: {relative_path}",
                            reference.content,
                        ]
                    ).strip()
                )
            sections.append("\n\n".join(skill_sections).strip())
        return "\n\n".join(section for section in sections if section).strip(), warnings

    def _resolve_skill(self, requested_name: str) -> SkillDefinition | None:
        normalized = str(requested_name or "").strip().lower()
        if not normalized:
            return None
        return self._catalog_by_lower_name.get(normalized)

    def _load_skill_definition(self, skill_file: Path) -> SkillDefinition | None:
        try:
            text = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        frontmatter, body = self._split_frontmatter(text)
        if frontmatter is None:
            return None

        name = self._normalize_frontmatter_value(frontmatter.get("name", ""))
        description = self._normalize_frontmatter_value(
            frontmatter.get("description", "")
        )
        if not name or not description:
            return None

        return SkillDefinition(
            name=name,
            description=description,
            source_dir=skill_file.parent,
            skill_file=skill_file,
            body=body.strip(),
            references=self._load_references(skill_file.parent),
        )

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[Dict[str, str] | None, str]:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return None, text

        closing_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                closing_index = index
                break
        if closing_index is None:
            return None, text

        frontmatter: Dict[str, str] = {}
        for line in lines[1:closing_index]:
            stripped = line.strip()
            if not stripped or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            frontmatter[key.strip()] = value.strip()

        body = "\n".join(lines[closing_index + 1 :])
        return frontmatter, body

    @staticmethod
    def _normalize_frontmatter_value(value: str) -> str:
        text = str(value or "").strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            return text[1:-1].strip()
        return text

    @staticmethod
    def _load_references(skill_dir: Path) -> List[SkillReference]:
        references_dir = skill_dir / "references"
        if not references_dir.is_dir():
            return []

        references: List[SkillReference] = []
        for ref_path in sorted(references_dir.rglob("*.md")):
            if not ref_path.is_file():
                continue
            try:
                content = ref_path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError):
                continue
            if not content:
                continue
            references.append(SkillReference(path=ref_path, content=content))
        return references
