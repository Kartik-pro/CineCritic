-- CineCritic: structure check. Run AFTER 01_schema.sql.
-- Expected: every row shows ok = true.

select 'table search_history exists' as check, to_regclass('public.search_history') is not null as ok
union all
select 'table user_preferences exists', to_regclass('public.user_preferences') is not null
union all
select 'RLS enabled on search_history',
       coalesce((select relrowsecurity from pg_class where oid = to_regclass('public.search_history')), false)
union all
select 'RLS enabled on user_preferences',
       coalesce((select relrowsecurity from pg_class where oid = to_regclass('public.user_preferences')), false)
union all
select 'search_history has 3 policies (select, insert, delete)',
       (select count(*) from pg_policies where schemaname = 'public' and tablename = 'search_history') = 3
union all
select 'user_preferences has 4 policies (select, insert, update, delete)',
       (select count(*) from pg_policies where schemaname = 'public' and tablename = 'user_preferences') = 4
union all
select 'every policy is limited to signed-in users (no anon/public policies)',
       not exists (
         select 1 from pg_policies
         where schemaname = 'public'
           and tablename in ('search_history', 'user_preferences')
           and roles <> '{authenticated}'::name[]
       )
union all
select 'signed-out role (anon) has no table privileges',
       not exists (
         select 1 from information_schema.role_table_grants
         where table_schema = 'public'
           and table_name in ('search_history', 'user_preferences')
           and grantee in ('anon', 'PUBLIC')
       )
union all
select 'history rows cannot be edited (no UPDATE grant)',
       not exists (
         select 1 from information_schema.role_table_grants
         where table_schema = 'public' and table_name = 'search_history'
           and grantee = 'authenticated' and privilege_type = 'UPDATE'
       )
union all
select 'search_history has its 3 custom indexes',
       (select count(*) from pg_indexes
        where schemaname = 'public' and tablename = 'search_history'
          and indexname in ('search_history_user_created_idx', 'search_history_user_normalized_idx', 'search_history_user_movie_idx')) = 3
union all
select 'deleting an account cascades to its data (both tables)',
       (select count(*) from pg_constraint c
        where c.contype = 'f' and c.confdeltype = 'c'
          and c.confrelid = 'auth.users'::regclass
          and c.conrelid in (to_regclass('public.search_history'), to_regclass('public.user_preferences'))) = 2;

-- Optional, run separately (select this statement only): list every policy so you can read it yourself.
-- select tablename, policyname, cmd, roles, qual as using_clause, with_check
-- from pg_policies where schemaname = 'public' order by tablename, cmd;
