"""``shadowprompt campaign``: run a Lab campaign and judge the score."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from shadowprompt_cli.client import ApiError, Client, Upload

ACTIVE = ("pending", "running", "paused")


@dataclass
class CampaignSettings:
    provider: str
    base_url: str
    model: str
    api_key: str | None
    levels: list[str]
    sample_size: int | None = None
    languages: list[str] = field(default_factory=list)
    packs: list[str] = field(default_factory=list)
    timeout_seconds: float = 30.0
    max_retries: int = 1
    poll_seconds: float = 2.0
    max_minutes: float = 120.0
    # Set when the target is the user's own chatbot (provider "chatbot").
    chatbot: dict | None = None
    indirect_delivery: str = "inline"


@dataclass
class CampaignOutcome:
    campaign_id: str
    status: str
    score: float | None
    rating: str | None
    total: int
    completed: int
    level_scores: list[dict]
    failures: list[dict]
    unclear: int
    error: str | None = None
    track_scores: list[dict] = field(default_factory=list)
    top_fixes: list[dict] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "status": self.status,
            "score": self.score,
            "rating": self.rating,
            "total_tests": self.total,
            "completed_tests": self.completed,
            "unclear": self.unclear,
            "track_scores": [{"track": t["track"], "score": t["score"]} for t in self.track_scores],
            "level_scores": [
                {"level": ls.get("code", ls["level"]), "name": ls["name"], "score": ls["score"]}
                for ls in self.level_scores
            ],
            "top_fixes": [
                {"title": f["title"], "failed_tests": f["failed_tests"]} for f in self.top_fixes
            ],
            "skipped": self.skipped,
            "failures": self.failures,
            "error": self.error,
        }


def _connection(settings: CampaignSettings) -> dict:
    connection = {
        "provider": "chatbot" if settings.chatbot else settings.provider,
        "base_url": settings.base_url,
        "model": settings.model,
        "api_key": None if settings.chatbot else settings.api_key,
    }
    if settings.chatbot:
        connection["chatbot"] = settings.chatbot
    return connection


def upload_packs(client: Client, paths: list[str]) -> list[str]:
    """Upload custom packs; the server returns the stored pack for repeat content."""
    ids = []
    for path in paths:
        content = Path(path).read_bytes()
        pack = client.request(
            "POST",
            "/lab/payload-packs",
            upload=("file", Upload(Path(path).name, content, "application/json")),
        )
        ids.append(pack["id"])
    return ids


def run_campaign(
    client: Client,
    settings: CampaignSettings,
    *,
    progress: Callable[[str], None] = lambda _m: None,
    clock: Callable[[], float] = time.monotonic,
) -> CampaignOutcome:
    connection = _connection(settings)
    progress(f"Testing the connection to {settings.model} ...")
    session = client.request("POST", "/lab/connect/test", body=connection)
    pack_ids = upload_packs(client, settings.packs) if settings.packs else []

    started = client.request(
        "POST",
        "/lab/campaigns",
        body={
            "session_id": session["session_id"],
            "connection": connection,
            "levels": settings.levels,
            "sample_size": settings.sample_size,
            "languages": settings.languages,
            "custom_pack_ids": pack_ids,
            "timeout_seconds": settings.timeout_seconds,
            "max_retries": settings.max_retries,
            "indirect_delivery": settings.indirect_delivery,
        },
    )
    campaign_id = started["campaign_id"]
    progress(f"Campaign {campaign_id} started with {started['total_tests']} tests.")

    deadline = clock() + settings.max_minutes * 60
    last = -1
    try:
        while True:
            campaign = client.request("GET", f"/lab/campaigns/{campaign_id}")
            if campaign["completed_tests"] != last:
                last = campaign["completed_tests"]
                progress(f"  {last}/{campaign['total_tests']} tests done")
            if campaign["status"] not in ACTIVE:
                break
            if clock() > deadline:
                client.request("POST", f"/lab/campaigns/{campaign_id}/stop")
                raise ApiError(
                    "CAMPAIGN_TIMEOUT",
                    f"The campaign did not finish within {settings.max_minutes:g} minutes",
                )
            client.sleep(settings.poll_seconds)
    except KeyboardInterrupt:
        # Stop the run on the server too, then let the interrupt through.
        try:
            client.request("POST", f"/lab/campaigns/{campaign_id}/stop")
        except ApiError:
            pass
        raise

    results = campaign.get("results", [])
    failures = [
        {"id": r["payload_id"], "level": r["level"], "name": r["name"], "verdict": r["verdict"]}
        for r in results
        if r["verdict"] in ("FAIL", "PARTIAL")
    ]
    return CampaignOutcome(
        campaign_id=campaign_id,
        status=campaign["status"],
        score=campaign.get("overall_score"),
        rating=(campaign.get("rating") or {}).get("label"),
        total=campaign["total_tests"],
        completed=campaign["completed_tests"],
        level_scores=campaign.get("level_scores", []),
        failures=failures,
        unclear=sum(1 for r in results if r["verdict"] == "UNCLEAR"),
        error=campaign.get("error_message"),
        track_scores=campaign.get("track_scores", []),
        top_fixes=campaign.get("top_fixes", []),
        skipped=((campaign.get("config") or {}).get("target") or {}).get("skipped", {}),
    )


def save_report(client: Client, campaign_id: str, path: str) -> str:
    fmt = "pdf" if path.lower().endswith(".pdf") else "html"
    content = client.request(
        "POST", "/lab/reports", body={"campaign_id": campaign_id, "format": fmt}, raw=True
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(content)
    return path


def breaches(outcome: CampaignOutcome, min_score: float) -> bool:
    """True when the campaign failed to finish or scored below the threshold."""
    if outcome.status != "completed":
        return True
    if outcome.score is None:
        # Every test was unclear: nothing shows the model is safe.
        return True
    return outcome.score < min_score
