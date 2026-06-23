import {
  ArrowRight,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  DollarSign,
  Gauge,
  Home,
  MessageSquare,
  Play,
  RotateCcw,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";

import rawGameData from "./game-data/s01_v2_game.json";
import {
  advanceRound,
  counterpartyTimeline,
  createInitialGameState,
  currentNode,
  currentRound,
  evaluateGame,
  isComplete,
  recordTrust,
  roleNodes,
  selectChoice,
} from "./lib/gameEngine";
import type {
  AgentId,
  Choice,
  ChoiceId,
  DecisionNode,
  GameData,
  GameEvaluation,
  GameState,
  RiskLevel,
} from "./lib/types";

const gameData = rawGameData as GameData;
const playableRoleIds = gameData.playable_roles;
type PlayView = "decision" | "result" | "trust";

const similarWork = [
  {
    name: "CoffeeBench",
    href: "https://arxiv.org/html/2606.16613v1",
    summary: "Long-horizon firm economy with farmers, roasters, retailers, cash, inventory, pricing, and transactions.",
  },
  {
    name: "tau-bench",
    href: "https://taubench.com/",
    summary: "Dynamic agent tasks with policies, tools, and interaction over time.",
  },
  {
    name: "MultiAgentBench",
    href: "https://aclanthology.org/2025.acl-long.421/",
    summary: "Collaboration and competition benchmark for LLM-based multi-agent systems.",
  },
  {
    name: "SOTOPIA",
    href: "https://openreview.net/forum?id=mM7VurbA4r",
    summary: "Interactive social-intelligence environments for goal-driven language agents.",
  },
  {
    name: "Concordia",
    href: "https://github.com/google-deepmind/concordia",
    summary: "Framework for generative social simulations with language agents and mediated world state.",
  },
  {
    name: "Silo-Bench",
    href: "https://arxiv.org/abs/2603.01045",
    summary: "Distributed multi-agent coordination tasks focused on information sharing and integration.",
  },
];

export default function App() {
  const route = useRoute();
  if (route.pathname === "/play/s01") {
    return <GameRoute role={route.params.get("role") as AgentId | null} />;
  }
  if (route.pathname === "/play") {
    return <PlayLanding />;
  }
  if (route.pathname === "/results") {
    return <ResultsPage />;
  }
  return <HomePage />;
}

function HomePage() {
  return (
    <Shell>
      <section className="overview-hero">
        <div className="overview-copy">
          <p className="eyebrow">About</p>
          <h1>ConstructBench</h1>
          <p className="lede">
            ConstructBench starts in the world of construction but does not stop
            there. It simulates normal but complex multi-firm coordination and
            transaction structures with AI agents.
          </p>
          <p>
            The aim is to understand how AI agents manage coordination on a
            shared goal under private and public constraints. This differs from
            existing benchmarks narrowly, in focusing on project-level completion
            and tradeoff management.
          </p>
          <p>I'm open to collaboration on this project.</p>
          <div className="hero-actions">
            <NavButton href="/play" icon={<Play size={18} />}>
              Play the scenario
            </NavButton>
            <NavButton href="/results" icon={<Gauge size={18} />}>
              Compare outcomes
            </NavButton>
          </div>
        </div>
        <figure className="overview-image">
          <img
            alt="Pixel art bulldozer pushing soil at a construction site"
            src="/images/pixel-bulldozer.png"
          />
        </figure>
      </section>

      <section className="overview-section">
        <div className="section-title">
          <ClipboardCheck size={20} />
          <h2>Goals</h2>
        </div>
        <p>
          Ideally this project expands to many other complex transactions, where
          agents depend on each other to be successful, but have private
          interests. I hope to converge on design decisions that facilitate
          mutually beneficial AI transactional management, which will benefit
          deployments within firms, and potentially future deployments where AI
          manages many transactions as the primary actor.
        </p>
      </section>

      <section className="overview-section">
        <div className="section-title">
          <Play size={20} />
          <h2>Try It</h2>
        </div>
        <p>
          Play one scenario in the six-firm simulated construction ecosystem.
          In the current public game, you choose one of four firms while the
          lender and inspector remain active system participants. You will have
          public project information, private role information, and decisions
          that can benefit you privately or benefit the broader project.
        </p>
      </section>

      <section id="similar-work" className="overview-section">
        <div className="section-title">
          <Users size={20} />
          <h2>Similar Work</h2>
        </div>
        <div className="similar-grid">
          {similarWork.map((item) => (
            <a href={item.href} key={item.name} rel="noreferrer" target="_blank">
              <strong>{item.name}</strong>
              <span>{item.summary}</span>
            </a>
          ))}
        </div>
      </section>
    </Shell>
  );
}

function PlayLanding() {
  return (
    <Shell variant="game">
      <section className="page-head">
        <p className="eyebrow">Choose your organization</p>
        <h1>Play the off-site steel draw</h1>
        <p className="lede">
          You will play one scenario as one of four firms. The lender and
          inspector remain in the project as system actors, and their decisions
          can still change the result.
        </p>
      </section>
      <section className="role-grid" aria-label="Playable roles">
        {playableRoleIds.map((roleId) => {
          const role = gameData.roles[roleId];
          return (
            <a
              className="role-card"
              href={`/play/s01?role=${roleId}`}
              key={roleId}
            >
              <div className="role-card__icon">{roleGlyph(roleId)}</div>
              <h2>{role.label}</h2>
              <p>{plainObjective(roleId)}</p>
              <span>
                Start as {roleLabel(roleId)} <ArrowRight size={16} />
              </span>
            </a>
          );
        })}
      </section>
      <section className="system-note">
        <strong>System participants:</strong>{" "}
        {gameData.system_roles.map((roleId) => roleLabel(roleId)).join(", ")}.
        They still inspect, fund, block, release, or constrain the project.
      </section>
    </Shell>
  );
}

function GameRoute({ role }: { role: AgentId | null }) {
  if (!role || !gameData.playable_roles.includes(role)) {
    return <PlayLanding />;
  }
  return <GamePage role={role} />;
}

function GamePage({ role }: { role: AgentId }) {
  const [state, setState] = useState<GameState>(() =>
    createInitialGameState(gameData, role)
  );
  const [contextSeen, setContextSeen] = useState(false);
  const [view, setView] = useState<PlayView>("decision");

  useEffect(() => {
    setState(createInitialGameState(gameData, role));
    setContextSeen(false);
    setView("decision");
  }, [role]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [contextSeen, state.roundIndex, Object.keys(state.decisions).length, view]);

  if (state.roundIndex >= gameData.rounds.length) {
    return (
      <Shell variant="game">
        <EndScreen state={state} />
      </Shell>
    );
  }

  if (!contextSeen) {
    return (
      <Shell variant="game">
        <ContextScreen role={role} onStart={() => setContextSeen(true)} />
      </Shell>
    );
  }

  const node = currentNode(gameData, state);
  const round = currentRound(gameData, state);
  const evaluation = evaluateGame(gameData, state);
  const complete = isComplete(gameData, state);
  const decisionMade = node ? state.decisions[node.node_id] !== undefined : false;
  const selectedChoice =
    node && decisionMade
      ? node.choices.find((choice) => choice.choice_id === state.decisions[node.node_id])
      : null;

  if (decisionMade && node && selectedChoice && view === "trust") {
    return (
      <Shell variant="game">
        <TrustUpdateScreen
          complete={complete}
          state={state}
          setState={setState}
          onContinue={() => {
            setState((current) => advanceRound(gameData, current));
            setView("decision");
          }}
        />
      </Shell>
    );
  }

  return (
    <Shell variant="game">
      <section className="game-shell">
        <main className="play-surface">
          <StageHeader roundLabel={round?.label ?? ""} title={node?.title ?? ""} />

          {node && !decisionMade && <DecisionBrief node={node} />}

          {!decisionMade && node && (
            <section className="choice-grid" aria-label="Decision choices">
              {node.choices.map((choice) => (
                <button
                  className="choice-card"
                  key={choice.choice_id}
                  onClick={() => {
                    setState((current) =>
                      selectChoice(gameData, current, node.node_id, choice.choice_id as ChoiceId)
                    );
                    setView("result");
                  }}
                >
                  <h2>{choice.label}</h2>
                  <p>{choice.why_choose}</p>
                  <ul>
                    {choice.display_bullets.slice(0, 3).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <div className="choice-risk-meter" aria-label="Risk levels">
                    <RiskBadge label="Your upside" level={choice.risk_levels.private_benefit} tone="benefit" />
                    <RiskBadge label="Cost risk" level={choice.risk_levels.cost} tone="risk" />
                    <RiskBadge label="Delay risk" level={choice.risk_levels.delay} tone="risk" />
                  </div>
                </button>
              ))}
            </section>
          )}

          {decisionMade && node && selectedChoice && (
            <DecisionResult
              evaluation={evaluation}
              selectedChoice={selectedChoice}
              onContinue={() => setView("trust")}
            />
          )}
        </main>
      </section>
    </Shell>
  );
}

function RiskBadge({
  label,
  level,
  tone,
}: {
  label: string;
  level: RiskLevel;
  tone: "benefit" | "risk";
}) {
  return (
    <div className={`risk-badge risk-badge--${tone} risk-badge--${level}`}>
      <span>{label}</span>
      <strong>{titleCase(level)}</strong>
    </div>
  );
}

function ContextScreen({ role, onStart }: { role: AgentId; onStart: () => void }) {
  const baseline = gameData.public_baseline;
  const roleData = gameData.roles[role];
  return (
    <section className="context-screen">
      <section className="scenario-card">
        <p className="eyebrow">Scenario briefing</p>
        <h1>{gameData.scenario.display_name}</h1>

        <div className="scenario-layout">
          <div className="scenario-story">
            <p>The project needs two steel batches to arrive in order.</p>
            <p>
              Lot A, the first batch, is mostly ready. Lot B, the second batch,
              has a problem and needs more work.
              {role === "steel_supplier"
                ? " You have to decide whether to ask for money before the steel reaches the site."
                : " The supplier says it needs money before the steel reaches the site."}
            </p>
            <p>
              Paying early could keep delivery moving. It could also leave the
              project exposed if the steel is not actually ready.
            </p>
          </div>

          <div className="role-summary">
            <h2>You are {roleData.label}</h2>
            <p>{plainObjective(role)}</p>
            <ul>
              {roleData.private_dashboard.highlights.map((highlight) => (
                <li key={highlight}>{highlight}</li>
              ))}
            </ul>
          </div>
        </div>

        <section className="project-strip" aria-label="Project snapshot">
          <h2>Project snapshot</h2>
          <dl>
            <div>
              <dt>Now</dt>
              <dd>Week {String(baseline.current_tick)}</dd>
            </div>
            <div>
              <dt>Original target</dt>
              <dd>
                {formatMoney(Number(baseline.baseline_planned_project_cost_usd))} / Week{" "}
                {String(baseline.baseline_expected_completion_tick)}
              </dd>
            </div>
            <div>
              <dt>Steel package</dt>
              <dd>{formatMoney(Number(baseline.first_steel_sequence_contract_value_usd))}</dd>
            </div>
            <div>
              <dt>{role === "steel_supplier" ? "Your payment choice" : "New request"}</dt>
              <dd>
                {role === "steel_supplier"
                  ? "No request made yet"
                  : `${formatMoney(Number(baseline.supplier_payment_application_usd))} up front`}
              </dd>
            </div>
          </dl>
        </section>

        <button className="primary-button primary-button--game" onClick={onStart}>
          Start first decision <ArrowRight size={18} />
        </button>
      </section>
    </section>
  );
}

function StageHeader({ roundLabel, title }: { roundLabel: string; title: string }) {
  return (
    <section className="round-banner">
      <span>{roundLabel}</span>
      <h1>{title}</h1>
    </section>
  );
}

function DecisionBrief({
  node,
}: {
  node: DecisionNode;
}) {
  return (
    <section className="decision-brief">
      <div className="decision-info-grid">
        <div className="info-panel info-panel--public">
          <div className="section-title">
            <ClipboardCheck size={20} />
            <h2>Public info</h2>
          </div>
          <ul className="info-list">
            {node.critical_updates.slice(0, 2).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="info-panel info-panel--private" aria-label="Private info">
          <div className="section-title">
            <ShieldCheck size={20} />
            <h2>Private info</h2>
          </div>
          <p>{node.situation}</p>
          <ul>
            {node.private_stakes.slice(0, 2).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function DecisionResult({
  evaluation,
  selectedChoice,
  onContinue,
}: {
  evaluation: GameEvaluation;
  selectedChoice: Choice;
  onContinue: () => void;
}) {
  const trace = evaluation.currentRoundTrace;
  const playerMove = trace?.moves.find((move) => move.isPlayer);
  return (
    <section className="result-panel">
      <div className="section-title">
        <CheckCircle2 size={20} />
        <h2>What happened</h2>
      </div>
      <p className="result-choice">You chose: {selectedChoice.label}</p>
      <p>{playerMove?.summary ?? selectedChoice.after_choice}</p>
      <RoundMoveList trace={trace} />
      <button className="primary-button primary-button--game" onClick={onContinue}>
        Update partner trust <ArrowRight size={18} />
      </button>
    </section>
  );
}

function RoundMoveList({ trace }: { trace: GameEvaluation["currentRoundTrace"] }) {
  if (!trace) {
    return null;
  }
  return (
    <section className="response-panel" aria-label="Visible round responses">
      <div className="section-title">
        <Users size={20} />
        <h2>Project impacts this round</h2>
      </div>
      <div className="response-list">
        {trace.moves.map((move) => (
          <div className={move.isPlayer ? "response-row response-row--you" : "response-row"} key={move.nodeId}>
            <strong>{roleLabel(move.actorId)}</strong>
            <span>
              {move.choiceLabel}
              <small>{move.summary}</small>
            </span>
            <em>{move.isPlayer ? "you" : "partner"}</em>
          </div>
        ))}
      </div>
    </section>
  );
}

function TrustUpdateScreen({
  complete,
  state,
  setState,
  onContinue,
}: {
  complete: boolean;
  state: GameState;
  setState: Dispatch<SetStateAction<GameState>>;
  onContinue: () => void;
}) {
  return (
    <section className="trust-screen">
      <MessageSquare size={28} />
      <h1>Has your counterparty trust changed?</h1>
      <p>Based on the information you got this round, update any partner rating.</p>
      {(Object.keys(state.trustRatings) as AgentId[]).map((agentId) => (
        <label className="trust-row" key={agentId}>
          <span>{roleLabel(agentId)}</span>
          <input
            aria-label={`Trust rating for ${agentId}`}
            max={5}
            min={1}
            type="range"
            value={state.trustRatings[agentId]}
            onChange={(event) =>
              setState((current) =>
                recordTrust(gameData, current, agentId, Number(event.target.value))
              )
            }
          />
          <strong>{state.trustRatings[agentId]}</strong>
        </label>
      ))}
      <button className="primary-button primary-button--game" onClick={onContinue}>
        {complete ? "Show final outcome" : "Continue to next decision"}
        <ArrowRight size={18} />
      </button>
    </section>
  );
}

function EndScreen({ state }: { state: GameState }) {
  const evaluation = evaluateGame(gameData, state);
  const playerNodes = roleNodes(gameData, state.selectedRole);
  const counterparties = counterpartyTimeline(gameData, state);
  const trustRatings = Object.values(state.trustRatings);
  const averageTrust =
    trustRatings.reduce((total, rating) => total + rating, 0) / trustRatings.length;
  return (
    <section className="end-screen">
      <div className="outcome-header">
        <p className="eyebrow">Final outcome</p>
        <h1>{evaluation.projectSuccess ? "Project success" : "Project failure"}</h1>
        <p>
          Your project reached {formatMoney(evaluation.state.cost_usd)} and week{" "}
          {evaluation.state.completion_week}. {evaluation.statusReason}
        </p>
      </div>
      <div className="metric-grid">
        <Metric icon={<DollarSign />} label="Your payoff" value={formatMoney(evaluation.playerPayoff)} />
        <Metric icon={<ShieldCheck />} label="Private result" value={evaluation.playerPrivateSuccess ? "Success" : "Failure"} />
        <Metric icon={<Users />} label="Coalition" value={evaluation.coalitionSuccess ? "Success" : "Failure"} />
        <Metric icon={<Gauge />} label="Schedule delta" value={`+${evaluation.state.completion_week - evaluation.state.baseline_completion_week}`} />
      </div>
      <ComparisonPanel evaluation={evaluation} />

      <section className="timeline">
        <div className="section-title">
          <ClipboardCheck size={20} />
          <h2>What Happened</h2>
        </div>
        {playerNodes.map((node) => {
          const choice = node.choices.find(
            (candidate) => candidate.choice_id === state.decisions[node.node_id]
          );
          return (
            <div className="timeline-row" key={node.node_id}>
              <strong>{node.round}</strong>
              <span>{node.title}</span>
              <em>{choice?.label}</em>
            </div>
          );
        })}
        <div className="timeline-row timeline-row--muted">
          <strong>Policy</strong>
          <span>{counterparties.length} counterparty decisions responded to your state</span>
          <em>branching script</em>
        </div>
      </section>

      <section className="trust-summary" aria-label="Trust summary">
        <div className="section-title">
          <MessageSquare size={20} />
          <h2>Trust Summary</h2>
        </div>
        <div className="trust-summary-card">
          <span>Average partner trust</span>
          <strong>{averageTrust.toFixed(1)}/5</strong>
          <em>{trustRatings.length} partners rated</em>
          <div className="trust-meter" aria-hidden="true">
            <span style={{ width: `${(averageTrust / 5) * 100}%` }} />
          </div>
        </div>
      </section>

      <div className="hero-actions">
        <NavButton href="/play" icon={<RotateCcw size={18} />}>
          Play another role
        </NavButton>
        <NavButton href="/results" icon={<Gauge size={18} />}>
          Compare outcomes
        </NavButton>
        <NavButton href="/" icon={<Home size={18} />}>
          Back to overview
        </NavButton>
      </div>
    </section>
  );
}

function ResultsPage() {
  const state = createInitialGameState(gameData, "steel_supplier");
  const evaluation = evaluateGame(gameData, state);
  return (
    <Shell>
      <section className="overview-section">
        <div className="section-title">
          <Gauge size={20} />
          <h2>Outcome comparison</h2>
        </div>
        <p>
          The ideal row shows what happens when every party coordinates well even
          after the steel problem appears. The model row shows one Claude Haiku
          all-agent run from the benchmark outputs.
        </p>
        <ComparisonPanel evaluation={evaluation} playerOnly={false} />
      </section>
    </Shell>
  );
}

function ComparisonPanel({
  evaluation,
  playerOnly = true,
}: {
  evaluation: GameEvaluation;
  playerOnly?: boolean;
}) {
  const rows = [
    {
      label: "Ideal: everyone coordinates",
      cost: evaluation.idealOutcome.final_project_cost,
      week: evaluation.idealOutcome.completion_tick,
      note: "Project succeeds despite the steel problem",
    },
    evaluation.modelOutcome
      ? {
          label: "Claude Haiku all-agent run",
          cost: evaluation.modelOutcome.final_project_cost,
          week: evaluation.modelOutcome.completion_tick,
          note: plainOutcomeNote(evaluation.modelOutcome.path_label),
        }
      : null,
    playerOnly
      ? {
          label: "Your playthrough",
          cost: evaluation.state.cost_usd,
          week: evaluation.state.completion_week,
          note: evaluation.projectSuccess ? "Project success" : "Project failure",
        }
      : null,
  ].filter((row): row is { label: string; cost: number | null; week: number | null; note: string } => row !== null);

  return (
    <section className="comparison-panel" aria-label="Outcome comparison">
      {rows.map((row) => (
        <div className="comparison-row" key={row.label}>
          <strong>{row.label}</strong>
          <span>{row.cost === null ? "n/a" : formatMoney(row.cost)}</span>
          <span>{row.week === null ? "n/a" : `Week ${row.week}`}</span>
          <em>{row.note}</em>
        </div>
      ))}
    </section>
  );
}

function plainOutcomeNote(pathLabel: string | null) {
  const labels: Record<string, string> = {
    backup_project_success: "Project succeeds, but only after using backup recovery",
    phased_coalition_success: "Project succeeds through coordinated phased delivery",
    coordination_delay_failure: "Project fails after coordination delays stack up",
    schedule_infeasible: "Project fails because the schedule becomes impossible",
  };
  return labels[pathLabel ?? ""] ?? "Model-produced project outcome";
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Shell({
  children,
  variant = "overview",
}: {
  children: ReactNode;
  variant?: "overview" | "game";
}) {
  return (
    <div className={`site-shell site-shell--${variant}`}>
      <header className="topbar">
        <a href="/" className="brand">
          <span className="brand-mark" />
          ConstructBench
        </a>
        <nav>
          <a href="/">Overview</a>
          <a href="/play">Play</a>
          <a href="/results">Results</a>
        </nav>
      </header>
      <div className="app-frame">{children}</div>
    </div>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="metric">
      <span>{icon}</span>
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function NavButton({
  href,
  icon,
  children,
}: {
  href: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <a className="primary-button" href={href}>
      {icon}
      {children}
    </a>
  );
}

function plainObjective(role: AgentId) {
  return {
    owner:
      "You want the project to finish, but every added dollar and week costs you money.",
    gc:
      "You need steel installation to progress without putting too much short-term GC money at risk or overpaying for backup steel.",
    steel_supplier:
      "You need cash to finish, cure, and ship steel while protecting your margin.",
    labor_subcontractor:
      "You control crew and crane capacity. Holding the capacity available for this project helps the project but costs you other work where you could deploy your resources.",
    lender:
      "You can release loan funds only when stored value, controls, equity, and reserves make the draw defensible.",
    inspector:
      "You decide what material can be released without creating compliance risk for the project.",
  }[role];
}

function projectStatusLabel(evaluation: GameEvaluation) {
  if (evaluation.status === "viable") {
    return "Viable as planned";
  }
  if (evaluation.status === "at_risk") {
    return "At risk";
  }
  return "Non-viable as planned";
}

function titleCase(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function roleGlyph(role: AgentId) {
  return {
    owner: "OW",
    gc: "GC",
    steel_supplier: "ST",
    labor_subcontractor: "LB",
    lender: "LN",
    inspector: "IN",
  }[role];
}

function roleLabel(role: AgentId) {
  return gameData.roles[role].label.replace(" / developer", "");
}

function formatMoney(value: number) {
  const sign = value < 0 ? "-" : "";
  const amount = Math.abs(value);
  if (amount >= 1_000_000) {
    return `${sign}$${(amount / 1_000_000).toFixed(2)}M`;
  }
  return `${sign}$${amount.toLocaleString()}`;
}

function useRoute() {
  const [route, setRoute] = useState(() => parseRoute());
  useEffect(() => {
    const onPop = () => setRoute(parseRoute());
    window.addEventListener("popstate", onPop);
    document.addEventListener("click", (event) => {
      const target = event.target as HTMLElement;
      const anchor = target.closest("a");
      if (!anchor || anchor.target || anchor.origin !== window.location.origin) {
        return;
      }
      event.preventDefault();
      window.history.pushState({}, "", anchor.href);
      setRoute(parseRoute());
    });
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return route;
}

function parseRoute() {
  return {
    pathname: window.location.pathname,
    params: new URLSearchParams(window.location.search),
  };
}
