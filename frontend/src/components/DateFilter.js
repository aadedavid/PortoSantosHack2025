import React, { useState } from 'react';

const DateFilter = ({ onDateChange, currentStartDate, currentEndDate }) => {
  const [startDate, setStartDate] = useState(currentStartDate || '');
  const [endDate, setEndDate] = useState(currentEndDate || '');

  const handleApplyFilter = () => {
    onDateChange(startDate, endDate);
  };

  const handleClearFilter = () => {
    setStartDate('');
    setEndDate('');
    onDateChange('', '');
  };

  const presetRanges = [
    {
      label: 'Últimos 7 dias',
      start: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      end: new Date().toISOString().split('T')[0]
    },
    {
      label: 'Últimos 30 dias',
      start: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      end: new Date().toISOString().split('T')[0]
    },
    {
      label: 'Este mês',
      start: new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0],
      end: new Date().toISOString().split('T')[0]
    }
  ];

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-6">
      <h3 className="text-lg font-medium text-gray-900 mb-4">Filtrar por Período</h3>
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Data Inicial
          </label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Data Final
          </label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        
        <div className="flex space-x-2">
          <button
            onClick={handleApplyFilter}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            Aplicar
          </button>
          <button
            onClick={handleClearFilter}
            className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors"
          >
            Limpar
          </button>
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Períodos Rápidos
          </label>
          <select
            onChange={(e) => {
              const preset = presetRanges[e.target.value];
              if (preset) {
                setStartDate(preset.start);
                setEndDate(preset.end);
                onDateChange(preset.start, preset.end);
              }
            }}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Selecionar período</option>
            {presetRanges.map((range, index) => (
              <option key={index} value={index}>
                {range.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      
      {(startDate || endDate) && (
        <div className="mt-3 text-sm text-gray-600">
          Período selecionado: {startDate || 'Início'} até {endDate || 'Fim'}
        </div>
      )}
    </div>
  );
};

export default DateFilter;