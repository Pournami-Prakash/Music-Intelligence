"""Source-level guards for result provenance and durable shared URLs.

These intentionally test the central composition points rather than CSS or
rendered pixels; browser walkthroughs remain the visual acceptance layer.
"""

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text()


def test_premium_pages_render_the_evidence_contract_and_share_control():
    premium = source("components/Premium.jsx")
    evidence = source("components/EvidencePanel.jsx")

    assert "<EvidencePanel" in premium
    assert "FEATURE_EVIDENCE[pathname]" in premium
    assert "<ShareResult" in evidence
    assert "Confidence basis" in evidence


def test_priority_result_pages_restore_their_shared_inputs():
    expected = {
        "pages/ArtistHabitat.jsx": ["readSharedParam('artist')", "replaceSharedParams({ artist:"],
        "pages/MoodMap.jsx": ["readSharedParam('mood')", "replaceSharedParams({ mood:"],
        "pages/TimeCapsule.jsx": ["readSharedParam('era')", "replaceSharedParams({ era:"],
        "pages/PlaylistLanguage.jsx": ["readSharedParam('playlist')", "replaceSharedParams({ playlist:"],
        "pages/PlaylistForensics.jsx": ["readSharedParam('playlist')", "replaceSharedParams({ playlist:"],
        "pages/SoundtrackGift.jsx": ["readSharedParam('brief')", "params={{ brief:"],
        "pages/TransitionFinder.jsx": ["readSharedParam('from')", "readSharedParam('to')", "params={{ from:"],
        "pages/PlaylistDoppelganger.jsx": ["readSharedParam('artist')", "replaceSharedParams({ artist:"],
    }

    for page, tokens in expected.items():
        page_source = source(page)
        for token in tokens:
            assert token in page_source, f"{page} is missing shared-state contract: {token}"


def test_overlap_arena_has_a_durable_two_artist_result_url():
    arena = source("pages/OverlapArena.jsx")

    assert "readSharedParam('a')" in arena
    assert "readSharedParam('b')" in arena
    assert "replaceSharedParams({ a:" in arena
