"""StrataBugs pipeline tests, including regressions for the two ported bugs."""

from pathlib import Path

import pandas as pd

from diskos.io.stratabugs import parse_stratabugs_simple
from diskos.palyno.aggregate import create_wide_format_with_target_matching
from diskos.palyno.taxa import fuzzy_match_taxa, normalize_taxon_name_for_columns

SAMPLE = Path(__file__).parent / "data" / "diskos_sample" / "7_11-1_S.ASC"


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


def test_aggregate_sums_counts_regression():
    # Two matched variants (taxa 100 and 101) both occur at depth 1000 with counts
    # 3 and 4. The old groupby('depth').first() returned 3; summing must give 7.
    parsed = parse_stratabugs_simple(SAMPLE)
    wide = create_wide_format_with_target_matching(
        parsed["observations"], ["Apectodinium homomorphum"], similarity_threshold=0.9
    )
    col = "Apectodinium_homomorphum_cnt"
    assert col in wide.columns
    assert wide.loc[1000.0, col] == 7
    assert wide.loc[1050.0, col] == 5


def test_aggregate_abundance_takes_strongest_code():
    # depth 1000 has codes C (rank 3) and O (rank 2); strongest is C.
    parsed = parse_stratabugs_simple(SAMPLE)
    wide = create_wide_format_with_target_matching(
        parsed["observations"], ["Apectodinium homomorphum"], similarity_threshold=0.9
    )
    assert wide.loc[1000.0, "Apectodinium_homomorphum_abn"] == "C"
    assert wide.loc[1050.0, "Apectodinium_homomorphum_abn"] == "A"
