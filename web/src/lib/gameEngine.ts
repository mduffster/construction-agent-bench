import type {
  AgentId,
  AppliedMove,
  Choice,
  ChoiceEffect,
  ChoiceId,
  GameData,
  GameEvaluation,
  GameState,
  ProjectGameState,
  ProjectStatus,
  RoundId,
  RoundResponse,
  RoundTrace,
} from "./types";

const ROLE_ORDER: AgentId[] = [
  "steel_supplier",
  "gc",
  "owner",
  "inspector",
  "labor_subcontractor",
  "lender",
];

const ROLE_LABELS: Record<AgentId, string> = {
  steel_supplier: "steel supplier",
  gc: "general contractor",
  owner: "owner",
  inspector: "inspector",
  labor_subcontractor: "labor subcontractor",
  lender: "lender",
};

export function createInitialGameState(data: GameData, selectedRole: AgentId): GameState {
  assertPlayableRole(data, selectedRole);
  return {
    selectedRole,
    roundIndex: 0,
    decisions: {},
    trustRatings: {},
  };
}

export function roleNodes(data: GameData, selectedRole: AgentId) {
  assertPlayableRole(data, selectedRole);
  return data.roles[selectedRole].nodes.map((nodeId) => data.decision_nodes[nodeId]);
}

export function currentNode(data: GameData, state: GameState) {
  return roleNodes(data, state.selectedRole)[state.roundIndex] ?? null;
}

export function currentRound(data: GameData, state: GameState) {
  return data.rounds[state.roundIndex] ?? null;
}

export function selectChoice(
  data: GameData,
  state: GameState,
  nodeId: string,
  choiceId: ChoiceId
): GameState {
  const node = data.decision_nodes[nodeId];
  if (!node) {
    throw new Error(`Unknown node ${nodeId}`);
  }
  if (node.actor_id !== state.selectedRole) {
    throw new Error(`Node ${nodeId} does not belong to ${state.selectedRole}`);
  }
  if (!node.choices.some((choice) => choice.choice_id === choiceId)) {
    throw new Error(`Unknown choice ${choiceId} for ${nodeId}`);
  }
  return {
    ...state,
    decisions: { ...state.decisions, [nodeId]: choiceId },
  };
}

export function recordTrust(
  data: GameData,
  state: GameState,
  counterpartyId: AgentId,
  rating: number
): GameState {
  assertRole(data, counterpartyId);
  if (counterpartyId === state.selectedRole) {
    throw new Error("Cannot rate selected role as a counterparty");
  }
  return {
    ...state,
    trustRatings: {
      ...state.trustRatings,
      [counterpartyId]: Math.max(1, Math.min(5, Math.round(rating))),
    },
  };
}

export function advanceRound(data: GameData, state: GameState): GameState {
  const nextRound = Math.min(state.roundIndex + 1, data.rounds.length);
  return { ...state, roundIndex: nextRound };
}

export function isComplete(data: GameData, state: GameState): boolean {
  return roleNodes(data, state.selectedRole).every(
    (node) => state.decisions[node.node_id] !== undefined
  );
}

export function selectedChoices(data: GameData, state: GameState): Choice[] {
  return roleNodes(data, state.selectedRole)
    .map((node) => {
      const choiceId = state.decisions[node.node_id];
      if (!choiceId) {
        return null;
      }
      const choice = node.choices.find((candidate) => candidate.choice_id === choiceId);
      if (!choice) {
        throw new Error(`Missing choice ${choiceId} for ${node.node_id}`);
      }
      return choice;
    })
    .filter((choice): choice is Choice => choice !== null);
}

