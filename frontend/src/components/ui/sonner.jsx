import React from 'react';
import { Toaster as Sonner, toast } from 'sonner';

const Toaster = ({ ...props }) => {
  return (
    <Sonner
      theme="dark"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            'group toast group-[.toaster]:bg-zinc-900/95 group-[.toaster]:backdrop-blur-md group-[.toaster]:text-zinc-100 group-[.toaster]:border-zinc-800 group-[.toaster]:shadow-xl group-[.toaster]:rounded-xl font-sans text-sm',
          description: 'group-[.toast]:text-zinc-400 text-xs leading-relaxed',
          actionButton:
            'group-[.toast]:bg-white group-[.toast]:text-zinc-950 font-medium text-xs px-3 py-1.5 rounded-lg shadow-sm hover:bg-zinc-200 transition-colors',
          cancelButton:
            'group-[.toast]:bg-zinc-800 group-[.toast]:text-zinc-300 font-medium text-xs px-3 py-1.5 rounded-lg hover:bg-zinc-700 transition-colors',
        },
      }}
      {...props}
    />
  );
};

export { Toaster, toast };
