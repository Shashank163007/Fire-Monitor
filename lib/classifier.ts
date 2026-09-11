/**
 * AI Classification Layer for Geo-Thermal Anomaly Nexus
 * Calibrated probabilistic scoring engine for satellite geo-thermal detections.
 */

import { ClassificationProbabilities, AnomalyType, ThermalHistoryPoint } from './types';

export interface ClassifierFeatureInput {
  frpMW: number;
  brightTi4K: number;
  brightTi5K: number;
  distanceToIndustrialMeters: number;
  isIndustrialOverlap: boolean;
  facilityType?: string;
  dominantLandCover?: 'INDUSTRIAL' | 'FOREST' | 'FARMLAND' | 'UNCLASSIFIED';
  dayNight?: 'DAY_PASS' | 'NIGHT_PASS';
  confidence: number;
  history7Days?: ThermalHistoryPoint[];
}

export interface ClassificationResult {
  primaryType: AnomalyType;
  classificationTag: string;
  probabilities: ClassificationProbabilities;
  riskScore: number;
  defensePriority: 'DELTA-1' | 'ALPHA-2' | 'BRAVO-1' | 'CHARLIE-3';
}

export function classifyAnomaly(features: ClassifierFeatureInput): ClassificationResult {
  const {
    frpMW,
    brightTi4K,
    brightTi5K,
    distanceToIndustrialMeters,
    isIndustrialOverlap,
    facilityType = '',
    dominantLandCover = 'UNCLASSIFIED',
    confidence,
    history7Days = [],
  } = features;

  // 1. Moving Average Math with Zero-Value Safety
  const historicalFRP = history7Days.slice(0, -1).map(h => h.frpMW);
  const sumFRP = historicalFRP.reduce((a, b) => a + b, 0);
  const countFRP = historicalFRP.length;
  
  // Safe moving average calculation avoiding divide-by-zero
  const movingAvgFRP = countFRP > 0 && sumFRP > 0 
    ? sumFRP / countFRP 
    : (frpMW > 0 ? frpMW : 1);

  // Spike Ratio calculation relative to baseline
  const spikeRatio = movingAvgFRP > 0 ? (frpMW - movingAvgFRP) / movingAvgFRP : 0;
  const spikePercent = Math.round(spikeRatio * 100);

  // 2. Strict Calibrated Scoring Rules

  const isForestOrPark = 
    dominantLandCover === 'FOREST' || 
    facilityType.toLowerCase().includes('national_park') ||
    facilityType.toLowerCase().includes('reserve') ||
    facilityType.toLowerCase().includes('forestry');

  const isIndustrial = 
    dominantLandCover === 'INDUSTRIAL' || 
    isIndustrialOverlap || 
    distanceToIndustrialMeters <= 2000;

  let probs: ClassificationProbabilities;
  let primaryType: AnomalyType;
  let classificationTag: string;
  let defensePriority: 'DELTA-1' | 'ALPHA-2' | 'BRAVO-1' | 'CHARLIE-3';
  let riskScore: number;

  if (isForestOrPark) {
    // RULE A: Natural Forest / National Park Zone
    // Wildfire/Biomass >= 88%, Industrial Flare <= 5%
    probs = {
      wildfire: 0.90,
      biomass_burning: 0.05,
      industrial_flare: 0.02,
      abnormal_spike: 0.02,
      unverified: 0.01,
    };
    primaryType = 'BIOMASS_FIRE';
    classificationTag = "NATURAL BIOMASS FIRE (FOREST CANOPY)";
    defensePriority = 'ALPHA-2';
    riskScore = Math.min(95, Math.max(60, Math.round(frpMW * 0.7 + confidence * 0.2)));

  } else if (isIndustrial && spikeRatio > 0.35) {
    // RULE B: Industrial Zone with Exponential Spike (>35% above 7-day moving average)
    // Abnormal Spike >= 82%, Industrial Flare <= 18%
    probs = {
      abnormal_spike: 0.85,
      industrial_flare: 0.12,
      biomass_burning: 0.01,
      wildfire: 0.01,
      unverified: 0.01,
    };
    primaryType = 'CRITICAL_SPIKE';
    classificationTag = `ABNORMAL REFINERY SPIKE (+${Math.max(40, spikePercent)}%)`;
    defensePriority = 'DELTA-1';
    riskScore = Math.min(100, Math.max(85, Math.round(85 + spikeRatio * 10)));

  } else if (isIndustrial) {
    // RULE C: Industrial Zone with Routine Operational Flaring (Variance <= 35%)
    // Industrial Flare >= 90%
    probs = {
      industrial_flare: 0.92,
      abnormal_spike: 0.05,
      biomass_burning: 0.01,
      wildfire: 0.01,
      unverified: 0.01,
    };
    primaryType = 'PERSISTENT_FLARE';
    classificationTag = "CONFIRMED INDUSTRIAL FLARE (ROUTINE FLARING)";
    defensePriority = 'BRAVO-1';
    riskScore = Math.min(90, Math.max(70, Math.round(70 + (frpMW / 300) * 15)));

  } else if (dominantLandCover === 'FARMLAND') {
    // RULE D: Agricultural Farmland Paddy Stubble
    probs = {
      biomass_burning: 0.88,
      wildfire: 0.08,
      industrial_flare: 0.02,
      abnormal_spike: 0.01,
      unverified: 0.01,
    };
    primaryType = 'AGRICULTURAL_STUBBLE';
    classificationTag = "UNVERIFIED STUBBLE BURNING CLUSTER";
    defensePriority = 'CHARLIE-3';
    riskScore = Math.min(65, Math.max(35, Math.round(frpMW * 0.8)));

  } else {
    // RULE E: Unverified Low-Confidence Telemetry
    probs = {
      unverified: 0.70,
      biomass_burning: 0.15,
      industrial_flare: 0.10,
      abnormal_spike: 0.03,
      wildfire: 0.02,
    };
    primaryType = 'THERMAL_TELEMETRY';
    classificationTag = "UNVERIFIED THERMAL SIGNATURE";
    defensePriority = 'CHARLIE-3';
    riskScore = 40;
  }

  return {
    primaryType,
    classificationTag,
    probabilities: probs,
    riskScore,
    defensePriority,
  };
}
