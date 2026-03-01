"""
Solar Power Profile Generator
==============================
Generates an AC power time-series for the 2.343 MWp PV array located
at the Kisengo mining site (approx. 7.3°S, 28.0°E, DRC).

Primary mode  : fetches Typical Meteorological Year (TMY) data from
                PVGIS via ``pvlib.iotools.get_pvgis_tmy``.
Fallback mode : synthesises a clear-sky irradiance profile, suitable
                for offline testing.

Output CSV columns:
  - datetime_utc : ISO-8601 timestamp (UTC)
  - ghi_Wm2      : Global Horizontal Irradiance (W/m²)
  - dni_Wm2      : Direct Normal Irradiance (W/m²)
  - dhi_Wm2      : Diffuse Horizontal Irradiance (W/m²)
  - temp_air_C   : Ambient air temperature (°C)
  - P_ac_kW      : Array AC output power (kW)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib
from pvlib.location import Location

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Site & array constants
# ──────────────────────────────────────────────────────────────────────────────
LATITUDE = -7.3          # °  (south is negative)
LONGITUDE = 28.0         # °
ALTITUDE_M = 1_250.0     # m  (Kisengo plateau)
TIMEZONE = "Africa/Lubumbashi"

# 2.343 MWp array – using STC 400 Wp modules arranged in 5_857 modules
ARRAY_POWER_WP = 2_343_000.0    # Wp
MODULE_POWER_WP = 400.0
N_MODULES = int(ARRAY_POWER_WP / MODULE_POWER_WP)   # 5857

# Inverter & wiring losses  → DC-to-AC derate
SYSTEM_LOSSES = 0.14    # 14 %  (IEC standard losses)
INVERTER_EFF = 0.97


def _get_pvgis_tmy() -> pd.DataFrame:
    """Attempt to fetch hourly TMY data from PVGIS (requires internet)."""
    tmy, _, _, _ = pvlib.iotools.get_pvgis_tmy(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        outputformat="json",
        usehorizon=True,
    )
    return tmy


def _generate_clearsky_tmy() -> pd.DataFrame:
    """
    Synthesise a full-year hourly irradiance profile using pvlib's
    Ineichen clear-sky model.  Used when PVGIS is unreachable.
    """
    loc = Location(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        tz=TIMEZONE,
        altitude=ALTITUDE_M,
        name="Kisengo",
    )
    times = pd.date_range(
        "2023-01-01", periods=8760, freq="h", tz=TIMEZONE
    ).tz_convert("UTC")
    clearsky = loc.get_clearsky(times)   # GHI, DNI, DHI
    tmy = pd.DataFrame(
        {
            "ghi": clearsky["ghi"],
            "dni": clearsky["dni"],
            "dhi": clearsky["dhi"],
            "temp_air": 25.0,            # constant proxy (°C)
            "wind_speed": 2.0,           # constant proxy (m/s)
        }
    )
    return tmy


def generate_pv_profile(
    use_tmy: bool = True,
    output_path: str | Path = "pv_profile.csv",
) -> pd.DataFrame:
    """
    Generate an hourly AC power time-series for the 2.343 MWp array.

    Parameters
    ----------
    use_tmy:
        If *True*, fetch TMY data from PVGIS.  Falls back automatically
        to the clear-sky model on network errors.
    output_path:
        Destination CSV file.  Pass ``None`` to skip writing.

    Returns
    -------
    pandas.DataFrame
        Columns: datetime_utc, ghi_Wm2, dni_Wm2, dhi_Wm2,
                 temp_air_C, P_ac_kW
    """
    # ── 1. Irradiance / weather data ─────────────────────────────────────────
    tmy: pd.DataFrame | None = None
    if use_tmy:
        try:
            logger.info("Fetching PVGIS TMY for Kisengo …")
            tmy = _get_pvgis_tmy()
            logger.info("PVGIS TMY fetched successfully.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("PVGIS fetch failed (%s) – using clear-sky model.", exc)

    if tmy is None:
        logger.info("Generating clear-sky TMY profile.")
        tmy = _generate_clearsky_tmy()

    # Normalise column names produced by PVGIS JSON format
    col_map = {
        "Gb(i)": "dni",
        "Gd(i)": "dhi",
        "G(i)": "ghi",
        "T2m": "temp_air",
        "WS10m": "wind_speed",
    }
    tmy = tmy.rename(columns=col_map)
    for col in ("ghi", "dni", "dhi"):
        if col not in tmy.columns:
            tmy[col] = 0.0
    if "temp_air" not in tmy.columns:
        tmy["temp_air"] = 25.0
    if "wind_speed" not in tmy.columns:
        tmy["wind_speed"] = 2.0

    # ── 2. pvlib PV model ────────────────────────────────────────────────────
    loc = Location(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        tz="UTC",
        altitude=ALTITUDE_M,
        name="Kisengo",
    )

    # Use pvlib's PVWatts model (no module database needed)
    # Tilt = |latitude| to maximise annual yield in southern hemisphere
    surface_tilt = abs(LATITUDE)
    surface_azimuth = 0.0  # facing North (southern hemisphere)

    # Solar position
    solar_pos = loc.get_solarposition(tmy.index)

    # Plane-of-array irradiance
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=surface_tilt,
        surface_azimuth=surface_azimuth,
        dni=tmy["dni"],
        ghi=tmy["ghi"],
        dhi=tmy["dhi"],
        solar_zenith=solar_pos["apparent_zenith"],
        solar_azimuth=solar_pos["azimuth"],
    )
    g_poa = poa["poa_global"].fillna(0.0).clip(lower=0.0)

    # Cell temperature (Faiman model)
    temp_cell = pvlib.temperature.faiman(
        g_poa,
        tmy["temp_air"],
        tmy.get("wind_speed", pd.Series(2.0, index=tmy.index)),
    )

    # PVWatts DC power (W) for the full array
    gamma_pdc = -0.0035   # %/°C – mono-PERC typical
    p_dc_w = pvlib.pvsystem.pvwatts_dc(
        g_poa,
        temp_cell,
        pdc0=ARRAY_POWER_WP,
        gamma_pdc=gamma_pdc,
    ).fillna(0.0).clip(lower=0.0)

    # PVWatts AC (inverter model)
    p_ac_w = pvlib.inverter.pvwatts(
        p_dc_w,
        pdc0=ARRAY_POWER_WP,
        eta_inv_nom=INVERTER_EFF,
    ).fillna(0.0).clip(lower=0.0)

    # Apply remaining system losses (wiring, soiling, etc.)
    p_ac_kw = p_ac_w * (1.0 - SYSTEM_LOSSES) / 1_000.0

    # ── 3. Assemble output DataFrame ─────────────────────────────────────────
    result = pd.DataFrame(
        {
            "datetime_utc": tmy.index.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ghi_Wm2": tmy["ghi"].values,
            "dni_Wm2": tmy["dni"].values,
            "dhi_Wm2": tmy["dhi"].values,
            "temp_air_C": tmy["temp_air"].values,
            "P_ac_kW": p_ac_kw.values,
        }
    )

    if output_path is not None:
        result.to_csv(output_path, index=False)
        logger.info("PV profile written to %s  (%d rows)", output_path, len(result))

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = generate_pv_profile(use_tmy=True)
    print(df.describe())
