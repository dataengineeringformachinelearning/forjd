-- =============================================================================
-- Platform status isolation — reserve platform-status; block product bleed
-- =============================================================================
-- Apply after 029. Absolute boundary: slug ``platform-status`` is immutable and
-- may only exist with metadata.kind = 'platform'. Customer tenants cannot claim
-- or mutate this sentinel via API or ad-hoc SQL without ops break-glass.
-- =============================================================================

-- --- Protect platform-status mutations ---
CREATE OR REPLACE FUNCTION public.status_pages_protect_platform_slug()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.slug = 'platform-status' THEN
      RAISE EXCEPTION 'platform-status is immutable'
        USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN OLD;
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.slug = 'platform-status' THEN
    RAISE EXCEPTION 'platform-status is immutable'
      USING ERRCODE = 'restrict_violation';
  END IF;

  IF NEW.slug = 'platform-status' THEN
    IF COALESCE(NEW.metadata->>'kind', '') IS DISTINCT FROM 'platform' THEN
      RAISE EXCEPTION 'platform-status requires metadata.kind=platform'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS status_pages_protect_platform_slug ON public.status_pages;
CREATE TRIGGER status_pages_protect_platform_slug
  BEFORE INSERT OR UPDATE OR DELETE ON public.status_pages
  FOR EACH ROW
  EXECUTE FUNCTION public.status_pages_protect_platform_slug();

-- Tag an existing platform-status row so the trigger accepts re-apply / ops reads.
UPDATE public.status_pages
SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('kind', 'platform')
WHERE slug = 'platform-status'
  AND COALESCE(metadata->>'kind', '') IS DISTINCT FROM 'platform';
