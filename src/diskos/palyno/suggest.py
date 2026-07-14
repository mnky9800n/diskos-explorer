"""Suggest candidate target species from the data, ranked by prevalence.

Rather than making Jack maintain a fixed target list, we look at what is actually
in the well(s) he is working on and suggest the species worth tracking, then let
him pick. "What he is doing" is, at minimum, which boreholes he is looking at.

This is the frequency-based version: rank taxa by how many depths they appear at
and their summed counts, collapsing author/spelling variants via the normalizer.
A future, richer version can use the model layer to suggest biostratigraphically
meaningful markers for a given formation/age/event (noted for the wiki phase).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import pandas as pd

from .taxa import normalize_taxon_name_for_columns


@dataclass
class TargetSuggestion:
    """One suggested target species, with the evidence for suggesting it."""

    name: str  # representative (most common) raw name for this taxon
    n_depths: int  # distinct depths it occurs at
    occurrences: int  # observation rows
    total_count: int  # summed numeric counts (0 if only presence/abundance)
    variants: list[str] = field(default_factory=list)  # raw name variants seen


def suggest_targets(obs_data: pd.DataFrame, top_n: int = 20) -> list[TargetSuggestion]:
    """Rank candidate targets in ``obs_data`` by prevalence (depths, then counts).

    Variants that normalize to the same canonical name are grouped together. The
    "Unknown" bucket (unparseable names) is dropped.
    """
    if obs_data.empty or "taxon_name" not in obs_data.columns:
        return []

    depths_by_key: dict[str, set] = defaultdict(set)
    rows_by_key: dict[str, int] = defaultdict(int)
    count_by_key: dict[str, float] = defaultdict(float)
    variant_rows: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    counts = pd.to_numeric(obs_data.get("count_value"), errors="coerce")

    for i, row in obs_data.reset_index(drop=True).iterrows():
        name = row.get("taxon_name")
        if not name or pd.isna(name):
            continue
        key = normalize_taxon_name_for_columns(name)
        if key == "Unknown":
            continue
        depths_by_key[key].add(row.get("depth"))
        rows_by_key[key] += 1
        value = counts.iloc[i]
        if pd.notna(value):
            count_by_key[key] += float(value)
        variant_rows[key][str(name)] += 1

    suggestions: list[TargetSuggestion] = []
    for key, depths in depths_by_key.items():
        variants = sorted(variant_rows[key], key=lambda n: variant_rows[key][n], reverse=True)
        suggestions.append(
            TargetSuggestion(
                name=variants[0],
                n_depths=len(depths),
                occurrences=rows_by_key[key],
                total_count=int(count_by_key[key]),
                variants=variants,
            )
        )

    suggestions.sort(key=lambda s: (s.n_depths, s.total_count, s.occurrences), reverse=True)
    return suggestions[:top_n]
