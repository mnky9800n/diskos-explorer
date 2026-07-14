"""Parser for StrataBugs ASCII (.ASC) palynology exports.

Ported from Jack's ``StrataBugs_Read_Mod.ipynb``. Behaviour is preserved; the
changes are: the hardcoded ``os.chdir`` is gone (paths are arguments), the bare
``except`` is removed, and unused imports are dropped.

Format (StrataBugs ASCII export, latin-1):
  - The file is split into sections by lines containing the keywords TAXA,
    SAMPLES, ABNSCHME.
  - TAXA section: ``<taxon_id>\\t<taxon name ...>`` -> an id->name dictionary.
  - SAMPLES section, one leading character per line:
      S <depth> <sample_type> <param1> [<param2>]   (space separated)
      D <data_type> [<sample_method>]
      T\\t<taxon_id>\\t<tokens...>                    (tab separated)
    In a T line the tokens after the id are classified positionally:
      '?' -> uncertainty, '+' -> present-outside-sample,
      one of R/O/C/A/SA -> abundance code, a numeric token -> count value,
      anything else -> an additional code.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ABUNDANCE_CODES = {"R", "O", "C", "A", "SA"}

OBSERVATION_COLUMNS = [
    "depth",
    "sample_type",
    "taxon_id",
    "taxon_name",
    "uncertainty",
    "abundance_code",
    "present_outside_sample",
    "count_value",
    "additional_code",
]


def parse_taxon_line_simple(line: str) -> dict:
    """Parse one ``T`` (taxon observation) line into a dict of fields."""
    if line.startswith("T"):
        line = line[1:].lstrip()

    parts = [p.strip() for p in line.split("\t") if p.strip() != ""]

    taxon_id = parts[0] if parts else None
    abundance_code = None
    present_outside = None
    count_value = None
    uncertainty = None
    additional_code = None

    for part in parts[1:]:
        if part == "?":
            uncertainty = "?"
        elif part == "+":
            present_outside = "+"
        elif part in ABUNDANCE_CODES:
            abundance_code = part
        elif part.replace(".", "", 1).isdigit():
            count_value = part
        else:
            additional_code = part

    return {
        "taxon_id": taxon_id,
        "uncertainty": uncertainty,
        "abundance_code": abundance_code,
        "present_outside_sample": present_outside,
        "count_value": count_value,
        "additional_code": additional_code,
    }


def parse_stratabugs_simple(file_path: str | Path) -> dict:
    """Parse a StrataBugs ``.ASC`` file.

    Returns a dict with keys:
      samples      -- list of per-sample dicts (depth, sample_type, observations, ...)
      observations -- a tidy DataFrame (one row per taxon observation)
      taxa         -- {taxon_id: taxon_name}
      sections     -- the raw section line lists (header/taxa/samples/abundance)
    """
    sections: dict[str, list[str]] = {
        "header": [],
        "taxa": [],
        "samples": [],
        "abundance": [],
    }

    with open(file_path, "r", encoding="latin-1") as handle:
        current_section = "header"
        for line in handle:
            line = line.rstrip("\n\r")

            if "TAXA" in line:
                current_section = "taxa"
                continue
            if "SAMPLES" in line:
                current_section = "samples"
                continue
            if "ABNSCHME" in line:
                current_section = "abundance"
                continue

            if line.strip():
                sections[current_section].append(line)

    # --- Parse the SAMPLES section ---
    sample_data: list[dict] = []
    current_sample: dict | None = None
    current_data_type: str | None = None
    current_sample_method: str | None = None

    for line in sections["samples"]:
        if line.startswith("S"):
            if current_sample:
                sample_data.append(current_sample.copy())

            parts = line.split()
            current_sample = {
                "depth": float(parts[1]),
                "sample_type": parts[2],
                "param1": parts[3] if len(parts) > 3 else None,
                "param2": parts[4] if len(parts) > 4 else None,
                "data_type": current_data_type,
                "sample_method": current_sample_method,
                "observations": [],
            }
            current_data_type = None
            current_sample_method = None

        elif line.startswith("D") and current_sample:
            parts = line.split()
            if len(parts) >= 2:
                current_data_type = parts[1]
                current_sample_method = parts[2] if len(parts) > 2 else None
                current_sample["data_type"] = current_data_type
                current_sample["sample_method"] = current_sample_method

        elif line.startswith("T") and current_sample:
            parsed_obs = parse_taxon_line_simple(line)
            parsed_obs["depth"] = current_sample["depth"]
            parsed_obs["sample_type"] = current_sample["sample_type"]
            current_sample["observations"].append(parsed_obs)

    if current_sample:
        sample_data.append(current_sample)

    all_observations = [obs for sample in sample_data for obs in sample["observations"]]
    obs_df = pd.DataFrame(all_observations)

    # --- Parse the TAXA section into an id -> name dictionary ---
    taxa_dict: dict[str, str] = {}
    for line in sections["taxa"]:
        parts = [p.strip() for p in line.split("\t") if p.strip()]
        if len(parts) >= 2 and parts[0].replace(".", "", 1).isdigit():
            taxa_dict[parts[0]] = " ".join(parts[1:])

    if not obs_df.empty:
        obs_df["taxon_name"] = obs_df["taxon_id"].map(taxa_dict)
        available_cols = [c for c in OBSERVATION_COLUMNS if c in obs_df.columns]
        obs_df = obs_df[available_cols].copy()

    return {
        "samples": sample_data,
        "observations": obs_df,
        "taxa": taxa_dict,
        "sections": sections,
    }
