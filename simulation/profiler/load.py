"""
Mining Load Profile Generator
==============================
Synthesises a stochastic industrial load time-series for a DRC hard-rock
mining operation (e.g. the Kisengo lithium project).

Load components:
  1. **Ventilation fans**  – continuous base load, slow drift
  2. **Dewatering pumps**  – semi-continuous, scheduled batch
  3. **Rock crushers**     – intermittent; exhibit severe induction-motor
                             inrush transients up to 6× FLA before decaying
                             exponentially to running load

Output CSV columns:
  - datetime_utc      : ISO-8601 timestamp (UTC)
  - P_ventilation_kW  : Ventilation fans (kW)
  - P_dewater_kW      : Dewatering pumps (kW)
  - P_crusher_kW      : Rock crushers incl. start transients (kW)
  - P_total_kW        : Sum of all loads (kW)
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Plant parameters
# ──────────────────────────────────────────────────────────────────────────────

# Ventilation (3 × 110 kW fans)
VENT_BASE_kW = 330.0
VENT_NOISE_STD = 10.0   # slow thermal drift (kW)

# Dewatering pumps (2 × 75 kW)
DEWATER_RUNNING_kW = 150.0
DEWATER_CYCLE_h = 4.0   # pump runs for a block, then rests

# Rock crushers (primary + secondary – total FLA = 250 kW running)
CRUSHER_FLA_kW = 250.0
CRUSHER_INRUSH_MULTIPLIER = 6.0            # 6 × FLA at t=0
CRUSHER_INRUSH_DECAY_S = 2.5              # exponential time-constant (s)
CRUSHER_STARTS_PER_DAY = 8               # number of start events per day
CRUSHER_RUN_DURATION_H = 1.5             # each run ≈ 90 minutes


def _inrush_envelope(
    duration_s: int,
    fla_kw: float,
    multiplier: float,
    decay_tau_s: float,
    dt_s: float = 1.0,
) -> np.ndarray:
    """
    Asymmetric induction-motor inrush current profile.

    The instantaneous power at time *t* (seconds after start) is:

        P(t) = FLA × [ 1 + (M-1) × exp(-t / τ) ]

    where M = ``multiplier`` and τ = ``decay_tau_s``.
    """
    t = np.arange(0, duration_s, dt_s)
    return fla_kw * (1.0 + (multiplier - 1.0) * np.exp(-t / decay_tau_s))


def generate_load_profile(
    n_days: int = 365,
    seed: int = 42,
    dt_minutes: int = 1,
    output_path: str | Path = "load_profile.csv",
) -> pd.DataFrame:
    """
    Generate a stochastic mining load time-series.

    Parameters
    ----------
    n_days:
        Simulation length in days.
    seed:
        Random seed for reproducibility.
    dt_minutes:
        Time-step resolution (minutes).  Default 1 min.
    output_path:
        Destination CSV file.  Pass ``None`` to skip writing.

    Returns
    -------
    pandas.DataFrame
        Columns: datetime_utc, P_ventilation_kW, P_dewater_kW,
                 P_crusher_kW, P_total_kW
    """
    rng = np.random.default_rng(seed)
    dt_s = dt_minutes * 60.0
    steps_per_hour = 60 // dt_minutes
    total_steps = n_days * 24 * steps_per_hour

    times = pd.date_range(
        "2023-01-01 00:00:00", periods=total_steps, freq=f"{dt_minutes}min", tz="UTC"
    )

    # ── 1. Ventilation fans ──────────────────────────────────────────────────
    # Slow random walk with clipping
    noise = rng.normal(0.0, VENT_NOISE_STD / np.sqrt(steps_per_hour), total_steps)
    p_vent = np.full(total_steps, VENT_BASE_kW) + np.cumsum(noise)
    p_vent = np.clip(p_vent, VENT_BASE_kW * 0.85, VENT_BASE_kW * 1.15)
    # Reset drift every day
    for d in range(n_days):
        start = d * 24 * steps_per_hour
        end = start + 24 * steps_per_hour
        p_vent[start:end] -= p_vent[start:end].mean() - VENT_BASE_kW

    # ── 2. Dewatering pumps ──────────────────────────────────────────────────
    p_dewater = np.zeros(total_steps)
    cycle_steps = int(DEWATER_CYCLE_h * steps_per_hour)
    # Pump on for first half of each cycle
    for i in range(total_steps):
        cycle_pos = i % (2 * cycle_steps)
        if cycle_pos < cycle_steps:
            p_dewater[i] = DEWATER_RUNNING_kW

    # ── 3. Rock crusher with inrush transients ───────────────────────────────
    p_crusher = np.zeros(total_steps)
    run_steps = int(CRUSHER_RUN_DURATION_H * steps_per_hour)
    # Pre-compute 1-second inrush profile then downsample to dt_minutes
    inrush_1s = _inrush_envelope(
        duration_s=int(run_steps * dt_s),
        fla_kw=CRUSHER_FLA_kW,
        multiplier=CRUSHER_INRUSH_MULTIPLIER,
        decay_tau_s=CRUSHER_INRUSH_DECAY_S,
        dt_s=1.0,
    )
    # Downsample to dt_minutes resolution by averaging windows
    n_s_per_step = int(dt_s)
    inrush_ds_len = len(inrush_1s) // n_s_per_step
    inrush_ds = inrush_1s[: inrush_ds_len * n_s_per_step].reshape(
        inrush_ds_len, n_s_per_step
    ).mean(axis=1)
    inrush_ds = np.clip(inrush_ds, 0, None)

    # Schedule crusher starts across each day
    for d in range(n_days):
        day_start = d * 24 * steps_per_hour
        # Random start offsets within the day (non-overlapping)
        available = list(range(24 * steps_per_hour - run_steps))
        rng.shuffle(available)
        starts = []
        for s in available:
            if not starts or all(abs(s - x) >= inrush_ds_len for x in starts):
                starts.append(s)
            if len(starts) == CRUSHER_STARTS_PER_DAY:
                break
        starts.sort()
        for s in starts:
            global_start = day_start + s
            end = min(global_start + inrush_ds_len, total_steps)
            seg = inrush_ds[: end - global_start]
            p_crusher[global_start:end] += seg

    # ── 4. Assemble DataFrame ────────────────────────────────────────────────
    result = pd.DataFrame(
        {
            "datetime_utc": times.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "P_ventilation_kW": np.round(p_vent, 2),
            "P_dewater_kW": np.round(p_dewater, 2),
            "P_crusher_kW": np.round(p_crusher, 2),
            "P_total_kW": np.round(p_vent + p_dewater + p_crusher, 2),
        }
    )

    if output_path is not None:
        result.to_csv(output_path, index=False)
        logger.info(
            "Load profile written to %s  (%d rows, %.1f-day horizon)",
            output_path,
            len(result),
            n_days,
        )

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = generate_load_profile(n_days=1, dt_minutes=1)
    print(df.head(10))
    print(f"\nPeak load: {df['P_total_kW'].max():.1f} kW")
    print(f"Base load (median): {df['P_total_kW'].median():.1f} kW")