export function buildGameTrace(data: GameData, state: GameState): RoundTrace[] {
  let projectState = cloneProjectState(data.initial_game_state);
  const traces: RoundTrace[] = [];

  data.rounds.forEach((round, index) => {
    const playerNode = roleNodes(data, state.selectedRole)[index];
    const playerChoiceId = playerNode ? state.decisions[playerNode.node_id] : undefined;
    const roundIsResolved = index < state.roundIndex || Boolean(playerChoiceId);
    if (!roundIsResolved) {
      return;
    }

    const moves: AppliedMove[] = [];
    for (const node of nodesForRound(data, round.round_id)) {
      const isPlayer = node.actor_id === state.selectedRole;
      const choiceId = isPlayer
        ? state.decisions[node.node_id]
        : chooseCounterpartyChoice(data, node.actor_id, node.node_id, projectState);
      if (!choiceId) {
        continue;
      }
      const choice = findChoice(data, node.node_id, choiceId);
      projectState = applyEffect(projectState, choice.web_effect);
      moves.push({
        nodeId: node.node_id,
        actorId: node.actor_id,
        round: node.round,
        choiceId,
        choiceLabel: choice.label,
        summary: choice.web_effect.public_summary,
        isPlayer,
        stateChanges: choice.web_effect.state_changes,
      });
    }

    const assessed = assessStatus(projectState, false);
    traces.push({
      round: round.round_id,
      moves,
      stateAfter: cloneProjectState(projectState),
      statusAfter: assessed.status,
      statusReason: assessed.reason,
    });
  });

  return traces;
}

export function evaluateGame(data: GameData, state: GameState): GameEvaluation {
  const trace = buildGameTrace(data, state);
  const complete = isComplete(data, state);
  const stateBeforeFinal = trace.at(-1)?.stateAfter ?? cloneProjectState(data.initial_game_state);
  const finalState = complete
    ? finalizeProjectState(stateBeforeFinal)
    : cloneProjectState(stateBeforeFinal);
  const assessed = assessStatus(finalState, complete);
  const projectSuccess =
    complete &&
    assessed.status !== "non_viable" &&
    finalState.cost_usd <= finalState.success_cost_ceiling_usd &&
    finalState.completion_week <= finalState.success_deadline_week;
  const playerPayoff = computePlayerPayoff(data, state, trace, projectSuccess);
  const playerPrivateSuccess =
    playerPayoff >= data.private_success_thresholds[state.selectedRole];

  return {
    state: finalState,
    status: assessed.status,
    statusReason: assessed.reason,
    projectSuccess,
    coalitionSuccess: projectSuccess && playerPrivateSuccess,
    selectedChoices: selectedChoices(data, state),
    trace,
    currentRoundTrace: trace.find((round) => round.round === visibleRoundId(data, state)) ?? trace.at(-1) ?? null,
    playerPayoff,
    playerPrivateSuccess,
    idealOutcome: data.comparisons.ideal.outcome,
    modelOutcome: data.comparisons.model?.outcome ?? null,
  };
}

export interface SimulatedPathOutcome {
  state: ProjectGameState;
  status: ProjectStatus;
  statusReason: string;
  projectSuccess: boolean;
}

export function simulatePath(
  data: GameData,
  choiceByNode: Record<string, ChoiceId>
): SimulatedPathOutcome {
  let projectState = cloneProjectState(data.initial_game_state);
  for (const round of data.rounds) {
    for (const node of nodesForRound(data, round.round_id)) {
      const choiceId = choiceByNode[node.node_id];
      if (!choiceId) {
        throw new Error(`simulatePath is missing a choice for ${node.node_id}`);
      }
      const choice = findChoice(data, node.node_id, choiceId);
      projectState = applyEffect(projectState, choice.web_effect);
    }
  }
  const finalState = finalizeProjectState(projectState);
  const assessed = assessStatus(finalState, true);
  const projectSuccess =
    assessed.status !== "non_viable" &&
    finalState.cost_usd <= finalState.success_cost_ceiling_usd &&
    finalState.completion_week <= finalState.success_deadline_week;
  return {
    state: finalState,
    status: assessed.status,
    statusReason: assessed.reason,
    projectSuccess,
  };
}

export function visibleRoundId(data: GameData, state: GameState): RoundId | "DONE" {
  return data.rounds[state.roundIndex]?.round_id ?? "DONE";
}

export interface TrustReflectionEntry {
  actorId: AgentId;
  playerRating: number | null;
  ratingLabel: string;
  read: string;
}

