import React, { useState } from 'react';
import { 
  FileText, 
  ShieldAlert, 
  Camera, 
  FileSpreadsheet, 
  Trash2, 
  ShieldCheck, 
  Plus, 
  Activity, 
  ExternalLink 
} from 'lucide-react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Progress } from './ui/progress';

const LABEL_MAP = {
  cockroach: '🪳 Cockroach Incursion',
  lizard: '🦎 Lizard Detected',
  rat: '🐀 Rat Sighting',
  no_apron: '🧥 Missing Apron',
  no_gloves: '🧤 Missing Gloves',
  no_hairnet: '👒 Missing Hairnet',
};

const PESTS = ['cockroach', 'lizard', 'rat'];

const VIOLATIONS_CONFIG = {
  pests: [
    { id: 'cockroach', label: 'Cockroach', icon: '🪳' },
    { id: 'lizard', label: 'Lizard', icon: '🦎' },
    { id: 'rat', label: 'Rat', icon: '🐀' },
  ],
  hygiene: [
    { id: 'no_apron', label: 'No Apron', icon: '🧥' },
    { id: 'no_gloves', label: 'No Gloves', icon: '🧤' },
    { id: 'no_hairnet', label: 'No Hairnet', icon: '👒' },
  ],
};

export default function InspectorDock({
  logs = [],
  amfvData = {},
  cameras = [],
  selectedCameraId,
  onSelectCamera,
  onClearLogs,
  onExportCsv,
  onViewSnapshot,
  onOpenAddCamera,
}) {
  const [activeTab, setActiveTab] = useState('logs');
  const [logFilter, setLogFilter] = useState('all');

  // Filter logs
  const filteredLogs = logs.filter((log) => {
    const isPest = PESTS.includes(log.class || log.label);
    if (logFilter === 'pests') return isPest;
    if (logFilter === 'hygiene') return !isPest;
    return true;
  });

  // AMFV computations
  const windowSize = amfvData?.window_size ?? 10;
  const ratios = amfvData?.ratios || {};
  const confirmedList = amfvData?.confirmed || [];
  const thresholds = amfvData?.thresholds || {};

  const renderAmfvRow = (item) => {
    const ratio = ratios[item.id] ?? 0;
    const threshold = thresholds[item.id] ?? (item.id.includes('no_') ? 0.45 : 0.35);
    const isConfirmed = confirmedList.includes(item.id);

    const pct = Math.min(100, Math.round(ratio * 100));
    const thrPct = Math.round(threshold * 100);

    let indicatorColor = "bg-zinc-500";
    if (isConfirmed) {
      indicatorColor = "bg-rose-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]";
    } else if (pct >= thrPct * 0.7) {
      indicatorColor = "bg-amber-400";
    }

    return (
      <div key={item.id} className="space-y-1.5 p-2 rounded-md bg-zinc-900/60 border border-zinc-800/80 mb-2">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 font-medium">
            <span className="text-sm">{item.icon}</span>
            <span className={isConfirmed ? "text-rose-400 font-bold" : "text-zinc-200"}>
              {item.label}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className={`font-mono text-[11px] ${isConfirmed ? 'text-rose-400 font-bold' : 'text-zinc-400'}`}>
              {pct}% <span className="text-zinc-600">/</span> {thrPct}%
            </span>
            {isConfirmed && (
              <Badge variant="destructive" className="h-4 px-1 py-0 text-[8px] font-bold uppercase animate-pulse">
                ALERT
              </Badge>
            )}
          </div>
        </div>

        <div className="relative pt-0.5">
          <Progress value={pct} indicatorClassName={indicatorColor} className="h-1.5 bg-zinc-800" />
          <div
            className="absolute top-0.5 bottom-0 w-0.5 bg-white/60 z-10"
            style={{ left: `${thrPct}%` }}
            title={`Threshold: ${thrPct}%`}
          />
        </div>
      </div>
    );
  };

  return (
    <Card className="flex flex-col h-[calc(100vh-140px)] min-h-[500px] bg-card border-border overflow-hidden shadow-lg">
      {/* ── TOP TAB NAVIGATION ─────────────────────────────────────────── */}
      <div className="p-2 border-b border-border bg-zinc-900/80 shrink-0">
        <div className="grid grid-cols-3 gap-1 bg-zinc-950/80 p-1 rounded-lg border border-zinc-800">
          <button
            onClick={() => setActiveTab('logs')}
            className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-semibold transition-all ${
              activeTab === 'logs'
                ? 'bg-white text-zinc-950 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
            }`}
          >
            <FileText className="h-3.5 w-3.5" />
            <span>Logs</span>
            {logs.length > 0 && (
              <span className={`ml-0.5 px-1.5 py-0 text-[10px] font-mono rounded-full ${
                activeTab === 'logs' ? 'bg-zinc-200 text-zinc-950' : 'bg-zinc-800 text-zinc-300'
              }`}>
                {logs.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('amfv')}
            className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-semibold transition-all ${
              activeTab === 'amfv'
                ? 'bg-white text-zinc-950 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
            }`}
          >
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>AMFV</span>
            {confirmedList.length > 0 && (
              <span className="h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
            )}
          </button>

          <button
            onClick={() => setActiveTab('cameras')}
            className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-md text-xs font-semibold transition-all ${
              activeTab === 'cameras'
                ? 'bg-white text-zinc-950 shadow-sm'
                : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
            }`}
          >
            <Camera className="h-3.5 w-3.5" />
            <span>Cameras</span>
            <span className={`ml-0.5 px-1 py-0 text-[10px] font-mono rounded ${
              activeTab === 'cameras' ? 'bg-zinc-200 text-zinc-950' : 'bg-zinc-800 text-zinc-400'
            }`}>
              {cameras.length}
            </span>
          </button>
        </div>
      </div>

      {/* ── TAB 1: INCIDENT LOGS ─────────────────────────────────────────── */}
      {activeTab === 'logs' && (
        <div className="flex-1 flex flex-col p-3 min-h-0 overflow-hidden">
          {/* Controls Bar */}
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/70 shrink-0">
            {/* Filter Pills */}
            <div className="flex items-center gap-1 bg-zinc-900 p-0.5 rounded-md border border-zinc-800">
              {['all', 'pests', 'hygiene'].map((f) => (
                <button
                  key={f}
                  onClick={() => setLogFilter(f)}
                  className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                    logFilter === f
                      ? 'bg-zinc-700 text-white shadow-xs'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={onExportCsv}
                className="h-6 px-2 text-[10px] text-zinc-300 hover:text-white border-zinc-800 hover:bg-zinc-800 gap-1"
                title="Download CSV report"
              >
                <FileSpreadsheet className="h-3 w-3 text-zinc-400" />
                <span>CSV</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={onClearLogs}
                className="h-6 px-2 text-[10px] text-rose-400 hover:text-rose-300 border-zinc-800 hover:bg-zinc-800 gap-1"
                title="Clear Logs"
              >
                <Trash2 className="h-3 w-3" />
                <span>Clear</span>
              </Button>
            </div>
          </div>

          {/* Scrollable Log Entries */}
          <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
            {filteredLogs.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center text-zinc-500 py-12">
                <ShieldCheck className="h-9 w-9 text-zinc-600 mb-2" />
                <div className="text-xs font-semibold text-zinc-300">No Incidents Recorded</div>
                <div className="text-[11px] text-zinc-500 max-w-[200px] mt-0.5">
                  Surveillance stream is active. AMFV consensus verifying all frames.
                </div>
              </div>
            ) : (
              filteredLogs.map((log, idx) => {
                const rawLabel = log.class || log.label || 'violation';
                const isPest = PESTS.includes(rawLabel);
                const title = LABEL_MAP[rawLabel] || rawLabel;
                const camName = log.camera_name || log.camera_id || 'Kitchen';
                const snapshot = log.snapshot || log.snapshot_path;
                const snapshotUrl = snapshot ? (snapshot.startsWith('/') ? snapshot : `/snapshots/${snapshot}`) : null;

                return (
                  <div
                    key={log.id || `${log.timestamp}-${idx}`}
                    className="flex items-center gap-2 p-2 rounded-md border border-zinc-800 bg-zinc-900/60 hover:bg-zinc-800/60 transition-colors"
                  >
                    <span className={`h-2 w-2 rounded-full shrink-0 ${isPest ? 'bg-rose-500' : 'bg-amber-400'}`} />

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-medium text-white truncate">
                          {title}
                        </span>
                        {(log.amfv_verified || log.verified) && (
                          <Badge variant="outline" className="h-3.5 px-1 py-0 text-[8px] font-mono text-emerald-400 border-emerald-500/30 bg-emerald-500/10">
                            ✓ AMFV
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 text-[10px] text-zinc-400 mt-0.5">
                        <span className="truncate max-w-[90px]">📹 {camName}</span>
                        <span className="text-zinc-600">•</span>
                        <span>{log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : 'Recent'}</span>
                        {log.confidence > 0 && (
                          <>
                            <span className="text-zinc-600">•</span>
                            <span className="text-zinc-300 font-mono">{Math.round(log.confidence * 100)}%</span>
                          </>
                        )}
                      </div>
                    </div>

                    {snapshotUrl && (
                      <div
                        className="h-8 w-11 rounded overflow-hidden border border-zinc-700/60 cursor-pointer shrink-0 hover:opacity-80 transition-opacity"
                        onClick={() => onViewSnapshot(snapshotUrl)}
                        title="Click to view evidence snapshot"
                      >
                        <img
                          src={snapshotUrl}
                          alt="Violation Evidence"
                          className="h-full w-full object-cover"
                          onError={(e) => { e.currentTarget.style.display = 'none'; }}
                        />
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* ── TAB 2: AMFV TELEMETRY ───────────────────────────────────────── */}
      {activeTab === 'amfv' && (
        <div className="flex-1 flex flex-col p-3 min-h-0 overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between pb-2 mb-3 border-b border-border/70 shrink-0">
            <div>
              <div className="text-xs font-bold text-white">Temporal Frame Voting</div>
              <div className="text-[10px] text-zinc-400">Rolling Consensus: {windowSize} frames (~0.6s)</div>
            </div>
            <Badge variant="outline" className="text-[9px] uppercase font-mono tracking-wider text-emerald-400 border-emerald-500/30 bg-emerald-500/10">
              ACTIVE
            </Badge>
          </div>

          {/* Sliders List */}
          <div className="space-y-3.5">
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 mb-1.5">
                Pest Incursion Thresholds
              </div>
              {VIOLATIONS_CONFIG.pests.map(renderAmfvRow)}
            </div>

            <div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-400 mb-1.5">
                Hygiene Compliance Thresholds
              </div>
              {VIOLATIONS_CONFIG.hygiene.map(renderAmfvRow)}
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 3: CAMERA FEEDS MANAGER ─────────────────────────────────── */}
      {activeTab === 'cameras' && (
        <div className="flex-1 flex flex-col p-3 min-h-0 overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between pb-2 mb-3 border-b border-border/70 shrink-0">
            <div>
              <div className="text-xs font-bold text-white">Surveillance Feeds</div>
              <div className="text-[10px] text-zinc-400">{cameras.length} camera stream{cameras.length === 1 ? '' : 's'} registered</div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={onOpenAddCamera}
              className="h-6 px-2 text-[10px] text-zinc-300 hover:text-white border-zinc-700 hover:bg-zinc-800 gap-1"
            >
              <Plus className="h-3 w-3" />
              <span>Add Stream</span>
            </Button>
          </div>

          <div className="space-y-2">
            {/* Merged View Pill */}
            <div
              onClick={() => onSelectCamera(null)}
              className={`flex items-center justify-between p-2.5 rounded-md border cursor-pointer transition-colors ${
                selectedCameraId === null
                  ? 'border-white bg-zinc-800 text-white shadow-sm'
                  : 'border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:bg-zinc-800/60'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_5px_rgba(52,211,153,0.8)]" />
                <span className="text-xs font-semibold">All Cameras (Merged)</span>
              </div>
              <span className="text-[10px] font-mono text-zinc-400">Default View</span>
            </div>

            {/* Individual Feeds */}
            {cameras.map((cam) => {
              const isSelected = selectedCameraId === cam.id;
              const isOnline = cam.connected ?? (cam.status === 'online');

              return (
                <div
                  key={cam.id}
                  onClick={() => onSelectCamera(cam.id)}
                  className={`flex items-center justify-between p-2.5 rounded-md border cursor-pointer transition-colors ${
                    isSelected
                      ? 'border-white bg-zinc-800 text-white shadow-sm'
                      : 'border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:bg-zinc-800/60'
                  }`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 rounded-full ${isOnline ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
                      <span className="text-xs font-semibold text-white">{cam.name}</span>
                    </div>
                    <div className="text-[10px] text-zinc-400 mt-0.5">
                      {cam.location || 'Kitchen'} · {cam.source_type?.toUpperCase() || 'RTSP'}
                    </div>
                  </div>

                  <div className="text-right">
                    <Badge variant="outline" className={`h-4 text-[9px] font-mono ${isOnline ? 'text-emerald-400 border-emerald-500/30' : 'text-zinc-500 border-zinc-800'}`}>
                      {isOnline ? 'ONLINE' : 'OFFLINE'}
                    </Badge>
                    {cam.fps != null && (
                      <div className="text-[10px] font-mono text-zinc-400 mt-0.5">{cam.fps} FPS</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
}
