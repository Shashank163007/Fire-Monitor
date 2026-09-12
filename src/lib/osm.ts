export interface IndustrialInfrastructureResult {
  osm_infrastructure_match: boolean;
  facility_name: string | null;
  facility_type: string | null;
}

export async function checkIndustrialInfrastructure(
  lat: number,
  lng: number,
  radius = 2000
): Promise<IndustrialInfrastructureResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);

  try {
    const query = `[out:json][timeout:4];
(
  node(around:${radius},${lat},${lng})["landuse"="industrial"];
  way(around:${radius},${lat},${lng})["landuse"="industrial"];
  relation(around:${radius},${lat},${lng})["landuse"="industrial"];
  node(around:${radius},${lat},${lng})["man_made"="works"];
  way(around:${radius},${lat},${lng})["man_made"="works"];
  relation(around:${radius},${lat},${lng})["man_made"="works"];
  node(around:${radius},${lat},${lng})["man_made"="petroleum_terminal"];
  way(around:${radius},${lat},${lng})["man_made"="petroleum_terminal"];
  relation(around:${radius},${lat},${lng})["man_made"="petroleum_terminal"];
  node(around:${radius},${lat},${lng})["power"="plant"];
  way(around:${radius},${lat},${lng})["power"="plant"];
  relation(around:${radius},${lat},${lng})["power"="plant"];
);
out tags center 1;`;

    const response = await fetch('https://overpass-api.de/api/interpreter', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'NTRO-GeoThermal-Nexus/1.0 (https://ntro.gov.in)',
      },
      body: `data=${encodeURIComponent(query)}`,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      return {
        osm_infrastructure_match: false,
        facility_name: null,
        facility_type: null,
      };
    }

    const data = await response.json();
    if (data && Array.isArray(data.elements) && data.elements.length > 0) {
      const match = data.elements[0];
      const tags = match.tags || {};
      const facility_name =
        tags.name || tags['name:en'] || tags.operator || tags.brand || null;
      const facility_type =
        tags.landuse || tags.man_made || tags.power || tags.industrial || null;

      return {
        osm_infrastructure_match: true,
        facility_name,
        facility_type,
      };
    }

    return {
      osm_infrastructure_match: false,
      facility_name: null,
      facility_type: null,
    };
  } catch (error) {
    clearTimeout(timeoutId);
    return {
      osm_infrastructure_match: false,
      facility_name: null,
      facility_type: null,
    };
  }
}
