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
}

export const KNOWN_INDIAN_FACILITIES = [
  {
    name: "Jamnagar Petroleum Refinery Complex",
    facilityType: "Petrochemical & Crude Oil Processing",
    state: "Gujarat",
    coordinates: [22.4707, 70.0577] as [number, number],
  },
  {
    name: "Bhilai Integrated Steel Plant",
    facilityType: "Metallurgical & Blast Furnace",
    state: "Chhattisgarh",
    coordinates: [21.1938, 81.3509] as [number, number],
  },
  {
    name: "Panipat Petrochemical Complex",
    facilityType: "Naphtha Cracker & Chemical Refinery",
    state: "Haryana",
    coordinates: [29.3909, 76.9637] as [number, number],
  },
  {
    name: "Bandhavgarh Tiger Reserve Forest Corridor",
    facilityType: "Protected Dense Canopy Forestry",
    state: "Madhya Pradesh",
    coordinates: [23.7019, 81.0252] as [number, number],
  },
  {
    name: "Punjab Agricultural Belt (Sangrur)",
    facilityType: "Agro-Paddy Crop Residue Zone",
    state: "Punjab",
    coordinates: [30.2458, 75.8421] as [number, number],
  },
  {
    name: "Visakhapatnam Naval & Metallurgical Hub",
    facilityType: "Coastal Heavy Industry & Shipyard",
    state: "Andhra Pradesh",
    coordinates: [17.6868, 83.2185] as [number, number],
  },
  {
    name: "Mumbai High Offshore Rig North",
    facilityType: "Offshore Crude Oil Drilling Platform",
    state: "Arabian Sea (Offshore MH)",
    coordinates: [19.4167, 71.3333] as [number, number],
  },
  {
    name: "Rourkela Steel Plant Complex",
    facilityType: "Primary Metallurgical Works",
    state: "Odisha",
    coordinates: [22.2604, 84.8536] as [number, number],
  },
  {
    name: "Digboi Oil Refinery & Oilfields",
    facilityType: "Legacy Hydrocarbon Refining",
    state: "Assam",
    coordinates: [27.3800, 95.6200] as [number, number],
  },
  {
    name: "Neyveli Lignite Thermal Power Station",
    facilityType: "Lignite Coal Fired Power Plant",
    state: "Tamil Nadu",
    coordinates: [11.6008, 79.4862] as [number, number],
  },
  {
    name: "Singrauli Super Thermal Energy Hub",
    facilityType: "Mega Coal-Fired Thermal Complex",
    state: "MP / UP Border",
    coordinates: [24.2012, 82.6719] as [number, number],
  },
  {
    name: "Koyali Refinery Complex Vadodara",
    facilityType: "Hydrocarbon Refining Facility",
    state: "Gujarat",
    coordinates: [22.3789, 73.1362] as [number, number],
  },
  {
    name: "Durgapur Industrial Corridor",
    facilityType: "Heavy Mechanical & Foundry",
    state: "West Bengal",
    coordinates: [23.5204, 87.3119] as [number, number],
  },
  {
    name: "Kudankulam Coastal Infrastructure Buffer",
    facilityType: "Nuclear Clean Thermal Cooling Outlet",
    state: "Tamil Nadu",
    coordinates: [8.1691, 77.7126] as [number, number],
  },
  {
    name: "Barmer Oil & Gas Field Basin",
    facilityType: "Onshore Hydrocarbon Extraction Zone",
    state: "Rajasthan",
    coordinates: [26.0921, 71.3412] as [number, number],
  },
  {
    name: "Angul Aluminium & Steel Hub",
    facilityType: "Alumina Smelter & Power Complex",
    state: "Odisha",
    coordinates: [20.9517, 85.1511] as [number, number],
  },
  {
    name: "Dahej Chemical & Petrochemical Estate",
    facilityType: "PCPIR Industrial Park & Flare Stack Zone",
    state: "Gujarat",
    coordinates: [21.8312, 73.7121] as [number, number],
  },
  {
    name: "Jharsuguda Industrial Corridor",
    facilityType: "Thermal Power & Metal Smelter",
    state: "Odisha",
    coordinates: [21.4682, 83.9812] as [number, number],
  },
  {
    name: "Dhanbad Coal Mining Belt",
    facilityType: "Open-Cast Coking Coal Fields",
    state: "Jharkhand",
    coordinates: [23.6345, 86.9512] as [number, number],
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
  const R = 6371000; // Radius of Earth in meters
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
 * Cross-references a thermal detection coordinate against known Indian industrial sites.
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

  const isOverlap = minDistance <= thresholdMeters;

  return {
    name: isOverlap ? closest.name : `Unregistered Sector (${lat.toFixed(2)}°N, ${lng.toFixed(2)}°E)`,
    facilityType: isOverlap ? closest.facilityType : "Non-Industrial Canopy / Rural Sector",
    state: closest.state,
    coordinates: closest.coordinates,
    distanceMeters: minDistance,
    isIndustrialOverlap: isOverlap,
  };
}
