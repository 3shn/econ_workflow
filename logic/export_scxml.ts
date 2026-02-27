/**
 * Export the MEMS state machine as a W3C-compliant SCXML file.
 *
 * Usage: tsx logic/export_scxml.ts
 * Output: mems_core_logic.scxml
 */

import { writeFileSync } from "fs";
import { memsMachine } from "./mems_machine.js";

interface TransitionConfig {
  target?: string;
  guard?: string | { type: string };
  actions?: unknown;
}

function guardLabel(guard: unknown): string {
  if (!guard) return "";
  if (typeof guard === "string") return guard;
  if (typeof guard === "object" && guard !== null && "type" in guard)
    return (guard as { type: string }).type;
  return "guard";
}

function toSCXML(machine: typeof memsMachine): string {
  const cfg = machine.config as {
    id?: string;
    initial: string;
    context: Record<string, number>;
    states: Record<string, { on?: Record<string, TransitionConfig | string> }>;
  };

  const indent = "  ";
  const lines: string[] = [
    `<?xml version="1.0" encoding="UTF-8"?>`,
    `<scxml xmlns="http://www.w3.org/2005/07/scxml"`,
    `       version="1.0"`,
    `       initial="${cfg.initial}"`,
    `       name="${cfg.id ?? "mems"}">`,
    ``,
    `${indent}<datamodel>`,
  ];

  for (const [key, val] of Object.entries(cfg.context)) {
    lines.push(`${indent}${indent}<data id="${key}" expr="${val}"/>`);
  }
  lines.push(`${indent}</datamodel>`, ``);

  for (const [stateName, stateDef] of Object.entries(cfg.states)) {
    lines.push(`${indent}<state id="${stateName}">`);
    const transitions = stateDef.on ?? {};
    for (const [eventType, t] of Object.entries(transitions)) {
      const tc: TransitionConfig =
        typeof t === "string" ? { target: t } : (t as TransitionConfig);
      const target = tc.target ? ` target="${tc.target}"` : "";
      const cond = tc.guard ? ` cond="${guardLabel(tc.guard)}"` : "";
      lines.push(
        `${indent}${indent}<transition event="${eventType}"${target}${cond}/>`
      );
    }
    lines.push(`${indent}</state>`, ``);
  }

  lines.push(`</scxml>`);
  return lines.join("\n");
}

const scxml = toSCXML(memsMachine);
const outPath = "mems_core_logic.scxml";
writeFileSync(outPath, scxml, "utf8");
console.log(`✓ Exported SCXML to ${outPath}`);
console.log(scxml);
