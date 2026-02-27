/**
 * MEMS Core Logic – IEEE 2030.7-2017 State Machine (XState v5)
 *
 * States:
 *   INITIALIZE        – Boot-up, waiting for stable grid
 *   SS1_GRID_CONNECTED – Steady-state: connected to utility grid
 *   T1_PLANNED_ISLAND  – Transition: planned islanding sequence
 *   T2_UNPLANNED_ISLAND– Transition: unplanned grid-fault response
 *   SS2_STABLE_ISLAND  – Steady-state: stable islanded microgrid
 *   T3_RECONNECTION    – Transition: re-synchronisation to grid
 */

import { createMachine, assign } from "xstate";

export interface MEMSContext {
  /** Grid voltage at PCC (kV) */
  grid_voltage: number;
  /** Grid frequency (Hz) */
  grid_frequency: number;
  /** Battery energy storage system state-of-charge (%) */
  bess_soc: number;
  /** PV array AC output (kW) */
  pv_power: number;
  /** Total microgrid load (kW) */
  load_power: number;
  /** Island-mode measured frequency (Hz) */
  island_frequency: number;
}

export type MEMSEvent =
  | { type: "GRID_AVAILABLE" }
  | { type: "PLANNED_ISLAND_COMMAND" }
  | { type: "GRID_FAULT" }
  | { type: "TRANSFER_COMPLETE" }
  | { type: "TRANSFER_FAILED" }
  | { type: "FREQUENCY_STABILIZED" }
  | { type: "ISLAND_FAILED" }
  | { type: "RECONNECTION_COMMAND" }
  | { type: "GRID_RESTORED" }
  | { type: "ISLAND_FAULT" }
  | { type: "SYNC_COMPLETE" }
  | { type: "SYNC_FAILED" }
  | {
      type: "UPDATE_CONTEXT";
      grid_voltage?: number;
      grid_frequency?: number;
      bess_soc?: number;
      pv_power?: number;
      load_power?: number;
      island_frequency?: number;
    };

export const memsMachine = createMachine(
  {
    id: "mems",
    types: {} as { context: MEMSContext; events: MEMSEvent },
    context: {
      grid_voltage: 33.0,
      grid_frequency: 50.0,
      bess_soc: 80.0,
      pv_power: 0.0,
      load_power: 500.0,
      island_frequency: 50.0,
    },
    initial: "INITIALIZE",
    states: {
      INITIALIZE: {
        on: {
          GRID_AVAILABLE: {
            target: "SS1_GRID_CONNECTED",
            guard: "gridVoltageAndFrequencyOk",
          },
        },
      },

      SS1_GRID_CONNECTED: {
        on: {
          PLANNED_ISLAND_COMMAND: {
            target: "T1_PLANNED_ISLAND",
            guard: "bessSOCAdequate",
          },
          GRID_FAULT: {
            target: "T2_UNPLANNED_ISLAND",
          },
          UPDATE_CONTEXT: {
            actions: "updateContext",
          },
        },
      },

      T1_PLANNED_ISLAND: {
        on: {
          TRANSFER_COMPLETE: {
            target: "SS2_STABLE_ISLAND",
            guard: "islandFrequencyStable",
          },
          TRANSFER_FAILED: {
            target: "SS1_GRID_CONNECTED",
          },
        },
      },

      T2_UNPLANNED_ISLAND: {
        on: {
          FREQUENCY_STABILIZED: {
            target: "SS2_STABLE_ISLAND",
            guard: "islandFrequencyStable",
          },
          ISLAND_FAILED: {
            target: "INITIALIZE",
          },
        },
      },

      SS2_STABLE_ISLAND: {
        on: {
          RECONNECTION_COMMAND: {
            target: "T3_RECONNECTION",
            guard: "gridVoltageRestored",
          },
          GRID_RESTORED: {
            target: "T3_RECONNECTION",
          },
          ISLAND_FAULT: {
            target: "T2_UNPLANNED_ISLAND",
          },
          UPDATE_CONTEXT: {
            actions: "updateContext",
          },
        },
      },

      T3_RECONNECTION: {
        on: {
          SYNC_COMPLETE: {
            target: "SS1_GRID_CONNECTED",
            guard: "syncConditionsMet",
          },
          SYNC_FAILED: {
            target: "SS2_STABLE_ISLAND",
          },
        },
      },
    },
  },
  {
    guards: {
      /** Grid voltage within ±10% of 33 kV and frequency within ±0.5 Hz */
      gridVoltageAndFrequencyOk: ({ context }) =>
        context.grid_voltage >= 30.0 &&
        context.grid_frequency >= 49.5 &&
        context.grid_frequency <= 50.5,

      /** BESS SOC must be ≥ 20% to sustain planned island */
      bessSOCAdequate: ({ context }) => context.bess_soc >= 20.0,

      /** Island frequency within ±0.5 Hz of 50 Hz */
      islandFrequencyStable: ({ context }) =>
        context.island_frequency >= 49.5 && context.island_frequency <= 50.5,

      /** Grid voltage adequate for reconnection */
      gridVoltageRestored: ({ context }) => context.grid_voltage >= 30.0,

      /** Voltage OK and frequency slip ≤ 0.1 Hz for synchronisation */
      syncConditionsMet: ({ context }) =>
        context.grid_voltage >= 30.0 &&
        Math.abs(context.grid_frequency - context.island_frequency) <= 0.1,
    },

    actions: {
      updateContext: assign(({ context, event }) => {
        if (event.type !== "UPDATE_CONTEXT") return {};
        return {
          ...(event.grid_voltage !== undefined && {
            grid_voltage: event.grid_voltage,
          }),
          ...(event.grid_frequency !== undefined && {
            grid_frequency: event.grid_frequency,
          }),
          ...(event.bess_soc !== undefined && { bess_soc: event.bess_soc }),
          ...(event.pv_power !== undefined && { pv_power: event.pv_power }),
          ...(event.load_power !== undefined && {
            load_power: event.load_power,
          }),
          ...(event.island_frequency !== undefined && {
            island_frequency: event.island_frequency,
          }),
        };
      }),
    },
  }
);
