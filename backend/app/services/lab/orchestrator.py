"""Campaign orchestration: run a campaign's tests in the background.

Each campaign runs as one asyncio task that works through its payloads in
order, one request at a time, which is gentle on the user's rate limits. Every
result is committed as soon as it is evaluated and published to any live
viewers, so a stopped, failed or interrupted campaign keeps everything it
finished.

* Level 1 to 4 tests are a single request.
* Level 5 tests are live conversations: each scripted user turn is sent with
  the model's real earlier replies, so the chain builds on what it said.
* Tests that Layers 1 and 2 leave UNCLEAR go to the Layer 3 judge, when it is
  configured, up to a per-campaign cap.
* A campaign can be paused between tests and resumed, or stopped.

Key lifetime (blueprint 10.1): the user's API key reaches this module inside
an :class:`LlmConfig` and is held only by the running task. It is never
written to the database, never logged, and is released when the task ends.

Every exit path finalises the campaign, so the database never holds a
campaign stuck in "running". On startup, campaigns left unfinished by a crash
are marked failed, because their key is gone and they cannot resume.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import Campaign, CampaignStatus, TestResult, Verdict
from app.db.session import get_sessionmaker
from app.schemas.common import ErrorCode
from app.services.lab import hosted_pages
from app.services.lab.chatbot import ConversationMode
from app.services.lab.evaluator import Evaluation, evaluate, evaluate_conversation
from app.services.lab.events import events
from app.services.lab.judge import Judge, JudgeRequest
from app.services.lab.llm_client import (
    ChatMessage,
    LlmBackend,
    LlmConfig,
    LlmReply,
    Provider,
    chat,
)
from app.services.lab.payloads import Payload
from app.services.lab.scoring import level_score, overall_score

logger = logging.getLogger(__name__)

# Errors that make every remaining test pointless.
FATAL_CODES = frozenset(
    {
        ErrorCode.LLM_AUTH_FAILED,
        ErrorCode.LLM_MODEL_NOT_FOUND,
        ErrorCode.BLOCKED_TARGET,
        ErrorCode.VALIDATION_ERROR,
    }
)
MAX_CONSECUTIVE_ERRORS = 3
ACTIVE_STATUSES = (CampaignStatus.PENDING, CampaignStatus.RUNNING, CampaignStatus.PAUSED)


class _Abort(Exception):
    """End the campaign early with a plain-language reason."""


@dataclass
class RunControl:
    """Signals from the API to a running campaign."""

    stop: asyncio.Event = field(default_factory=asyncio.Event)
    resume: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self.resume.set()


@dataclass
class RunHandle:
    campaign_id: uuid.UUID
    task: asyncio.Task[None]
    control: RunControl


class CampaignRegistry:
    """The campaigns running in this process."""

    def __init__(self) -> None:
        self._runs: dict[uuid.UUID, RunHandle] = {}

    def active_count(self) -> int:
        return len(self._runs)

    def is_running(self, campaign_id: uuid.UUID) -> bool:
        return campaign_id in self._runs

    def start(
        self,
        campaign_id: uuid.UUID,
        runner: Callable[[RunControl], Awaitable[None]],
    ) -> RunHandle:
        control = RunControl()
        task = asyncio.create_task(runner(control), name=f"campaign-{campaign_id}")
        handle = RunHandle(campaign_id, task, control)
        self._runs[campaign_id] = handle
        task.add_done_callback(lambda _t: self._runs.pop(campaign_id, None))
        return handle

    def request_stop(self, campaign_id: uuid.UUID) -> bool:
        handle = self._runs.get(campaign_id)
        if handle is None:
            return False
        handle.control.stop.set()
        handle.control.resume.set()  # wake a paused run so it can stop
        return True

    def pause(self, campaign_id: uuid.UUID) -> bool:
        handle = self._runs.get(campaign_id)
        if handle is None:
            return False
        handle.control.resume.clear()
        return True

    def resume(self, campaign_id: uuid.UUID) -> bool:
        handle = self._runs.get(campaign_id)
        if handle is None:
            return False
        handle.control.resume.set()
        return True

    async def wait(self, campaign_id: uuid.UUID) -> None:
        handle = self._runs.get(campaign_id)
        if handle is not None:
            await asyncio.wait({handle.task})

    async def shutdown(self) -> None:
        """Stop every run and let each one finalise its campaign."""
        handles = list(self._runs.values())
        for handle in handles:
            handle.control.stop.set()
            handle.control.resume.set()
            handle.task.cancel()
        if handles:
            await asyncio.gather(*(h.task for h in handles), return_exceptions=True)


registry = CampaignRegistry()


# --------------------------------------------------------------------------- #
# Persistence helpers
# --------------------------------------------------------------------------- #


async def _set_status(campaign_id: uuid.UUID, status: CampaignStatus) -> None:
    async with get_sessionmaker()() as db:
        await db.execute(update(Campaign).where(Campaign.id == campaign_id).values(status=status))
        await db.commit()
    events.publish(campaign_id, {"type": "status", "status": status.value})


async def _record(campaign_id: uuid.UUID, payload: Payload, **values: object) -> TestResult:
    async with get_sessionmaker()() as db:
        row = TestResult(
            campaign_id=campaign_id,
            track=payload.track.value,
            level=payload.level,
            category=payload.spec.category,
            payload_id=payload.id,
            **values,
        )
        db.add(row)
        await db.commit()

    from app.services.lab.campaign_service import result_out

    events.publish(
        campaign_id,
        {"type": "result", "result": result_out(row, payload).model_dump(mode="json")},
    )
    return row


async def finalize(
    campaign_id: uuid.UUID, status: CampaignStatus, error_message: str | None = None
) -> None:
    """Write the final status and scores computed from the saved results."""
    async with get_sessionmaker()() as db:
        campaign = await db.get(Campaign, campaign_id)
        if campaign is None:
            return
        rows = (
            await db.execute(
                select(TestResult.track, TestResult.level, TestResult.verdict).where(
                    TestResult.campaign_id == campaign_id
                )
            )
        ).all()
        by_level: dict[tuple[str, int], list[Verdict]] = {}
        for track, level, verdict in rows:
            by_level.setdefault((track, level), []).append(verdict)
        # Direct before indirect, then by level.
        keys = sorted(by_level, key=lambda key: (key[0] != "direct", key[1]))
        scores = [level_score(track, level, by_level[(track, level)]) for track, level in keys]

        campaign.status = status
        campaign.completed_at = datetime.now(UTC)
        campaign.level_scores = [s.as_dict() for s in scores]
        campaign.overall_score = overall_score(scores)
        if error_message:
            campaign.error_message = error_message[:500]
        await db.commit()
        score = campaign.overall_score
    events.publish(
        campaign_id,
        {"type": "done", "status": status.value, "overall_score": score, "error": error_message},
    )


async def recover_orphans() -> int:
    """Fail campaigns a previous process left unfinished. Returns the count."""
    async with get_sessionmaker()() as db:
        result = await db.execute(
            update(Campaign)
            .where(Campaign.status.in_(ACTIVE_STATUSES))
            .values(
                status=CampaignStatus.FAILED,
                completed_at=datetime.now(UTC),
                error_message=(
                    "The server restarted during this run. Results up to that point are kept."
                ),
            )
        )
        await db.commit()
        return result.rowcount or 0


# --------------------------------------------------------------------------- #
# Running one test
# --------------------------------------------------------------------------- #


@dataclass
class _RunState:
    judge: Judge | None
    judge_calls: int = 0
    consecutive_errors: int = 0


def _conversation_id(campaign_id: uuid.UUID, payload: Payload, config: LlmConfig) -> str:
    """A fresh id per test, so a chatbot that keeps history starts each test clean."""
    if config.provider is not Provider.CHATBOT:
        return ""
    return f"shadowprompt-{campaign_id.hex[:8]}-{payload.id}-{secrets.token_hex(3)}"


def _server_keeps_history(config: LlmConfig) -> bool:
    return config.chatbot is not None and config.chatbot.mode is ConversationMode.SERVER


async def _converse(
    payload: Payload,
    config: LlmConfig,
    settings: Settings,
    backend: LlmBackend,
    conversation_id: str = "",
) -> list[LlmReply]:
    """Play a live conversation: each user turn, then the model's real reply."""
    history = [ChatMessage("system", payload.spec.system_context)]
    replies: list[LlmReply] = []
    for turn in payload.user_turns():
        history.append(ChatMessage("user", turn))
        # A chatbot that keeps its own history gets each new message alone.
        sent = [history[-1]] if _server_keeps_history(config) else history
        reply = await chat(
            config, sent, settings=settings, backend=backend, conversation_id=conversation_id
        )
        replies.append(reply)
        history.append(ChatMessage("assistant", reply.text or "(no reply)"))
    return replies


