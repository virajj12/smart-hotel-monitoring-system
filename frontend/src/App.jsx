import React, { useState, useEffect, useCallback } from 'react';
import Navbar from './components/Navbar';
import KpiStrip from './components/KpiStrip';
import CameraGrid from './components/CameraGrid';
import InspectorDock from './components/InspectorDock';

import AddCameraModal from './components/AddCameraModal';
import AnalyticsModal from './components/AnalyticsModal';
import SnapshotGalleryModal from './components/SnapshotGalleryModal';
import SettingsModal from './components/SettingsModal';

import { api } from './services/api';
import { Badge } from './components/ui/badge';
import { X } from 'lucide-react';

export default function App() {
  // Telemetry & Data State
  const [cameras, setCameras] = useState([]);
  const [selectedCameraId, setSelectedCameraId] = useState(null);
  const [focusedCamId, setFocusedCamId] = useState(null);
  const [stats, setStats] = useState({ total: 0, pest: 0, hygiene: 0, breakdown: {} });
  const [logs, setLogs] = useState([]);
  const [amfvData, setAmfvData] = useState({});
  const [systemInfo, setSystemInfo] = useState(null);

  // Inspector Panel Collapse State (True by default)
  const [isInspectorOpen, setIsInspectorOpen] = useState(true);

  // Modal Visibility State
  const [isAddCameraOpen, setIsAddCameraOpen] = useState(false);
  const [isAnalyticsOpen, setIsAnalyticsOpen] = useState(false);
  const [isGalleryOpen, setIsGalleryOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [zoomedImageUrl, setZoomedImageUrl] = useState(null);

  // Fetch cameras
  const fetchCameras = useCallback(async () => {
    try {
      const data = await api.getCameras();
      setCameras(data || []);
    } catch (err) {
      console.error('Failed to load cameras', err);
    }
  }, []);

  // Fetch telemetry data
  const fetchTelemetry = useCallback(async () => {
    try {
      const [logsRes, amfvRes, statsRes, sysRes] = await Promise.allSettled([
        api.getLogs(selectedCameraId),
        api.getAmfvStatus(selectedCameraId),
        api.getStats(selectedCameraId),
        api.getSystemInfo(),
      ]);

      if (logsRes.status === 'fulfilled') setLogs(logsRes.value || []);
      if (amfvRes.status === 'fulfilled') setAmfvData(amfvRes.value || {});
      if (statsRes.status === 'fulfilled') setStats(statsRes.value || { total: 0, pest: 0, hygiene: 0, breakdown: {} });
      if (sysRes.status === 'fulfilled') setSystemInfo(sysRes.value || null);
    } catch (err) {
      console.error('Polling error', err);
    }
  }, [selectedCameraId]);

  // Initial load & Polling
  useEffect(() => {
    fetchCameras();
    fetchTelemetry();

    const telemetryInterval = setInterval(fetchTelemetry, 2200);
    const cameraInterval = setInterval(fetchCameras, 6000);

    return () => {
      clearInterval(telemetryInterval);
      clearInterval(cameraInterval);
    };
  }, [fetchCameras, fetchTelemetry]);

  // Actions
  const handleAddDemoCamera = async () => {
    try {
      await api.addCamera({
        name: 'Kitchen CCTV Feed (demo1)',
        location: 'Kitchen - Surveillance Area',
        source_type: 'file',
        file_path: 'demo1.mp4',
      });
      await fetchCameras();
      await fetchTelemetry();
    } catch (err) {
      alert(`Failed to load demo video: ${err.message}`);
    }
  };

  const handleRemoveCamera = async (id) => {
    if (!window.confirm('Remove this CCTV camera stream?')) return;
    try {
      await api.deleteCamera(id);
      if (selectedCameraId === id) setSelectedCameraId(null);
      if (focusedCamId === id) setFocusedCamId(null);
      fetchCameras();
      fetchTelemetry();
    } catch (err) {
      alert(`Failed to remove camera: ${err.message}`);
    }
  };

  const handleClearLogs = async () => {
    if (!window.confirm('Clear all incident logs for the selected view?')) return;
    try {
      await api.clearLogs(selectedCameraId);
      fetchTelemetry();
    } catch (err) {
      alert(`Failed to clear logs: ${err.message}`);
    }
  };

  const handleExportCsv = () => {
    window.open(api.getCsvExportUrl(selectedCameraId), '_blank');
  };

  return (
    <div className="flex flex-col min-h-screen bg-background text-foreground">
      {/* Top Navigation Bar */}
      <Navbar
        systemInfo={systemInfo}
        onOpenAddCamera={() => setIsAddCameraOpen(true)}
        onOpenAnalytics={() => setIsAnalyticsOpen(true)}
        onOpenGallery={() => setIsGalleryOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onExportCsv={handleExportCsv}
      />

      {/* Main Surveillance Workspace */}
      <main className="flex-1 max-w-[1740px] w-full mx-auto p-4 flex flex-col">
        {/* Slim KPI Strip (Replaces bulky 3-column cards) */}
        <KpiStrip
          stats={stats}
          amfvData={amfvData}
          focusedCamId={focusedCamId}
          onResetFocus={() => setFocusedCamId(null)}
          isInspectorOpen={isInspectorOpen}
          onToggleInspector={() => setIsInspectorOpen((prev) => !prev)}
        />

        {/* Dynamic Canvas: CCTV Stream Stage (Left) & Unified Inspector Dock (Right) */}
        <div className={`grid gap-4 items-start transition-all ${
          isInspectorOpen
            ? 'grid-cols-1 lg:grid-cols-[minmax(0,1fr)_370px]'
            : 'grid-cols-1'
        }`}>
          {/* Hero Video Canvas */}
          <section className="flex flex-col w-full min-w-0">
            <CameraGrid
              cameras={cameras}
              focusedCamId={focusedCamId}
              onToggleFocus={(id) => setFocusedCamId(focusedCamId === id ? null : id)}
              onSelectCamera={(id) => setSelectedCameraId(id)}
              onRemoveCamera={handleRemoveCamera}
              onOpenAddCamera={() => setIsAddCameraOpen(true)}
              onAddDemoCamera={handleAddDemoCamera}
            />
          </section>

          {/* Tabbed Inspector Rail */}
          {isInspectorOpen && (
            <aside className="w-full">
              <InspectorDock
                logs={logs}
                amfvData={amfvData}
                cameras={cameras}
                selectedCameraId={selectedCameraId}
                onSelectCamera={(id) => setSelectedCameraId(id)}
                onClearLogs={handleClearLogs}
                onExportCsv={handleExportCsv}
                onViewSnapshot={(url) => setZoomedImageUrl(url)}
                onOpenAddCamera={() => setIsAddCameraOpen(true)}
              />
            </aside>
          )}
        </div>
      </main>

      {/* System Status Footer */}
      <footer className="border-t border-border py-2.5 px-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-zinc-500 bg-zinc-950/80">
        <div className="flex items-center gap-3">
          <span>Enterprise Hotel CCTV Monitoring</span>
          <span>•</span>
          <span className="font-mono text-[11px] text-zinc-400">YOLOv8 + AMFV 10-Frame Filter</span>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono text-[10px] text-zinc-400 border-zinc-800">shadcn/ui</Badge>
          <Badge variant="outline" className="font-mono text-[10px] text-zinc-400 border-zinc-800">React 19</Badge>
          <Badge variant="outline" className="font-mono text-[10px] text-zinc-400 border-zinc-800">Tailwind</Badge>
          <Badge variant="outline" className="font-mono text-[10px] text-zinc-400 border-zinc-800">FastAPI</Badge>
        </div>
      </footer>

      {/* Modals */}
      <AddCameraModal
        isOpen={isAddCameraOpen}
        onClose={() => setIsAddCameraOpen(false)}
        onCameraAdded={() => {
          fetchCameras();
          fetchTelemetry();
        }}
      />

      <AnalyticsModal
        isOpen={isAnalyticsOpen}
        onClose={() => setIsAnalyticsOpen(false)}
        selectedCameraId={selectedCameraId}
      />

      <SnapshotGalleryModal
        isOpen={isGalleryOpen}
        onClose={() => setIsGalleryOpen(false)}
        selectedCameraId={selectedCameraId}
        onZoomImage={(url) => setZoomedImageUrl(url)}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />

      {/* High-Resolution Evidence Zoom Dialog */}
      {zoomedImageUrl && (
        <div
          className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in"
          onClick={() => setZoomedImageUrl(null)}
        >
          <div
            className="relative max-w-4xl w-full bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-3 border-b border-zinc-800 bg-zinc-900/60">
              <span className="text-xs font-bold text-white">Full-Resolution Violation Evidence Snapshot</span>
              <button
                onClick={() => setZoomedImageUrl(null)}
                className="h-6 w-6 flex items-center justify-center rounded-md hover:bg-zinc-800 text-zinc-400 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-2 bg-black flex items-center justify-center max-h-[75vh]">
              <img
                src={zoomedImageUrl}
                alt="Zoomed Evidence"
                className="max-h-[70vh] w-auto object-contain rounded"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
