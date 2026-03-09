"""
Corpus validation utilities.

Checks schema compliance, data integrity, duplicate detection,
and cross-reference consistency for the prompt injection database.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "id",
    "name",
    "title",
    "summary",
    "prompt",
    "prompt_text",
    "taxonomy",
    "category",
    "subcategory",
    "attack_family",
    "delivery_vector",
    "target_surface",
    "target_type",
    "agent_capability_targeted",
    "applicable_context",
    "difficulty",
    "stealth",
    "realism",
    "tags",
    "language",
    "format",
    "source",
    "status",
    "quality_score",
    "last_reviewed",
    "safe_internal_use_only",
    "related_prompts",
    "mutation_guidance",
    "postgres",
]

VALID_DIFFICULTIES = {"low", "medium", "high"}
VALID_STEALTH = {"low", "medium", "high"}
VALID_REALISM = {"low", "medium", "high"}
VALID_STATUSES = {"active", "deprecated", "draft", "review"}
VALID_FORMATS = {"text", "json", "code", "markdown", "html", "mixed"}
VALID_LANGUAGES = {"en", "multi", "zh", "es", "fr", "de", "ja", "ko", "ar", "ru"}

# ---------------------------------------------------------------------------
# Validation issue types
# ---------------------------------------------------------------------------


class ValidationIssue:
    """Represents a single validation problem."""

    def __init__(self, file_path: str, record_id: str, severity: str, message: str):
        self.file_path = file_path
        self.record_id = record_id
        self.severity = severity  # "error", "warning", "info"
        self.message = message

    def __repr__(self) -> str:
        return f"[{self.severity.upper()}] {self.record_id} ({self.file_path}): {self.message}"

    def to_dict(self) -> Dict[str, str]:
        return {
            "file_path": self.file_path,
            "record_id": self.record_id,
            "severity": self.severity,
            "message": self.message,
        }


# ---------------------------------------------------------------------------
# CorpusValidator
# ---------------------------------------------------------------------------


class CorpusValidator:
    """
    Validates all prompt records in the corpus.

    Usage::

        validator = CorpusValidator("/path/to/repo")
        issues = validator.validate_all()
        for issue in issues:
            print(issue)
    """

    def __init__(self, root: Optional[Union[str, Path]] = None):
        self._root = Path(root) if root else Path(__file__).resolve().parent.parent
        self._issues: List[ValidationIssue] = []
        self._records: Dict[str, Dict[str, Any]] = {}
        self._file_map: Dict[str, str] = {}  # id -> file path

    def _add(self, path: str, rid: str, severity: str, msg: str) -> None:
        self._issues.append(ValidationIssue(path, rid, severity, msg))

    def validate_all(self) -> List[ValidationIssue]:
        """Run all validation checks and return a list of issues."""
        self._issues = []
        self._records = {}
        self._file_map = {}

        files = sorted(self._root.rglob("*.postgres.json"))
        if not files:
            self._add("", "", "error", "No .postgres.json files found in repository")
            return self._issues

        # Phase 1: Load and validate individual files
        for path in files:
            rel = str(path.relative_to(self._root))
            self._validate_file(path, rel)

        # Phase 2: Cross-record checks
        self._check_duplicate_ids()
        self._check_related_prompts()
        self._check_orphaned_categories()

        return self._issues

    def _validate_file(self, path: Path, rel: str) -> None:
        """Validate a single JSON file."""
        # 1. Parse JSON
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            self._add(rel, "?", "error", f"Malformed JSON: {exc}")
            return
        except OSError as exc:
            self._add(rel, "?", "error", f"Cannot read file: {exc}")
            return

        rid = data.get("id", "UNKNOWN")

        # 2. Required fields
        for field in REQUIRED_FIELDS:
            if field not in data:
                self._add(rel, rid, "error", f"Missing required field: {field}")

        # 3. Field type checks
        if "prompt" in data and not isinstance(data["prompt"], list):
            self._add(rel, rid, "error", "Field 'prompt' must be an array of strings")

        if "tags" in data and not isinstance(data["tags"], list):
            self._add(rel, rid, "error", "Field 'tags' must be an array of strings")

        # 4. prompt_text consistency
        if "prompt" in data and "prompt_text" in data:
            expected = "\n".join(data["prompt"])
            if data["prompt_text"] != expected:
                self._add(rel, rid, "warning", "prompt_text does not match joined prompt array")

        # 5. Enum validations
        if data.get("difficulty") and data["difficulty"] not in VALID_DIFFICULTIES:
            self._add(rel, rid, "warning", f"Invalid difficulty: {data['difficulty']}")
        if data.get("stealth") and data["stealth"] not in VALID_STEALTH:
            self._add(rel, rid, "warning", f"Invalid stealth: {data['stealth']}")
        if data.get("realism") and data["realism"] not in VALID_REALISM:
            self._add(rel, rid, "warning", f"Invalid realism: {data['realism']}")
        if data.get("status") and data["status"] not in VALID_STATUSES:
            self._add(rel, rid, "warning", f"Invalid status: {data['status']}")
        if data.get("format") and data["format"] not in VALID_FORMATS:
            self._add(rel, rid, "warning", f"Invalid format: {data['format']}")
        if data.get("language") and data["language"] not in VALID_LANGUAGES:
            self._add(rel, rid, "warning", f"Invalid language: {data['language']}")

        # 6. Empty content checks
        if data.get("summary") and len(data["summary"].strip()) < 10:
            self._add(rel, rid, "warning", "Summary is too short (< 10 chars)")
        if data.get("prompt") and len(data["prompt"]) == 0:
            self._add(rel, rid, "error", "Prompt array is empty")
        if data.get("tags") and len(data["tags"]) == 0:
            self._add(rel, rid, "warning", "Tags array is empty")

        # 7. ID format check
        if not re.match(r"^\d+\.\d+-\d{3}$", str(rid)):
            self._add(rel, rid, "warning", f"ID does not match expected format X.Y-NNN: {rid}")

        # 8. Taxonomy consistency
        taxonomy = data.get("taxonomy", {})
        if taxonomy:
            if not taxonomy.get("root_category"):
                self._add(rel, rid, "warning", "taxonomy.root_category is empty")
            if not taxonomy.get("subcategory_code"):
                self._add(rel, rid, "warning", "taxonomy.subcategory_code is empty")

        # 9. safe_internal_use_only check
        if data.get("safe_internal_use_only") is not True:
            self._add(rel, rid, "info", "safe_internal_use_only is not set to true")

        # Store for cross-record checks
        self._records[rid] = data
        if rid in self._file_map:
            self._add(rel, rid, "error", f"Duplicate ID (also in {self._file_map[rid]})")
        self._file_map[rid] = rel

    def _check_duplicate_ids(self) -> None:
        """Check for duplicate record IDs across all files."""
        id_counts = Counter(self._file_map.keys())
        # Already handled in _validate_file via self._file_map

    def _check_related_prompts(self) -> None:
        """Check that related_prompts references point to valid IDs."""
        all_ids = set(self._records.keys())
        for rid, rec in self._records.items():
            for ref in rec.get("related_prompts", []):
                if ref not in all_ids:
                    self._add(
                        self._file_map.get(rid, "?"),
                        rid,
                        "warning",
                        f"related_prompts references unknown ID: {ref}",
                    )

    def _check_orphaned_categories(self) -> None:
        """Check for categories that have only one record."""
        cat_counts: Counter = Counter()
        for rec in self._records.values():
            cat_counts[rec.get("subcategory", "")] += 1
        for cat, count in cat_counts.items():
            if count == 1 and cat:
                # Find the record
                for rid, rec in self._records.items():
                    if rec.get("subcategory") == cat:
                        self._add(
                            self._file_map.get(rid, "?"),
                            rid,
                            "info",
                            f"Subcategory '{cat}' has only one record",
                        )
                        break

    # -- reporting -----------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a summary of validation results."""
        errors = [i for i in self._issues if i.severity == "error"]
        warnings = [i for i in self._issues if i.severity == "warning"]
        infos = [i for i in self._issues if i.severity == "info"]
        return {
            "total_files": len(self._file_map),
            "total_issues": len(self._issues),
            "errors": len(errors),
            "warnings": len(warnings),
            "info": len(infos),
            "issues": [i.to_dict() for i in self._issues],
        }

    def is_valid(self) -> bool:
        """Return True if no errors were found (warnings are OK)."""
        return all(i.severity != "error" for i in self._issues)
