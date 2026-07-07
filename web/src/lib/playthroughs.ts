import type { AgentId, ChoiceId } from "./types";

export interface PlaythroughSubmission {
  role: AgentId;
  decisions: Record<string, ChoiceId>;
  projectSuccess: boolean;
  privateSuccess: boolean;
  costUsd: number;
  completionWeek: number;
}

export interface CrowdStats {
  totalPlays: number;
  rolePlays: number;
  projectSuccessCount: number;
  privateSuccessCount: number;
  averageCostUsd: number | null;
  averageCompletionWeek: number | null;
  nodes: Record<string, Partial<Record<ChoiceId, number>>>;
}

const ENDPOINT = "/api/playthroughs";
const SUBMITTED_MARKER_PREFIX = "constructsim.playthrough.";

function submissionKey(submission: PlaythroughSubmission): string {
  const path = Object.entries(submission.decisions)
    .map(([nodeId, choiceId]) => `${nodeId}=${choiceId}`)
    .sort()
    .join("&");
  return `${SUBMITTED_MARKER_PREFIX}${submission.role}:${path}`;
}

// Fire-and-forget: crowd stats are a bonus layer, so storage being down or
// unconfigured must never affect the game itself.
export async function submitPlaythrough(
  submission: PlaythroughSubmission
): Promise<void> {
  const marker = submissionKey(submission);
  try {
    if (window.sessionStorage.getItem(marker)) {
      return;
    }
    window.sessionStorage.setItem(marker, "1");
  } catch {
    // Storage unavailable (private browsing); accept possible double counts.
  }
  try {
    await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(submission),
      signal: AbortSignal.timeout(4000),
    });
  } catch {
    // Ignore: dev servers and previews have no backend.
  }
}

export async function fetchCrowdStats(
  role: AgentId,
  nodeIds: string[]
): Promise<CrowdStats | null> {
  try {
    const params = new URLSearchParams({ role, nodes: nodeIds.join(",") });
    const response = await fetch(`${ENDPOINT}?${params.toString()}`, {
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as CrowdStats & {
      available: boolean;
    };
    if (!payload.available) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}
