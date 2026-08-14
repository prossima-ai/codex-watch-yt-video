"""Hermetic package-contract model used only by the discovery/install tests.

It validates repository artifacts and disposable filesystem fixtures. It does not
query Codex Desktop, mutate a personal skill directory, or prove host behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat


@dataclass(frozen=True)
class PackageValidation:
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class DiscoveredSkill:
    scope: str
    name: str
    skill_root: Path
    resolved_skill_root: Path


@dataclass(frozen=True)
class PersonalInstallation:
    status: str
    target: Path
    source: Path


@dataclass(frozen=True)
class ManualInstallationPlan:
    status: str
    target: Path
    source: Path
    requires_explicit_approval: bool
    exact_mutation: str | None


@dataclass(frozen=True)
class InvocationDecision:
    route: str
    grants_authority: bool


@dataclass(frozen=True)
class TaskInventoryEntry:
    scope: str
    name: str
    skill_root: Path
    metadata: str


@dataclass(frozen=True)
class TaskInventory:
    entries: tuple[TaskInventoryEntry, ...]


@dataclass(frozen=True)
class PathIsolation:
    status: str
    selected_path: Path | None


def discover_repository_skills(
    task_directory: Path, repository_root: Path
) -> tuple[DiscoveredSkill, ...]:
    task_path = Path(os.path.abspath(task_directory))
    root_path = Path(os.path.abspath(repository_root))
    try:
        task_path.relative_to(root_path)
    except ValueError:
        return ()

    candidates: list[DiscoveredSkill] = []
    current = task_path
    while True:
        candidates.extend(_discover_skills_at(current, "repository"))
        if current == root_path:
            break
        current = current.parent
    return tuple(candidates)


def discover_personal_skills(personal_home: Path) -> tuple[DiscoveredSkill, ...]:
    home_path = Path(os.path.abspath(personal_home))
    return tuple(_discover_skills_at(home_path, "personal"))


def capture_fresh_task_inventory(
    task_directory: Path,
    repository_root: Path,
    *,
    personal_home: Path | None = None,
) -> TaskInventory:
    candidates = list(discover_repository_skills(task_directory, repository_root))
    if personal_home is not None:
        candidates.extend(discover_personal_skills(personal_home))
    entries = tuple(
        TaskInventoryEntry(
            candidate.scope,
            candidate.name,
            candidate.skill_root,
            (candidate.skill_root / "agents" / "openai.yaml").read_text(
                encoding="utf-8"
            ),
        )
        for candidate in candidates
        if (candidate.skill_root / "agents" / "openai.yaml").is_file()
    )
    return TaskInventory(entries)


def isolate_skill_path(
    inventory: TaskInventory, name: str, *, expected_path: Path | None = None
) -> PathIsolation:
    matches = [entry for entry in inventory.entries if entry.name == name]
    if expected_path is None:
        return PathIsolation("path_required", None)
    for entry in matches:
        if entry.skill_root == expected_path:
            return PathIsolation("isolated", entry.skill_root)
    return PathIsolation("path_not_found", None)


def inspect_personal_installation(
    personal_home: Path, repository_root: Path
) -> PersonalInstallation:
    home_path = Path(os.path.abspath(personal_home))
    target = home_path / ".agents" / "skills" / "watch"
    source = (
        Path(os.path.abspath(repository_root)) / ".agents" / "skills" / "watch"
    ).resolve()
    if not os.path.lexists(target):
        return PersonalInstallation("absent", target, source)
    if not target.is_symlink():
        return PersonalInstallation("existing_non_symlink", target, source)
    if not target.exists():
        return PersonalInstallation("broken_symlink", target, source)
    if target.resolve() != source:
        return PersonalInstallation("wrong_symlink_target", target, source)
    return PersonalInstallation("valid_symlink", target, source)


def plan_manual_personal_installation(
    personal_home: Path, repository_root: Path
) -> ManualInstallationPlan:
    inspection = inspect_personal_installation(personal_home, repository_root)
    parent_refusal = _personal_parent_refusal(Path(os.path.abspath(personal_home)))
    if parent_refusal is not None:
        return ManualInstallationPlan(
            parent_refusal,
            inspection.target,
            inspection.source,
            False,
            None,
        )
    if os.path.lexists(inspection.target):
        return ManualInstallationPlan(
            "refused_existing_target",
            inspection.target,
            inspection.source,
            False,
            None,
        )
    return ManualInstallationPlan(
        "manual_action_required",
        inspection.target,
        inspection.source,
        True,
        (
            "Create exactly one symbolic link at "
            f"{inspection.target} pointing to {inspection.source}."
        ),
    )


def _personal_parent_refusal(personal_home: Path) -> str | None:
    agents_parent = personal_home / ".agents"
    skills_parent = agents_parent / "skills"
    for parent in (agents_parent, skills_parent):
        if not os.path.lexists(parent):
            return "refused_missing_parent"
        if parent.is_symlink():
            return "refused_parent_symlink"
        if not parent.is_dir():
            return "refused_parent_not_directory"
    return None


def route_watch_invocation(
    request: str,
    *,
    source_count: int,
    has_current_source: bool = False,
    source_state: str = "supported",
) -> InvocationDecision:
    normalized = request.casefold()
    if re.search(r"(?<![\w$])\$watch\b", normalized):
        return InvocationDecision("explicit", False)

    if source_state != "supported" or source_count not in {0, 1}:
        return InvocationDecision("none", False)
    if source_count == 0 and not has_current_source:
        return InvocationDecision("none", False)
    if _contains_excluded_action(normalized):
        return InvocationDecision("none", False)
    if not _requests_inspection_or_answer(normalized):
        return InvocationDecision("none", False)
    if source_count == 1 and re.search(r"\bvideo\b", normalized):
        return InvocationDecision("implicit", False)
    if source_count == 0 and "current source" in normalized:
        return InvocationDecision("implicit", False)
    return InvocationDecision("none", False)


def _contains_excluded_action(request: str) -> bool:
    return bool(
        re.search(
            r"\b(download|edit|trim|clip|upload|code|script|convert|transcode|create|generate|install|copy|move|delete|cleanup)\b",
            request,
        )
    )


def _requests_inspection_or_answer(request: str) -> bool:
    return bool(
        re.search(
            r"\b(inspect|analy[sz]e|summari[sz]e|answer|what|when|where|who|why|how)\b",
            request,
        )
    )


def validate_skill_package(skill_root: Path) -> PackageValidation:
    errors: list[str] = []
    expected_entries = {"SKILL.md", "agents", "references", "scripts"}
    forbidden_entries = {
        "tests",
        "test",
        "fixtures",
        "fixture",
        "development",
        "dev",
        "release-evidence",
        "release_evidence",
    }

    root_mode = _lstat_mode(skill_root)
    if root_mode is None or not stat.S_ISDIR(root_mode):
        return PackageValidation(("skill_root_missing",))

    entries = {path.name for path in skill_root.iterdir()}
    missing_entries = expected_entries.difference(entries)
    errors.extend(f"missing_entry:{entry}" for entry in sorted(missing_entries))
    errors.extend(_tree_integrity_errors(skill_root, forbidden_entries))

    for directory in ("agents", "references", "scripts"):
        if not _is_directory_no_follow(skill_root / directory):
            errors.append(f"skill_directory_invalid:{directory}")

    skill_file = skill_root / "SKILL.md"
    if _is_regular_file_no_follow(skill_file):
        skill_text = skill_file.read_text(encoding="utf-8")
        errors.extend(_front_matter_errors(skill_text))
        errors.extend(_authority_claim_errors(skill_text))
    else:
        errors.append("skill_file_missing")

    metadata_file = skill_root / "agents" / "openai.yaml"
    if _is_directory_no_follow(skill_root / "agents") and _is_regular_file_no_follow(
        metadata_file
    ):
        errors.extend(_metadata_errors(metadata_file.read_text(encoding="utf-8")))
    else:
        errors.append("metadata_file_missing")

    return PackageValidation(tuple(errors))


def _lstat_mode(path: Path) -> int | None:
    try:
        return os.lstat(path).st_mode
    except FileNotFoundError:
        return None


def _is_regular_file_no_follow(path: Path) -> bool:
    mode = _lstat_mode(path)
    return mode is not None and stat.S_ISREG(mode)


def _is_directory_no_follow(path: Path) -> bool:
    mode = _lstat_mode(path)
    return mode is not None and stat.S_ISDIR(mode)


def _tree_integrity_errors(skill_root: Path, forbidden_entries: set[str]) -> list[str]:
    errors: list[str] = []
    for directory, subdirectories, files in os.walk(
        skill_root, topdown=True, followlinks=False
    ):
        current = Path(directory)
        for name in sorted((*subdirectories, *files)):
            path = current / name
            relative_path = path.relative_to(skill_root).as_posix()
            mode = _lstat_mode(path)
            if mode is not None and stat.S_ISLNK(mode):
                errors.append(f"symlink_in_skill_tree:{relative_path}")
            if name in forbidden_entries:
                errors.append(f"forbidden_skill_entry:{relative_path}")
    return errors


def _front_matter_errors(skill_text: str) -> list[str]:
    sections = skill_text.split("---", 2)
    if len(sections) < 3 or sections[0].strip():
        return ["front_matter_missing"]

    fields: list[str] = []
    values: dict[str, str] = {}
    for line in sections[1].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            return ["front_matter_invalid"]
        name, value = line.split(":", 1)
        field_name = name.strip()
        fields.append(field_name)
        values[field_name] = value.strip()
    if fields != ["name", "description"]:
        return ["front_matter_fields_invalid"]
    if not _is_narrow_trigger_description(values["description"]):
        return ["trigger_description_invalid"]
    return []


def _is_narrow_trigger_description(description: str) -> bool:
    required_terms = (
        "$watch",
        "exactly one",
        "implicitly only",
        "exclude",
        "downloads",
        "edits",
        "code",
        "private",
        "authenticated",
        "live",
        "playlists",
        "ambiguous",
        "multiple",
    )
    normalized = description.casefold()
    has_implicit_watch_trigger = bool(
        re.search(r"\basks?\s+(codex\s+)?to\s+watch\b", normalized)
    )
    return all(
        term in normalized for term in required_terms
    ) and not has_implicit_watch_trigger


def _discover_skills_at(root: Path, scope: str) -> list[DiscoveredSkill]:
    skills_directory = root / ".agents" / "skills"
    if not skills_directory.is_dir():
        return []

    candidates: list[DiscoveredSkill] = []
    for skill_root in sorted(skills_directory.iterdir(), key=lambda path: path.name):
        skill_file = skill_root / "SKILL.md"
        if not skill_root.is_dir() or not skill_file.is_file():
            continue
        name = _skill_name(skill_file.read_text(encoding="utf-8"))
        if name is not None:
            candidates.append(DiscoveredSkill(scope, name, skill_root, skill_root.resolve()))
    return candidates


def _skill_name(skill_text: str) -> str | None:
    sections = skill_text.split("---", 2)
    if len(sections) < 3 or sections[0].strip():
        return None
    for line in sections[1].splitlines():
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            return name or None
    return None


def _metadata_errors(metadata_text: str) -> list[str]:
    fields: dict[str, dict[str, str]] = {}
    current_section: str | None = None
    for line in metadata_text.splitlines():
        if not line.strip():
            continue
        if line.startswith("  "):
            if current_section is None or ":" not in line:
                return ["metadata_invalid"]
            name, value = line.strip().split(":", 1)
            fields.setdefault(current_section, {})[name] = value.strip().strip('"')
            continue
        if line.endswith(":") and not line.startswith(" "):
            current_section = line[:-1]
            fields.setdefault(current_section, {})
            continue
        return ["metadata_invalid"]

    if set(fields) != {"interface", "policy"}:
        return ["metadata_sections_invalid"]
    interface = fields["interface"]
    if set(interface) != {"display_name", "short_description", "default_prompt"}:
        return ["metadata_interface_invalid"]
    if not all(interface.values()):
        return ["metadata_display_value_missing"]
    if not interface["default_prompt"].startswith("$watch"):
        return ["metadata_default_prompt_invalid"]
    if fields["policy"] != {"allow_implicit_invocation": "true"}:
        return ["metadata_policy_invalid"]
    return []


def _authority_claim_errors(skill_text: str) -> list[str]:
    unsupported_claim_patterns = (
        r"\b(can|will|may|automatically)\s+(self[- ]?)?install\b",
        r"\b(can|will|may|automatically)\s+(self[- ]?)?update\b",
        r"\b(requires?|uses?|has)\s+(an?\s+)?mcp\b",
        r"\bbypasses?\s+(the\s+)?sandbox\b",
        r"\b(unrestricted|automatic)\s+(network|global)\b",
    )
    if any(re.search(pattern, skill_text.casefold()) for pattern in unsupported_claim_patterns):
        return ["unsupported_authority_claim"]
    return []
