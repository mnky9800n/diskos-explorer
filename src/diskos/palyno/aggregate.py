"""Build the wide per-well palynology table (depth x target taxon).

Takes an already-decided ``taxa_mapping`` (target -> accepted variant names) from
``reconcile.resolve_matches``, so name reconciliation (including any human
same/different calls) happens upstream and this module only aggregates.

The count data-loss bug from the notebook is fixed here: matched variants at a
shared depth are SUMMED, not collapsed with ``groupby('depth').first()``.

Per-column aggregation semantics (count is unambiguous; the others are
provisional and flagged for Jack, see the plan's open decisions):
  _cnt   : sum of counts across matched variants at that depth.
  _abn   : highest-ranked abundance code present (R < O < C < A < SA).
  _p-out : "+" if any matched variant is present-outside-sample at that depth.
  _unct  : "?" if any matched variant is marked uncertain at that depth.
"""

from __future__ import annotations

import pandas as pd

# Abundance codes ordered from least to most abundant. Used to pick the
# strongest code when several variants coincide at one depth.
ABUNDANCE_RANK = {"R": 1, "O": 2, "C": 3, "A": 4, "SA": 5}
_RANK_TO_CODE = {rank: code for code, rank in ABUNDANCE_RANK.items()}


def _sum_counts(subset: pd.DataFrame, index: pd.Index) -> pd.Series:
    counts = pd.to_numeric(subset["count_value"], errors="coerce")
    # min_count=1 keeps depths with no numeric count as NaN rather than 0.
    return counts.groupby(subset["depth"]).sum(min_count=1).reindex(index)


def _max_abundance(subset: pd.DataFrame, index: pd.Index) -> pd.Series:
    ranks = subset["abundance_code"].map(ABUNDANCE_RANK)
    top = ranks.groupby(subset["depth"]).max().reindex(index)
    return top.map(_RANK_TO_CODE)


def _any_flag(subset: pd.DataFrame, column: str, flag: str, index: pd.Index) -> pd.Series:
    present = subset[column].eq(flag).groupby(subset["depth"]).any().reindex(index)
    return present.map(lambda x: flag if x else pd.NA)


def create_wide_format(
    obs_data: pd.DataFrame,
    taxa_mapping: dict[str, list[str]],
) -> pd.DataFrame:
    """Return a wide DataFrame indexed by depth, one group of columns per target.

    Args:
        obs_data: tidy observations from ``parse_stratabugs_simple``.
        taxa_mapping: target -> list of variant names accepted as that target
            (from ``reconcile.resolve_matches().mapping``).

    Columns are ``<Target_Name>_cnt`` (and ``_abn`` / ``_p-out`` / ``_unct`` where
    data exists). Targets with no accepted variants contribute no columns.
    """
    if obs_data.empty:
        return pd.DataFrame()

    depths = sorted(obs_data["depth"].dropna().unique())
    wide = pd.DataFrame(index=pd.Index(depths, name="depth"))

    have_count = "count_value" in obs_data.columns
    have_abund = "abundance_code" in obs_data.columns
    have_present = "present_outside_sample" in obs_data.columns
    have_uncert = "uncertainty" in obs_data.columns

    for target, variants in taxa_mapping.items():
        if not variants:
            continue

        subset = obs_data[obs_data["taxon_name"].isin(variants)]
        if subset.empty:
            continue

        canonical = target.replace(" ", "_")

        if have_count:
            wide[f"{canonical}_cnt"] = _sum_counts(subset, wide.index)
        if have_abund:
            wide[f"{canonical}_abn"] = _max_abundance(subset, wide.index)
        if have_present and subset["present_outside_sample"].eq("+").any():
            wide[f"{canonical}_p-out"] = _any_flag(
                subset, "present_outside_sample", "+", wide.index
            )
        if have_uncert and subset["uncertainty"].eq("?").any():
            wide[f"{canonical}_unct"] = _any_flag(subset, "uncertainty", "?", wide.index)

    return wide
