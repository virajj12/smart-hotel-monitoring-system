import React, { useState, useEffect } from 'react';
import { Sliders, CheckCircle2 } from 'lucide-react';
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogDescription, 
  DialogFooter 
} from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Slider } from './ui/slider';
import { Switch } from './ui/switch';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import { api } from '../services/api';

export default function SettingsModal({ isOpen, onClose }) {
  const [conf, setConf] = useState(45);
  const [imgsz, setImgsz] = useState('640');
  const [geomFilter, setGeomFilter] = useState(true);
  const [tta, setTta] = useState(false);
  const [iou, setIou] = useState(0.45);

  const [amfvWindow, setAmfvWindow] = useState(10);
  const [pestThreshold, setPestThreshold] = useState(0.35);
  const [hygieneThreshold, setHygieneThreshold] = useState(0.45);
  const [cooldown, setCooldown] = useState(30);

  const [email, setEmail] = useState('');
  const [webhook, setWebhook] = useState('');

  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setSavedSuccess(false);
    api.getSettings()
      .then((cfg) => {
        setConf(Math.round((cfg.conf_threshold ?? 0.45) * 100));
        setImgsz(String(cfg.imgsz ?? 640));
        setGeomFilter(cfg.geometric_filter !== false);
        setTta(!!cfg.enable_tta);
        setIou(cfg.iou_threshold ?? 0.45);

        setAmfvWindow(cfg.amfv_window ?? 10);
        setPestThreshold(cfg.amfv_threshold_pest ?? 0.35);
        setHygieneThreshold(cfg.amfv_threshold_hygiene ?? 0.45);
        setCooldown(cfg.cooldown_seconds ?? 30);

        setEmail(cfg.notification_email || '');
        setWebhook(cfg.webhook_url || '');
      })
      .catch((err) => console.error('Settings load error', err));
  }, [isOpen]);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSavedSuccess(false);
    try {
      await api.updateSettings({
        conf_threshold: conf / 100,
        imgsz: parseInt(imgsz) || 640,
        geometric_filter: geomFilter,
        enable_tta: tta,
        iou_threshold: iou,
        amfv_window: parseInt(amfvWindow) || 10,
        amfv_threshold_pest: parseFloat(pestThreshold),
        amfv_threshold_hygiene: parseFloat(hygieneThreshold),
        cooldown_seconds: parseInt(cooldown) || 30,
        notification_email: email,
        webhook_url: webhook,
      });
      setSavedSuccess(true);
      setTimeout(() => {
        setSavedSuccess(false);
        onClose();
      }, 900);
    } catch (err) {
      alert(`Failed to save settings: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto bg-zinc-950 border-zinc-800 text-zinc-100">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Sliders className="h-5 w-5 text-zinc-300" />
            <DialogTitle className="text-base font-bold text-white">Surveillance Calibration &amp; Notifications</DialogTitle>
          </div>
          <DialogDescription className="text-xs text-zinc-400">
            Tune YOLOv8 confidence, temporal AMFV voting window, and alert channels.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSave} className="space-y-4 pt-2">
          {/* Section 1: AI Model */}
          <div className="space-y-3">
            <div className="text-xs font-semibold text-white uppercase tracking-wider flex items-center justify-between">
              <span>YOLOv8 Detection Parameters</span>
              <Badge variant="outline" className="text-[10px] text-zinc-400 border-zinc-800">Tier 1 &amp; Tier 2</Badge>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs text-zinc-300">
                <Label htmlFor="conf-slider" className="text-xs text-zinc-300">Confidence Threshold</Label>
                <span className="font-mono text-white font-bold">{conf}%</span>
              </div>
              <Slider
                id="conf-slider"
                min={20}
                max={90}
                step={5}
                value={[conf]}
                onValueChange={([val]) => setConf(val)}
                className="py-1"
              />
              <p className="text-[11px] text-zinc-400">
                Recommended 45% to suppress false positives on reflections while catching fast pests.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-1">
              <div className="space-y-1">
                <Label className="text-xs text-zinc-300">Input Image Resolution</Label>
                <Input
                  value={imgsz}
                  onChange={(e) => setImgsz(e.target.value)}
                  placeholder="640"
                  className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                />
              </div>

              <div className="space-y-1">
                <Label className="text-xs text-zinc-300">NMS IoU Threshold</Label>
                <Input
                  type="number"
                  step="0.05"
                  value={iou}
                  onChange={(e) => setIou(parseFloat(e.target.value) || 0.45)}
                  className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <div>
                <Label className="text-xs text-zinc-300">Geometric Aspect &amp; Size Filter</Label>
                <p className="text-[11px] text-zinc-400">Discard oversized/tiny bounding boxes</p>
              </div>
              <Switch checked={geomFilter} onCheckedChange={setGeomFilter} />
            </div>
          </div>

          <Separator className="bg-zinc-800" />

          {/* Section 2: AMFV */}
          <div className="space-y-3">
            <div className="text-xs font-semibold text-white uppercase tracking-wider flex items-center justify-between">
              <span>AMFV Temporal Voting Configuration</span>
              <Badge variant="outline" className="text-[10px] text-zinc-400 border-zinc-800">Tier 3 Verification</Badge>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs text-zinc-300">
                <Label className="text-xs text-zinc-300">Temporal Window Size</Label>
                <span className="font-mono text-white font-bold">{amfvWindow} frames</span>
              </div>
              <Slider
                min={5}
                max={30}
                step={1}
                value={[amfvWindow]}
                onValueChange={([val]) => setAmfvWindow(val)}
                className="py-1"
              />
              <p className="text-[11px] text-zinc-400">
                Number of consecutive frames sampled for consensus check (10 frames = ~0.6 sec).
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-zinc-300">Pest Threshold Ratio</Label>
                <Input
                  type="number"
                  step="0.05"
                  min="0.1"
                  max="1.0"
                  value={pestThreshold}
                  onChange={(e) => setPestThreshold(e.target.value)}
                  className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-zinc-300">Hygiene Threshold Ratio</Label>
                <Input
                  type="number"
                  step="0.05"
                  min="0.1"
                  max="1.0"
                  value={hygieneThreshold}
                  onChange={(e) => setHygieneThreshold(e.target.value)}
                  className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                />
              </div>
            </div>
          </div>

          <Separator className="bg-zinc-800" />

          {/* Section 3: Alerts */}
          <div className="space-y-3">
            <div className="text-xs font-semibold text-white uppercase tracking-wider">
              Notification Dispatch
            </div>

            <div className="space-y-1">
              <Label className="text-xs text-zinc-300">Recipient Email Address</Label>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="manager@hotelkitchen.com"
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
              />
            </div>

            <div className="space-y-1">
              <Label className="text-xs text-zinc-300">Webhook URL (Slack / Teams / Discord)</Label>
              <Input
                type="url"
                value={webhook}
                onChange={(e) => setWebhook(e.target.value)}
                placeholder="https://hooks.slack.com/services/..."
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
              />
            </div>
          </div>

          <DialogFooter className="pt-2 flex justify-between items-center sm:justify-between">
            {savedSuccess ? (
              <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                <CheckCircle2 className="h-4 w-4" />
                Settings updated successfully
              </span>
            ) : <span />}

            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm" onClick={onClose} className="text-zinc-300 border-zinc-800 hover:bg-zinc-900">
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={saving} className="bg-white text-zinc-950 hover:bg-zinc-200">
                {saving ? 'Saving...' : 'Save Configuration'}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
