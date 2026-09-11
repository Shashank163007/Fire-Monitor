/**
 * OpenStreetMap (OSM) Overpass Spatial Fusion Engine
 * Queries OSM Overpass API for industrial polygons & landcover negative signals.
 * Industrial tags ALWAYS take absolute precedence over ambient tree/scrub tags.
 */

import { findNearestIndustrialFacility } from './landcover';

export interface OverpassResult {
  overlap: boolean;
  facilityName: string;
  facilityType: string;
  distanceMeters: number;
  dominantLandCover: 'INDUSTRIAL' | 'FOREST' | 'FARMLAND' | 'UNCLASSIFIED';
  source: 'OVERPASS_API_LIVE' | 'ORBITAL_CACHE_SPATIAL_INDEX';
  isSynthetic: boolean;
  timestamp: string;
}

const OVERPASS_CACHE = new Map<string, { data: OverpassResult; expiresAt: number }>();
const CACHE_TTL_MS = 60 * 60 * 1000;

export async function checkIndustrialOverlap(
  lat: number,
  lng: number,
  radiusMeters: number = 2000
): Promise<OverpassResult> {
  const cacheKey = `${lat.toFixed(3)}_${lng.toFixed(3)}_${radiusMeters}`;
  const now = Date.now();

  // 1. Check TTL Cache
  const cached = OVERPASS_CACHE.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    return cached.data;
  }

  // 2. Build Overpass QL Query
  const overpassQL = `
    [out:json][timeout:4];
    (
      nwr(around:${radiusMeters},${lat},${lng})["landuse"="industrial"];
      nwr(around:${radiusMeters},${lat},${lng})["man_made"="works"];
      nwr(around:${radiusMeters},${lat},${lng})["man_made"="petroleum_terminal"];
      nwr(around:${radiusMeters},${lat},${lng})["power"="plant"];
      nwr(around:${radiusMeters},${lat},${lng})["natural"="wood"];
      nwr(around:${radiusMeters},${lat},${lng})["landuse"="forest"];
      nwr(around:${radiusMeters},${lat},${lng})["landuse"="farmland"];
    );
    out tags 15;
  `.trim();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);

  try {
    const res = await fetch('https://overpass-api.de/api/interpreter', {
      method: 'POST',
      body: `data=${encodeURIComponent(overpassQL)}`,
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'NTRO-GIS-Nexus/2.0',
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      const elements: any[] = data.elements || [];

      let industrialCount = 0;
      let forestCount = 0;
      let farmlandCount = 0;
      let closestFacilityName = '';
      let closestFacilityType = '';

      elements.forEach(elem => {
        const tags = elem.tags || {};
        // Industrial check takes absolute priority
        if (tags.landuse === 'industrial' || tags.man_made === 'works' || tags.man_made === 'petroleum_terminal' || tags.power === 'plant') {
          industrialCount++;
          if (!closestFacilityName && (tags.name || tags.operator || tags.man_made || tags.landuse)) {
            closestFacilityName = tags.name || tags.operator || `${tags.man_made || tags.landuse} facility`;
            closestFacilityType = tags.man_made === 'petroleum_terminal' ? 'petroleum_refinery' : (tags.man_made ? `man_made=${tags.man_made}` : `landuse=${tags.landuse}`);
          }
        } else if (tags.natural === 'wood' || tags.landuse === 'forest') {
          forestCount++;
        } else if (tags.landuse === 'farmland') {
          farmlandCount++;
        }
      });

      // Strict Priority Rule: Industrial > Forest > Farmland
      let dominantLandCover: 'INDUSTRIAL' | 'FOREST' | 'FARMLAND' | 'UNCLASSIFIED' = 'UNCLASSIFIED';
      if (industrialCount > 0) {
        dominantLandCover = 'INDUSTRIAL';
      } else if (forestCount > farmlandCount && forestCount > 0) {
        dominantLandCover = 'FOREST';
      } else if (farmlandCount > 0) {
        dominantLandCover = 'FARMLAND';
      }

      const overlap = industrialCount > 0;
      
      const result: OverpassResult = {
        overlap,
        facilityName: overlap 
          ? closestFacilityName || 'Confirmed OSM Industrial Facility'
          : (dominantLandCover === 'FOREST' ? 'Forest Reserve Canopy' : 'Agricultural Farmland Zone'),
        facilityType: closestFacilityType || (overlap ? 'petroleum_refinery' : `landcover=${dominantLandCover.toLowerCase()}`),
        distanceMeters: overlap ? 250 : radiusMeters,
        dominantLandCover,
        source: 'OVERPASS_API_LIVE',
        isSynthetic: false,
        timestamp: new Date().toISOString(),
      };

      OVERPASS_CACHE.set(cacheKey, { data: result, expiresAt: now + CACHE_TTL_MS });
      return result;
    }
  } catch (err: any) {
    clearTimeout(timeoutId);
    console.warn('[OVERPASS ENGINE] Live API query timed out (4s) or failed. Engaging Spatial Index Fallback.');
  }

  // Fallback to local spatial lookup
  const fallbackMatch = findNearestIndustrialFacility(lat, lng, radiusMeters);

  const fallbackResult: OverpassResult = {
    overlap: fallbackMatch.isIndustrialOverlap,
    facilityName: fallbackMatch.name,
    facilityType: fallbackMatch.facilityType,
    distanceMeters: fallbackMatch.distanceMeters,
    dominantLandCover: fallbackMatch.dominantLandCover,
    source: 'ORBITAL_CACHE_SPATIAL_INDEX',
    isSynthetic: true,
    timestamp: new Date().toISOString(),
  };

  OVERPASS_CACHE.set(cacheKey, { data: fallbackResult, expiresAt: now + CACHE_TTL_MS });

  return fallbackResult;
}
