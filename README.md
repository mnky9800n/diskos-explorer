# diskosAI

Tools for working with data pulled from the Norwegian DISKOS petroleum database:
per-well palynology, well logs, and XRF, plus (later) an LLM wiki that situates
each well in the larger context of the whole corpus, delivered to domain users
through a web front end.

See `projectNotes.md` for the vision and `CLAUDE.md` for conventions. The full
roadmap lives in the approved plan; this README covers running Phase 1.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/). Never use pip or bare python.

```bash
uv sync              # create the venv and install deps
uv run pytest        # run the test suite (uses a committed sample, no SSH needed)
```

## Data

The real DISKOS data is not in this repo. It lives on `lambda-scalar` at
`//lambda-scalar/home/mnky9800n/data/DISKOS` (SSH-only, immutable). Two ways to run:

1. **On lambda-scalar** (full corpus): keep `prefer = "diskos_root"` in `config.toml`.
2. **Laptop dev**: rsync a few wells into `./data/DISKOS` and set
   `prefer = "local_sample"`, e.g.

   ```bash
   rsync -av --include='*/' --include='*.ASC' --include='*.LAS' --exclude='*' \
     lambda-scalar:/home/mnky9800n/data/DISKOS/ ./data/DISKOS/
   ```

You can also override the root ad hoc with the `DISKOS_ROOT` environment variable.

## Phase 1: palynology pipeline

```bash
# Which boreholes were discovered, and what data each has:
uv run diskos wells

# Parse .ASC StrataBugs exports -> match target species -> one wide CSV per well:
uv run diskos stratabugs --all --out out/
uv run diskos stratabugs --well 7_11-1 --out out/
```

Target species live in `src/diskos/palyno/targets.py`. Output CSVs are indexed by
depth with `<Species>_cnt` / `_abn` / `_p-out` / `_unct` columns.

Try it against the committed sample without any real data:

```bash
DISKOS_ROOT=./tests/data/diskos_sample uv run diskos stratabugs --all --out out/
```
