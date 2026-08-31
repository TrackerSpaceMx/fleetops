import React, { useEffect, useState } from 'react';
import { ChevronRight, UploadCloud, Check, X, AlertCircle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'framer-motion';
import { authFetch } from '../lib/auth';

const API = 'https://fleetops-space.com.mx';

export function FuelRegistration() {
  const [formData, setFormData] = useState({
    unidad: '',
    conductor: '',
    proveedor: '',
    tipo: 'DIESEL',
    fecha: new Date().toISOString().slice(0, 16),
    odometro: '',
    litros: '',
    precio: '',
    tanqueLleno: false,
    notas: ''
  });

  const fuelOptions = [
    { label: 'DIESEL', value: 'DIESEL' },
    { label: 'GASOLINA COMÚN', value: 'GASOLINA_COMUN' },
    { label: 'GASOLINA PREMIUM', value: 'GASOLINA_PREMIUM' }
  ];

  const [errors, setErrors] = useState<Record<string, boolean>>({});
  const [showConfirm, setShowConfirm] = useState(false);
  const [total, setTotal] = useState(0);

  const [vehicles, setVehicles] = useState<any[]>([]);
  const [selectedVehicle, setSelectedVehicle] = useState<any>(null);
  const [lastOdometer, setLastOdometer] = useState<number | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [ticketUrl, setTicketUrl] = useState<string>('');
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [vehiclesLoading, setVehiclesLoading] = useState(true);
  const [manualUnidad, setManualUnidad] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;
    setFile(selectedFile);
    setTicketUrl('');
    const fileURL = URL.createObjectURL(selectedFile);
    setPreview(fileURL);
  };

  useEffect(() => {
    const fetchVehicles = async () => {
      setVehiclesLoading(true);
      try {
        const res = await authFetch(`${API}/api/fleet/vehicles`);
        const data = await res.json();
        const list = data.vehicles || [];
        setVehicles(list);
        // Si no llegó ninguna unidad desde el GPS (ej. Fulltrack sin credenciales
        // válidas), activamos automáticamente el modo manual para no bloquear el registro.
        if (list.length === 0) setManualUnidad(true);
      } catch (error) {
        console.error('Error cargando vehículos:', error);
        toast.error('No se pudo cargar la lista de unidades desde el GPS. Puedes escribir la unidad manualmente.');
        setManualUnidad(true);
      } finally {
        setVehiclesLoading(false);
      }
    };
    fetchVehicles();
  }, []);

  // Auto-calculate total
  useEffect(() => {
    const lts = parseFloat(formData.litros) || 0;
    const price = parseFloat(formData.precio) || 0;
    setTotal(lts * price);
  }, [formData.litros, formData.precio]);

  const handleSave = () => {
    const newErrors: Record<string, boolean> = {};
    if (!formData.unidad) newErrors.unidad = true;
    if (!formData.conductor) newErrors.conductor = true;
    if (!formData.proveedor) newErrors.proveedor = true;
    if (!formData.odometro) newErrors.odometro = true;
    if (!formData.litros) newErrors.litros = true;
    if (!formData.precio) newErrors.precio = true;
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      toast.error('Por favor completa todos los campos obligatorios');
      return;
    }
    setErrors({});
    setShowConfirm(true);
  };

  const confirmSave = async () => {
    setSaving(true);
    try {
      let fotoUrl = ticketUrl;

      // 1️⃣ Subir ticket a S3 si hay archivo y no se subió aún
      // Si falla (ej. S3 no configurado en el servidor), no bloqueamos el
      // registro de la carga — avisamos y seguimos guardando sin foto.
      if (file && !fotoUrl) {
        setUploading(true);
        try {
          const formPayload = new FormData();
          formPayload.append('vehicle_id', formData.unidad);
          formPayload.append('file', file);

          const uploadRes = await authFetch(`${API}/api/fuel/upload-ticket`, {
            method: 'POST',
            body: formPayload,
          });

          if (!uploadRes.ok) {
            const err = await uploadRes.json().catch(() => ({}));
            throw new Error(err.detail || `Error ${uploadRes.status} al subir el ticket`);
          }

          const uploadData = await uploadRes.json();
          fotoUrl = uploadData.url;
          setTicketUrl(fotoUrl);
        } catch (uploadError: any) {
          console.error(uploadError);
          toast.warning(
            uploadError.message?.includes('S3')
              ? 'No se pudo subir la foto (almacenamiento no configurado). Se guardará la carga sin foto.'
              : 'No se pudo subir la foto del ticket. Se guardará la carga sin foto.'
          );
          fotoUrl = '';
        } finally {
          setUploading(false);
        }
      }

      // 2️⃣ Registrar la carga con la URL del ticket
      await authFetch(`${API}/api/fuel/load`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vehicle_id:      formData.unidad,
          conductor:       formData.conductor,
          proveedor:       formData.proveedor,
          tipo:            formData.tipo,
          fecha:           new Date(formData.fecha).toISOString(),
          liters:          parseFloat(formData.litros),
          price_per_liter: parseFloat(formData.precio),
          odometro_actual: parseFloat(formData.odometro),
          tanque_lleno:    formData.tanqueLleno,
          foto_ticket_url: fotoUrl,
        }),
      });

      toast.success('Carga de combustible guardada exitosamente');
      setShowConfirm(false);

      setFormData({
        unidad: '',
        conductor: '',
        proveedor: '',
        tipo: 'DIESEL',
        fecha: new Date().toISOString().slice(0, 16),
        odometro: '',
        litros: '',
        precio: '',
        tanqueLleno: false,
        notas: ''
      });
      setFile(null);
      setPreview(null);
      setTicketUrl('');

    } catch (error: any) {
      console.error(error);
      toast.error(error.message || 'Error al guardar la carga');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-8 max-w-[1200px] mx-auto animate-fade-in-up">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
          <span>Inicio</span>
          <ChevronRight className="w-4 h-4" />
          <span>Combustible</span>
          <ChevronRight className="w-4 h-4" />
          <span className="text-gray-900 font-medium">Nueva Carga</span>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">
          Nueva Carga de Combustible
        </h1>
      </div>

      {/* Form Card */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-8 grid grid-cols-1 lg:grid-cols-2 gap-12">
          {/* Left Column */}
          <div className="space-y-6">
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider">
                  Unidad
                </label>
                {vehicles.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setManualUnidad((v) => !v)}
                    className="text-xs font-medium text-blue-500 hover:text-blue-600"
                  >
                    {manualUnidad ? 'Elegir de la lista' : '¿No aparece tu unidad? Escríbela'}
                  </button>
                )}
              </div>

              {vehiclesLoading ? (
                <div className="w-full p-3 rounded-lg border border-gray-200 text-sm text-gray-400 flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" /> Cargando unidades…
                </div>
              ) : manualUnidad ? (
                <input
                  type="text"
                  placeholder="Ej. TM-04"
                  className={`w-full p-3 rounded-lg border ${errors.unidad ? 'border-danger bg-danger/5' : 'border-gray-200'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                  value={formData.unidad}
                  onChange={(e) => setFormData({ ...formData, unidad: e.target.value })}
                />
              ) : (
                <select
                  className={`w-full p-3 rounded-lg border ${errors.unidad ? 'border-danger bg-danger/5' : 'border-gray-200'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                  value={formData.unidad}
                  onChange={(e) => {
                    const vehicleId = e.target.value;
                    const vehicle = vehicles.find((v) => v.ras_vei_id === vehicleId);
                    setSelectedVehicle(vehicle);
                    setFormData({ ...formData, unidad: vehicleId, conductor: vehicle?.ras_mot_nome || '' });
                    setLastOdometer(Number(vehicle?.ras_eve_hodometro || 0));
                  }}
                >
                  <option value="">Seleccionar unidad...</option>
                  {vehicles.map((v) => (
                    <option key={v.ras_vei_id} value={v.ras_vei_id}>
                      {v.ras_vei_placa}
                    </option>
                  ))}
                </select>
              )}

              {vehicles.length === 0 && !vehiclesLoading && (
                <p className="text-xs text-amber-600 mt-1.5 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> No se pudo obtener la lista de unidades desde el GPS (Fulltrack). Escribe el número económico manualmente.
                </p>
              )}
              {errors.unidad && (
                <p className="text-danger text-xs mt-1 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" /> Requerido
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Conductor
              </label>
              <input
                type="text"
                className={`w-full p-3 rounded-lg border ${errors.conductor ? 'border-danger bg-danger/5' : 'border-gray-200'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                value={formData.conductor}
                onChange={(e) => setFormData({ ...formData, conductor: e.target.value })}
                placeholder="Nombre del conductor"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Proveedor de Combustible
              </label>
              <select
                className={`w-full p-3 rounded-lg border ${errors.proveedor ? 'border-danger bg-danger/5' : 'border-gray-200'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                value={formData.proveedor}
                onChange={(e) => setFormData({ ...formData, proveedor: e.target.value })}
              >
                <option value="">Seleccionar proveedor...</option>
                <option value="pemex">Pemex</option>
                <option value="privada">Estación Privada</option>
                <option value="interna">Bomba Interna</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Tipo de Combustible
              </label>
              <div className="flex gap-2">
                {fuelOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setFormData((prev) => ({ ...prev, tipo: opt.value }))}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      formData.tipo === opt.value
                        ? 'bg-navy-500 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Fecha y Hora
              </label>
              <input
                type="datetime-local"
                className="w-full p-3 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={formData.fecha}
                onChange={(e) => setFormData({ ...formData, fecha: e.target.value })}
              />
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Odómetro Actual
              </label>
              <div className="relative">
                <input
                  type="number"
                  className={`w-full p-3 pr-12 rounded-lg border font-mono ${errors.odometro ? 'border-danger bg-danger/5' : 'border-gray-200'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                  value={formData.odometro}
                  onChange={(e) => setFormData({ ...formData, odometro: e.target.value })}
                  placeholder="0"
                />
                <span className="absolute right-4 top-3.5 text-gray-400 font-medium">km</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Último registro: {lastOdometer?.toLocaleString('es-MX') || '0'} km
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Litros Cargados
                </label>
                <input
                  type="number"
                  className={`w-full p-3 rounded-lg border font-mono ${errors.litros ? 'border-danger bg-danger/5' : 'border-gray-200'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                  value={formData.litros}
                  onChange={(e) => setFormData({ ...formData, litros: e.target.value })}
                  placeholder="0.00"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Precio por Litro
                </label>
                <div className="relative">
                  <span className="absolute left-4 top-3.5 text-gray-400 font-medium">$</span>
                  <input
                    type="number"
                    className={`w-full p-3 pl-8 rounded-lg border font-mono ${errors.precio ? 'border-danger bg-danger/5' : 'border-gray-200'} focus:outline-none focus:ring-2 focus:ring-blue-500`}
                    value={formData.precio}
                    onChange={(e) => setFormData({ ...formData, precio: e.target.value })}
                    placeholder="0.00"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Total Calculado
              </label>
              <div className="w-full p-4 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-between">
                <span className="text-blue-600 font-medium">Importe Total</span>
                <span className="text-2xl font-bold text-blue-700 font-mono tabular-nums">
                  ${total.toLocaleString('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                ¿Tanque Lleno?
              </label>
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setFormData({ ...formData, tanqueLleno: true })}
                  className={`flex-1 py-3 rounded-lg font-bold border-2 transition-colors ${formData.tanqueLleno ? 'border-success bg-success/10 text-success' : 'border-gray-200 text-gray-400 hover:border-gray-300'}`}
                >
                  SÍ
                </button>
                <button
                  onClick={() => setFormData({ ...formData, tanqueLleno: false })}
                  className={`flex-1 py-3 rounded-lg font-bold border-2 transition-colors ${!formData.tanqueLleno ? 'border-gray-400 bg-gray-100 text-gray-700' : 'border-gray-200 text-gray-400 hover:border-gray-300'}`}
                >
                  NO
                </button>
              </div>
            </div>
          </div>

          {/* Full Width */}
          <div className="col-span-1 lg:col-span-2 space-y-6 pt-6 border-t border-gray-100">
            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Foto del Ticket
              </label>
              <label className="w-full h-40 rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 flex flex-col items-center justify-center text-gray-500 hover:bg-gray-100 hover:border-blue-400 transition-colors cursor-pointer">
                <input
                  type="file"
                  accept="image/*,application/pdf"
                  className="hidden"
                  onChange={handleFileChange}
                />
                {!preview ? (
                  <>
                    <UploadCloud className="w-8 h-8 mb-2 text-gray-400" />
                    <p className="font-medium text-gray-700">Arrastra el ticket o toma una foto</p>
                    <p className="text-xs mt-1">Formatos: JPG, PNG, PDF</p>
                  </>
                ) : (
                  <>
                    {file?.type === 'application/pdf' ? (
                      <p className="text-sm font-medium text-gray-700">PDF seleccionado: {file.name}</p>
                    ) : (
                      <img src={preview} alt="preview" className="h-full object-contain rounded-lg" />
                    )}
                  </>
                )}
              </label>
              {file && (
                <p className="text-xs text-gray-400 mt-1">
                  📎 {file.name} — se subirá al confirmar
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Notas Adicionales
              </label>
              <textarea
                className="w-full p-3 rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[100px]"
                value={formData.notas}
                onChange={(e) => setFormData({ ...formData, notas: e.target.value })}
                placeholder="Observaciones sobre la carga..."
              />
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="p-6 bg-gray-50 border-t border-gray-100 flex justify-end gap-4">
          <button className="px-6 py-2.5 rounded-lg font-medium text-gray-600 hover:bg-gray-200 transition-colors">
            Cancelar
          </button>
          <button
            onClick={handleSave}
            className="px-6 py-2.5 rounded-lg font-medium bg-blue-500 text-white hover:bg-blue-600 transition-colors flex items-center gap-2 shadow-sm"
          >
            <Check className="w-4 h-4" />
            Guardar Carga
          </button>
        </div>
      </div>

      {/* Confirmation Modal */}
      <AnimatePresence>
        {showConfirm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-900/40 backdrop-blur-sm">
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-white rounded-xl shadow-xl max-w-md w-full overflow-hidden"
            >
              <div className="p-6 border-b border-gray-100 flex justify-between items-center">
                <h3 className="text-lg font-bold text-gray-900">Confirmar Carga</h3>
                <button onClick={() => setShowConfirm(false)} className="text-gray-400 hover:text-gray-600">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 space-y-4">
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">Unidad</span>
                  <span className="font-bold text-gray-900">{formData.unidad}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">Litros</span>
                  <span className="font-mono font-bold text-gray-900">{formData.litros} L</span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">Total</span>
                  <span className="font-mono font-bold text-blue-600">
                    ${total.toLocaleString('es-MX', { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="flex justify-between py-2 border-b border-gray-50">
                  <span className="text-gray-500">Odómetro</span>
                  <span className="font-mono font-bold text-gray-900">{formData.odometro} km</span>
                </div>
                {file && (
                  <div className="flex justify-between py-2 border-b border-gray-50">
                    <span className="text-gray-500">Ticket</span>
                    <span className="text-sm font-medium text-gray-700 truncate max-w-[200px]">
                      📎 {file.name}
                    </span>
                  </div>
                )}
              </div>
              <div className="p-6 bg-gray-50 flex gap-3">
                <button
                  onClick={() => setShowConfirm(false)}
                  disabled={saving}
                  className="flex-1 py-2.5 rounded-lg font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 transition-colors disabled:opacity-50"
                >
                  Editar
                </button>
                <button
                  onClick={confirmSave}
                  disabled={saving}
                  className="flex-1 py-2.5 rounded-lg font-medium text-white bg-blue-500 hover:bg-blue-600 transition-colors shadow-sm flex items-center justify-center gap-2 disabled:opacity-60"
                >
                  {saving ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {uploading ? 'Subiendo ticket...' : 'Guardando...'}
                    </>
                  ) : (
                    'Confirmar'
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
