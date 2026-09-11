'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Header } from '../components/layout/Header';
import { TacticalMap } from '../components/map/TacticalMap';
import { TargetDrawer } from '../components/dashboard/TargetDrawer';
import { AlertTicker } from '../components/dashboard/AlertTicker';
import { MOCK_THERMAL_TARGETS } from '../lib/mock-data';
import { ThermalTarget, MapLayerOptions, AnomalyType, QuickStats } from '../lib/types';
import { ChevronLeft, ChevronRight, Crosshair } from 'lucide-react';

export default function CommandCenterDashboard() {
  const [targets, setTargets] = useState<ThermalTarget[]>(MOCK_THERMAL_TARGETS);
  const [selectedTarget, setSelectedTarget] = useState<ThermalTarget | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(true);
  const [selectedFilter, setSelectedFilter] = useState<AnomalyType | 'ALL'>('ALL');
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncSourceLabel, setSyncSourceLabel] = useState<string>("ORBITAL CACHE // VIIRS-SNPP REPLAY");

  const [layers, setLayers] = useState<MapLayerOptions>({
    firmsHotspots: true,
    osmIndustrial: true,
    cloudCover: false,
    thermalHeatmap: false,
  });

  // Fetch anomalies from persistent database on load and trigger FIRMS sync
  useEffect(() => {
    async function syncAndLoadData() {
      setIsSyncing(true);
      try {
        // Trigger API telemetry sync
        const syncRes = await fetch('/api/firms/sync', { method: 'POST' });
        if (syncRes.ok) {
          const syncData = await syncRes.json();
          if (syncData.anomalies && syncData.anomalies.length > 0) {
            setTargets(syncData.anomalies);
            setSyncSourceLabel(syncData.sourceLabel || "ORBITAL CACHE // VIIRS-SNPP REPLAY");
            // Set initial selected target
            const defaultTarget = syncData.anomalies.find((t: ThermalTarget) => t.type === 'CRITICAL_SPIKE') || syncData.anomalies[0];
            setSelectedTarget(defaultTarget);
          }
        }
      } catch (err) {
        console.warn('[NEXUS DASHBOARD] Persistent API sync fallback to local store:', err);
        setSelectedTarget(MOCK_THERMAL_TARGETS[0]);
      } finally {
        setIsSyncing(false);
      }
    }

    syncAndLoadData();
  }, []);

  // Compute dynamic quick stats from targets
  const quickStats: QuickStats = useMemo(() => {
    const active = targets.length;
    const flares = targets.filter(t => t.type === 'PERSISTENT_FLARE').length;
    const critical = targets.filter(t => t.type === 'CRITICAL_SPIKE').length;
    const unverified = targets.filter(t => t.type === 'AGRICULTURAL_STUBBLE' || t.type === 'THERMAL_TELEMETRY' || t.status === 'UNVERIFIED').length;

    return {
      activeTargets: active || 35,
      industrialFlares: flares || 18,
      unverifiedAnomalies: unverified || 8,
      criticalAlarms: critical || 4,
    };
  }, [targets]);

  // Filter targets according to selected classification
  const filteredTargets = useMemo(() => {
    if (selectedFilter === 'ALL') return targets;
    return targets.filter(t => t.type === selectedFilter);
  }, [targets, selectedFilter]);

  const handleSelectTarget = (target: ThermalTarget) => {
    setSelectedTarget(target);
    setIsDrawerOpen(true);
  };

  const handleToggleLayer = (layerKey: keyof MapLayerOptions) => {
    setLayers(prev => ({
      ...prev,
      [layerKey]: !prev[layerKey],
    }));
  };

  const handleManualSync = async () => {
    setIsSyncing(true);
    try {
      const syncRes = await fetch('/api/firms/sync', { method: 'POST' });
      if (syncRes.ok) {
        const syncData = await syncRes.json();
        if (syncData.anomalies && syncData.anomalies.length > 0) {
          setTargets(syncData.anomalies);
          setSyncSourceLabel(syncData.sourceLabel || "ORBITAL CACHE // VIIRS-SNPP REPLAY");
        }
      }
    } catch (err) {
      console.error('Manual FIRMS sync error:', err);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleDispatchDrone = (targetId: string) => {
    console.log(`[NTRO RECON] Dispatched tactical satellite recon drone to ${targetId}`);
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-[#090d16] overflow-hidden select-none">
      {/* Top Navigation Header */}
      <Header
        quickStats={quickStats}
        selectedFilter={selectedFilter}
        onFilterChange={setSelectedFilter}
        onSyncTelemetry={handleManualSync}
        isSyncing={isSyncing}
        syncSourceLabel={syncSourceLabel}
      />

      {/* Main Command Center Viewport (Full height - header, zero scroll) */}
      <div className="relative flex flex-1 h-[calc(100vh-3.5rem)] overflow-hidden">
        {/* Main Map Viewport Canvas */}
        <div className="relative flex-1 h-full">
          <TacticalMap
            targets={filteredTargets}
            selectedTarget={selectedTarget}
            onSelectTarget={handleSelectTarget}
            layers={layers}
            onToggleLayer={handleToggleLayer}
          />

          {/* Bottom Live Alert Telemetry Ticker */}
          <AlertTicker
            targets={targets}
            onSelectTarget={handleSelectTarget}
          />

          {/* Floating Target Drawer Re-Open Button (When closed) */}
          {!isDrawerOpen && selectedTarget && (
            <button
              onClick={() => setIsDrawerOpen(true)}
              className="absolute top-4 right-4 z-20 bg-slate-900/90 border border-slate-800 text-cyan-400 hover:text-cyan-300 p-2.5 rounded-lg shadow-2xl backdrop-blur-md font-mono text-xs flex items-center space-x-2 transition"
              title="Open Target Inspection Panel"
            >
              <Crosshair className="w-4 h-4 text-cyan-400 animate-spin" style={{ animationDuration: '8s' }} />
              <span className="font-bold">INSPECT [{selectedTarget.id}]</span>
              <ChevronLeft className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Right-Side Target Inspection Drawer */}
        {isDrawerOpen && (
          <div className="relative flex">
            {/* Drawer Collapse Button Handle */}
            <button
              onClick={() => setIsDrawerOpen(false)}
              className="absolute top-1/2 -left-3 -translate-y-1/2 z-30 bg-slate-900 border border-slate-700 text-slate-400 hover:text-slate-100 p-1 rounded-full shadow-2xl transition"
              title="Collapse Inspection Drawer"
            >
              <ChevronRight className="w-4 h-4" />
            </button>

            <TargetDrawer
              target={selectedTarget}
              onClose={() => setIsDrawerOpen(false)}
              onDispatchDrone={handleDispatchDrone}
            />
          </div>
        )}
      </div>
    </div>
  );
}
