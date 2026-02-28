# econ_workflow — Copilot Instructions

## What This Repo Is

IEEE 2030.7-2017 MEMS (Microgrid Energy Management System) for the Kisengo DRC microgrid.
Two independent layers that must stay in sync:

- **`logic/`** — XState v5 (TypeScript): the canonical MEMS controller state machine
- **`simulation/`** — Python: co-simulation (mosaik), hardware-in-the-loop (Modbus TCP bridge)

The SCXML file (`mems_core_logic.scxml`) is a **generated artifact** from `npm run export-scxml`. Never edit it directly.

## State Machine (`logic/mems_machine.ts`)

Six states following IEEE 2030.7 terminology:

```
INITIALIZE → SS1_GRID_CONNECTED ⇄ T1_PLANNED_ISLAND → SS2_STABLE_ISLAND
                    ↕ T2_UNPLANNED_ISLAND                      ↕ T3_RECONNECTION
```

Guard thresholds are domain constants (±0.5 Hz tolerance, BESS SOC ≥ 20%, sync slip ≤ 0.1 Hz). Any change must be reflected in both the XState guards **and** `MicrogridPhysics` in `simulation/hil/orchestrator.py`.

## Dev Commands

```bash
# TypeScript / XState
npm run test          # state + transition coverage via @xstate/graph shortest-paths
npm run export-scxml  # regenerate mems_core_logic.scxml from mems_machine.ts

# Python
uv run pytest

# Matches CI exactly
nix develop --no-pure-eval -c run-all-tests   # runs both npm test + pytest

# Generate CSV profiles for co-simulation (not committed; create before running orchestrator)
uv run python -m simulation.profiler.solar    # → pv_profile.csv
uv run python -m simulation.profiler.load     # → load_profile.csv

# Full co-simulation (requires mosaik + profiles)
uv run python -m simulation.hil.orchestrator
```

## Critical: Nix Flake File Visibility

**Nix cannot see unstaged files.** After creating any new file:

```bash
git add <filename>   # MUST do this before nix build / nix develop / nix flake check
```

Failure to stage will produce a misleading "file not found" error from Nix, not a git error.

## Dependency Management

**Python** — `uv` only. Never use `pip`, `poetry`, or `conda`.
- `uv add <pkg>` / `uv add --dev <pkg>`, then commit `uv.lock`
- Packages live in `pyproject.toml`; dev deps under `[dependency-groups] dev`

**Node** — `npm`. Dependencies declared in `package.json`.

**System tools / CLI utilities** — add to `packages = with pkgs; [ ... ]` in `flake.nix`. Never use `apt-get`, `brew`, or `nix-env -i`.

`shellHook` in `flake.nix` guards network calls with directory existence checks (`if [ ! -d ".venv" ]`) — preserve this pattern.

## Naming Conventions

All variable names must include units:
`freq_hz`, `voltage_kv`, `bess_soc_pct`, `pv_kw`, `load_kw`, `net_power_kw`, `batt_v_reg`

## Modbus Register Map (`simulation/hil/modbus_bridge.py`)

Two device protocols emulated:

- **DSE GenComm**: `dse_address(page, reg)` → page × 256 + offset. Frequency at page 0 reg 4, scaled ×10 (0.1 Hz/LSB).
- **Sungrow SG250HX v1.1.53**: base address 5000. `sungrow_kw_to_int(kw)` → kW × 1000 as integer (10.333 kW → 10333).

## Simulation Profiles

`pv_profile.csv` and `load_profile.csv` are not committed. Generate them with the profilers above before running the orchestrator. The solar profiler fetches TMY data from PVGIS (pvlib); it falls back to clear-sky synthesis offline. The load profiler synthesises a stochastic mining load (ventilation fans, dewatering pumps, rock crushers with inrush transients).

## CI (`.github/workflows/ci.yml`)

All test commands run via `nix develop --no-pure-eval -c <cmd>`. Key actions:
- `DeterminateSystems/determinate-nix-action@v3` — installs Nix; FlakeHub Cache built in
- `nix-community/cache-nix-action@v1` — fallback GHA cache
- `DeterminateSystems/flake-checker-action@main` — validates `flake.lock` health

Do not modify caching steps unless explicitly asked.

## Agent Workflow

1. Edit `.py`, `.ts`, or `.nix` files.
2. `git add .` — mandatory before any Nix command.
3. `nix develop --no-pure-eval -c run-all-tests`
4. Read output; iterate on failure.

Output analysis results as CSVs and PNGs. Do not invent Nix derivations for packages not in nixpkgs — flag the gap instead.

## Formal Verification (`verification/formal/`)

Planned pipeline:
1. `npm run export-scxml` → `mems_core_logic.scxml`
2. Translate SCXML to UPPAAL / TLA⁺ / NuSMV format
3. Verify IEEE 2030.7 §7 safety and liveness properties