async def _maybe_judge(
    payload: Payload, evaluation: Evaluation, state: _RunState, settings: Settings
) -> dict | None:
    if evaluation.verdict is not Verdict.UNCLEAR or state.judge is None:
        return None
    if not state.judge.available:
        return {"verdict": None, "reason": "Layer 3 is not configured on this server."}
    if state.judge_calls >= state.judge.settings.layer3_max_calls_per_campaign:
        return {"verdict": None, "reason": "This campaign reached its Layer 3 call limit."}
    state.judge_calls += 1
    result = await state.judge.judge(
        JudgeRequest(
            payload_id=payload.id,
            objective=payload.spec.objective.value,
            criteria=payload.spec.evaluation_hint,
            attack=payload.attack_text(),
            transcript=evaluation.summary,
        )
    )
    return result.as_dict()


async def _run_one(
    campaign_id: uuid.UUID,
    payload: Payload,
    config: LlmConfig,
    settings: Settings,
    backend: LlmBackend,
    state: _RunState,
) -> None:
    started = asyncio.get_running_loop().time()
    conversation_id = _conversation_id(campaign_id, payload, config)
    try:
        if payload.is_live:
            replies = await _converse(payload, config, settings, backend, conversation_id)
            evaluation = evaluate_conversation(payload, replies)
        else:
            reply = await chat(
                config,
                payload.messages(),
                settings=settings,
                backend=backend,
                conversation_id=conversation_id,
            )
            evaluation = evaluate(payload, reply)
    except AppError as exc:
        if exc.code in FATAL_CODES:
            raise _Abort(f"{exc.message} ({exc.code.value})") from exc
        await _record(
            campaign_id,
            payload,
            verdict=Verdict.UNCLEAR,
            response_summary=None,
            evaluation_detail={
                "decided_by": "error",
                "error": {"code": exc.code.value, "message": exc.message},
            },
            latency_ms=None,
        )
        state.consecutive_errors += 1
        if state.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            raise _Abort(
                f"The model failed to respond {MAX_CONSECUTIVE_ERRORS} times in a row, "
                "so the campaign was stopped."
            ) from exc
        return

    state.consecutive_errors = 0
    verdict = evaluation.verdict
    detail = evaluation.detail()
    exposed = True
    if payload.hosted_key:
        status = await hosted_pages.fetch_status(payload.hosted_key)
        detail["hosted_page"] = {"url": payload.page_link, **status.as_dict()}
        if status.fetch_count == 0 and verdict is not Verdict.FAIL:
            # The bot never read the page, so the hidden instruction never
            # reached it: resisting it proves nothing.
            exposed = False
            verdict = Verdict.UNCLEAR
            detail["decided_by"] = "page_not_fetched"
    judged = await _maybe_judge(payload, evaluation, state, settings) if exposed else None
    if judged is not None:
        detail["layer3"] = judged
        if judged["verdict"]:
            verdict = Verdict(judged["verdict"])
            detail["decided_by"] = "layer3"
    if payload.page_scan is not None:
        detail["page_scan"] = payload.page_scan.as_dict()
    if config.chatbot is not None:
        detail["target"] = "chatbot"
        scripted = isinstance(payload.spec.prompt, list) and not payload.is_live
        if scripted and config.chatbot.mode is not ConversationMode.HISTORY:
            # The bot cannot take a scripted history, so it arrived as one message.
            detail["history_flattened"] = True

    await _record(
        campaign_id,
        payload,
        verdict=verdict,
        response_summary=evaluation.summary,
        evaluation_detail=detail,
        latency_ms=round((asyncio.get_running_loop().time() - started) * 1000),
    )


