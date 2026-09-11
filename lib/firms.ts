import { 
  ThermalTarget, 
  FirmsRawRecord, 
  SensorType, 
  ThermalHistoryPoint 
} from './types';
import { findNearestIndustrialFacility } from './landcover';
import { classifyAnomaly } from './classifier';

/**
 * Normalizes raw NASA FIRMS (VIIRS/MODIS) records into application ThermalTarget schema.
 */
export function normalizeFirmsRecord(
  raw: FirmsRawRecord,
  index: number = 0,
  isLiveDownlink: boolean = false
): ThermalTarget {
  const lat = typeof raw.latitude === 'string' ? parseFloat(raw.latitude) : raw.latitude;
  const lng = typeof raw.longitude === 'string' ? parseFloat(raw.longitude) : raw.longitude;
  const brightTi4K = typeof raw.bright_ti4 === 'string' ? parseFloat(raw.bright_ti4) : raw.bright_ti4;
  const brightTi5K = raw.bright_ti5 
    ? (typeof raw.bright_ti5 === 'string' ? parseFloat(raw.bright_ti5) : raw.bright_ti5)
    : brightTi4K - 120.0;
  
  const frpMW = typeof raw.frp === 'string' ? parseFloat(raw.frp) : raw.frp;
  
  // Parse confidence
  let confidence = 85;
  if (typeof raw.confidence === 'string') {
    if (raw.confidence.toLowerCase() === 'h') confidence = 96;
    else if (raw.confidence.toLowerCase() === 'n') confidence = 78;
    else if (raw.confidence.toLowerCase() === 'l') confidence = 45;
    else confidence = parseInt(raw.confidence, 10) || 75;
  } else if (typeof raw.confidence === 'number') {
    confidence = raw.confidence;
  }

  // Parse sensor
  let sensorId: SensorType = 'VIIRS_VNP14IMGTDL';
  if (raw.satellite === 'N' || raw.satellite === 'NOAA-20') sensorId = 'VIIRS_NRT_NOAA20';
  else if (raw.satellite === 'T' || raw.satellite === 'TERRA') sensorId = 'MODIS_MYD14';

  const dayNight: 'DAY_PASS' | 'NIGHT_PASS' = raw.daynight === 'D' ? 'DAY_PASS' : 'NIGHT_PASS';

  // Spatial landcover cross-reference
  const landcoverMatch = findNearestIndustrialFacility(lat, lng, 5000);

  // Acquisition timestamp
  const dateStr = raw.acq_date || new Date().toISOString().substring(0, 10);
  const timeStr = raw.acq_time ? `${raw.acq_time.padStart(4, '0').substring(0, 2)}:${raw.acq_time.padStart(4, '0').substring(2, 4)}` : '23:45';
  const lastDetected = `${dateStr} ${timeStr}:00 UTC`;

  // Deterministic 7-day history with explicit isMockHistory provenance flag
  const history7Days: ThermalHistoryPoint[] = generate7DayBaselineHistory(dateStr, brightTi4K, frpMW);

  // AI Probabilistic Classifier calibrated with history and landcover
  const classification = classifyAnomaly({
    frpMW,
    brightTi4K,
    brightTi5K,
    distanceToIndustrialMeters: landcoverMatch.distanceMeters,
    isIndustrialOverlap: landcoverMatch.isIndustrialOverlap,
    facilityType: landcoverMatch.facilityType,
    dominantLandCover: landcoverMatch.dominantLandCover,
    dayNight,
    confidence,
    history7Days,
  });

  const brightTempC = Number((brightTi4K - 273.15).toFixed(1));
  const id = `TRG-VNR-${String(index + 1).padStart(2, '0')}`;

  return {
    id,
    name: landcoverMatch.name,
    facilityType: landcoverMatch.facilityType,
    state: landcoverMatch.state,
    coordinates: [lat, lng],
    type: classification.primaryType,
    classification: classification.classificationTag,
    sensorId,
    brightnessTempK: Number(brightTi4K.toFixed(1)),
    brightTi4: Number(brightTi4K.toFixed(1)),
    brightTi5: Number(brightTi5K.toFixed(1)),
    brightTempC,
    frpMW: Number(frpMW.toFixed(1)),
    confidence,
    osmOverlap: landcoverMatch.isIndustrialOverlap,
    nearestFacilityName: landcoverMatch.name,
    distanceToFacilityMeters: landcoverMatch.distanceMeters,
    lastDetected,
    dayNight,
    status: frpMW > 250 ? 'ACTIVE_ALERT' : (landcoverMatch.isIndustrialOverlap ? 'VERIFIED_STABLE' : 'UNVERIFIED'),
    defensePriority: classification.defensePriority,
    riskScore: classification.riskScore,
    description: `Satellite detection via ${sensorId}. FRP: ${frpMW} MW, Temp: ${brightTi4K} K (${brightTempC} °C). Infrastructure match: ${landcoverMatch.name} (${landcoverMatch.facilityType}, ${landcoverMatch.distanceMeters}m).`,
    history7Days,
    classificationProbs: classification.probabilities,
    isSynthetic: !isLiveDownlink,
    dataSourceLabel: isLiveDownlink 
      ? 'LIVE DIRECT DOWNLINK (NASA-EOSDIS)' 
      : 'ORBITAL CACHE // VIIRS-SNPP REPLAY',
  };
}

/**
 * Generates a deterministic 7-day thermal intensity history.
 */
function generate7DayBaselineHistory(
  baseDateStr: string,
  currentTempK: number,
  currentFrpMW: number
): ThermalHistoryPoint[] {
  const history: ThermalHistoryPoint[] = [];
  const baseDate = new Date(baseDateStr);

  for (let i = 6; i >= 0; i--) {
    const d = new Date(baseDate);
    d.setDate(d.getDate() - i);
    const mmdd = `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

    const tempVariance = i === 0 ? 0 : Math.sin(i * 1.5) * 8;
    const frpVariance = i === 0 ? 0 : Math.sin(i * 1.5) * 12;

    history.push({
      date: mmdd,
      tempK: Number((currentTempK + tempVariance).toFixed(1)),
      frpMW: Math.max(1, Number((currentFrpMW + frpVariance).toFixed(1))),
      isMockHistory: true,
    });
  }

  return history;
}
