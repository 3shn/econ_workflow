"""
Tests for simulation/hil/orchestrator.py and simulation/hil/modbus_bridge.py
"""

from __future__ import annotations

import asyncio

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Modbus Bridge – protocol mapping tests (no server started)
# ──────────────────────────────────────────────────────────────────────────────

class TestDSEGencommProtocol:

    def test_dse_address_page_0(self):
        from simulation.hil.modbus_bridge import dse_address
        assert dse_address(0, 0) == 0
        assert dse_address(0, 4) == 4
        assert dse_address(0, 255) == 255

    def test_dse_address_page_1(self):
        from simulation.hil.modbus_bridge import dse_address, DSE_PAGE_SIZE
        assert dse_address(1, 0) == DSE_PAGE_SIZE        # 256
        assert dse_address(1, 2) == DSE_PAGE_SIZE + 2    # 258

    def test_dse_address_page_255(self):
        from simulation.hil.modbus_bridge import dse_address, DSE_PAGE_SIZE
        assert dse_address(255, 0) == 255 * DSE_PAGE_SIZE

    def test_dse_address_invalid_register(self):
        from simulation.hil.modbus_bridge import dse_address
        with pytest.raises(ValueError):
            dse_address(0, 256)  # register must be 0-255

    def test_build_dse_registers_keys(self):
        from simulation.hil.modbus_bridge import build_dse_registers
        state = {"freq_hz": 50.0, "voltage_kv": 33.0, "net_power_kw": 100.0, "bess_soc_pct": 80.0}
        regs = build_dse_registers(state)
        assert isinstance(regs, dict)
        assert len(regs) == 5

    def test_dse_frequency_scaling(self):
        """Frequency register = freq_hz × 10 (0.1 Hz LSB)."""
        from simulation.hil.modbus_bridge import build_dse_registers, dse_address
        state = {"freq_hz": 49.8, "voltage_kv": 33.0, "net_power_kw": 0.0, "bess_soc_pct": 50.0}
        regs = build_dse_registers(state)
        assert regs[dse_address(0, 4)] == 498

    def test_dse_register_values_are_non_negative(self):
        from simulation.hil.modbus_bridge import build_dse_registers
        state = {"freq_hz": 50.0, "voltage_kv": 33.0, "net_power_kw": -500.0, "bess_soc_pct": 80.0}
        regs = build_dse_registers(state)
        for addr, val in regs.items():
            assert val >= 0, f"Register {addr} has negative value {val}"

    def test_dse_register_values_fit_16bit(self):
        from simulation.hil.modbus_bridge import build_dse_registers
        state = {"freq_hz": 50.0, "voltage_kv": 33.0, "net_power_kw": 2500.0, "bess_soc_pct": 100.0}
        regs = build_dse_registers(state)
        for addr, val in regs.items():
            assert 0 <= val <= 65535, f"Register {addr} value {val} out of 16-bit range"


class TestSungrowProtocol:

    def test_sungrow_kw_to_int_example(self):
        """10.333 kW → 10333 (the canonical example from the spec)."""
        from simulation.hil.modbus_bridge import sungrow_kw_to_int
        assert sungrow_kw_to_int(10.333) == 10333

    def test_sungrow_kw_to_int_zero(self):
        from simulation.hil.modbus_bridge import sungrow_kw_to_int
        assert sungrow_kw_to_int(0.0) == 0

    def test_sungrow_kw_to_int_large(self):
        from simulation.hil.modbus_bridge import sungrow_kw_to_int
        assert sungrow_kw_to_int(2343.0) == 2_343_000

    def test_sungrow_kw_to_int_no_negatives(self):
        from simulation.hil.modbus_bridge import sungrow_kw_to_int
        assert sungrow_kw_to_int(-5.0) == 0

    def test_sungrow_address_base(self):
        from simulation.hil.modbus_bridge import sungrow_address, SUNGROW_BASE
        assert sungrow_address(0) == SUNGROW_BASE
        assert sungrow_address(4) == SUNGROW_BASE + 4

    def test_build_sungrow_registers_keys(self):
        from simulation.hil.modbus_bridge import build_sungrow_registers
        state = {"P_ac_kW": 500.0, "freq_hz": 50.0, "bess_soc_pct": 75.0, "voltage_kv": 33.0}
        regs = build_sungrow_registers(state)
        assert len(regs) == 5

    def test_sungrow_frequency_register(self):
        """Frequency register = freq_hz × 100 (0.01 Hz LSB)."""
        from simulation.hil.modbus_bridge import build_sungrow_registers, sungrow_address
        state = {"P_ac_kW": 0.0, "freq_hz": 50.05, "bess_soc_pct": 80.0, "voltage_kv": 33.0}
        regs = build_sungrow_registers(state)
        assert regs[sungrow_address(1)] == 5005  # 50.05 × 100

    def test_sungrow_soc_register(self):
        """SoC register = soc_pct × 10 (0.1 % LSB)."""
        from simulation.hil.modbus_bridge import build_sungrow_registers, sungrow_address
        state = {"P_ac_kW": 0.0, "freq_hz": 50.0, "bess_soc_pct": 72.5, "voltage_kv": 33.0}
        regs = build_sungrow_registers(state)
        assert regs[sungrow_address(2)] == 725


