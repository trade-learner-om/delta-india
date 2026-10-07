import { useEffect, useRef, useState } from "react";

export default function PriceFlashTicker({ value, children, className = "" }) {
  const previous = useRef(null);
  const [flash, setFlash] = useState("");
  const number = Number(value);

  useEffect(() => {
    if (!Number.isFinite(number)) return undefined;
    if (previous.current == null) {
      previous.current = number;
      return undefined;
    }
    if (number === previous.current) return undefined;
    const next = number > previous.current ? "animate-flash-green" : "animate-flash-red";
    previous.current = number;
    setFlash("");
    const frame = window.requestAnimationFrame(() => setFlash(next));
    return () => window.cancelAnimationFrame(frame);
  }, [number]);

  return (
    <span className={`inline-flex rounded px-1 ${flash} ${className}`} onAnimationEnd={() => setFlash("")}>
      {children}
    </span>
  );
}
