import { useMemo, useState } from "react";
import { jsPDF } from "jspdf";
import { CRYPTOBRIDGE_LOGO_SRC } from "../../utils/documentTitle";
import { compareBacktestRuns } from "../../utils/stOptionsBacktestCompare";
import WorkspaceDataTable, {
  WorkspaceTable,
  WorkspaceTableBody,
  WorkspaceTableHead,
} from "../ui/WorkspaceDataTable";
import {
  modalOverlay,
  modalPanel,
  primaryButton,
  secondaryButton,
  textHeading,
  textMuted,
  profitText,
  lossText,
} from "../../utils/workspace/workspaceClasses";

function fmt(n, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}

function pnlClass(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "";
  return n > 0 ? profitText() : lossText();
}

async function loadLogoDataUrl() {
  try {
    const res = await fetch(CRYPTOBRIDGE_LOGO_SRC);
    const blob = await res.blob();
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

export default function StOptionsBacktestCompareModal({
  open,
  runs,
  runAId,
  runBId,
  onChangeA,
  onChangeB,
  onClose,
}) {
  const [pdfPending, setPdfPending] = useState(false);
  const runA = useMemo(() => runs.find((r) => r.id === runAId) || null, [runs, runAId]);
  const runB = useMemo(() => runs.find((r) => r.id === runBId) || null, [runs, runBId]);
  const comparison = useMemo(() => {
    if (!runA?.result || !runB?.result) return null;
    return compareBacktestRuns(runA, runB);
  }, [runA, runB]);

  if (!open) return null;

  const downloadPdf = async () => {
    if (!comparison || !runA || !runB) return;
    setPdfPending(true);
    try {
      const doc = new jsPDF({ unit: "pt", format: "a4" });
      const margin = 40;
      let y = margin;
      const logo = await loadLogoDataUrl();
      if (logo) {
        try {
          doc.addImage(logo, "PNG", margin, y, 120, 28);
        } catch {
          /* svg may fail; fall through */
        }
        y += 40;
      }
      doc.setFontSize(16);
      doc.text("ST Options — Backtest Compare", margin, y);
      y += 22;
      doc.setFontSize(10);
      doc.setTextColor(80);
      doc.text(
        `Run A: ${runA.from || "—"} → ${runA.to || "—"}  |  Run B: ${runB.from || "—"} → ${runB.to || "—"}`,
        margin,
        y,
      );
      y += 18;
      doc.setTextColor(0);
      doc.text("Input differences", margin, y);
      y += 14;
      comparison.inputDiffs.slice(0, 20).forEach((row) => {
        doc.text(`${row.key}: ${row.a ?? "—"} → ${row.b ?? "—"}`, margin, y);
        y += 12;
        if (y > 760) {
          doc.addPage();
          y = margin;
        }
      });
      y += 8;
      doc.text(
        `Overlapping trades: ${comparison.overlapping.length}  |  Norm PnL A ${fmt(comparison.sumA)}  B ${fmt(comparison.sumB)}  Δ% ${
          comparison.totalPctDiff == null ? "—" : fmt(comparison.totalPctDiff, 1)
        }`,
        margin,
        y,
      );
      y += 16;
      doc.text(comparison.verdict, margin, y, { maxWidth: 515 });
      y += 28;
      doc.text("Overlapping trades (normalized)", margin, y);
      y += 14;
      comparison.overlapping.slice(0, 40).forEach((row) => {
        doc.text(
          `${row.date || ""} ${row.direction} ${row.optionSymbol}  A:${fmt(row.normA)} B:${fmt(row.normB)} Δ%:${
            row.pctDiff == null ? "—" : fmt(row.pctDiff, 1)
          }`,
          margin,
          y,
        );
        y += 12;
        if (y > 760) {
          doc.addPage();
          y = margin;
        }
      });
      doc.save(`st-options-compare-${runA.id?.slice?.(0, 6) || "a"}-${runB.id?.slice?.(0, 6) || "b"}.pdf`);
    } finally {
      setPdfPending(false);
    }
  };

  return (
    <div className={modalOverlay()} role="dialog" aria-modal="true" aria-labelledby="st-bt-compare-title">
      <div className={modalPanel("max-w-5xl w-full overflow-hidden max-h-[90vh] flex flex-col")}>
        <div className="px-6 py-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between gap-3 shrink-0">
          <h3 id="st-bt-compare-title" className={`text-base font-bold uppercase tracking-wider ${textHeading()}`}>
            Compare backtests
          </h3>
          <button
            type="button"
            className="p-2 rounded bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-zinc-600 dark:text-zinc-300"
            onClick={onClose}
            title="Close"
          >
            <span className="sr-only">Close</span>
            <svg fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 space-y-5 overflow-y-auto">
          <div className="grid md:grid-cols-2 gap-3">
            <label className="block space-y-1">
              <span className={`text-[10px] font-bold uppercase tracking-widest ${textMuted()}`}>Run A</span>
              <select
                className="w-full rounded-lg border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm"
                value={runAId || ""}
                onChange={(e) => onChangeA(e.target.value)}
              >
                <option value="">Select…</option>
                {runs.map((r) => (
                  <option key={r.id} value={r.id} disabled={r.id === runBId}>
                    {(r.from || "?") + " → " + (r.to || "?")} · {fmt(r.totalPnl)} ({r.totalTrades ?? 0})
                  </option>
                ))}
              </select>
            </label>
            <label className="block space-y-1">
              <span className={`text-[10px] font-bold uppercase tracking-widest ${textMuted()}`}>Run B</span>
              <select
                className="w-full rounded-lg border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-2 text-sm"
                value={runBId || ""}
                onChange={(e) => onChangeB(e.target.value)}
              >
                <option value="">Select…</option>
                {runs.map((r) => (
                  <option key={r.id} value={r.id} disabled={r.id === runAId}>
                    {(r.from || "?") + " → " + (r.to || "?")} · {fmt(r.totalPnl)} ({r.totalTrades ?? 0})
                  </option>
                ))}
              </select>
            </label>
          </div>

          {!comparison ? (
            <p className={`text-sm ${textMuted()}`}>Select two saved runs with results to compare.</p>
          ) : (
            <>
              <div>
                <p className={`text-[10px] font-bold uppercase tracking-widest mb-2 ${textMuted()}`}>Input differences</p>
                <div className="grid sm:grid-cols-2 gap-2">
                  {comparison.inputDiffs.map((row) => (
                    <div
                      key={row.key}
                      className={`rounded-lg border px-3 py-2 text-xs font-mono ${
                        row.changed
                          ? "border-amber-300 dark:border-amber-700 bg-amber-50/60 dark:bg-amber-950/30"
                          : "border-slate-200 dark:border-zinc-800"
                      }`}
                    >
                      <span className={textMuted()}>{row.key}</span>
                      <div className="mt-0.5">
                        {String(row.a ?? "—")} → {String(row.b ?? "—")}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <WorkspaceDataTable
                title="Overlapping trades"
                badge={`${comparison.overlapping.length}`}
                emptyMessage="No overlapping trades (same entry time, side, and option)."
              >
                {comparison.overlapping.length ? (
                  <WorkspaceTable>
                    <WorkspaceTableHead>
                      <th className="px-3 py-2">Date</th>
                      <th className="px-3 py-2">Side</th>
                      <th className="px-3 py-2">Option</th>
                      <th className="px-3 py-2 text-right">Norm A</th>
                      <th className="px-3 py-2 text-right">Norm B</th>
                      <th className="px-3 py-2 text-right">Δ %</th>
                    </WorkspaceTableHead>
                    <WorkspaceTableBody>
                      {comparison.overlapping.map((row) => (
                        <tr key={row.key} className="hover:bg-slate-50 dark:hover:bg-zinc-950/60">
                          <td className="px-3 py-2 whitespace-nowrap">{row.date || "—"}</td>
                          <td className="px-3 py-2">{row.direction}</td>
                          <td className="px-3 py-2 font-mono text-xs">{row.optionSymbol}</td>
                          <td className={`px-3 py-2 text-right font-mono ${pnlClass(row.normA)}`}>{fmt(row.normA)}</td>
                          <td className={`px-3 py-2 text-right font-mono ${pnlClass(row.normB)}`}>{fmt(row.normB)}</td>
                          <td className={`px-3 py-2 text-right font-mono ${pnlClass(row.absDiff)}`}>
                            {row.pctDiff == null ? "—" : `${fmt(row.pctDiff, 1)}%`}
                          </td>
                        </tr>
                      ))}
                    </WorkspaceTableBody>
                  </WorkspaceTable>
                ) : null}
              </WorkspaceDataTable>

              <div className="rounded-xl border border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-zinc-950 p-4 space-y-1">
                <p className={`text-[10px] font-bold uppercase tracking-widest ${textMuted()}`}>Verdict</p>
                <p className="text-sm font-semibold">{comparison.verdict}</p>
                <p className={`text-xs ${textMuted()}`}>
                  Only in A: {comparison.onlyInA} · Only in B: {comparison.onlyInB} · Normalized to initial lots A=
                  {comparison.lotsA} / B={comparison.lotsB}
                </p>
              </div>
            </>
          )}
        </div>

        <div className="bg-slate-50 dark:bg-zinc-950 px-6 py-4 border-t border-slate-200 dark:border-zinc-800 flex justify-end gap-3 shrink-0">
          <button type="button" className={secondaryButton()} onClick={onClose}>
            Close
          </button>
          <button
            type="button"
            className={primaryButton()}
            disabled={!comparison || pdfPending}
            onClick={downloadPdf}
          >
            {pdfPending ? "Preparing…" : "Download PDF"}
          </button>
        </div>
      </div>
    </div>
  );
}
