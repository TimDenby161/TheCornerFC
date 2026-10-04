-- Additive and repeatable. NOT APPLIED YET.
-- Accounts (README: Accounts): a signed-in visitor can delete their own account from the site's
-- account box. Supabase's API has no call for that with the public key, so this function does it,
-- for the caller only: auth.uid() comes from their sign-in token and is null for anyone else, so
-- nothing is deleted. Removing the auth.users row removes their sign-in identities and sessions
-- with it. When applied, append this file to db/schema.sql as the other migrations are.
CREATE OR REPLACE FUNCTION delete_my_account() RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
    DELETE FROM auth.users WHERE id = (SELECT auth.uid());
$$;

REVOKE ALL ON FUNCTION delete_my_account() FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON FUNCTION delete_my_account() FROM anon;
    END IF;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        GRANT EXECUTE ON FUNCTION delete_my_account() TO authenticated;
    END IF;
END; $$;

-- Check afterwards (expect one row: authenticated):
--   select grantee from information_schema.routine_privileges
--    where routine_schema='public' and routine_name='delete_my_account' and grantee in ('anon','authenticated','PUBLIC');