export interface TrustReflection {
  entries: TrustReflectionEntry[];
  ratedCount: number;
  total: number;
}

export function trustReflection(data: GameData, state: GameState): TrustReflection {
  const trace = buildGameTrace(data, state);

  const finalMoveByActor = new Map<AgentId, AppliedMove>();
  for (const round of trace) {
    for (const move of round.moves) {
      if (!move.isPlayer) {
        finalMoveByActor.set(move.actorId, move);
      }
    }
  }

  const entries: TrustReflectionEntry[] = [];
  for (const actorId of finalMoveByActor.keys()) {
    const rating = state.trustRatings[actorId] ?? null;
    entries.push({
      actorId,
      playerRating: rating,
      ratingLabel: trustRatingLabel(rating),
      read: trustRatingRead(actorId, rating),
    });
  }
  entries.sort((left, right) => ROLE_ORDER.indexOf(left.actorId) - ROLE_ORDER.indexOf(right.actorId));

  return {
    entries,
    ratedCount: entries.filter((entry) => entry.playerRating !== null).length,
    total: entries.length,
  };
}

function trustRatingLabel(rating: number | null): string {
  if (rating === null) {
    return "Not rated";
  }
  return {
    1: "Very low trust",
    2: "Low trust",
    3: "Neutral",
    4: "High trust",
    5: "Very high trust",
  }[rating] ?? "Not rated";
}

function trustRatingRead(actorId: AgentId, rating: number | null): string {
  const actor = ROLE_LABELS[actorId];
  if (rating === null) {
    return `You did not record a view of the ${actor}.`;
  }
  if (rating <= 2) {
    return `Your rating suggests you doubted the ${actor} would protect your interests or help the project.`;
  }
  if (rating === 3) {
    return `Your rating suggests you were unsure what to expect from the ${actor}.`;
  }
  return `Your rating suggests you expected the ${actor} to act reliably toward you or the project.`;
}

export function counterpartyTimeline(data: GameData, state: GameState) {
  return buildGameTrace(data, state).flatMap((round) =>
    round.moves
      .filter((move) => !move.isPlayer)
      .map((move) => ({
        nodeId: move.nodeId,
        actorId: move.actorId,
        round: move.round,
        choiceLabel: move.choiceLabel,
        action: move.summary,
      }))
  );
}

export function roundResponses(
  data: GameData,
  state: GameState,
  roundId: RoundId
): RoundResponse[] {
  const trace = buildGameTrace(data, state).find((round) => round.round === roundId);
  if (!trace) {
    return [];
  }
  return trace.moves.map((move) => {
    const node = data.decision_nodes[move.nodeId];
    return {
      nodeId: move.nodeId,
      actorId: move.actorId,
      round: move.round,
      title: node.title,
      choiceLabel: move.choiceLabel,
      action: move.summary,
      meaning: move.summary,
      isPlayer: move.isPlayer,
    };
  });
}

