export type AnomalyType = 
  | 'CRITICAL_SPIKE'
  | 'PERSISTENT_FLARE'
  | 'BIOMASS_FIRE'
  | 'AGRICULTURAL_STUBBLE'
  | 'THERMAL_TELEMETRY';

export type SensorType = 
  | 'VIIRS_VNP14IMGTDL' 
  | 'VIIRS_NRT_NOAA20'
  | 'MODIS_MYD14' 
  | 'SLSTR_SENTINEL3'
  | 'LANDSAT_8_TIRS';

export interface ThermalHistoryPoint {
  date: string;
  tempK: number;
  frpMW: number;
  isMockHistory?: boolean;
}

export interface ClassificationProbabilities {
  industrial_flare: number;
  abnormal_spike: number;
  biomass_burning: number;
  wildfire: number;
  unverified: number;
}

export interface ThermalTarget {
  id: string;
  name: string;
  facilityType: string;
  state: string;
  coordinates: [number, number]; // [lat, lng]
  type: AnomalyType;
  classification: string;
  sensorId: SensorType;
  brightnessTempK: number;
  brightTi4?: number;
  brightTi5?: number;
  brightTempC: number;
  frpMW: number;
  confidence: number; // 0 - 100%
  osmOverlap: boolean;
  nearestFacilityName?: string;
  distanceToFacilityMeters?: number;
  lastDetected: string;
  dayNight?: 'DAY_PASS' | 'NIGHT_PASS';
  status: 'ACTIVE_ALERT' | 'VERIFIED_STABLE' | 'UNDER_RECON' | 'UNVERIFIED';
  defensePriority: 'DELTA-1' | 'ALPHA-2' | 'BRAVO-1' | 'CHARLIE-3';
  riskScore: number;
  description: string;
  history7Days: ThermalHistoryPoint[];
  classificationProbs?: ClassificationProbabilities;
  isSynthetic: boolean;
  dataSourceLabel?: string; // "LIVE DIRECT DOWNLINK (NASA-EOSDIS)" | "ORBITAL CACHE // VIIRS-SNPP REPLAY"
}

export interface MapLayerOptions {
  firmsHotspots: boolean;
  osmIndustrial: boolean;
  cloudCover: boolean;
  thermalHeatmap: boolean;
}

export interface QuickStats {
  activeTargets: number;
  industrialFlares: number;
  unverifiedAnomalies: number;
  criticalAlarms: number;
}

export interface FirmsRawRecord {
  latitude: number | string;
  longitude: number | string;
  bright_ti4: number | string;
  scan?: number | string;
  track?: number | string;
  acq_date?: string;
  acq_time?: string;
  satellite?: string;
  confidence: number | string;
  bright_ti5?: number | string;
  frp: number | string;
  daynight?: string;
}

export interface FirmsSyncResponse {
  success: boolean;
  source: 'NASA_FIRMS_LIVE' | 'ORBITAL_CACHE_REPLAY';
  sourceLabel: string;
  timestamp: string;
  sensor: SensorType;
  totalIngested: number;
  latencyMs: number;
  anomalies: ThermalTarget[];
}
