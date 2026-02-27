# Formal Verification Stub

## Purpose

This directory is reserved for future **mathematical model checking** of the
MEMS core state machine (`mems_core_logic.scxml`) against formal specifications
derived from IEEE 2030.7-2017.

---

## What Formal Verification Would Validate

| Property | Description |
|---|---|
| **Reachability** | Every operating state (SS1, SS2) is reachable from INITIALIZE |
| **Safety** | The system never enters an undefined transition under any combination of measurement inputs |
| **Deadlock-freedom** | No state exists from which no event can cause a transition |
| **Liveness** | The system always eventually reaches a stable state (SS1 or SS2) |
| **Guard completeness** | For every grid disturbance event, exactly one guard is satisfiable |

---

## Recommended Toolchains

### 1. UPPAAL (timed automata)
- **Format**: UPPAAL XML (`.xml`)
- **Approach**: Model the MEMS state machine as a timed automaton with clock
  constraints for transition timing (e.g. maximum 2 s for T1 transfer).
- **Reference**: https://uppaal.org/

### 2. TChecker (timed automata, open-source)
- **Format**: TChecker description language (`.tck`)
- **Approach**: Import the SCXML states and events; add timing constraints.
- **Reference**: https://github.com/ticktac-project/tchecker

### 3. TLA⁺ / PlusCal (temporal logic)
- **Format**: `.tla` specification files
- **Approach**: Encode the state machine as a TLA⁺ `Next` predicate; use the
  TLC model checker to verify liveness and safety invariants.
- **Reference**: https://lamport.azurewebsites.net/tla/tla.html

### 4. NuSMV / nuXmv (symbolic model checker)
- **Format**: SMV modules (`.smv`)
- **Approach**: Translate the SCXML to SMV notation; verify CTL/LTL formulae
  such as `AG(SS2 -> AF(SS1 | SS2))`.

---

## Integration Path

1. Run `npm run export-scxml` to regenerate `mems_core_logic.scxml`.
2. Use a parser to translate SCXML → target tool format.
3. Add formal property specifications (invariants, fairness conditions).
4. Run the model checker and report any counter-examples.
5. Feed counter-examples back into the XState unit tests.

This process closes the loop between the executable simulation and formal
mathematical guarantees, fulfilling the verification requirements of
IEEE 2030.7 Section 7 (Microgrid Controller Functional Requirements).
