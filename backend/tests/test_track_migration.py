"""Phase 5.1: campaigns from before the two tracks are migrated intact."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid
from contextlib import closing
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def alembic(db: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )


def test_old_campaigns_move_to_level_codes_and_new_ids(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    alembic(db, "upgrade", "df5bef2e47be")

    session_id, campaign_id = uuid.uuid4().hex, uuid.uuid4().hex
    custom_spec = {
        "id": "C4-ABCDEF-001",
        "level": 4,
        "category": "indirect_injection",
        "html_page": "C4-ABCDEF-001_custom.html",
    }
    rows = [
        ("L1-001", 1, "PASS"),
        ("L4-028", 4, "FAIL"),  # Base64 page: now I3
        ("L5-005", 5, "PASS"),  # context poisoning, no page: now D4
        ("L5-001", 5, "FAIL"),  # page-primed chain: now I5
        ("C4-ABCDEF-001", 4, "FAIL"),  # custom page test: now CI1
    ]
    with closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "insert into sessions (id, provider, model_name, created_at) "
            "values (?, 'openai_compatible', 'm', '2026-10-01')",
            (session_id,),
        )
        conn.execute(
            "insert into campaigns (id, session_id, levels_run, status, total_tests, config, "
            "level_scores, overall_score, started_at) values (?, ?, ?, 'COMPLETED', 5, ?, ?, 50, "
            "'2026-10-01')",
            (
                campaign_id,
                session_id,
                json.dumps([1, 4, 5]),
                json.dumps({"custom_payloads": [{"pack_name": "p", "spec": custom_spec}]}),
                json.dumps([{"level": 1, "score": 100}]),
            ),
        )
        for payload_id, level, verdict in rows:
            conn.execute(
                "insert into test_results (id, campaign_id, level, category, payload_id, verdict, "
                "created_at) values (?, ?, ?, 'old', ?, ?, '2026-10-01')",
                (uuid.uuid4().hex, campaign_id, level, payload_id, verdict),
            )
        conn.commit()

    alembic(db, "upgrade", "head")

    with closing(sqlite3.connect(db)) as conn:
        results = dict(
            (
                (pid, (track, level, cat))
                for pid, track, level, cat in conn.execute(
                    "select payload_id, track, level, category from test_results"
                )
            )
        )
        levels_run, level_scores, overall, config = conn.execute(
            "select levels_run, level_scores, overall_score, config from campaigns"
        ).fetchone()

    assert results == {
        "D1-001": ("direct", 1, "basic_override"),
        "I3-001": ("indirect", 3, "obfuscated_instruction"),
        "D4-001": ("direct", 4, "multi_turn"),
        "I5-001": ("indirect", 5, "chained_indirect"),
        "CI1-ABCDEF-001": ("indirect", 1, "hidden_instruction"),
    }
    assert json.loads(levels_run) == ["D1", "D4", "I1", "I2", "I3", "I4", "I5"]
    scores = {(s["track"], s["level"]): s["score"] for s in json.loads(level_scores)}
    assert scores == {
        ("direct", 1): 100.0,
        ("direct", 4): 100.0,
        ("indirect", 1): 0.0,
        ("indirect", 3): 0.0,
        ("indirect", 5): 0.0,
    }
    assert overall is not None
    spec = json.loads(config)["custom_payloads"][0]["spec"]
    assert (spec["id"], spec["track"], spec["level"], spec["html_page"]) == (
        "CI1-ABCDEF-001",
        "indirect",
        1,
        "CI1-ABCDEF-001_custom.html",
    )
