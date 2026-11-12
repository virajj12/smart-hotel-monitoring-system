import React, { useState, useEffect } from 'react';
import { Image as ImageIcon, CheckCircle2, ZoomIn } from 'lucide-react';
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogDescription 
} from './ui/dialog';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Card } from './ui/card';
import { Tabs, TabsList, TabsTrigger } from './ui/tabs';
import { api } from '../services/api';

const LABEL_MAP = {
  cockroach: '🪳 Cockroach',
  lizard: '🦎 Lizard',
  rat: '🐀 Rat',
  no_apron: '🧥 No Apron',
  no_gloves: '🧤 No Gloves',
  no_hairnet: '👒 No Hairnet',
};

export default function SnapshotGalleryModal({
  isOpen,
  onClose,
  selectedCameraId,
  onZoomImage,
}) {
  const [snapshots, setSnapshots] = useState([]);
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    if (!isOpen) return;
    api.getSnapshots(selectedCameraId)
      .then((items) => setSnapshots(items || []))
      .catch((err) => console.error('Snapshot load error', err));
  }, [isOpen, selectedCameraId]);

  const handleAcknowledge = async (id, e) => {
    e.stopPropagation();
    try {
      await api.acknowledgeViolation(id);
      setSnapshots((prev) =>
        prev.map((s) => (s.id === id ? { ...s, acknowledged: true } : s))
      );
    } catch (err) {
      console.error('Failed to acknowledge', err);
    }
  };

  const filtered = snapshots.filter((s) => {
    if (filter === 'pest') return s.category === 'pest';
    if (filter === 'hygiene') return s.category === 'hygiene';
    return true;
  });

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto bg-zinc-950 border-zinc-800 text-zinc-100">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <ImageIcon className="h-5 w-5 text-zinc-300" />
            <DialogTitle className="text-base font-bold text-white">Surveillance Snapshot Evidence Gallery</DialogTitle>
          </div>
          <DialogDescription className="text-xs text-zinc-400">
            High-resolution frames auto-captured during confirmed AMFV violations
          </DialogDescription>
        </DialogHeader>

        {/* Filter Tabs */}
        <div className="flex items-center justify-between pt-1">
          <Tabs value={filter} onValueChange={setFilter} className="w-auto">
            <TabsList className="h-7 bg-zinc-900 border border-zinc-800 p-0.5">
              <TabsTrigger value="all" className="text-xs py-1 data-[state=active]:bg-white data-[state=active]:text-zinc-950 text-zinc-400 font-medium">All ({snapshots.length})</TabsTrigger>
              <TabsTrigger value="pest" className="text-xs py-1 data-[state=active]:bg-white data-[state=active]:text-zinc-950 text-zinc-400 font-medium">Pests</TabsTrigger>
              <TabsTrigger value="hygiene" className="text-xs py-1 data-[state=active]:bg-white data-[state=active]:text-zinc-950 text-zinc-400 font-medium">Hygiene</TabsTrigger>
            </TabsList>
          </Tabs>

          <span className="text-xs text-zinc-500">
            Click image to inspect full view
          </span>
        </div>

        {/* Gallery Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-2">
          {filtered.length === 0 ? (
            <div className="col-span-full py-16 text-center text-xs text-zinc-500">
              No evidence snapshots found matching current filter.
            </div>
          ) : (
            filtered.map((item) => {
              const imgUrl = item.snapshot ? (item.snapshot.startsWith('/') ? item.snapshot : `/snapshots/${item.snapshot}`) : null;
              const isPest = item.category === 'pest';
              const title = LABEL_MAP[item.label] || item.label;

              return (
                <Card
                  key={item.id}
                  className="overflow-hidden bg-zinc-900 border-zinc-800 cursor-pointer hover:border-zinc-700 transition-all flex flex-col p-0"
                  onClick={() => imgUrl && onZoomImage(imgUrl)}
                >
                  <div className="relative aspect-video bg-black">
                    {imgUrl ? (
                      <img
                        src={imgUrl}
                        alt={title}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-zinc-600 text-xs">
                        No Preview
                      </div>
                    )}

                    <div className="absolute top-2 left-2 flex gap-1">
                      <Badge variant={isPest ? "destructive" : "warning"} className="h-4 px-1.5 py-0 text-[9px] font-bold">
                        {isPest ? 'PEST' : 'PPE'}
                      </Badge>
                      {item.confidence && (
                        <Badge variant="outline" className="h-4 px-1 py-0 text-[9px] font-mono bg-black/60 text-zinc-300 border-zinc-700">
                          {Math.round(item.confidence * 100)}%
                        </Badge>
                      )}
                    </div>

                    <div className="absolute bottom-2 right-2 bg-black/70 p-1 rounded-md text-zinc-300 opacity-0 group-hover:opacity-100 transition-opacity">
                      <ZoomIn className="h-3.5 w-3.5" />
                    </div>
                  </div>

                  <div className="p-2.5 flex items-center justify-between text-xs">
                    <div>
                      <div className="font-semibold text-white">{title}</div>
                      <div className="text-[10px] text-zinc-400 mt-0.5">
                        {item.camera_name || 'Kitchen'} · {item.timestamp ? new Date(item.timestamp).toLocaleTimeString() : ''}
                      </div>
                    </div>

                    <Button
                      variant={item.acknowledged ? "ghost" : "outline"}
                      size="sm"
                      className={`h-6 px-2 text-[10px] gap-1 ${item.acknowledged ? 'text-zinc-500' : 'text-zinc-300 border-zinc-700 hover:bg-zinc-800'}`}
                      onClick={(e) => handleAcknowledge(item.id, e)}
                    >
                      <CheckCircle2 className="h-3 w-3" />
                      <span>{item.acknowledged ? 'Reviewed' : 'Review'}</span>
                    </Button>
                  </div>
                </Card>
              );
            })
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
