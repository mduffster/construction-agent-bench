import {
  ArrowRight,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  DollarSign,
  Eye,
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
import rawPopulationData from "./game-data/s01_v2_population.json";
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
  trustCalibration,
} from "./lib/gameEngine";
import type {
  AgentId,
  Choice,
  ChoiceId,
  DecisionNode,
  Disclosure,
  GameData,
  GameEvaluation,
  GameState,
  PopulationData,
  PopulationRun,
  ProjectGameState,
  RiskLevel,
} from "./lib/types";

const gameData = rawGameData as GameData;
const populationData = rawPopulationData as PopulationData;
const playableRoleIds = gameData.playable_roles;
type PlayView = "decision" | "result";
type ProjectPhase =
  | "empty_lot"
  | "paperwork_dispute"
  | "steel_delivery"
  | "delivery_blocked"
  | "erection_progress"
  | "erected_structure";

const projectPhaseImages: Record<
  ProjectPhase,
  { alt: string; src: string; summary: string }
> = {
  empty_lot: {
    alt: "Empty graded construction lot waiting for steel delivery",
    src: "/images/s01-phase-empty-lot.png",
    summary:
      "The project is waiting for cash, inspection, and release controls before steel can move.",
  },
  paperwork_dispute: {
    alt: "Construction paperwork and payment documents with held steel behind the site fence",
    src: "/images/s01-phase-paperwork-dispute.png",
    summary:
      "The action is still in the payment, documentation, and release-review lane.",
  },
  steel_delivery: {
    alt: "Flatbed truck delivering steel beams to a construction site",
    src: "/images/s01-phase-steel-delivery.png",
    summary:
      "Steel is moving toward the site, but the full sequence still depends on release and coordination.",
  },
  delivery_blocked: {
    alt: "Steel delivery truck stopped at a blocked construction gate with paperwork in view",
    src: "/images/s01-phase-delivery-blocked.png",
    summary:
      "The steel path is blocked by a gate, paperwork, funding, labor, or release problem.",
  },
  erection_progress: {
    alt: "Crane lifting steel beams into a partially erected structure",
    src: "/images/s01-phase-erection-progress.png",
    summary:
      "Released steel and field capacity have turned into active erection work.",
  },
  erected_structure: {
    alt: "Completed steel frame standing on the construction site",
    src: "/images/s01-phase-erected-structure.png",
    summary:
      "The steel sequence is substantially erected and the project has a viable path forward.",
  },
};

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
  useEffect(() => {
    Object.values(projectPhaseImages).forEach((phaseImage) => {
      const image = new Image();
      image.src = phaseImage.src;
    });
  }, []);

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
          <h1>ConstructSim</h1>
          <p className="lede">
            ConstructSim starts in the world of construction but the idea is to
            test on many multi-firm coordination tasks. These are simulations of
            normal but complex multi-firm coordination and transaction
            structures with AI agents.
          </p>
          <p>
            I'm focused on understanding how AI agents manage coordination on a
            shared goal while managing private and public constraints. In these
            scenarios, switching costs are high, and acting overly cooperative
            or overly competitive will cause projects to fail, or generate
            massive private losses. In these scenarios, project completion,
            private incentives, and realistic tradeoffs matter.
          </p>
          <p>I'm open to collaboration on this project.</p>
          <div className="hero-actions">
            <NavButton href="/play" icon={<Play size={18} />}>
              Play the scenario
            </NavButton>
            <NavButton href="/results" icon={<Gauge size={18} />}>
              See example runs
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
          <Eye size={20} />
          <h2>Some of what I've observed so far</h2>
        </div>
        <p>
          In one scenario, with one live agent, other scripted actors, small samples,
          and a two model tiers. A couple things show up at times 
          when an AI agent plays the steel supplier:
        </p>
        <ul className="findings-list">
          <li>
            <strong>It sometimes fails to price its own replaceability.</strong> The agent
            demands price relief whether or not the buyer has a cheap, credible
            replacement. It's a winning move when no good alternative exists,
            but self-defeating otherwise. The agent gets replaced and takes a
            loss it could have avoided by not over-asking. The project still 
            finishes but the steel supplier loses out.
          </li>
          <li>
            <strong>Its honesty tracks relationship history; but strategy does
            not.</strong> With no prior track record, the agent overstates the cash
            it needs; with a verified history with the counterparties, it reports accurately.
            Yet its bargaining position stays the same either way.
          </li>
        </ul>
        <p>
          The harness scores these against each firm's private truth and
          objective payoffs, and every run is deterministic and replayable. Code
          and the evidence write-ups are on{" "}
          <a href="https://github.com/mduffster/construction-agent-bench" rel="noreferrer" target="_blank">
            GitHub
          </a>
          .
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
          that can benefit you privately or benefit the broader project. The
          game is a simplified version of the full simulation: you face the
          same kind of information problem the AI agents face, but the agents
          work through much larger structured decision spaces than the choices
          shown here.
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
          can still change the result. Each choice you make is a simplified
          stand-in for a much larger structured decision the AI agents must
          construct in the full simulation.
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

  return (
    <Shell variant="game">
      <section className="game-shell">
        <main className="play-surface">
          <StageHeader roundLabel={round?.label ?? ""} title={node?.title ?? ""} />

          {node && !decisionMade && (
            <>
              <ProjectScene
                state={evaluation.state}
                title="Site view before your decision"
              />
              <DecisionBrief node={node} />
            </>
          )}

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
              complete={complete}
              evaluation={evaluation}
              selectedChoice={selectedChoice}
              state={state}
              setState={setState}
              onContinue={() => {
                setState((current) => advanceRound(gameData, current));
                setView("decision");
              }}
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
  complete,
  evaluation,
  selectedChoice,
  state,
  setState,
  onContinue,
}: {
  complete: boolean;
  evaluation: GameEvaluation;
  selectedChoice: Choice;
  state: GameState;
  setState: Dispatch<SetStateAction<GameState>>;
  onContinue: () => void;
}) {
  const trace = evaluation.currentRoundTrace;
  const playerMove = trace?.moves.find((move) => move.isPlayer);
  return (
    <>
      <ProjectScene
        state={trace?.stateAfter ?? evaluation.state}
        title="Site view after the round"
      />
      <section className="result-panel">
        <div className="section-title">
          <CheckCircle2 size={20} />
          <h2>What happened</h2>
        </div>
        <p className="result-choice">You chose: {selectedChoice.label}</p>
        <p>{playerMove?.summary ?? selectedChoice.after_choice}</p>
      </section>
      {selectedChoice.disclosure && (
        <DisclosurePanel disclosure={selectedChoice.disclosure} />
      )}
      <PartnerDecisionReview
        trace={trace}
        state={state}
        setState={setState}
      />
      <button className="primary-button primary-button--game" onClick={onContinue}>
        {complete ? "Show final outcome" : "Continue to next decision"}
        <ArrowRight size={18} />
      </button>
    </>
  );
}

