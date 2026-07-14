"""Taxon-name normalization and fuzzy matching.

Ported from Jack's ``StrataBugs_Read_Mod.ipynb``. The one behavioural fix is in
``normalize_taxon_name_for_columns``: the original parenthesis-stripping step used
``re.sub(r'$[^)]*$', '', name)`` (anchors, matches nothing), so parenthetical
author names were never removed. It now uses ``\\([^)]*\\)``.

The real aggregation driver is ``fuzzy_match_taxa``: it splits names into genus and
species and compares each with ``difflib.SequenceMatcher``, so spelling and author
variants from different operators collapse onto a single canonical target.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import pandas as pd

ABUNDANCE_UNDIFF_GENUS_THRESHOLD = 0.90


def normalize_taxon_name_for_columns(taxon_name: str | None) -> str:
    """Normalize a taxon name into a column-safe canonical form.

    Strips author names, years, qualifiers (cf./aff./sp./spp./var. ...),
    parenthetical content, sensu stricto/lato, group/complex, and undiff, then
    joins with underscores. Returns "Unknown" if nothing usable remains.
    """
    if not taxon_name or pd.isna(taxon_name):
        return "Unknown"

    name = str(taxon_name).strip()

    # Step 0: Add spaces after qualifiers that lack them (e.g. "sp.Foo").
    name = re.sub(r"(cf|aff|sp|spp)\.([a-zA-Z])", r"\1. \2", name)

    # Step 1: Remove s.s. / s.l. / sensu stricto / sensu lato.
    name = re.sub(r"\s+(s\.?\s*s\.?|sensu\s+stricto|strict)", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+(s\.?\s*l\.?|sensu\s+lato|latum)", "", name, flags=re.IGNORECASE)

    # Step 2: Remove qualifiers cf. aff. sp. spp. var. subsp. form f.
    name = re.sub(r"\s+(cf|aff|sp|spp|var|subsp|form|f)\.?\b", "", name, flags=re.IGNORECASE)

    # Step 3: Forward slashes -> space.
    name = re.sub(r"/", " ", name)

    # Step 4: Remove parenthetical content (usually author names).
    # FIX: original was r'$[^)]*$' (anchored, matched nothing).
    name = re.sub(r"\([^)]*\)", "", name)

    # Step 5: Remove author info (initials, "Lentin,J.", "& Williams", etc.).
    name = re.sub(r"\s+[A-Z][a-z]+,?\s*[A-Z]\.", "", name)
    name = re.sub(r"\s+[A-Z][a-z]+,?\s*[A-Z]\.?\s*[A-Z]\.?", "", name)

    # Years with possible author parts.
    name = re.sub(r",?\s*\d{4}\s*$", "", name)
    name = re.sub(r",?\s*\d{4}\s+", " ", name)

    # Standalone author initials without years.
    name = re.sub(r"\s+[A-Z]\.(?:[A-Z]\.)?(?:[A-Z]\.)?", "", name)

    # Author names separated by &.
    name = re.sub(r"\s+[A-Z][a-z]+\.?\s*&\s*[A-Z][a-z]+\.?", "", name)

    # Step 6: Trailing underscore author patterns.
    name = re.sub(r"\s*[A-Z_]+_[A-Z_]+_\d{4}\s*$", "", name)

    # Step 7: Leftover connectives / punctuation.
    name = re.sub(r"\s+&\s*$", "", name)
    name = re.sub(r"\s+[&,\.\-\_]+\s*$", "", name)

    # Step 8: group / complex indicators.
    name = re.sub(r"\s+(group|complex)\b", "", name, flags=re.IGNORECASE)

    # Step 9: undifferentiated suffix.
    name = re.sub(r"\s+undiff\.?\b", "", name, flags=re.IGNORECASE)

    # Step 10: collapse whitespace, then make a column-safe token.
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace(" ", "_")
    name = re.sub(r"[^\w_]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = re.sub(r"^_+|_+$", "", name)

    return name if name else "Unknown"


def is_undifferentiated_or_spp(taxon_name: str) -> bool:
    """True if the name is an undifferentiated / spp. / unidentified category."""
    name = str(taxon_name).lower().strip()
    undiff_patterns = [
        r"\bspp\.?\b",
        r"\bundiff\.?\b",
        r"\bundifferentiated",
        r"\bsp\.?\s*unidentified",
    ]
    return any(re.search(pattern, name) for pattern in undiff_patterns)


def fuzzy_match_taxa(
    target_taxon: str,
    available_taxa: list[str],
    similarity_threshold: float = 0.85,
) -> list[str]:
    """Return every taxon in ``available_taxa`` that matches ``target_taxon``.

    Genus is the first whitespace token, species the second. Matching rules:
      - Undifferentiated target: match only other undifferentiated taxa of the
        same genus (genus similarity >= 0.90).
      - Genus-only target: match on genus similarity >= threshold.
      - Genus+species target: both genus and species similarity >= threshold.
    """
    target_parts = str(target_taxon).strip().split()
    if not target_parts:
        return []

    target_genus = target_parts[0].lower()
    target_species = target_parts[1].lower() if len(target_parts) > 1 else None
    target_is_undiff = is_undifferentiated_or_spp(target_taxon)

    matches: list[str] = []
    for available_taxon in available_taxa:
        avail_parts = available_taxon.strip().split()
        if not avail_parts:
            continue

        avail_genus = avail_parts[0].lower()
        avail_species = avail_parts[1].lower() if len(avail_parts) > 1 else None
        genus_similarity = SequenceMatcher(None, target_genus, avail_genus).ratio()

        if target_is_undiff:
            if not is_undifferentiated_or_spp(available_taxon):
                continue
            if genus_similarity >= ABUNDANCE_UNDIFF_GENUS_THRESHOLD:
                matches.append(available_taxon)
            continue

        if target_species is None:
            if genus_similarity >= similarity_threshold:
                matches.append(available_taxon)
        else:
            if avail_species is None:
                continue
            species_similarity = SequenceMatcher(None, target_species, avail_species).ratio()
            if genus_similarity >= similarity_threshold and species_similarity >= similarity_threshold:
                matches.append(available_taxon)

    return matches


def find_all_matches_for_targets(
    available_taxa: list[str],
    target_taxa_list: list[str],
    similarity_threshold: float = 0.85,
) -> dict[str, list[str]]:
    """Map each target taxon to its matching variants in the data.

    Quiet counterpart of the notebook's diagnostic function (no printing).
    """
    return {
        target: fuzzy_match_taxa(target, available_taxa, similarity_threshold)
        for target in target_taxa_list
    }
