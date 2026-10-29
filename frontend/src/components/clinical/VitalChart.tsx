import { useState } from "react";
import { fmtDate } from "@/lib/format";
import type { Observation, Rule } from "@/types";

type Series = { name: string; metric: string; pick: (o: Observation) => number | null | undefined; color: string };
const W = 640, H = 260, PAD = { l: 44, r: 64, t: 16, b: 30 };

/** Full-size trend of one vital with the doctor-approved alert thresholds drawn as dashed lines. Hover for exact readings. */
export function VitalChart({ type, unit, observations, rules }: { type: string; unit: string; observations: Observation[]; rules: Rule[] }) {
  const list = observations.filter((o) => o.type === type).sort((a, b) => +new Date(a.recordedAt) - +new Date(b.recordedAt));
  const series: Series[] =
    type === "BP"
      ? [
          { name: "Systolic", metric: "SYSTOLIC_BP", pick: (o) => o.value, color: "#6366f1" },
          { name: "Diastolic", metric: "DIASTOLIC_BP", pick: (o) => o.value2, color: "#475569" },
        ]
      : [{ name: unit, metric: type, pick: (o) => o.value, color: "#6366f1" }];
  const [hover, setHover] = useState<number | null>(null);
  if (list.length < 2) return <p className="py-8 text-center text-sm text-ink-500">Needs at least two readings to draw a trend.</p>;

  const limits = series.flatMap((s) => rules.filter((r) => r.metric === s.metric && r.threshold != null && [">", ">=", "<", "<="].includes(r.operator)).map((r) => ({ ...r, s })));
  const vals = [...series.flatMap((s) => list.map((o) => s.pick(o)).filter((v): v is number => typeof v === "number")), ...limits.map((l) => l.threshold as number)];
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
  const min = lo - span * 0.12, max = hi + span * 0.12;
  const t0 = +new Date(list[0].recordedAt), t1 = +new Date(list[list.length - 1].recordedAt);
  const x = (t: number) => PAD.l + ((t - t0) / (t1 - t0 || 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - (v - min) / (max - min)) * (H - PAD.t - PAD.b);
  const ticks = [0, 1, 2, 3].map((i) => min + ((max - min) * i) / 3);
  const point = hover != null ? list[hover] : null;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${type} trend`} onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          let best = 0;
          list.forEach((o, i) => { if (Math.abs(x(+new Date(o.recordedAt)) - px) < Math.abs(x(+new Date(list[best].recordedAt)) - px)) best = i; });
          setHover(best);
        }}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="#e2e8f0" strokeWidth="1" />
            <text x={PAD.l - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill="#64748b">{Math.round(v * 10) / 10}</text>
          </g>
        ))}
        {limits.map((l) => (
          <g key={l.id}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(l.threshold as number)} y2={y(l.threshold as number)} stroke="#e11d48" strokeWidth="1.5" strokeDasharray="5 4" />
            <text x={W - PAD.r + 4} y={y(l.threshold as number) + 4} fontSize="10.5" fill="#be123c">⚠ {l.operator} {l.threshold}</text>
          </g>
        ))}
        {series.map((s) => {
          const pts = list.filter((o) => typeof s.pick(o) === "number");
          return (
            <g key={s.metric}>
              <polyline fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" points={pts.map((o) => `${x(+new Date(o.recordedAt))},${y(s.pick(o) as number)}`).join(" ")} />
              {pts.map((o) => (
                <circle key={o.id} cx={x(+new Date(o.recordedAt))} cy={y(s.pick(o) as number)} r={o.flagged ? 5 : 3.5} fill={o.flagged ? "#e11d48" : s.color} stroke="#fff" strokeWidth="2" />
              ))}
              {series.length > 1 && <text x={x(t1) + 8} y={y(s.pick(list[list.length - 1]) as number) + 4} fontSize="11" fill="#334155">{s.name}</text>}
            </g>
          );
        })}
        <text x={PAD.l} y={H - 8} fontSize="11" fill="#64748b">{fmtDate(list[0].recordedAt, "d MMM")}</text>
        <text x={W - PAD.r} y={H - 8} textAnchor="end" fontSize="11" fill="#64748b">{fmtDate(list[list.length - 1].recordedAt, "d MMM")}</text>
        {point && <line x1={x(+new Date(point.recordedAt))} x2={x(+new Date(point.recordedAt))} y1={PAD.t} y2={H - PAD.b} stroke="#94a3b8" strokeWidth="1" />}
      </svg>
      <div className="min-h-9 text-xs text-ink-700" aria-live="polite">
        {point ? (
          <span>
            <b>{fmtDate(point.recordedAt, "d MMM, h:mm a")}</b> · {series.map((s) => `${s.name === unit ? "" : s.name + " "}${s.pick(point) ?? "—"}`).join(" / ")} {unit}
            {point.flagged && <b className="ml-2 text-rose-600">⚠ flagged</b>} <span className="text-ink-400">({point.source.toLowerCase()})</span>
          </span>
        ) : (
          <span className="text-ink-400">Hover the chart for exact readings. Dashed line = alert threshold set in the approved plan; red dot = flagged reading.</span>
        )}
      </div>
    </div>
  );
}
