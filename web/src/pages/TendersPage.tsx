import { Fragment, useEffect, useState, useCallback } from "react";
import { ChevronDown, ChevronRight, RefreshCw, ExternalLink, Search } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { usePageHeader } from "@/contexts/usePageHeader";

// tender-api runs as its own service (compose: tender-api:8000), separate from
// the Seple T Agent dashboard server — so we can't use the built-in `api` helper.
// CORS on tender-api is open (allow_origins=["*"]). Override per-deployment with
// VITE_TENDER_API_URL if the API isn't on localhost:8000.
// ponytail: hardcoded localhost default; set VITE_TENDER_API_URL to change.
const TENDER_API =
  import.meta.env.VITE_TENDER_API_URL || "http://localhost:8000";

type Tender = {
  id: string;
  title: string;
  issuing_authority: string | null;
  location: string | null;
  category: string | null;
  value_raw: string | null;
  value_inr: number | null;
  deadline: string | null;
  source_url: string | null;
  source_name: string | null;
  fit_classification: string | null;
  confidence: string | null;
  status: string | null;
  matched_keywords: string[] | null;
  matching_rationale: string | null;
  analysis_model?: string | null;
  uncertainty_notes?: string[] | null;
};

type SourceStatus = {
  source: string;
  status: string;
  tenders_found: number;
  error: string | null;
  completed_at: string | null;
};

type Stats = {
  total_tenders: number;
  tenders_today: number;
  strong_fit_count: number;
  potential_fit_count: number;
  sources_active: number;
  source_status?: SourceStatus[];
};

const FITS = ["", "strong_fit", "potential_fit", "low_fit"] as const;
const SOURCES = ["", "TenderTiger", "Tender247", "CPPP", "GeM"] as const;

const FIT_LABEL: Record<string, string> = {
  strong_fit: "Strong Fit",
  potential_fit: "Potential Fit",
  low_fit: "Low Fit",
};
const FIT_TONE: Record<string, "success" | "warning" | "outline"> = {
  strong_fit: "success",
  potential_fit: "warning",
  low_fit: "outline",
};

