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
import rawResearchProgramData from "./game-data/s01_research_program.json";
import rawResponseCurveData from "./game-data/s01_response_curve.json";
import { fetchCrowdStats, submitPlaythrough } from "./lib/playthroughs";
import type { CrowdStats } from "./lib/playthroughs";
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
  trustReflection,
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
  ResearchProgramData,
  ResearchProgramLadderRow,
  ResponseCurveData,
} from "./lib/types";

const gameData = rawGameData as GameData;
const populationData = rawPopulationData as PopulationData;
const researchProgramData = rawResearchProgramData as ResearchProgramData;
const responseCurveData = rawResponseCurveData as ResponseCurveData;
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
      "The project is waiting for money, approval, and permission to move the steel.",
  },
  paperwork_dispute: {
    alt: "Construction paperwork and payment documents with held steel behind the site fence",
    src: "/images/s01-phase-paperwork-dispute.png",
    summary:
      "The team is still sorting out payment, proof that the steel is ready, and permission to ship it.",
  },
  steel_delivery: {
    alt: "Flatbed truck delivering steel beams to a construction site",
    src: "/images/s01-phase-steel-delivery.png",
    summary:
      "Steel is heading to the site, but later deliveries still depend on payment, approval, and scheduling.",
  },
  delivery_blocked: {
    alt: "Steel delivery truck stopped at a blocked construction gate with paperwork in view",
    src: "/images/s01-phase-delivery-blocked.png",
    summary:
      "Steel cannot reach the site because money, paperwork, approval, or workers are missing.",
  },
  erection_progress: {
    alt: "Crane lifting steel beams into a partially erected structure",
    src: "/images/s01-phase-erection-progress.png",
    summary:
      "Approved steel has arrived, and the crew is putting it up.",
  },
  erected_structure: {
    alt: "Completed steel frame standing on the construction site",
    src: "/images/s01-phase-erected-structure.png",
    summary:
      "The steel frame is nearly complete, and the project can move forward.",
  },
};

