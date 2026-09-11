import { NextRequest, NextResponse } from 'next/server';
import { checkIndustrialOverlap } from '@/lib/overpass';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const latStr = searchParams.get('lat');
  const lngStr = searchParams.get('lng');
  const radiusStr = searchParams.get('radius');

  if (!latStr || !lngStr) {
    return NextResponse.json(
      { error: 'Missing required parameters lat and lng' },
      { status: 400 }
    );
  }

  const lat = parseFloat(latStr);
  const lng = parseFloat(lngStr);
  const radius = radiusStr ? parseInt(radiusStr, 10) : 2000;

  if (isNaN(lat) || isNaN(lng)) {
    return NextResponse.json(
      { error: 'Invalid lat or lng parameter' },
      { status: 400 }
    );
  }

  const result = await checkIndustrialOverlap(lat, lng, radius);

  return NextResponse.json(result);
}
