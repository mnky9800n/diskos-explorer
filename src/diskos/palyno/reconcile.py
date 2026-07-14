"""Human-in-the-loop reconciliation of taxon-name variants.

Different operators spell and qualify species names slightly differently. We do
NOT silently merge similar names. The rule (Jack's call):

  - Exact genus+species match (author/year ignored) -> automatically the SAME
    species. Author citations are not different taxa.
  - Merely SIMILAR names (a spelling near-miss, e.g. "homomorphm" vs
    "homomorphum") -> a human decides "same" or "different". Until decided, the
    variant is held apart (not merged) and surfaced for review.
  - Not similar enough -> different, ignored.

Decisions are persisted in a small CSV keyed by (target, variant), so a call is
made once and reused everywhere (CLI now, the web app later).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from .taxa import is_undifferentiated_or_spp

# A candidate must be at least this similar to be considered the same species at
# all. Between this and AUTO_SAME it is "similar" and needs a human decision.
REVIEW_THRESHOLD = 0.85
# At or above this, genus+species are effectively identical -> auto same.
AUTO_SAME_THRESHOLD = 1.0
# Undifferentiated / spp. targets match only other undiff taxa of the same genus.
UNDIFF_GENUS_THRESHOLD = 0.90

SAME = "same"
DIFFERENT = "different"


def _tokens(name: str) -> tuple[str, str | None]:
    parts = str(name).strip().split()
    genus = parts[0].lower() if parts else ""
    species = parts[1].lower() if len(parts) > 1 else None
    return genus, species


def candidate_similarity(target: str, variant: str) -> float | None:
    """Similarity of ``variant`` to ``target`` if it is a plausible same-species
    candidate, else None.

    Returns 1.0 for an exact genus+species match (author/year ignored), a value
    in [REVIEW_THRESHOLD, 1.0) for a similar name, or None if not a candidate.
    """
    t_genus, t_species = _tokens(target)
    v_genus, v_species = _tokens(variant)
    if not t_genus or not v_genus:
        return None

    genus_sim = SequenceMatcher(None, t_genus, v_genus).ratio()

    if is_undifferentiated_or_spp(target):
        if not is_undifferentiated_or_spp(variant):
            return None
        return genus_sim if genus_sim >= UNDIFF_GENUS_THRESHOLD else None

    if t_species is None:
        # Genus-only target: aggregate the whole genus.
        return genus_sim if genus_sim >= REVIEW_THRESHOLD else None

    if v_species is None:
        return None
    species_sim = SequenceMatcher(None, t_species, v_species).ratio()
    if genus_sim >= REVIEW_THRESHOLD and species_sim >= REVIEW_THRESHOLD:
        return min(genus_sim, species_sim)
    return None


@dataclass(frozen=True)
class PendingPair:
    """A similar name awaiting a human same/different decision."""

    target: str
    variant: str
    similarity: float


@dataclass
class MatchResult:
    # target -> variant names accepted as the same species (exact or decided "same")
    mapping: dict[str, list[str]]
    # similar names with no decision yet
    pending: list[PendingPair]


class Decisions:
    """Persistent store of human same/different calls, keyed by (target, variant)."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self._map: dict[tuple[str, str], str] = {}

    @classmethod
    def load(cls, path: Path | None) -> "Decisions":
        store = cls(path)
        if store.path and store.path.exists():
            with open(store.path, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    store._map[(row["target"], row["variant"])] = row["decision"]
        return store

    def get(self, target: str, variant: str) -> str | None:
        return self._map.get((target, variant))

    def set(self, target: str, variant: str, decision: str) -> None:
        if decision not in (SAME, DIFFERENT):
            raise ValueError(f"decision must be {SAME!r} or {DIFFERENT!r}, got {decision!r}")
        self._map[(target, variant)] = decision

    def save(self) -> None:
        if not self.path:
            raise ValueError("Decisions has no path to save to.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["target", "variant", "decision"])
            for (target, variant), decision in sorted(self._map.items()):
                writer.writerow([target, variant, decision])


def resolve_matches(
    targets: list[str],
    available_taxa: list[str],
    decisions: Decisions | None = None,
) -> MatchResult:
    """Match target taxa to the names present in the data, deferring similar
    names to recorded human decisions.
    """
    mapping: dict[str, list[str]] = {t: [] for t in targets}
    pending: list[PendingPair] = []

    for target in targets:
        for variant in available_taxa:
            sim = candidate_similarity(target, variant)
            if sim is None:
                continue
            if sim >= AUTO_SAME_THRESHOLD:
                mapping[target].append(variant)
                continue
            decision = decisions.get(target, variant) if decisions else None
            if decision == SAME:
                mapping[target].append(variant)
            elif decision == DIFFERENT:
                continue
            else:
                pending.append(PendingPair(target, variant, round(sim, 3)))

    return MatchResult(mapping=mapping, pending=pending)
