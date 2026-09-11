/**
 * Land-Cover & OSM Industrial Polygon Cross-Reference Engine for India
 * Computes exact spatial proximity (meters) to major critical infrastructure facilities.
 */

export interface FacilityMatch {
  name: string;
  facilityType: string;
  state: string;
  coordinates: [number, number];
  distanceMeters: number;
  isIndustrialOverlap: boolean;
  dominantLandCover: 'INDUSTRIAL' | 'FOREST' | 'FARMLAND' | 'UNCLASSIFIED';
}

export const KNOWN_INDIAN_FACILITIES = [
  {
    name: "Jamnagar Petroleum & Petrochemical Complex",
    facilityType: "petroleum_refinery",
    state: "Gujarat",
    coordinates: [22.4707, 70.0577] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Jamnagar Petrochemical Complex (West Basin)",
    facilityType: "petroleum_refinery",
    state: "Gujarat",
    coordinates: [22.3590, 69.8640] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Bhilai Integrated Steel Plant",
    facilityType: "metallurgical_plant",
    state: "Chhattisgarh",
    coordinates: [21.1938, 81.3509] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Panipat Petrochemical Complex",
    facilityType: "chemical_refinery",
    state: "Haryana",
    coordinates: [29.3909, 76.9637] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Bandhavgarh Tiger Reserve Forest Corridor",
    facilityType: "national_park",
    state: "Madhya Pradesh",
    coordinates: [23.6850, 81.0310] as [number, number],
    dominantLandCover: 'FOREST' as const,
  },
  {
    name: "Bandhavgarh Tiger Reserve Forest Corridor (North)",
    facilityType: "national_park",
    state: "Madhya Pradesh",
    coordinates: [23.7019, 81.0252] as [number, number],
    dominantLandCover: 'FOREST' as const,
  },
  {
    name: "Punjab Agricultural Belt (Sangrur)",
    facilityType: "paddy_agricultural_belt",
    state: "Punjab",
    coordinates: [30.2458, 75.8421] as [number, number],
    dominantLandCover: 'FARMLAND' as const,
  },
  {
    name: "Visakhapatnam Naval & Metallurgical Hub",
    facilityType: "shipyard_metallurgical",
    state: "Andhra Pradesh",
    coordinates: [17.6868, 83.2185] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Mumbai High Offshore Rig North",
    facilityType: "offshore_drilling_platform",
    state: "Arabian Sea (Offshore MH)",
    coordinates: [19.4167, 71.3333] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Rourkela Steel Plant Complex",
    facilityType: "steel_plant",
    state: "Odisha",
    coordinates: [22.2604, 84.8536] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Digboi Oil Refinery & Oilfields",
    facilityType: "petroleum_refinery",
    state: "Assam",
    coordinates: [27.3800, 95.6200] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Neyveli Lignite Thermal Power Station",
    facilityType: "power_plant",
    state: "Tamil Nadu",
    coordinates: [11.6008, 79.4862] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Singrauli Super Thermal Energy Hub",
    facilityType: "power_plant",
    state: "MP / UP Border",
    coordinates: [24.2012, 82.6719] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Koyali Refinery Complex Vadodara",
    facilityType: "petroleum_refinery",
    state: "Gujarat",
    coordinates: [22.3789, 73.1362] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Durgapur Industrial Corridor",
    facilityType: "foundry_metallurgical",
    state: "West Bengal",
    coordinates: [23.5204, 87.3119] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  },
  {
    name: "Kudankulam Coastal Infrastructure Buffer",
    facilityType: "nuclear_cooling_buffer",
    state: "Tamil Nadu",
    coordinates: [8.1691, 77.7126] as [number, number],
    dominantLandCover: 'INDUSTRIAL' as const,
  }
];

/**
 * Calculates Haversine distance between two lat/lng points in meters.
 */
export function calculateHaversineDistance(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) *
      Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(R * c);
}

/**
 * Cross-references a thermal detection coordinate against known Indian industrial/forest sites.
 */
export function findNearestIndustrialFacility(
  lat: number,
  lng: number,
  thresholdMeters: number = 5000
): FacilityMatch {
  let minDistance = Infinity;
  let closest = KNOWN_INDIAN_FACILITIES[0];

  for (const fac of KNOWN_INDIAN_FACILITIES) {
    const dist = calculateHaversineDistance(lat, lng, fac.coordinates[0], fac.coordinates[1]);
    if (dist < minDistance) {
      minDistance = dist;
      closest = fac;
    }
  }

  const isOverlap = minDistance <= thresholdMeters && closest.dominantLandCover === 'INDUSTRIAL';

  return {
    name: minDistance <= thresholdMeters ? closest.name : `Unregistered Sector (${lat.toFixed(2)}°N, ${lng.toFixed(2)}°E)`,
    facilityType: minDistance <= thresholdMeters ? closest.facilityType : "rural_canopy",
    state: closest.state,
    coordinates: closest.coordinates,
    distanceMeters: minDistance,
    isIndustrialOverlap: isOverlap,
    dominantLandCover: minDistance <= thresholdMeters ? closest.dominantLandCover : 'UNCLASSIFIED',
  };
}