# ──────────────────────────────────────────────────────────────────────────────
# Microgrid Physics Engine tests
# ──────────────────────────────────────────────────────────────────────────────

class TestMicrogridPhysics:

    def test_soc_decreases_when_load_exceeds_pv(self):
        from simulation.hil.orchestrator import MicrogridPhysics
        phy = MicrogridPhysics()
        initial_soc = phy.soc
        # Load >> PV → BESS must discharge → SoC decreases
        result = phy.step(pv_kw=100.0, load_kw=800.0)
        assert phy.soc < initial_soc

    def test_soc_increases_when_pv_exceeds_load(self):
        from simulation.hil.orchestrator import MicrogridPhysics
        phy = MicrogridPhysics()
        phy.soc = 0.5  # start at 50%
        result = phy.step(pv_kw=1500.0, load_kw=100.0)
        assert phy.soc > 0.5

    def test_soc_clamped_at_minimum(self):
        from simulation.hil.orchestrator import MicrogridPhysics
        phy = MicrogridPhysics()
        phy.soc = MicrogridPhysics.BESS_SOC_MIN + 0.001
        for _ in range(200):
            phy.step(pv_kw=0.0, load_kw=2000.0, dt_h=1.0)
        assert phy.soc >= MicrogridPhysics.BESS_SOC_MIN

    def test_soc_clamped_at_maximum(self):
        from simulation.hil.orchestrator import MicrogridPhysics
        phy = MicrogridPhysics()
        phy.soc = 0.99
        for _ in range(100):
            phy.step(pv_kw=3000.0, load_kw=0.0, dt_h=1.0)
        assert phy.soc <= MicrogridPhysics.BESS_SOC_MAX

    def test_output_keys(self):
        from simulation.hil.orchestrator import MicrogridPhysics
        phy = MicrogridPhysics()
        result = phy.step(pv_kw=500.0, load_kw=400.0)
        for key in ("bess_soc_pct", "net_power_kw", "freq_hz", "voltage_kv", "bess_power_kw"):
            assert key in result, f"Missing key: {key}"

    def test_balanced_system_near_nominal_frequency(self):
        """When PV ≈ load, frequency should be close to 50 Hz."""
        from simulation.hil.orchestrator import MicrogridPhysics
        phy = MicrogridPhysics()
        result = phy.step(pv_kw=500.0, load_kw=500.0)
        assert abs(result["freq_hz"] - 50.0) < 0.1


# ──────────────────────────────────────────────────────────────────────────────
# Modbus Bridge – push_state integration (no TCP server)
# ──────────────────────────────────────────────────────────────────────────────

class TestModbusBridgePushState:

    def test_push_state_updates_dse_registers(self):
        pymodbus = pytest.importorskip("pymodbus")
        from simulation.hil.modbus_bridge import ModbusBridge, dse_address
        bridge = ModbusBridge()
        state = {
            "freq_hz": 49.8,
            "voltage_kv": 33.0,
            "net_power_kw": 200.0,
            "bess_soc_pct": 65.0,
            "P_ac_kW": 300.0,
        }
        asyncio.run(bridge.push_state(state))
        # Verify DSE frequency register
        freq_reg = bridge._context[0].getValues(3, dse_address(0, 4), count=1)[0]
        assert freq_reg == round(49.8 * 10)  # 498

    def test_push_state_updates_sungrow_registers(self):
        pymodbus = pytest.importorskip("pymodbus")
        from simulation.hil.modbus_bridge import ModbusBridge, sungrow_address, sungrow_kw_to_int
        bridge = ModbusBridge()
        state = {
            "freq_hz": 50.0,
            "voltage_kv": 33.0,
            "net_power_kw": 0.0,
            "bess_soc_pct": 80.0,
            "P_ac_kW": 10.333,
        }
        asyncio.run(bridge.push_state(state))
        pv_reg = bridge._context[0].getValues(3, sungrow_address(0), count=1)[0]
        assert pv_reg == sungrow_kw_to_int(10.333)  # 10333
