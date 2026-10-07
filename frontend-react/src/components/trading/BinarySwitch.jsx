export default function BinarySwitch({ value, onChange, leftLabel = "Buy", rightLabel = "Sell", leftValue = "BUY", rightValue = "SELL" }) {
  const isLeft = value === leftValue;
  return (
    <div className="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1">
      <button
        type="button"
        onClick={() => onChange(leftValue)}
        className={`rounded-lg px-4 py-2 text-sm font-semibold ${isLeft ? "bg-emerald-600 text-white" : "text-slate-600"}`}
      >
        {leftLabel}
      </button>
      <button
        type="button"
        onClick={() => onChange(rightValue)}
        className={`rounded-lg px-4 py-2 text-sm font-semibold ${!isLeft ? "bg-rose-600 text-white" : "text-slate-600"}`}
      >
        {rightLabel}
      </button>
    </div>
  );
}
