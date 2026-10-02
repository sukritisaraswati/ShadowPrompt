"""Phase 5.5: fix guidance for failed tests and the campaign's top fixes."""

from __future__ import annotations

import pytest

from app.services.lab.guidance import GUIDANCE, guidance_for, guidance_key, top_fixes
from app.services.lab.payloads import get_library
from tests.test_lab_api import aligned, connect, launch, vulnerable, wait_done

LIB = get_library()


def test_every_library_test_maps_to_guidance() -> None:
    used = {guidance_key(p) for p in LIB.payloads}
    assert used <= set(GUIDANCE)
    # Every family of advice is reachable from at least one test.
    assert used == set(GUIDANCE)


@pytest.mark.parametrize(
    ("payload_id", "expected"),
    [
        ("D1-001", "instruction_override"),
        ("D4-005", "multi_turn"),
        ("I3-001", "indirect_obfuscated"),
        ("I4-001", "indirect_multi_vector"),
    ],
)
def test_tests_map_to_the_right_family(payload_id: str, expected: str) -> None:
    assert guidance_key(LIB.by_id(payload_id)) == expected


def test_technique_names_steer_direct_tests() -> None:
    by_technique = {p.spec.technique: guidance_key(p) for p in LIB.for_level("D3")}
    assert by_technique["base64"] == "encoding"
    assert by_technique["leetspeak"] == "encoding"
    assert by_technique["fake system message"] == "fake_authority"
    assert by_technique["few-shot"] == "forged_history"
    assert by_technique["fictional"] == "fiction"
    assert by_technique["nested roleplay"] == "fiction"


def test_every_guidance_entry_is_actionable() -> None:
    for g in GUIDANCE.values():
        assert g.title and g.why and len(g.fixes) >= 2, g.key
        assert all(fix.endswith(".") for fix in g.fixes), g.key


def test_top_fixes_rank_by_weighted_failures() -> None:
    failed = LIB.for_level("D1")[:3] + LIB.for_level("D4")[:2]
    fixes = top_fixes(failed)
    # Two D4 failures (weight 2.5 each) outrank three D1 failures (weight 1 each).
    assert [f["key"] for f in fixes] == ["multi_turn", "instruction_override"]
    assert fixes[0]["failed_tests"] == 2 and len(fixes[0]["examples"]) == 2
    assert top_fixes([]) == []


def test_failed_results_carry_guidance_and_passed_ones_do_not(client, use_model) -> None:
    use_model(vulnerable)
    bad = wait_done(client, launch(client, connect(client), levels=("D1", "D3"), sample_size=4))
    for r in bad["results"]:
        assert r["verdict"] == "FAIL"
        assert r["guidance"]["key"] == guidance_for(LIB.by_id(r["payload_id"])).key
        assert r["guidance"]["fixes"]
    assert bad["top_fixes"] and bad["top_fixes"][0]["failed_tests"] >= 1
    every_fix = top_fixes([LIB.by_id(r["payload_id"]) for r in bad["results"]], limit=99)
    assert sum(f["failed_tests"] for f in every_fix) == len(bad["results"])

    use_model(aligned)
    good = wait_done(client, launch(client, connect(client), levels=("D1",), sample_size=3))
    assert all(r["guidance"] is None for r in good["results"])
    assert good["top_fixes"] == []


def test_the_report_leads_with_what_to_fix(client, use_model) -> None:
    use_model(vulnerable)
    campaign_id = launch(client, connect(client), levels=("D2",), sample_size=3)
    wait_done(client, campaign_id)
    report = client.post("/api/v1/lab/reports", json={"campaign_id": campaign_id}).text
    assert "What to fix first" in report
    assert GUIDANCE["persona"].title in report
    assert "Suggested system prompt wording" in report
    assert report.index("What to fix first") < report.index("Detailed findings")
