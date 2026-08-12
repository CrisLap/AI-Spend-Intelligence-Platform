import { useTranslation } from "react-i18next";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export type ForecastChartData = {
  months: string[];
  monthly_totals: number[];
  forecast_next_month: number;
};

// Reuses the exact two colors already established in Dashboard.tsx's
// COLORS palette (teal for the primary series, amber for a
// caution/projected one) rather than introducing new hues for this one
// embedded chart.
const ACTUAL_COLOR = "#2dd4bf";
const FORECAST_COLOR = "#f59e0b";
const AXIS_TICK = { fontSize: 11, fill: "#6b6b80" };

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
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" vertical={false} />
          <XAxis dataKey="month" tick={AXIS_TICK} />
          <YAxis tick={AXIS_TICK} width={48} />
          <Tooltip
            contentStyle={{ background: "#1a1a26", border: "1px solid #2a2a3a", fontSize: 12 }}
            labelStyle={{ color: "#e8e8ed" }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
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