function DisclosurePanel({ disclosure }: { disclosure: Disclosure }) {
  return (
    <section className={`disclosure-panel disclosure-panel--${disclosure.verdict}`} aria-label="What you disclosed">
      <div className="section-title">
        <Eye size={20} />
        <h2>What you told the team vs. what you know</h2>
      </div>
      <p className="disclosure-lead">
        The AI agents score this gap directly. Here it is in plain language.
      </p>
      <div className="disclosure-grid">
        <div className="disclosure-cell disclosure-cell--claimed">
          <span>What the team hears</span>
          <p>{disclosure.claimed}</p>
        </div>
        <div className="disclosure-cell disclosure-cell--private">
          <span>What you privately know</span>
          <p>{disclosure.private_truth}</p>
        </div>
      </div>
      <p className="disclosure-read">
        <strong>{disclosure.verdict === "withheld" ? "Withheld" : "Accurate"}:</strong>{" "}
        {disclosure.honesty_read}
      </p>
    </section>
  );
}

function ProjectScene({
  state,
  title,
}: {
  state: ProjectGameState;
  title: string;
}) {
  const tone = projectSceneTone(state);
  const phase = projectPhaseFor(state);
  const phaseImage = projectPhaseImages[phase];
  const headline = criticalBlocker(state) ?? phaseImage.summary;
  return (
    <section className={`project-scene project-scene--${tone}`} aria-label={title}>
      <div className="project-scene__header">
        <p className="eyebrow">Project scene</p>
        <h2>{title}</h2>
        <p>{headline}</p>
      </div>

      <figure className={`project-postcard project-postcard--${phase}`}>
        <img
          alt={phaseImage.alt}
          className="project-postcard__image"
          decoding="sync"
          loading="eager"
          src={phaseImage.src}
        />
      </figure>

      <div className="scene-bars" aria-label="Risk meters">
        <SceneBar
          label="Payment path"
          status={paymentPathLabel(state)}
          tone="cash"
          value={paymentPathScore(state)}
        />
        <SceneBar
          label="Steel release"
          status={releasePathLabel(state)}
          tone="release"
          value={releasePathScore(state)}
        />
        <SceneBar
          label="Project pressure"
          status={pressureLabel(state)}
          tone="risk"
          value={pressureScore(state)}
        />
      </div>
    </section>
  );
}

