"""StrataBugs pipeline tests, including regressions for the two ported bugs."""

from pathlib import Path

from diskos.io.stratabugs import parse_stratabugs_simple
from diskos.palyno import reconcile
from diskos.palyno.aggregate import create_wide_format
from diskos.palyno.suggest import suggest_targets
from diskos.palyno.taxa import fuzzy_match_taxa, normalize_taxon_name_for_columns

SAMPLE = Path(__file__).parent / "data" / "diskos_sample" / "7_11-1_S.ASC"
TARGET = "Apectodinium homomorphum"
SIMILAR = "Apectodinium homomorphm"


def _available(obs):
    return sorted(obs["taxon_name"].dropna().unique().tolist())


def test_parse_samples_and_depths():
    parsed = parse_stratabugs_simple(SAMPLE)
    obs = parsed["observations"]
    assert not obs.empty
    assert set(obs["depth"].unique()) == {1000.0, 1050.0}
    # TAXA section built the id -> name map.
    assert parsed["taxa"]["103"] == "Azolla"


def test_normalize_strips_parentheses_regression():
    # Regression for the broken r'$[^)]*$' regex: the parenthetical author must go.
    result = normalize_taxon_name_for_columns(
        "Apectodinium homomorphum (Wetzel) Lentin & Williams 1977"
    )
    assert "Wetzel" not in result
    assert result == "Apectodinium_homomorphum"


def test_fuzzy_match_collapses_spelling_variant():
    available = ["Apectodinium homomorphum (Wetzel) Lentin & Williams 1977", "Apectodinium homomorphm"]
    matches = fuzzy_match_taxa("Apectodinium homomorphum", available, similarity_threshold=0.9)
    assert set(matches) == set(available)


def test_exact_variant_merges_but_similar_is_held_for_review():
    # Taxon 100 (exact genus+species) merges automatically; taxon 101 (a spelling
    # near-miss) is held apart pending a human decision, not silently merged.
    obs = parse_stratabugs_simple(SAMPLE)["observations"]
    result = reconcile.resolve_matches([TARGET], _available(obs))
    wide = create_wide_format(obs, result.mapping)
    col = "Apectodinium_homomorphum_cnt"
    assert wide.loc[1000.0, col] == 3  # only the exact variant (count 3)
    assert any(p.variant == SIMILAR for p in result.pending)


def test_recorded_decision_sums_counts_regression(tmp_path):
    # Once a human rules the similar name is the SAME, both variants merge and
    # counts SUM at the shared depth: 3 + 4 = 7 (regression for groupby.first()).
    obs = parse_stratabugs_simple(SAMPLE)["observations"]
    decisions = reconcile.Decisions(tmp_path / "dec.csv")
    decisions.set(TARGET, SIMILAR, reconcile.SAME)
    result = reconcile.resolve_matches([TARGET], _available(obs), decisions)
    wide = create_wide_format(obs, result.mapping)
    col = "Apectodinium_homomorphum_cnt"
    assert wide.loc[1000.0, col] == 7
    assert wide.loc[1050.0, col] == 5
    # Strongest abundance across the merged variants at 1000 is C (C > O).
    assert wide.loc[1000.0, "Apectodinium_homomorphum_abn"] == "C"


def test_suggest_ranks_by_prevalence():
    obs = parse_stratabugs_simple(SAMPLE)["observations"]
    suggestions = suggest_targets(obs, top_n=10)
    assert suggestions, "expected some suggestions"
    # Apectodinium homomorphum occurs at both depths -> ranks first.
    assert "Apectodinium" in suggestions[0].name
    depths = [s.n_depths for s in suggestions]
    assert depths == sorted(depths, reverse=True)
