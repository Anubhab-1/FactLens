import { useEffect } from "react";
import { FileText, Globe, LoaderCircle, Search, X, Youtube, Zap } from "lucide-react";

const INPUT_MODES = [
  { id: "text", label: "Text",    Icon: FileText },
  { id: "url",  label: "URL",     Icon: Globe    },
];

const CHAR_LIMIT = 15000;

function InputPanel({
  inputMode, setInputMode,
  inputValue, setInputValue,
  onSubmit, onReviewClaims,
  isLoading, isReviewLoading,
}) {
  const isBusy  = isLoading || isReviewLoading;
  const charLen = inputValue.length;
  const nearLimit = charLen > 14000;
  const overLimit = charLen >= CHAR_LIMIT;
  const isYoutube =
    inputMode === "url" &&
    (inputValue.includes("youtube.com") || inputValue.includes("youtu.be"));

  // Ctrl/Cmd + Enter shortcut
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !isBusy && inputValue.trim()) {
        e.preventDefault();
        onSubmit();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isBusy, inputValue, onSubmit]);

  return (
    <div className="glass-card-static overflow-hidden animate-fade-in-up">

      {/* ── Mode tabs ───────────────────────────────────────── */}
      <div
        className="flex items-center gap-1 border-b px-4 py-2.5"
        style={{ borderColor: "var(--border-faint)" }}
      >
        {INPUT_MODES.map(({ id, label, Icon }) => {
          const active = inputMode === id;
          return (
            <button
              key={id}
              type="button"
              disabled={isBusy}
              onClick={() => setInputMode(id)}
              className={`flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all duration-200 ${
                active
                  ? "bg-white/8 text-white"
                  : "text-white/30 hover:bg-white/4 hover:text-white/70"
              } disabled:opacity-40`}
            >
              <Icon className="h-3.5 w-3.5 shrink-0" />
              {label}
            </button>
          );
        })}

        {isYoutube && (
          <span className="ml-auto flex items-center gap-1.5 rounded-full bg-rose-500/10 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-rose-400 ring-1 ring-inset ring-rose-500/20 animate-fade-in">
            <Youtube className="h-3 w-3 shrink-0" />
            YouTube
          </span>
        )}
      </div>

      {/* ── Input area ──────────────────────────────────────── */}
      <div className="relative group/input">
        {inputMode === "text" ? (
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            disabled={isBusy}
            rows={9}
            placeholder="Paste an article, transcript, or social post to extract and verify its claims."
            className="w-full resize-none px-5 py-5 text-[15px] leading-relaxed text-white placeholder:text-white/20 focus:outline-none sm:px-7 sm:py-6 disabled:opacity-50"
          />
        ) : (
          <input
            type="url"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            disabled={isBusy}
            placeholder="https://example.com/article"
            className="w-full px-5 py-6 text-[15px] text-white placeholder:text-white/20 focus:outline-none sm:px-7 disabled:opacity-50"
          />
        )}

        {inputValue && !isBusy && (
          <button
            type="button"
            onClick={() => setInputValue("")}
            className="absolute top-4 right-4 flex h-8 w-8 items-center justify-center rounded-xl bg-white/5 text-white/40 opacity-0 transition-all hover:bg-white/10 hover:text-white group-hover/input:opacity-100 sm:top-5 sm:right-5"
            title="Clear input"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* ── Footer ──────────────────────────────────────────── */}
      <div
        className="flex flex-col gap-3 border-t px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7"
        style={{ borderColor: "var(--border-faint)" }}
      >
        {/* Char counter */}
        <span
          className="font-mono text-xs tabular-nums"
          style={{
            color: overLimit
              ? "var(--rose)"
              : nearLimit
              ? "var(--amber)"
              : "var(--ink-3)",
          }}
        >
          {charLen.toLocaleString()} / {CHAR_LIMIT.toLocaleString()}
        </span>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onReviewClaims}
            disabled={isBusy || !inputValue.trim()}
            className="btn-secondary text-xs"
          >
            {isReviewLoading ? (
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Search className="h-3.5 w-3.5" />
            )}
            Review claims first
          </button>

          <button
            type="button"
            onClick={onSubmit}
            disabled={isBusy || !inputValue.trim() || overLimit}
            className="btn-primary btn-shimmer text-xs"
          >
            {isLoading ? (
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Zap className="h-3.5 w-3.5 fill-current" />
            )}
            Verify now
          </button>
        </div>
      </div>

      {/* Keyboard hint */}
      <p
        className="border-t px-5 py-2.5 text-center font-mono text-[10px]"
        style={{ borderColor: "var(--border-faint)", color: "var(--ink-3)" }}
      >
        {isYoutube
          ? "FactLens will transcribe the video audio automatically."
          : <>Press <kbd className="rounded-md bg-white/6 px-1.5 py-0.5">Ctrl+Enter</kbd> to verify instantly.</>
        }
      </p>
    </div>
  );
}

export default InputPanel;
