import { useEffect, useState } from "react";
import { Sparkles, Check, Loader2 } from "lucide-react";

/**
 * Shows the pipeline's progress through each stage.
 * Stages complete as new events arrive, with animated transitions.
 */

// Defines the ordered stages and their display labels
const PIPELINE_STAGES = [
    { key: "router", label: "Understanding query", detail: "Detecting intent and expanding search terms" },
    { key: "retrieval", label: "Searching medical databases", detail: "PubMed • OpenAlex • ClinicalTrials.gov" },
    { key: "retrieved", label: "Gathering results", detail: null },
    { key: "grading", label: "Ranking relevance", detail: "BM25 pre-filter → cross-encoder reranking" },
    { key: "ranked", label: "Selecting best sources", detail: null },
    { key: "synthesis", label: "Synthesizing insights", detail: "Llama 3.3 70B" },
    { key: "validation", label: "Validating citations", detail: null },
];

export default function PipelineProgress({ currentStage, stageDetail, elapsed }) {
    // Find the index of the currently active stage
    const currentIndex = PIPELINE_STAGES.findIndex((s) => s.key === currentStage);

    return (
        <div className="flex gap-3 message-enter">
            <div className="w-7 h-7 rounded-lg bg-cura-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Sparkles className="w-3.5 h-3.5 text-cura-300" />
            </div>

            <div className="flex-1 bg-cura-900/50 border border-cura-800/50 rounded-2xl rounded-tl-md px-4 py-3.5 max-w-[85%]">
                <div className="space-y-2">
                    {PIPELINE_STAGES.map((stage, idx) => {
                        const isComplete = currentIndex > idx || currentStage === "complete";
                        const isActive = currentIndex === idx;
                        const isUpcoming = currentIndex < idx && currentStage !== "complete";

                        return (
                            <div
                                key={stage.key}
                                className="flex items-start gap-2.5 transition-opacity duration-300"
                                style={{ opacity: isUpcoming ? 0.35 : 1 }}
                            >
                                {/* Status icon */}
                                <div className="flex-shrink-0 w-4 h-4 mt-0.5 flex items-center justify-center">
                                    {isComplete ? (
                                        <Check className="w-3.5 h-3.5 text-cura-400" />
                                    ) : isActive ? (
                                        <Loader2 className="w-3.5 h-3.5 text-cura-300 animate-spin" />
                                    ) : (
                                        <div className="w-1.5 h-1.5 rounded-full bg-cura-700" />
                                    )}
                                </div>

                                {/* Label + detail */}
                                <div className="flex-1 min-w-0">
                                    <div
                                        className={`text-xs leading-snug transition-colors ${isActive
                                            ? "text-cura-100 font-medium"
                                            : isComplete
                                                ? "text-cura-400"
                                                : "text-cura-600"
                                            }`}
                                    >
                                        {stage.label}
                                    </div>

                                    {/* Detail text — show custom detail if active, else default */}
                                    {isActive && (stageDetail || stage.detail) && (
                                        <div className="text-[11px] text-cura-500 mt-0.5 leading-snug">
                                            {stageDetail || stage.detail}
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>

                {/* Elapsed time at the bottom */}
                {elapsed > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-cura-800/40 text-[10px] text-cura-600">
                        {elapsed.toFixed(1)}s elapsed
                    </div>
                )}
            </div>
        </div>
    );
}