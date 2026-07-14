"""Canonical target species lists (editable data, not logic).

These are the taxa of interest that the pipeline aggregates onto. Different
operators spell and qualify names slightly differently in the raw data; the fuzzy
matcher in ``taxa.py`` collapses those variants onto the canonical target here.

Edit these lists to change which species the pipeline extracts. If Jack ends up
changing them often, promote them to config.toml / a targets.yaml so he edits data
rather than Python (noted as an open decision in the plan).
"""

from __future__ import annotations

# The active list the pipeline uses by default.
TARGETS: list[str] = [
    "Apectodinium augustum",
    "Apectodinium cornufruticosum",
    "Apectodinium folliculum",
    "Apectodinium homomorphum",
    "Apectodinium hyperacanthum",
    "Apectodinium paniculatum",
    "Apectodinium parvum",
    "Apectodinium quinquelatum",
    "Apectodinium summissum",
    "Apectodinium tesselatum",
    "Apectodinium undiff",
    "Spiniferites ramosus",
    "Cerodinium wardenense",
    "Deflandrea oebisfeldensis",
    "Spinidium",
    "Areoligera",
    "Azolla",
]

APECTODINIUM_SPECIES: list[str] = [
    "Apectodinium augustum",
    "Apectodinium cornufruticosum",
    "Apectodinium folliculum",
    "Apectodinium homomorphum",
    "Apectodinium hyperacanthum",
    "Apectodinium paniculatum",
    "Apectodinium parvum",
    "Apectodinium quinquelatum",
    "Apectodinium summissum",
    "Apectodinium tesselatum",
    "Apectodinium undiff",
]

SPINIFERITES_SPECIES: list[str] = [
    "Spiniferites ramosus",
]

CERODINIUM_SPECIES: list[str] = [
    "Cerodinium wardenense",
]

DEFLANDREA_SPECIES: list[str] = [
    "Deflandrea oebisfeldensis",
]

SPINIDIUM_SPECIES: list[str] = [
    "Spinidium",
]

AREOLIGERA_SPECIES: list[str] = [
    "Areoligera",
]

AZOLLA_PARTS: list[str] = [
    "Azolla",
]