async def run_campaign(
    campaign_id: uuid.UUID,
    config: LlmConfig,
    payloads: list[Payload],
    control: RunControl,
    *,
    settings: Settings,
    backend: LlmBackend,
    judge: Judge | None = None,
) -> None:
    status = CampaignStatus.COMPLETED
    error_message: str | None = None
    state = _RunState(judge=judge)
    try:
        await _set_status(campaign_id, CampaignStatus.RUNNING)
        for payload in payloads:
            if not control.resume.is_set() and not control.stop.is_set():
                await _set_status(campaign_id, CampaignStatus.PAUSED)
                await control.resume.wait()
                if not control.stop.is_set():
                    await _set_status(campaign_id, CampaignStatus.RUNNING)
            if control.stop.is_set():
                status = CampaignStatus.STOPPED
                break
            await _run_one(campaign_id, payload, config, settings, backend, state)
        else:
            if control.stop.is_set():
                status = CampaignStatus.STOPPED
    except _Abort as exc:
        status, error_message = CampaignStatus.FAILED, str(exc)
    except asyncio.CancelledError:
        status = CampaignStatus.STOPPED
        error_message = "The run was interrupted before it finished."
        await finalize(campaign_id, status, error_message)
        raise
    except Exception:
        logger.exception("Campaign %s failed unexpectedly", campaign_id)
        status, error_message = CampaignStatus.FAILED, "An internal error ended the campaign."
    await finalize(campaign_id, status, error_message)
    logger.info("Campaign %s finished with status %s", campaign_id, status.value)
