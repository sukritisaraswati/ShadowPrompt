"""Detection rules, loaded from ``data/detection_rules.json``.

Rules live in a data file so they can be reviewed and tuned without touching
code. The file is validated on load: a malformed rule, an unknown category, or
a regex that fails to compile stops the application at startup rather than
silently weakening detection.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

RULES_PATH = Path(__file__).parent / "data" / "detection_rules.json"


class Category(StrEnum):
    """The seven ShadowScan detection categories (blueprint 6.2)."""

    INSTRUCTION_OVERRIDE = "instruction_override"
    DATA_EXFILTRATION = "data_exfiltration"
    UNAUTHORIZED_ACTION = "unauthorized_action"
    PERSONA_OVERRIDE = "persona_override"
    STEALTH_INSTRUCTION = "stealth_instruction"
    CONTEXT_INJECTION = "context_injection"
    CHAINED_PAYLOAD_SETUP = "chained_payload_setup"


class _CategorySpec(BaseModel):
    label: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    remediation: str = Field(min_length=1)


class _RuleSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$")
    category: Category
    description: str = Field(min_length=1)
    weight: int = Field(ge=1, le=50)
    case_sensitive: bool = False
    patterns: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _id_matches_category(self) -> _RuleSpec:
        if self.id.split(".")[0] != self.category.value:
            raise ValueError(f"rule {self.id} is filed under {self.category.value}")
        return self


class _RuleFile(BaseModel):
    version: int
    categories: dict[Category, _CategorySpec]
    rules: list[_RuleSpec]

    @field_validator("categories")
    @classmethod
    def _every_category_described(
        cls, value: dict[Category, _CategorySpec]
    ) -> dict[Category, _CategorySpec]:
        missing = set(Category) - set(value)
        if missing:
            raise ValueError(f"categories missing descriptions: {sorted(missing)}")
        return value

    @model_validator(mode="after")
    def _unique_and_complete(self) -> _RuleFile:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate rule ids")
        uncovered = set(Category) - {rule.category for rule in self.rules}
        if uncovered:
            raise ValueError(f"categories with no rules: {sorted(uncovered)}")
        return self


@dataclass(frozen=True)
class CategoryInfo:
    label: str
    impact: str
    remediation: str


@dataclass(frozen=True)
class Rule:
    id: str
    category: Category
    description: str
    weight: int
    patterns: tuple[re.Pattern[str], ...]

    def search(self, text: str) -> re.Match[str] | None:
        for pattern in self.patterns:
            match = pattern.search(text)
            if match:
                return match
        return None


@dataclass(frozen=True)
class RuleSet:
    version: int
    rules: tuple[Rule, ...]
    categories: dict[Category, CategoryInfo]


def load_rules(path: Path = RULES_PATH) -> RuleSet:
    """Parse, validate and compile a rule file."""
    spec = _RuleFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    rules = []
    for rule in spec.rules:
        flags = 0 if rule.case_sensitive else re.IGNORECASE
        try:
            compiled = tuple(re.compile(pattern, flags) for pattern in rule.patterns)
        except re.error as exc:
            raise ValueError(f"rule {rule.id} has an invalid pattern: {exc}") from exc
        rules.append(
            Rule(
                id=rule.id,
                category=rule.category,
                description=rule.description,
                weight=rule.weight,
                patterns=compiled,
            )
        )
    categories = {
        category: CategoryInfo(label=c.label, impact=c.impact, remediation=c.remediation)
        for category, c in spec.categories.items()
    }
    return RuleSet(version=spec.version, rules=tuple(rules), categories=categories)


@lru_cache
def get_rules() -> RuleSet:
    """The application rule set, loaded once."""
    return load_rules()
