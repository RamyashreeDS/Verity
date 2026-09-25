"use client";

import clsx from "clsx";
import type { HealthEvent, HealthSeverity } from "@/lib/types";

const SEVERITY_STYLES: Record<HealthSeverity, string> = {
  low: "border-l-gray-600 bg-gray-900/40",
  medium: "border-l-yellow-600 bg-yellow-900/20",
  high: "border-l-orange-500 bg-orange-900/20",
  critical: "border-l-red-500 bg-red-900/20",
};

const SEVERITY_BADGE: Record<HealthSeverity, string> = {
  low: "bg-gray-800 text-gray-400",
  medium: "bg-yellow-900/50 text-yellow-400",
  high: "bg-orange-900/50 text-orange-400",
  critical: "bg-red-900/50 text-red-400",
};

const TYPE_ICONS: Record<string, string> = {
  stale: "⏱",
  contradiction: "⚡",
  missing: "❓",
  loop: "🔁",
  source_failure: "📡",
  source_degraded: "⚠️",
};

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

interface Props {
  events: HealthEvent[];
}

export default function HealthEvents({ events }: Props) {
  const open = events.filter((e) => !e.resolved);
  const resolved = events.filter((e) => e.resolved);

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">
          Health Events
        </h2>
        {open.length > 0 && (
          <span className="text-xs bg-red-900/50 text-red-400 px-2 py-0.5 rounded-full font-mono">
            {open.length} open
          </span>
        )}
      </div>

      {events.length === 0 && (
        <p className="text-sm text-gray-600 text-center py-4">Pipeline healthy — no events</p>
      )}

      <div className="flex flex-col gap-2 max-h-96 overflow-y-auto scrollbar-hide">
        {open.map((event) => (
          <div
            key={event.id}
            className={clsx(
              "border-l-2 rounded-r-lg px-3 py-2.5 flex flex-col gap-1",
              SEVERITY_STYLES[event.severity]
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <span className="text-xs">{TYPE_ICONS[event.type] ?? "•"}</span>
                <span
                  className={clsx("text-xs px-1.5 py-0.5 rounded font-mono", SEVERITY_BADGE[event.severity])}
                >
                  {event.severity}
                </span>
                <span className="text-xs text-gray-500">{event.type.replace("_", " ")}</span>
              </div>
              <span className="text-xs text-gray-600 mono">{timeAgo(event.detected_at)}</span>
            </div>
            <p className="text-xs text-gray-300 leading-relaxed">{event.description}</p>
            {event.entity && (
              <p className="text-xs text-gray-600 mono">{event.entity} · {event.claim_type}</p>
            )}
          </div>
        ))}

        {resolved.length > 0 && (
          <>
            <p className="text-xs text-gray-600 uppercase tracking-wider mt-1">Resolved</p>
            {resolved.map((event) => (
              <div key={event.id} className="border-l-2 border-l-green-800 bg-green-900/10 rounded-r-lg px-3 py-2 flex flex-col gap-1 opacity-60">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs">✓</span>
                  <span className="text-xs text-gray-500">{event.type.replace("_", " ")}</span>
                </div>
                <p className="text-xs text-gray-500 leading-relaxed">{event.description}</p>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
