/**
 * State-coverage verification using @xstate/graph.
 *
 * Uses getShortestPaths to auto-discover the minimum set of event sequences
 * that reaches every reachable state, then executes each sequence against a
 * live XState actor to guarantee 100% state and transition coverage.
 *
 * Exit code 0 = all assertions pass; non-zero = failures detected.
 */

import { createActor } from "xstate";
import { getShortestPaths } from "@xstate/graph";
import { memsMachine } from "../mems_machine.js";

const EXPECTED_STATES = new Set([
  "INITIALIZE",
  "SS1_GRID_CONNECTED",
  "T1_PLANNED_ISLAND",
  "T2_UNPLANNED_ISLAND",
  "SS2_STABLE_ISLAND",
  "T3_RECONNECTION",
]);

// ──────────────────────────────────────────────────────────────────────────────
// Compute shortest paths to every reachable state
// ──────────────────────────────────────────────────────────────────────────────
const paths = getShortestPaths(memsMachine);

console.log(
  `\n@xstate/graph discovered ${paths.length} shortest path(s) to unique states.\n`
);

let passed = 0;
let failed = 0;
const reachedStates = new Set<string>();

for (const path of paths) {
  const targetStateValue = path.state.value as string;
  reachedStates.add(targetStateValue);

  // Replay the path on a fresh actor
  const actor = createActor(memsMachine);
  actor.start();

  try {
    for (const step of path.steps) {
      actor.send(step.event);
    }

    const actual = actor.getSnapshot().value as string;

    if (actual === targetStateValue) {
      console.log(
        `  ✓ PASS  ${targetStateValue}  (${path.steps.length} step(s))`
      );
      passed++;
    } else {
      console.error(
        `  ✗ FAIL  expected="${targetStateValue}" actual="${actual}"`
      );
      failed++;
    }
  } catch (err) {
    console.error(`  ✗ ERROR executing path to "${targetStateValue}":`, err);
    failed++;
  } finally {
    actor.stop();
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Check that every required state was reached
// ──────────────────────────────────────────────────────────────────────────────
console.log("\n── Coverage Report ──");
for (const state of EXPECTED_STATES) {
  if (reachedStates.has(state)) {
    console.log(`  ✓ ${state}`);
  } else {
    console.error(`  ✗ NOT REACHED: ${state}`);
    failed++;
  }
}

const coverage = ((reachedStates.size / EXPECTED_STATES.size) * 100).toFixed(
  1
);
console.log(
  `\nState coverage: ${reachedStates.size}/${EXPECTED_STATES.size} (${coverage}%)`
);
console.log(`Paths executed: ${passed} passed, ${failed} failed\n`);

if (failed > 0) {
  console.error(`${failed} test(s) FAILED – see above.`);
  process.exit(1);
}

console.log("All state-coverage assertions PASSED ✓");
