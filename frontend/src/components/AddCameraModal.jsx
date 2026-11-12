import React, { useState, useEffect } from 'react';
import { Video, RefreshCw, Check, AlertCircle } from 'lucide-react';
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
import { Tabs, TabsList, TabsTrigger } from './ui/tabs';
import { Badge } from './ui/badge';
import { api } from '../services/api';

const RTSP_PRESETS = {
  generic: { label: 'Generic RTSP Stream', path: '/live' },
  mobile: { label: 'Mobile IP Webcam (Android/iOS)', path: '/h264_pcm.sdp' },
  hikvision: { label: 'Hikvision IP Camera', path: '/Streaming/Channels/101' },
  dahua: { label: 'Dahua / Imou Camera', path: '/cam/realmonitor?channel=1&subtype=0' },
  reolink: { label: 'Reolink IP Camera', path: '/h264Preview_01_main' },
};

export default function AddCameraModal({ isOpen, onClose, onCameraAdded }) {
  const [sourceType, setSourceType] = useState('rtsp');
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');

  // RTSP fields
  const [brand, setBrand] = useState('generic');
  const [ip, setIp] = useState('192.168.1.100');
  const [port, setPort] = useState('554');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [rtspPath, setRtspPath] = useState('/live');

  // Other types
  const [httpUrl, setHttpUrl] = useState('http://192.168.1.100:8080/video');
  const [webcamIndex, setWebcamIndex] = useState('0');
  const [filePath, setFilePath] = useState('demo1.mp4');

  // Testing & Submit state
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (RTSP_PRESETS[brand]) {
      setRtspPath(RTSP_PRESETS[brand].path);
      if (brand === 'mobile') setPort('8080');
      else setPort('554');
    }
  }, [brand]);

  const constructSourceUrl = () => {
    if (sourceType === 'rtsp') {
      const auth = username && password ? `${encodeURIComponent(username)}:${encodeURIComponent(password)}@` : '';
      return `rtsp://${auth}${ip}:${port}${rtspPath.startsWith('/') ? rtspPath : `/${rtspPath}`}`;
    }
    if (sourceType === 'http') return httpUrl;
    if (sourceType === 'webcam') return webcamIndex;
    if (sourceType === 'file') return filePath;
    return '';
  };

  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const source = constructSourceUrl();
      const res = await api.testCamera(source, sourceType);
      setTestResult(res);
    } catch (err) {
      setTestResult({ success: false, error: err.message });
    } finally {
      setTesting(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = {
        name: name.trim() || `Camera (${sourceType.toUpperCase()})`,
        location: location.trim() || 'Kitchen',
        source_type: sourceType,
        source: constructSourceUrl(),
        username,
        password,
      };

      if (sourceType === 'rtsp') {
        payload.ip = ip;
        payload.port = parseInt(port) || 554;
        payload.path = rtspPath;
      } else if (sourceType === 'file') {
        payload.file_path = filePath;
      }

      await api.addCamera(payload);
      onCameraAdded();
      onClose();
    } catch (err) {
      alert(`Failed to add camera: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto bg-zinc-950 border-zinc-800 text-zinc-100">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Video className="h-5 w-5 text-zinc-300" />
            <DialogTitle className="text-base font-bold text-white">Add CCTV Camera Stream</DialogTitle>
          </div>
          <DialogDescription className="text-xs text-zinc-400">
            Connect an IP camera, mobile webcam, USB device, or video file for continuous monitoring.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          {/* Source Type Tabs */}
          <Tabs value={sourceType} onValueChange={(val) => { setSourceType(val); setTestResult(null); }}>
            <TabsList className="grid w-full grid-cols-4 h-8 bg-zinc-900 border border-zinc-800 p-0.5">
              <TabsTrigger value="rtsp" className="text-xs py-1 data-[state=active]:bg-white data-[state=active]:text-zinc-950 text-zinc-400 font-medium">RTSP IP Cam</TabsTrigger>
              <TabsTrigger value="http" className="text-xs py-1 data-[state=active]:bg-white data-[state=active]:text-zinc-950 text-zinc-400 font-medium">HTTP Stream</TabsTrigger>
              <TabsTrigger value="webcam" className="text-xs py-1 data-[state=active]:bg-white data-[state=active]:text-zinc-950 text-zinc-400 font-medium">USB Webcam</TabsTrigger>
              <TabsTrigger value="file" className="text-xs py-1 data-[state=active]:bg-white data-[state=active]:text-zinc-950 text-zinc-400 font-medium">Video File</TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Common info */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs text-zinc-300">Camera Name</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Kitchen Main Feed"
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-300">Surveillance Location</Label>
              <Input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="Kitchen - Food Prep Counter"
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
              />
            </div>
          </div>

          {/* Conditional Fields */}
          {sourceType === 'rtsp' && (
            <div className="space-y-3 p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-300">Camera Brand / Mobile Preset</Label>
                  <select
                    value={brand}
                    onChange={(e) => setBrand(e.target.value)}
                    className="w-full h-8 px-2.5 text-xs rounded-md border border-zinc-800 bg-zinc-900 text-white focus:outline-none"
                  >
                    {Object.entries(RTSP_PRESETS).map(([k, v]) => (
                      <option key={k} value={k}>{v.label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-300">IP Address</Label>
                  <Input
                    value={ip}
                    onChange={(e) => setIp(e.target.value)}
                    placeholder="192.168.1.100"
                    className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-300">RTSP Port</Label>
                  <Input
                    value={port}
                    onChange={(e) => setPort(e.target.value)}
                    placeholder="554"
                    className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-300">Username</Label>
                  <Input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="admin"
                    className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-300">Password</Label>
                  <Input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                  />
                </div>
              </div>

              <div className="space-y-1">
                <Label className="text-xs text-zinc-300">Stream Subpath</Label>
                <Input
                  value={rtspPath}
                  onChange={(e) => setRtspPath(e.target.value)}
                  placeholder="/live"
                  className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white font-mono"
                />
              </div>
            </div>
          )}

          {sourceType === 'http' && (
            <div className="space-y-1 p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
              <Label className="text-xs text-zinc-300">HTTP / MJPEG Stream URL</Label>
              <Input
                value={httpUrl}
                onChange={(e) => setHttpUrl(e.target.value)}
                placeholder="http://192.168.1.100:8080/video"
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white font-mono"
              />
              <p className="text-[11px] text-zinc-400">
                Use with apps like IP Webcam Android (`http://IP:8080/video`).
              </p>
            </div>
          )}

          {sourceType === 'webcam' && (
            <div className="space-y-1 p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
              <Label className="text-xs text-zinc-300">Webcam Device Index</Label>
              <Input
                value={webcamIndex}
                onChange={(e) => setWebcamIndex(e.target.value)}
                placeholder="0"
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white font-mono"
              />
              <p className="text-[11px] text-zinc-400">
                Default primary camera is usually index `0`.
              </p>
            </div>
          )}

          {sourceType === 'file' && (
            <div className="space-y-1 p-3 rounded-lg border border-zinc-800 bg-zinc-900/50">
              <Label className="text-xs text-zinc-300">Video File Path</Label>
              <Input
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                placeholder="demo1.mp4"
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white font-mono"
              />
              <p className="text-[11px] text-zinc-400">
                Enter relative or absolute path (e.g. `demo1.mp4`). Video loops continuously.
              </p>
            </div>
          )}

          {/* Constructed URL Preview & Test */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-2.5">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">Generated Connection URI</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTestConnection}
                disabled={testing}
                className="h-5 px-2 text-[10px] text-zinc-300 border-zinc-700 hover:bg-zinc-800 gap-1"
              >
                <RefreshCw className={`h-2.5 w-2.5 ${testing ? 'animate-spin' : ''}`} />
                <span>{testing ? 'Testing...' : 'Test Connection'}</span>
              </Button>
            </div>
            <div className="font-mono text-[11px] text-zinc-300 truncate bg-black/40 p-1.5 rounded">
              {constructSourceUrl() || 'Incomplete Configuration'}
            </div>

            {testResult && (
              <div className={`mt-2 flex items-center gap-1.5 text-xs ${testResult.success ? 'text-emerald-400' : 'text-rose-400'}`}>
                {testResult.success ? <Check className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
                <span>
                  {testResult.success ? `Stream Verified (${testResult.resolution || 'Active'})` : `Connection failed: ${testResult.error || 'Timed out'}`}
                </span>
              </div>
            )}
          </div>

          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose} className="text-zinc-300 border-zinc-800 hover:bg-zinc-900">
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={submitting} className="bg-white text-zinc-950 hover:bg-zinc-200">
              {submitting ? 'Connecting...' : 'Add Camera Stream'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
