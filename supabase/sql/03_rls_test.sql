-- CineCritic: Row Level Security isolation test, run entirely inside the SQL Editor.
--
-- BEFORE RUNNING: replace the two placeholder UUIDs below with the IDs of two DIFFERENT real users
-- (dashboard -> Authentication -> Users -> click a user to see its User UID).
-- User IDs are identifiers, not secrets.
--
-- The script pretends to be each user in turn, tries both allowed and forbidden actions, and raises
-- an error naming the first thing that behaves wrongly. Everything is rolled back at the end,
-- so no test data is left behind.
-- Expected result: a single row saying PASSED. Any error message means a policy is wrong.

begin;

do $$
declare
  user_a constant uuid := '00000000-0000-0000-0000-00000000000a';  -- <-- replace with user A's UID
  user_b constant uuid := '00000000-0000-0000-0000-00000000000b';  -- <-- replace with user B's UID
  n integer;
begin
  if user_a = user_b then
    raise exception 'SETUP: user_a and user_b must be different users';
  end if;
  if not exists (select 1 from auth.users where id = user_a) or not exists (select 1 from auth.users where id = user_b) then
    raise exception 'SETUP: replace both placeholder UUIDs with real user IDs from Authentication -> Users';
  end if;

  -- ===== Act as user A =====
  perform set_config('request.jwt.claims', json_build_object('sub', user_a, 'role', 'authenticated')::text, true);
  set local role authenticated;

  insert into public.search_history (query, normalized_query, search_type) values ('rls test', 'rls test', 'title');
  insert into public.user_preferences (preferred_genres) values ('{Thriller}');

  select count(*) into n from public.search_history;
  if n < 1 then raise exception 'FAIL: user A cannot read their own history'; end if;

  begin
    insert into public.search_history (user_id, query, normalized_query, search_type) values (user_b, 'forged', 'forged', 'title');
    raise exception 'FAIL: user A was able to insert a history row for user B';
  exception when insufficient_privilege then null;
  end;

  begin
    insert into public.user_preferences (user_id) values (user_b);
    raise exception 'FAIL: user A was able to create preferences for user B';
  exception when insufficient_privilege then null;
  end;

  begin
    update public.search_history set query = 'edited';
    raise exception 'FAIL: history rows should not be editable';
  exception when insufficient_privilege then null;
  end;

  -- ===== Act as user B =====
  reset role;
  perform set_config('request.jwt.claims', json_build_object('sub', user_b, 'role', 'authenticated')::text, true);
  set local role authenticated;

  select count(*) into n from public.search_history where user_id = user_a;
  if n <> 0 then raise exception 'FAIL: user B can read user A''s history (% rows)', n; end if;

  select count(*) into n from public.user_preferences where user_id = user_a;
  if n <> 0 then raise exception 'FAIL: user B can read user A''s preferences'; end if;

  delete from public.search_history where user_id = user_a;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'FAIL: user B deleted % of user A''s history rows', n; end if;

  update public.user_preferences set personalization_enabled = false where user_id = user_a;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'FAIL: user B changed user A''s preferences'; end if;

  delete from public.user_preferences where user_id = user_a;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'FAIL: user B deleted user A''s preferences'; end if;

  -- ===== Act as a signed-out visitor =====
  reset role;
  perform set_config('request.jwt.claims', '', true);
  set local role anon;

  begin
    perform 1 from public.search_history limit 1;
    raise exception 'FAIL: signed-out visitors can read search_history';
  exception when insufficient_privilege then null;
  end;

  begin
    perform 1 from public.user_preferences limit 1;
    raise exception 'FAIL: signed-out visitors can read user_preferences';
  exception when insufficient_privilege then null;
  end;

  reset role;
end;
$$;

rollback;

select 'PASSED: accounts are isolated and signed-out visitors are blocked' as result;
