export function buildEquitySparkline(equityCurve, width = 280, height = 60) {
  if (!Array.isArray(equityCurve) || equityCurve.length < 2) return null;
  const values = equityCurve.map((point) => Number(point.equity ?? point.value) || 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = width / (values.length - 1);
  const points = values
    .map((value, index) => {
      const x = index * stepX;
      const y = height - ((value - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const zeroY = height - ((0 - min) / span) * height;
  return { points, zeroY: zeroY.toFixed(1), width, height, min, max };
}
