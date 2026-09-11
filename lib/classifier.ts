/**
 * AI Classification Layer for Geo-Thermal Anomaly Nexus
 * 
 * AUDIT NOTE / ARCHITECTURE DOCUMENTATION:
 * This module implements a feature-scored probabilistic model `classifyAnomaly()`.
 * Current features use heuristic scoring weights based on satellite physical parameters 
 * and spatial landcover proximity. This layer is designed as a modular, swappable 
 * interface that can be replaced with an ONNX Runtime or PyTorch XGBoost / Random Forest 
 * inference engine without changing API contracts.
 */

import { ClassificationProbabilities, AnomalyType } from './types';

export interface ClassifierFeatureInput {
  frpMW: number;
  brightTi4K: number;
  brightTi5K: number;
  distanceToIndustrialMeters: number;
  isIndustrialOverlap: boolean;
  dayNight: 'DAY_PASS' | 'NIGHT_PASS';
  confidence: number;
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
    dayNight,
    confidence
  } = features;

  // Feature 1: Thermal Channel Delta (brightness temp difference ti4 - ti5 in Kelvin)
  const thermalDelta = brightTi4K - brightTi5K;

  // Initial score accumulators for each candidate class
  let scoreFlare = 0;
  let scoreSpike = 0;
  let scoreBiomass = 0;
  let scoreWildfire = 0;
  let scoreUnverified = 0;

  // --- FEATURE SCORING LOGIC ---

  // Feature A: Spatial Proximity to OSM Industrial Facility
  if (isIndustrialOverlap || distanceToIndustrialMeters <= 5000) {
    scoreFlare += 45;
    scoreSpike += 35;
    scoreBiomass -= 25;
    scoreWildfire -= 30;
  } else {
    // Non-industrial canopy or rural zone
    scoreBiomass += 40;
    scoreWildfire += 35;
    scoreFlare -= 40;
    scoreSpike -= 30;
  }

  // Feature B: Fire Radiative Power (FRP MW) Magnitude
  if (frpMW >= 250) {
    scoreSpike += 50;
    scoreFlare += 30;
  } else if (frpMW >= 100) {
    scoreFlare += 40;
    scoreSpike += 20;
    scoreWildfire += 15;
  } else if (frpMW >= 40) {
    scoreFlare += 15;
    scoreBiomass += 30;
  } else {
    scoreUnverified += 45;
    scoreBiomass += 20;
  }

  // Feature C: Thermal Delta Signature (High ti4-ti5 indicates intense gas flare / hot metal furnace)
  if (thermalDelta > 100) {
    scoreFlare += 30;
    scoreSpike += 35;
  } else if (thermalDelta < 30 && !isIndustrialOverlap) {
    scoreBiomass += 25;
    scoreWildfire += 20;
  }

  // Feature D: Day/Night Pass Consistency
  if (dayNight === 'NIGHT_PASS' && isIndustrialOverlap) {
    // Night thermal detections over factories strongly favor continuous flaring
    scoreFlare += 15;
  }

  // Feature E: Low Confidence Sat Detection
  if (confidence < 50) {
    scoreUnverified += 40;
  }

  // Normalize scores into softmax-style probability distribution (0 to 1)
  const rawScores = [
    Math.max(0, scoreFlare),
    Math.max(0, scoreSpike),
    Math.max(0, scoreBiomass),
    Math.max(0, scoreWildfire),
    Math.max(0, scoreUnverified)
  ];
  
  const totalScore = rawScores.reduce((a, b) => a + b, 0) || 1;

  const probs: ClassificationProbabilities = {
    industrial_flare: Number((rawScores[0] / totalScore).toFixed(2)),
    abnormal_spike: Number((rawScores[1] / totalScore).toFixed(2)),
    biomass_burning: Number((rawScores[2] / totalScore).toFixed(2)),
    wildfire: Number((rawScores[3] / totalScore).toFixed(2)),
    unverified: Number((rawScores[4] / totalScore).toFixed(2)),
  };

  // Determine winning class
  let primaryType: AnomalyType = 'PERSISTENT_FLARE';
  let classificationTag = 'CONFIRMED INDUSTRIAL FLARE';
  let defensePriority: 'DELTA-1' | 'ALPHA-2' | 'BRAVO-1' | 'CHARLIE-3' = 'BRAVO-1';

  if (probs.abnormal_spike >= 0.35 && frpMW >= 200) {
    primaryType = 'CRITICAL_SPIKE';
    classificationTag = `ABNORMAL REFINERY SPIKE (+${Math.round((frpMW / 200) * 35)}%)`;
    defensePriority = 'DELTA-1';
  } else if (probs.industrial_flare >= 0.40) {
    primaryType = 'PERSISTENT_FLARE';
    classificationTag = 'CONFIRMED INDUSTRIAL FLARE';
    defensePriority = 'BRAVO-1';
  } else if (probs.wildfire >= 0.35) {
    primaryType = 'BIOMASS_FIRE';
    classificationTag = 'NATURAL BIOMASS WILDFIRE';
    defensePriority = 'ALPHA-2';
  } else if (probs.biomass_burning >= 0.35) {
    primaryType = 'AGRICULTURAL_STUBBLE';
    classificationTag = 'UNVERIFIED STUBBLE BURNING CLUSTER';
    defensePriority = 'CHARLIE-3';
  } else {
    primaryType = 'THERMAL_TELEMETRY';
    classificationTag = 'UNVERIFIED THERMAL SIGNATURE';
    defensePriority = 'CHARLIE-3';
  }

  // Calculate composite spatial risk score (0 - 100)
  const riskScore = Math.min(
    100,
    Math.round(
      (frpMW / 350) * 40 +
      (brightTi4K / 600) * 30 +
      (confidence / 100) * 15 +
      (isIndustrialOverlap ? 15 : 5)
    )
  );

  return {
    primaryType,
    classificationTag,
    probabilities: probs,
    riskScore,
    defensePriority,
  };
}