function SceneBar({
  label,
  status,
  value,
  tone,
}: {
  label: string;
  status: string;
  value: number;
  tone: "cash" | "release" | "risk";
}) {
  const clampedValue = Math.round(Math.max(0, Math.min(100, value)));
  return (
    <div
      aria-label={`${label}: ${status}`}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={clampedValue}
      className={`scene-bar scene-bar--${tone}`}
      role="meter"
    >
      <span>
        {label}
        <strong>{status}</strong>
      </span>
      <div>
        <i style={{ width: `${clampedValue}%` }} />
      </div>
    </div>
  );
}

function PartnerDecisionReview({
  trace,
  state,
  setState,
}: {
  trace: GameEvaluation["currentRoundTrace"];
  state: GameState;
  setState: Dispatch<SetStateAction<GameState>>;
}) {
  if (!trace) {
    return null;
  }
  const partnerMoves = trace.moves.filter((move) => !move.isPlayer);
  return (
    <section className="partner-review-panel" aria-label="Partner decisions and trust">
      <div className="section-title">
        <Users size={20} />
        <h2>Partner decisions and trust</h2>
      </div>
      <p className="trust-update-prompt">
        This is the best public and private information you have about the actions
        your business partners have taken. Do you want to adjust how much you trust
        each partner?
      </p>
      <div className="partner-review-list">
        {partnerMoves.map((move) => {
          const reads = partnerDecisionReads(move);
          return (
            <article className="partner-review-card" key={move.nodeId}>
              <header>
                <strong>{roleLabel(move.actorId)}</strong>
                <em>{move.choiceLabel}</em>
              </header>
              <p>{move.summary}</p>
              <div className="decision-read-grid">
                <div>
                  <span>Charitable read</span>
                  <p>{reads.charitable}</p>
                </div>
                <div>
                  <span>Uncharitable read</span>
                  <p>{reads.uncharitable}</p>
                </div>
              </div>
              <label className="partner-trust-row">
                <span>Trust</span>
                <input
                  aria-label={`Trust rating for ${move.actorId}`}
                  max={5}
                  min={1}
                  type="range"
                  value={state.trustRatings[move.actorId]}
                  onChange={(event) =>
                    setState((current) =>
                      recordTrust(gameData, current, move.actorId, Number(event.target.value))
                    )
                  }
                />
                <strong>{state.trustRatings[move.actorId]}</strong>
              </label>
            </article>
          );
        })}
      </div>
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
  const scheduleDelta =
    evaluation.state.completion_week - evaluation.state.baseline_completion_week;
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
        <Metric icon={<ShieldCheck />} label="Organization target" value={evaluation.playerPrivateSuccess ? "Met" : "Missed"} />
        <Metric icon={<Users />} label="Outcome mix" value={outcomeMixValue(evaluation)} />
        <Metric icon={<Gauge />} label="Schedule vs baseline" value={formatDelta(scheduleDelta, "week")} />
      </div>
      <OutcomeExplanation evaluation={evaluation} role={state.selectedRole} />
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
          <strong>Partners</strong>
          <span>{counterparties.length} counterparty decisions responded to your project state</span>
          <em>state-reactive decisions</em>
        </div>
      </section>

      <TrustCalibrationPanel state={state} averageTrust={averageTrust} />

      <div className="hero-actions">
        <NavButton href="/play" icon={<RotateCcw size={18} />}>
          Play another role
        </NavButton>
        <NavButton href="/results" icon={<Gauge size={18} />}>
          See example runs
        </NavButton>
        <NavButton href="/" icon={<Home size={18} />}>
          Back to overview
        </NavButton>
      </div>
    </section>
  );
}

