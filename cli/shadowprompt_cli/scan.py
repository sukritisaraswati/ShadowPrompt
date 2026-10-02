"""``shadowprompt scan``: check pages for hidden LLM instructions."""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

from shadowprompt_cli.client import ApiError, Client, Upload

SEVERITIES = ("clean", "low", "medium", "high", "critical")
HTML_SUFFIXES = (".html", ".htm")
# The server's upload limit; larger files are reported, not sent.
MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass
class ScanOutcome:
    target: str
    score: int | None = None
    severity: str | None = None
    findings: list[dict] = field(default_factory=list)
    scan_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "score": self.score,
            "severity": self.severity,
            "finding_count": len(self.findings),
            "findings": [
                {
                    "category": f.get("category_label"),
                    "source": f.get("source_label"),
                    "rule": f.get("matched_rule"),
                    "decoded_from": f.get("obfuscation_label"),
                    "note": f.get("obfuscation_note"),
                    "evidence": f.get("evidence_text"),
                }
                for f in self.findings
            ],
            "scan_id": self.scan_id,
            "error": self.error,
        }


def is_url(target: str) -> bool:
    return target.startswith(("http://", "https://"))


def expand_targets(targets: list[str]) -> list[str]:
    """URLs as given; files, directories (searched for .html) and glob patterns expanded."""
    out: list[str] = []
    for target in targets:
        if is_url(target):
            out.append(target)
            continue
        path = Path(target)
        if path.is_dir():
            out.extend(str(p) for p in sorted(path.rglob("*")) if p.suffix.lower() in HTML_SUFFIXES)
        elif any(ch in target for ch in "*?["):
            out.extend(sorted(glob.glob(target, recursive=True)))
        else:
            out.append(target)
    return list(dict.fromkeys(out))


def scan_one(client: Client, target: str, *, render: bool = False) -> ScanOutcome:
    try:
        if is_url(target):
            result = client.request("POST", "/scan/url", body={"url": target, "render": render})
        else:
            path = Path(target)
            if not path.is_file():
                return ScanOutcome(target, error="file not found")
            if path.stat().st_size > MAX_FILE_BYTES:
                return ScanOutcome(target, error="file is larger than the 2 MB upload limit")
            upload = Upload(path.name, path.read_bytes(), "text/html")
            result = client.request(
                "POST", "/scan/html", upload=("file", upload), fields={"render": render}
            )
    except ApiError as exc:
        if exc.code == "SERVER_UNREACHABLE":
            raise
        return ScanOutcome(target, error=str(exc))
    return ScanOutcome(
        target,
        score=result["score"],
        severity=result["severity"]["level"],
        findings=result.get("findings", []),
        scan_id=result["id"],
    )


def save_report(client: Client, outcome: ScanOutcome, report_dir: str) -> str | None:
    if outcome.scan_id is None:
        return None
    os.makedirs(report_dir, exist_ok=True)
    name = Path(outcome.target).stem if not is_url(outcome.target) else outcome.scan_id[:8]
    path = Path(report_dir) / f"shadowscan-{name}-{outcome.scan_id[:8]}.html"
    content = client.request(
        "POST", "/scan/reports", body={"scan_id": outcome.scan_id, "format": "html"}, raw=True
    )
    path.write_bytes(content)
    return str(path)


def breaches(outcome: ScanOutcome, fail_on: str) -> bool:
    """True when the outcome reaches the failing severity (or could not be scanned)."""
    if outcome.error is not None:
        return True
    if fail_on == "never" or outcome.severity is None:
        return False
    return SEVERITIES.index(outcome.severity) >= SEVERITIES.index(fail_on)
