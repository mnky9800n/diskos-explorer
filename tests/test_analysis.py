"""Analytical assistant: multi-log stats over a formation/interval (#24)."""

from pathlib import Path

from diskos import formations, npd, wells
from diskos.web import analysis

SAMPLE_ROOT = Path(__file__).parent / "data" / "diskos_sample"
NPD_SAMPLE = Path(__file__).parent / "data" / "npd_sample"


def _tops_and_records():
    return formations.load_formation_tops(NPD_SAMPLE), npd.load_factpages(NPD_SAMPLE)


def test_pick_curves():
    assert analysis.pick_curves(["GR", "RHOB", "DT", "FOO"]) == {
        "gamma": "GR", "density": "RHOB", "sonic": "DT",
    }


def test_compute_over_named_formation():
    tops, records = _tops_and_records()
    well = wells.well_files(SAMPLE_ROOT, "7_11-1")
    out = analysis.compute([well], formation="BALDER FM", tops_by_well=tops, records=records)
    assert out["target"] == "BALDER FM"
    assert len(out["per_well"]) == 1
    entry = out["per_well"][0]
    assert entry["interval"] == [1002.0, 1006.0]
    gr = entry["curves"]["gamma"]
    assert gr["mnemonic"] == "GR" and gr["n"] > 0 and "mean" in gr


def test_compute_over_interval_needs_no_tops():
    well = wells.well_files(SAMPLE_ROOT, "7_11-1")
    out = analysis.compute([well], top=1000, bottom=1004)
    assert out["per_well"][0]["curves"]["gamma"]["n"] >= 1


def test_compute_flags_wells_without_the_formation():
    tops, records = _tops_and_records()
    well = wells.well_files(SAMPLE_ROOT, "35_9-1")  # no logs, no tops
    out = analysis.compute([well], formation="BALDER FM", tops_by_well=tops, records=records)
    assert out["per_well"] == []
    assert out["missing"] == ["35_9-1"]


def test_analyze_adds_narrative_with_client():
    tops, records = _tops_and_records()
    well = wells.well_files(SAMPLE_ROOT, "7_11-1")

    class FakeClient:
        def ask(self, prompt, **kw):
            assert "BALDER FM" in prompt  # grounded in the computed target
            return "The gamma is low, suggesting clean sand."

    out = analysis.analyze(
        [well], formation="BALDER FM", tops_by_well=tops, records=records, client=FakeClient()
    )
    assert "clean sand" in out["narrative"]