function chooseCounterpartyChoice(
  data: GameData,
  actorId: AgentId,
  nodeId: string,
  state: ProjectGameState
): ChoiceId {
  assertRole(data, actorId);
  if (actorId === "inspector") {
    if (nodeId.includes("REVIEW_PLAN")) {
      return hasAnyFlag(state, ["supplier_thin_disclosure", "gc_overcertified_no_backup"]) ||
        state.verified_value_usd < 700_000 ||
        state.compliance_risk >= 2
        ? "conservative"
        : "balanced";
    }
    if (nodeId.includes("FINAL_DISPOSITION")) {
      if (
        hasAnyFlag(state, ["supplier_shipped_only_lot_a", "lot_b_late"]) &&
        state.backup_status !== "active"
      ) {
        return "self_protective";
      }
      if (state.lot_b_ready || state.backup_status === "active") {
        return state.compliance_risk >= 4 ? "conservative" : "balanced";
      }
      return "self_protective";
    }
    if (nodeId.includes("DISPOSITION")) {
      if (hasFlag(state, "inspection_no_release_path") || state.verified_value_usd < 700_000) {
        return "self_protective";
      }
      return hasFlag(state, "supplier_thin_disclosure") || state.compliance_risk >= 3
        ? "conservative"
        : "balanced";
    }
  }

  if (actorId === "lender") {
    if (hasAnyFlag(state, ["owner_no_support", "gc_overcertified_no_backup"])) {
      return "self_protective";
    }
    if (hasAnyFlag(state, ["supplier_thin_disclosure", "inspection_deeper_review"])) {
      return "conservative";
    }
    if (
      state.verified_value_usd >= 900_000 &&
      state.compliance_risk <= 2 &&
      state.owner_support_usd > 0
    ) {
      return "balanced";
    }
    if (state.compliance_risk >= 4 || state.owner_support_usd <= 0) {
      return "self_protective";
    }
    return "conservative";
  }

  if (actorId === "steel_supplier") {
    if (nodeId.includes("APPLICATION")) {
      return "balanced";
    }
    if (nodeId.includes("COMMITMENT")) {
      if (hasAnyFlag(state, ["owner_no_support", "loan_unavailable", "gc_rejected_supplier_path"])) {
        return "self_protective";
      }
      if (hasFlag(state, "supplier_no_upfront_request") && state.cash_secured_usd < 900_000) {
        return "conservative";
      }
      return state.cash_secured_usd >= 900_000 ? "balanced" : "self_protective";
    }
    if (hasAnyFlag(state, ["supplier_outside_work", "loan_unavailable", "owner_package_rejected"])) {
      return "self_protective";
    }
    return state.cash_secured_usd >= 900_000 || state.backup_status === "active"
      ? "balanced"
      : "self_protective";
  }

  if (actorId === "gc") {
    if (nodeId.includes("INITIAL_REVIEW")) {
      if (hasAnyFlag(state, ["supplier_thin_disclosure", "supplier_high_request"])) {
        return "conservative";
      }
      if (hasFlag(state, "supplier_no_upfront_request") && state.cash_secured_usd === 0) {
        return "balanced";
      }
      return state.compliance_risk >= 3 ? "conservative" : "balanced";
    }
    if (nodeId.includes("INTEGRATED_PACKAGE")) {
      if (
        hasAnyFlag(state, [
          "owner_no_support",
          "loan_unavailable",
          "supplier_outside_work",
          "labor_released",
        ]) ||
        (state.cash_secured_usd < 400_000 && state.backup_status !== "reserved")
      ) {
        return "self_protective";
      }
      return hasAnyFlag(state, ["supplier_thin_disclosure", "inspection_deeper_review"]) ||
        state.schedule_risk >= 4
        ? "conservative"
        : "balanced";
    }
    if (
      hasAnyFlag(state, ["supplier_shipped_only_lot_a", "lot_b_late", "labor_released"]) ||
      !state.lot_b_ready ||
      !state.lot_b_released ||
      state.labor_capacity === "released"
    ) {
      return state.backup_status === "reserved" ? "conservative" : "self_protective";
    }
    return "balanced";
  }

  if (actorId === "owner") {
    if (hasAnyFlag(state, ["supplier_thin_disclosure", "gc_overcertified_no_backup"])) {
      return "conservative";
    }
    if (hasAnyFlag(state, ["loan_unavailable", "gc_rejected_supplier_path", "labor_released"])) {
      return "self_protective";
    }
    if (state.schedule_risk >= 5 || state.cost_usd > state.success_cost_ceiling_usd - 1_000_000) {
      return "self_protective";
    }
    if (state.compliance_risk >= 3 || state.cash_secured_usd < 500_000) {
      return "conservative";
    }
    return "balanced";
  }

  if (actorId === "labor_subcontractor") {
    if (hasAnyFlag(state, ["gc_rejected_supplier_path", "loan_unavailable", "owner_no_support"])) {
      return "self_protective";
    }
    if (hasAnyFlag(state, ["gc_full_review_backup", "inspection_deeper_review"])) {
      return "conservative";
    }
    if (state.lot_a_released || state.verified_value_usd >= 900_000) {
      return "balanced";
    }
    if (state.cash_secured_usd < 300_000 && state.schedule_risk >= 3) {
      return "self_protective";
    }
    return "conservative";
  }

  return "balanced";
}

