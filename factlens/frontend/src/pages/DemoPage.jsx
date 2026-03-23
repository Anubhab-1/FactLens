import { ArrowRight, PlayCircle, Presentation, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { sampleInputs } from "../data/sampleInputs";

function DemoPage({ onUseSample }) {
  return (
    <div className="space-y-6">
      <section className="glass-card-static rounded-[2rem] p-6 animate-fade-in-up gradient-border">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">Demo mode</p>
        <h1 className="mt-2 text-3xl font-semibold text-white">Hackathon walkthrough deck</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
          Use these scenario packs in order to walk judges from a clean verification pass into conflict,
          freshness, and live-article ambiguity. The goal is to demonstrate accuracy, explainability, and
          the claim-review workflow without improvising the story on stage.
        </p>

        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            to="/workspace"
            className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition-all duration-300 hover:scale-[1.03]"
          >
            <PlayCircle className="h-4 w-4" />
            Open workspace
          </Link>
          <Link
            to="/methodology"
            className="glass-pill inline-flex items-center gap-2 rounded-full px-5 py-3 text-sm font-medium text-slate-200 transition-all duration-300 hover:bg-white/10 hover:text-white"
          >
            <Sparkles className="h-4 w-4" />
            Review methodology
          </Link>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="grid gap-5">
          {sampleInputs.map((scenario, index) => (
            <article
              key={scenario.id}
              className={`glass-card rounded-[1.75rem] p-5 animate-fade-in-up delay-${Math.min(index + 1, 6)}`}
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-white/8 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300">
                      Step {index + 1}
                    </span>
                    <span className="glass-pill rounded-full px-3 py-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                      {scenario.mode === "url" ? "Live URL" : "Text pack"}
                    </span>
                    <span className="rounded-full bg-amber-500/12 px-3 py-1 text-xs uppercase tracking-[0.18em] text-amber-200 ring-1 ring-inset ring-amber-400/20">
                      {scenario.challenge}
                    </span>
                  </div>

                  <h2 className="mt-4 text-2xl font-semibold text-white">{scenario.label}</h2>
                  <p className="mt-3 text-sm leading-7 text-slate-400">{scenario.description}</p>
                  <p className="mt-3 text-sm leading-7 text-slate-300">{scenario.talkingPoint}</p>
                </div>

                <button
                  type="button"
                  onClick={() => onUseSample(scenario)}
                  className="btn-shimmer inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-950 transition-all duration-300 hover:bg-blue-100"
                >
                  Load scenario
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>

              {scenario.value ? (
                <div className="mt-5 rounded-[1.35rem] border border-white/6 bg-slate-950/35 p-4 text-sm leading-7 text-slate-300">
                  {scenario.value}
                </div>
              ) : (
                <div className="mt-5 rounded-[1.35rem] border border-dashed border-white/8 bg-white/3 p-4 text-sm leading-7 text-slate-400">
                  Paste a live article URL in the workspace when you are ready to demonstrate scraping, claim review, and live-source disagreement.
                </div>
              )}
            </article>
          ))}
        </div>

        <aside className="glass-card-static rounded-[1.75rem] p-5 animate-fade-in-up delay-3 xl:sticky xl:top-28 xl:self-start">
          <div className="flex items-center gap-2">
            <Presentation className="h-4 w-4 text-blue-300" />
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">10-minute arc</p>
          </div>
          <div className="mt-4 space-y-3 text-sm leading-7 text-slate-300">
            <p>1. Start with the clean truth pack to establish trust in the pipeline.</p>
            <p>2. Move to the mixed verdict pack to show multiple verdict classes in one report.</p>
            <p>3. Use the time-sensitive pack to highlight freshness warnings and recovery search.</p>
            <p>4. End with a live URL and use claim review before verification to show human control.</p>
          </div>
        </aside>
      </section>
    </div>
  );
}

export default DemoPage;
