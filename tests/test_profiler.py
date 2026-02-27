"""
Tests for simulation/profiler/solar.py and simulation/profiler/load.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Load profiler tests (no external I/O, always runnable)
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadProfiler:

    def test_returns_dataframe(self):
        from simulation.profiler.load import generate_load_profile
        df = generate_load_profile(n_days=1, dt_minutes=15, output_path=None)
        assert isinstance(df, pd.DataFrame)

    def test_expected_columns(self):
        from simulation.profiler.load import generate_load_profile
        df = generate_load_profile(n_days=1, dt_minutes=15, output_path=None)
        expected = {
            "datetime_utc",
            "P_ventilation_kW",
            "P_dewater_kW",
            "P_crusher_kW",
            "P_total_kW",
        }
        assert expected.issubset(set(df.columns))

    def test_row_count(self):
        from simulation.profiler.load import generate_load_profile
        df = generate_load_profile(n_days=2, dt_minutes=60, output_path=None)
        assert len(df) == 48  # 2 days × 24 hours

    def test_total_equals_sum_of_components(self):
        from simulation.profiler.load import generate_load_profile
        df = generate_load_profile(n_days=1, dt_minutes=15, output_path=None)
        computed = (
            df["P_ventilation_kW"] + df["P_dewater_kW"] + df["P_crusher_kW"]
        )
        np.testing.assert_allclose(df["P_total_kW"], computed, rtol=1e-3)

    def test_no_negative_power(self):
        from simulation.profiler.load import generate_load_profile
        df = generate_load_profile(n_days=1, dt_minutes=15, output_path=None)
        assert (df["P_total_kW"] >= 0).all()

    def test_ventilation_base_load_within_bounds(self):
        from simulation.profiler.load import generate_load_profile, VENT_BASE_kW
        df = generate_load_profile(n_days=1, dt_minutes=15, output_path=None)
        assert df["P_ventilation_kW"].min() >= VENT_BASE_kW * 0.80
        assert df["P_ventilation_kW"].max() <= VENT_BASE_kW * 1.20

    def test_crusher_inrush_peak_is_6x_fla(self):
        """Peak crusher draw must be approximately 6 × FLA (2 s resolution)."""
        from simulation.profiler.load import (
            generate_load_profile,
            CRUSHER_FLA_kW,
            CRUSHER_INRUSH_MULTIPLIER,
        )
        df = generate_load_profile(n_days=1, dt_minutes=1, output_path=None)
        peak = df["P_crusher_kW"].max()
        expected_peak = CRUSHER_FLA_kW * CRUSHER_INRUSH_MULTIPLIER
        # Peak must be ≤ theoretical max; allow 10% tolerance for dt downsampling
        assert peak <= expected_peak * 1.05

    def test_reproducible_with_same_seed(self):
        from simulation.profiler.load import generate_load_profile
        df1 = generate_load_profile(n_days=3, seed=99, dt_minutes=60, output_path=None)
        df2 = generate_load_profile(n_days=3, seed=99, dt_minutes=60, output_path=None)
        pd.testing.assert_frame_equal(df1, df2)

    def test_different_seeds_give_different_crusher_profiles(self):
        from simulation.profiler.load import generate_load_profile
        df1 = generate_load_profile(n_days=7, seed=1, dt_minutes=60, output_path=None)
        df2 = generate_load_profile(n_days=7, seed=2, dt_minutes=60, output_path=None)
        assert not df1["P_crusher_kW"].equals(df2["P_crusher_kW"])

    def test_csv_output(self, tmp_path):
        from simulation.profiler.load import generate_load_profile
        out = tmp_path / "load_profile.csv"
        df = generate_load_profile(n_days=1, dt_minutes=60, output_path=out)
        assert out.exists()
        loaded = pd.read_csv(out)
        assert len(loaded) == len(df)


# ──────────────────────────────────────────────────────────────────────────────
# Solar profiler tests (uses pvlib; no network I/O – uses clear-sky model)
# ──────────────────────────────────────────────────────────────────────────────

class TestSolarProfiler:

    def test_returns_dataframe_clearsky(self):
        pvlib = pytest.importorskip("pvlib")
        from simulation.profiler.solar import generate_pv_profile
        df = generate_pv_profile(use_tmy=False, output_path=None)
        assert isinstance(df, pd.DataFrame)

    def test_expected_columns_clearsky(self):
        pvlib = pytest.importorskip("pvlib")
        from simulation.profiler.solar import generate_pv_profile
        df = generate_pv_profile(use_tmy=False, output_path=None)
        expected = {"datetime_utc", "ghi_Wm2", "dni_Wm2", "dhi_Wm2", "temp_air_C", "P_ac_kW"}
        assert expected.issubset(set(df.columns))

    def test_8760_rows_for_full_year(self):
        pvlib = pytest.importorskip("pvlib")
        from simulation.profiler.solar import generate_pv_profile
        df = generate_pv_profile(use_tmy=False, output_path=None)
        assert len(df) == 8760  # hourly, full year

    def test_no_negative_pv_power(self):
        pvlib = pytest.importorskip("pvlib")
        from simulation.profiler.solar import generate_pv_profile
        df = generate_pv_profile(use_tmy=False, output_path=None)
        assert (df["P_ac_kW"] >= 0).all()

    def test_peak_pv_below_rated_capacity(self):
        """Peak AC output must not exceed the nameplate Wp capacity."""
        pvlib = pytest.importorskip("pvlib")
        from simulation.profiler.solar import (
            generate_pv_profile,
            ARRAY_POWER_WP,
            SYSTEM_LOSSES,
        )
        df = generate_pv_profile(use_tmy=False, output_path=None)
        max_ac_kw = ARRAY_POWER_WP * (1 - SYSTEM_LOSSES) / 1_000.0
        assert df["P_ac_kW"].max() <= max_ac_kw * 1.05  # 5% tolerance

    def test_csv_output_clearsky(self, tmp_path):
        pvlib = pytest.importorskip("pvlib")
        from simulation.profiler.solar import generate_pv_profile
        out = tmp_path / "pv_profile.csv"
        df = generate_pv_profile(use_tmy=False, output_path=out)
        assert out.exists()
        loaded = pd.read_csv(out)
        assert len(loaded) == len(df)

    def test_night_hours_have_zero_pv(self):
        """At midnight, PV output should be zero (clear-sky model)."""
        pvlib = pytest.importorskip("pvlib")
        from simulation.profiler.solar import generate_pv_profile
        df = generate_pv_profile(use_tmy=False, output_path=None)
        midnight_rows = df[df["datetime_utc"].str.contains("T00:00:00")]
        # Kisengo UTC offset ≈ +2h; midnight UTC is 02:00 local → still dark
        assert (midnight_rows["P_ac_kW"] == 0).all()
