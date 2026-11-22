import { useTranslation } from "react-i18next";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export type ForecastChartData = {
  months: string[];
  monthly_totals: number[];
  forecast_next_month: number;
};

// Two series, two meanings: the accent for actual spend, amber for the
// projected month. Both come from the theme tokens so light/dark both work.
const ACTUAL_COLOR = "var(--color-teal)";
const FORECAST_COLOR = "var(--color-amber)";
const AXIS_TICK = { fontSize: 12, fill: "var(--color-muted)", fontFamily: "var(--font-mono)" };

export default function ForecastChart({ chart }: { chart: ForecastChartData }) {
  const { t } = useTranslation("costSaving");

  // One combined series per month: `actual` is set for every historical
  // month, `forecast` only for the last historical month (so the dashed
  // segment visually connects) and the projected month - this is how a
  // single LineChart renders two visually distinct segments (solid vs
  // dashed) sharing one continuous line, without a dual-axis chart.
  type Point = { month: string; actual: number | null; forecast: number | null };
  const data: Point[] = chart.months.map((m, i) => ({
    month: m,
    actual: chart.monthly_totals[i],
    forecast: i === chart.months.length - 1 ? chart.monthly_totals[i] : null,
  }));
  data.push({ month: t("card.forecastPoint"), actual: null, forecast: chart.forecast_next_month });

  return (
    <div className="mt-2">
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-border)" vertical={false} />
          <XAxis dataKey="month" tick={AXIS_TICK} axisLine={false} tickLine={false} />
          <YAxis tick={AXIS_TICK} width={48} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{ background: "var(--color-panel)", border: "1px solid var(--color-border)", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "var(--color-parchment)" }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="actual"
            name={t("card.actualSpend")}
            stroke={ACTUAL_COLOR}
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="forecast"
            name={t("card.forecastSpend")}
            stroke={FORECAST_COLOR}
            strokeWidth={2}
            strokeDasharray="4 4"
            dot={{ r: 3 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
