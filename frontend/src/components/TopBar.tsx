import React, { useEffect, useState } from 'react';
interface TopBarProps {
  title: string;
}
export function TopBar({ title }: TopBarProps) {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  const formattedDate = time.toLocaleDateString('es-MX', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
  const formattedTime = time.toLocaleTimeString('es-MX', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-8 sticky top-0 z-10 shadow-sm">
      <div className="flex items-center gap-4">
        <h2 className="text-xl font-bold text-gray-900 capitalize">{title}</h2>
        <div className="h-5 w-px bg-gray-300 mx-2"></div>
        <div className="flex items-center gap-2 text-sm text-gray-500 font-mono">
          <span className="w-2 h-2 rounded-full bg-success animate-live-pulse"></span>
          LIVE
        </div>
      </div>

      <div className="flex items-center gap-6">
        {/* Live Clock */}
        <div className="flex flex-col items-end text-right">
          <span className="text-sm font-bold text-gray-900 font-mono tabular-nums tracking-tight">
            {formattedTime}
          </span>
          <span className="text-xs text-gray-500 capitalize">
            {formattedDate}
          </span>
        </div>
      </div>
    </header>);

}