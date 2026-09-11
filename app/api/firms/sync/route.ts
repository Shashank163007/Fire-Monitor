import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { FirmsRawRecord, FirmsSyncResponse, ThermalTarget } from '@/lib/types';
import { normalizeFirmsRecord } from '@/lib/firms';
import { upsertAnomaliesToDB } from '@/lib/db';

export async function GET(req: NextRequest) {
  return handleSync(req);
}

export async function POST(req: NextRequest) {
  return handleSync(req);
}

async function handleSync(req: NextRequest): Promise<NextResponse> {
  const startTime = Date.now();
  const apiKey = process.env.NASA_FIRMS_MAP_KEY;
  
  let rawRecords: FirmsRawRecord[] = [];
  let isLiveDownlink = false;
  let sourceMode: 'NASA_FIRMS_LIVE' | 'ORBITAL_CACHE_REPLAY' = 'ORBITAL_CACHE_REPLAY';
  let sourceLabel = 'ORBITAL CACHE // VIIRS-SNPP REPLAY';

  // 1. Attempt Live NASA FIRMS Ingestion if API Key defined
  if (apiKey && apiKey.trim() !== '') {
    try {
      const url = `https://firms.modaps.eosdis.nasa.gov/api/country/csv/${apiKey.trim()}/VIIRS_SNPP_NRT/IND/1`;
      const res = await fetch(url, { next: { revalidate: 300 } });

      if (res.ok) {
        const csvText = await res.text();
        const parsed = parseFirmsCSV(csvText);
        if (parsed.length > 0) {
          rawRecords = parsed;
          isLiveDownlink = true;
          sourceMode = 'NASA_FIRMS_LIVE';
          sourceLabel = 'LIVE DIRECT DOWNLINK (NASA-EOSDIS)';
        }
      }
    } catch (err) {
      console.warn('[FIRMS SYNC] Live fetch failed or throttled. Engaging Orbital Cache Fallback.', err);
    }
  }

  // 2. Zero-Latency Fallback to Bundled India VIIRS Satellite Dataset
  if (rawRecords.length === 0) {
    try {
      const fallbackPath = path.join(process.cwd(), 'data', 'firms-india-real.json');
      if (fs.existsSync(fallbackPath)) {
        const fileData = fs.readFileSync(fallbackPath, 'utf-8');
        rawRecords = JSON.parse(fileData);
      }
    } catch (err) {
      console.error('[FIRMS SYNC] Fallback read error:', err);
    }
  }

  // 3. Spatial Bounding Box Filter for India (Lat: 6.5-37.0 N, Lng: 68.0-97.5 E)
  const validRecords = rawRecords.filter(r => {
    const lat = typeof r.latitude === 'string' ? parseFloat(r.latitude) : r.latitude;
    const lng = typeof r.longitude === 'string' ? parseFloat(r.longitude) : r.longitude;
    return lat >= 6.5 && lat <= 37.0 && lng >= 68.0 && lng <= 97.5;
  });

  // 4. Normalize records & run AI Landcover / Proximity Classification
  const anomalies: ThermalTarget[] = validRecords.map((rec, idx) => 
    normalizeFirmsRecord(rec, idx, isLiveDownlink)
  );

  // 5. Upsert anomalies into persistent DB
  await upsertAnomaliesToDB(anomalies);

  const latencyMs = Date.now() - startTime;

  const response: FirmsSyncResponse = {
    success: true,
    source: sourceMode,
    sourceLabel,
    timestamp: new Date().toISOString(),
    sensor: 'VIIRS_NRT_NOAA20',
    totalIngested: anomalies.length,
    latencyMs,
    anomalies,
  };

  return NextResponse.json(response);
}

/**
 * Parses raw NASA FIRMS CSV output into structured FirmsRawRecord array.
 */
function parseFirmsCSV(csvText: string): FirmsRawRecord[] {
  const lines = csvText.trim().split('\n');
  if (lines.length < 2) return [];

  const headers = lines[0].split(',').map(h => h.trim());
  const records: FirmsRawRecord[] = [];

  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(',').map(v => v.trim());
    if (values.length < headers.length) continue;

    const row: any = {};
    headers.forEach((h, idx) => {
      row[h] = values[idx];
    });

    records.push({
      latitude: parseFloat(row.latitude),
      longitude: parseFloat(row.longitude),
      bright_ti4: parseFloat(row.bright_ti4),
      scan: parseFloat(row.scan || '0.39'),
      track: parseFloat(row.track || '0.36'),
      acq_date: row.acq_date,
      acq_time: row.acq_time,
      satellite: row.satellite,
      confidence: row.confidence,
      bright_ti5: row.bright_ti5 ? parseFloat(row.bright_ti5) : undefined,
      frp: parseFloat(row.frp || '0'),
      daynight: row.daynight,
    });
  }

  return records;
}
