/** Clear up/down bias arrows (SuperTrend colour). */
export default function BiasIcon({ colour, sentiment, className = "w-7 h-7" }) {
  const c = String(colour || "").toLowerCase();
  let dir = null;
  if (c === "green" || sentiment === "LONG") dir = "up";
  else if (c === "red" || sentiment === "SHORT") dir = "down";
  else if (String(sentiment || "").toLowerCase() === "up") dir = "up";
  else if (String(sentiment || "").toLowerCase() === "down") dir = "down";

  if (!dir) {
    return (
      <span className={`inline-flex items-center justify-center font-bold ${className}`} aria-label="Bias unknown">
        —
      </span>
    );
  }

  const tone =
    dir === "up"
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-rose-600 dark:text-rose-400";
  const label = dir === "up" ? "Up" : "Down";

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`inline-block shrink-0 ${className} ${tone}`}
      aria-label={label}
      role="img"
    >
      {dir === "up" ? (
        <>
          <path d="M12 19V5" />
          <path d="M5 12l7-7 7 7" />
        </>
      ) : (
        <>
          <path d="M12 5v14" />
          <path d="M19 12l-7 7-7-7" />
        </>
      )}
    </svg>
  );
}
