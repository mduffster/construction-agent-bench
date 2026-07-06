import { describe, expect, it } from "vitest";

import rawGameData from "../game-data/s01_v2_game.json";
import {
  advanceRound,
  buildGameTrace,
  createInitialGameState,
  evaluateGame,
  isComplete,
  recordTrust,
  roleNodes,
  selectChoice,
  trustCalibration,
} from "./gameEngine";
import type { AgentId, ChoiceId, GameData, GameState } from "./types";

const data = rawGameData as GameData;

function playChoices(role: AgentId, choices: ChoiceId[]): GameState {
  let state = createInitialGameState(data, role);
  roleNodes(data, role).forEach((node, index) => {
    state = selectChoice(data, state, node.node_id, choices[index]);
    state = advanceRound(data, state);
  });
  return state;
}

function playFirstRound(role: AgentId, choice: ChoiceId): GameState {
  let state = createInitialGameState(data, role);
  const [firstNode] = roleNodes(data, role);
  state = selectChoice(data, state, firstNode.node_id, choice);
  return state;
}

describe("S01 V2 public human game engine", () => {
  it("exposes four playable roles while retaining six scenario organizations", () => {
    expect(data.playable_roles).toEqual([
      "steel_supplier",
      "gc",
      "owner",
      "labor_subcontractor",
    ]);
    expect(data.system_roles).toEqual(["lender", "inspector"]);
    expect(Object.keys(data.roles).sort()).toEqual(
      ["gc", "inspector", "labor_subcontractor", "lender", "owner", "steel_supplier"].sort()
    );
    expect(() => createInitialGameState(data, "inspector")).toThrow(/system role/);
  });

  it("lets every playable role complete three stateful rounds", () => {
    for (const role of data.playable_roles) {
      const state = playChoices(role, ["balanced", "balanced", "balanced"]);
      const evaluation = evaluateGame(data, state);
      expect(isComplete(data, state)).toBe(true);
      expect(evaluation.trace).toHaveLength(3);
      expect(evaluation.projectSuccess).toBe(true);
      expect(evaluation.state.release_value_usd).toBeGreaterThanOrEqual(950_000);
      expect(evaluation.state.labor_capacity).not.toBe("uncommitted");
    }
  });

  it("makes player choices change the project state", () => {
    const balanced = playChoices("steel_supplier", ["balanced", "balanced", "balanced"]);
    const lateLotB = playChoices("steel_supplier", [
      "balanced",
      "self_protective",
      "self_protective",
    ]);

    const balancedEvaluation = evaluateGame(data, balanced);
    const lateEvaluation = evaluateGame(data, lateLotB);

    expect(lateEvaluation.state.completion_week).toBeGreaterThan(
      balancedEvaluation.state.completion_week
    );
    expect(lateEvaluation.projectSuccess).toBe(false);
    expect(lateEvaluation.state.blockers.join(" ")).toMatch(/Lot B|cash gap|release/i);
  });

  it("branches non-player moves from current state", () => {
    const balanced = buildGameTrace(data, playFirstRound("steel_supplier", "balanced"))[0];
    const thinDisclosure = buildGameTrace(
      data,
      playFirstRound("steel_supplier", "self_protective")
    )[0];
    const balancedMoves = Object.fromEntries(
      balanced.moves.map((move) => [move.actorId, move.choiceId])
    );
    const thinMoves = Object.fromEntries(
      thinDisclosure.moves.map((move) => [move.actorId, move.choiceId])
    );

    expect(balanced.moves).toHaveLength(6);
    expect(thinDisclosure.moves).toHaveLength(6);
    expect(balancedMoves.gc).toBe("balanced");
    expect(thinMoves.gc).toBe("conservative");
    expect(thinMoves.inspector).toBe("conservative");
    expect(thinMoves.lender).not.toBe(balancedMoves.lender);
    expect(thinDisclosure.stateAfter.story_flags).toContain("supplier_thin_disclosure");
  });

  it("makes later counterparties react to player funding and labor choices", () => {
    const ownerNoSupport = buildGameTrace(data, playFirstRound("owner", "self_protective"))[0];
    const laborReleased = evaluateGame(
      data,
      playChoices("labor_subcontractor", [
        "self_protective",
        "self_protective",
        "self_protective",
      ])
    );

    expect(
      ownerNoSupport.moves.find((move) => move.actorId === "lender")?.choiceId
    ).toBe("self_protective");
    expect(
      laborReleased.trace[1].moves.find((move) => move.actorId === "gc")?.choiceId
    ).toBe("self_protective");
    expect(laborReleased.projectSuccess).toBe(false);
  });

  it("uses distinct private tradeoffs for each supplier round", () => {
    const supplierStakeText = roleNodes(data, "steel_supplier").map((node) =>
      node.private_stakes.join(" ")
    );

    expect(new Set(supplierStakeText).size).toBe(3);
    expect(supplierStakeText[0]).toMatch(/request|disclosure/i);
    expect(supplierStakeText[1]).toMatch(/outside work|margin/i);
    expect(supplierStakeText[2]).toMatch(/shipping|reporting/i);
  });

  it("keeps trust ratings out of outcome resolution", () => {
    const initial = playChoices("gc", ["balanced", "conservative", "balanced"]);
    const before = evaluateGame(data, initial);
    const afterTrust = recordTrust(data, initial, "steel_supplier", 1);
    const after = evaluateGame(data, afterTrust);

    expect(afterTrust.trustRatings.steel_supplier).toBe(1);
    expect(after.state).toEqual(before.state);
    expect(after.playerPayoff).toBe(before.playerPayoff);
  });

  it("includes ideal and model comparison data", () => {
    const state = playChoices("labor_subcontractor", [
      "balanced",
      "balanced",
      "balanced",
    ]);
    const evaluation = evaluateGame(data, state);

    expect(evaluation.idealOutcome.final_project_cost).toBe(95_650_000);
    expect(evaluation.modelOutcome?.final_project_cost).toBeGreaterThanOrEqual(95_000_000);
  });

  it("rates every counterparty in the trust calibration", () => {
    const state = playChoices("steel_supplier", ["balanced", "balanced", "balanced"]);
    const calibration = trustCalibration(data, state);

    expect(calibration.entries).toHaveLength(5);
    expect(calibration.total).toBe(5);
    for (const entry of calibration.entries) {
      expect(entry.actorId).not.toBe("steel_supplier");
      expect(["cooperative", "reaction_to_risk", "independent_caution"]).toContain(entry.driver);
      expect(entry.read.length).toBeGreaterThan(0);
    }
  });

  it("reads a low rating of a risk-reacting partner as a misread", () => {
    // Thin disclosure creates package risk; counterparties turn defensive in
    // response, so a low trust rating of one is a calibration miss.
    let state = playChoices("steel_supplier", [
      "self_protective",
      "self_protective",
      "self_protective",
    ]);
    state = recordTrust(data, state, "lender", 1);
    const calibration = trustCalibration(data, state);
    const lender = calibration.entries.find((entry) => entry.actorId === "lender");

    expect(lender?.driver).toBe("reaction_to_risk");
    expect(lender?.wellCalibrated).toBe(false);
    expect(lender?.read).toMatch(/misread/i);
  });

  it("counts high trust in cooperative partners as well calibrated", () => {
    let state = playChoices("steel_supplier", ["balanced", "balanced", "balanced"]);
    for (const actorId of ["gc", "owner", "inspector", "labor_subcontractor", "lender"] as AgentId[]) {
      state = recordTrust(data, state, actorId, 5);
    }
    const calibration = trustCalibration(data, state);
    const cooperative = calibration.entries.filter((entry) => entry.driver === "cooperative");

    expect(cooperative.length).toBeGreaterThan(0);
    for (const entry of cooperative) {
      expect(entry.wellCalibrated).toBe(true);
    }
  });
});
