import { NextResponse } from 'next/server';
import Papa from 'papaparse';
import { supabase, NTROAnomaly, SupabaseNTROAnomalyRecord } from '@/lib/supabase';
import { checkIndustrialInfrastructure } from '@/lib/osm';

interface FIRMSCsvRecord {
  latitude: string;
  longitude: string;
  bright_ti4?: string;
  brightness?: string;
  scan?: string;
  track?: string;
  acq_date: string;
  acq_time: string;
  satellite?: string;
  instrument?: string;
  confidence: string;
  version?: string;
  bright_ti5?: string;
  frp?: string;
  daynight?: string;
}

function isHighOrNominalConfidence(confidence: string): boolean {
  if (!confidence) return true;
  const c = String(confidence).toLowerCase().trim();
  if (c === 'h' || c === 'high' || c === 'n' || c === 'nominal') return true;
  if (c === 'l' || c === 'low') return false;
  const num = parseFloat(c);
  if (!isNaN(num)) return num >= 50;
  return true;
}

function parseDetectionTimestamp(acq_date: string, acq_time: string): string {
  if (!acq_date) return new Date().toISOString();
  const timeStr = (acq_time || '0000').padStart(4, '0');
  const hours = timeStr.slice(0, 2);
  const minutes = timeStr.slice(2, 4);
  const isoStr = `${acq_date}T${hours}:${minutes}:00Z`;
  const dateObj = new Date(isoStr);
  return isNaN(dateObj.getTime()) ? new Date().toISOString() : dateObj.toISOString();
}

export async function GET() {
  const apiKey = process.env.NASA_FIRMS_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: 'NASA_FIRMS_API_KEY environment variable is not configured.' },
      { status: 500 }
    );
  }

  const firmsUrl = `https://firms.modaps.eosdis.nasa.gov/api/area/csv/${apiKey}/VIIRS_SNPP_NRT/68,6.5,97.5,37/1`;

  try {
    const response = await fetch(firmsUrl, { next: { revalidate: 0 } });
    if (!response.ok) {
      return NextResponse.json(
        { error: `NASA FIRMS API returned HTTP status ${response.status}` },
        { status: 502 }
      );
    }

    const csvText = await response.text();

    const parsed = Papa.parse<FIRMSCsvRecord>(csvText, {
      header: true,
      skipEmptyLines: true,
    });

    const rawRecords = parsed.data || [];
    const highConfidenceRecords = rawRecords.filter((rec) =>
      rec.latitude && rec.longitude && isHighOrNominalConfidence(rec.confidence)
    );

    const anomalies: NTROAnomaly[] = [];
    const dbRecords: SupabaseNTROAnomalyRecord[] = [];

    // Process in batches of 5 to run OSM spatial fusion queries efficiently
    const BATCH_SIZE = 5;
    for (let i = 0; i < highConfidenceRecords.length; i += BATCH_SIZE) {
      const batch = highConfidenceRecords.slice(i, i + BATCH_SIZE);
      const batchResults = await Promise.all(
        batch.map(async (record) => {
          const lat = parseFloat(record.latitude);
          const lng = parseFloat(record.longitude);

          if (isNaN(lat) || isNaN(lng)) return null;

          const osmResult = await checkIndustrialInfrastructure(lat, lng);
          const classification: 'INDUSTRIAL_FLARE' | 'NATURAL_FOREST_FIRE' =
            osmResult.osm_infrastructure_match ? 'INDUSTRIAL_FLARE' : 'NATURAL_FOREST_FIRE';

          const brightness_k = parseFloat(record.bright_ti4 || record.brightness || '0');
          const frp_mw = parseFloat(record.frp || '0');
          const detectionTimestamp = parseDetectionTimestamp(record.acq_date, record.acq_time);
          const uniqueId = `${lat}_${lng}_${record.acq_date}`;

          const landcoverMatch = JSON.stringify({
            osm_infrastructure_match: osmResult.osm_infrastructure_match,
            facility_name: osmResult.facility_name,
            facility_type: osmResult.facility_type,
          });

          const dbRecord: SupabaseNTROAnomalyRecord = {
            id: uniqueId,
            latitude: lat,
            longitude: lng,
            brightness_k,
            frp_mw,
            confidence: record.confidence || 'nominal',
            satellite: record.satellite || 'VIIRS_SNPP_NRT',
            classification,
            detection_timestamp: detectionTimestamp,
            landcover_match: landcoverMatch,
          };

          const fullAnomaly: NTROAnomaly = {
            ...dbRecord,
            brightness: brightness_k,
            scan: parseFloat(record.scan || '0'),
            track: parseFloat(record.track || '0'),
            acq_date: record.acq_date,
            acq_time: record.acq_time,
            instrument: record.instrument || 'VIIRS',
            version: record.version || '1',
            bright_ti5: parseFloat(record.bright_ti5 || '0'),
            frp: frp_mw,
            daynight: record.daynight || 'D',
            osm_infrastructure_match: osmResult.osm_infrastructure_match,
            facility_name: osmResult.facility_name,
            facility_type: osmResult.facility_type,
          };

          return { dbRecord, fullAnomaly };
        })
      );

      for (const res of batchResults) {
        if (res) {
          dbRecords.push(res.dbRecord);
          anomalies.push(res.fullAnomaly);
        }
      }
    }

    let upsertedCount = 0;
    if (dbRecords.length > 0) {
      const { data: upsertData, error: upsertError } = await supabase
        .from('ntro_anomalies')
        .upsert(dbRecords, { onConflict: 'id' })
        .select();

      if (upsertError) {
        return NextResponse.json(
          {
            error: 'Failed to upsert records into Supabase ntro_anomalies',
            details: upsertError.message,
          },
          { status: 500 }
        );
      }

      upsertedCount = upsertData ? upsertData.length : dbRecords.length;
    }

    return NextResponse.json({
      success: true,
      total_records_fetched: rawRecords.length,
      high_confidence_records: highConfidenceRecords.length,
      upserted_count: upsertedCount,
      anomalies,
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error?.message || 'An unexpected error occurred during live sync.' },
      { status: 500 }
    );
  }
}
