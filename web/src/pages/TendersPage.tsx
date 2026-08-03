import { useEffect, useState, useCallback } from "react";
import { RefreshCw, ExternalLink, Search } from "lucide-react";
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
  status: string | null;
  matched_keywords: string[] | null;
};

type Stats = {
  total_tenders: number;
  tenders_today: number;
  strong_fit_count: number;
  potential_fit_count: number;
  sources_active: number;
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

export default function TendersPage() {
  const { setTitle } = usePageHeader();
  const [tenders, setTenders] = useState<Tender[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fit, setFit] = useState("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (fit) params.set("fit", fit);
      if (source) params.set("source", source);
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
  }, [fit, source]);

  useEffect(() => {
    setTitle("Tenders");
  }, [setTitle]);
  useEffect(() => {
    load();
  }, [load]);

  const shown = query
    ? tenders.filter((t) =>
        `${t.title} ${t.issuing_authority} ${t.category}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      )
    : tenders;

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

      {/* filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="text-text-tertiary absolute left-2 top-2.5 h-4 w-4" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by title, authority, category…"
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
          {shown.length} shown
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
                <th className="p-2 font-medium">Fit</th>
                <th className="p-2 font-medium">Authority</th>
                <th className="p-2 font-medium">Title</th>
                <th className="p-2 font-medium">Category</th>
                <th className="p-2 font-medium">Value</th>
                <th className="p-2 font-medium">Deadline</th>
                <th className="p-2 font-medium">Source</th>
                <th className="p-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {shown.map((t) => (
                <tr key={t.id} className="border-border border-t align-top">
                  <td className="p-2">
                    <Badge tone={FIT_TONE[t.fit_classification || ""] || "outline"}>
                      {FIT_LABEL[t.fit_classification || ""] || "—"}
                    </Badge>
                  </td>
                  <td className="p-2">{t.issuing_authority || "—"}</td>
                  <td className="max-w-md p-2">{t.title}</td>
                  <td className="p-2">{t.category || "—"}</td>
                  <td className="whitespace-nowrap p-2">{fmtValue(t)}</td>
                  <td className="whitespace-nowrap p-2">{t.deadline || "—"}</td>
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
              ))}
              {!shown.length && (
                <tr>
                  <td colSpan={8} className="text-text-tertiary p-6 text-center">
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
