import React from 'react';
import {
  LayoutDashboard,
  Truck,
  Fuel,
  Scale,
  BarChart3,
  Bell,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight } from
'lucide-react';
import { useAuth } from '../lib/auth';
interface SidebarProps {
  activePage: string;
  setActivePage: (page: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}
export function Sidebar({ activePage, setActivePage, collapsed, onToggleCollapse }: SidebarProps) {
  const { user, logout } = useAuth();
  const initials = (user?.nombre || user?.username || '??')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const navItems = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: LayoutDashboard
  },
  {
    id: 'flota',
    label: 'Flota',
    icon: Truck
  },
  {
    id: 'combustible',
    label: 'Combustible',
    icon: Fuel
  },
  {
    id: 'bascula',
    label: 'Báscula',
    icon: Scale
  },
  {
    id: 'reportes',
    label: 'Reportes',
    icon: BarChart3
  },
  {
    id: 'alertas',
    label: 'Alertas',
    icon: Bell
  },
  {
    id: 'configuracion',
    label: 'Configuración',
    icon: Settings
  }].filter((item) => item.id !== 'configuracion' || user?.rol === 'admin');

  return (
    <aside className={`${collapsed ? 'w-20' : 'w-64'} bg-navy-500 h-screen flex flex-col fixed left-0 top-0 text-white shadow-xl z-20 transition-all duration-200`}>
      {/* Logo Area */}
      <div className={`h-16 flex items-center border-b border-navy-400/30 relative ${collapsed ? 'justify-center px-2' : 'justify-between px-6'}`}>
        {collapsed ? (
          <div className="w-6 h-6 bg-blue-500 rounded-md flex items-center justify-center shrink-0">
            <Truck className="w-4 h-4 text-white" />
          </div>
        ) : (
          <div className="flex flex-col justify-center min-w-0">
            <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
              <div className="w-6 h-6 bg-blue-500 rounded-md flex items-center justify-center shrink-0">
                <Truck className="w-4 h-4 text-white" />
              </div>
              FLEETOPS
            </h1>
            <span className="text-[10px] text-blue-200 tracking-widest uppercase font-semibold mt-0.5 truncate">
              Tersa Mundi S.A. de C.V.
            </span>
          </div>
        )}
        <button
          onClick={onToggleCollapse}
          title={collapsed ? 'Expandir menú' : 'Contraer menú'}
          className={`shrink-0 w-6 h-6 flex items-center justify-center rounded-md text-blue-300 hover:text-white hover:bg-navy-400/40 transition-colors ${collapsed ? 'absolute -right-3 top-1/2 -translate-y-1/2 bg-navy-500 border border-navy-400/50' : ''}`}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-6 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = activePage === item.id;
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => setActivePage(item.id)}
              title={collapsed ? item.label : undefined}
              className={`w-full flex items-center rounded-lg transition-all duration-200 group ${collapsed ? 'justify-center px-0 py-2.5' : 'justify-between px-3 py-2.5'} ${isActive ? 'bg-blue-500 text-white shadow-md' : 'text-blue-100 hover:bg-navy-400/40 hover:text-white'}`}>
              
              <div className={`flex items-center ${collapsed ? '' : 'gap-3'}`}>
                <Icon
                  className={`w-5 h-5 shrink-0 ${isActive ? 'text-white' : 'text-blue-300 group-hover:text-white'}`} />
                
                {!collapsed && <span className="font-medium text-sm">{item.label}</span>}
              </div>
            </button>);

        })}
      </nav>

      {/* User Profile */}
      <div className="p-4 border-t border-navy-400/30">
        <div className={`flex items-center rounded-lg hover:bg-navy-400/20 transition-colors group ${collapsed ? 'flex-col gap-2 px-0 py-2' : 'gap-3 px-2 py-2'}`}>
          <div className="w-9 h-9 rounded-full bg-navy-400 flex items-center justify-center text-sm font-bold border border-navy-400/50 shrink-0" title={collapsed ? (user?.nombre || user?.username) : undefined}>
            {initials}
          </div>
          {!collapsed && (
            <div className="flex flex-col text-left min-w-0 flex-1">
              <span className="text-sm font-semibold text-white truncate">
                {user?.nombre || user?.username}
              </span>
              <span className="text-xs text-blue-300 capitalize">
                {user?.rol === 'admin' ? 'Administrador' : 'Operador'}
              </span>
            </div>
          )}
          <button
            onClick={logout}
            title="Cerrar sesión"
            className="shrink-0 w-8 h-8 flex items-center justify-center rounded-lg text-blue-300 hover:text-white hover:bg-danger/80 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>);

}