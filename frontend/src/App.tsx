import React, { useState } from 'react';
import { Toaster } from 'sonner';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { Dashboard } from './pages/Dashboard';
import { FuelRegistration } from './pages/FuelRegistration';
import { VehicleDetail } from './pages/VehicleDetail';
import { Alerts } from './pages/Alerts';
import Reports from './pages/Reports';

export function App() {
  const [activePage, setActivePage]           = useState('dashboard');
  const [selectedVehicleId, setSelectedVehicleId] = useState<string | undefined>();

  const pageTitles: Record<string, string> = {
    dashboard:    'Mission Control',
    flota:        'Gestión de Flota',
    combustible:  'Control de Combustible',
    'nueva-carga':'Nueva Carga de Combustible',
    bascula:      'Registro de Báscula',
    rutas:        'Monitoreo de Rutas',
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
      <Sidebar activePage={activePage} setActivePage={setActivePage} />

      <div className="flex-1 flex flex-col ml-64 h-full relative">
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
