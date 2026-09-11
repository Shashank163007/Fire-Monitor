'use client';

import React, { useState, useEffect } from 'react';
import { Shield, Radio, Activity, AlertTriangle, Flame, Trees, Cpu, Filter, RefreshCw } from 'lucide-react';
import { QuickStats, AnomalyType } from '../../lib/types';

interface HeaderProps {
  quickStats: QuickStats;
  selectedFilter: AnomalyType | 'ALL';
  onFilterChange: (filter: AnomalyType | 'ALL') => void;
  onSyncTelemetry?: () => void;
  isSyncing?: boolean;
  syncSourceLabel?: string;
}

export const Header: React.FC<HeaderProps> = ({
  quickStats,
  selectedFilter,
  onFilterChange,
  onSyncTelemetry,
  isSyncing = false,
  syncSourceLabel = "ORBITAL CACHE // VIIRS-SNPP REPLAY",
}) => {
  const [utcTime, setUtcTime] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const iso = now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
      setUtcTime(iso);
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="h-14 bg-[#090d16]/95 border-b border-slate-800 text-slate-200 px-4 flex items-center justify-between z-30 relative backdrop-blur-md select-none">
      {/* Left side: Badge, Live Indicator & Clock */}
      <div className="flex items-center space-x-3">
        {/* NTRO Badge */}
        <div className="flex items-center space-x-2.5 bg-slate-900/90 border border-slate-700/80 px-3 py-1 rounded shadow-inner">
          <Shield className="w-5 h-5 text-cyan-400 animate-pulse" />
          <span className="font-mono font-bold tracking-wider text-sm text-slate-100 uppercase">
            NTRO <span className="text-cyan-500">//</span> GEO-THERMAL ANOMALY NEXUS
          </span>
        </div>

        {/* System Telemetry Live Dot */}
        <div className="flex items-center space-x-2 bg-emerald-950/40 border border-emerald-800/60 px-2.5 py-1 rounded-full text-xs font-mono text-emerald-400">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="tracking-widest font-semibold text-[11px]">TELEMETRY LIVE</span>
        </div>

        {/* FIRMS Sync Button */}
        {onSyncTelemetry && (
          <button
            onClick={onSyncTelemetry}
            disabled={isSyncing}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded text-xs font-mono border transition ${
              isSyncing
                ? 'bg-cyan-950 border-cyan-500 text-cyan-300'
                : 'bg-slate-900 hover:bg-slate-800 border-slate-700 text-slate-300'
            }`}
            title="Trigger Live NASA FIRMS Ingestion Sync"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${isSyncing ? 'animate-spin' : ''}`} />
            <span className="font-bold hidden sm:inline">{isSyncing ? 'SYNCING...' : 'SYNC TELEMETRY'}</span>
          </button>
        )}

        {/* Live UTC Clock */}
        <div className="hidden lg:flex items-center space-x-2 bg-slate-900/60 border border-slate-800 px-3 py-1 rounded text-xs font-mono text-cyan-300 tracking-wider">
          <Radio className="w-3.5 h-3.5 text-cyan-400 animate-spin" style={{ animationDuration: '6s' }} />
          <span>{utcTime || 'SYS_SYNCING...'}</span>
        </div>
      </div>

      {/* Center Filter Buttons */}
      <div className="hidden xl:flex items-center space-x-1.5 bg-slate-950/80 p-1 rounded-lg border border-slate-800/80">
        <button
          onClick={() => onFilterChange('ALL')}
          className={`px-2.5 py-1 rounded text-xs font-mono transition-all flex items-center space-x-1 ${
            selectedFilter === 'ALL'
              ? 'bg-slate-800 text-cyan-400 border border-cyan-500/50 shadow'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          <Filter className="w-3 h-3" />
          <span>ALL ({quickStats.activeTargets})</span>
        </button>

        <button
          onClick={() => onFilterChange('CRITICAL_SPIKE')}
          className={`px-2.5 py-1 rounded text-xs font-mono transition-all flex items-center space-x-1 ${
            selectedFilter === 'CRITICAL_SPIKE'
              ? 'bg-red-950/80 text-red-400 border border-red-500/60'
              : 'text-slate-400 hover:text-red-400 hover:bg-red-950/30'
          }`}
        >
          <AlertTriangle className="w-3 h-3 text-red-500" />
          <span>CRITICAL ({quickStats.criticalAlarms})</span>
        </button>

        <button
          onClick={() => onFilterChange('PERSISTENT_FLARE')}
          className={`px-2.5 py-1 rounded text-xs font-mono transition-all flex items-center space-x-1 ${
            selectedFilter === 'PERSISTENT_FLARE'
              ? 'bg-amber-950/80 text-amber-400 border border-amber-500/60'
              : 'text-slate-400 hover:text-amber-400 hover:bg-amber-950/30'
          }`}
        >
          <Flame className="w-3 h-3 text-amber-500" />
          <span>FLARES ({quickStats.industrialFlares})</span>
        </button>

        <button
          onClick={() => onFilterChange('BIOMASS_FIRE')}
          className={`px-2.5 py-1 rounded text-xs font-mono transition-all flex items-center space-x-1 ${
            selectedFilter === 'BIOMASS_FIRE'
              ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-500/60'
              : 'text-slate-400 hover:text-emerald-400 hover:bg-emerald-950/30'
          }`}
        >
          <Trees className="w-3 h-3 text-emerald-500" />
          <span>BIOMASS</span>
        </button>

        <button
          onClick={() => onFilterChange('AGRICULTURAL_STUBBLE')}
          className={`px-2.5 py-1 rounded text-xs font-mono transition-all flex items-center space-x-1 ${
            selectedFilter === 'AGRICULTURAL_STUBBLE'
              ? 'bg-cyan-950/80 text-cyan-400 border border-cyan-500/60'
              : 'text-slate-400 hover:text-cyan-400 hover:bg-cyan-950/30'
          }`}
        >
          <Cpu className="w-3 h-3 text-cyan-400" />
          <span>UNVERIFIED ({quickStats.unverifiedAnomalies})</span>
        </button>
      </div>

      {/* Right side: Quick stats counter badges */}
      <div className="flex items-center space-x-2">
        {/* Active Targets */}
        <div className="flex items-center space-x-1.5 bg-slate-900 border border-slate-700/80 px-2.5 py-1 rounded">
          <Activity className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs text-slate-400 hidden sm:inline">Active Targets:</span>
          <span className="font-mono text-xs font-bold text-cyan-300">[{quickStats.activeTargets}]</span>
        </div>

        {/* Industrial Flares */}
        <div className="flex items-center space-x-1.5 bg-amber-950/30 border border-amber-800/60 px-2.5 py-1 rounded">
          <Flame className="w-3.5 h-3.5 text-amber-500" />
          <span className="text-xs text-amber-300/80 hidden sm:inline">Industrial Flares:</span>
          <span className="font-mono text-xs font-bold text-amber-400">[{quickStats.industrialFlares}]</span>
        </div>

        {/* Unverified Anomalies */}
        <div className="flex items-center space-x-1.5 bg-cyan-950/30 border border-cyan-800/60 px-2.5 py-1 rounded hidden md:flex">
          <Cpu className="w-3.5 h-3.5 text-cyan-400" />
          <span className="text-xs text-cyan-300/80">Unverified:</span>
          <span className="font-mono text-xs font-bold text-cyan-300">[{quickStats.unverifiedAnomalies}]</span>
        </div>

        {/* Critical Alarms */}
        <div className="flex items-center space-x-1.5 bg-red-950/60 border border-red-600/80 px-2.5 py-1 rounded shadow-lg shadow-red-950/50 animate-pulse">
          <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
          <span className="text-xs text-red-300 font-semibold hidden sm:inline">Critical Alarms:</span>
          <span className="font-mono text-xs font-extrabold text-red-400">[{quickStats.criticalAlarms}]</span>
        </div>
      </div>
    </header>
  );
};
