import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, 
  BarChart3, 
  Image as ImageIcon, 
  Settings, 
  Download, 
  Plus, 
  Clock 
} from 'lucide-react';
import { Button } from './ui/button';
import { Badge } from './ui/badge';

export default function Navbar({
  systemInfo,
  onOpenAddCamera,
  onOpenAnalytics,
  onOpenGallery,
  onOpenSettings,
  onExportCsv,
}) {
  const [timeStr, setTimeStr] = useState('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeStr(
        now.toLocaleDateString('en-US', {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const onlineCams = systemInfo?.online_cameras ?? 0;
  const totalCams = systemInfo?.total_cameras ?? 0;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/90 backdrop-blur-md px-6 py-3 transition-all">
      <div className="mx-auto flex max-w-[1680px] items-center justify-between">
        {/* Brand identity - Monotonous Ash Grey & Crisp White */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-800 border border-zinc-700/80 text-white">
            <ShieldCheck className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold tracking-tight text-white">
                HOTEL SURVEILLANCE AI
              </span>
              <Badge variant="outline" className="h-4 px-1.5 py-0 text-[9px] font-mono font-medium uppercase tracking-wider text-zinc-400 border-zinc-700">
                AMFV 2.0
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
              <span className="flex items-center gap-1.5 font-medium">
                <span className={`h-1.5 w-1.5 rounded-full ${onlineCams > 0 ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]' : 'bg-rose-500'}`} />
                <span className="text-zinc-300 font-mono text-[11px]">{onlineCams > 0 ? `${onlineCams}/${totalCams} Active Feeds` : 'No Active Feed'}</span>
              </span>
              <span className="text-zinc-600">•</span>
              <span className="text-zinc-400 text-[11px]">YOLOv8 + 10-Frame AMFV Consensus</span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {/* Clock Pill */}
          <div className="hidden md:flex items-center gap-2 rounded-md border border-border bg-secondary/50 px-3 py-1 text-xs font-mono text-zinc-300">
            <Clock className="h-3 w-3 text-zinc-400" />
            <span>{timeStr || 'Connecting...'}</span>
          </div>

          <Button size="sm" onClick={onOpenAddCamera} className="gap-1.5 bg-white text-zinc-950 hover:bg-zinc-200">
            <Plus className="h-3.5 w-3.5" />
            <span>Add Camera</span>
          </Button>

          <Button variant="outline" size="sm" onClick={onOpenAnalytics} className="gap-1.5 text-zinc-300 hover:text-white border-zinc-800 hover:bg-zinc-800/60">
            <BarChart3 className="h-3.5 w-3.5 text-zinc-400" />
            <span>Analytics</span>
          </Button>

          <Button variant="outline" size="sm" onClick={onOpenGallery} className="gap-1.5 text-zinc-300 hover:text-white border-zinc-800 hover:bg-zinc-800/60">
            <ImageIcon className="h-3.5 w-3.5 text-zinc-400" />
            <span>Evidence</span>
          </Button>

          <Button variant="outline" size="sm" onClick={onExportCsv} className="gap-1.5 text-zinc-300 hover:text-white border-zinc-800 hover:bg-zinc-800/60">
            <Download className="h-3.5 w-3.5 text-zinc-400" />
            <span>CSV Audit</span>
          </Button>

          <Button variant="ghost" size="icon" onClick={onOpenSettings} title="Surveillance Settings" className="text-zinc-400 hover:text-white hover:bg-zinc-800/60">
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  );
}
