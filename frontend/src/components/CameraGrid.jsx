import React from 'react';
import { 
  Maximize2, 
  Minimize2, 
  MoreVertical, 
  Play, 
  Plus, 
  Trash2, 
  Filter, 
  Camera, 
  Activity 
} from 'lucide-react';
import { Card, CardTitle, CardDescription } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { 
  DropdownMenu, 
  DropdownMenuTrigger, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuSeparator 
} from './ui/dropdown-menu';

export default function CameraGrid({
  cameras = [],
  focusedCamId,
  onToggleFocus,
  onSelectCamera,
  onRemoveCamera,
  onOpenAddCamera,
  onAddDemoCamera,
}) {
  if (cameras.length === 0) {
    return (
      <Card className="flex flex-col items-center justify-center p-12 text-center h-full min-h-[500px] bg-card border-border">
        <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-zinc-800 text-zinc-300 border border-zinc-700/60 mb-3">
          <Camera className="h-7 w-7" />
        </div>
        <CardTitle className="text-base font-bold text-white mb-1">No CCTV Stream Connected</CardTitle>
        <CardDescription className="max-w-md mb-5 text-xs text-zinc-400">
          Connect your hotel kitchen IP/RTSP camera, mobile webcam, or load the demo surveillance video to begin real-time AI monitoring.
        </CardDescription>
        <div className="flex gap-2.5">
          <Button onClick={onOpenAddCamera} className="gap-2 bg-white text-zinc-950 hover:bg-zinc-200">
            <Plus className="h-4 w-4" />
            <span>Connect Camera</span>
          </Button>
          <Button variant="outline" onClick={onAddDemoCamera} className="gap-2 text-zinc-300 hover:text-white border-zinc-700 hover:bg-zinc-800">
            <Play className="h-4 w-4 text-zinc-400" />
            <span>Load Demo Video</span>
          </Button>
        </div>
      </Card>
    );
  }

  const isSingle = cameras.length === 1 || focusedCamId != null;

  return (
    <div
      className={`grid gap-3.5 w-full ${
        isSingle
          ? 'grid-cols-1'
          : 'grid-cols-1 md:grid-cols-2'
      }`}
    >
      {cameras.map((cam) => {
        const isFocused = focusedCamId === cam.id;
        const isOnline = cam.connected ?? (cam.status === 'online');

        if (focusedCamId && !isFocused) return null;

        return (
          <Card key={cam.id} className="overflow-hidden flex flex-col p-0 bg-card border-border shadow-md">
            {/* Camera Header Bar */}
            <div className="flex items-center justify-between p-3 border-b border-border bg-zinc-900/60">
              <div className="flex items-center gap-2">
                <Camera className="h-3.5 w-3.5 text-zinc-400" />
                <div>
                  <div className="text-xs font-bold text-white leading-tight">{cam.name}</div>
                  <div className="text-[10px] text-zinc-400">{cam.location || 'Kitchen'} · {cam.source_type?.toUpperCase() || 'FILE'}</div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge variant="outline" className={`h-5 gap-1 text-[10px] font-mono ${isOnline ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' : 'text-zinc-500 border-zinc-800'}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-600'}`} />
                  {isOnline ? 'LIVE' : 'OFFLINE'}
                </Badge>
                {cam.fps != null && (
                  <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-mono text-zinc-400 border-zinc-800 bg-zinc-900">
                    {cam.fps} FPS
                  </Badge>
                )}
              </div>
            </div>

            {/* Video Feed Stage */}
            <div className={`relative w-full bg-black flex items-center justify-center overflow-hidden ${
              isSingle ? 'aspect-[16/9] min-h-[380px] max-h-[calc(100vh-250px)]' : 'aspect-video'
            }`}>
              <img
                src={`/video_feed/${cam.id}`}
                alt={cam.name}
                className="w-full h-full object-contain block"
                onError={(e) => {
                  if (!e.currentTarget.dataset.retried) {
                    e.currentTarget.dataset.retried = 'true';
                    e.currentTarget.src = '/video_feed';
                  }
                }}
              />

              {/* Video Overlay Badges (Top-Left) */}
              <div className="absolute top-3 left-3 flex items-center gap-1.5 z-10">
                <Badge variant="destructive" className="h-5 px-1.5 gap-1 text-[9px] font-mono uppercase bg-rose-600/90 text-white backdrop-blur-sm border-0 shadow-sm">
                  <span className="h-1.5 w-1.5 rounded-full bg-white animate-pulse" />
                  REC
                </Badge>
                <Badge variant="secondary" className="h-5 px-1.5 text-[9px] font-mono bg-zinc-900/85 text-zinc-300 backdrop-blur-sm border border-zinc-700/60 shadow-sm">
                  YOLOv8 · Conf &ge; 45%
                </Badge>
                <Badge variant="secondary" className="h-5 px-1.5 text-[9px] font-mono bg-zinc-900/85 text-zinc-300 backdrop-blur-sm border border-zinc-700/60 shadow-sm">
                  AMFV · W=10
                </Badge>
              </div>

              {/* Reconnection Overlay */}
              {!isOnline && (
                <div className="absolute inset-0 bg-black/90 flex flex-col items-center justify-center z-20">
                  <Activity className="h-7 w-7 text-zinc-400 animate-spin mb-2" />
                  <span className="text-xs text-zinc-400">Reconnecting surveillance stream...</span>
                </div>
              )}
            </div>

            {/* Camera Footer Controls */}
            <div className="flex items-center justify-between p-2.5 px-3 border-t border-border bg-zinc-900/40">
              <span className="text-xs text-zinc-400">
                Violations Logged: <strong className="text-white font-mono">{cam.violation_count || 0}</strong>
              </span>

              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 px-2 text-[11px] text-zinc-300 hover:text-white border-zinc-700 hover:bg-zinc-800 gap-1"
                  onClick={() => onToggleFocus(cam.id)}
                  title={isFocused ? 'Restore Grid View' : 'Maximize this Camera'}
                >
                  {isFocused ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
                  <span>{isFocused ? 'Restore' : 'Focus'}</span>
                </Button>

                {/* Dropdown Menu */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-6 w-6 text-zinc-400 hover:text-white hover:bg-zinc-800">
                      <MoreVertical className="h-3.5 w-3.5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="bg-zinc-900 border-zinc-700 text-zinc-300">
                    <DropdownMenuItem onClick={() => onSelectCamera(cam.id)} className="gap-2 text-xs focus:bg-zinc-800 focus:text-white">
                      <Filter className="h-3.5 w-3.5" />
                      <span>Filter Stats by this Camera</span>
                    </DropdownMenuItem>
                    <DropdownMenuSeparator className="bg-zinc-800" />
                    <DropdownMenuItem
                      onClick={() => onRemoveCamera(cam.id)}
                      className="gap-2 text-xs text-rose-400 focus:bg-rose-500/10 focus:text-rose-300"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      <span>Remove Camera</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
