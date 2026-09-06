'use client';

import { useEffect, useState } from 'react';
import { Info, CheckCircle, AlertCircle, X } from 'lucide-react';

export interface ToastProps {
  message: string;
  type?: 'info' | 'success' | 'warning';
  onClose?: () => void;
}

export function Toast({ message, type = 'info', onClose }: ToastProps) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setVisible(false);
      onClose?.();
    }, 5000);
    return () => window.clearTimeout(timer);
  }, [onClose]);

  if (!visible) return null;

  const iconMap = {
    info: Info,
    success: CheckCircle,
    warning: AlertCircle,
  };
  const Icon = iconMap[type];
  const colorClass = {
    info: 'text-info',
    success: 'text-success',
    warning: 'text-warning',
  }[type];

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed top-16 right-4 z-50 max-w-sm w-[calc(100%-2rem)] bg-surface border border-border shadow-kt-md rounded-md p-4 flex items-start gap-3"
    >
      <Icon size={20} className={`${colorClass} shrink-0`} aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text-primary">{message}</p>
      </div>
      <button
        type="button"
        onClick={() => {
          setVisible(false);
          onClose?.();
        }}
        aria-label="Fermer"
        className="shrink-0 text-text-tertiary hover:text-text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 rounded-sm"
      >
        <X size={16} aria-hidden="true" />
      </button>
    </div>
  );
}
