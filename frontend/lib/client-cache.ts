import type { AppUser, WaybillFilters, WaybillItem } from "./types";

const CACHE_PREFIX = "epix.session-cache.v1.";
const ACCOUNT_KEY = `${CACHE_PREFIX}account`;
const WAYBILL_PREFIX = `${CACHE_PREFIX}waybills.`;
const USER_PREFIX = `${CACHE_PREFIX}users.`;
const CACHE_VERSION = 1;

export const WAYBILL_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

type CacheEnvelope<T> = {
  version: number;
  ownerId: string;
  storedAt: number;
  data: T;
};

export type CacheSnapshot<T> = {
  data: T;
  storedAt: number;
};

function getStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function readEnvelope<T>(key: string): CacheEnvelope<T> | null {
  const storage = getStorage();
  if (!storage) return null;
  try {
    const parsed = JSON.parse(storage.getItem(key) || "null") as CacheEnvelope<T> | null;
    if (
      !parsed ||
      parsed.version !== CACHE_VERSION ||
      typeof parsed.ownerId !== "string" ||
      typeof parsed.storedAt !== "number" ||
      !("data" in parsed)
    ) {
      storage.removeItem(key);
      return null;
    }
    return parsed;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

function writeEnvelope<T>(key: string, ownerId: string, data: T, storedAt = Date.now()) {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.setItem(
      key,
      JSON.stringify({ version: CACHE_VERSION, ownerId, storedAt, data })
    );
  } catch {
    // Cache writes must never block normal API behavior.
  }
}

function normalizeFilters(filters?: WaybillFilters) {
  return {
    userId: filters?.userId || "",
    status: filters?.status || "",
    q: filters?.q?.trim().toLocaleLowerCase() || ""
  };
}

function waybillKey(user: AppUser, filters?: WaybillFilters) {
  const scope = encodeURIComponent(JSON.stringify(normalizeFilters(filters)));
  return `${WAYBILL_PREFIX}${user.id}.${user.role}.${scope}`;
}

export function clearClientCache() {
  const storage = getStorage();
  if (!storage) return;
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(CACHE_PREFIX)) keys.push(key);
  }
  keys.forEach((key) => storage.removeItem(key));
}

export function readAccountCache(): CacheSnapshot<AppUser> | null {
  const envelope = readEnvelope<AppUser>(ACCOUNT_KEY);
  if (!envelope?.data?.id || !envelope.data.email || !envelope.data.role) return null;
  return { data: envelope.data, storedAt: envelope.storedAt };
}

export function writeAccountCache(user: AppUser) {
  const existing = readAccountCache();
  if (
    existing &&
    (existing.data.id !== user.id || existing.data.role !== user.role)
  ) {
    clearClientCache();
  }
  writeEnvelope(ACCOUNT_KEY, user.id, user);
}

export function readUsersCache(ownerId: string): CacheSnapshot<AppUser[]> | null {
  const envelope = readEnvelope<AppUser[]>(`${USER_PREFIX}${ownerId}`);
  if (!envelope || envelope.ownerId !== ownerId || !Array.isArray(envelope.data)) return null;
  return { data: envelope.data, storedAt: envelope.storedAt };
}

export function writeUsersCache(ownerId: string, users: AppUser[]) {
  writeEnvelope(`${USER_PREFIX}${ownerId}`, ownerId, users);
}

export function readWaybillCache(
  user: AppUser,
  filters?: WaybillFilters
): CacheSnapshot<WaybillItem[]> | null {
  const envelope = readEnvelope<WaybillItem[]>(waybillKey(user, filters));
  if (!envelope || envelope.ownerId !== user.id || !Array.isArray(envelope.data)) return null;
  return { data: envelope.data, storedAt: envelope.storedAt };
}

export function writeWaybillCache(
  user: AppUser,
  filters: WaybillFilters | undefined,
  waybills: WaybillItem[],
  storedAt = Date.now()
) {
  writeEnvelope(waybillKey(user, filters), user.id, waybills, storedAt);
}

export function isCacheFresh(snapshot: CacheSnapshot<unknown>, now = Date.now()) {
  return now - snapshot.storedAt < WAYBILL_REFRESH_INTERVAL_MS;
}

export function updateWaybillInCache(updated: WaybillItem) {
  const storage = getStorage();
  if (!storage) return;
  const unfilteredScope = encodeURIComponent(JSON.stringify(normalizeFilters()));
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(WAYBILL_PREFIX)) keys.push(key);
  }
  keys.forEach((key) => {
    if (!key.endsWith(unfilteredScope)) {
      storage.removeItem(key);
      return;
    }
    const envelope = readEnvelope<WaybillItem[]>(key);
    if (!envelope || !Array.isArray(envelope.data)) return;
    const next = envelope.data.map((item) => (item.id === updated.id ? updated : item));
    if (next.some((item, index) => item !== envelope.data[index])) {
      writeEnvelope(key, envelope.ownerId, next, envelope.storedAt);
    }
  });
}

export function invalidateWaybillCaches() {
  const storage = getStorage();
  if (!storage) return;
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(WAYBILL_PREFIX)) keys.push(key);
  }
  keys.forEach((key) => storage.removeItem(key));
}
