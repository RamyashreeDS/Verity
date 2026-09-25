"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { WorldStateEntry, HealthEvent, ApiStatus } from "@/lib/types";
import CrisisQuery from "@/components/CrisisQuery";
import PipelineStatus from "@/components/PipelineStatus";
import WorldStateCard from "@/components/WorldStateCard";
import HealthEvents from "@/components/HealthEvents";

const ENTITY_TYPE_ORDER = [
  "fire", "evacuation_zone", "flood", "road", "shelter", "weather", "utility",
];

function groupByEntityType(entries: WorldStateEntry[]): Record<string, WorldStateEntry[]> {
  return entries.reduce<Record<string, WorldStateEntry[]>>((acc, entry) => {
    if (!acc[entry.entity_type]) acc[entry.entity_type] = [];
    acc[entry.entity_type].push(entry);
    return acc;
  }, {});
}

function ApiStatusDot({ label, active }: { label: string; active: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-1.5 h-1.5 rounded-full ${active ? "bg-green-500" : "bg-gray-600"}`} />
      <span className="text-xs text-gray-500">{label}</span>
    </div>
  );
}

export default function HomePage() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [entries, setEntries] = useState<WorldStateEntry[]>([]);
  const [healthEvents, setHealthEvents] = useState<HealthEvent[]>([]);
  const [apiStatus, setApiStatus] = useState<ApiStatus | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [visualUrl, setVisualUrl] = useState<string | null>(null);
  const [generatingVisual, setGeneratingVisual] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [dash, health] = await Promise.all([
        api.dashboard(),
        api.healthEvents(false),
      ]);
      setEntries(dash.entries);
      setLastUpdated(dash.last_updated ?? null);
      setHealthEvents(health.events);
    } catch {}
  }, []);

  useEffect(() => {
    api.status().then(setApiStatus).catch(() => {});
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  async function handleGenerateVisual() {
    setGeneratingVisual(true);
    try {
      const result = await api.generateVisual();
      setVisualUrl(result.image_url);
    } catch {}
    setGeneratingVisual(false);
  }

  const grouped = groupByEntityType(entries);
  const openEventCount = healthEvents.filter((e) => !e.resolved).length;

  return (
    <div className="min-h-screen bg-[#0a0f1e] text-gray-200">
      {/* Header */}
      <header className="border-b border-[#1f2937] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-orange-500 text-xl font-bold tracking-tight">VERITY</span>
          <span className="text-gray-600 text-sm">crisis monitor</span>
        </div>
        <div className="flex items-center gap-4">
          {apiStatus && (
            <div className="flex items-center gap-3">
              <ApiStatusDot label="Nimble" active={apiStatus.nimble} />
              <ApiStatusDot label="Liquid AI" active={apiStatus.liquid_ai} />
              <ApiStatusDot label="Tinybird" active={apiStatus.tinybird} />
              <ApiStatusDot label="BFL" active={apiStatus.bfl} />
            </div>
          )}
          {lastUpdated && (
            <span className="text-xs text-gray-600 mono">
              updated {new Date(lastUpdated).toLocaleTimeString()}
            </span>
          )}
          {openEventCount > 0 && (
            <span className="text-xs bg-red-900/50 text-red-400 px-2 py-1 rounded-full animate-pulse">
              {openEventCount} health alert{openEventCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 flex flex-col gap-6">
        {/* Query + Pipeline */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <CrisisQuery onRunStarted={(id) => { setActiveRunId(id); setTimeout(refresh, 3000); }} />
          <PipelineStatus runId={activeRunId} />
        </div>

        {/* Main content grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* World State */}
          <div className="lg:col-span-2 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">
                World State
              </h2>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-600">{entries.length} tracked facts</span>
                {apiStatus?.bfl && (
                  <button
                    onClick={handleGenerateVisual}
                    disabled={generatingVisual || entries.length === 0}
                    className="text-xs px-3 py-1.5 bg-[#1f2937] hover:bg-[#374151] text-gray-400 hover:text-white rounded-lg transition-colors disabled:opacity-40"
                  >
                    {generatingVisual ? "Generating…" : "Generate Visual"}
                  </button>
                )}
              </div>
            </div>

            {entries.length === 0 ? (
              <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-12 text-center">
                <p className="text-gray-600 text-sm">No data yet — run the pipeline to start monitoring</p>
              </div>
            ) : (
              ENTITY_TYPE_ORDER.filter((t) => grouped[t]).map((entityType) => (
                <div key={entityType}>
                  <p className="text-xs text-gray-600 uppercase tracking-wider mb-2">
                    {entityType.replace("_", " ")}
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {grouped[entityType].map((entry) => (
                      <WorldStateCard
                        key={`${entry.entity}-${entry.claim_type}`}
                        entry={entry}
                      />
                    ))}
                  </div>
                </div>
              ))
            )}

            {/* FLUX visual */}
            {visualUrl && (
              <div className="bg-[#111827] border border-[#1f2937] rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-[#1f2937]">
                  <p className="text-xs text-gray-400 uppercase tracking-widest">Situation Visual · BFL FLUX</p>
                </div>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={visualUrl} alt="Crisis situation visual" className="w-full object-cover" />
              </div>
            )}
          </div>

          {/* Health Events sidebar */}
          <div className="flex flex-col gap-4">
            <HealthEvents events={healthEvents} />

            {/* Healing stats */}
            {healthEvents.some((e) => e.resolved) && (
              <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-4">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
                  Healing Loop
                </h3>
                <div className="flex gap-4">
                  <div className="flex flex-col">
                    <span className="text-xl font-bold text-green-400">
                      {healthEvents.filter((e) => e.resolved).length}
                    </span>
                    <span className="text-xs text-gray-600">healed</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xl font-bold text-red-400">
                      {healthEvents.filter((e) => !e.resolved).length}
                    </span>
                    <span className="text-xs text-gray-600">open</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
