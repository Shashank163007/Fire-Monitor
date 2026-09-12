import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

if (!supabaseUrl || !supabaseServiceKey) {
  console.warn('Missing NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables.');
}

export const supabase = createClient(supabaseUrl, supabaseServiceKey);

export interface NTROAnomaly {
  id: string;
  latitude: number;
  longitude: number;
  brightness?: number;
  brightness_k?: number;
  scan?: number;
  track?: number;
  acq_date?: string;
  acq_time?: string;
  satellite?: string;
  instrument?: string;
  confidence?: string;
  version?: string;
  bright_ti5?: number;
  frp?: number;
  frp_mw?: number;
  daynight?: string;
  classification: 'INDUSTRIAL_FLARE' | 'NATURAL_FOREST_FIRE';
  osm_infrastructure_match: boolean;
  facility_name: string | null;
  facility_type: string | null;
  landcover_match?: string;
  detection_timestamp?: string;
  created_at?: string;
}

export interface SupabaseNTROAnomalyRecord {
  id: string;
  latitude: number;
  longitude: number;
  brightness_k: number;
  frp_mw: number;
  confidence: string;
  satellite: string;
  classification: 'INDUSTRIAL_FLARE' | 'NATURAL_FOREST_FIRE';
  detection_timestamp: string;
  landcover_match: string;
  created_at?: string;
}
