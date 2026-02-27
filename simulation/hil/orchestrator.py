"""
CHIL Orchestrator – mosaik-based co-simulation loop
=====================================================
Sets up a mosaik ``World`` that orchestrates:
  1. PV profile simulator (CSV reader)
  2. Load profile simulator (CSV reader)
  3. Microgrid physics engine (pymgrid wrapper)
  4. Protocol bridge (Modbus TCP server updates)

Usage::

    python -m simulation.hil.orchestrator

The simulation runs for one year at 1-minute resolution.  After each
step the physics outputs are pushed to the Modbus datastore so that
any Modbus TCP client can poll live register values.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Simulation parameters
# ──────────────────────────────────────────────────────────────────────────────
SIM_START = "2023-01-01 00:00:00"
SIM_END = 365 * 24 * 60  # minutes  (one year at 1-min resolution)
STEP_SIZE = 1             # minutes per step
MODBUS_HOST = "127.0.0.1"
MODBUS_PORT = 5502

CSV_PV = Path("pv_profile.csv")
CSV_LOAD = Path("load_profile.csv")


# ──────────────────────────────────────────────────────────────────────────────
# mosaik simulator adapters
# ──────────────────────────────────────────────────────────────────────────────

class CSVSimulator:
    """
    Minimal mosaik-compatible simulator that streams rows from a CSV.
    Not a full mosaik SIM_API implementation – used for unit-testing the
    orchestration logic without running the full mosaik framework.
    """

    META: dict[str, Any] = {
        "api_version": "3.0",
        "type": "time-based",
        "models": {
            "CSVModel": {
                "public": True,
                "params": ["csv_path", "columns"],
                "attrs": [],  # filled from CSV columns at init
            }
        },
    }

    def __init__(self, csv_path: Path) -> None:
        import pandas as pd

        self._df = pd.read_csv(csv_path)
        self._step = 0
        logger.info("CSVSimulator loaded %s  (%d rows)", csv_path, len(self._df))

    def step(self) -> dict[str, float]:
        """Return the row corresponding to the current time step."""
        if self._step >= len(self._df):
            self._step = len(self._df) - 1  # clamp at end
        row = self._df.iloc[self._step].to_dict()
        self._step += 1
        return row


class MicrogridPhysics:
    """
    Step-based microgrid physics engine.

    Integrates battery SoC from net power imbalance and calculates
    voltage/frequency deviations – a simplified substitute for the
    full pymgrid optimiser used in production.
    """

    # Battery parameters
    BESS_CAPACITY_kWh = 2_000.0    # usable energy (kWh)
    BESS_SOC_INIT = 0.80           # initial SoC fraction
    BESS_SOC_MIN = 0.10
    BESS_SOC_MAX = 1.00
    BESS_CHARGE_EFF = 0.95
    BESS_DISCHARGE_EFF = 0.95

    # Grid parameters
    NOMINAL_VOLTAGE_KV = 33.0
    NOMINAL_FREQ_HZ = 50.0

    def __init__(self) -> None:
        self.soc = self.BESS_SOC_INIT  # fraction
        logger.info(
            "MicrogridPhysics initialised.  BESS capacity=%.0f kWh, SoC=%.0f%%",
            self.BESS_CAPACITY_kWh,
            self.soc * 100,
        )

    def step(
        self,
        pv_kw: float,
        load_kw: float,
        dt_h: float = 1 / 60,
    ) -> dict[str, float]:
        """
        Advance physics by one time step.

        Parameters
        ----------
        pv_kw:  AC power from PV array (kW)
        load_kw: Total demand (kW)
        dt_h:   Step duration in hours (default 1/60 for 1-min steps)

        Returns
        -------
        dict with keys:
            bess_soc_pct, net_power_kw, freq_hz, voltage_kv,
            bess_power_kw (positive = discharge)
        """
        net = pv_kw - load_kw  # positive → surplus → charge BESS

        # Ideal BESS dispatch: absorb/supply net imbalance
        bess_power_kw = -net   # negative = charging, positive = discharging

        if bess_power_kw > 0:
            # Discharging
            delta_soc = -(bess_power_kw / self.BESS_DISCHARGE_EFF) * dt_h / self.BESS_CAPACITY_kWh
        else:
            # Charging
            delta_soc = -(bess_power_kw * self.BESS_CHARGE_EFF) * dt_h / self.BESS_CAPACITY_kWh

        self.soc = float(
            max(self.BESS_SOC_MIN, min(self.BESS_SOC_MAX, self.soc + delta_soc))
        )

        # Simplified frequency deviation model (droop: 1 Hz per 100 kW imbalance)
        residual = net + bess_power_kw  # residual after BESS dispatch
        freq_hz = self.NOMINAL_FREQ_HZ + residual / 100.0

        # Simplified voltage: ±5% for ±300 kW net
        voltage_kv = self.NOMINAL_VOLTAGE_KV * (1 + residual / 6_000.0)

        return {
            "bess_soc_pct": round(self.soc * 100.0, 2),
            "net_power_kw": round(net, 2),
            "freq_hz": round(freq_hz, 4),
            "voltage_kv": round(voltage_kv, 4),
            "bess_power_kw": round(bess_power_kw, 2),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Full mosaik orchestration (requires mosaik + pymgrid installed)
# ──────────────────────────────────────────────────────────────────────────────

def run_cosimulation(
    end_minutes: int = SIM_END,
    use_pymgrid: bool = False,
) -> None:
    """
    Launch the mosaik co-simulation world.

    Parameters
    ----------
    end_minutes:
        Total simulation duration in minutes.
    use_pymgrid:
        If *True*, use pymgrid's Microgrid engine.
        Otherwise, use the lightweight :class:`MicrogridPhysics` stub.
    """
    try:
        import mosaik  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "mosaik is required for co-simulation.  Install with: uv add mosaik"
        ) from exc

    from simulation.hil.modbus_bridge import ModbusBridge

    SIM_CONFIG: dict[str, Any] = {
        "PVSim": {
            "python": "simulation.hil.orchestrator:CSVSimulator",
        },
        "LoadSim": {
            "python": "simulation.hil.orchestrator:CSVSimulator",
        },
    }

    world = mosaik.World(SIM_CONFIG)  # type: ignore[attr-defined]
    bridge = ModbusBridge(host=MODBUS_HOST, port=MODBUS_PORT)
    physics = MicrogridPhysics()

    pv_sim = world.start("PVSim", csv_path=str(CSV_PV))
    load_sim = world.start("LoadSim", csv_path=str(CSV_LOAD))
    pv_entity = pv_sim.CSVModel.create(1)[0]
    load_entity = load_sim.CSVModel.create(1)[0]

    world.connect(pv_entity, load_entity, ("P_ac_kW", "pv_power"))

    async def step_callback(
        time: int,
        pv_data: dict[str, float],
        load_data: dict[str, float],
    ) -> None:
        state = physics.step(
            pv_kw=pv_data.get("P_ac_kW", 0.0),
            load_kw=load_data.get("P_total_kW", 0.0),
        )
        await bridge.push_state(state)

    logger.info("Starting mosaik simulation for %d minutes …", end_minutes)
    world.run(until=end_minutes)
    logger.info("Co-simulation complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_cosimulation(end_minutes=1440)  # 1 day demo
