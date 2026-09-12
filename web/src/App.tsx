import { FormEvent, useEffect, useRef, useState } from "react";

import {
  HeadToHeadQueryResult,
  PlayerOpportunityResult,
  QueryResult,
  ScoreFlashMatch,
  TeamQueryResult,
  configureApiFootballKey,
  submitQuestion,
} from "./api";

const examples = [
  "Qual a média de gols no confronto Grêmio e Vasco sendo o Grêmio mandante pelo Campeonato Brasileiro?",
  "Qual a média de finalizações do Flamengo nos últimos 5 jogos?",
  "O São Paulo chuta mais fora ou em casa?",
  "O Léo Ortiz é uma boa ideia para finalizar amanhã pelo Flamengo?",
];

const localKeySetupEnabled = import.meta.env.VITE_ENABLE_LOCAL_KEY_SETUP !== "false";

function FlashMark() {
  return (
    <svg aria-hidden="true" className="h-6 w-6" viewBox="0 0 28 28" fill="none">
      <path d="M14 2.5a11.5 11.5 0 1 0 11.5 11.5" stroke="currentColor" strokeWidth="3.1" strokeLinecap="round" />
      <path d="M14 7v7l5.2 3" stroke="currentColor" strokeWidth="3.1" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="14" cy="14" r="1.8" fill="currentColor" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 20 20" fill="none">
      <path d="M3 10h12M11 4.5 16.5 10 11 15.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PulseIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 20 20" fill="none">
      <path d="M2 10h3l1.7-4.2L10 15l2.1-5H18" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 20 20" fill="none">
      <path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" })
    .format(new Date(`${value}T12:00:00`))
    .replace(".", "");
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(value);
}

function venueLabel(venue: TeamQueryResult["venue"]) {
  if (venue === "home") return "em casa";
  if (venue === "away") return "fora de casa";
  return "todos os mandos";
}

function matchScore(match: ScoreFlashMatch) {
  return match.score ? `${match.score[0]} — ${match.score[1]}` : "—";
}

function verifiedMetric(match: PlayerOpportunityResult["individual_matches"][number], market: string) {
  if (market === "chutes no alvo") return match.shots_on_target;
  if (market === "faltas cometidas") return match.fouls_committed;
  if (market === "cartões amarelos") return match.yellow_cards;
  return match.shots_total;
}

function opportunityLabel(result: PlayerOpportunityResult) {
  if (result.status === "ready") return result.recommendation;
  if (result.status === "needs_provider_key") return "dados individuais pendentes";
  if (result.status === "provider_unavailable") return "fonte indisponível";
  return "amostra insuficiente";
}

function confidenceWidth(confidence: TeamQueryResult["confidence"]) {
  if (confidence === "alta") return "w-full";
  if (confidence === "média") return "w-2/3";
  return "w-1/3";
}

function ResultsSkeleton() {
  return (
    <div className="space-y-8" aria-label="Buscando estatísticas">
      <div className="flex items-center justify-between">
        <div className="h-3 w-32 animate-pulse bg-white/10" />
        <div className="h-3 w-20 animate-pulse bg-white/10" />
      </div>
      <div className="space-y-4 border-b border-white/10 pb-8">
        <div className="h-16 w-36 animate-pulse bg-white/10" />
        <div className="h-6 w-2/3 animate-pulse bg-white/10" />
        <div className="h-4 w-full animate-pulse bg-white/8" />
        <div className="h-4 w-4/5 animate-pulse bg-white/8" />
      </div>
      <div className="grid grid-cols-2 gap-px bg-white/10">
        <div className="h-20 animate-pulse bg-[#202728]" />
        <div className="h-20 animate-pulse bg-[#202728]" />
      </div>
      <div className="space-y-3">
        <div className="h-3 w-28 animate-pulse bg-white/10" />
        <div className="h-12 animate-pulse border-b border-white/8" />
        <div className="h-12 animate-pulse border-b border-white/8" />
      </div>
    </div>
  );
}

function EmptyResult() {
  return (
    <div className="flex min-h-[390px] flex-col justify-between sm:min-h-[520px]">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.17em] text-[#e9877e] uppercase">
          <span className="h-2 w-2 rounded-full bg-[#e4524b] motion-safe:animate-pulse" />
          Pronto para analisar
        </div>
        <h2 className="mt-7 max-w-xl font-display text-[clamp(2.15rem,11vw,4rem)] leading-[0.97] tracking-[-0.055em] text-[#f6f1e9] sm:mt-8">
          Uma pergunta.<br />Uma leitura direta.
        </h2>
        <p className="mt-6 max-w-lg text-base leading-7 text-[#abb4ae]">
          Sem garimpar tabela, sem transformar futebol em planilha. Você pergunta do seu jeito; o ScoreFlash mostra a conta e os jogos que sustentam a resposta.
        </p>
      </div>

      <div className="grid gap-0 border-y border-white/10 sm:grid-cols-[0.86fr_1.14fr]">
        <div className="border-b border-white/10 py-5 pr-6 sm:border-r sm:border-b-0">
          <p className="text-[10px] font-semibold tracking-[0.17em] text-[#7f8984] uppercase">Você pode perguntar</p>
          <p className="mt-2 text-sm leading-6 text-[#e0e3dc]">Times, mandos, médias, escanteios, posse, chutes e tendências recentes.</p>
        </div>
        <div className="py-5 sm:pl-6">
          <p className="text-[10px] font-semibold tracking-[0.17em] text-[#7f8984] uppercase">Como a resposta vem</p>
          <p className="mt-2 text-sm leading-6 text-[#e0e3dc]">Métrica principal, recorte aplicado, confiança e a lista das partidas usadas.</p>
        </div>
      </div>
    </div>
  );
}

function PlayerOpportunityPanel({ result }: { result: PlayerOpportunityResult }) {
  return (
    <div className="space-y-6 sm:space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-5">
        <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.17em] text-[#e9877e] uppercase"><PulseIcon /> Leitura de jogador</div>
        <span className="border border-[#d96a63]/40 px-2.5 py-1 text-[10px] font-semibold tracking-[0.12em] text-[#f1ada7] uppercase">{opportunityLabel(result)}</span>
      </div>

      <div>
        <p className="font-display text-[clamp(2.25rem,11vw,4.4rem)] leading-[0.94] tracking-[-0.055em] text-[#f6f1e9]">{result.player}</p>
        <p className="mt-3 text-sm text-[#aab2ad]">{result.team} <span className="px-1 text-[#67706c]">/</span> {result.market}</p>
        <p className="mt-5 max-w-2xl text-lg leading-7 text-[#e6e8e2] sm:mt-6 sm:text-xl sm:leading-8">{result.answer}</p>
      </div>

      <section className="grid grid-cols-3 border-y border-white/10" aria-label="Indicadores da oportunidade">
        <div className="border-r border-white/10 py-4 pr-3 sm:py-5 sm:pr-5">
          <p className="text-[10px] font-semibold tracking-[0.14em] text-[#7f8984] uppercase">Média individual</p>
          <p className="mt-2 font-mono text-2xl tracking-[-0.06em] text-[#f4f0e9] sm:text-3xl">{result.average_metric !== null ? formatNumber(result.average_metric) : "—"}</p>
        </div>
        <div className="border-r border-white/10 px-3 py-4 sm:px-5 sm:py-5">
          <p className="text-[10px] font-semibold tracking-[0.14em] text-[#7f8984] uppercase">Linha {result.threshold}+</p>
          <p className="mt-2 font-mono text-2xl tracking-[-0.06em] text-[#f4f0e9] sm:text-3xl">{result.hit_rate !== null ? `${formatNumber(result.hit_rate)}%` : "—"}</p>
        </div>
        <div className="py-4 pl-3 sm:py-5 sm:pl-5">
          <p className="text-[10px] font-semibold tracking-[0.14em] text-[#7f8984] uppercase">Minutos médios</p>
          <p className="mt-2 font-mono text-2xl tracking-[-0.06em] text-[#f4f0e9] sm:text-3xl">{result.average_minutes !== null ? formatNumber(result.average_minutes) : "—"}</p>
        </div>
      </section>

      <section className="border-l-2 border-[#d96a63] pl-4" aria-label="Critério da análise">
        <h3 className="text-xs font-semibold tracking-[0.15em] text-[#d9ddda] uppercase">Critério da análise</h3>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#b8bfbb]">{result.insight}</p>
      </section>

      {result.next_match && (
        <section className="border-t border-white/10 pt-5" aria-label="Próximo jogo listado">
          <p className="text-[10px] font-semibold tracking-[0.15em] text-[#87908b] uppercase">Próximo jogo listado</p>
          <p className="mt-3 text-base text-[#edf0ea]">{result.next_match.home_team} <span className="text-[#767e7a]">x</span> {result.next_match.away_team}</p>
          <p className="mt-1 text-xs text-[#858d89]">{formatDate(result.next_match.date)} <span className="px-1">/</span> {result.next_match.competition}</p>
        </section>
      )}

      {result.individual_matches.length > 0 && (
        <section className="border-t border-white/10 pt-5" aria-label="Evidências individuais">
          <div className="mb-3 flex items-center justify-between gap-4">
            <h3 className="text-xs font-semibold tracking-[0.15em] text-[#d9ddda] uppercase">Jogos verificados</h3>
            <span className="text-xs text-[#858d89]">{result.individual_matches.length} usados</span>
          </div>
          <div className="divide-y divide-white/8">
            {result.individual_matches.map((match) => (
              <div key={match.id} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 py-3.5 text-sm">
                <time className="font-mono text-[11px] text-[#8e9692]" dateTime={match.date}>{formatDate(match.date)}</time>
                <div className="min-w-0">
                  <p className="truncate text-[#e5e7e2]">{match.home_team} <span className="text-[#767e7a]">x</span> {match.away_team}</p>
                  <p className="mt-0.5 truncate text-[11px] text-[#777f7b]">{match.minutes ?? "—"} min <span className="px-1">/</span> {match.competition}</p>
                </div>
                <span className="font-mono text-sm font-semibold text-[#f0c4be]">{verifiedMetric(match, result.market) ?? "—"}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function TeamResultPanel({ result }: { result: TeamQueryResult }) {
  return (
    <div className="space-y-6 sm:space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-5">
        <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.17em] text-[#e9877e] uppercase"><PulseIcon /> Análise concluída</div>
        {result.cached && <span className="border border-white/12 px-2.5 py-1 text-[10px] font-semibold tracking-[0.12em] text-[#abb3af] uppercase">resultado recente</span>}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,0.78fr)_minmax(235px,0.42fr)] lg:items-end">
        <div>
          <p className="text-sm font-medium text-[#adb5b0]">{result.team}</p>
          <div className="mt-2 flex flex-wrap items-end gap-x-4 gap-y-2">
            <p className="font-display text-[clamp(3.9rem,20vw,7rem)] leading-[0.78] tracking-[-0.09em] text-[#f6f1e9] sm:text-[clamp(4rem,9vw,7rem)]">{formatNumber(result.average)}</p>
            <p className="mb-1 max-w-[12ch] text-sm leading-5 text-[#aeb6b1]">{result.metric} por partida</p>
          </div>
        </div>
        <div className="border-l border-white/10 pl-4 lg:pb-1">
          <p className="text-[10px] font-semibold tracking-[0.15em] text-[#7f8984] uppercase">Amostra usada</p>
          <p className="mt-2 font-mono text-2xl tracking-[-0.06em] text-[#ecefe8]">{result.games} {result.games === 1 ? "jogo" : "jogos"}</p>
          <p className="mt-1 text-xs leading-5 text-[#959d98]">{venueLabel(result.venue)}{result.competition ? ` / ${result.competition}` : ""}</p>
        </div>
      </div>

      <p className="max-w-3xl text-lg leading-7 text-[#e5e8e1] sm:text-xl sm:leading-8">{result.answer}</p>

      <section className="grid gap-5 border-y border-white/10 py-5 sm:grid-cols-[1fr_auto] sm:items-start" aria-label="Leitura do analista">
        <div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-xs font-semibold tracking-[0.15em] text-[#d9ddda] uppercase">Leitura do analista</h3>
            <span className="text-[10px] font-semibold tracking-[0.12em] text-[#e9877e] uppercase">Confiança {result.confidence}</span>
          </div>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-[#b8bfbb]">{result.insight || "A análise detalhada ficará disponível na próxima consulta."}</p>
        </div>
        <div className="w-full sm:w-24 sm:pt-1">
          <div className="h-px w-full bg-white/10"><div className={`h-px bg-[#d96a63] ${confidenceWidth(result.confidence)}`} /></div>
        </div>
      </section>

      <section aria-label="Jogos usados">
        <div className="mb-3 flex items-center justify-between gap-4">
          <h3 className="text-xs font-semibold tracking-[0.15em] text-[#d9ddda] uppercase">Jogos considerados</h3>
          <span className="text-xs text-[#878e8b]">{result.matches.length} encontrados</span>
        </div>
        <div className="divide-y divide-white/8">
          {result.matches.map((match) => (
            <div key={match.id} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 py-3.5 text-sm">
              <time className="font-mono text-[11px] text-[#8e9692]" dateTime={match.date}>{formatDate(match.date)}</time>
              <div className="min-w-0">
                <p className="truncate text-[#e5e7e2]">{match.home_team} <span className="text-[#767e7a]">x</span> {match.away_team}</p>
                <p className="mt-0.5 truncate text-[11px] text-[#777f7b]">{match.competition}</p>
              </div>
              <span className="font-mono text-xs font-semibold text-[#d7dbd6]">{matchScore(match)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function HeadToHeadResultPanel({ result }: { result: HeadToHeadQueryResult }) {
  return (
    <div className="space-y-6 sm:space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-5">
        <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.17em] text-[#e9877e] uppercase"><PulseIcon /> Confronto direto</div>
        {result.cached && <span className="border border-white/12 px-2.5 py-1 text-[10px] font-semibold tracking-[0.12em] text-[#abb3af] uppercase">resultado recente</span>}
      </div>

      <div>
        <p className="font-display text-[clamp(2.6rem,11vw,5.2rem)] leading-[0.92] tracking-[-0.065em] text-[#f6f1e9]">
          {result.team} <span className="text-[#d96a63]">x</span> {result.opponent}
        </p>
        <p className="mt-3 text-sm text-[#aab2ad]">
          {venueLabel(result.venue)}{result.competition ? ` / ${result.competition}` : ""}
        </p>
      </div>

      <section className="grid grid-cols-3 border-y border-white/10" aria-label="Médias de gols do confronto">
        <div className="border-r border-white/10 py-4 pr-3 sm:py-5 sm:pr-5">
          <p className="text-[10px] font-semibold tracking-[0.14em] text-[#7f8984] uppercase">{result.team}</p>
          <p className="mt-2 font-mono text-2xl tracking-[-0.06em] text-[#f4f0e9] sm:text-3xl">{formatNumber(result.team_average)}</p>
          <p className="mt-1 text-[11px] text-[#858d89]">gols por jogo</p>
        </div>
        <div className="border-r border-white/10 px-3 py-4 sm:px-5 sm:py-5">
          <p className="text-[10px] font-semibold tracking-[0.14em] text-[#7f8984] uppercase">{result.opponent}</p>
          <p className="mt-2 font-mono text-2xl tracking-[-0.06em] text-[#f4f0e9] sm:text-3xl">{formatNumber(result.opponent_average)}</p>
          <p className="mt-1 text-[11px] text-[#858d89]">gols por jogo</p>
        </div>
        <div className="py-4 pl-3 sm:py-5 sm:pl-5">
          <p className="text-[10px] font-semibold tracking-[0.14em] text-[#e9877e] uppercase">Total</p>
          <p className="mt-2 font-mono text-2xl tracking-[-0.06em] text-[#f1b7b2] sm:text-3xl">{formatNumber(result.average)}</p>
          <p className="mt-1 text-[11px] text-[#858d89]">gols por jogo</p>
        </div>
      </section>

      <p className="max-w-3xl text-lg leading-7 text-[#e5e8e1] sm:text-xl sm:leading-8">{result.answer}</p>

      <section className="border-l-2 border-[#d96a63] pl-4" aria-label="Critério do confronto">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-xs font-semibold tracking-[0.15em] text-[#d9ddda] uppercase">Leitura do confronto</h3>
          <span className="text-[10px] font-semibold tracking-[0.12em] text-[#e9877e] uppercase">Confiança {result.confidence}</span>
        </div>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#b8bfbb]">{result.insight}</p>
      </section>

      <section aria-label="Confrontos usados">
        <div className="mb-3 flex items-center justify-between gap-4">
          <h3 className="text-xs font-semibold tracking-[0.15em] text-[#d9ddda] uppercase">Confrontos usados</h3>
          <span className="text-xs text-[#858d89]">{result.games} {result.games === 1 ? "jogo" : "jogos"}</span>
        </div>
        <div className="divide-y divide-white/8 border-y border-white/10">
          {result.matches.map((match) => (
            <div key={match.id} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 py-3.5 text-sm">
              <time className="font-mono text-[11px] text-[#8e9692]" dateTime={match.date}>{formatDate(match.date)}</time>
              <div className="min-w-0">
                <p className="truncate text-[#e5e7e2]">{match.home_team} <span className="text-[#767e7a]">x</span> {match.away_team}</p>
                <p className="mt-0.5 truncate text-[11px] text-[#777f7b]">{match.competition ?? "Competição não informada"}</p>
              </div>
              <span className="font-mono text-sm font-semibold text-[#f0c4be]">{matchScore(match)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function ResultsPanel({ result }: { result: QueryResult | null }) {
  if (!result) return <EmptyResult />;
  if (result.kind === "player_opportunity") return <PlayerOpportunityPanel result={result} />;
  if (result.kind === "head_to_head") return <HeadToHeadResultPanel result={result} />;
  return <TeamResultPanel result={result} />;
}

function LocalKeySetup({ onClose }: { onClose: () => void }) {
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanKey = apiKey.trim();
    if (cleanKey.length < 12) {
      setError("Cole a chave inteira que aparece no painel da API-Football.");
      return;
    }
    setError("");
    setSuccess("");
    setIsSaving(true);
    try {
      await configureApiFootballKey(cleanKey);
      setApiKey("");
      setSuccess("Dados individuais ativados neste computador.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível salvar a chave.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-20 grid overflow-y-auto bg-[#101416]/88 px-4 py-4 sm:place-items-center sm:px-5 sm:py-8" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="api-football-setup-title" className="my-auto w-full max-w-lg border border-white/12 bg-[#202728] p-5 shadow-[0_24px_60px_-28px_rgba(0,0,0,0.65)] sm:p-8">
        <div className="flex items-start justify-between gap-5">
          <div>
            <p className="text-xs font-semibold tracking-[0.16em] text-[#e9877e] uppercase">Somente neste computador</p>
            <h2 id="api-football-setup-title" className="mt-3 font-display text-3xl tracking-[-0.05em] text-[#f5f0e8]">Ativar dados individuais</h2>
          </div>
          <button type="button" onClick={onClose} className="grid h-11 w-11 place-items-center border border-white/12 text-[#d9ddda] transition-colors hover:border-[#d96a63] active:translate-y-px" aria-label="Fechar configuração"><CloseIcon /></button>
        </div>

        <ol className="mt-7 space-y-3 border-y border-white/10 py-5 text-sm leading-6 text-[#bac1bd]">
          <li><span className="mr-2 font-mono text-[#e9877e]">01</span> Abra o cadastro gratuito da API-Football.</li>
          <li><span className="mr-2 font-mono text-[#e9877e]">02</span> Copie a chave que o painel mostrar.</li>
          <li><span className="mr-2 font-mono text-[#e9877e]">03</span> Cole abaixo. Ela não aparece de novo na tela.</li>
        </ol>

        <a href="https://dashboard.api-football.com/register" target="_blank" rel="noreferrer" className="mt-5 inline-flex border border-[#d96a63]/60 px-4 py-3 text-sm font-semibold text-[#f4cdc8] transition-colors hover:bg-[#d96a63] hover:text-[#171b1c] active:translate-y-px">Abrir cadastro gratuito</a>

        <form onSubmit={handleSubmit} className="mt-7">
          <label htmlFor="api-football-key" className="text-xs font-semibold tracking-[0.14em] text-[#d9ddda] uppercase">Chave da API-Football</label>
          <input id="api-football-key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="off" spellCheck="false" placeholder="Cole a chave aqui" className="mt-3 min-h-[48px] w-full border border-white/12 bg-[#101416] px-4 py-3 text-base text-[#f1f2ec] outline-none transition-colors placeholder:text-[#68706d] focus:border-[#e4524b]" />
          <p className="mt-2 text-xs leading-5 text-[#818985]">Para a versão pública, a chave fica no servidor — nunca nesta tela.</p>
          {error && <p role="alert" className="mt-3 border-l-2 border-[#e4524b] pl-3 text-sm leading-6 text-[#f1b7b2]">{error}</p>}
          {success && <p role="status" className="mt-3 border-l-2 border-[#d96a63] pl-3 text-sm leading-6 text-[#eadfd7]">{success}</p>}
          <div className="mt-5 flex justify-end">
            <button type="submit" disabled={isSaving} className="min-h-[44px] bg-[#e4524b] px-4 py-3 text-sm font-bold text-[#141718] transition-colors hover:bg-[#f0645d] disabled:cursor-wait disabled:bg-[#9e514d] active:translate-y-px">{isSaving ? "Salvando" : "Salvar e ativar"}</button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default function App() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSetupOpen, setIsSetupOpen] = useState(false);
  const resultsRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!result || !window.matchMedia("(max-width: 1023px)").matches) return;
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [result]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuestion = question.trim();
    if (cleanQuestion.length < 6) {
      setError("Escreva uma pergunta um pouco mais completa.");
      return;
    }

    setError("");
    setResult(null);
    setIsLoading(true);
    try {
      setResult(await submitQuestion(cleanQuestion));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Não foi possível consultar os dados.");
    } finally {
      setIsLoading(false);
    }
  }

  function useExample(example: string) {
    setQuestion(example);
    setError("");
  }

  return (
    <div className="min-h-[100dvh] overflow-x-hidden bg-[#101416] text-[#edf0eb]">
      <header className="mx-auto flex max-w-[1440px] items-center justify-between border-b border-white/8 px-4 py-4 sm:px-8 sm:py-5 lg:px-10">
        <a href="/" className="group flex items-center gap-2.5 text-[#f3eee5]" aria-label="ScoreFlash, início">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-[#e4524b] text-[#101416] transition-transform duration-300 group-hover:rotate-[-12deg]"><FlashMark /></span>
          <span className="text-lg font-bold tracking-[-0.05em]">ScoreFlash</span>
        </a>
        <div className="flex items-center gap-3 text-xs text-[#aeb5b1]">
          <span className="hidden items-center gap-2 sm:flex"><span className="h-1.5 w-1.5 rounded-full bg-[#d96a63] motion-safe:animate-pulse" /> Futebol em linguagem natural</span>
          {localKeySetupEnabled && <button type="button" onClick={() => setIsSetupOpen(true)} className="min-h-[44px] border border-white/12 px-3 py-2 font-semibold text-[#e8eae4] transition-colors hover:border-[#d96a63] active:translate-y-px">Modo dono</button>}
        </div>
      </header>

      <main className="mx-auto grid max-w-[1440px] gap-4 px-4 pb-4 pt-4 sm:px-8 sm:pb-8 sm:pt-6 lg:grid-cols-[minmax(360px,0.72fr)_minmax(0,1.28fr)] lg:gap-0 lg:px-10 lg:pb-10 lg:pt-10">
        <section className="flex min-h-0 flex-col border border-white/10 bg-[#151b1d] p-5 sm:min-h-[610px] sm:p-8 lg:border-r-0 lg:p-10">
          <div className="max-w-xl">
            <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.17em] text-[#e9877e] uppercase"><PulseIcon /> Comando de análise</div>
            <h1 className="mt-6 max-w-lg font-display text-[clamp(2.6rem,12vw,4rem)] leading-[0.88] tracking-[-0.07em] text-[#f5f0e8] sm:mt-7 sm:text-[clamp(3rem,5vw,5rem)]">Futebol sem procurar tabela.</h1>
            <p className="mt-5 max-w-md text-base leading-7 text-[#aeb6b2] sm:mt-6">Pergunte sobre um time ou jogador. A resposta vem com recorte, leitura humana e cada jogo usado no cálculo.</p>
          </div>

          <form onSubmit={handleSubmit} className="mt-8 sm:mt-10">
            <label htmlFor="question" className="text-[11px] font-semibold tracking-[0.16em] text-[#d9ddda] uppercase">O que você quer descobrir?</label>
            <div className="mt-3 border border-white/12 bg-[#101416] transition-colors focus-within:border-[#e4524b]">
              <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ex.: O São Paulo finaliza bem quando joga fora?" rows={3} maxLength={500} className="w-full resize-none bg-transparent px-4 py-4 text-base leading-6 text-[#f1f2ec] outline-none placeholder:text-[#68706d] sm:py-5" />
              <div className="flex items-center justify-between gap-4 border-t border-white/8 px-3 py-3">
                <span className="hidden text-xs text-[#79827d] sm:block">Escreva como falaria com um analista.</span>
                <button type="submit" disabled={isLoading} className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 bg-[#e4524b] px-4 py-2.5 text-sm font-bold text-[#141718] transition-colors hover:bg-[#f0645d] disabled:cursor-wait disabled:bg-[#9e514d] active:translate-y-px sm:ml-auto sm:w-auto">
                  {isLoading ? "Analisando" : "Analisar"}
                  {!isLoading && <ArrowIcon />}
                </button>
              </div>
            </div>
            {error && <p role="alert" className="mt-4 border-l-2 border-[#e4524b] pl-3 text-sm leading-6 text-[#f1b7b2]">{error}</p>}
          </form>

          <div className="mt-8 border-t border-white/10 pt-5 sm:mt-auto sm:pt-6">
            <p className="mb-3 text-[10px] font-semibold tracking-[0.16em] text-[#7f8984] uppercase">Experimente uma pergunta</p>
            <div className="-mx-1 flex snap-x snap-mandatory gap-2 overflow-x-auto px-1 pb-1">
              {examples.map((example) => (
                <button key={example} type="button" onClick={() => useExample(example)} className="min-h-[44px] min-w-[13rem] snap-start border border-white/12 px-3 py-2 text-left text-xs leading-4 text-[#bec6c0] transition-colors hover:border-[#d96a63] hover:text-[#f3eee5] active:translate-y-px">{example}</button>
              ))}
            </div>
          </div>
        </section>

        <aside ref={resultsRef} className="min-h-0 scroll-mt-4 border border-white/10 bg-[#202728] p-5 sm:min-h-[610px] sm:p-8 lg:p-10">
          {isLoading ? <ResultsSkeleton /> : <ResultsPanel result={result} />}
        </aside>
      </main>

      <footer className="mx-auto flex max-w-[1440px] flex-col gap-2 border-t border-white/8 px-4 py-6 text-xs leading-5 text-[#737b77] sm:flex-row sm:items-center sm:justify-between sm:px-8 lg:px-10">
        <span>ScoreFlash <span className="px-1">/</span> dados consultados sob demanda</span>
        <span>Leitura estatística; não é garantia de resultado.</span>
      </footer>

      {isSetupOpen && localKeySetupEnabled && <LocalKeySetup onClose={() => setIsSetupOpen(false)} />}
    </div>
  );
}
