import { describe, expect, it } from "vitest";

import rawGameData from "../game-data/s01_v2_game.json";
import { simulatePath } from "./gameEngine";
import type { ChoiceId, GameData, WitnessOutcome } from "./types";

// Parity guard: the web engine is a second implementation of consequence
// semantics. These tests assert that the archetype paths named in the
// export's path_rules land in the same outcome class as the harness
// witnesses they were derived from, so the two implementations cannot
// drift silently. Parity is class-level (success/failure, cost side of
// the ceiling, week side of the deadline), not exact dollars: the web
// effects are intentionally simplified.

const data = rawGameData as GameData;
const SUCCESS_COST_CEILING_USD = 102_000_000;
const SUCCESS_DEADLINE_WEEK = 48;

function uniformChoices(choiceId: ChoiceId): Record<string, ChoiceId> {
  return Object.fromEntries(
    Object.keys(data.decision_nodes).map((nodeId) => [nodeId, choiceId])
  );
}

function witnessFor(pathRule: string): WitnessOutcome {
  const fixtureName = data.path_rules[pathRule];
  const witness = data.witnesses[fixtureName];
  if (!witness) {
    throw new Error(`path rule ${pathRule} points at unknown witness ${fixtureName}`);
  }
  return witness;
}

function expectOutcomeClassParity(
  pathRule: string,
  choiceId: ChoiceId
): void {
  const witness = witnessFor(pathRule);
  const outcome = simulatePath(data, uniformChoices(choiceId));

  expect(outcome.projectSuccess).toBe(witness.project_success === true);
  expect(outcome.state.cost_usd <= outcome.state.success_cost_ceiling_usd).toBe(
    (witness.final_project_cost ?? Number.POSITIVE_INFINITY) <= SUCCESS_COST_CEILING_USD
  );
  expect(outcome.state.completion_week <= outcome.state.success_deadline_week).toBe(
    (witness.completion_tick ?? Number.POSITIVE_INFINITY) <= SUCCESS_DEADLINE_WEEK
  );
}

describe("witness parity guard", () => {
  it("maps every path rule to an exported witness", () => {
    for (const fixtureName of Object.values(data.path_rules)) {
      expect(data.witnesses[fixtureName]).toBeDefined();
    }
  });

  it("keeps the all-balanced path in its harness witness outcome class", () => {
    expectOutcomeClassParity("all_balanced", "balanced");
  });

  it("keeps the all-conservative path in its harness witness outcome class", () => {
    expectOutcomeClassParity("all_conservative", "conservative");
  });

  it("keeps an all-self-protective path in the coordination-failure class", () => {
    const witness = witnessFor("two_or_more_self_protective");
    const outcome = simulatePath(data, uniformChoices("self_protective"));

    expect(witness.project_success).toBe(false);
    expect(outcome.projectSuccess).toBe(false);
    expect(outcome.status).toBe("non_viable");
  });
});
