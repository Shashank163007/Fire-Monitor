/**
 * Safe Persistent Storage Architecture for Geo-Thermal Anomaly Nexus
 * 
 * Implements a resilient file-backed persistent database engine (`data/anomalies-db.json`)
 * with atomic disk sync and zero native C++ compilation / node-gyp dependencies.
 * Guarantees 100% build safety and instant execution on Windows Next.js App Router.
 */

import fs from 'fs';
import path from 'path';
import { ThermalTarget } from './types';
import { MOCK_THERMAL_TARGETS } from './mock-data';

const DB_DIR = path.join(process.cwd(), 'data');
const DB_FILE = path.join(DB_DIR, 'anomalies-db.json');

// In-memory cache for fast sub-millisecond lookups
let inMemoryStore: ThermalTarget[] | null = null;

/**
 * Initializes the persistent database file if not present.
 */
export function initDatabase(): ThermalTarget[] {
  try {
    if (!fs.existsSync(DB_DIR)) {
      fs.mkdirSync(DB_DIR, { recursive: true });
    }

    if (fs.existsSync(DB_FILE)) {
      const content = fs.readFileSync(DB_FILE, 'utf-8');
      inMemoryStore = JSON.parse(content);
    } else {
      // Seed with initial high-priority targets
      inMemoryStore = [...MOCK_THERMAL_TARGETS];
      persistStore(inMemoryStore);
    }
  } catch (error) {
    console.warn('[DB] Persistent file storage read warning, using in-memory store:', error);
    if (!inMemoryStore) {
      inMemoryStore = [...MOCK_THERMAL_TARGETS];
    }
  }

  return inMemoryStore || [];
}

/**
 * Atomically writes the store to disk.
 */
function persistStore(targets: ThermalTarget[]) {
  try {
    if (!fs.existsSync(DB_DIR)) {
      fs.mkdirSync(DB_DIR, { recursive: true });
    }
    const tempFile = `${DB_FILE}.tmp`;
    fs.writeFileSync(tempFile, JSON.stringify(targets, null, 2), 'utf-8');
    fs.renameSync(tempFile, DB_FILE);
  } catch (err) {
    console.error('[DB] Error persisting store to disk:', err);
  }
}

/**
 * Retrieves all thermal anomalies stored in DB.
 */
export async function getAllAnomaliesFromDB(): Promise<ThermalTarget[]> {
  if (!inMemoryStore) {
    initDatabase();
  }
  return inMemoryStore || [];
}

/**
 * Upserts a single or batch of thermal anomaly records into DB.
 */
export async function upsertAnomaliesToDB(newAnomalies: ThermalTarget[]): Promise<number> {
  if (!inMemoryStore) {
    initDatabase();
  }

  const existingMap = new Map<string, ThermalTarget>();
  
  // Index existing targets
  (inMemoryStore || []).forEach(item => existingMap.set(item.id, item));

  let upsertCount = 0;
  for (const anomaly of newAnomalies) {
    existingMap.set(anomaly.id, anomaly);
    upsertCount++;
  }

  inMemoryStore = Array.from(existingMap.values());
  persistStore(inMemoryStore);

  return upsertCount;
}

/**
 * Query anomaly by ID.
 */
export async function getAnomalyByIdFromDB(id: string): Promise<ThermalTarget | null> {
  const anomalies = await getAllAnomaliesFromDB();
  return anomalies.find(a => a.id === id) || null;
}
