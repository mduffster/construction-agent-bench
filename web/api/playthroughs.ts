// Anonymized playthrough counters for the "you vs the crowd" panel.
// Storage is Upstash Redis via its REST API (Vercel KV-compatible env vars).
// When no storage is configured the endpoint reports unavailable and the
// client hides the panel, so local dev and previews work without setup.

const PLAYABLE_ROLES = new Set([
  "owner",
  "gc",
  "steel_supplier",
  "labor_subcontractor",
]);
const CHOICE_IDS = new Set(["balanced", "self_protective", "conservative"]);
const NODE_ID_PATTERN = /^S01_[A-Z0-9_]{1,60}$/;
const KEY_PREFIX = "s01v2";
const MAX_DECISIONS = 6;

interface PlaythroughBody {
  role: string;
  decisions: Record<string, string>;
  projectSuccess: boolean;
  privateSuccess: boolean;
  costUsd: number;
  completionWeek: number;
}

export function validatePlaythrough(body: unknown): PlaythroughBody | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const record = body as Record<string, unknown>;
  const role = record.role;
  if (typeof role !== "string" || !PLAYABLE_ROLES.has(role)) {
    return null;
  }
  const decisions = record.decisions;
  if (typeof decisions !== "object" || decisions === null) {
    return null;
  }
  const entries = Object.entries(decisions as Record<string, unknown>);
  if (entries.length === 0 || entries.length > MAX_DECISIONS) {
    return null;
  }
  const validated: Record<string, string> = {};
  for (const [nodeId, choiceId] of entries) {
    if (!NODE_ID_PATTERN.test(nodeId)) {
      return null;
    }
    if (typeof choiceId !== "string" || !CHOICE_IDS.has(choiceId)) {
      return null;
    }
    validated[nodeId] = choiceId;
  }
  const projectSuccess = record.projectSuccess;
  const privateSuccess = record.privateSuccess;
  if (typeof projectSuccess !== "boolean" || typeof privateSuccess !== "boolean") {
    return null;
  }
  const costUsd = record.costUsd;
  const completionWeek = record.completionWeek;
  if (
    typeof costUsd !== "number" ||
    !Number.isFinite(costUsd) ||
    costUsd < 0 ||
    costUsd > 1_000_000_000
  ) {
    return null;
  }
  if (
    typeof completionWeek !== "number" ||
    !Number.isFinite(completionWeek) ||
    completionWeek < 0 ||
    completionWeek > 200
  ) {
    return null;
  }
  return {
    role,
    decisions: validated,
    projectSuccess,
    privateSuccess,
    costUsd: Math.round(costUsd),
    completionWeek: Math.round(completionWeek),
  };
}

export function validateNodeIds(raw: string | undefined): string[] | null {
  if (!raw) {
    return null;
  }
  const nodeIds = raw.split(",").filter(Boolean);
  if (nodeIds.length === 0 || nodeIds.length > MAX_DECISIONS) {
    return null;
  }
  if (!nodeIds.every((nodeId) => NODE_ID_PATTERN.test(nodeId))) {
    return null;
  }
  return nodeIds;
}

function redisConfig(): { url: string; token: string } | null {
  const url = process.env.KV_REST_API_URL ?? process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN ?? process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) {
    return null;
  }
  return { url, token };
}

async function redisPipeline(
  config: { url: string; token: string },
  commands: Array<Array<string | number>>
): Promise<Array<{ result: unknown }>> {
  const response = await fetch(`${config.url}/pipeline`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(commands),
  });
  if (!response.ok) {
    throw new Error(`redis pipeline failed with status ${response.status}`);
  }
  return (await response.json()) as Array<{ result: unknown }>;
}

function hashToCounts(result: unknown): Record<string, number> {
  // Upstash HGETALL returns a flat [field, value, field, value] array.
  const counts: Record<string, number> = {};
  if (!Array.isArray(result)) {
    return counts;
  }
  for (let index = 0; index + 1 < result.length; index += 2) {
    counts[String(result[index])] = Number(result[index + 1]) || 0;
  }
  return counts;
}

export default async function handler(req: any, res: any): Promise<void> {
  const config = redisConfig();

  if (req.method === "POST") {
    if (!config) {
      res.status(204).end();
      return;
    }
    const record = validatePlaythrough(req.body);
    if (!record) {
      res.status(400).json({ error: "invalid playthrough payload" });
      return;
    }
    const commands: Array<Array<string | number>> = [
      ["INCR", `${KEY_PREFIX}:plays`],
      ["INCR", `${KEY_PREFIX}:plays:${record.role}`],
      ["INCRBY", `${KEY_PREFIX}:sum:cost:${record.role}`, record.costUsd],
      ["INCRBY", `${KEY_PREFIX}:sum:week:${record.role}`, record.completionWeek],
    ];
    if (record.projectSuccess) {
      commands.push(["INCR", `${KEY_PREFIX}:success:project:${record.role}`]);
    }
    if (record.privateSuccess) {
      commands.push(["INCR", `${KEY_PREFIX}:success:private:${record.role}`]);
    }
    for (const [nodeId, choiceId] of Object.entries(record.decisions)) {
      commands.push(["HINCRBY", `${KEY_PREFIX}:choices:${nodeId}`, choiceId, 1]);
    }
    await redisPipeline(config, commands);
    res.status(201).json({ recorded: true });
    return;
  }

  if (req.method === "GET") {
    if (!config) {
      res.status(200).json({ available: false });
      return;
    }
    const role = typeof req.query.role === "string" ? req.query.role : "";
    if (!PLAYABLE_ROLES.has(role)) {
      res.status(400).json({ error: "unknown role" });
      return;
    }
    const nodeIds = validateNodeIds(
      typeof req.query.nodes === "string" ? req.query.nodes : undefined
    );
    if (!nodeIds) {
      res.status(400).json({ error: "invalid node list" });
      return;
    }
    const commands: Array<Array<string | number>> = [
      ["GET", `${KEY_PREFIX}:plays`],
      ["GET", `${KEY_PREFIX}:plays:${role}`],
      ["GET", `${KEY_PREFIX}:success:project:${role}`],
      ["GET", `${KEY_PREFIX}:success:private:${role}`],
      ["GET", `${KEY_PREFIX}:sum:cost:${role}`],
      ["GET", `${KEY_PREFIX}:sum:week:${role}`],
      ...nodeIds.map((nodeId) => ["HGETALL", `${KEY_PREFIX}:choices:${nodeId}`]),
    ];
    const results = await redisPipeline(config, commands);
    const asNumber = (index: number) => Number(results[index]?.result) || 0;
    const rolePlays = asNumber(1);
    const nodes: Record<string, Record<string, number>> = {};
    nodeIds.forEach((nodeId, index) => {
      nodes[nodeId] = hashToCounts(results[6 + index]?.result);
    });
    res.status(200).json({
      available: true,
      totalPlays: asNumber(0),
      rolePlays,
      projectSuccessCount: asNumber(2),
      privateSuccessCount: asNumber(3),
      averageCostUsd: rolePlays ? Math.round(asNumber(4) / rolePlays) : null,
      averageCompletionWeek: rolePlays ? Math.round(asNumber(5) / rolePlays) : null,
      nodes,
    });
    return;
  }

  res.status(405).json({ error: "method not allowed" });
}
