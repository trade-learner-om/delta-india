export function appShell() {
  return "h-dvh overflow-hidden bg-slate-50 text-slate-900 dark:bg-zinc-950 dark:text-zinc-100 flex flex-col font-sans selection:bg-lime-400 selection:text-zinc-950";
}

export function headerShell() {
  return "bg-white dark:bg-zinc-900 border-b-2 border-lime-400 sticky top-0 z-40 px-6 py-3 flex flex-wrap justify-between items-center gap-4 shadow-md text-zinc-900 dark:text-zinc-100";
}

export function navShell() {
  return "bg-slate-100 dark:bg-zinc-900 border-b border-slate-200 dark:border-zinc-850 px-6 py-2 flex gap-1.5 overflow-x-auto select-none text-slate-800 dark:text-zinc-200";
}

export function authShell() {
  return "min-h-screen bg-slate-100 dark:bg-zinc-950 flex flex-col items-center justify-center p-4 select-none";
}

export function card(extra = "") {
  return `bg-white border border-slate-200 dark:bg-zinc-900 dark:border-zinc-800 rounded-xl shadow-sm dark:shadow-none text-slate-900 dark:text-zinc-100 ${extra}`.trim();
}

export function cardInner(extra = "") {
  return `bg-slate-50 border border-slate-200 dark:bg-zinc-950 dark:border-zinc-850 rounded-xl text-slate-900 dark:text-zinc-100 ${extra}`.trim();
}

export function field(extra = "") {
  return `w-full bg-white border border-slate-300 dark:bg-zinc-950 dark:border-zinc-850 dark:[color-scheme:dark] rounded-lg px-3 py-2 text-xs text-slate-900 dark:text-zinc-100 focus:outline-none focus:border-lime-500 dark:focus:border-lime-400 transition font-mono ${extra}`.trim();
}

export function fieldLabel() {
  return "block text-[10px] text-slate-500 dark:text-zinc-500 uppercase font-bold mb-1 tracking-wider";
}

export function formLabel() {
  return "block text-sm font-medium text-slate-700 dark:text-zinc-300";
}

export function formHint() {
  return "mt-1 block text-[11px] font-normal text-slate-400 dark:text-zinc-500";
}

export function statBoxTone(tone = "slate") {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-900 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100",
    emerald: "border-emerald-200 bg-emerald-50/70 text-emerald-900 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-400",
    rose: "border-rose-200 bg-rose-50/70 text-rose-900 dark:border-rose-400/30 dark:bg-rose-400/10 dark:text-rose-400",
    indigo: "border-indigo-200 bg-indigo-50/70 text-indigo-900 dark:border-lime-400/30 dark:bg-lime-400/10 dark:text-lime-400",
    profit: "border-emerald-200 bg-emerald-50/70 text-emerald-900 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-400",
    loss: "border-rose-200 bg-rose-50/70 text-rose-900 dark:border-rose-400/30 dark:bg-rose-400/10 dark:text-rose-400",
    accent: "border-indigo-200 bg-indigo-50/70 text-indigo-900 dark:border-lime-400/30 dark:bg-lime-400/10 dark:text-lime-400",
  };
  return tones[tone] || tones.slate;
}

export function panelInner(extra = "") {
  return `rounded-2xl border border-slate-200 bg-slate-50 dark:border-zinc-800 dark:bg-zinc-950 px-4 py-3 ${extra}`.trim();
}

export function resultPanelHeader() {
  return "border-b border-slate-100 dark:border-zinc-800 bg-gradient-to-r from-slate-50 via-white to-indigo-50/60 dark:from-zinc-950 dark:via-zinc-900 dark:to-lime-400/5 px-5 py-5";
}

export function segmentedBar() {
  return "mt-1 flex rounded-xl border border-slate-300 dark:border-zinc-700 p-1";
}

export function segmentedOption(active) {
  return active
    ? "flex-1 rounded-lg px-3 py-2 text-sm font-semibold bg-indigo-600 dark:bg-lime-400 text-white dark:text-zinc-950"
    : "flex-1 rounded-lg px-3 py-2 text-sm font-semibold text-slate-600 dark:text-zinc-400 hover:bg-slate-50 dark:hover:bg-zinc-800";
}

export function tableHeadSticky() {
  return "sticky top-0 bg-white dark:bg-zinc-900 text-xs uppercase tracking-[0.14em] text-slate-500 dark:text-zinc-500";
}