function TrustCalibrationPanel({
  state,
  averageTrust,
}: {
  state: GameState;
  averageTrust: number;
}) {
  const calibration = trustCalibration(gameData, state);
  return (
    <section className="trust-summary" aria-label="Trust calibration">
      <div className="section-title">
        <MessageSquare size={20} />
        <h2>How well did you read your partners?</h2>
      </div>
      <p className="trust-calibration-lead">
        You rated each partner without seeing their private information. Here is what
        each one was actually responding to — and whether your rating matched.
      </p>
      <div className="trust-summary-card">
        <span>Ratings that matched the partner's real driver</span>
        <strong>
          {calibration.wellCalibratedCount}/{calibration.total}
        </strong>
        <em>Average trust you gave: {averageTrust.toFixed(1)}/5</em>
        <div className="trust-meter" aria-hidden="true">
          <span
            style={{
              width: `${
                calibration.total
                  ? (calibration.wellCalibratedCount / calibration.total) * 100
                  : 0
              }%`,
            }}
          />
        </div>
      </div>
      <div className="trust-calibration-list">
        {calibration.entries.map((entry) => (
          <article
            className={`trust-calibration-card trust-calibration-card--${entry.driver}${
              entry.wellCalibrated ? "" : " trust-calibration-card--miss"
            }`}
            key={entry.actorId}
          >
            <header>
              <strong>{roleLabel(entry.actorId)}</strong>
              <span className="trust-calibration-rating">You rated {entry.playerRating}/5</span>
            </header>
            <p className="trust-calibration-driver">{entry.driverLabel}</p>
            <p className="trust-calibration-read">{entry.read}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function OutcomeExplanation({
  evaluation,
  role,
}: {
  evaluation: GameEvaluation;
  role: AgentId;
}) {
  const privateTarget = gameData.private_success_thresholds[role];
  const privateGap = evaluation.playerPayoff - privateTarget;
  const projectText = evaluation.projectSuccess
    ? "The project stayed within the public cost and schedule limits."
    : "The project missed the public cost or schedule limits.";
  const privateText = evaluation.playerPrivateSuccess
    ? `Your organization also met its private target of ${formatMoney(privateTarget)}.`
    : `Your organization missed its private target of ${formatMoney(privateTarget)} by ${formatMoney(Math.abs(privateGap))}.`;

  return (
    <section className="outcome-explanation" aria-label="Outcome explanation">
      <strong>{evaluation.projectSuccess && !evaluation.playerPrivateSuccess ? "Project success, private miss" : outcomeMixValue(evaluation)}</strong>
      <p>
        {projectText} {privateText}
      </p>
    </section>
  );
}

function ResultsPage() {
  const idealWitness = gameData.witnesses.efficient_phased_coalition_success;
  const failureWitness = gameData.witnesses.excessive_conservatism_failure;
  const blowoutWitness = gameData.witnesses.budget_blowout_failure;
  const baseline = gameData.public_baseline;
  const limits = gameData.initial_game_state;
  const plannedCost = Number(baseline.baseline_planned_project_cost_usd);
  const plannedWeek = Number(baseline.baseline_expected_completion_tick);

  const rows = [
    {
      label: "Coordinated phased success",
      cost: idealWitness.final_project_cost,
      week: idealWitness.completion_tick,
      note: "Every firm gives a little; the project lands despite the steel problem.",
    },
    {
      label: "Excessive-caution failure",
      cost: failureWitness.final_project_cost,
      week: failureWitness.completion_tick,
      note: "Every firm self-protects; the project fails with no deception involved.",
    },
    blowoutWitness
      ? {
          label: "Panic-spending failure",
          cost: blowoutWitness.final_project_cost,
          week: blowoutWitness.completion_tick,
          note: "The coalition buys backup steel, overtime, and standby all at once — on time, but over budget.",
        }
      : null,
  ].filter(
    (row): row is { label: string; cost: number | null; week: number | null; note: string } =>
      row !== null
  );

  return (
    <Shell>
      <section className="overview-section">
        <div className="section-title">
          <ClipboardCheck size={20} />
          <h2>How to read these numbers</h2>
        </div>
        <p>
          Every run below is the same project: a build planned to finish at{" "}
          <strong>{formatMoney(plannedCost)}</strong> in{" "}
          <strong>week {plannedWeek}</strong>. A run counts as a project success
          only if the final cost stays at or under{" "}
          <strong>{formatMoney(limits.success_cost_ceiling_usd)}</strong> and the
          work finishes by <strong>week {limits.success_deadline_week}</strong>.
          Anything between the plan and those limits is money and time the steel
          problem burned. A firm can also miss its own private profit target even
          when the project succeeds — that is the "firms met target" column.
        </p>
        <section className="project-strip" aria-label="Targets">
          <dl>
            <div>
              <dt>Original plan</dt>
              <dd>
                {formatMoney(plannedCost)} / week {plannedWeek}
              </dd>
            </div>
            <div>
              <dt>Success limits</dt>
              <dd>
                {formatMoney(limits.success_cost_ceiling_usd)} / week{" "}
                {limits.success_deadline_week}
              </dd>
            </div>
            <div>
              <dt>Failure modes</dt>
              <dd>Over budget, too late, or unsafe steel installed</dd>
            </div>
            <div>
              <dt>Firms involved</dt>
              <dd>6, each with a private profit target</dd>
            </div>
          </dl>
        </section>
      </section>

      <PopulationSection />

      <section className="overview-section">
        <div className="section-title">
          <Gauge size={20} />
          <h2>Scripted reference paths</h2>
        </div>
        <p>
          These are hand-scripted runs the harness uses as fixed points — what
          coordinated success looks like, and two ways the project fails without
          any deception: everyone playing it too safe, or everyone buying their
          way out of trouble at once.
        </p>
        <section className="comparison-panel" aria-label="Reference paths">
          {rows.map((row) => (
            <div className="comparison-row" key={row.label}>
              <strong>{row.label}</strong>
              <span>{row.cost === null ? "n/a" : formatMoney(row.cost)}</span>
              <span>{row.week === null ? "n/a" : `Week ${row.week}`}</span>
              <em>{row.note}</em>
            </div>
          ))}
        </section>
      </section>
    </Shell>
  );
}

function PopulationSection() {
  const population = populationData;
  if (!population || population.runs.length === 0) {
    return null;
  }
  const validRuns = population.runs.filter((run) => run.run_valid);
  const modelLabel = Array.isArray(population.model)
    ? population.model.join(", ")
    : population.model;
  return (
    <section className="overview-section">
      <div className="section-title">
        <Users size={20} />
        <h2>What the AI agents actually did</h2>
      </div>
      <p>
        Each row is one complete run with <strong>{modelLabel}</strong> playing
        all six firms. Every decision is
        made by the model. {population.project_success_count} of{" "}
        {population.valid_run_count} valid runs finished as project successes;
        final costs ranged {formatMoney(population.cost_min ?? 0)} to{" "}
        {formatMoney(population.cost_max ?? 0)}. "Firms met target" counts how
        many of the six organizations also hit their private profit goals. Anything below
        6 is a cost of coordination that project-level numbers don't capture.
      </p>
      <div className="population-table" role="table" aria-label="Live agent runs">
        <div className="population-row population-row--head" role="row">
          <span>Run</span>
          <span>Outcome</span>
          <span>Final cost</span>
          <span>Finished</span>
          <span>Firms met target</span>
        </div>
        {validRuns.map((run, displayIndex) => (
          <div
            className={`population-row${run.project_success ? "" : " population-row--failed"}`}
            role="row"
            key={`${run.batch}-${run.replicate_index}`}
          >
            <span>
              Run {displayIndex + 1}
              {run.temperature === 0 ? " (deterministic)" : ""}
            </span>
            <span>{populationOutcomeLabel(run)}</span>
            <span>{run.final_project_cost === null ? "n/a" : formatMoney(run.final_project_cost)}</span>
            <span>{run.completion_tick === null ? "n/a" : `Week ${run.completion_tick}`}</span>
            <span>
              {run.firms_meeting_private_target === null
                ? "n/a"
                : `${run.firms_meeting_private_target}/6`}
            </span>
          </div>
        ))}
      </div>
      {population.valid_run_count < population.run_count && (
        <p className="population-footnote">
          {population.run_count - population.valid_run_count} additional run
          {population.run_count - population.valid_run_count === 1 ? "" : "s"}{" "}
          ended early because an agent produced an invalid decision; the harness
          stops those runs rather than guessing. Better repair logic is forthcoming.
        </p>
      )}
    </section>
  );
}

function populationOutcomeLabel(run: PopulationRun) {
  if (run.project_success) {
    return run.coalition_success ? "Success — every firm won" : "Success — some firms lost";
  }
  const labels: Record<string, string> = {
    BUDGET_INFEASIBLE: "Failed — over budget",
    SCHEDULE_INFEASIBLE: "Failed — too late",
    CRITICAL_PATH_DEADLOCK: "Failed — work deadlocked",
  };
  return labels[run.terminal_status] ?? "Failed";
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
    backup_project_success: "Project succeeds, but only after using backup steel",
    phased_coalition_success: "Project succeeds through coordinated phased delivery",
    coordination_delay_failure: "Project fails after coordination delays compound",
    schedule_infeasible: "Project fails because the schedule becomes impossible",
  };
  return labels[pathLabel ?? ""] ?? "Model-produced project outcome";
}

function outcomeMixValue(evaluation: GameEvaluation) {
  if (evaluation.projectSuccess && evaluation.playerPrivateSuccess) {
    return "Aligned";
  }
  if (evaluation.projectSuccess) {
    return "Mixed";
  }
  if (evaluation.playerPrivateSuccess) {
    return "Private only";
  }
  return "Missed";
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
          ConstructSim
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

function projectSceneTone(state: ProjectGameState) {
  if (
    criticalBlocker(state) ||
    state.schedule_risk >= 5 ||
    state.compliance_risk >= 5 ||
    state.completion_week > state.success_deadline_week
  ) {
    return "blocked";
  }
  if (
    state.schedule_risk >= 3 ||
    state.compliance_risk >= 3 ||
    state.cash_secured_usd < 900_000 ||
    !state.lot_b_ready ||
    !state.lot_b_released
  ) {
    return "watch";
  }
  return "clear";
}

function projectPhaseFor(state: ProjectGameState): ProjectPhase {
  if (isOpeningWaitingState(state)) {
    return "empty_lot";
  }
  if (
    criticalBlocker(state) ||
    state.labor_capacity === "released" ||
    state.schedule_risk >= 5 ||
    state.compliance_risk >= 5 ||
    hasStoryFlag(state, "loan_unavailable") ||
    hasStoryFlag(state, "owner_no_support") ||
    hasStoryFlag(state, "gc_rejected_supplier_path")
  ) {
    return "delivery_blocked";
  }
  if (
    state.lot_a_released &&
    state.lot_b_released &&
    state.lot_b_ready &&
    state.labor_capacity !== "uncommitted"
  ) {
    return "erected_structure";
  }
  if (state.lot_a_released && state.lot_b_released) {
    return "erection_progress";
  }
  if (state.lot_a_released || state.lot_b_released) {
    return "steel_delivery";
  }
  if (
    state.cash_secured_usd > 0 ||
    state.compliance_risk > 0 ||
    state.schedule_risk > 0 ||
    state.backup_status !== "none" ||
    hasStoryFlag(state, "supplier_thin_disclosure") ||
    hasStoryFlag(state, "inspection_deeper_review")
  ) {
    return "paperwork_dispute";
  }
  return "empty_lot";
}

function isOpeningWaitingState(state: ProjectGameState) {
  return (
    state.cash_secured_usd === 0 &&
    state.verified_value_usd === 0 &&
    state.release_value_usd === 0 &&
    state.backup_status === "none" &&
    state.labor_capacity === "uncommitted" &&
    !state.lot_a_released &&
    !state.lot_b_released
  );
}

function criticalBlocker(state: ProjectGameState) {
  return (
    state.blockers.find((blocker) =>
      /never|blocked|not available|not released|cash gap|compliance failure|schedule failure|miss/i.test(
        blocker
      )
    ) ?? null
  );
}

function paymentPathScore(state: ProjectGameState) {
  return Math.min(100, (state.cash_secured_usd / 900_000) * 100);
}

function releasePathScore(state: ProjectGameState) {
  if (state.backup_status === "active") {
    return 90;
  }
  let score = 0;
  if (state.lot_a_released) {
    score += 45;
  }
  if (state.lot_b_released) {
    score += 45;
  }
  if (state.release_value_usd > 0) {
    score += 10;
  }
  return Math.min(100, score);
}

function pressureScore(state: ProjectGameState) {
  return Math.min(100, (Math.max(state.schedule_risk, state.compliance_risk) / 6) * 100);
}

function paymentPathLabel(state: ProjectGameState) {
  if (paymentPathScore(state) >= 100) {
    return "ready";
  }
  if (state.cash_secured_usd > 0) {
    return "partial";
  }
  return "unfunded";
}

function releasePathLabel(state: ProjectGameState) {
  if (state.backup_status === "active") {
    return "backup active";
  }
  if (state.lot_a_released && state.lot_b_released) {
    return "released";
  }
  if (state.lot_a_released || state.lot_b_released || state.release_value_usd > 0) {
    return "partial";
  }
  return "held";
}

function pressureLabel(state: ProjectGameState) {
  const score = pressureScore(state);
  if (score >= 80) {
    return "high";
  }
  if (score >= 45) {
    return "watch";
  }
  return "low";
}

function hasStoryFlag(state: ProjectGameState, flag: string) {
  return state.story_flags.includes(flag);
}

function partnerDecisionReads(move: { actorId: AgentId; choiceId: ChoiceId }) {
  const actor = roleLabel(move.actorId).toLowerCase();
  return {
    balanced: {
      charitable:
        `The ${actor} is treating the recovery path as workable and is keeping the project moving while accepting some exposure.`,
      uncharitable:
        `The ${actor} may be pushing ahead before every condition is fully settled because momentum helps their own position.`,
    },
    conservative: {
      charitable:
        `The ${actor} is adding controls because the current package still has real payment, release, or schedule risk.`,
      uncharitable:
        `The ${actor} may be slowing the job and shifting cost, delay, or proof burdens to other players.`,
    },
    self_protective: {
      charitable:
        `The ${actor} is protecting itself from a package that may not be supportable yet.`,
      uncharitable:
        `The ${actor} may be prioritizing its own downside over the shared project schedule.`,
    },
  }[move.choiceId];
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

function formatDelta(value: number, unit: string) {
  const label = Math.abs(value) === 1 ? unit : `${unit}s`;
  if (value === 0) {
    return `0 ${label}`;
  }
  return `${value > 0 ? "+" : ""}${value} ${label}`;
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