function fmtValue(t: Tender): string {
  if (t.value_inr) return "₹" + t.value_inr.toLocaleString("en-IN");
  return t.value_raw || "—";
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export default function TendersPage() {
  const { setTitle } = usePageHeader();
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fit, setFit] = useState("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, Tender>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (fit) params.set("fit", fit);
      if (source) params.set("source", source);
      if (debouncedQuery) params.set("q", debouncedQuery);
      const [tRes, sRes] = await Promise.all([
        fetch(`${TENDER_API}/api/tenders?${params}`),
        fetch(`${TENDER_API}/api/stats`),
      ]);
      if (!tRes.ok) throw new Error(`API ${tRes.status}`);
      const tData = await tRes.json();
      setTenders(tData.data || []);
      if (sRes.ok) setStats(await sRes.json());
    } catch {
      setError(
        `Could not reach the tender API at ${TENDER_API}. Is the tender-api service running?`,
      );
      setTenders([]);
    } finally {
      setLoading(false);
    }
  }, [fit, source, debouncedQuery]);

  const toggleDetails = useCallback(async (t: Tender) => {
    if (expandedId === t.id) {
      setExpandedId(null);
      return;
    }

    setExpandedId(t.id);
    if (details[t.id]) return;

    try {
      const res = await fetch(`${TENDER_API}/api/tenders/${t.id}`);
      if (!res.ok) throw new Error(`API ${res.status}`);
      const data = await res.json();
      setDetails((prev) => ({ ...prev, [t.id]: data }));
    } catch {
      setDetails((prev) => ({
        ...prev,
        [t.id]: {
          ...t,
          matching_rationale: "Classification details could not be loaded.",
          uncertainty_notes: [],
        },
      }));
    }
  }, [details, expandedId]);

  useEffect(() => {
    setTitle("Tenders");
  }, [setTitle]);
  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedQuery(query.trim());
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [query]);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* stat tiles */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ["Total", stats.total_tenders],
            ["Strong fit", stats.strong_fit_count],
            ["Needs review", stats.potential_fit_count],
            ["Sources", stats.sources_active],
          ].map(([label, n]) => (
            <Card key={label as string}>
              <CardContent className="p-4">
                <div className="text-2xl font-semibold">{n as number}</div>
                <div className="text-text-tertiary text-sm">{label}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* per-source scan outcome — a failed scraper must not read as "no tenders" */}
      {stats?.source_status?.length ? (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-text-tertiary">Last scan:</span>
          {stats.source_status.map((s) => (
            <Badge
              key={s.source}
              tone={s.status === "failed" ? "destructive" : s.tenders_found ? "success" : "outline"}
              className="font-sans tracking-wide"
              title={s.error || (s.completed_at ? `Completed ${fmtDate(s.completed_at)}` : "")}
            >
              {s.source}: {s.status === "failed" ? "failed" : `${s.tenders_found}`}
            </Badge>
          ))}
        </div>
      ) : null}

      {/* filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="text-text-tertiary absolute left-2 top-2.5 h-4 w-4" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search title, authority, category, description…"
            className="border-border bg-background h-9 w-72 rounded-md border pl-8 pr-3 text-sm"
          />
        </div>
        <select
          value={fit}
          onChange={(e) => setFit(e.target.value)}
          className="border-border bg-background h-9 rounded-md border px-2 text-sm"
        >
          {FITS.map((f) => (
            <option key={f} value={f}>
              {f ? FIT_LABEL[f] : "All fits"}
            </option>
          ))}
        </select>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="border-border bg-background h-9 rounded-md border px-2 text-sm"
        >
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {s || "All sources"}
            </option>
          ))}
        </select>
        <Button outlined size="sm" onClick={load} disabled={loading}>
          <RefreshCw className="mr-1 h-4 w-4" />
          Refresh
        </Button>
        <span className="text-text-tertiary ml-auto text-sm">
          {tenders.length} shown
        </span>
      </div>

      {error && (
        <div className="text-destructive border-destructive/40 rounded-md border p-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center p-8">
          <Spinner />
        </div>
      ) : (
        <div className="border-border overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-text-tertiary text-left">
              <tr>
                <th className="w-8 p-2 font-medium"></th>
                <th className="p-2 font-medium">Fit</th>
                <th className="p-2 font-medium">Authority</th>
                <th className="p-2 font-medium">Title</th>
                <th className="p-2 font-medium">Category</th>
                <th className="p-2 font-medium">Location</th>
                <th className="p-2 font-medium">Value</th>
                <th className="p-2 font-medium">Deadline</th>
                <th className="p-2 font-medium">Source</th>
                <th className="p-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {tenders.map((t) => {
                const detail = details[t.id];
                const isExpanded = expandedId === t.id;
                const keywords = detail?.matched_keywords || t.matched_keywords || [];
                return (
                  <Fragment key={t.id}>
                    <tr className="border-border border-t align-top">
                      <td className="p-2">
                        <button
                          type="button"
                          aria-label={isExpanded ? "Collapse classification details" : "Expand classification details"}
                          aria-expanded={isExpanded}
                          onClick={() => void toggleDetails(t)}
                          className="text-text-tertiary hover:text-text-primary inline-flex h-6 w-6 items-center justify-center rounded"
                        >
                          {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </button>
                      </td>
                      <td className="p-2">
                        <Badge tone={FIT_TONE[t.fit_classification || ""] || "outline"} className="font-sans tracking-wide">
                          {FIT_LABEL[t.fit_classification || ""] || "—"}
                        </Badge>
                      </td>
                      <td className="p-2">{t.issuing_authority || "—"}</td>
                      <td className="max-w-md p-2">{t.title}</td>
                      <td className="p-2">{t.category || "—"}</td>
                      <td className="p-2">{t.location || "—"}</td>
                      <td className="whitespace-nowrap p-2">{fmtValue(t)}</td>
                      <td className="whitespace-nowrap p-2">{fmtDate(t.deadline)}</td>
                      <td className="p-2">{t.source_name || "—"}</td>
                      <td className="p-2">
                        {t.source_url && (
                          <a
                            href={t.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary inline-flex items-center gap-1"
                          >
                            Open <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="border-border bg-muted/20 border-t">
                        <td colSpan={10} className="p-4">
                          {detail ? (
                            <div className="flex flex-col gap-3">
                              <div>
                                <div className="text-text-tertiary mb-1 text-xs font-medium uppercase tracking-wide">Why this fit</div>
                                <p className="text-sm">{detail.matching_rationale || "No rationale recorded."}</p>
                              </div>
                              <div className="flex flex-wrap items-center gap-2 text-sm">
                                <span className="text-text-tertiary">Confidence:</span>
                                <span>{detail.confidence || "—"}</span>
                                {detail.analysis_model === "fallback-regex" && (
                                  <Badge tone="warning">Needs review — automated fallback (LLM unavailable)</Badge>
                                )}
                              </div>
                              <div className="flex flex-wrap gap-1">
                                {keywords.length ? keywords.map((keyword) => (
                                  <Badge key={keyword} tone="outline">{keyword}</Badge>
                                )) : <span className="text-text-tertiary text-sm">No matched keywords recorded.</span>}
                              </div>
                              {detail.uncertainty_notes?.length ? (
                                <div className="text-sm">
                                  <div className="text-text-tertiary mb-1 text-xs font-medium uppercase tracking-wide">Uncertainty notes</div>
                                  <ul className="list-disc pl-5">
                                    {detail.uncertainty_notes.map((note) => (
                                      <li key={note}>{note}</li>
                                    ))}
                                  </ul>
                                </div>
                              ) : null}
                              <div className="text-text-tertiary text-xs">
                                Criteria source: skills/tender-intelligence/SKILL.md §Fit Classification Rules.
                              </div>
                            </div>
                          ) : (
                            <div className="text-text-tertiary text-sm">Loading classification details…</div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
              {!tenders.length && (
                <tr>
                  <td colSpan={10} className="text-text-tertiary p-6 text-center">
                    No tenders. Run a scan or adjust filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
