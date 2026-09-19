"""Phase 7 — experiment pack integrity + post-publish remeasure helper locks."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PHASE7 = ROOT / "docs" / "verification" / "artifacts" / "phase7"
PHASE7_DOC = ROOT / "docs" / "verification" / "PHASE7-AEO-OPTIMIZATION-EXPERIMENT-2026-09-19.md"
PHASE7_JSON = ROOT / "docs" / "verification" / "PHASE7-AEO-OPTIMIZATION-EXPERIMENT-2026-09-19.json"
SCRIPT = ROOT / "scripts" / "phase7_post_publish_remeasure.py"

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from phase7_post_publish_remeasure import (  # noqa: E402
    DEFAULT_SEED,
    baseline_remeasure_options,
    load_publish_status,
)


REQUIRED_ARTIFACTS = [
    "PHASE7_BASELINE_CONFIRMED.json",
    "PHASE7_LIVE_BRAND_VERIFY.json",
    "PHASE7_READY_TO_PUBLISH.json",
    "PHASE7_READY_TO_PUBLISH.md",
    "PHASE7_PUBLISH_STATUS.json",
    "PHASE6_COS_BASELINE_EVIDENCE.json",
    "PHASE6_COS_BASELINE_SNAPSHOT.json",
    "PHASE6_RECOMMENDATION_EXAMPLES.json",
]


def test_phase7_artifacts_present():
    for name in REQUIRED_ARTIFACTS:
        path = PHASE7 / name
        assert path.is_file(), f"missing {path}"


def test_phase7_docs_present_and_blocked():
    assert PHASE7_DOC.is_file()
    assert PHASE7_JSON.is_file()
    text = PHASE7_DOC.read_text(encoding="utf-8")
    assert "BLOCKED_PENDING_PUBLISH" in text
    assert "NOT_ESTABLISHED" in text
    assert "NOT RUN" in text or "NOT_RUN" in text
    data = json.loads(PHASE7_JSON.read_text(encoding="utf-8"))
    assert data["experiment_status"] == "BLOCKED_PENDING_PUBLISH"
    assert data["published"] is False
    assert data["live_cms_publish"] is False
    assert data["post_change_measurement"] == "NOT_RUN"
    assert data["causal_impact"] == "NOT_ESTABLISHED"


def test_publish_status_honestly_unpublished():
    status = json.loads((PHASE7 / "PHASE7_PUBLISH_STATUS.json").read_text(encoding="utf-8"))
    assert status["published"] is False
    assert status["status"] == "BLOCKED_PENDING_PUBLISH"
    assert status["post_change_measurement"] == "NOT_RUN"
    assert status["causal_impact"] == "NOT_ESTABLISHED"
    assert status.get("hashnode_pat_present_in_env") is False


def test_baseline_confirmed_matches_phase6_numbers():
    confirmed = json.loads((PHASE7 / "PHASE7_BASELINE_CONFIRMED.json").read_text(encoding="utf-8"))
    evidence = json.loads((PHASE7 / "PHASE6_COS_BASELINE_EVIDENCE.json").read_text(encoding="utf-8"))
    snap = json.loads((PHASE7 / "PHASE6_COS_BASELINE_SNAPSHOT.json").read_text(encoding="utf-8"))

    base = confirmed["authoritative_baseline"]
    assert base["job_id"] == "e26c5919-0ac5-4aab-86f4-36def39ec882"
    assert base["selection_seed"] == 3236362228
    assert base["provider"] == "openai_compatible"
    assert base["experiment_kind"] == "llm_mention"
    assert base["retrieval_enabled"] is False
    assert base["paid_do_calls"] == 0
    assert confirmed["scores"]["aeo_health"] == 76.4
    assert confirmed["scores"]["entity"] == 52.5
    assert abs(confirmed["visibility"]["llm_mention_rate"] - (8 / 60)) < 1e-9
    assert confirmed["homepage_page_intelligence"]["h1"] is None
    assert confirmed["preferred_brand"] == "Nikhil Ikhar"

    assert evidence["job_id"] == base["job_id"]
    assert evidence["scores"]["aeo_health"] == 76.4
    assert evidence["query_set"]["seed"] == 3236362228
    assert abs(float(evidence["visibility"]["llm_mention_rate"]) - (8 / 60)) < 1e-9
    assert snap["selection_seed"] == 3236362228
    assert snap["mention_rate"] == pytest.approx(8 / 60)


def test_ready_to_publish_pack_implements_r1_r3_only():
    pack = json.loads((PHASE7 / "PHASE7_READY_TO_PUBLISH.json").read_text(encoding="utf-8"))
    md = (PHASE7 / "PHASE7_READY_TO_PUBLISH.md").read_text(encoding="utf-8")
    recs = json.loads((PHASE7 / "PHASE6_RECOMMENDATION_EXAMPLES.json").read_text(encoding="utf-8"))
    codes = {r["code"] for r in recs}

    assert pack["status"] == "NOT_PUBLISHED"
    assert "NOT PUBLISHED" in md
    assert set(pack["recommendations_implemented"]) == {
        "REC_CONSOLIDATE_BRAND_NAME",
        "REC_CLARIFY_BRAND_IN_COPY",
        "REC_FIX_HEADING_HIERARCHY",
    }
    assert set(pack["recommendations_implemented"]) <= codes
    assert pack["preferred_brand"] == "Nikhil Ikhar"
    assert pack["exact_h1_text"] == "Nikhil Ikhar"
    assert "Nikhil Ikhar writes practical guides" in pack["exact_lead_about_blurb"]
    assert pack["exact_meta_description"].startswith("Nikhil Ikhar:")

    ld = pack["json_ld"]
    assert ld["@context"] == "https://schema.org"
    types = {node["@type"] for node in ld["@graph"]}
    assert types == {"Person", "Organization"}
    for node in ld["@graph"]:
        assert node["name"] == "Nikhil Ikhar"
    # Valid JSON round-trip of injection payload
    html = pack["json_ld_injection_html"]
    assert '<script type="application/ld+json">' in html
    raw = html.split(">", 1)[1].rsplit("</script>", 1)[0].strip()
    parsed = json.loads(raw)
    assert parsed["@graph"][0]["name"] == "Nikhil Ikhar"

    before_after = {(b["before"], b["after"]) for b in pack["brand_string_replacements"]}
    assert ("Nikhil Ikhar's blog", "Nikhil Ikhar") in before_after


def test_live_brand_verify_still_unpublished_state():
    live = json.loads((PHASE7 / "PHASE7_LIVE_BRAND_VERIFY.json").read_text(encoding="utf-8"))
    assert live["publish_status"] == "NOT_PUBLISHED"
    assert live["observed"]["h1_count"] == 0
    assert live["preferred_brand_decision"]["preferred"] == "Nikhil Ikhar"
    assert live["still_matches_phase6_baseline"]["h1_null"] is True


def test_remeasure_options_lock_seed_and_refuse_paid():
    opts = baseline_remeasure_options()
    assert opts["selection_seed"] == DEFAULT_SEED == 3236362228
    assert opts["provider"] == "openai_compatible"
    assert opts["paid_retrieval_opt_in"] is False
    with pytest.raises(ValueError, match="ADR-026|paid_retrieval"):
        baseline_remeasure_options(paid_retrieval_opt_in=True)
    with pytest.raises(ValueError, match="openai_compatible"):
        baseline_remeasure_options(provider="digitalocean_web_search")


def test_remeasure_script_refuses_unpublished_by_default():
    assert SCRIPT.is_file()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "refusing_remeasure_until_published" in proc.stderr


def test_remeasure_script_print_options_only():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--print-options-only"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["options"]["selection_seed"] == 3236362228
    assert payload["options"]["provider"] == "openai_compatible"
    assert payload["options"]["paid_retrieval_opt_in"] is False
    assert payload["publish_status"]["published"] is False


def test_load_publish_status_helper():
    status = load_publish_status(PHASE7 / "PHASE7_PUBLISH_STATUS.json")
    assert status["published"] is False
