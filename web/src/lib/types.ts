export type AgentId =
  | "owner"
  | "gc"
  | "steel_supplier"
  | "labor_subcontractor"
  | "lender"
  | "inspector";

export type ChoiceId = "balanced" | "self_protective" | "conservative";
export type RoundId = "A" | "B" | "C";
export type LaborCapacity = "uncommitted" | "split" | "full" | "released";
export type BackupStatus = "none" | "reserved" | "active";
export type ProjectStatus = "viable" | "at_risk" | "non_viable";
export type RiskLevel = "low" | "medium" | "high";

export interface ChoiceEffect {
  cost_delta_usd: number;
  completion_delta_weeks: number;
  cash_delta_usd: number;
  verified_value_delta_usd: number;
  release_value_delta_usd: number;
  owner_support_delta_usd: number;
  lender_release_delta_usd: number;
  gc_bridge_delta_usd: number;
  compliance_risk_delta: number;
  schedule_risk_delta: number;
  lot_a_released: boolean | null;
  lot_b_released: boolean | null;
  lot_b_ready: boolean | null;
  labor_capacity: LaborCapacity | null;
  backup_status: BackupStatus | null;
  blocker_add: string | null;
  blocker_remove: string | null;
  flags_add: string[];
  flags_remove: string[];
  payoff_delta_by_role: Partial<Record<AgentId, number>>;
  public_summary: string;
  state_changes: string[];
}

export interface Choice {
  choice_id: ChoiceId;
  label: string;
  role_action: string;
  summary: string;
  stance: string;
  project_score_delta: number;
  private_score_delta: number;
  risk_note: string;
  source_fixture: string;
  parameters: Record<string, unknown>;
  display_bullets: string[];
  after_choice: string;
  public_meaning: string;
  why_choose: string;
  tradeoff: string;
  risk_levels: {
    private_benefit: RiskLevel;
    cost: RiskLevel;
    delay: RiskLevel;
  };
  parameter_summary: string[];
  web_effect: ChoiceEffect;
  disclosure: Disclosure | null;
  reads: DecisionReads;
}

export interface Disclosure {
  claimed: string;
  private_truth: string;
  honesty_read: string;
  verdict: "accurate" | "withheld";
}

export interface DecisionReads {
  charitable: string;
  uncharitable: string;
}

export interface DecisionNode {
  node_id: string;
  actor_id: AgentId;
  round: RoundId;
  prompt: string;
  title: string;
  situation: string;
  critical_updates: string[];
  private_stakes: string[];
  terms: Array<{ term: string; meaning: string }>;
  impact_tags: string[];
  choices: Choice[];
}

export interface RoundResponse {
  nodeId: string;
  actorId: AgentId;
  round: RoundId;
  title: string;
  choiceLabel: string;
  action: string;
  meaning: string;
  isPlayer: boolean;
}

export interface RoleData {
  agent_id: AgentId;
  label: string;
  playable: boolean;
  briefing: {
    objective: string;
    terminal_metric_definition: string;
    known_project_situation: string;
  };
  private_dashboard: {
    highlights: string[];
    starting_private_facts: Record<string, unknown>;
  };
  nodes: string[];
}

export interface WitnessOutcome {
  fixture_name: string;
  terminal_status: string;
  terminal_reason: string | null;
  run_valid: boolean;
  path_label: string | null;
  project_success: boolean | null;
  coalition_success: boolean | null;
  final_project_cost: number | null;
  completion_tick: number | null;
  project_welfare: {
    normalized_cost_score?: number;
    normalized_schedule_score?: number;
    cost_delta_from_baseline?: number;
    schedule_delta_from_baseline?: number;
  };
  realized_payoff_by_organization: Partial<Record<AgentId, number>>;
  normalized_payoff_by_organization: Partial<Record<AgentId, number>>;
  private_success_by_organization: Partial<Record<AgentId, boolean>>;
}

export interface ProjectGameState {
  current_week: number;
  cost_usd: number;
  completion_week: number;
  baseline_cost_usd: number;
  baseline_completion_week: number;
  success_cost_ceiling_usd: number;
  success_deadline_week: number;
  cash_secured_usd: number;
  verified_value_usd: number;
  release_value_usd: number;
  owner_support_usd: number;
  lender_release_usd: number;
  gc_bridge_usd: number;
  lot_a_released: boolean;
  lot_b_released: boolean;
  lot_b_ready: boolean;
  labor_capacity: LaborCapacity;
  backup_status: BackupStatus;
  compliance_risk: number;
  schedule_risk: number;
  blockers: string[];
  story_flags: string[];
}

export interface GameData {
  schema_version: string;
  scenario: {
    scenario_key: string;
    scenario_id: string;
    display_name: string;
    source: string;
    content_hash: string;
  };
  public_baseline: Record<string, unknown>;
  initial_game_state: ProjectGameState;
  playable_roles: AgentId[];
  system_roles: AgentId[];
  roles: Record<AgentId, RoleData>;
  decision_nodes: Record<string, DecisionNode>;
  rounds: Array<{ round_id: RoundId; label: string; summary: string }>;
  counterparty_policy: {
    policy_id: string;
    summary: string;
    default_choice_id: ChoiceId;
  };
  witnesses: Record<string, WitnessOutcome>;
  comparisons: {
    ideal: {
      label: string;
      source: string;
      source_id: string;
      outcome: WitnessOutcome;
    };
    model: {
      label: string;
      source: string;
      model_provider: string | null;
      model_id: string | null;
      outcome: WitnessOutcome;
    } | null;
  };
  private_success_thresholds: Record<AgentId, number>;
  lexicon: Record<string, string>;
  path_rules: Record<string, string>;
}

