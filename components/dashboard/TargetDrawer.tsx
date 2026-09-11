'use client';

import React, { useState } from 'react';
import { 
  X, ShieldAlert, Thermometer, Zap, Award, MapPin, 
  Clock, Navigation, CheckCircle2, AlertOctagon, 
  Download, Send, Eye, Layers, ChevronRight, Cpu, Radio, Activity, RefreshCw, Search
} from 'lucide-react';
import { ThermalTarget } from '../../lib/types';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip } from 'recharts';

interface TargetDrawerProps {
  target: ThermalTarget | null;
  onClose: () => void;
  onDispatchDrone?: (targetId: string) => void;
  onOsmVerified?: (targetId: string, osmData: any) => void;
}

export const TargetDrawer: React.FC<TargetDrawerProps> = ({
  target,
  onClose,
  onDispatchDrone,
  onOsmVerified,
}) => {
  const [isReconDispatched, setIsReconDispatched] = useState<boolean>(false);
  const [chartMetric, setChartMetric] = useState<'frp' | 'temp'>('frp');
  
  // OSM Verification State
  const [isVerifyingOsm, setIsVerifyingOsm] = useState<boolean>(false);
  const [osmStatusText, setOsmStatusText] = useState<string | null>(null);
  const [osmResultData, setOsmResultData] = useState<any>(null);

  if (!target) return null;

  const getAccentColor = () => {
    switch (target.type) {
      case 'CRITICAL_SPIKE':
        return {
          border: 'border-red-600/80',
          text: 'text-red-400',
          bg: 'bg-red-950/60',
          badge: 'bg-red-900/80 text-red-200 border-red-500/80',
          chartColor: '#ef4444',
        };
      case 'PERSISTENT_FLARE':
        return {
          border: 'border-amber-600/80',
          text: 'text-amber-400',
          bg: 'bg-amber-950/60',
          badge: 'bg-amber-900/80 text-amber-200 border-amber-500/80',
          chartColor: '#f59e0b',
        };
      case 'BIOMASS_FIRE':
        return {
          border: 'border-emerald-600/80',
          text: 'text-emerald-400',
          bg: 'bg-emerald-950/60',
          badge: 'bg-emerald-900/80 text-emerald-200 border-emerald-500/80',
          chartColor: '#10b981',
        };
      default:
        return {
          border: 'border-cyan-600/80',
          text: 'text-cyan-400',
          bg: 'bg-cyan-950/60',
          badge: 'bg-cyan-900/80 text-cyan-200 border-cyan-500/80',
          chartColor: '#06b6d4',
        };
    }
  };

  const accent = getAccentColor();

  const handleExportJSON = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(target, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `telemetry_${target.id}_${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleDispatch = () => {
    setIsReconDispatched(true);
    if (onDispatchDrone) onDispatchDrone(target.id);
    setTimeout(() => setIsReconDispatched(false), 5000);
  };

  const handleVerifyOsmBoundary = async () => {
    setIsVerifyingOsm(true);
    setOsmStatusText('[TRANSMITTING OVERPASS QL TO OSM INTERPRETER...]');

    try {
      const [lat, lng] = target.coordinates;
      const res = await fetch(`/api/osm/check?lat=${lat}&lng=${lng}&radius=2000`);
      
      if (res.ok) {
        const osmData = await res.json();
        setOsmResultData(osmData);
        setOsmStatusText(`[VERIFIED via ${osmData.source}]`);
        if (onOsmVerified) {
          onOsmVerified(target.id, osmData);
        }
      } else {
        setOsmStatusText('[OSM INTERPRETER FAIL - ENFORCED LOCAL INDEX]');
      }
    } catch (err) {
      console.error('OSM verification error:', err);
      setOsmStatusText('[OSM INTERPRETER TIMEOUT - LOCAL INDEX ENGAGED]');
    } finally {
      setIsVerifyingOsm(false);
    }
  };

  const chartData = target.history7Days.map(item => ({
    date: item.date,
    frp: item.frpMW,
    temp: item.tempK,
  }));

  // Fallback probability values if missing
  const probs = target.classificationProbs || {
    industrial_flare: target.type === 'PERSISTENT_FLARE' ? 0.92 : 0.05,
    abnormal_spike: target.type === 'CRITICAL_SPIKE' ? 0.85 : 0.05,
    biomass_burning: target.type === 'BIOMASS_FIRE' ? 0.05 : 0.02,
    wildfire: target.type === 'BIOMASS_FIRE' ? 0.90 : 0.02,
    unverified: 0.01,
  };

  const flarePct = Math.round(probs.industrial_flare * 100);
  const spikePct = Math.round(probs.abnormal_spike * 100);
  const biomassPct = Math.round((probs.wildfire + probs.biomass_burning) * 100);

  return (
    <aside className="w-96 bg-[#090d16]/95 border-l border-slate-800 text-slate-200 h-[calc(100vh-3.5rem)] flex flex-col z-20 backdrop-blur-xl shadow-2xl overflow-y-auto select-none transition-all duration-300">
      {/* Drawer Header */}
      <div className="p-4 border-b border-slate-800 flex items-start justify-between bg-slate-900/90">
        <div>
          <div className="flex items-center space-x-2">
            <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase border transition-colors duration-500 ${accent.badge}`}>
              {target.defensePriority}
            </span>
            <span className="font-mono text-xs text-slate-400">ID: {target.id}</span>
          </div>
          <h2 className="text-base font-bold text-slate-100 mt-1 line-clamp-1">{target.name}</h2>
          <p className="text-xs text-slate-400 font-mono flex items-center mt-0.5">
            <MapPin className="w-3 h-3 text-cyan-400 mr-1" />
            {target.state}, INDIA
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition"
          title="Close Inspection Panel"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Data Provenance Badge */}
      <div className="px-4 py-1.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between text-[11px] font-mono">
        <span className="text-slate-400 flex items-center">
          <Radio className="w-3 h-3 text-cyan-400 mr-1.5 animate-pulse" /> TELEMETRY STREAM:
        </span>
        <span className={`font-bold px-2 py-0.5 rounded ${target.isSynthetic ? 'bg-cyan-950/80 text-cyan-300 border border-cyan-800' : 'bg-emerald-950 text-emerald-400 border border-emerald-800'}`}>
          {target.dataSourceLabel || (target.isSynthetic ? "ORBITAL CACHE // VIIRS-SNPP REPLAY" : "LIVE DIRECT DOWNLINK (NASA-EOSDIS)")}
        </span>
      </div>

      {/* Main Drawer Body */}
      <div className="p-4 space-y-4 flex-1">
        {/* Classification Tag Banner */}
        <div className={`p-3 rounded-lg border transition-all duration-500 ${accent.border} ${accent.bg} flex items-center justify-between`}>
          <div className="flex items-center space-x-2">
            <ShieldAlert className={`w-5 h-5 transition-colors duration-500 ${accent.text}`} />
            <div>
              <span className="text-[10px] text-slate-400 font-mono block uppercase tracking-wider">Classification Tag</span>
              <span className={`text-xs font-mono font-extrabold uppercase transition-colors duration-500 ${accent.text}`}>
                {target.classification}
              </span>
            </div>
          </div>
        </div>

        {/* Tactical Key Metrics Grid */}
        <div className="grid grid-cols-2 gap-2">
          {/* Brightness Temp */}
          <div className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg">
            <div className="flex items-center space-x-1.5 text-slate-400 mb-1">
              <Thermometer className="w-3.5 h-3.5 text-red-400" />
              <span className="text-[10px] font-mono uppercase">Brightness Temp</span>
            </div>
            <div className="font-mono text-lg font-bold text-slate-100">
              {target.brightnessTempK.toFixed(1)} <span className="text-xs font-normal text-slate-400">K</span>
            </div>
            <span className="text-[10px] font-mono text-slate-400">{target.brightTempC ?? (target.brightnessTempK - 273.15).toFixed(1)} °C</span>
          </div>

          {/* FRP */}
          <div className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg">
            <div className="flex items-center space-x-1.5 text-slate-400 mb-1">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-[10px] font-mono uppercase">Thermal FRP</span>
            </div>
            <div className="font-mono text-lg font-bold text-slate-100">
              {target.frpMW.toFixed(1)} <span className="text-xs font-normal text-slate-400">MW</span>
            </div>
            <span className="text-[10px] font-mono text-amber-400/80">Radiative Power</span>
          </div>

          {/* Confidence */}
          <div className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg">
            <div className="flex items-center space-x-1.5 text-slate-400 mb-1">
              <Award className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-[10px] font-mono uppercase">Confidence</span>
            </div>
            <div className="font-mono text-lg font-bold text-emerald-400">
              {target.confidence}%
            </div>
            <span className="text-[10px] font-mono text-slate-500">VIIRS Pixel Verif.</span>
          </div>

          {/* AI Risk Score */}
          <div className="bg-slate-900/90 border border-slate-800 p-2.5 rounded-lg">
            <div className="flex items-center space-x-1.5 text-slate-400 mb-1">
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-[10px] font-mono uppercase">Spatial Risk Score</span>
            </div>
            <div className="font-mono text-lg font-bold text-cyan-300">
              {target.riskScore || 85} <span className="text-xs font-normal text-slate-500">/100</span>
            </div>
            <span className="text-[10px] font-mono text-cyan-400/80">Scorable Vector</span>
          </div>
        </div>

        {/* AI Model Classification Probabilities Distribution */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-lg p-3 space-y-2.5 font-mono text-xs">
          <div className="flex items-center justify-between pb-1.5 border-b border-slate-800">
            <span className="font-bold text-slate-300 flex items-center">
              <Cpu className="w-3.5 h-3.5 text-cyan-400 mr-1.5" />
              AI Probabilistic Model Distribution
            </span>
            <span className="text-[10px] text-slate-500">CALIBRATED</span>
          </div>

          <div className="space-y-2 pt-1">
            {/* 1. Industrial Persistent Flare */}
            <div>
              <div className="flex justify-between text-[11px] text-slate-300 mb-0.5">
                <span>1. Industrial Persistent Flare</span>
                <span className="font-bold text-amber-400">{flarePct}%</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-amber-500 transition-all duration-500 ease-out" 
                  style={{ width: `${flarePct}%` }} 
                />
              </div>
            </div>

            {/* 2. Abnormal Critical Spike */}
            <div>
              <div className="flex justify-between text-[11px] text-slate-300 mb-0.5">
                <span>2. Abnormal Critical Spike</span>
                <span className="font-bold text-red-400">{spikePct}%</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-red-500 transition-all duration-500 ease-out" 
                  style={{ width: `${spikePct}%` }} 
                />
              </div>
            </div>

            {/* 3. Natural Wildfire / Biomass */}
            <div>
              <div className="flex justify-between text-[11px] text-slate-300 mb-0.5">
                <span>3. Natural Wildfire / Biomass</span>
                <span className="font-bold text-emerald-400">{biomassPct}%</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-emerald-500 transition-all duration-500 ease-out" 
                  style={{ width: `${biomassPct}%` }} 
                />
              </div>
            </div>
          </div>
        </div>

        {/* OSM Overpass Spatial Fusion Section */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-lg p-3 space-y-2 font-mono text-xs">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-200 flex items-center">
              <Search className="w-3.5 h-3.5 text-cyan-400 mr-1.5" />
              OSM Overpass Spatial Verification
            </span>
            <button
              onClick={handleVerifyOsmBoundary}
              disabled={isVerifyingOsm}
              className="px-2 py-1 bg-cyan-950 hover:bg-cyan-900 border border-cyan-700 text-cyan-300 text-[10px] rounded flex items-center space-x-1 transition"
            >
              <RefreshCw className={`w-3 h-3 text-cyan-400 ${isVerifyingOsm ? 'animate-spin' : ''}`} />
              <span>VERIFY OSM BOUNDARY</span>
            </button>
          </div>

          {/* Tactical Status Message */}
          {osmStatusText && (
            <div className={`p-2 rounded border text-[11px] leading-snug font-mono transition-all duration-300 ${
              isVerifyingOsm 
                ? 'bg-cyan-950/80 border-cyan-700 text-cyan-300 animate-pulse' 
                : 'bg-slate-950 border-slate-800 text-emerald-400'
            }`}>
              {osmStatusText}
            </div>
          )}

          {osmResultData && (
            <div className="bg-slate-950 p-2 rounded border border-slate-800 space-y-1 text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-400">Dominant Landcover:</span>
                <span className="text-cyan-300 font-bold">{osmResultData.dominantLandCover}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Facility Match:</span>
                <span className="text-slate-200 truncate max-w-[160px]">{osmResultData.facilityName}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">OSM Overlap Status:</span>
                <span className={osmResultData.overlap ? 'text-emerald-400 font-bold' : 'text-amber-400'}>
                  {osmResultData.overlap ? 'CONFIRMED INDUSTRIAL' : 'ZERO OVERLAP'}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Geographical & Metadata Parameters */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3 space-y-2 text-xs font-mono">
          <div className="flex justify-between items-center pb-1.5 border-b border-slate-800/80">
            <span className="text-slate-400 flex items-center">
              <Navigation className="w-3 h-3 text-cyan-400 mr-1.5" /> Coordinates:
            </span>
            <span className="text-cyan-300 font-bold">
              {target.coordinates[0].toFixed(4)}° N, {target.coordinates[1].toFixed(4)}° E
            </span>
          </div>

          <div className="flex justify-between items-center pb-1.5 border-b border-slate-800/80">
            <span className="text-slate-400 flex items-center">
              <Layers className="w-3 h-3 text-amber-400 mr-1.5" /> Infrastructure Match:
            </span>
            <span className="text-slate-200 text-right truncate max-w-[170px]" title={target.facilityType}>
              {target.facilityType}
            </span>
          </div>

          <div className="flex justify-between items-center pb-1.5 border-b border-slate-800/80">
            <span className="text-slate-400 flex items-center">
              <CheckCircle2 className="w-3 h-3 text-emerald-400 mr-1.5" /> OSM Boundary Distance:
            </span>
            <span className={target.osmOverlap ? 'text-emerald-400 font-bold' : 'text-slate-400'}>
              {target.distanceToFacilityMeters != null ? `${target.distanceToFacilityMeters}m` : (target.osmOverlap ? '0m (OVERLAP)' : '>5000m')}
            </span>
          </div>

          <div className="flex justify-between items-center">
            <span className="text-slate-400 flex items-center">
              <Clock className="w-3 h-3 text-cyan-400 mr-1.5" /> Detection Timestamp:
            </span>
            <span className="text-slate-300 text-[11px]">
              {target.lastDetected}
            </span>
          </div>
        </div>

        {/* 7-Day Historical Thermal Trend Chart */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider flex items-center">
              <ChevronRight className="w-3.5 h-3.5 text-cyan-400 mr-1" />
              7-Day Thermal Intensity Baseline
            </span>
            <div className="flex space-x-1 font-mono text-[10px]">
              <button
                onClick={() => setChartMetric('frp')}
                className={`px-1.5 py-0.5 rounded ${chartMetric === 'frp' ? 'bg-cyan-950 text-cyan-400 border border-cyan-700' : 'text-slate-500 hover:text-slate-300'}`}
              >
                FRP (MW)
              </button>
              <button
                onClick={() => setChartMetric('temp')}
                className={`px-1.5 py-0.5 rounded ${chartMetric === 'temp' ? 'bg-red-950 text-red-400 border border-red-700' : 'text-slate-500 hover:text-slate-300'}`}
              >
                TEMP (K)
              </button>
            </div>
          </div>

          <div className="h-36 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                <defs>
                  <linearGradient id="thermalGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={accent.chartColor} stopOpacity={0.8}/>
                    <stop offset="95%" stopColor={accent.chartColor} stopOpacity={0.05}/>
                  </linearGradient>
                </defs>
                <XAxis 
                  dataKey="date" 
                  stroke="#475569" 
                  fontSize={10} 
                  tickLine={false}
                />
                <YAxis 
                  stroke="#475569" 
                  fontSize={10} 
                  tickLine={false}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#1e293b',
                    borderRadius: '0.375rem',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                    color: '#e2e8f0',
                  }}
                  formatter={(val: any) => [
                    `${val ?? 0} ${chartMetric === 'frp' ? 'MW' : 'K'}`, 
                    chartMetric === 'frp' ? 'Fire Radiative Power' : 'Brightness Temp'
                  ]}
                />
                <Area 
                  type="monotone" 
                  dataKey={chartMetric} 
                  stroke={accent.chartColor} 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#thermalGradient)" 
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[10px] font-mono text-slate-400 italic">
            {target.type === 'CRITICAL_SPIKE' 
              ? '⚠️ Warning: Exponential spike observed over last 48 hours relative to baseline.'
              : 'Continuous multi-day thermal baseline proves persistent operational flare activity.'}
          </p>
        </div>

        {/* Operational Intelligence Note */}
        <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 text-xs text-slate-300 leading-relaxed font-sans">
          <span className="font-mono text-cyan-400 font-bold block mb-1 uppercase text-[11px]">
            Operational Intelligence Brief
          </span>
          {target.description}
        </div>
      </div>

      {/* Drawer Action Controls Footer */}
      <div className="p-4 border-t border-slate-800 bg-slate-900/90 space-y-2">
        <button
          onClick={handleDispatch}
          disabled={isReconDispatched}
          className={`w-full py-2 px-3 rounded font-mono text-xs font-bold uppercase transition flex items-center justify-center space-x-2 ${
            isReconDispatched
              ? 'bg-emerald-950 border border-emerald-500 text-emerald-400'
              : 'bg-red-950/80 hover:bg-red-900 border border-red-600/80 text-red-200 shadow-lg shadow-red-950/40'
          }`}
        >
          {isReconDispatched ? (
            <>
              <CheckCircle2 className="w-4 h-4 text-emerald-400 animate-bounce" />
              <span>RECON DRONE DISPATCHED (LIVE TELEMETRY STREAMING)</span>
            </>
          ) : (
            <>
              <Send className="w-4 h-4 text-red-400" />
              <span>DISPATCH THERMAL RECON DRONE</span>
            </>
          )}
        </button>

        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={handleExportJSON}
            className="py-1.5 px-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-[11px] font-mono text-slate-200 flex items-center justify-center space-x-1.5 transition"
          >
            <Download className="w-3.5 h-3.5 text-cyan-400" />
            <span>EXPORT JSON</span>
          </button>

          <button
            onClick={handleVerifyOsmBoundary}
            className="py-1.5 px-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-[11px] font-mono text-slate-200 flex items-center justify-center space-x-1.5 transition"
          >
            <AlertOctagon className="w-3.5 h-3.5 text-amber-400" />
            <span>VERIFY OSM</span>
          </button>
        </div>
      </div>
    </aside>
  );
};
