import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Cloud,
  Link2,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import { api } from '../services/api';

const DEFAULT_CENTRAL_URL = 'http://127.0.0.1:9000';

export default function CentralConnectModal({ isOpen, onClose, onStatusChange }) {
  const [centralUrl, setCentralUrl] = useState(DEFAULT_CENTRAL_URL);
  const [ownerId, setOwnerId] = useState('OWN-DEFAULT-SYSTEM');
  const [hotelName, setHotelName] = useState('');
  const [kitchenName, setKitchenName] = useState('');
  const [location, setLocation] = useState('');
  const [pairingCode, setPairingCode] = useState('');

  const [status, setStatus] = useState(null);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const applyStatus = useCallback(
    (nextStatus) => {
      setStatus(nextStatus);
      if (onStatusChange) onStatusChange(nextStatus);
    },
    [onStatusChange]
  );

  useEffect(() => {
    if (!isOpen) return undefined;
    let cancelled = false;
    const refreshStatus = async () => {
      try {
        const data = await api.getCentralStatus();
        if (!cancelled) applyStatus(data);
      } catch {
        // App-level polling will recover when the backend is reachable.
      }
    };
    const loadInitial = async () => {
      try {
        const data = await api.getCentralStatus();
        if (cancelled) return;
        setError('');
        setMessage('');
        applyStatus(data);
        if (data.central_url) setCentralUrl(data.central_url);
        if (data.owner_id) setOwnerId(data.owner_id);
        if (data.hotel_name) setHotelName(data.hotel_name);
        if (data.kitchen_name) setKitchenName(data.kitchen_name);
        if (data.location) setLocation(data.location);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    };
    loadInitial();
    const interval = setInterval(refreshStatus, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [isOpen, applyStatus]);

  const handleConnect = async (event) => {
    event.preventDefault();
    setConnecting(true);
    setError('');
    setMessage('');
    try {
      const data = await api.connectCentral({
        central_url: centralUrl,
        owner_id: ownerId,
        hotel_name: hotelName,
        kitchen_name: kitchenName,
        location,
        pairing_code: pairingCode.trim() || undefined,
      });
      applyStatus(data);
      if (data.status === 'pending') {
        setMessage(
          `Awaiting approval from the administrator of ${ownerId}. Verification PIN: ${data.pin || 'check central portal'}`
        );
      } else {
        setMessage(`Connected as ${data.kitchen_id || 'edge node'}`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setConnecting(false);
    }
  };

  const handleSyncNow = async () => {
    setSyncing(true);
    setError('');
    setMessage('');
    try {
      const result = await api.syncCentralNow();
      if (result.success) {
        setMessage(
          result.synced_count > 0
            ? `Synced ${result.synced_count} incident(s)`
            : result.message || 'Everything is already synced'
        );
      } else {
        setError(result.error || 'Sync failed');
      }
      const data = await api.getCentralStatus();
      applyStatus(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSyncing(false);
    }
  };

  const configured = !!status?.configured;
  const connected = !!status?.connected;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto bg-zinc-950 border-zinc-800 text-zinc-100">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <Cloud className="h-5 w-5 text-zinc-300" />
            <DialogTitle className="text-base font-bold text-white">
              Central Fleet Connection
            </DialogTitle>
          </div>
          <DialogDescription className="text-xs text-zinc-400">
            Register this kitchen with the fleet admin server, keep a duplex command
            channel open, and sync confirmed incidents.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300">
              Connection Status
            </span>
            <div className="flex items-center gap-2">
              {status?.unsynced_count > 0 && (
                <Badge variant="outline" className="h-5 border-amber-700/60 text-[10px] text-amber-300">
                  {status.unsynced_count} pending
                </Badge>
              )}
              <Badge
                variant="outline"
                className={`h-5 gap-1 text-[10px] ${
                  connected
                    ? 'border-emerald-700/60 text-emerald-300'
                    : configured
                      ? 'border-amber-700/60 text-amber-300'
                      : 'border-zinc-700 text-zinc-400'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    connected ? 'bg-emerald-400' : configured ? 'bg-amber-400' : 'bg-zinc-500'
                  }`}
                />
                {connected ? 'Connected' : configured ? 'Offline' : 'Not configured'}
              </Badge>
            </div>
          </div>

          {configured && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-zinc-400">
              <span>Kitchen ID</span>
              <span className="font-mono text-zinc-200 truncate">{status.kitchen_id}</span>
              <span>Unsynced incidents</span>
              <span className="font-mono text-zinc-200">
                {status.unsynced_count ?? 0}
              </span>
              <span>Last sync</span>
              <span className="font-mono text-zinc-200">
                {status.last_synced_at || 'Never'}
              </span>
              <span>Sync interval</span>
              <span className="font-mono text-zinc-200">
                {status.sync_interval_minutes || 60} min
              </span>
            </div>
          )}

          {status?.last_error && (
            <p className="flex items-start gap-1.5 text-[11px] text-rose-300">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{status.last_error}</span>
            </p>
          )}
        </div>

        {(status?.pending_request_id || status?.request_id) && (
          <div className="rounded-lg border border-amber-700/40 bg-amber-500/10 p-3 space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-amber-300">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Awaiting Owner Approval
            </div>
            <p className="text-[11px] text-amber-100/80">
              Ask the administrator of <span className="font-mono">{status.owner_id || ownerId}</span> to
              approve this kitchen request in the Central Fleet Portal.
            </p>
            <div className="flex items-center gap-3">
              <div className="text-[10px] uppercase tracking-wider text-amber-200/70">Verification PIN</div>
              <div className="px-3 py-1 rounded-md bg-zinc-950/60 border border-amber-700/40 font-mono text-lg font-bold tracking-[0.2em] text-amber-200">
                {status.pending_pin || status.pin || '------'}
              </div>
            </div>
            <div className="text-[10px] font-mono text-amber-200/60 truncate">
              Request: {status.pending_request_id || status.request_id}
            </div>
          </div>
        )}

        <form onSubmit={handleConnect} className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs text-zinc-300">Central Server URL</Label>
            <Input
              value={centralUrl}
              onChange={(event) => setCentralUrl(event.target.value)}
              placeholder={DEFAULT_CENTRAL_URL}
              className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs text-zinc-300">Owner / Organization ID</Label>
            <Input
              value={ownerId}
              onChange={(event) => setOwnerId(event.target.value)}
              placeholder="OWN-MARRIOTT-8492"
              className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
              required
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-zinc-300">Hotel Name</Label>
              <Input
                value={hotelName}
                onChange={(event) => setHotelName(event.target.value)}
                placeholder="Grand Hotel & Suites"
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                required
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-zinc-300">Kitchen Name</Label>
              <Input
                value={kitchenName}
                onChange={(event) => setKitchenName(event.target.value)}
                placeholder="Main Prep Kitchen"
                className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
                required
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-zinc-300">Location (optional)</Label>
            <Input
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="Level 2 - Hot Kitchen"
              className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white"
            />
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-zinc-300">Pairing OTP Code (optional)</Label>
            <Input
              value={pairingCode}
              onChange={(event) => setPairingCode(event.target.value)}
              placeholder="849201 — skips manual approval"
              className="h-8 text-xs bg-zinc-900 border-zinc-800 text-white font-mono"
            />
          </div>

          {error && (
            <p className="flex items-start gap-1.5 text-[11px] text-rose-300">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{error}</span>
            </p>
          )}
          {message && (
            <p className="flex items-start gap-1.5 text-[11px] text-emerald-300">
              <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{message}</span>
            </p>
          )}

          <Separator className="bg-zinc-800" />

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleSyncNow}
              disabled={!configured || syncing}
              className="gap-1.5 border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-800/60"
            >
              {syncing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              Sync Now
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={connecting}
              className="gap-1.5 bg-white text-zinc-950 hover:bg-zinc-200"
            >
              {connecting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Link2 className="h-3.5 w-3.5" />
              )}
              {configured ? 'Reconnect' : 'Connect'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
