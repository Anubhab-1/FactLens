import { Globe, MonitorSmartphone, ShieldAlert, Youtube, Zap } from "lucide-react";

const MODE_META = {
  http: {
    label: "Direct Capture",
    tone: "text-blue-400 border-blue-500/20 bg-blue-500/5",
    Icon: Globe,
  },
  browser: {
    label: "Browser Render",
    tone: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
    Icon: MonitorSmartphone,
  },
  unknown: {
    label: "Unknown Mode",
    tone: "text-neutral-500 border-white/10 bg-white/5",
    Icon: ShieldAlert,
  },
  youtube: {
    label: "YouTube Extract",
    tone: "text-rose-400 border-rose-500/20 bg-rose-500/5",
    Icon: Youtube,
  },
};

function SourceCapturePanel({ sourceCapture, inputMode }) {
  const isYoutube = inputMode === "youtube";
  if (!isYoutube && (inputMode !== "url" || !sourceCapture)) return null;

  const mode = isYoutube ? "youtube" : (sourceCapture?.mode || "unknown");
  const meta = MODE_META[mode] || MODE_META.unknown;
  const Icon = meta.Icon;

  return (
    <div className="animate-fade-in-up">
      <div className={`glass-card-static flex flex-wrap items-center justify-between gap-4 border px-6 py-4 rounded-2xl ${meta.tone}`}>
        <div className="flex items-center gap-3">
           <Icon className="h-4 w-4" />
           <div className="flex flex-col">
              <span className="text-[10px] font-bold uppercase tracking-widest opacity-60">Source Method</span>
              <span className="text-sm font-semibold">{meta.label}</span>
           </div>
        </div>

        <div className="flex flex-wrap items-center gap-6">
           <div className="flex flex-col">
              <span className="text-[10px] font-bold uppercase tracking-widest opacity-60">Engine</span>
              <span className="text-sm font-semibold text-white">FactLens Core v2</span>
           </div>
           {!isYoutube && sourceCapture && (
             <>
               <div className="flex flex-col">
                  <span className="text-[10px] font-bold uppercase tracking-widest opacity-60">Content</span>
                  <span className="text-sm font-semibold text-white">{sourceCapture.text_chars || 0} chars</span>
               </div>
               <div className="flex flex-col">
                  <span className="text-[10px] font-bold uppercase tracking-widest opacity-60">Media</span>
                  <span className="text-sm font-semibold text-white">{sourceCapture.media_count || 0} units</span>
               </div>
             </>
           )}
           {isYoutube && (
             <div className="flex flex-col">
                <span className="text-[10px] font-bold uppercase tracking-widest opacity-60">Mode</span>
                <span className="text-sm font-semibold text-white">Transcript Sync</span>
             </div>
           )}
        </div>

        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[9px] font-bold uppercase tracking-widest text-neutral-400">
           <Zap className="h-3 w-3 fill-current" />
           Optimized
        </div>
      </div>
      
      {!isYoutube && sourceCapture?.fallback_used && (
        <p className="mt-3 text-[11px] font-medium text-amber-400/80 px-2 italic">
           * Note: Headless browser fallback was triggered for full content fidelity.
        </p>
      )}
    </div>
  );
}

export default SourceCapturePanel;
