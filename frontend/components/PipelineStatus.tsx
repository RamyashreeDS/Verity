"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PipelineRun } from "@/lib/types";
import clsx from "clsx";

const STAGES = ["sense", "understand", "validate", "world_state", "health_monitor", "healing_loop"];
const STAGE_LABELS: Record<string, string> = {
  sense: "Sense",
  understand: "Understand",
  validate: "Validate",
  world_state: "World State",
  health_monitor: "Health Monitor",
  healing_loop: "Healing Loop",
};

interface Props {
  runId: string | null;
}

export default function PipelineStatus({ runId }: Props) {
  const [run, setRun] = useState<PipelineRun | null>(null);

  useEffect(() => {
    if (!runId) return;
    const poll = async () => {
      try {
        const data = await api.getPipelineRun(runId);
        setRun(data);
        if (data.status === "running" || data.status === "pending") {
          setTimeout(poll, 1500);
        }
      } catch {}
    };
    poll();
  }, [runId]);

  if (!run) return null;

  const stageMap = Object.fromEntries(run.stages.map((s) => [s.stage, s]));

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">Pipeline</h2>
        <span
          className={clsx("text-xs px-2.5 py-1 rounded-full font-mono", {
            "bg-yellow-900/40 text-yellow-400": run.status === "running" || run.status === "pending",
            "bg-green-900/40 text-green-400": run.status === "completed",
            "bg-red-900/40 text-red-400": run.status === "failed",
          })}
        >
          {run.status}
        </span>
      </div>

      <div className="flex items-center gap-1">
        {STAGES.map((stage, i) => {
          const s = stageMap[stage];
          const status = s?.status ?? "pending";
          return (
            <div key={stage} className="flex-1 flex flex-col items-center gap-1.5">
              <div
                className={clsx("w-full h-1.5 rounded-full transition-all duration-500", {
                  "bg-orange-500": status === "done",
                  "bg-yellow-500 animate-pulse": status === "running",
                  "bg-red-500": status === "failed",
                  "bg-[#374151]": status === "pending",
                })}
              />
              <span className="text-[10px] text-gray-500 text-center leading-tight">
                {STAGE_LABELS[stage]}
              </span>
              {s && status === "done" && (
                <span className="text-[10px] text-gray-500 mono">{s.count}</span>
              )}
            </div>
          );
        })}
      </div>

      {run.error && (
        <p className="mt-3 text-red-400 text-xs mono">{run.error}</p>
      )}
    </div>
  );
}
