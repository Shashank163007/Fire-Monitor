'use client';

import React, { useEffect, useRef, useState } from 'react';
import { ThermalTarget, MapLayerOptions } from '../../lib/types';
import { 
  ZoomIn, ZoomOut, Compass, RotateCcw, Layers, 
  Flame, Trees, Cpu
} from 'lucide-react';

interface TacticalMapProps {
  targets: ThermalTarget[];
  selectedTarget: ThermalTarget | null;
  onSelectTarget: (target: ThermalTarget) => void;
  layers: MapLayerOptions;
  onToggleLayer: (layerKey: keyof MapLayerOptions) => void;
}

export const TacticalMap: React.FC<TacticalMapProps> = ({
  targets,
  selectedTarget,
  onSelectTarget,
  layers,
  onToggleLayer,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<any>(null);
  const markersRef = useRef<{ [id: string]: any }>({});
  const overlayLayersRef = useRef<{ firms?: any; osm?: any; cloud?: any }>({});
  
  const [mapLoaded, setMapLoaded] = useState<boolean>(false);
  const [showLayerPanel, setShowLayerPanel] = useState<boolean>(false);
  const [currentZoom, setCurrentZoom] = useState<number>(5);

  const INDIA_CENTER: [number, number] = [20.5937, 78.9629];
  const DEFAULT_ZOOM = 5;

  // Initialize Leaflet Map
  useEffect(() => {
    if (typeof window === 'undefined' || !mapContainerRef.current) return;

    let L: any;
    const initMap = async () => {
      L = (await import('leaflet')).default;
      
      delete L.Icon.Default.prototype._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
      });

      if (!leafletMapRef.current) {
        const map = L.map(mapContainerRef.current, {
          center: INDIA_CENTER,
          zoom: DEFAULT_ZOOM,
          zoomControl: false,
          attributionControl: false,
        });

        // 100% Watermark-Free Tactical Dark Matter Base Layer using OpenStreetMap inverted tiles
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          className: 'tactical-dark-tiles',
          attribution: '',
        }).addTo(map);

        map.on('zoomend', () => {
          setCurrentZoom(map.getZoom());
        });

        leafletMapRef.current = map;
        setMapLoaded(true);
      }
    };

    initMap();

    return () => {
      if (leafletMapRef.current) {
        leafletMapRef.current.remove();
        leafletMapRef.current = null;
      }
    };
  }, []);

  // Update Target Markers on Map
  useEffect(() => {
    if (!mapLoaded || !leafletMapRef.current || typeof window === 'undefined') return;

    const L = require('leaflet');
    const map = leafletMapRef.current;

    // Clear existing markers
    Object.values(markersRef.current).forEach((marker: any) => marker.remove());
    markersRef.current = {};

    targets.forEach((target) => {
      const isSelected = selectedTarget?.id === target.id;
      
      let markerColor = '#06b6d4'; // Cyan default

      if (target.type === 'CRITICAL_SPIKE') {
        markerColor = '#ef4444';
      } else if (target.type === 'PERSISTENT_FLARE') {
        markerColor = '#f59e0b';
      } else if (target.type === 'BIOMASS_FIRE') {
        markerColor = '#10b981';
      }

      // Create Custom Tactical DivIcon
      const iconHtml = `
        <div class="relative flex items-center justify-center">
          <!-- Pulse Outer Aura Ring -->
          <div class="absolute -inset-2 rounded-full opacity-75 animate-ping" style="background-color: ${markerColor}; animation-duration: ${target.type === 'CRITICAL_SPIKE' ? '1s' : '2.5s'};"></div>
          
          <!-- Tactical Core Beacon Marker -->
          <div class="relative z-10 w-7 h-7 rounded-full border-2 border-slate-900 flex items-center justify-center shadow-lg transition-transform ${isSelected ? 'scale-125 ring-4 ring-cyan-400 ring-offset-2 ring-offset-slate-950' : 'hover:scale-110'}" style="background-color: ${markerColor}; shadow: 0 0 15px ${markerColor};">
            <span class="w-2.5 h-2.5 rounded-full bg-slate-950"></span>
          </div>

          <!-- Label tooltip preview -->
          ${isSelected ? `
            <div class="absolute top-8 left-1/2 -translate-x-1/2 whitespace-nowrap bg-slate-950/90 border border-slate-700 text-slate-100 font-mono text-[10px] px-2 py-0.5 rounded shadow-xl pointer-events-none z-30">
              <span class="font-bold text-cyan-400">${target.id}</span> | ${target.frpMW} MW
            </div>
          ` : ''}
        </div>
      `;

      const customIcon = L.divIcon({
        html: iconHtml,
        className: 'tactical-marker',
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      });

      const marker = L.marker(target.coordinates, { icon: customIcon }).addTo(map);

      marker.on('click', () => {
        onSelectTarget(target);
        map.flyTo(target.coordinates, Math.max(map.getZoom(), 8), {
          duration: 1.2,
        });
      });

      markersRef.current[target.id] = marker;
    });
  }, [mapLoaded, targets, selectedTarget]);

  // Handle Layer Overlays (FIRMS, OSM Polygons, Cloud Cover)
  useEffect(() => {
    if (!mapLoaded || !leafletMapRef.current || typeof window === 'undefined') return;

    const L = require('leaflet');
    const map = leafletMapRef.current;

    // FIRMS Thermal Hotspots Layer Overlay
    if (layers.firmsHotspots) {
      if (!overlayLayersRef.current.firms) {
        const firmsGroup = L.layerGroup();
        targets.forEach(t => {
          for (let i = 0; i < 4; i++) {
            const offsetLat = (Math.random() - 0.5) * 0.15;
            const offsetLng = (Math.random() - 0.5) * 0.15;
            const circle = L.circle([t.coordinates[0] + offsetLat, t.coordinates[1] + offsetLng], {
              color: '#ef4444',
              fillColor: '#f87171',
              fillOpacity: 0.25,
              radius: 4000 + Math.random() * 6000,
              weight: 1,
              dashArray: '3, 3'
            });
            firmsGroup.addLayer(circle);
          }
        });
        overlayLayersRef.current.firms = firmsGroup;
      }
      map.addLayer(overlayLayersRef.current.firms);
    } else if (overlayLayersRef.current.firms) {
      map.removeLayer(overlayLayersRef.current.firms);
    }

    // OSM Industrial Polygons Layer Overlay
    if (layers.osmIndustrial) {
      if (!overlayLayersRef.current.osm) {
        const osmGroup = L.layerGroup();
        targets.filter(t => t.osmOverlap).forEach(t => {
          const lat = t.coordinates[0];
          const lng = t.coordinates[1];
          const bounds = [
            [lat - 0.04, lng - 0.04],
            [lat - 0.04, lng + 0.04],
            [lat + 0.04, lng + 0.04],
            [lat + 0.04, lng - 0.04],
          ];
          const polygon = L.polygon(bounds, {
            color: '#06b6d4',
            fillColor: '#0891b2',
            fillOpacity: 0.15,
            weight: 1.5,
            dashArray: '4, 4'
          });
          osmGroup.addLayer(polygon);
        });
        overlayLayersRef.current.osm = osmGroup;
      }
      map.addLayer(overlayLayersRef.current.osm);
    } else if (overlayLayersRef.current.osm) {
      map.removeLayer(overlayLayersRef.current.osm);
    }

    // Cloud Cover / Radar Mask Layer Overlay
    if (layers.cloudCover) {
      if (!overlayLayersRef.current.cloud) {
        const cloudGroup = L.layerGroup();
        const cloudBounds = [
          [15.0, 72.0], [25.0, 72.0], [25.0, 85.0], [15.0, 85.0]
        ];
        const cloudPoly = L.polygon(cloudBounds, {
          color: '#475569',
          fillColor: '#334155',
          fillOpacity: 0.12,
          weight: 1,
        });
        cloudGroup.addLayer(cloudPoly);
        overlayLayersRef.current.cloud = cloudGroup;
      }
      map.addLayer(overlayLayersRef.current.cloud);
    } else if (overlayLayersRef.current.cloud) {
      map.removeLayer(overlayLayersRef.current.cloud);
    }

  }, [mapLoaded, layers, targets]);

  // Floating Map Controls Actions
  const handleZoomIn = () => {
    if (leafletMapRef.current) leafletMapRef.current.zoomIn();
  };

  const handleZoomOut = () => {
    if (leafletMapRef.current) leafletMapRef.current.zoomOut();
  };

  const handleResetView = () => {
    if (leafletMapRef.current) {
      leafletMapRef.current.flyTo(INDIA_CENTER, DEFAULT_ZOOM, { duration: 1.5 });
    }
  };

  return (
    <div className="relative w-full h-[calc(100vh-3.5rem)] bg-[#090d16] overflow-hidden select-none">
      {/* Map Canvas Container */}
      <div ref={mapContainerRef} className="w-full h-full z-0" />

      {/* Floating Tactical Map Controls Overlay (Top-Left) */}
      <div className="absolute top-4 left-4 z-10 flex flex-col space-y-2">
        {/* Navigation & Zoom Controls */}
        <div className="bg-slate-900/90 border border-slate-800 rounded-lg p-1 shadow-2xl backdrop-blur-md flex flex-col space-y-1">
          <button
            onClick={handleZoomIn}
            className="p-2 text-slate-300 hover:text-cyan-400 hover:bg-slate-800 rounded transition"
            title="Zoom In"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={handleZoomOut}
            className="p-2 text-slate-300 hover:text-cyan-400 hover:bg-slate-800 rounded transition"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <div className="w-full h-[1px] bg-slate-800 my-0.5" />
          <button
            onClick={handleResetView}
            className="p-2 text-slate-300 hover:text-cyan-400 hover:bg-slate-800 rounded transition"
            title="Reset Map to Center of India"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
        </div>

        {/* Tactical Layer Toggle Menu Trigger */}
        <div className="relative">
          <button
            onClick={() => setShowLayerPanel(!showLayerPanel)}
            className={`p-2 rounded-lg border shadow-2xl backdrop-blur-md transition flex items-center space-x-1.5 ${
              showLayerPanel 
                ? 'bg-cyan-950 border-cyan-500 text-cyan-300' 
                : 'bg-slate-900/90 border-slate-800 text-slate-300 hover:bg-slate-800'
            }`}
            title="Toggle Tactical Map Layers"
          >
            <Layers className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-mono font-bold hidden sm:inline">LAYERS</span>
          </button>

          {/* Layer Selection Dropdown Panel */}
          {showLayerPanel && (
            <div className="absolute top-0 left-full ml-2 w-64 bg-slate-900/95 border border-slate-800 rounded-lg p-3 shadow-2xl backdrop-blur-xl space-y-2 z-30 font-mono text-xs text-slate-200">
              <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider pb-1 border-b border-slate-800 flex justify-between items-center">
                <span>Tactical GIS Overlays</span>
                <span className="text-cyan-400">ACTIVE</span>
              </div>

              {/* FIRMS Hotspots */}
              <label className="flex items-center justify-between cursor-pointer p-1.5 hover:bg-slate-800/80 rounded transition">
                <span className="flex items-center space-x-2">
                  <Flame className="w-3.5 h-3.5 text-red-500" />
                  <span>FIRMS Hotspot Grid</span>
                </span>
                <input
                  type="checkbox"
                  checked={layers.firmsHotspots}
                  onChange={() => onToggleLayer('firmsHotspots')}
                  className="accent-red-500 cursor-pointer"
                />
              </label>

              {/* OSM Industrial Polygons */}
              <label className="flex items-center justify-between cursor-pointer p-1.5 hover:bg-slate-800/80 rounded transition">
                <span className="flex items-center space-x-2">
                  <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                  <span>OSM Industrial Boundaries</span>
                </span>
                <input
                  type="checkbox"
                  checked={layers.osmIndustrial}
                  onChange={() => onToggleLayer('osmIndustrial')}
                  className="accent-cyan-500 cursor-pointer"
                />
              </label>

              {/* Cloud Cover Mask */}
              <label className="flex items-center justify-between cursor-pointer p-1.5 hover:bg-slate-800/80 rounded transition">
                <span className="flex items-center space-x-2">
                  <Trees className="w-3.5 h-3.5 text-slate-400" />
                  <span>Cloud Cover Radar Mask</span>
                </span>
                <input
                  type="checkbox"
                  checked={layers.cloudCover}
                  onChange={() => onToggleLayer('cloudCover')}
                  className="accent-slate-400 cursor-pointer"
                />
              </label>
            </div>
          )}
        </div>
      </div>

      {/* Floating Tactical Coordinate Radar Legend (Bottom-Left) */}
      <div className="absolute bottom-4 left-4 z-10 bg-slate-900/90 border border-slate-800 rounded-lg px-3 py-1.5 backdrop-blur-md font-mono text-[11px] text-slate-400 flex items-center space-x-3 shadow-xl">
        <div className="flex items-center space-x-1.5">
          <Compass className="w-3.5 h-3.5 text-cyan-400 animate-spin" style={{ animationDuration: '10s' }} />
          <span>ZOOM: <span className="text-cyan-300 font-bold">{currentZoom}</span></span>
        </div>
        <div className="h-3 w-[1px] bg-slate-800" />
        <div>PROJECTION: <span className="text-slate-200">EPSG:3857 (WATERMARK-FREE)</span></div>
        <div className="h-3 w-[1px] bg-slate-800 hidden md:block" />
        <div className="hidden md:block">BASE: <span className="text-emerald-400">OPENSTREETMAP TACTICAL DARK</span></div>
      </div>
    </div>
  );
};
