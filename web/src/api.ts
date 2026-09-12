export type ScoreFlashMatch = {
  id: string;
  date: string;
  home_team: string;
  away_team: string;
  score: number[] | null;
  competition: string | null;
};

export type TeamQueryResult = {
  kind: "team_statistic";
  answer: string;
  team: string;
  metric: string;
  games: number;
  venue: "any" | "home" | "away";
  competition: string | null;
  average: number;
  unit: string;
  matches: ScoreFlashMatch[];
  cached: boolean;
  insight: string;
  confidence: "inicial" | "média" | "alta";
};

export type HeadToHeadQueryResult = {
  kind: "head_to_head";
  answer: string;
  team: string;
  opponent: string;
  metric: "gols";
  games: number;
  venue: "any" | "home" | "away";
  competition: string | null;
  average: number;
  team_average: number;
  opponent_average: number;
  matches: ScoreFlashMatch[];
  cached: boolean;
  insight: string;
  confidence: "inicial" | "média" | "alta";
};

export type PlayerAppearance = {
  id: string;
  date: string;
  home_team: string;
  away_team: string;
  competition: string | null;
  minutes: number | null;
  rating: number | null;
};

export type VerifiedPlayerMatch = PlayerAppearance & {
  shots_total: number | null;
  shots_on_target: number | null;
  fouls_committed: number | null;
  fouls_drawn: number | null;
  yellow_cards: number | null;
  red_cards: number | null;
};

export type PlayerOpportunityResult = {
  kind: "player_opportunity";
  answer: string;
  player: string;
  team: string;
  market: string;
  status: "ready" | "needs_provider_key" | "insufficient_coverage" | "provider_unavailable";
  recommendation: "favorável" | "neutro" | "evitar" | "sem dados";
  threshold: number;
  average_metric: number | null;
  hit_rate: number | null;
  appearances_considered: number;
  average_minutes: number | null;
  average_rating: number | null;
  next_match: Omit<ScoreFlashMatch, "score"> | null;
  appearances: PlayerAppearance[];
  individual_matches: VerifiedPlayerMatch[];
  insight: string;
};

export type QueryResult = TeamQueryResult | HeadToHeadQueryResult | PlayerOpportunityResult;

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

export async function submitQuestion(question: string): Promise<QueryResult> {
  const response = await fetch(`${apiBaseUrl}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : "Não foi possível concluir a consulta agora.";
    throw new Error(detail);
  }

  return payload as QueryResult;
}

export async function configureApiFootballKey(apiKey: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/settings/api-football`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : "Não foi possível salvar a configuração agora.";
    throw new Error(detail);
  }
}
