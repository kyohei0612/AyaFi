// Persistent settings (profile / NG flags / spice) that must survive across
// dev ↔ installed builds and across version updates.
//
// Previously we used `localStorage`, but that's keyed by webview origin:
//   dev        → http://localhost:5173
//   installed  → tauri://localhost  (different origin → different storage)
// so aya lost her profile every time a new installer ran. We now mirror the
// settings into a JSON file under `%APPDATA%\<app-id>\settings.dat` via
// `@tauri-apps/plugin-store`, which is shared regardless of webview origin.
//
// localStorage is kept as a synchronous warm-cache for React's initial
// render. On mount, we async-load from the store and upgrade local state
// with whatever the store returns (plus migrate values that exist only in
// localStorage up into the store).

import { LazyStore } from "@tauri-apps/plugin-store";

const STORE_FILE = "settings.dat";

// A single shared handle is fine — plugin-store dedupes concurrent access.
const store = new LazyStore(STORE_FILE);

export async function storeGet<T>(key: string): Promise<T | undefined> {
  try {
    return await store.get<T>(key);
  } catch {
    return undefined;
  }
}

export async function storeSet<T>(key: string, value: T): Promise<void> {
  try {
    await store.set(key, value);
    await store.save();
  } catch {
    // Store unavailable (dev without plugin / permission) — fail silent.
    // The localStorage mirror still holds the value for the current session.
  }
}
