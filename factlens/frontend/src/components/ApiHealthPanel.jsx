import { useEffect, useState } from "react";
import { Activity, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { API_URL } from "../lib/api";

export default function ApiHealthPanel() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/health`)
      .then(r => r.json())
      .then(data => {
        setHealth(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return null;

  const keys = health?.keys || {};
  const allOk = Object.values(keys).every(v => v);

  return (
    <div className="glass-card-static p-5 space-y-4 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <span className="label-cap">System Readiness</span>
        <Activity className={`h-3 w-3 ${allOk ? "text-emerald-400" : "text-amber-400"} animate-pulse`} />
      </div>
      
      <div className="space-y-3">
        {Object.entries(keys).map(([name, active]) => (
          <div key={name} className="flex items-center justify-between">
            <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest">{name} Protocol</span>
            {active ? (
              <CheckCircle2 className="h-3 w-3 text-emerald-500/60" />
            ) : (
              <AlertCircle className="h-3 w-3 text-rose-500/60" />
            )}
          </div>
        ))}
      </div>

      <div className={`mt-2 rounded-xl border p-3 text-center ${allOk ? "border-emerald-500/10 bg-emerald-500/5" : "border-rose-500/10 bg-rose-500/5"}`}>
        <p className={`text-[10px] font-bold uppercase tracking-tight ${allOk ? "text-emerald-400" : "text-rose-400"}`}>
          {allOk ? "All Systems Nominal" : "Limited Capability Map"}
        </p>
      </div>
    </div>
  );
}