export function tableRow() {
  return "border-b border-slate-100 dark:border-zinc-850";
}

export function tableFooter() {
  return "flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 dark:border-zinc-850 px-3 py-2 text-sm";
}

export function subTab(active) {
  return active
    ? "px-4 py-1.5 text-xs font-bold rounded-lg transition bg-slate-200 text-slate-900 dark:bg-zinc-800 dark:text-lime-400"
    : "px-4 py-1.5 text-xs font-semibold rounded-lg transition text-slate-500 hover:text-slate-800 dark:text-zinc-400 dark:hover:text-zinc-200";
}

export function subTabBar() {
  return "flex bg-slate-100 dark:bg-zinc-900 p-1 rounded-xl border border-slate-200 dark:border-zinc-800";
}

export function pageShell() {
  return "flex-1 p-6 space-y-6 max-w-[1600px] w-full mx-auto text-slate-900 dark:text-zinc-100";
}

export function pageTitleRow() {
  return "flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-200 dark:border-zinc-800 pb-4";
}

export function textMuted() {
  return "text-slate-500 dark:text-zinc-500";
}

export function textBody() {
  return "text-slate-800 dark:text-zinc-200";
}

export function textHeading() {
  return "text-slate-900 dark:text-zinc-100";
}

export function accentLabel() {
  return "text-lime-600 dark:text-lime-400";
}

export function accentBadge() {
  return "text-lime-600 dark:text-lime-400 bg-lime-500/10 border-lime-500/20 dark:bg-lime-400/10 dark:border-lime-400/20";
}

export function accentText() {
  return "text-lime-600 dark:text-lime-400";
}

export function profitText() {
  return "text-emerald-600 dark:text-lime-400";
}

export function lossText() {
  return "text-red-600 dark:text-red-400";
}

export function tableCell() {
  return "text-slate-700 dark:text-zinc-300";
}

export function tableCellStrong() {
  return "text-slate-900 dark:text-zinc-100";
}

export function inactiveChip() {
  return "border-slate-200 bg-slate-100 text-slate-600 hover:border-slate-300 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:border-zinc-700";
}

export function activeChip() {
  return "border-lime-500/50 bg-lime-500/10 text-lime-600 dark:border-lime-400/50 dark:bg-lime-400/10 dark:text-lime-400";
}

export function dividerBorder() {
  return "border-slate-200 dark:border-zinc-800";
}

export function primaryButton(extra = "") {
  return `px-4 py-2 bg-lime-500 hover:bg-lime-600 dark:bg-lime-400 dark:hover:bg-lime-500 text-zinc-950 font-bold text-xs uppercase tracking-wider rounded-lg transition shadow-lg shadow-lime-400/10 disabled:opacity-50 ${extra}`.trim();
}

export function dangerButton(extra = "") {
  return `px-4 py-2 bg-red-500 hover:bg-red-600 text-zinc-100 font-extrabold text-xs uppercase rounded-lg transition ${extra}`.trim();
}

export function secondaryButton(extra = "") {
  return `inline-flex items-center gap-1.5 px-4 py-2 bg-slate-100 hover:bg-slate-200 border border-slate-300 text-slate-700 dark:bg-zinc-800 dark:hover:bg-zinc-700 dark:border-zinc-700 dark:text-zinc-200 font-bold text-xs uppercase tracking-wider rounded-lg transition disabled:opacity-50 ${extra}`.trim();
}

export function chartSurface(extra = "") {
  return `rounded-xl border border-slate-200 bg-slate-50 dark:border-zinc-800 dark:bg-zinc-950 ${extra}`.trim();
}

export function chartEmptyState(extra = "") {
  return `flex items-center justify-center rounded-xl border border-dashed border-slate-300 dark:border-zinc-800 bg-slate-50 dark:bg-zinc-950 text-sm text-slate-500 dark:text-zinc-500 ${extra}`.trim();
}

export function chartRangeTrack(extra = "") {
  return `relative h-10 rounded-full border border-slate-200 bg-slate-100 dark:border-zinc-800 dark:bg-zinc-950 ${extra}`.trim();
}

export function modalOverlay() {
  return "fixed inset-0 z-50 bg-slate-900/50 dark:bg-black/80 backdrop-blur-sm flex items-center justify-center p-4";
}

export function modalPanel(extra = "") {
  return `bg-white border border-slate-200 dark:bg-zinc-900 dark:border-zinc-800 rounded-2xl shadow-2xl ${extra}`.trim();
}
