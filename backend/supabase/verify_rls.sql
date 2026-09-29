-- ==============================================================================
-- VajraNowcast — RLS Verification & Security Audit Script
-- ==============================================================================
-- Run this script in the Supabase SQL Editor to audit Row-Level Security policies.
-- Wrapped in BEGIN ... ROLLBACK to ensure zero test artifacts or mutations persist.
-- ==============================================================================

BEGIN;

DO $$
DECLARE
    pol_count INT;
    anon_insert_success BOOLEAN := FALSE;
    anon_alerts_count INT;
    anon_preds_count INT;
    anon_cache_count INT;
BEGIN
    RAISE NOTICE '================================================================';
    RAISE NOTICE '>>> VAJRANOWCAST RLS SECURITY AUDIT STARTING';
    RAISE NOTICE '================================================================';

    -- 1. Verify Active Policies Count
    SELECT COUNT(*) INTO pol_count
    FROM pg_policies
    WHERE schemaname = 'public' AND tablename IN ('alerts', 'predictions', 'weather_cache');

    IF pol_count >= 4 THEN
        RAISE NOTICE '[PASS] Policy Audit: Found % active RLS policies across protected tables.', pol_count;
    ELSE
        RAISE WARNING '[FAIL] Policy Audit: Expected at least 4 active policies, found %.', pol_count;
    END IF;

    -- 2. Verify anon SELECT on active alerts
    BEGIN
        SET LOCAL ROLE anon;
        SELECT COUNT(*) INTO anon_alerts_count FROM public.alerts WHERE is_active = true;
        RAISE NOTICE '[PASS] anon SELECT on public.alerts: Accessible (found % active alerts).', anon_alerts_count;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING '[FAIL] anon SELECT on public.alerts: Query failed unexpectedly with message: %', SQLERRM;
    END;

    -- 3. Verify anon INSERT on alerts is BLOCKED by RLS
    BEGIN
        SET LOCAL ROLE anon;
        INSERT INTO public.alerts (
            alert_id, city, alert_type, severity, thunderstorm_probability,
            lightning_probability, valid_until, lead_time_hours, message, is_active
        ) VALUES (
            'test-rls-probe-id', 'Delhi', 'thunderstorm', 'severe', 0.85,
            0.75, NOW() + INTERVAL '1 hour', 1.0, 'Test probe message', true
        );

        -- If no exception was thrown, the anon insert succeeded, which violates RLS!
        anon_insert_success := TRUE;
    EXCEPTION WHEN OTHERS THEN
        anon_insert_success := FALSE;
        RAISE NOTICE '[PASS] anon INSERT on public.alerts: Blocked by RLS as required (SQLSTATE %, %)', SQLSTATE, SQLERRM;
    END;

    IF anon_insert_success THEN
        RAISE WARNING '[FAIL] Security Breach: anon role was able to INSERT directly into public.alerts!';
    END IF;

    -- 4. Verify anon SELECT on public.predictions (Must be denied / 0 rows)
    BEGIN
        SET LOCAL ROLE anon;
        SELECT COUNT(*) INTO anon_preds_count FROM public.predictions;
        IF anon_preds_count = 0 THEN
            RAISE NOTICE '[PASS] anon access to public.predictions: Restricted (0 rows returned to anon).';
        ELSE
            RAISE WARNING '[FAIL] anon access to public.predictions: Leaked % rows to anon role!', anon_preds_count;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE '[PASS] anon SELECT on public.predictions: Blocked by RLS with message: %', SQLERRM;
    END;

    -- 5. Verify anon SELECT on public.weather_cache (Must be denied / 0 rows)
    BEGIN
        SET LOCAL ROLE anon;
        SELECT COUNT(*) INTO anon_cache_count FROM public.weather_cache;
        IF anon_cache_count = 0 THEN
            RAISE NOTICE '[PASS] anon access to public.weather_cache: Restricted (0 rows returned to anon).';
        ELSE
            RAISE WARNING '[FAIL] anon access to public.weather_cache: Leaked % rows to anon role!', anon_cache_count;
        END IF;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE '[PASS] anon SELECT on public.weather_cache: Blocked by RLS with message: %', SQLERRM;
    END;

    RAISE NOTICE '================================================================';
    RAISE NOTICE '>>> VAJRANOWCAST RLS SECURITY AUDIT COMPLETE — ROLLING BACK TRANSACTION';
    RAISE NOTICE '================================================================';
END $$;

-- Guarantee that all test operations are rolled back completely
ROLLBACK;
