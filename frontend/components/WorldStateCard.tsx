import clsx from "clsx";
import type { WorldStateEntry, WorldStateStatus, EntityType } from "@/lib/types";

const ENTITY_ICONS: Record<EntityType, string> = {
  fire: "🔥",
  evacuation_zone: "🚨",
  road: "🛣",
  shelter: "🏠",
  weather: "🌬",
  utility: "⚡",
  flood: "🌊",
};

const STATUS_STYLES: Record<WorldStateStatus, string> = {
  confirmed: "bg-green-900/30 border-green-800/50 text-green-400",
  low_confidence: "bg-yellow-900/30 border-yellow-800/50 text-yellow-400",
  unresolved: "bg-orange-900/30 border-orange-800/50 text-orange-400",
  conflicted: "bg-red-900/30 border-red-800/50 text-red-400",
  stale: "bg-gray-800/50 border-gray-700/50 text-gray-500",
};

const STATUS_DOT: Record<WorldStateStatus, string> = {
  confirmed: "bg-green-500",
  low_confidence: "bg-yellow-500",
  unresolved: "bg-orange-500",
  conflicted: "bg-red-500 animate-pulse",
  stale: "bg-gray-600",
};

interface Props {
  entry: WorldStateEntry;
}

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function WorldStateCard({ entry }: Props) {
  return (
    <div
      className={clsx(
        "rounded-xl border p-4 flex flex-col gap-2 transition-all",
        STATUS_STYLES[entry.status]
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{ENTITY_ICONS[entry.entity_type] ?? "❓"}</span>
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            {entry.entity_type.replace("_", " ")}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className={clsx("w-2 h-2 rounded-full", STATUS_DOT[entry.status])} />
          <span className="text-xs capitalize">{entry.status.replace("_", " ")}</span>
        </div>
      </div>

      <div>
        <p className="text-sm font-medium text-gray-300 truncate">{entry.entity}</p>
        <p className="text-xs text-gray-500">{entry.claim_type.replace(/_/g, " ")}</p>
      </div>

      <p className="text-base font-semibold text-white capitalize">{entry.current_value}</p>

      <div className="flex items-center justify-between text-xs text-gray-600">
        <span className="mono">{(entry.confidence * 100).toFixed(0)}% conf</span>
        <span>{timeAgo(entry.last_updated)}</span>
      </div>

      {entry.status === "conflicted" && (
        <p className="text-xs text-red-400 bg-red-900/20 rounded px-2 py-1">
          Conflict detected — Healing Loop active
        </p>
      )}
    </div>
  );
}
