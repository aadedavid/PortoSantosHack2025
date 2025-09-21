import React, { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import axios from "axios";
import "./App.css";
import { InfoIcon } from "./components/ui/tooltip";
import DateFilter from "./components/DateFilter";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// KPI Explanations
const KPI_EXPLANATIONS = {
  mae_eta: "MAE(ETA) - Mean Absolute Error: Erro médio absoluto em minutos entre o horário estimado de chegada (ETA) e o horário real de chegada (ATA). Quanto menor, melhor a precisão das previsões.",
  wb_ratio: "W/B Ratio - Waiting to Berth Ratio: Razão entre tempo de espera para atracar e tempo atracado. Calculado como (ATB-ATA)/(ATD-ATB). Quanto menor, mais eficiente o processo.",
  rcj: "RCJ - Berth Window Reliability: Percentual de atracações que ocorreram dentro da janela comprometida (±30 minutos do ETB). Meta: ≥85%.",
  conflicts: "Conflitos: Número de sobreposições detectadas entre navios no mesmo berço ou terminal. Zero é o ideal."
};

// Main Dashboard Component
const Dashboard = () => {
  const [vessels, setVessels] = useState([]);
  const [berthTimeline, setBerthTimeline] = useState({});
  const [conflicts, setConflicts] = useState([]);
  const [kpis, setKpis] = useState({});
  const [marineTraffic, setMarineTraffic] = useState([]);
  const [currentOps, setCurrentOps] = useState({});
  const [loading, setLoading] = useState(true);
  const [lastSync, setLastSync] = useState(null);
  const [dateFilter, setDateFilter] = useState({ start: '', end: '' });
  const [timelineInfo, setTimelineInfo] = useState({});
  const [isNowView, setIsNowView] = useState(false);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async (startDate = '', endDate = '') => {
    try {
      setLoading(true);
      
      // Build query parameters for date filtering
      const timelineParams = new URLSearchParams();
      if (startDate) timelineParams.append('start_date', startDate);
      if (endDate) timelineParams.append('end_date', endDate);
      
      const kpiParams = new URLSearchParams();
      if (startDate) kpiParams.append('start_date', startDate);
      if (endDate) kpiParams.append('end_date', endDate);
      
      // Load all dashboard data
      const requests = [
        axios.get(`${API}/vessels`),
        axios.get(`${API}/berths/timeline?${timelineParams.toString()}`),
        axios.get(`${API}/conflicts`),
        axios.get(`${API}/kpis?${kpiParams.toString()}`),
        axios.get(`${API}/marine-traffic/santos`).catch(() => ({ data: { vessels_approaching: [] } }))
      ];

      // Add current operations if this is "now" view
      if (startDate === new Date().toISOString().split('T')[0] && 
          endDate === new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().split('T')[0]) {
        requests.push(axios.get(`${API}/operations/now`).catch(() => ({ data: { current_operations: {} } })));
        setIsNowView(true);
      } else {
        setIsNowView(false);
      }

      const responses = await Promise.all(requests);
      const [vesselsRes, timelineRes, conflictsRes, kpisRes, marineRes, currentOpsRes] = responses;

      setVessels(vesselsRes.data);
      
      // Handle new timeline response format
      if (timelineRes.data.berth_timeline) {
        setBerthTimeline(timelineRes.data.berth_timeline);
        setTimelineInfo({
          total_vessels: timelineRes.data.total_vessels,
          date_filter: timelineRes.data.date_filter
        });
      } else {
        setBerthTimeline(timelineRes.data);
        setTimelineInfo({});
      }
      
      setConflicts(conflictsRes.data);
      setKpis(kpisRes.data);
      setMarineTraffic(marineRes.data.vessels_approaching || []);
      
      // Set current operations if available
      if (currentOpsRes) {
        setCurrentOps(currentOpsRes.data.current_operations || {});
      }
      
      setLastSync(new Date().toLocaleString('pt-BR'));
    } catch (error) {
      console.error('Erro ao carregar dados do dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  const syncExternalData = async () => {
    try {
      setLoading(true);
      await axios.post(`${API}/sync-external-data`);
      await loadDashboardData(dateFilter.start, dateFilter.end);
    } catch (error) {
      console.error('Erro ao sincronizar dados:', error);
    }
  };

  const syncHistoricalData = async () => {
    try {
      setLoading(true);
      await axios.get(`${API}/sync-historical-data?days_back=7`);
      await loadDashboardData(dateFilter.start, dateFilter.end);
    } catch (error) {
      console.error('Erro ao sincronizar dados históricos:', error);
    }
  };

  const handleDateChange = (startDate, endDate) => {
    setDateFilter({ start: startDate, end: endDate });
    loadDashboardData(startDate, endDate);
  };

  const openMarineTrafficLink = async (vesselId) => {
    try {
      const response = await axios.get(`${API}/marine-traffic/links/${vesselId}`);
      const links = response.data.marine_traffic_links;
      
      // Prefer details page, fallback to map
      const url = links.details || links.map_vessel || links.map_coords;
      
      if (url) {
        window.open(url, '_blank', 'noopener,noreferrer');
      } else {
        alert('Dados de rastreamento AIS não disponíveis para este navio');
      }
    } catch (error) {
      console.error('Erro ao abrir link MarineTraffic:', error);
      alert('Erro ao acessar dados de rastreamento');
    }
  };

  const openPortMapLink = async () => {
    try {
      const response = await axios.get(`${API}/marine-traffic/port-santos`);
      const portUrl = response.data.marine_traffic_links.port_map;
      
      if (portUrl) {
        window.open(portUrl, '_blank', 'noopener,noreferrer');
      }
    } catch (error) {
      console.error('Erro ao abrir mapa do porto:', error);
      // Fallback to direct Santos port URL
      window.open('https://www.marinetraffic.com/pt/ais/home/centerx:-46.3334/centery:-23.9534/zoom:11', '_blank');
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      'concluido': 'bg-green-500',
      'em_andamento': 'bg-blue-500', 
      'pendente': 'bg-yellow-500',
      'cancelado': 'bg-red-500',
      'atraso': 'bg-orange-500',
      'planejado': 'bg-gray-500'
    };
    return colors[status] || 'bg-gray-400';
  };

  const getPriorityColor = (priority) => {
    const colors = {
      'imediata': 'border-red-600 bg-red-50',
      'preferencial': 'border-orange-600 bg-orange-50',
      'prioritaria': 'border-yellow-600 bg-yellow-50',
      'sequencial': 'border-gray-600 bg-gray-50'
    };
    return colors[priority] || 'border-gray-400 bg-gray-50';
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Carregando dados do Porto...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Hub de Atracação</h1>
              <p className="text-sm text-gray-600">Porto de Santos - PCS</p>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-500">
                Última sincronização: {lastSync}
              </span>
              <button
                onClick={syncHistoricalData}
                className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition-colors text-sm"
                disabled={loading}
              >
                Dados Históricos
              </button>
              <button
                onClick={syncExternalData}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
                disabled={loading}
              >
                Sincronizar Dados
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        
        {/* Date Filter */}
        <DateFilter 
          onDateChange={handleDateChange}
          currentStartDate={dateFilter.start}
          currentEndDate={dateFilter.end}
        />

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="p-2 bg-blue-100 rounded-lg">
                <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <div className="ml-4 flex-1">
                <div className="flex items-center">
                  <p className="text-sm font-medium text-gray-600">MAE(ETA)</p>
                  <InfoIcon tooltip={KPI_EXPLANATIONS.mae_eta} className="ml-2" />
                </div>
                <p className="text-2xl font-semibold text-gray-900">
                  {kpis.mae_eta ? `${Math.round(kpis.mae_eta)} min` : 'N/A'}
                </p>
                {kpis.mae_eta && (
                  <p className="text-xs text-gray-500 mt-1">
                    Meta: Redução ≥30%
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="p-2 bg-green-100 rounded-lg">
                <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="ml-4 flex-1">
                <div className="flex items-center">
                  <p className="text-sm font-medium text-gray-600">W/B Ratio</p>
                  <InfoIcon tooltip={KPI_EXPLANATIONS.wb_ratio} className="ml-2" />
                </div>
                <p className="text-2xl font-semibold text-gray-900">
                  {kpis.wb_ratio ? kpis.wb_ratio.toFixed(2) : 'N/A'}
                </p>
                {kpis.wb_ratio && (
                  <p className="text-xs text-gray-500 mt-1">
                    Meta: Redução ≥15%
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="p-2 bg-purple-100 rounded-lg">
                <svg className="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="ml-4 flex-1">
                <div className="flex items-center">
                  <p className="text-sm font-medium text-gray-600">RCJ</p>
                  <InfoIcon tooltip={KPI_EXPLANATIONS.rcj} className="ml-2" />
                </div>
                <p className="text-2xl font-semibold text-gray-900">
                  {kpis.rcj_reliability ? `${Math.round(kpis.rcj_reliability)}%` : 'N/A'}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Meta: ≥85%
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center">
              <div className="p-2 bg-yellow-100 rounded-lg">
                <svg className="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="ml-4 flex-1">
                <div className="flex items-center">
                  <p className="text-sm font-medium text-gray-600">Conflitos</p>
                  <InfoIcon tooltip={KPI_EXPLANATIONS.conflicts} className="ml-2" />
                </div>
                <p className="text-2xl font-semibold text-gray-900">{conflicts.length}</p>
                <p className="text-xs text-gray-500 mt-1">
                  Detecção automática
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Period Information */}
        {kpis.periodo_inicio && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <div className="flex items-center">
              <svg className="w-5 h-5 text-blue-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clipRule="evenodd" />
              </svg>
              <div className="ml-3 text-sm text-blue-800">
                <strong>Período dos KPIs:</strong> {new Date(kpis.periodo_inicio).toLocaleDateString('pt-BR')} até {new Date(kpis.periodo_fim).toLocaleDateString('pt-BR')} 
                ({kpis.total_escalas} escalas analisadas)
              </div>
            </div>
          </div>
        )}

        {/* Current Operations - Real Time View */}
        {isNowView && Object.keys(currentOps).length > 0 && (
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4 mb-6">
            <div className="flex">
              <svg className="w-5 h-5 text-indigo-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
              </svg>
              <div className="ml-3 flex-1">
                <h3 className="text-sm font-medium text-indigo-800">Operações em Tempo Real - Últimas 24h</h3>
                <div className="mt-3 grid grid-cols-1 md:grid-cols-4 gap-4">
                  
                  {/* Recently Arrived */}
                  {currentOps.recently_arrived && currentOps.recently_arrived.length > 0 && (
                    <div className="bg-white rounded-lg p-3 shadow-sm">
                      <h4 className="font-medium text-green-800 mb-2">
                        Recém Chegados ({currentOps.recently_arrived.length})
                      </h4>
                      {currentOps.recently_arrived.slice(0, 3).map((vessel, idx) => (
                        <div key={idx} className="text-xs mb-2">
                          <div className="font-medium">{vessel.vessel}</div>
                          <div className="text-gray-600">{vessel.terminal}</div>
                          <div className="text-green-600">Há {vessel.hours_ago}h</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Currently Berthed */}
                  {currentOps.currently_berthed && currentOps.currently_berthed.length > 0 && (
                    <div className="bg-white rounded-lg p-3 shadow-sm">
                      <h4 className="font-medium text-blue-800 mb-2">
                        Atracados Agora ({currentOps.currently_berthed.length})
                      </h4>
                      {currentOps.currently_berthed.slice(0, 3).map((vessel, idx) => (
                        <div key={idx} className="text-xs mb-2">
                          <div className="font-medium">{vessel.vessel}</div>
                          <div className="text-gray-600">{vessel.terminal}</div>
                          <div className="text-blue-600">{vessel.hours_berthed}h atracado</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Arriving Soon */}
                  {currentOps.arriving_soon && currentOps.arriving_soon.length > 0 && (
                    <div className="bg-white rounded-lg p-3 shadow-sm">
                      <h4 className="font-medium text-yellow-800 mb-2">
                        Chegando Hoje ({currentOps.arriving_soon.length})
                      </h4>
                      {currentOps.arriving_soon.slice(0, 3).map((vessel, idx) => (
                        <div key={idx} className="text-xs mb-2">
                          <div className="font-medium">{vessel.vessel}</div>
                          <div className="text-gray-600">{vessel.terminal}</div>
                          <div className="text-yellow-600">Em {vessel.hours_until}h</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Departing Soon */}
                  {currentOps.departing_soon && currentOps.departing_soon.length > 0 && (
                    <div className="bg-white rounded-lg p-3 shadow-sm">
                      <h4 className="font-medium text-purple-800 mb-2">
                        Saindo Hoje ({currentOps.departing_soon.length})
                      </h4>
                      {currentOps.departing_soon.slice(0, 3).map((vessel, idx) => (
                        <div key={idx} className="text-xs mb-2">
                          <div className="font-medium">{vessel.vessel}</div>
                          <div className="text-gray-600">{vessel.terminal}</div>
                          <div className="text-purple-600">Em {vessel.hours_until}h</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Marine Traffic Alert */}
        {marineTraffic.length > 0 && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
            <div className="flex">
              <svg className="w-5 h-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-green-800">Navios se Aproximando (AIS)</h3>
                <div className="mt-2 text-sm text-green-700">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {marineTraffic.map(vessel => (
                      <div key={vessel.mmsi} className="bg-white rounded p-3 shadow-sm">
                        <div className="font-medium">{vessel.vessel_name}</div>
                        <div className="text-xs text-gray-600">
                          ETA: {new Date(vessel.eta).toLocaleString('pt-BR')}
                        </div>
                        <div className="text-xs text-gray-600">
                          Distância: {vessel.distance_to_port} km
                        </div>
                        <div className="text-xs text-gray-600">
                          Velocidade: {vessel.current_speed} nós
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Conflicts Alert */}
        {conflicts.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <div className="flex">
              <svg className="w-5 h-5 text-red-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Conflitos de Atracação Detectados</h3>
                <div className="mt-2 text-sm text-red-700">
                  {conflicts.map(conflict => (
                    <div key={conflict.id} className="mb-2">
                      <strong>{conflict.berco}:</strong> {conflict.descricao}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Gantt Chart by Berth */}
        <div className="bg-white rounded-lg shadow mb-8">
          <div className="px-6 py-4 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Timeline de Atracação por Berço</h2>
                <p className="text-sm text-gray-600">Visualização Gantt das operações portuárias</p>
              </div>
              {timelineInfo.total_vessels && (
                <div className="text-sm text-gray-500">
                  {timelineInfo.total_vessels} navios no período
                </div>
              )}
            </div>
          </div>
          <div className="p-6">
            {Object.entries(berthTimeline).map(([terminal, schedules]) => (
              <div key={terminal} className="mb-8">
                <h3 className="text-md font-medium text-gray-800 mb-4">{terminal}</h3>
                <div className="space-y-3">
                  {schedules.map(schedule => (
                    <div key={schedule.vessel_id} className={`border-l-4 p-4 rounded-lg ${getPriorityColor(schedule.priority)}`}>
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <div className="flex items-center space-x-3">
                            <h4 className="font-medium text-gray-900">{schedule.vessel_name}</h4>
                            <span className={`px-2 py-1 rounded-full text-xs text-white ${getStatusColor(schedule.status)}`}>
                              {schedule.status.toUpperCase()}
                            </span>
                            <span className="text-xs bg-gray-100 px-2 py-1 rounded">
                              {schedule.priority.toUpperCase()}
                            </span>
                          </div>
                          <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm text-gray-600">
                            <div>
                              <span className="font-medium">ETB:</span> {schedule.etb ? new Date(schedule.etb).toLocaleString('pt-BR', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                            </div>
                            <div>
                              <span className="font-medium">ATB:</span> {schedule.atb ? new Date(schedule.atb).toLocaleString('pt-BR', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'N/A'}
                            </div>
                            <div>
                              <span className="font-medium">ATD:</span> {schedule.atd ? new Date(schedule.atd).toLocaleString('pt-BR', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'Em operação'}
                            </div>
                            <div>
                              <span className="font-medium">Operação:</span> {schedule.operation_type || 'N/A'}
                            </div>
                          </div>
                          <div className="mt-2 text-sm">
                            <span className="font-medium">Agência:</span> {schedule.agency}
                            {schedule.observations && (
                              <div className="mt-1 text-gray-500">{schedule.observations}</div>
                            )}
                            <div className="mt-2 flex space-x-2">
                              <button
                                onClick={() => openMarineTrafficLink(schedule.vessel_id)}
                                className="text-xs bg-blue-100 hover:bg-blue-200 text-blue-800 px-2 py-1 rounded transition-colors"
                                title="Ver no MarineTraffic"
                              >
                                🌊 AIS
                              </button>
                              <button
                                onClick={() => openPortMapLink()}
                                className="text-xs bg-green-100 hover:bg-green-200 text-green-800 px-2 py-1 rounded transition-colors"
                                title="Ver mapa do porto"
                              >
                                🗺️ Mapa
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Vessel Status Table */}
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Status Detalhado dos Navios</h2>
            <p className="text-sm text-gray-600">Informações consolidadas R/E/O (Registrado/Estimado/Ocorrido)</p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Navio</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Terminal</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Prioridade</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ETA/ATA</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ETB/ATB</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Intercorrências</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">AIS</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {vessels.map(vessel => (
                  <tr key={vessel.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">{vessel.identificador_navio}</div>
                      <div className="text-sm text-gray-500">{vessel.agencia_maritima}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {vessel.terminal}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 py-1 rounded-full text-xs text-white ${getStatusColor(vessel.status)}`}>
                        {vessel.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="text-xs bg-gray-100 px-2 py-1 rounded">
                        {vessel.prioridade_rap.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      <div>
                        {(vessel.eta?.estimado || vessel.eta?.registrado) && (
                          <div>ETA: {new Date(vessel.eta.estimado || vessel.eta.registrado).toLocaleString('pt-BR', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</div>
                        )}
                        {vessel.ata && (
                          <div className="text-green-600">ATA: {new Date(vessel.ata).toLocaleString('pt-BR', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      <div>
                        {vessel.etb?.estimado && (
                          <div>ETB: {new Date(vessel.etb.estimado).toLocaleString('pt-BR', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</div>
                        )}
                        {vessel.atb && (
                          <div className="text-green-600">ATB: {new Date(vessel.atb).toLocaleString('pt-BR', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {vessel.intercorrencias || 'Nenhuma'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

// Navigation Component
const Navigation = () => {
  return (
    <nav className="bg-blue-800 text-white p-4">
      <div className="max-w-7xl mx-auto flex justify-between items-center">
        <Link to="/" className="text-xl font-bold">Hub de Atracação - Santos</Link>
        <div className="space-x-4">
          <Link to="/" className="hover:text-blue-200">Dashboard</Link>
          <Link to="/vessels" className="hover:text-blue-200">Navios</Link>
          <Link to="/berths" className="hover:text-blue-200">Berços</Link>
        </div>
      </div>
    </nav>
  );
};

// Vessels Page
const VesselsPage = () => {
  return (
    <div>
      <Navigation />
      <div className="p-8">
        <h2 className="text-2xl font-bold mb-4">Gestão de Navios</h2>
        <div className="bg-white rounded-lg shadow p-6">
          <p>Página detalhada de gestão de navios em desenvolvimento...</p>
        </div>
      </div>
    </div>
  );
};

// Berths Page
const BerthsPage = () => {
  return (
    <div>
      <Navigation />
      <div className="p-8">
        <h2 className="text-2xl font-bold mb-4">Gestão de Berços</h2>
        <div className="bg-white rounded-lg shadow p-6">
          <p>Página detalhada de gestão de berços em desenvolvimento...</p>
        </div>
      </div>
    </div>
  );
};

// Main App Component
function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/vessels" element={<VesselsPage />} />
          <Route path="/berths" element={<BerthsPage />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;