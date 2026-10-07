// Where the data lives. The REST URL is Supabase's (https://REF.supabase.co/rest/v1) in production
// and a local PostgREST (http://localhost:3000) in development. The anon key is PUBLIC by design:
// the database's row-level security, not this key, is what keeps it read-only.
export const config = {
  restUrl: (import.meta.env.VITE_REST_URL ?? "http://localhost:3000").replace(/\/$/, ""),
  anonKey: import.meta.env.VITE_ANON_KEY ?? "",
  // Optional FastAPI service for the live photo demo. Without it, that panel explains itself.
  apiUrl: (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, ""),
};