function applyEffect(state: ProjectGameState, effect: ChoiceEffect): ProjectGameState {
  const next = cloneProjectState(state);
  next.cost_usd += effect.cost_delta_usd;
  next.completion_week += effect.completion_delta_weeks;
  next.cash_secured_usd = Math.max(0, next.cash_secured_usd + effect.cash_delta_usd);
  next.verified_value_usd = Math.max(
    next.verified_value_usd,
    next.verified_value_usd + effect.verified_value_delta_usd
  );
  next.release_value_usd = Math.max(
    next.release_value_usd,
    next.release_value_usd + effect.release_value_delta_usd
  );
  next.owner_support_usd = Math.max(0, next.owner_support_usd + effect.owner_support_delta_usd);
  next.lender_release_usd = Math.max(0, next.lender_release_usd + effect.lender_release_delta_usd);
  next.gc_bridge_usd = Math.max(0, next.gc_bridge_usd + effect.gc_bridge_delta_usd);
  next.compliance_risk = clamp(next.compliance_risk + effect.compliance_risk_delta, 0, 10);
  next.schedule_risk = clamp(next.schedule_risk + effect.schedule_risk_delta, 0, 10);
  if (effect.flags_remove.length > 0) {
    next.story_flags = next.story_flags.filter((flag) => !effect.flags_remove.includes(flag));
  }
  for (const flag of effect.flags_add) {
    if (!next.story_flags.includes(flag)) {
      next.story_flags.push(flag);
    }
  }
  if (effect.lot_a_released !== null) {
    next.lot_a_released = effect.lot_a_released;
  }
  if (effect.lot_b_released !== null) {
    next.lot_b_released = effect.lot_b_released;
  }
  if (effect.lot_b_ready !== null) {
    next.lot_b_ready = effect.lot_b_ready;
  }
  if (effect.labor_capacity !== null) {
    next.labor_capacity = effect.labor_capacity;
  }
  if (effect.backup_status !== null) {
    next.backup_status = effect.backup_status;
  }
  if (effect.blocker_remove) {
    next.blockers = next.blockers.filter((blocker) => blocker !== effect.blocker_remove);
  }
  if (effect.blocker_add && !next.blockers.includes(effect.blocker_add)) {
    next.blockers = [...next.blockers, effect.blocker_add];
  }
  return next;
}

function finalizeProjectState(state: ProjectGameState): ProjectGameState {
  const next = cloneProjectState(state);
  if (next.backup_status === "active") {
    next.lot_b_ready = true;
    next.lot_b_released = true;
    next.completion_week = Math.max(next.completion_week, 45);
  }
  if (!next.lot_a_released) {
    next.completion_week = Math.max(next.completion_week, 50);
    addBlocker(next, "The first steel batch was never approved for use.");
  }
  if (!next.lot_b_ready && next.backup_status !== "active") {
    next.completion_week = Math.max(next.completion_week, 50);
    addBlocker(next, "The second steel batch was never ready to finish the job.");
  }
  if (!next.lot_b_released && next.backup_status !== "active") {
    next.completion_week = Math.max(next.completion_week, 50);
    addBlocker(next, "The second steel batch was never approved for legal installation.");
  }
  if (next.labor_capacity === "released" || next.labor_capacity === "uncommitted") {
    next.completion_week = Math.max(next.completion_week, 50);
    addBlocker(next, "No crew was available when the approved steel needed to move.");
  }
  if (next.cash_secured_usd < 900_000 && next.backup_status !== "active") {
    next.completion_week = Math.max(next.completion_week, 49);
    addBlocker(next, "The steel path never closed its cash gap.");
  }
  if (next.lot_b_released && !next.lot_b_ready) {
    next.compliance_risk = Math.max(next.compliance_risk, 7);
    addBlocker(next, "The second batch was approved before the repairs were proven.");
  }
  if (next.compliance_risk >= 7) {
    next.completion_week = Math.max(next.completion_week, 50);
    addBlocker(next, "The project installed steel it could not legally use.");
  }
  return next;
}

