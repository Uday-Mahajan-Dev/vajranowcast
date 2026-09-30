-- ==============================================================================
-- VajraNowcast — Database Security & Row Level Security (RLS) Migration
-- ==============================================================================

-- 1. Drop all existing policies on core application tables
DO $$
DECLARE
    pol RECORD;
BEGIN
    FOR pol IN 
        SELECT schemaname, tablename, policyname 
        FROM pg_policies 
        WHERE tablename IN ('alerts', 'predictions', 'weather_cache')
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I.%I', pol.policyname, pol.schemaname, pol.tablename);
    END LOOP;
END $$;

-- 2. Enable Row Level Security
ALTER TABLE IF EXISTS public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.weather_cache ENABLE ROW LEVEL SECURITY;

-- 3. Cleanup existing duplicate active alerts before creating unique partial index:
-- For each (city, alert_type) with multiple active alerts, keep the newest by created_at and deactivate the rest.
WITH ranked_active_alerts AS (
    SELECT alert_id,
           ROW_NUMBER() OVER (
               PARTITION BY city, alert_type 
               ORDER BY created_at DESC
           ) as rn
    FROM public.alerts
    WHERE is_active = true
)
UPDATE public.alerts
SET is_active = false
WHERE alert_id IN (
    SELECT alert_id FROM ranked_active_alerts WHERE rn > 1
);

-- 4. Unique Partial Index on Alerts to guarantee single active alert per city/type under concurrency
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_active_city_type
    ON public.alerts (city, alert_type)
    WHERE (is_active = true);

-- 5. Public Read Policies
-- NOTE FOR FRONTEND INTEGRATION:
-- - 'public.alerts': Granted to anon & authenticated so the frontend map and mobile alert banners
--   can stream/subscribe to active alerts in real-time without user login.
-- - Since the RLS policy only allows SELECT where is_active = true, when an alert is deactivated
--   (is_active updated to false), Supabase Realtime will NOT emit an UPDATE payload to anon listeners.
-- - CONTRACT FOR FRONTEND:
--   1. The alert banner must filter out expired alerts client-side where valid_until < now().
--   2. The frontend must periodically refetch GET /api/v1/alerts/active every 5 minutes as a fallback.
-- - 'public.predictions' & 'public.weather_cache': Backend-only (service_role). Frontend queries
--   predictions via FastAPI endpoints (/nowcast), so direct PostgREST access to raw tables is disallowed.

CREATE POLICY "Public read access for active alerts"
    ON public.alerts
    FOR SELECT
    TO anon, authenticated
    USING (is_active = true);

-- 6. Service Role Management Policies (Full access strictly for backend services)
CREATE POLICY "Service role full access on alerts"
    ON public.alerts
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role full access on predictions"
    ON public.predictions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role full access on weather_cache"
    ON public.weather_cache
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
