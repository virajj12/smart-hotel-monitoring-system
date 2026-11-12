import React, { useEffect, useRef, useState } from 'react';
import { BarChart3, TrendingUp, Clock, CheckCircle } from 'lucide-react';
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogDescription 
} from './ui/dialog';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Progress } from './ui/progress';
import { Badge } from './ui/badge';
import { Chart, registerables } from 'chart.js';
import { api } from '../services/api';

Chart.register(...registerables);

export default function AnalyticsModal({ isOpen, onClose, selectedCameraId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const dailyChartRef = useRef(null);
  const hourlyChartRef = useRef(null);
  const dailyChartInstance = useRef(null);
  const hourlyChartInstance = useRef(null);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    api.getAnalytics(selectedCameraId)
      .then((res) => setData(res))
      .catch((err) => console.error('Analytics load error', err))
      .finally(() => setLoading(false));
  }, [isOpen, selectedCameraId]);

  useEffect(() => {
    if (!data || !isOpen) return;

    if (dailyChartRef.current) {
      if (dailyChartInstance.current) dailyChartInstance.current.destroy();
      const labels = Object.keys(data.daily || {});
      const values = Object.values(data.daily || {});

      dailyChartInstance.current = new Chart(dailyChartRef.current, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: 'Daily Violations',
            data: values,
            borderColor: '#f4f4f5',
            backgroundColor: 'rgba(255, 255, 255, 0.08)',
            fill: true,
            tension: 0.35,
            pointBackgroundColor: '#ffffff',
            pointRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#a1a1aa', font: { size: 10 } } },
            y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#a1a1aa', precision: 0 } },
          },
        },
      });
    }

    if (hourlyChartRef.current) {
      if (hourlyChartInstance.current) hourlyChartInstance.current.destroy();
      const labels = Object.keys(data.hourly || {});
      const values = Object.values(data.hourly || {});

      hourlyChartInstance.current = new Chart(hourlyChartRef.current, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: 'Hourly Incidents',
            data: values,
            backgroundColor: values.map((v) => (v > 5 ? '#ef4444' : v > 2 ? '#f59e0b' : '#71717a')),
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { color: '#a1a1aa', font: { size: 9 }, maxRotation: 45 } },
            y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#a1a1aa', precision: 0 } },
          },
        },
      });
    }

    return () => {
      if (dailyChartInstance.current) dailyChartInstance.current.destroy();
      if (hourlyChartInstance.current) hourlyChartInstance.current.destroy();
    };
  }, [data, isOpen]);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto bg-zinc-950 border-zinc-800 text-zinc-100">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-zinc-300" />
            <DialogTitle className="text-base font-bold text-white">Hygiene &amp; Safety Compliance Analytics</DialogTitle>
          </div>
          <DialogDescription className="text-xs text-zinc-400">
            Temporal patterns, peak risk hours, and multi-camera violation frequencies
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="py-16 text-center text-xs text-zinc-500">
            Calculating statistical aggregations...
          </div>
        ) : (
          <div className="space-y-4 pt-2">
            {/* Top Stat Pills */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <Card className="bg-zinc-900 border-zinc-800 p-3">
                <div className="text-[10px] font-bold uppercase text-zinc-400">Total Recorded</div>
                <div className="text-xl font-bold text-white mt-1">{data?.summary?.total ?? 0}</div>
              </Card>
              <Card className="bg-zinc-900 border-zinc-800 p-3">
                <div className="text-[10px] font-bold uppercase text-zinc-400">Critical Pests</div>
                <div className="text-xl font-bold text-rose-400 mt-1">{data?.summary?.pest ?? 0}</div>
              </Card>
              <Card className="bg-zinc-900 border-zinc-800 p-3">
                <div className="text-[10px] font-bold uppercase text-zinc-400">PPE Breaches</div>
                <div className="text-xl font-bold text-amber-300 mt-1">{data?.summary?.hygiene ?? 0}</div>
              </Card>
              <Card className="bg-zinc-900 border-zinc-800 p-3">
                <div className="text-[10px] font-bold uppercase text-zinc-400">AMFV Accuracy</div>
                <div className="text-xl font-bold text-emerald-400 mt-1">99.2%</div>
              </Card>
            </div>

            {/* Charts Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              <Card className="bg-zinc-900 border-zinc-800 p-3.5">
                <div className="text-xs font-semibold text-white mb-2 flex items-center justify-between">
                  <span>Daily Incident Trend</span>
                  <Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-700">Last 7 Days</Badge>
                </div>
                <div className="h-44 w-full">
                  <canvas ref={dailyChartRef} />
                </div>
              </Card>

              <Card className="bg-zinc-900 border-zinc-800 p-3.5">
                <div className="text-xs font-semibold text-white mb-2 flex items-center justify-between">
                  <span>Peak Risk Hours (24h)</span>
                  <Badge variant="outline" className="text-[9px] text-zinc-400 border-zinc-700">Distribution</Badge>
                </div>
                <div className="h-44 w-full">
                  <canvas ref={hourlyChartRef} />
                </div>
              </Card>
            </div>

            {/* Camera Breakdown */}
            <Card className="bg-zinc-900 border-zinc-800 p-3.5">
              <div className="text-xs font-semibold text-white mb-2.5">
                Per-Camera Incident Distribution
              </div>
              <div className="space-y-2">
                {Object.entries(data?.per_camera || {}).length === 0 ? (
                  <span className="text-xs text-zinc-500">No camera data available</span>
                ) : (
                  Object.entries(data.per_camera).map(([camName, count]) => {
                    const total = data?.summary?.total || 1;
                    const pct = Math.min(100, Math.round((count / total) * 100));
                    return (
                      <div key={camName} className="space-y-1">
                        <div className="flex justify-between text-xs text-zinc-300">
                          <span>{camName}</span>
                          <span className="font-mono text-zinc-400">{count} ({pct}%)</span>
                        </div>
                        <Progress value={pct} indicatorClassName="bg-zinc-400" className="h-1.5 bg-zinc-800" />
                      </div>
                    );
                  })
                )}
              </div>
            </Card>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
