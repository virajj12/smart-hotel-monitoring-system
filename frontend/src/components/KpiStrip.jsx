import React from 'react';
import { 
  AlertTriangle, 
  Bug, 
  UserX, 
  ShieldCheck, 
  Grid2X2, 
  Square, 
  PanelRightClose, 
  PanelRightOpen 
} from 'lucide-react';
import { Badge } from './ui/badge';
import { Button } from './ui/button';

export default function KpiStrip({
  stats,
  amfvData,
  focusedCamId,
  onResetFocus,
  isInspectorOpen,
  onToggleInspector,
}) {
  const total = stats?.total ?? 0;
  const pest = stats?.pest ?? 0;
  const hygiene = stats?.hygiene ?? 0;
  const confirmedPests = amfvData?.confirmed || [];
  const hasActiveAlert = confirmedPests.length > 0;

  return (
    <div className="w-full flex flex-wrap items-center justify-between gap-3 px-4 py-2 mb-3 rounded-lg border border-border bg-card/90 backdrop-blur-md">
      {/* Left: Compact Metric Pills */}
      <div className="flex items-center flex-wrap gap-2 text-xs">
        {/* Total Incidents */}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800">
          <AlertTriangle className="h-3.5 w-3.5 text-zinc-400" />
          <span className="text-zinc-400 font-medium">Total:</span>
          <span className="font-bold font-mono text-white">{total}</span>
        </div>

        {/* Pest Incursions */}
        <div className={`flex items-center gap-2 px-2.5 py-1 rounded-md border ${
          pest > 0 
            ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' 
            : 'bg-zinc-900 border-zinc-800 text-zinc-400'
        }`}>
          <Bug className="h-3.5 w-3.5" />
          <span className="font-medium">Pests:</span>
          <span className={`font-bold font-mono ${pest > 0 ? 'text-rose-400' : 'text-white'}`}>{pest}</span>
        </div>

        {/* Hygiene Breaches */}
        <div className={`flex items-center gap-2 px-2.5 py-1 rounded-md border ${
          hygiene > 0 
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-300' 
            : 'bg-zinc-900 border-zinc-800 text-zinc-400'
        }`}>
          <UserX className="h-3.5 w-3.5" />
          <span className="font-medium">Hygiene:</span>
          <span className={`font-bold font-mono ${hygiene > 0 ? 'text-amber-300' : 'text-white'}`}>{hygiene}</span>
        </div>

        {/* AMFV Consensus Status */}
        <div className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-400">
          <ShieldCheck className={`h-3.5 w-3.5 ${hasActiveAlert ? 'text-rose-400' : 'text-emerald-400'}`} />
          <span className="font-medium">AMFV Consensus:</span>
          <span className={`font-mono font-semibold ${hasActiveAlert ? 'text-rose-400 animate-pulse' : 'text-emerald-400'}`}>
            {hasActiveAlert ? 'BREACH DETECTED' : 'NORMAL (W=10)'}
          </span>
        </div>
      </div>

      {/* Right: Layout Switchers & Inspector Toggle */}
      <div className="flex items-center gap-1.5">
        {/* Focus Mode Indicator / Reset */}
        {focusedCamId && (
          <Button
            variant="outline"
            size="sm"
            onClick={onResetFocus}
            className="h-7 px-2 text-[11px] text-zinc-300 hover:text-white border-zinc-700 hover:bg-zinc-800 gap-1"
          >
            <Grid2X2 className="h-3 w-3" />
            <span>Restore Grid</span>
          </Button>
        )}

        {/* Toggle Inspector Drawer */}
        <Button
          variant="outline"
          size="sm"
          onClick={onToggleInspector}
          className="h-7 px-2.5 text-[11px] text-zinc-300 hover:text-white border-zinc-800 hover:bg-zinc-800 gap-1.5"
          title={isInspectorOpen ? "Collapse Inspector for Full-Width Video" : "Expand Inspector Panel"}
        >
          {isInspectorOpen ? (
            <>
              <PanelRightClose className="h-3.5 w-3.5 text-zinc-400" />
              <span className="hidden md:inline">Collapse Panel</span>
            </>
          ) : (
            <>
              <PanelRightOpen className="h-3.5 w-3.5 text-zinc-400" />
              <span>Show Panel</span>
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

