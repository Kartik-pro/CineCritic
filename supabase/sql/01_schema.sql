-- CineCritic: search history + user preferences, with Row Level Security.
-- Run in: Supabase dashboard -> SQL Editor -> New query -> paste all -> Run.
-- Safe to re-run: tables/indexes use IF NOT EXISTS, policies/triggers are dropped and recreated.
-- NOTE: IF NOT EXISTS will NOT change a table that already exists with a different shape.
--       If you created these tables by hand earlier, run 02_verify.sql and send me the output.

-- ---------------------------------------------------------------------------
-- Shared helper: keep updated_at current on UPDATE
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- search_history
-- search_type: 'title' = typed search, 'pick' = a film chosen from suggestions or a card,
--              'mood'  = a free-text "Describe a mood" search.
-- user_id defaults to the signed-in user, so the app never needs to send it, and the
-- policies below reject any row whose user_id is not the caller.
-- ---------------------------------------------------------------------------
create table if not exists public.search_history (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null default auth.uid() references auth.users (id) on delete cascade,
  query            text not null check (char_length(query) between 1 and 300),
  normalized_query text not null check (char_length(normalized_query) between 1 and 300),
  search_type      text not null check (search_type in ('title', 'pick', 'mood')),
  movie_id         integer check (movie_id is null or movie_id > 0),
  movie_title      text check (movie_title is null or char_length(movie_title) <= 200),
  genres           text[] not null default '{}' check (cardinality(genres) <= 10),
  created_at       timestamptz not null default now()
);

create index if not exists search_history_user_created_idx
  on public.search_history (user_id, created_at desc);
create index if not exists search_history_user_normalized_idx
  on public.search_history (user_id, normalized_query);
create index if not exists search_history_user_movie_idx
  on public.search_history (user_id, movie_id) where movie_id is not null;

-- Safety cap so one account cannot grow the table without limit: keep the newest 500 rows per user.
create or replace function public.trim_search_history()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  delete from public.search_history
  where user_id = new.user_id
    and id in (
      select id from public.search_history
      where user_id = new.user_id
      order by created_at desc, id desc
      offset 500
    );
  return null;
end;
$$;

drop trigger if exists search_history_trim on public.search_history;
create trigger search_history_trim
  after insert on public.search_history
  for each row execute function public.trim_search_history();

alter table public.search_history enable row level security;

-- Least privilege: signed-out visitors get nothing; signed-in users can read, add and delete
-- (but never edit) their own rows.
revoke all on table public.search_history from public, anon, authenticated;
grant select, insert, delete on table public.search_history to authenticated;

drop policy if exists "search_history_select_own" on public.search_history;
create policy "search_history_select_own" on public.search_history
  for select to authenticated
  using (user_id = (select auth.uid()));

drop policy if exists "search_history_insert_own" on public.search_history;
create policy "search_history_insert_own" on public.search_history
  for insert to authenticated
  with check (user_id = (select auth.uid()));

drop policy if exists "search_history_delete_own" on public.search_history;
create policy "search_history_delete_own" on public.search_history
  for delete to authenticated
  using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- user_preferences (one row per user)
-- No API keys or other secrets belong here.
-- ---------------------------------------------------------------------------
create table if not exists public.user_preferences (
  user_id                 uuid primary key default auth.uid() references auth.users (id) on delete cascade,
  preferred_genres        text[] not null default '{}' check (cardinality(preferred_genres) <= 10),
  preferred_language      text check (preferred_language is null or char_length(preferred_language) <= 40),
  personalization_enabled boolean not null default true,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

drop trigger if exists user_preferences_set_updated_at on public.user_preferences;
create trigger user_preferences_set_updated_at
  before update on public.user_preferences
  for each row execute function public.set_updated_at();

alter table public.user_preferences enable row level security;

revoke all on table public.user_preferences from public, anon, authenticated;
grant select, insert, update, delete on table public.user_preferences to authenticated;

drop policy if exists "user_preferences_select_own" on public.user_preferences;
create policy "user_preferences_select_own" on public.user_preferences
  for select to authenticated
  using (user_id = (select auth.uid()));

drop policy if exists "user_preferences_insert_own" on public.user_preferences;
create policy "user_preferences_insert_own" on public.user_preferences
  for insert to authenticated
  with check (user_id = (select auth.uid()));

drop policy if exists "user_preferences_update_own" on public.user_preferences;
create policy "user_preferences_update_own" on public.user_preferences
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

drop policy if exists "user_preferences_delete_own" on public.user_preferences;
create policy "user_preferences_delete_own" on public.user_preferences
  for delete to authenticated
  using (user_id = (select auth.uid()));
