"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { EventType } from "@/lib/types";

const EVENT_TYPES: { value: EventType; label: string; icon: string }[] = [
  { value: "wildfire", label: "Wildfire", icon: "🔥" },
  { value: "flood", label: "Flood", icon: "🌊" },
  { value: "earthquake", label: "Earthquake", icon: "🏚" },
  { value: "hurricane", label: "Hurricane", icon: "🌀" },
  { value: "accident", label: "Accident", icon: "🚨" },
];

interface Props {
  onRunStarted: (runId: string) => void;
}

export default function CrisisQuery({ onRunStarted }: Props) {
  const [eventType, setEventType] = useState<EventType>("wildfire");
  const [location, setLocation] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!location.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.startPipeline({ event_type: eventType, location: location.trim() });
      onRunStarted(result.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start pipeline");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">
        Monitor Crisis
      </h2>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex gap-2 flex-wrap">
          {EVENT_TYPES.map((et) => (
            <button
              key={et.value}
              type="button"
              onClick={() => setEventType(et.value)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                eventType === et.value
                  ? "bg-orange-500 text-white"
                  : "bg-[#1f2937] text-gray-400 hover:bg-[#374151] hover:text-white"
              }`}
            >
              {et.icon} {et.label}
            </button>
          ))}
        </div>

        <div className="flex gap-3">
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. Los Angeles County, CA"
            className="flex-1 bg-[#1f2937] border border-[#374151] rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-orange-500 transition-colors"
          />
          <button
            type="submit"
            disabled={loading || !location.trim()}
            className="px-6 py-2.5 bg-orange-500 hover:bg-orange-600 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold rounded-lg text-sm transition-colors"
          >
            {loading ? "Starting…" : "Run Pipeline"}
          </button>
        </div>

        {error && <p className="text-red-400 text-sm">{error}</p>}
      </form>
    </div>
  );
}
