import { NextRequest, NextResponse } from 'next/server';
import { getAllAnomaliesFromDB, getAnomalyByIdFromDB } from '@/lib/db';
import { ThermalTarget } from '@/lib/types';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const id = searchParams.get('id');
  const filter = searchParams.get('filter');

  if (id) {
    const anomaly = await getAnomalyByIdFromDB(id);
    if (!anomaly) {
      return NextResponse.json({ error: 'Target not found' }, { status: 404 });
    }
    return NextResponse.json({ success: true, anomaly });
  }

  let anomalies: ThermalTarget[] = await getAllAnomaliesFromDB();

  if (filter && filter !== 'ALL') {
    anomalies = anomalies.filter(a => a.type === filter);
  }

  return NextResponse.json({
    success: true,
    total: anomalies.length,
    anomalies,
  });
}
