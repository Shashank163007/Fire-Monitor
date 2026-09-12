import { NextResponse } from 'next/server';
import { supabase, NTROAnomaly } from '@/lib/supabase';

export async function GET() {
  try {
    const { data, error } = await supabase
      .from('ntro_anomalies')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(200);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    const anomalies: NTROAnomaly[] = (data || []).map((record: any) => {
      let osm_infrastructure_match = record.classification === 'INDUSTRIAL_FLARE';
      let facility_name: string | null = null;
      let facility_type: string | null = null;

      if (record.landcover_match) {
        try {
          const parsed = JSON.parse(record.landcover_match);
          if (parsed && typeof parsed === 'object') {
            osm_infrastructure_match = Boolean(parsed.osm_infrastructure_match);
            facility_name = parsed.facility_name ?? null;
            facility_type = parsed.facility_type ?? null;
          }
        } catch {
          // If landcover_match is not JSON
        }
      }

      return {
        id: record.id,
        latitude: record.latitude,
        longitude: record.longitude,
        brightness: record.brightness_k ?? record.brightness,
        brightness_k: record.brightness_k,
        frp: record.frp_mw ?? record.frp,
        frp_mw: record.frp_mw,
        confidence: record.confidence,
        satellite: record.satellite,
        classification: record.classification,
        detection_timestamp: record.detection_timestamp,
        landcover_match: record.landcover_match,
        osm_infrastructure_match,
        facility_name,
        facility_type,
        created_at: record.created_at,
      };
    });

    return NextResponse.json(anomalies);
  } catch (err: any) {
    return NextResponse.json(
      { error: err?.message || 'Internal server error' },
      { status: 500 }
    );
  }
}
