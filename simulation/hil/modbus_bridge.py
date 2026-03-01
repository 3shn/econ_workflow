"""
Protocol Bridge – Modbus TCP Server
=====================================
Maps microgrid physics outputs onto Modbus holding registers, mimicking
two proprietary device protocols:

  1. **Deep Sea Electronics (DSE) GenComm** – generator controller
     256-page architecture; page/register offset calculations.
  2. **Sungrow SG250HX** v1.1.53 – string inverter protocol
     Floats scaled to integers (e.g. 10.333 kW → register value 10333).

The server is implemented using **pymodbus ≥ 3.6** with
``StartAsyncTcpServer``.

Register map (all Holding Registers, FC3/FC16):
-----------------------------------------------
  DSE GenComm page/register scheme (page × 256 + register):
    Page 0, Reg 4    (addr   4) : Gen frequency × 10  [0.1 Hz / LSB]
    Page 0, Reg 5    (addr   5) : Gen voltage L-L × 10  [0.1 V / LSB]
    Page 0, Reg 8    (addr   8) : Gen active power × 10  [0.1 kW / LSB]
    Page 1, Reg 0    (addr 256) : Engine speed (RPM)
    Page 1, Reg 2    (addr 258) : Battery voltage × 10  [0.1 V / LSB]

  Sungrow v1.1.53 scheme (base address 5000):
    Addr 5000 : PV power total in Watts (integer); 10.333 kW → register 10333
    Addr 5001 : Grid frequency × 100  [0.01 Hz / LSB]
    Addr 5002 : BESS SoC × 10  [0.1 % / LSB]
    Addr 5003 : Total AC output (W as integer, ×1)
    Addr 5004 : DC bus voltage × 10  [0.1 V / LSB]
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# DSE GenComm helpers
# ──────────────────────────────────────────────────────────────────────────────

DSE_PAGE_SIZE = 256  # registers per page


def dse_address(page: int, register: int) -> int:
    """
    Compute the flat Modbus holding-register address from a DSE
    page/register pair using the 256-page architecture.

    Example::
        dse_address(0, 4)  → 4      (Page 0 frequency register)
        dse_address(1, 0)  → 256    (Page 1 base)
    """
    if page < 0 or register < 0 or register >= DSE_PAGE_SIZE:
        raise ValueError(
            f"Invalid DSE address: page={page}, register={register}. "
            f"register must be 0-{DSE_PAGE_SIZE - 1}."
        )
    return page * DSE_PAGE_SIZE + register


# ──────────────────────────────────────────────────────────────────────────────
# Sungrow helpers
# ──────────────────────────────────────────────────────────────────────────────

SUNGROW_BASE = 5000
SUNGROW_SCALE_KW = 1000   # kW → W (integer register value)


def sungrow_kw_to_int(kw: float) -> int:
    """
    Scale a kW float value to an integer register value.

    The Sungrow v1.1.53 protocol stores power in Watts (integer) so
    10.333 kW becomes the register value 10333.

    >>> sungrow_kw_to_int(10.333)
    10333
    >>> sungrow_kw_to_int(0.0)
    0
    """
    return max(0, round(kw * SUNGROW_SCALE_KW))


def sungrow_address(offset: int) -> int:
    """Absolute Modbus address from a Sungrow protocol offset."""
    return SUNGROW_BASE + offset


# ──────────────────────────────────────────────────────────────────────────────
# Register map builders
# ──────────────────────────────────────────────────────────────────────────────

def build_dse_registers(state: dict[str, Any]) -> dict[int, int]:
    """
    Build a dict of {modbus_address: register_value} for DSE GenComm
    registers from a physics-engine state dict.

    Expected state keys:
        freq_hz, voltage_kv, net_power_kw, bess_soc_pct
    """
    freq_hz = float(state.get("freq_hz", 50.0))
    voltage_kv = float(state.get("voltage_kv", 33.0))
    power_kw = float(state.get("net_power_kw", 0.0))
    soc_pct = float(state.get("bess_soc_pct", 80.0))

    # DSE register values (unsigned 16-bit)
    # Page 0: basic measurements
    gen_freq_reg = max(0, round(freq_hz * 10))       # 0.1 Hz LSB
    gen_volt_reg = max(0, round(voltage_kv * 10_000))  # 0.1 V LSB: 33 kV = 330,000 × 0.1 V → clamped to 65535
    gen_volt_reg = min(gen_volt_reg, 65535)
    gen_power_reg = max(0, round(abs(power_kw) * 10))  # 0.1 kW LSB

    # Page 1: secondary
    engine_rpm = 1500       # 4-pole, 50 Hz
    batt_v_reg = max(0, round(soc_pct * 2.4 * 10))   # proxy: 240 V at 100% SoC

    return {
        dse_address(0, 4): gen_freq_reg,
        dse_address(0, 5): gen_volt_reg,
        dse_address(0, 8): gen_power_reg,
        dse_address(1, 0): engine_rpm,
        dse_address(1, 2): batt_v_reg,
    }


def build_sungrow_registers(state: dict[str, Any]) -> dict[int, int]:
    """
    Build a dict of {modbus_address: register_value} for Sungrow v1.1.53
    registers.

    Expected state keys:
        pv_power_kw / P_ac_kW, freq_hz, bess_soc_pct, voltage_kv
    """
    pv_kw = float(
        state.get("pv_power_kw", state.get("P_ac_kW", 0.0))
    )
    freq_hz = float(state.get("freq_hz", 50.0))
    soc_pct = float(state.get("bess_soc_pct", 80.0))
    voltage_kv = float(state.get("voltage_kv", 33.0))

    # Sungrow: 10.333 kW → 10333 (kW × 1000 = W, stored as integer)
    pv_power_reg = sungrow_kw_to_int(pv_kw)
    freq_reg = max(0, round(freq_hz * 100))        # 0.01 Hz LSB
    soc_reg = max(0, round(soc_pct * 10))          # 0.1 % LSB
    ac_output_reg = pv_power_reg                   # W integer
    dc_bus_v_reg = max(0, round(voltage_kv * 10_000 * 10))  # 0.1 V LSB
    dc_bus_v_reg = min(dc_bus_v_reg, 65535)

    return {
        sungrow_address(0): pv_power_reg,
        sungrow_address(1): freq_reg,
        sungrow_address(2): soc_reg,
        sungrow_address(3): ac_output_reg,
        sungrow_address(4): dc_bus_v_reg,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Modbus TCP Server
# ──────────────────────────────────────────────────────────────────────────────

class ModbusBridge:
    """
    Asynchronous Modbus TCP server that exposes microgrid state to Modbus
    TCP clients (e.g. SCADA, HMI, or the EMS controller under test).

    Uses pymodbus ≥ 3.6 ``StartAsyncTcpServer``.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 5502) -> None:
        self.host = host
        self.port = port
        self._context: Any = None  # pymodbus ModbusServerContext

    def _build_context(self) -> Any:
        """Create a pymodbus server context with zeroed holding registers."""
        from pymodbus.datastore import (
            ModbusServerContext,
            ModbusDeviceContext,
            ModbusSequentialDataBlock,
        )

        # Allocate a flat 10 000-register holding register block
        hr_block = ModbusSequentialDataBlock(0, [0] * 10_000)
        device_ctx = ModbusDeviceContext(hr=hr_block)
        return ModbusServerContext(devices=device_ctx, single=True)

    def _write_registers(
        self, context: Any, addr_value_map: dict[int, int]
    ) -> None:
        """Write multiple register values into the server context."""
        for address, value in addr_value_map.items():
            context[0].setValues(3, address, [value])

    async def push_state(self, state: dict[str, Any]) -> None:
        """
        Update Modbus holding registers from a physics-engine state dict.

        Called after each mosaik step.
        """
        if self._context is None:
            self._context = self._build_context()

        dse_regs = build_dse_registers(state)
        sg_regs = build_sungrow_registers(state)

        self._write_registers(self._context, dse_regs)
        self._write_registers(self._context, sg_regs)
        logger.debug("Modbus registers updated: %d DSE + %d Sungrow",
                     len(dse_regs), len(sg_regs))

    async def serve(self) -> None:
        """Start the Modbus TCP server (runs indefinitely)."""
        from pymodbus.server import StartAsyncTcpServer

        if self._context is None:
            self._context = self._build_context()

        logger.info("Starting Modbus TCP server on %s:%d", self.host, self.port)
        await StartAsyncTcpServer(
            context=self._context,
            address=(self.host, self.port),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def _demo() -> None:
        bridge = ModbusBridge()
        demo_state = {
            "freq_hz": 50.02,
            "voltage_kv": 33.1,
            "net_power_kw": 150.0,
            "bess_soc_pct": 72.5,
            "P_ac_kW": 10.333,
        }
        await bridge.push_state(demo_state)
        print("DSE registers:", build_dse_registers(demo_state))
        print("Sungrow registers:", build_sungrow_registers(demo_state))

    asyncio.run(_demo())
