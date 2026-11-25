import { describeTrend } from "@/components/dashboard/labels";

/**
 * Small trend line for a KPI tile. It is an image to assistive tech, so its accessible
 * name summarises the series. The exact weekly numbers sit in the weekly activity table.
 */
export function Sparkline({ values, label }: { values: readonly number[]; label: string }) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 22 - (value / max) * 20;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      role="img"
      aria-label={describeTrend(values, label)}
      viewBox="0 0 100 24"
      preserveAspectRatio="none"
      className="h-6 w-full text-chart-1"
    >
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        points={points}
      />
    </svg>
  );
}
