import React, { useState } from 'react';
import { Toaster } from 'sonner';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { Dashboard } from './pages/Dashboard';
import { FuelRegistration } from './pages/FuelRegistration';
import { VehicleDetail } from './pages/VehicleDetail';
import { Alerts } from './pages/Alerts';
import Reports from './pages/Reports';
import { Bascula } from './pages/Bascula';
import { Configuracion } from './pages/Configuracion';
import { Login } from './pages/Login';
import { AuthProvider, useAuth } from './lib/auth';

export function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

function AppShell() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-surface text-gray-400">
        Cargando…
      </div>
    );
  }

  if (!user) {
    return (
      <>
        <Toaster position="bottom-right" richColors />
        <Login />
      </>
    );
  }

  return <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const [activePage, setActivePage]           = useState('dashboard');
  const [selectedVehicleId, setSelectedVehicleId] = useState<string | undefined>();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const pageTitles: Record<string, string> = {
    dashboard:    'Mission Control',
    flota:        'Gestión de Flota',
    combustible:  'Control de Combustible',
    'nueva-carga':'Nueva Carga de Combustible',
    bascula:      'Registro de Báscula',
    reportes:     'Generador de Reportes',
    alertas:      'Centro de Alertas',
    configuracion:'Configuración del Sistema',
  };

  // Navegación centralizada — cualquier página puede pasar un vehicleId opcional
  const handleNavigate = (page: string, vehicleId?: string) => {
    if (vehicleId) setSelectedVehicleId(vehicleId);
    setActivePage(page);
  };

  return (
    <div className="flex h-screen w-full bg-surface overflow-hidden font-sans">
      <Toaster position="bottom-right" richColors />
      <Sidebar
        activePage={activePage}
        setActivePage={setActivePage}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
      />

      <div className={`flex-1 flex flex-col h-full relative transition-all duration-200 ${sidebarCollapsed ? 'ml-20' : 'ml-64'}`}>
        <TopBar title={pageTitles[activePage] || 'Dashboard'} />

        <main className="flex-1 overflow-y-auto overflow-x-hidden">
          {activePage === 'dashboard' ? (
            <Dashboard onNavigate={handleNavigate} />
          ) : activePage === 'combustible' ? (
            <FuelRegistration />
          ) : activePage === 'nueva-carga' ? (
            <FuelRegistration />
          ) : activePage === 'flota' ? (
            <VehicleDetail onNavigate={handleNavigate} vehicleId={selectedVehicleId} />
          ) : activePage === 'alertas' ? (
            <Alerts />
          ) : activePage === 'reportes' ? (
            <Reports />
          ) : activePage === 'bascula' ? (
            <Bascula />
          ) : activePage === 'configuracion' ? (
            <Configuracion />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 flex-col gap-4">
              <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mb-2">
                <span className="text-2xl">🚧</span>
              </div>
              <h2 className="text-xl font-medium text-gray-600">Módulo en construcción</h2>
              <p className="text-sm">
                El módulo de{' '}
                <span className="font-bold text-gray-700 capitalize">{activePage}</span>{' '}
                estará disponible pronto.
              </p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