const similarWork = [
  {
    name: "CoffeeBench",
    href: "https://arxiv.org/html/2606.16613v1",
    summary: "AI-run companies grow, roast, price, buy, and sell coffee over many rounds.",
  },
  {
    name: "tau-bench",
    href: "https://taubench.com/",
    summary: "Tests whether AI assistants can follow rules, use tools, and handle conversations that change over time.",
  },
  {
    name: "MultiAgentBench",
    href: "https://aclanthology.org/2025.acl-long.421/",
    summary: "Tests how groups of AI systems work together or compete.",
  },
  {
    name: "SOTOPIA",
    href: "https://openreview.net/forum?id=mM7VurbA4r",
    summary: "Places AI systems in social situations and measures how they pursue their goals.",
  },
  {
    name: "Concordia",
    href: "https://github.com/google-deepmind/concordia",
    summary: "Tools for building shared worlds where several AI-run characters can act and interact.",
  },
  {
    name: "Silo-Bench",
    href: "https://arxiv.org/abs/2603.01045",
    summary: "Tests whether separate AI systems can share information and put it together correctly.",
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
  if (route.pathname === "/research") {
    return <ResearchPage />;
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
            We test whether an AI-run company can make good business decisions when
            information is incomplete and conditions can change. We start with one
            company, then follow its decisions into a project shared by several companies.
          </p>
          <p>
            Construction is our first test setting. Six companies share a deadline and
            want to finish the project at a reasonable cost, but each company knows
            different facts, controls different choices, and has its own financial goals.
            They need one another to finish the job. ConstructSim lets each company make
            its own decisions. We also run smaller tests that add one AI-run company at a
            time, so we can see where a bad decision begins.
          </p>
          <p>
            Built by Matt Duffy. I'm open to collaboration. Find me on{" "}
            <a href="https://github.com/mduffster" rel="noreferrer" target="_blank">
              GitHub
            </a>
            ,{" "}
            <a href="https://x.com/iammattduff" rel="noreferrer" target="_blank">
              Twitter
            </a>
            , or{" "}
            <a href="https://seekingsignal.substack.com" rel="noreferrer" target="_blank">
              Substack
            </a>
            .
          </p>
          <div className="hero-actions">
            <NavButton href="/play" icon={<Play size={18} />}>
              Play the scenario
            </NavButton>
            <NavButton href="/results" icon={<Gauge size={18} />}>
              See example runs
            </NavButton>
            <NavButton href="/research" icon={<Eye size={18} />}>
              Read the research
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
          <h2>What we're testing</h2>
        </div>
        <p>
          We test whether AI agents can select useful facts,
          generate a reasonable decision, communicate information to the right partner, and act on that information
          while protecting their own organization. Construction projects are a useful testing ground,
          but the harness and decision structure apply whenever several firms must complete a
          transaction without sharing all of their information or incentives.
        </p>
      </section>

      <ResearchTeaser />

      <section className="overview-section">
        <div className="section-title">
          <Play size={20} />
          <h2>
            <a className="text-link" href="/play">
              Try It
            </a>
          </h2>
        </div>
        <p>
          Play one construction problem involving six companies. You choose one
          of four companies, while the game makes decisions for the lender and
          inspector. You will see facts everyone knows, facts only your company
          knows, and choices that may help your company, the project, or both.
          This public game uses three clear choices at each step. In the research,
          the AI must build a much more detailed answer on its own.
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

function ResearchTeaser() {
  const handoff = researchProgramData.handoff;
  const multiplayer = researchProgramData.multiplayer;
  return (
    <section className="overview-section research-teaser">
      <div className="section-title">
        <Eye size={20} />
        <h2>Latest research</h2>
      </div>
      <div className="research-teaser__layout">
        <div>
          <p className="research-kicker">From one choice to six companies</p>
          <h3>The steel supplier kept asking for about $800K regardless of its real leverage.</h3>
          <p>
            The research follows this supplier decision when another company must pass
            along key information and then when all six companies can make choices. The
            companies had the facts they needed, but they did not always use them well.
            We tried several ways to help. The one that worked was a short summary shown
            only to the supplier before each decision. In this test, putting the important
            facts in front of the supplier worked better than expecting it to find and
            combine them on its own. That suggests an AI should be shown the facts that
            matter when it is time to choose.
          </p>
          <div className="research-mini-metrics" aria-label="Study highlights">
            <span>
              <strong>
                {handoff.assigned_run_count}
              </strong>
              two-company test runs
            </span>
            <span>
              <strong>
                {handoff.safe_action_given_exact_count}/{handoff.exact_live_calculation_count}
              </strong>
              safe choices after correct calculations
            </span>
            <span>
              <strong>{multiplayer.completed_stage_count}/4</strong>
              tests with more AI-run companies
            </span>
          </div>
          <NavButton href="/research" icon={<ArrowRight size={18} />}>
            Read the findings
          </NavButton>
        </div>
        <figure className="research-figure research-figure--compact">
          <img
            alt="Line chart showing the rational safe supplier request rising while Haiku requests stay nearly flat and Sonnet requests remain high"
            src="/images/s01-response-curve.png"
          />
          <figcaption>
            The first test found this pricing mistake. Later tests followed the same
            choice through two companies and then through a six-company project.
          </figcaption>
        </figure>
      </div>
    </section>
  );
}

function ResearchPage() {
  const haiku = responseCurveData.haiku_confirmation;
  const sonnet = responseCurveData.sonnet_confirmation;
  return (
    <Shell>
      <section className="page-head research-head">
        <p className="eyebrow">Research</p>
        <h1>From one decision to six companies</h1>
        <p className="lede">
          Can AI-run companies receive the right information, pass it to one another,
          and make sound business decisions?
        </p>
        <p>
          We add one source of difficulty at a time: one AI-run company, two
          companies that must share a useful number, a project with as many as six
          AI-run companies, and finally several ways of putting useful facts in
          front of the decision maker. This helps us tell whether a bad result began
          with missing information, a message that did not help, a wrong calculation,
          or a poor business choice.
        </p>
      </section>

      <ResearchProgramOverview />

      <section className="overview-section research-methods-callout" aria-label="Fair comparisons">
        <div className="section-title">
          <ShieldCheck size={20} />
          <h2>How we make the comparisons fair</h2>
        </div>
        <p>
          Each comparison changes one thing and keeps the rest of the project the
          same. Before a test begins, we decide what will change and what counts as
          success. That makes it easier to tell whether the thing we changed actually
          caused a different result.
        </p>
      </section>

      <section className="overview-section" id="response-curve">
        <div className="section-title">
          <Gauge size={20} />
          <h2>Stage 1 — does the supplier ask for more when it is harder to replace?</h2>
        </div>
        <p>
          An AI system makes decisions for the steel supplier while the other five
          companies follow fixed rules. We change only the extra cost of replacing
          the supplier. When replacement becomes cheaper, does the supplier ask for
          less money so the project has a reason to keep it?
        </p>
        <div className="metric-grid research-metric-grid">
          <Metric
            icon={<ClipboardCheck size={20} />}
            label="Completed Haiku runs"
            value={`${haiku.valid_run_count}/${haiku.run_count} runs`}
          />
          <Metric
            icon={<RotateCcw size={20} />}
            label="Supplier replaced"
            value={`${Math.round(haiku.replacement_rate * 100)}%`}
          />
          <Metric
            icon={<DollarSign size={20} />}
            label="Average money left on the table"
            value={formatRoundedResearchMoney(haiku.mean_attainable_regret_usd)}
          />
        </div>
        <p className="body-copy">
          Haiku asked for about $800K in 39 completed runs and $600K in seven,
          even though the highest amount it could safely ask for changed by $1M.
        </p>
        <div className="research-program-takeaway research-program-takeaway--plain">
          <strong>The 15 Sonnet runs showed the same basic problem.</strong>
          <p>
            We ran Sonnet three times at each replacement cost. The project replaced
            the supplier in {Math.round(sonnet.replacement_rate * 100)}% of those runs,
            and the supplier missed out on about{" "}
            {formatRoundedResearchMoney(sonnet.mean_attainable_regret_usd)} per run by
            making a weaker request than it could have. Sonnet did better when the
            supplier was hardest to replace, but once asked for less even though its
            replacing it had become more expensive. This result describes this one problem;
            it is not a general ranking of the models.
          </p>
        </div>
      </section>

      <section className="overview-section">
        <div className="section-title">
          <ClipboardCheck size={20} />
          <h2>How the test works</h2>
        </div>
        <div className="research-method-grid">
          <article>
            <span>1</span>
            <strong>Keep everything else the same</strong>
            <p>The supplier always faces the same added cost, cash need, contract, and deadline.</p>
          </article>
          <article>
            <span>2</span>
            <strong>Make replacement cheaper or more expensive</strong>
            <p>Only the extra cost of hiring another supplier changes, from $0 to $1 million.</p>
          </article>
          <article>
            <span>3</span>
            <strong>Compare the request with the best safe choice</strong>
            <p>We check how much the supplier asked for and whether that request caused the project to replace it.</p>
          </article>
        </div>
      </section>

      <section className="overview-section research-chart-section">
        <div className="section-title">
          <Eye size={20} />
          <h2>How the request should change</h2>
        </div>
        <p>
          A supplier can safely ask for more money when replacing it would cost the
          project more. The black line shows that rising limit. The AI's requests
          stay almost flat or move in the wrong direction.
        </p>
        <figure className="research-figure">
          <img
            alt="Chart comparing the highest safe supplier request with requests made by Haiku and Sonnet"
            src="/images/s01-response-curve.png"
          />
          <figcaption>
            The thin Sonnet line shows one early example. The table below uses the
            later test with three Sonnet runs at each replacement cost.
          </figcaption>
        </figure>
        <div className="research-table" role="table" aria-label="Supplier request results">
          <div className="research-table__row research-table__row--head" role="row">
            <span>Extra cost to replace supplier</span>
            <span>Highest request before replacement</span>
            <span>Haiku, current facts only</span>
            <span>Haiku, with past results</span>
            <span>Sonnet, three runs each</span>
          </div>
          {responseCurveData.levels.map((level) => (
            <div className="research-table__row" role="row" key={level.response_curve_level}>
              <span data-label="Extra cost to replace supplier">
                {formatMoney(level.replacement_cost_usd)}
              </span>
              <span data-label="Highest request before replacement">
                {formatMoney(level.maximum_safe_relief_usd)}
              </span>
              <span data-label="Haiku, current facts only">
                {formatRoundedResearchMoney(level.haiku_no_history_mean_request_usd)}
              </span>
              <span data-label="Haiku, with past results">
                {formatRoundedResearchMoney(level.haiku_history_mean_request_usd)}
              </span>
              <span data-label="Sonnet, three runs each">
                {formatRoundedResearchMoney(level.sonnet_confirmation_mean_request_usd)}
              </span>
            </div>
          ))}
        </div>
      </section>

      <ResponseCurveMechanismSection />

      <HandoffResearchSection />

      <MultiplayerResearchSection />

      <DecisionPacketResearchSection />

      <section className="overview-section research-reading">
        <div>
          <div className="section-title">
            <DollarSign size={20} />
            <h2>Why it matters</h2>
          </div>
          <p>
            A project can finish while one of its companies loses money or misses
            its own goal. These tests ask two separate questions: did each company
            receive the facts it needed, and did it make a good choice with those facts?
          </p>
        </div>
        <div>
          <div className="section-title">
            <ShieldCheck size={20} />
            <h2>How to read this</h2>
          </div>
          <p>
            These results come from one simulated construction problem. They are not
            a general ranking of AI models. Some tests have only one run, repeated
            runs of the same AI are not the same as testing different people, all
            tested AI systems come from one provider, and we have not yet compared their
            choices with those of construction professionals.
          </p>
        </div>
      </section>

      <section className="overview-section research-source">
        <div className="section-title">
          <Building2 size={20} />
          <h2>Evidence and code</h2>
        </div>
        <p>
          The study plans, results, and code are public so other people can inspect
          the work and decide whether the conclusions are justified.
        </p>
        <div className="research-source-links">
          <ResearchSourceLink
            href="https://github.com/mduffster/constructsim/blob/main/docs/evidence/response_curve/evidence_package.md"
            label="Supplier request evidence"
          />
          <ResearchSourceLink
            href="https://github.com/mduffster/constructsim/blob/main/docs/s01_response_curve_sonnet_confirmation_results.md"
            label="Sonnet follow-up results"
          />
          <ResearchSourceLink
            href="https://github.com/mduffster/constructsim/blob/main/docs/s01_distributed_threshold_handoff_results.md"
            label="Two-company information-sharing results"
          />
          <ResearchSourceLink
            href="https://github.com/mduffster/constructsim/blob/main/docs/s01_v2_multiplayer_bridge_results.md"
            label="Six-company results"
          />
          <ResearchSourceLink
            href="https://github.com/mduffster/constructsim/blob/main/docs/s01_v2_derived_state_packet_results.md"
            label="Decision-summary pilot"
          />
          <ResearchSourceLink
            href="https://github.com/mduffster/constructsim/blob/main/docs/s01_v2_decision_summary_factorial_results.md"
            label="Short-summary comparison"
          />
        </div>
      </section>
    </Shell>
  );
}

function ResearchProgramOverview() {
  const handoff = researchProgramData.handoff;
  const multiplayer = researchProgramData.multiplayer;
  const factorial = researchProgramData.decision_summary_factorial;
  const trustedThreshold = responseCurveData.mechanism_test.trusted_threshold_effect;
  return (
    <section className="overview-section research-program-overview">
      <div className="section-title">
        <ClipboardCheck size={20} />
        <h2>What we have learned so far</h2>
      </div>
      <div className="research-program-grid">
        <article>
          <span className="research-stage-chip">1 AI-run company</span>
          <strong>Choosing how much to ask for</strong>
          <p>
            The supplier barely changed its request as replacing it became more
            expensive. When we gave it the highest request that would not cause
            replacement, it left{" "}
            {Math.round(trustedThreshold.mean_attainable_regret_reduction_fraction * 100)}%
            less money on the table.
          </p>
          <a href="#response-curve">See the supplier test</a>
        </article>
        <article>
          <span className="research-stage-chip">2 AI-run companies</span>
          <strong>Passing the key number</strong>
          <p>
            {handoff.valid_run_count} of {handoff.assigned_run_count} planned runs
            produced usable results. Whenever the contractor calculated the right
            limit, the supplier made a safe choice.
          </p>
          <a href="#handoff">See the two-company test</a>
        </article>
        <article>
          <span className="research-stage-chip">Up to 6 AI-run companies</span>
          <strong>Adding more companies</strong>
          <p>
            All {multiplayer.completed_stage_count} tests reached a complete project
            result. The right messages arrived, but every AI-run group spent more
            than the lower-cost example and left at least one company short of its goal.
          </p>
          <a href="#multiplayer">See what happened as the group grew</a>
        </article>
        <article>
          <span className="research-stage-chip">2 companies, 4 setups</span>
          <strong>Who needs the short summary?</strong>
          <p>
            All 20 runs with a supplier summary met every company's goal without
            backup steel. None of the 20 runs without that summary did. A summary for
            the contractor did not change the result.
          </p>
          <a href="#decision-packet">See the summary test</a>
        </article>
      </div>
      <div className="research-program-takeaway">
        <strong>What this suggests</strong>
        <p>
          Getting facts to the right company was not enough. A short summary helped
          the supplier connect how much steel had been verified, how much money was
          available, and how much cash it needed. The result held across{" "}
          {factorial.assigned_run_count} runs without showing the supplier's private
          cash needs to the contractor.
        </p>
      </div>
    </section>
  );
}

function HandoffResearchSection() {
  const handoff = researchProgramData.handoff;
  return (
    <section className="overview-section" id="handoff">
      <div className="section-title">
        <MessageSquare size={20} />
        <h2>Stage 2 — can one company give another company the number it needs?</h2>
      </div>
      <p>
        The general contractor—the company managing the overall build—calculates the
        highest request the supplier can make without being replaced. It then sends
        that number to the supplier. We compare a known correct calculation with an
        AI-run contractor that must work out the number and send it on its own.
      </p>
      <div className="metric-grid research-metric-grid">
        <Metric
          icon={<ClipboardCheck size={20} />}
          label="Planned runs completed"
          value={`${handoff.valid_run_count}/${handoff.assigned_run_count}`}
        />
        <Metric
          icon={<CheckCircle2 size={20} />}
          label="Safe supplier choices after correct calculations"
          value={`${handoff.safe_action_given_exact_count}/${handoff.exact_live_calculation_count}`}
        />
        <Metric
          icon={<MessageSquare size={20} />}
          label="AI contractor, written note"
          value={formatRate(handoff.arms.find((arm) => arm.arm_id === "live-prose")!.end_to_end_success_rate)}
        />
        <Metric
          icon={<Building2 size={20} />}
          label="AI contractor, form fields"
          value={formatRate(handoff.arms.find((arm) => arm.arm_id === "live-structured")!.end_to_end_success_rate)}
        />
      </div>
      <div className="program-table" role="table" aria-label="Two-company information-sharing results">
        <div className="program-row program-row--handoff program-row--head" role="row">
          <span>Who calculated it</span>
          <span>How it was sent</span>
          <span>Completed</span>
          <span>Right number</span>
          <span>Safe choice</span>
          <span>Supplier replaced</span>
        </div>
        {handoff.arms.map((arm) => (
          <div className="program-row program-row--handoff" role="row" key={arm.arm_id}>
            <span data-label="Who calculated it">{handoffSenderLabel(arm.sender)}</span>
            <span data-label="How it was sent">{handoffFormatLabel(arm.representation)}</span>
            <span data-label="Completed">
              {arm.valid_run_count}/{arm.assigned_run_count}
            </span>
            <span data-label="Right number">{formatRate(arm.exact_transfer_itt_rate)}</span>
            <span data-label="Safe choice">{formatRate(arm.end_to_end_success_rate)}</span>
            <span data-label="Supplier replaced">{formatRate(arm.replacement_rate)}</span>
          </div>
        ))}
      </div>
      <div className="research-program-takeaway research-program-takeaway--plain">
        <strong>The message format was not the main problem.</strong>
        <p>
          A written note and a set of form fields worked equally well when the
          contractor calculated the right number. Most failures happened before the
          message was sent, when the contractor chose the wrong facts or calculated
          the number incorrectly.
        </p>
      </div>
      <p className="mechanism-caveat">
        These are repeat runs of the same AI models, not different people. Every
        planned run is included. If the AI did not make a usable required choice,
        that run did not count as a success.
      </p>
    </section>
  );
}

function MultiplayerResearchSection() {
  const multiplayer = researchProgramData.multiplayer;
  const reference = multiplayer.reference;
  const efficient = multiplayer.efficient_reference_path;
  const live = multiplayer.common_live_path;
  return (
    <section className="overview-section" id="multiplayer">
      <div className="section-title">
        <Users size={20} />
        <h2>Stage 3 — what happens as more companies use AI?</h2>
      </div>
      <p>
        We started with an AI-run supplier and contractor, then added the inspector,
        owner, lender, and labor company one at a time. Companies not yet run by AI
        followed fixed rules based on what had happened in the project. A test counted
        as complete only if every required company made a usable choice and the needed
        messages reached the next company.
      </p>
      <div className="metric-grid research-metric-grid">
        <Metric
          icon={<CheckCircle2 size={20} />}
          label="Tests completed"
          value={`${multiplayer.completed_stage_count}/4`}
        />
        <Metric
          icon={<Eye size={20} />}
          label="Expected messages received"
          value={`${multiplayer.expected_exposure_count}/${multiplayer.expected_exposure_count}`}
        />
        <Metric
          icon={<ShieldCheck size={20} />}
          label="Decisions that took effect"
          value={`${multiplayer.operative_link_count}/${multiplayer.operative_link_count}`}
        />
      </div>
      <div className="program-table" role="table" aria-label="Results by number of AI-run companies">
        <div className="program-row program-row--ladder program-row--head" role="row">
          <span>AI-run companies</span>
          <span>Project</span>
          <span>All companies met goals</span>
          <span>Final cost</span>
          <span>Finished</span>
        </div>
        <div className="program-row program-row--ladder program-row--reference" role="row">
          <span data-label="AI-run companies">Written example</span>
          <span data-label="Project">{yesNo(reference.project_success)}</span>
          <span data-label="All companies met goals">{yesNo(reference.coalition_success)}</span>
          <span data-label="Final cost">{formatMoney(reference.final_project_cost)}</span>
          <span data-label="Finished">Week {reference.completion_tick}</span>
        </div>
        {multiplayer.rows.map((row) => (
          <div className="program-row program-row--ladder" role="row" key={row.stage_id}>
            <span data-label="AI-run companies">{ladderStageLabel(row)}</span>
            <span data-label="Project">{yesNo(row.project_success)}</span>
            <span data-label="All companies met goals">{yesNo(row.coalition_success)}</span>
            <span data-label="Final cost">{formatMoney(row.final_project_cost)}</span>
            <span data-label="Finished">Week {row.completion_tick}</span>
          </div>
        ))}
      </div>
      <div className="path-contrast-grid">
        <article>
          <span>Lower-cost written example</span>
          <strong>{formatMoney(efficient.supplier_payment_request_usd)} request</strong>
          <ul>
            <li>{efficient.gc_inspector_routed_document_count} documents sent to the inspector</li>
            <li>Both steel lots prepared</li>
            <li>Both lots shipped</li>
            <li>Steel shipped in stages; backup canceled</li>
          </ul>
        </article>
        <article className="path-contrast-grid__live">
          <span>Every AI-run version</span>
          <strong>{formatMoney(live.supplier_payment_request_usd)} request</strong>
          <ul>
            <li>{live.gc_inspector_routed_document_count} Lot A documents sent to the inspector</li>
            <li>Only Lot A prepared</li>
            <li>Lot A shipped; the second batch was held back</li>
            <li>Backup steel was kept available and then used</li>
          </ul>
        </article>
      </div>
      <div className="research-program-takeaway research-program-takeaway--plain">
        <strong>The information arrived, but the strategy was still expensive.</strong>
        <p>
          Every AI-run group planned only for the first steel batch. That left the
          second batch unavailable and forced the project to buy expensive backup steel.
          The first costly choice came when the supplier and contractor set that plan,
          so the next test focused on those two companies.
        </p>
      </div>
      <p className="mechanism-caveat">
        There is only one run at each company count. That is enough to show that the
        larger setup works, but not enough to tell us how often this result would happen
        or which company caused it.
      </p>
    </section>
  );
}

function DecisionPacketResearchSection() {
  const factorial = researchProgramData.decision_summary_factorial;
  const withSupplier = factorial.arms.filter((arm) =>
    ["supplier_only", "both_summaries"].includes(arm.condition_id)
  );
  const withoutSupplier = factorial.arms.filter((arm) =>
    ["no_summary", "contractor_only"].includes(arm.condition_id)
  );
  const withSupplierJoint = withSupplier.reduce(
    (total, arm) => total + arm.joint_outcome_count,
    0
  );
  const withoutSupplierJoint = withoutSupplier.reduce(
    (total, arm) => total + arm.joint_outcome_count,
    0
  );
  return (
    <section className="overview-section" id="decision-packet">
      <div className="section-title">
        <ClipboardCheck size={20} />
        <h2>Stage 4 — which company needs the short summary?</h2>
      </div>
      <p>
        The supplier and contractor were run by AI while the other four companies
        followed fixed rules. We compared four setups: no summary, a supplier summary,
        a contractor summary, and both summaries. Each
        summary used only facts that company was already allowed to know. The supplier's
        private cash needs never appeared in the contractor's summary.
      </p>
      <div className="metric-grid research-metric-grid">
        <Metric
          icon={<CheckCircle2 size={20} />}
          label="Completed runs"
          value={`${factorial.valid_run_count}/${factorial.assigned_run_count}`}
        />
        <Metric
          icon={<ClipboardCheck size={20} />}
          label="Without a supplier summary"
          value={`${withoutSupplierJoint}/20 good results`}
        />
        <Metric
          icon={<ShieldCheck size={20} />}
          label="With a supplier summary"
          value={`${withSupplierJoint}/20 good results`}
        />
        <Metric
          icon={<MessageSquare size={20} />}
          label="Did a contractor summary change the result?"
          value={factorial.contractor_summary_risk_difference === 0 ? "No" : "Yes"}
        />
      </div>
      <div className="program-table" role="table" aria-label="Decision summary results">
        <div className="program-row program-row--packet program-row--head" role="row">
          <span>Version</span>
          <span>All companies met goals, no backup</span>
          <span>Uncertainty from only 10 runs</span>
          <span>Both steel batches fixed</span>
          <span>Used backup steel</span>
          <span>Finished</span>
          <span>Average cost</span>
        </div>
        {factorial.arms.map((arm) => (
          <FactorialResultRow arm={arm} key={arm.condition_id} />
        ))}
      </div>
      <div className="research-program-takeaway">
        <strong>The supplier summary was the part that changed the result.</strong>
        <p>
          Both setups with a supplier summary fixed both steel batches in every run,
          made the second batch ready, and avoided backup steel. Neither setup without
          that summary reached the same result. Giving the contractor a summary did
          not change what happened.
        </p>
      </div>
      <p className="mechanism-caveat">
        Each setup was tested ten times in this one simulated problem. The wide
        uncertainty ranges show how little ten runs can tell us about what would
        happen elsewhere. This test shows which company benefited from a summary,
        but not which sentence inside the summary made the difference.
      </p>
    </section>
  );
}

function FactorialResultRow({
  arm,
}: {
  arm: ResearchProgramData["decision_summary_factorial"]["arms"][number];
}) {
  return (
    <div
      className={`program-row program-row--packet${
        arm.condition_id.includes("supplier") || arm.condition_id === "both_summaries"
          ? " program-row--packet-treatment"
          : ""
      }`}
      role="row"
    >
      <span data-label="Version">{factorialConditionLabel(arm.condition_id)}</span>
      <span data-label="All companies met goals, no backup">
        {arm.joint_outcome_count}/{arm.assigned_run_count}
      </span>
      <span data-label="Uncertainty from only 10 runs">
        {formatPercentInterval(arm.joint_outcome_exact_95_ci)}
      </span>
      <span data-label="Both steel batches fixed">
        {arm.full_sequence_cure_count}/{arm.assigned_run_count}
      </span>
      <span data-label="Used backup steel">
        {arm.backup_activation_count}/{arm.assigned_run_count}
      </span>
      <span data-label="Finished">Week {arm.mean_completion_tick}</span>
      <span data-label="Average cost">{formatMoney(arm.mean_final_project_cost)}</span>
    </div>
  );
}

function factorialConditionLabel(value: string) {
  return {
    no_summary: "No summary",
    supplier_only: "Supplier only",
    contractor_only: "Contractor only",
    both_summaries: "Both companies",
  }[value] ?? value;
}

function formatPercentInterval(interval: [number, number]) {
  return `${Math.round(interval[0] * 100)}%–${Math.round(interval[1] * 100)}%`;
}

function ladderStageLabel(row: ResearchProgramLadderRow) {
  return `${row.live_role_count} AI-run`;
}

function yesNo(value: boolean) {
  return value ? "Yes" : "No";
}

function formatRate(value: number) {
  return `${Math.round(value * 100)}%`;
}

function handoffSenderLabel(value: string) {
  return value === "Scripted GC" ? "Known correct calculation" : "AI-run contractor";
}

function handoffFormatLabel(value: string) {
  const labels: Record<string, string> = {
    "No handoff": "No message",
    "Rendered prose": "Written message",
    "Structured record": "Form fields",
  };
  return labels[value] ?? value;
}

function ResearchSourceLink({ href, label }: { href: string; label: string }) {
  return (
    <a className="text-link" href={href} rel="noreferrer" target="_blank">
      {label} <ArrowRight size={16} />
    </a>
  );
}

function PlayLanding() {
  return (
    <Shell variant="game">
      <section className="page-head">
        <p className="eyebrow">Choose your organization</p>
        <h1>Play the steel payment problem</h1>
        <p className="lede">
          Choose one of four companies and make three decisions during a troubled
          steel delivery. The game makes decisions for the lender and inspector,
          and their choices can still change what happens. Your three options at
          each step are simplified versions of the more detailed answers the AI
          must produce in the research.
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
        <strong>Companies run by the game:</strong>{" "}
        {gameData.system_roles.map((roleId) => roleLabel(roleId)).join(", ")}.
        They can approve steel, release money, block work, or let it proceed.
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
                  className={`choice-card choice-card--${choice.choice_id}`}
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
              <dt>Steel contract</dt>
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
            <h2>What everyone knows</h2>
          </div>
          <ul className="info-list">
            {node.critical_updates.slice(0, 2).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="info-panel info-panel--private" aria-label="Information only your company knows">
          <div className="section-title">
            <ShieldCheck size={20} />
            <h2>What only your company knows</h2>
          </div>
          <p>{node.situation}</p>
          <ul>
            {node.private_stakes.slice(0, 2).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
      {node.terms.length > 0 ? (
        <div className="term-list" aria-label="Words used in this decision">
          {node.terms.map((item) => (
            <div key={item.term}>
              <strong>{item.term}</strong>
              <span>{item.meaning}</span>
            </div>
          ))}
        </div>
      ) : null}
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
        The research tracks whether a company's public claim matches what it
        privately knows. Here is what your choice communicated.
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
          label="Money available"
          status={paymentPathLabel(state)}
          tone="cash"
          value={paymentPathScore(state)}
        />
        <SceneBar
          label="Steel cleared to move"
          status={releasePathLabel(state)}
          tone="release"
          value={releasePathScore(state)}
        />
        <SceneBar
          label="Schedule and safety risk"
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
        Trust is optional and does not change the project. Each slider starts at 3,
        meaning neutral. Move it only if you want to record a view. At the end, we
        describe what your ratings suggest you believed about each partner; they are
        not compared with the choices the game made for that partner.
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
                  <span>Most generous reading</span>
                  <p>{reads.charitable}</p>
                </div>
                <div>
                  <span>Most skeptical reading</span>
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
                  value={state.trustRatings[move.actorId] ?? 3}
                  onChange={(event) =>
                    setState((current) =>
                      recordTrust(gameData, current, move.actorId, Number(event.target.value))
                    )
                  }
                />
                <strong>{state.trustRatings[move.actorId] ?? 3}</strong>
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
    trustRatings.length > 0
      ? trustRatings.reduce((total, rating) => total + rating, 0) / trustRatings.length
      : null;
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
        <Metric icon={<DollarSign />} label="Your company's financial result" value={formatMoney(evaluation.playerPayoff)} />
        <Metric icon={<ShieldCheck />} label="Your company's goal" value={evaluation.playerPrivateSuccess ? "Met" : "Missed"} />
        <Metric icon={<Users />} label="Project and your company" value={outcomeMixValue(evaluation)} />
        <Metric icon={<Gauge />} label="Delay from original plan" value={formatDelta(scheduleDelta, "week")} />
      </div>
      <OutcomeExplanation evaluation={evaluation} role={state.selectedRole} />
      <ComparisonPanel evaluation={evaluation} />
      <CrowdComparisonPanel
        state={state}
        evaluation={evaluation}
        playerNodes={playerNodes}
      />

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
          <strong>Other companies</strong>
          <span>{counterparties.length} decisions were made based on what had happened so far</span>
          <em>Choices changed with the project</em>
        </div>
      </section>

      <TrustReflectionPanel state={state} averageTrust={averageTrust} />

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

function CrowdComparisonPanel({
  state,
  evaluation,
  playerNodes,
}: {
  state: GameState;
  evaluation: GameEvaluation;
  playerNodes: DecisionNode[];
}) {
  const [stats, setStats] = useState<CrowdStats | null>(null);
  useEffect(() => {
    let cancelled = false;
    const nodeIds = playerNodes.map((node) => node.node_id);
    submitPlaythrough({
      role: state.selectedRole,
      decisions: state.decisions,
      projectSuccess: evaluation.projectSuccess,
      privateSuccess: evaluation.playerPrivateSuccess,
      costUsd: evaluation.state.cost_usd,
      completionWeek: evaluation.state.completion_week,
    })
      .then(() => fetchCrowdStats(state.selectedRole, nodeIds))
      .then((crowd) => {
        if (!cancelled) {
          setStats(crowd);
        }
      });
    return () => {
      cancelled = true;
    };
    // Submit and fetch exactly once per completed game.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!stats) {
    return null;
  }

  const validAgentRuns = populationData.valid_run_count;
  const agentSuccesses = populationData.project_success_count;
  if (stats.rolePlays <= 1) {
    return (
      <section className="crowd-panel" aria-label="Player comparison">
        <div className="section-title">
          <Users size={20} />
          <h2>You vs. other players</h2>
        </div>
        <p>
          You are the first recorded {roleLabel(state.selectedRole)} playthrough.
          As more people play, this panel will show how your calls compare to
          theirs — and to the {validAgentRuns} completed runs where AI made the
          choices, of which{" "}
          {agentSuccesses} ended in project success.
        </p>
      </section>
    );
  }

  const successRate = Math.round(
    (stats.projectSuccessCount / stats.rolePlays) * 100
  );
  return (
    <section className="crowd-panel" aria-label="Player comparison">
      <div className="section-title">
        <Users size={20} />
        <h2>You vs. other players</h2>
      </div>
      <p>
        {stats.rolePlays} people have finished a playthrough as the{" "}
        {roleLabel(state.selectedRole)}. {successRate}% reached project success
        — AI made the choices in {validAgentRuns} other completed runs, with{" "}
        {agentSuccesses} project successes. Here is how your choices compare:
      </p>
      <div className="crowd-list">
        {playerNodes.map((node) => {
          const yourChoiceId = state.decisions[node.node_id];
          const yourChoice = node.choices.find(
            (choice) => choice.choice_id === yourChoiceId
          );
          const counts = stats.nodes[node.node_id] ?? {};
          const totalAtNode = node.choices.reduce(
            (total, choice) => total + (counts[choice.choice_id] ?? 0),
            0
          );
          const sameCalls = counts[yourChoiceId] ?? 0;
          return (
            <article className="crowd-row" key={node.node_id}>
              <header>
                <strong>{node.title}</strong>
                <span>
                  You chose “{yourChoice?.label}” — so did{" "}
                  {totalAtNode
                    ? `${Math.round((sameCalls / totalAtNode) * 100)}% of players`
                    : "no one else yet"}
                </span>
              </header>
              <div className="crowd-bar" aria-hidden="true">
                {node.choices.map((choice) => (
                  <span
                    className={`crowd-bar-segment crowd-bar-segment--${choice.choice_id}${
                      choice.choice_id === yourChoiceId
                        ? " crowd-bar-segment--yours"
                        : ""
                    }`}
                    key={choice.choice_id}
                    style={{
                      flexGrow: Math.max(counts[choice.choice_id] ?? 0, 0.01),
                    }}
                    title={`${choice.label}: ${counts[choice.choice_id] ?? 0}`}
                  />
                ))}
              </div>
              <footer>
                {node.choices.map((choice) => (
                  <span key={choice.choice_id}>
                    {choice.label}: {counts[choice.choice_id] ?? 0}
                  </span>
                ))}
              </footer>
            </article>
          );
        })}
      </div>
      {stats.averageCostUsd !== null && stats.averageCompletionWeek !== null ? (
        <p className="crowd-averages">
          Average player finish: {formatMoney(stats.averageCostUsd)} at week{" "}
          {stats.averageCompletionWeek}. Yours:{" "}
          {formatMoney(evaluation.state.cost_usd)} at week{" "}
          {evaluation.state.completion_week}.
        </p>
      ) : null}
    </section>
  );
}

function TrustReflectionPanel({
  state,
  averageTrust,
}: {
  state: GameState;
  averageTrust: number | null;
}) {
  const reflection = trustReflection(gameData, state);
  return (
    <section className="trust-summary" aria-label="Trust reflection">
      <div className="section-title">
        <MessageSquare size={20} />
        <h2>How did you read your partners?</h2>
      </div>
      <p className="trust-calibration-lead">
        These ratings describe what you expected from each partner. There is no right
        answer here, and the game does not treat any partner it controls as good or bad.
      </p>
      <div className="trust-summary-card">
        <span>Partners you chose to rate</span>
        <strong>
          {reflection.ratedCount}/{reflection.total}
        </strong>
        <em>
          {averageTrust === null
            ? "No trust ratings recorded"
            : `Average trust you gave: ${averageTrust.toFixed(1)}/5`}
        </em>
        <div className="trust-meter" aria-hidden="true">
          <span
            style={{
              width: `${
                reflection.total
                  ? (reflection.ratedCount / reflection.total) * 100
                  : 0
              }%`,
            }}
          />
        </div>
      </div>
      <div className="trust-calibration-list">
        {reflection.entries.map((entry) => (
          <article className="trust-calibration-card" key={entry.actorId}>
            <header>
              <strong>{roleLabel(entry.actorId)}</strong>
              <span className="trust-calibration-rating">
                {entry.playerRating === null ? "Not rated" : `You rated ${entry.playerRating}/5`}
              </span>
            </header>
            <p className="trust-calibration-driver">{entry.ratingLabel}</p>
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
    ? `Your company also met its financial goal of ${formatMoney(privateTarget)}.`
    : `Your company missed its financial goal of ${formatMoney(privateTarget)} by ${formatMoney(Math.abs(privateGap))}.`;

  return (
    <section className="outcome-explanation" aria-label="Outcome explanation">
      <strong>{evaluation.projectSuccess && !evaluation.playerPrivateSuccess ? "The project succeeded, but your company missed its goal" : outcomeMixValue(evaluation)}</strong>
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
      label: "Success through shared compromise",
      cost: idealWitness.final_project_cost,
      week: idealWitness.completion_tick,
      note: "Every company gives a little, and the project succeeds despite the steel problem.",
    },
    {
      label: "Failure from too much caution",
      cost: failureWitness.final_project_cost,
      week: failureWitness.completion_tick,
      note: "Every company protects itself, and the project fails even though no one lies.",
    },
    blowoutWitness
      ? {
          label: "Failure from emergency spending",
          cost: blowoutWitness.final_project_cost,
          week: blowoutWitness.completion_tick,
          note: "The team buys backup steel, overtime, and pays workers to wait — on time, but over budget.",
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
          Anything between the plan and those limits is money and time lost to the
          steel problem. A company can also miss its own financial goal even when
          the project succeeds. The "companies meeting goals" column shows that.
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
              <dt>Companies involved</dt>
              <dd>6, each with its own financial goal</dd>
            </div>
          </dl>
        </section>
      </section>

      <section className="research-crosslink" aria-label="Latest research">
        <div>
          <strong>Looking for the latest findings?</strong>
          <span>
            The Research page follows one supplier choice from a one-company test,
            through a two-company information test, and into 40 runs that compare
            different short summaries.
          </span>
        </div>
        <a href="/research#decision-packet">
          Read the findings <ArrowRight size={16} />
        </a>
      </section>

      <PopulationSection />

      <section className="overview-section">
        <div className="section-title">
          <Gauge size={20} />
          <h2>Written examples for comparison</h2>
        </div>
        <p>
          We wrote these examples by hand to show one route where the companies
          work together successfully and two routes where the project fails without
          anyone lying: every company protects itself too much, or every company
          spends heavily at the same time.
        </p>
        <section className="comparison-panel" aria-label="Written examples for comparison">
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

function ResponseCurveMechanismSection() {
  const mechanism = responseCurveData.mechanism_test;
  const reduction = Math.round(
    mechanism.trusted_threshold_effect.mean_attainable_regret_reduction_fraction * 100
  );
  return (
    <section className="overview-section mechanism-result">
      <div className="section-title">
        <Eye size={20} />
        <h2>Why did the supplier make poor requests?</h2>
      </div>
      <p className="mechanism-lede">
        <strong>A formula was not enough. The correct limit was.</strong>{" "}
        We repeated the same supplier choice with three kinds of help while keeping
        the project and the other companies the same.
      </p>

      <div className="mechanism-table" role="table" aria-label="Supplier decision support results">
        <div className="mechanism-row mechanism-row--head" role="row">
          <span>Help provided</span>
          <span>Number of runs</span>
          <span>Completed</span>
          <span>Average money left on the table</span>
          <span>Supplier replaced</span>
          <span>Times the request moved the wrong way</span>
        </div>
        {mechanism.conditions.map((condition) => (
          <div
            className={`mechanism-row mechanism-row--${condition.condition_id}`}
            role="row"
            key={condition.condition_id}
          >
            <span className="mechanism-condition" data-label="Help provided">
              <strong>{mechanismConditionLabel(condition.condition_id)}</strong>
              <small>{mechanismConditionDescription(condition.condition_id)}</small>
            </span>
            <span data-label="Number of runs">{mechanismEvidenceLabel(condition.evidence_tier)}</span>
            <span data-label="Completed">
              {condition.valid_run_count}/{condition.run_count}
            </span>
            <span data-label="Average money left on the table">
              {formatRoundedResearchMoney(condition.mean_attainable_regret_usd)}
            </span>
            <span data-label="Supplier replaced">{Math.round(condition.replacement_rate * 100)}%</span>
            <span data-label="Times the request moved the wrong way">{condition.request_monotonicity_violations}</span>
          </div>
        ))}
      </div>

      <div className="mechanism-takeaway">
        <strong>{reduction}% less money left on the table</strong>
        <p>
          When the AI received the highest safe request, the project never replaced
          it and its requests changed in the right direction as replacement became more
          expensive. This suggests that the AI struggled to choose the right facts
          and calculate the limit. It still left{" "}
          {formatRoundedResearchMoney(
            mechanism.trusted_threshold_effect.residual_high_level_anchor_usd
          )} on the table in the highest-price case.
        </p>
      </div>
      <p className="mechanism-caveat">
        The formula version has only one run at each replacement cost. Giving the
        the AI the correct limit shows whether it can use that number. It does not show
        that the AI can calculate the limit on its own.
      </p>
    </section>
  );
}

function mechanismEvidenceLabel(value: string) {
  const labels: Record<string, string> = {
    five_per_cell_confirmation: "5 runs per replacement cost",
    one_per_cell_modal_diagnostic: "1 run per replacement cost",
    three_per_cell_confirmation: "3 runs per replacement cost",
  };
  return labels[value] ?? value;
}

function mechanismConditionLabel(value: string) {
  const labels: Record<string, string> = {
    unassisted: "No extra help",
    threshold_worksheet: "Formula provided",
    trusted_threshold: "Highest safe request provided",
  };
  return labels[value] ?? value;
}

function mechanismConditionDescription(value: string) {
  const descriptions: Record<string, string> = {
    unassisted: "The supplier sees the market facts and decides on its own.",
    threshold_worksheet: "The supplier gets the formula and must show its work.",
    trusted_threshold: "The supplier gets the correct number, but no recommended action.",
  };
  return descriptions[value] ?? value;
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
  const successfulRuns = validRuns.filter((run) => run.project_success);
  const allFirmSuccesses = successfulRuns.filter((run) => run.coalition_success).length;
  return (
    <section className="overview-section">
      <div className="section-title">
        <Users size={20} />
        <h2>When the project succeeds but companies still lose</h2>
      </div>
      <div className="metric-grid research-metric-grid">
        <Metric
          icon={<CheckCircle2 size={20} />}
          label="Project successes"
          value={`${successfulRuns.length}/${validRuns.length}`}
        />
        <Metric
          icon={<Users size={20} />}
          label="Successful projects where every company met its goal"
          value={`${allFirmSuccesses}/${successfulRuns.length}`}
        />
      </div>
      <p>
        A project can finish under its public cost and schedule limits while one or
        more companies miss their own financial goal. In these runs, the AI made
        every decision for all six companies. {successfulRuns.length} of{" "}
        {validRuns.length} completed runs finished the project, but only{" "}
        {allFirmSuccesses} of those successful projects also met every company's goal.
      </p>
      <p>
        These were early tests and were not designed to support a strong comparison.
        Some test settings changed between groups of runs, so the rows are best read
        as examples of what can happen. In every row, <strong>{modelLabel}</strong>{" "}
        made decisions for all six companies. Final costs ranged from{" "}
        {formatMoney(population.cost_min ?? 0)} to {formatMoney(population.cost_max ?? 0)}.
        "Companies meeting goals" shows how many of the six companies also reached their
        own profit goal. A number below 6 reveals a loss that the project-wide result
        does not show.
      </p>
      <div className="population-table" role="table" aria-label="Examples where AI played all six companies">
        <div className="population-row population-row--head" role="row">
          <span>Run</span>
          <span>Outcome</span>
          <span>Final cost</span>
          <span>Finished</span>
          <span>Companies meeting goals</span>
        </div>
        {validRuns.map((run, displayIndex) => (
          <div
            className={`population-row${run.project_success ? "" : " population-row--failed"}`}
            role="row"
            key={`${run.batch}-${run.replicate_index}`}
          >
            <span>
              Run {displayIndex + 1}
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
    </section>
  );
}

function populationOutcomeLabel(run: PopulationRun) {
  if (run.project_success) {
    return run.coalition_success
      ? "Success — every company met its goal"
      : "Success — some companies missed their goals";
  }
  const labels: Record<string, string> = {
    BUDGET_INFEASIBLE: "Failed — over budget",
    SCHEDULE_INFEASIBLE: "Failed — too late",
    CRITICAL_PATH_DEADLOCK: "Failed — required work could not continue",
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
      label: "Written example: everyone works together",
      cost: evaluation.idealOutcome.final_project_cost,
      week: evaluation.idealOutcome.completion_tick,
      note: "Project succeeds despite the steel problem",
    },
    evaluation.modelOutcome
      ? {
          label: "Example where Claude Haiku played all companies",
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
    phased_coalition_success: "Project succeeds because the companies deliver the steel in stages",
    coordination_delay_failure: "Project fails after delays build up",
    schedule_infeasible: "Project fails because the schedule becomes impossible",
  };
  return labels[pathLabel ?? ""] ?? "AI-produced project outcome";
}

function outcomeMixValue(evaluation: GameEvaluation) {
  if (evaluation.projectSuccess && evaluation.playerPrivateSuccess) {
    return "Both met their goals";
  }
  if (evaluation.projectSuccess) {
    return "Project only";
  }
  if (evaluation.playerPrivateSuccess) {
    return "Your company only";
  }
  return "Neither met its goal";
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
          <a href="/research">Research</a>
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
      "You need the steel work to keep moving without putting too much of your company's cash at risk or overpaying for backup steel.",
    steel_supplier:
      "You need cash to fix, finish, and ship the steel — without giving away too much profit.",
    labor_subcontractor:
      "You control the workers and crane. Keeping them available helps this project, but you could earn money by sending them to other jobs instead.",
    lender:
      "You release loan money only when there is proof that the steel is ready, the owner has committed its own money, and the loan is protected.",
    inspector:
      "You decide what steel is safe and legal to use.",
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
    return "enough money";
  }
  if (state.cash_secured_usd > 0) {
    return "some money";
  }
  return "no money yet";
}

function releasePathLabel(state: ProjectGameState) {
  if (state.backup_status === "active") {
    return "using backup steel";
  }
  if (state.lot_a_released && state.lot_b_released) {
    return "both batches approved";
  }
  if (state.lot_a_released || state.lot_b_released || state.release_value_usd > 0) {
    return "some steel approved";
  }
  return "waiting for approval";
}

function pressureLabel(state: ProjectGameState) {
  const score = pressureScore(state);
  if (score >= 80) {
    return "high";
  }
  if (score >= 45) {
    return "medium";
  }
  return "low";
}

function hasStoryFlag(state: ProjectGameState, flag: string) {
  return state.story_flags.includes(flag);
}

function partnerDecisionReads(move: {
  nodeId: string;
  actorId: AgentId;
  choiceId: ChoiceId;
}) {
  const choice = gameData.decision_nodes[move.nodeId]?.choices.find(
    (candidate) => candidate.choice_id === move.choiceId
  );
  if (choice?.reads) {
    return choice.reads;
  }
  const actor = roleLabel(move.actorId).toLowerCase();
  return {
    balanced: {
      charitable:
        `The ${actor} believes the plan can work and is keeping the project moving even though some risk remains.`,
      uncharitable:
        `The ${actor} may be moving ahead before every open question is settled because progress helps its own position.`,
    },
    conservative: {
      charitable:
        `The ${actor} is asking for more proof because payment, steel approval, or timing is still uncertain.`,
      uncharitable:
        `The ${actor} may be slowing the job and making other companies carry more cost, delay, or paperwork.`,
    },
    self_protective: {
      charitable:
        `The ${actor} is protecting itself from a plan that may not work yet.`,
      uncharitable:
        `The ${actor} may care more about avoiding its own loss than keeping the shared project on time.`,
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

function formatRoundedResearchMoney(value: number) {
  const rounded = Math.round(value / 1_000) * 1_000;
  if (Math.abs(rounded) >= 1_000_000) {
    return formatMoney(rounded);
  }
  const sign = rounded < 0 ? "-" : "";
  return `${sign}$${Math.abs(rounded / 1_000).toLocaleString()}K`;
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
