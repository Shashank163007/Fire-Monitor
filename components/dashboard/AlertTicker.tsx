'use client';

import React, { useState, useEffect } from 'react';
import { AlertTriangle, Flame, ShieldAlert, Radio, ChevronRight } from 'lucide-react';
import { ThermalTarget } from '../../lib/types';

interface AlertTickerProps {
  targets: ThermalTarget[];
  onSelectTarget: (target: ThermalTarget) => void;
}

export const AlertTicker: React.FC<AlertTickerProps> = ({
  targets,
  onSelectTarget,
}) => {
  const [activeAlertIndex, setActiveAlertIndex] = useState<number>(0);

  // Filter critical and high-frp targets for real-time alert ticker
  const alertTargets = targets.filter(t => t.type === 'CRITICAL_SPIKE' || t.frpMW > 150);

  useEffect(() => {
    if (alertTargets.length === 0) return;
    const interval = setInterval(() => {
      setActiveAlertIndex((prev) => (prev + 1) % alertTargets.length);
    }, 4500);
    return () => clearInterval(interval);
  }, [alertTargets.length]);

  if (alertTargets.length === 0) return null;

  const currentTarget = alertTargets[activeAlertIndex];

  return (
    <div className="absolute bottom-0 left-0 right-0 h-8 bg-[#090d16]/95 border-t border-slate-800 z-10 flex items-center px-4 backdrop-blur-md overflow-hidden select-none">
      {/* Left Badge */}
      <div className="flex items-center space-x-2 bg-red-950/80 border border-red-800/80 px-2 py-0.5 rounded text-[10px] font-mono text-red-400 shrink-0 font-bold">
        <Radio className="w-3 h-3 text-red-500 animate-pulse" />
        <span>LIVE TELEMETRY STREAM</span>
      </div>

      {/* Scrolling / Animated Active Alert */}
      <div 
        onClick={() => onSelectTarget(currentTarget)}
        className="ml-4 flex items-center space-x-3 text-xs font-mono text-slate-300 hover:text-cyan-300 cursor-pointer transition truncate flex-1"
      >
        <span className="text-red-400 font-bold flex items-center">
          <AlertTriangle className="w-3.5 h-3.5 mr-1 text-red-500 animate-bounce" />
          [{currentTarget.id}]
        </span>

        <span className="text-slate-100 font-semibold truncate">
          {currentTarget.name} ({currentTarget.state})
        </span>

        <span className="text-amber-400 font-bold hidden sm:inline">
          FRP: {currentTarget.frpMW} MW
        </span>

        <span className="text-red-400 font-bold hidden md:inline">
          TEMP: {currentTarget.brightnessTempK} K
        </span>

        <span className="text-slate-400 hidden lg:inline text-[11px]">
          CLASSIFICATION: <span className="text-slate-200">{currentTarget.classification}</span>
        </span>
      </div>

      {/* Right Target Direct Select Click */}
      <button 
        onClick={() => onSelectTarget(currentTarget)}
        className="ml-2 text-[10px] font-mono text-cyan-400 hover:text-cyan-300 flex items-center shrink-0"
      >
        <span>INSPECT ANOMALY</span>
        <ChevronRight className="w-3 h-3 ml-0.5" />
      </button>
    </div>
  );
};
