-- ==============================================================================
-- VajraNowcast — Alert Tiers & Test/Drill Mode Migration
-- ==============================================================================

-- 1. Add nullable tier column ('watch', 'advisory', 'warning')
ALTER TABLE IF EXISTS public.alerts 
    ADD COLUMN IF NOT EXISTS tier text;

-- 2. Add is_test boolean flag (default false)
ALTER TABLE IF EXISTS public.alerts 
    ADD COLUMN IF NOT EXISTS is_test boolean DEFAULT false;

-- 3. Create index on tier and is_test for efficient filtering
CREATE INDEX IF NOT EXISTS idx_alerts_tier 
    ON public.alerts (tier) 
    WHERE (is_active = true);

CREATE INDEX IF NOT EXISTS idx_alerts_is_test 
    ON public.alerts (is_test) 
    WHERE (is_active = true);
