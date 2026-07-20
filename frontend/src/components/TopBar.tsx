import React, { useEffect, useState } from 'react';
import { Bell, Search, ChevronDown } from 'lucide-react';
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

        <div className="h-8 w-px bg-gray-200"></div>

        {/* Actions */}
        <div className="flex items-center gap-4">
          <button className="text-gray-400 hover:text-gray-600 transition-colors">
            <Search className="w-5 h-5" />
          </button>

          <button className="relative text-gray-400 hover:text-gray-600 transition-colors">
            <Bell className="w-5 h-5" />
            <span className="absolute -top-1 -right-1 w-4 h-4 bg-danger text-white text-[10px] font-bold flex items-center justify-center rounded-full border-2 border-white">
              3
            </span>
          </button>

          <button className="flex items-center gap-2 hover:bg-gray-50 p-1 pr-2 rounded-full transition-colors border border-transparent hover:border-gray-200">
            <img
              src="https://i.pravatar.cc/150?u=admin"
              alt="User avatar"
              className="w-8 h-8 rounded-full border border-gray-200" />
            
            <ChevronDown className="w-4 h-4 text-gray-500" />
          </button>
        </div>
      </div>
    </header>);

}