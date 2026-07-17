interface CalibBucket {
  label: string;
  mid: number;
  n: number;
  mean_conf: number | null;
  win_rate: number | null;
}

const W = 400, H = 260, PAD = { top: 16, right: 16, bottom: 48, left: 48 };
const IW = W - PAD.left - PAD.right;
const IH = H - PAD.top - PAD.bottom;

function x(v: number) { return PAD.left + v * IW; }
function y(v: number) { return PAD.top + (1 - v) * IH; }

export default function CalibrationChart({ buckets }: { buckets: CalibBucket[] }) {
  const filled = buckets.filter((b) => b.win_rate !== null && b.mean_conf !== null);

  return (
    <div>
      <p className="text-xs text-gray-500 mb-3">
        Reliability diagram — each dot is a confidence bucket. On the diagonal = perfectly
        calibrated. Above = underconfident, below = overconfident.
      </p>
      <div className="flex flex-col items-center">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-md" aria-label="Calibration chart">
          {/* grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((v) => (
            <g key={v}>
              <line x1={x(0)} y1={y(v)} x2={x(1)} y2={y(v)} stroke="#333" strokeWidth="0.5" />
              <text x={PAD.left - 6} y={y(v) + 4} textAnchor="end" fontSize="10" fill="#6b7280">
                {Math.round(v * 100)}%
              </text>
            </g>
          ))}
          {[0.5, 0.6, 0.7, 0.8, 0.9, 1].map((v) => (
            <g key={v}>
              <line x1={x(v - 0.5)} y1={y(0)} x2={x(v - 0.5)} y2={y(1)} stroke="#333" strokeWidth="0.5" />
              <text x={x(v - 0.5)} y={y(0) + 18} textAnchor="middle" fontSize="10" fill="#6b7280">
                {Math.round(v * 100)}%
              </text>
            </g>
          ))}

          {/* perfect calibration diagonal */}
          <line
            x1={x(0)} y1={y(0.5)}
            x2={x(0.5)} y2={y(1)}
            stroke="#4b5563" strokeWidth="1.5" strokeDasharray="4 3"
          />

          {/* axis labels */}
          <text x={W / 2} y={H - 4} textAnchor="middle" fontSize="11" fill="#9ca3af">
            Predicted confidence
          </text>
          <text
            x={14} y={PAD.top + IH / 2}
            textAnchor="middle" fontSize="11" fill="#9ca3af"
            transform={`rotate(-90, 14, ${PAD.top + IH / 2})`}
          >
            Actual win rate
          </text>

          {/* data points — circle sized by n */}
          {filled.map((b) => {
            const cx = x(b.mean_conf! - 0.5);
            const cy = y(b.win_rate!);
            const r  = Math.max(5, Math.min(14, 4 + Math.sqrt(b.n) * 1.5));
            const diff = Math.abs(b.win_rate! - b.mean_conf!);
            const fill = diff < 0.08 ? "#22c55e" : diff < 0.15 ? "#f59e0b" : "#ef4444";
            return (
              <g key={b.label}>
                <circle cx={cx} cy={cy} r={r} fill={fill} fillOpacity="0.8" />
                <text x={cx} y={cy + 4} textAnchor="middle" fontSize="9" fill="white" fontWeight="bold">
                  {b.n}
                </text>
              </g>
            );
          })}
        </svg>

        {/* bucket legend */}
        {filled.length > 0 ? (
          <div className="mt-3 grid grid-cols-3 gap-x-6 gap-y-1 text-xs text-gray-400">
            {filled.map((b) => (
              <span key={b.label}>
                {b.label}: {b.win_rate !== null ? `${(b.win_rate * 100).toFixed(0)}% (n=${b.n})` : "—"}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-500 mt-2">Not enough graded predictions yet.</p>
        )}
      </div>

      <div className="mt-3 flex gap-4 text-xs justify-center">
        {[["#22c55e", "< 8pp off diagonal"], ["#f59e0b", "8–15pp off"], ["#ef4444", "> 15pp off"]].map(([c, l]) => (
          <span key={l} className="flex items-center gap-1">
            <span style={{ background: c }} className="inline-block w-2.5 h-2.5 rounded-full" />
            <span className="text-gray-400">{l}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
