"""Reconciliation tests: exact = auto same, similar = human decision."""

from diskos.palyno import reconcile

TARGET = "Apectodinium homomorphum"
EXACT = "Apectodinium homomorphum (Wetzel) Lentin & Williams 1977"
SIMILAR = "Apectodinium homomorphm"


def test_exact_match_is_auto_same():
    # Author/year differences are not a different taxon.
    assert reconcile.candidate_similarity(TARGET, EXACT) == 1.0


def test_similar_name_falls_in_review_band():
    sim = reconcile.candidate_similarity(TARGET, SIMILAR)
    assert sim is not None
    assert reconcile.REVIEW_THRESHOLD <= sim < reconcile.AUTO_SAME_THRESHOLD


def test_unrelated_name_is_not_a_candidate():
    assert reconcile.candidate_similarity(TARGET, "Azolla") is None


def test_resolve_auto_merges_exact_defers_similar():
    result = reconcile.resolve_matches([TARGET], [EXACT, SIMILAR])
    assert EXACT in result.mapping[TARGET]
    assert SIMILAR not in result.mapping[TARGET]
    assert [p.variant for p in result.pending] == [SIMILAR]


def test_decision_same_merges_similar(tmp_path):
    decisions = reconcile.Decisions(tmp_path / "dec.csv")
    decisions.set(TARGET, SIMILAR, reconcile.SAME)
    result = reconcile.resolve_matches([TARGET], [EXACT, SIMILAR], decisions)
    assert SIMILAR in result.mapping[TARGET]
    assert not result.pending


def test_decision_different_excludes_similar(tmp_path):
    decisions = reconcile.Decisions(tmp_path / "dec.csv")
    decisions.set(TARGET, SIMILAR, reconcile.DIFFERENT)
    result = reconcile.resolve_matches([TARGET], [EXACT, SIMILAR], decisions)
    assert SIMILAR not in result.mapping[TARGET]
    assert not result.pending


def test_decisions_persist_roundtrip(tmp_path):
    path = tmp_path / "dec.csv"
    decisions = reconcile.Decisions(path)
    decisions.set(TARGET, SIMILAR, reconcile.SAME)
    decisions.save()
    reloaded = reconcile.Decisions.load(path)
    assert reloaded.get(TARGET, SIMILAR) == reconcile.SAME
