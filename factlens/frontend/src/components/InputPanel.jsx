import { LoaderCircle, Search, Zap } from "lucide-react";

function InputPanel({
  inputMode,
  setInputMode,
  inputValue,
  setInputValue,
  onSubmit,
  isLoading,
}) {
  return (
    <section className="glass-card-static overflow-hidden rounded-[2rem] animate-fade-in-up gradient-border">
      <header className="border-b border-white/6 bg-gradient-to-r from-slate-900/80 to-slate-950/80 px-4 py-4 sm:px-6 sm:py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 text-blue-300 ring-1 ring-inset ring-blue-400/20">
              <Search className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <p className="font-display text-2xl leading-none text-white sm:text-3xl">FactLens</p>
              <p className="mt-1 hidden text-sm text-slate-400 sm:block">
                Inspect claims, search the web, and score credibility in one pass.
              </p>
            </div>
          </div>
          <div className="hidden glass-pill rounded-full px-3 py-1.5 text-xs font-medium uppercase tracking-[0.24em] text-slate-400 md:block">
            Verification pipeline
          </div>
        </div>
      </header>

      <div className="space-y-5 px-4 py-5 sm:px-6 sm:py-6">
        <div className="inline-flex rounded-full border border-white/8 bg-white/4 p-1">
          {["text", "url"].map((mode) => {
            const selected = inputMode === mode;
            return (
              <button
                key={mode}
                type="button"
                onClick={() => setInputMode(mode)}
                disabled={isLoading}
                className={`rounded-full px-5 py-2 text-sm font-medium transition-all duration-300 ${
                  selected
                    ? "bg-gradient-to-r from-blue-500 to-blue-400 text-white shadow-lg shadow-blue-900/30"
                    : "text-slate-400 hover:text-white"
                } ${isLoading ? "cursor-not-allowed opacity-60" : ""}`}
              >
                {mode === "text" ? "Paste Text" : "Enter URL"}
              </button>
            );
          })}
        </div>

        {inputMode === "text" ? (
          <textarea
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            disabled={isLoading}
            rows={10}
            placeholder="Paste an article, transcript, or social post to extract and verify its claims."
            className="min-h-48 w-full rounded-[1.5rem] border border-white/8 bg-slate-950/40 px-4 py-4 text-sm leading-7 text-white outline-none transition-all duration-300 placeholder:text-slate-500 focus:border-blue-400/30 focus:bg-slate-950/60 sm:min-h-72 sm:px-5 disabled:cursor-not-allowed disabled:opacity-60"
          />
        ) : (
          <input
            type="url"
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            disabled={isLoading}
            placeholder="https://example.com/article"
            className="w-full rounded-[1.5rem] border border-white/8 bg-slate-950/40 px-4 py-4 text-sm text-white outline-none transition-all duration-300 placeholder:text-slate-500 focus:border-blue-400/30 focus:bg-slate-950/60 sm:px-5 disabled:cursor-not-allowed disabled:opacity-60"
          />
        )}

        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-2xl text-sm text-slate-400">
            Extracts atomic claims, gathers sources, and explains how each verdict was reached.
          </p>

          <button
            type="button"
            onClick={onSubmit}
            disabled={isLoading || !inputValue.trim()}
            className="btn-shimmer inline-flex w-full items-center justify-center gap-2 rounded-full bg-gradient-to-r from-blue-500 to-blue-400 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-600/25 transition-all duration-300 hover:shadow-xl hover:shadow-blue-500/30 hover:scale-[1.03] sm:w-auto sm:min-w-56 disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:scale-100"
          >
            {isLoading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
            {isLoading ? "Analyzing..." : "Verify with FactLens"}
          </button>
        </div>
      </div>
    </section>
  );
}

export default InputPanel;