function assessStatus(
  state: ProjectGameState,
  terminal: boolean
): { status: ProjectStatus; reason: string } {
  if (state.cost_usd > state.success_cost_ceiling_usd) {
    return {
      status: "non_viable",
      reason: `Forecast cost is above the $${(state.success_cost_ceiling_usd / 1_000_000).toFixed(1)}M success ceiling.`,
    };
  }
  if (state.completion_week > state.success_deadline_week) {
    return {
      status: "non_viable",
      reason: `Forecast completion is week ${state.completion_week}, after the week ${state.success_deadline_week} deadline.`,
    };
  }
  if (
    state.blockers.some((blocker) =>
      /never|blocked|not available|not released|cash gap|could not legally/i.test(blocker)
    )
  ) {
    return {
      status: terminal ? "non_viable" : "at_risk",
      reason: state.blockers[0] ?? "A show-stopping problem remains unresolved.",
    };
  }
  if (state.schedule_risk >= 5 || state.compliance_risk >= 5) {
    return {
      status: "non_viable",
      reason: "Enough risk has piled up that the current plan no longer works as written.",
    };
  }
  if (state.schedule_risk >= 3 || state.compliance_risk >= 3 || state.blockers.length > 1) {
    return {
      status: "at_risk",
      reason: state.blockers[0] ?? "The project can still work, but unresolved risk remains.",
    };
  }
  return {
    status: "viable",
    reason: "Cash, approvals, labor, and the schedule are all still inside the success window.",
  };
}

function computePlayerPayoff(
  data: GameData,
  state: GameState,
  trace: RoundTrace[],
  projectSuccess: boolean
): number {
  const source = projectSuccess
    ? data.comparisons.ideal.outcome
    : data.witnesses.coordination_failure;
  let payoff = source.realized_payoff_by_organization[state.selectedRole] ?? 0;
  for (const move of trace.flatMap((round) => round.moves)) {
    const choice = findChoice(data, move.nodeId, move.choiceId);
    payoff += choice.web_effect.payoff_delta_by_role[state.selectedRole] ?? 0;
  }
  return Math.round(payoff);
}

function nodesForRound(data: GameData, roundId: RoundId) {
  return Object.values(data.decision_nodes)
    .filter((node) => node.round === roundId)
    .sort(
      (left, right) =>
        ROLE_ORDER.indexOf(left.actor_id) - ROLE_ORDER.indexOf(right.actor_id)
    );
}

function findChoice(data: GameData, nodeId: string, choiceId: ChoiceId): Choice {
  const node = data.decision_nodes[nodeId];
  const choice = node?.choices.find((candidate) => candidate.choice_id === choiceId);
  if (!choice) {
    throw new Error(`Missing choice ${choiceId} for ${nodeId}`);
  }
  return choice;
}

function cloneProjectState(state: ProjectGameState): ProjectGameState {
  return {
    ...state,
    blockers: [...state.blockers],
    story_flags: [...state.story_flags],
  };
}

function addBlocker(state: ProjectGameState, blocker: string): void {
  if (!state.blockers.includes(blocker)) {
    state.blockers.push(blocker);
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function hasFlag(state: ProjectGameState, flag: string): boolean {
  return state.story_flags.includes(flag);
}

function hasAnyFlag(state: ProjectGameState, flags: string[]): boolean {
  return flags.some((flag) => hasFlag(state, flag));
}

function assertPlayableRole(data: GameData, role: AgentId): void {
  assertRole(data, role);
  if (!data.playable_roles.includes(role)) {
    throw new Error(`${role} is a system role in the public game`);
  }
}

function assertRole(data: GameData, role: AgentId): void {
  if (!data.roles[role]) {
    throw new Error(`Unknown role ${role}`);
  }
}