export interface PopulationRun {
  batch: string;
  temperature: number;
  repair_budget?: number;
  repair_attempt_count?: number | null;
  repaired_turn_count?: number | null;
  replicate_index: number;
  run_valid: boolean;
  terminal_status: string;
  path_label: string | null;
  final_project_cost: number | null;
  completion_tick: number | null;
  project_success: boolean | null;
  coalition_success: boolean | null;
  firms_meeting_private_target: number | null;
  private_success_by_organization: Partial<Record<AgentId, boolean>>;
}

export interface PopulationData {
  schema_version: string;
  generated_at: string;
  model: string | string[];
  run_count: number;
  valid_run_count: number;
  project_success_count: number;
  coalition_success_count: number;
  cost_min: number | null;
  cost_max: number | null;
  tick_min: number | null;
  tick_max: number | null;
  runs: PopulationRun[];
}

export interface ResponseCurveSample {
  model: string;
  temperature: number;
  run_count: number;
  valid_run_count: number;
  invalid_run_count: number;
  valid_rate: number;
  replacement_rate: number;
  mean_attainable_regret_usd: number;
  request_monotonicity_violations: number;
}

export interface ResponseCurveLevel {
  response_curve_level: string;
  replacement_cost_usd: number;
  replacement_threshold_usd: number;
  maximum_safe_relief_usd: number;
  haiku_no_history_valid_n: number;
  haiku_no_history_mean_request_usd: number;
  haiku_no_history_replacement_rate: number;
  haiku_no_history_mean_attainable_regret_usd: number;
  haiku_history_valid_n: number;
  haiku_history_mean_request_usd: number;
  haiku_history_replacement_rate: number;
  haiku_history_mean_attainable_regret_usd: number;
  sonnet_no_history_valid_n: number;
  sonnet_no_history_mean_request_usd: number;
  sonnet_no_history_replacement_rate: number;
  sonnet_no_history_mean_attainable_regret_usd: number;
}

export interface ResponseCurveMechanismCondition {
  condition_id: "unassisted" | "threshold_worksheet" | "trusted_threshold";
  label: string;
  description: string;
  evidence_tier:
    | "five_per_cell_confirmation"
    | "one_per_cell_modal_diagnostic"
    | "three_per_cell_confirmation";
  run_count: number;
  valid_run_count: number;
  valid_rate: number;
  mean_attainable_regret_usd: number;
  replacement_rate: number;
  request_monotonicity_violations: number;
  mechanism_gate_passed: boolean | null;
  correct_threshold_count?: number;
  parseable_calculation_count?: number;
  stated_ceiling_override_count?: number;
}

export interface ResponseCurveData {
  schema_version: string;
  experiment_id: string;
  title: string;
  question: string;
  design: {
    focal_role: AgentId;
    llm_respondent_count_per_run: number;
    deterministic_counterparty_count: number;
    replacement_cost_level_count: number;
    relationship_history_condition_count: number;
    deterministic_reference_trajectory_count: number;
    minimum_safe_request_usd: number;
    maximum_safe_request_usd: number;
  };
  haiku_confirmation: ResponseCurveSample;
  sonnet_modal: ResponseCurveSample;
  mechanism_test: {
    question: string;
    conditions: ResponseCurveMechanismCondition[];
    trusted_threshold_effect: {
      mean_attainable_regret_reduction_fraction: number;
      mean_attainable_regret_reduction_usd: number;
      modal_gate_passed: boolean;
      confirmation_gate_passed: boolean;
      residual_high_level_anchor_usd: number;
    };
    interpretation: string;
    limitations: string[];
  };
  haiku_request_counts: Record<string, number>;
  levels: ResponseCurveLevel[];
  limitations: string[];
  source: {
    evidence_path: string;
    evidence_manifest_sha256: string;
    response_table_sha256: string;
    chart_sha256: string;
    intervention_summary_sha256: string;
  };
  content_sha256: string;
}

export interface GameState {
  selectedRole: AgentId;
  roundIndex: number;
  decisions: Record<string, ChoiceId>;
  trustRatings: Record<AgentId, number>;
}

export interface AppliedMove {
  nodeId: string;
  actorId: AgentId;
  round: RoundId;
  choiceId: ChoiceId;
  choiceLabel: string;
  summary: string;
  isPlayer: boolean;
  stateChanges: string[];
}

export interface RoundTrace {
  round: RoundId;
  moves: AppliedMove[];
  stateAfter: ProjectGameState;
  statusAfter: ProjectStatus;
  statusReason: string;
}

export interface GameEvaluation {
  state: ProjectGameState;
  status: ProjectStatus;
  statusReason: string;
  projectSuccess: boolean;
  coalitionSuccess: boolean;
  selectedChoices: Choice[];
  trace: RoundTrace[];
  currentRoundTrace: RoundTrace | null;
  playerPayoff: number;
  playerPrivateSuccess: boolean;
  idealOutcome: WitnessOutcome;
  modelOutcome: WitnessOutcome | null;
}
