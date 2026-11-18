-- Zaod cloud backend: the hosted side of accounts, Studio projects and the store.
--
-- Run this once in a Supabase project (SQL editor). Everything personal is fenced
-- by row level security on auth.uid(), so a token can only ever touch its own rows;
-- the store catalogue is readable and every write to it needs the service role.
--
-- The desktop keeps working without any of this: the machine's own zaod-hub holds
-- the same data locally, and this database is where it is backed up and shared.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- accounts --
create table if not exists public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  username     text not null unique check (username ~ '^[a-z0-9][a-z0-9._-]{2,31}$'),
  display_name text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- A profile appears the moment someone signs up, without a second round trip.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
declare wanted text;
begin
  wanted := coalesce(
    nullif(new.raw_user_meta_data ->> 'username', ''),
    split_part(coalesce(new.email, 'person'), '@', 1) || '-' || substr(new.id::text, 1, 6)
  );
  insert into public.profiles (id, username, display_name)
  values (new.id, lower(wanted), new.raw_user_meta_data ->> 'display_name')
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- -------------------------------------------------------- studio projects --
create table if not exists public.studio_projects (
  id         uuid primary key default gen_random_uuid(),
  owner      uuid not null references auth.users (id) on delete cascade,
  local_id   text not null,                    -- the id the desktop hub uses
  name       text not null default 'Untitled project',
  document   jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique (owner, local_id)
);
create index if not exists studio_projects_owner_idx on public.studio_projects (owner, updated_at desc);

-- ------------------------------------------------------ installed records --
create table if not exists public.install_records (
  owner        uuid not null references auth.users (id) on delete cascade,
  app_id       text not null,
  installed_at timestamptz not null default now(),
  primary key (owner, app_id)
);

-- ------------------------------------------------------------- the store --
create table if not exists public.developer_accounts (
  email                 text primary key,
  display_name          text,
  status                text not null default 'pending'
                        check (status in ('pending', 'approved', 'suspended')),
  tier                  text not null default 'free' check (tier in ('free', 'pro', 'company')),
  max_apps              integer not null default 3 check (max_apps >= 0),
  max_size_mb           integer not null default 64 check (max_size_mb > 0),
  max_downloads_per_day integer not null default 1000 check (max_downloads_per_day >= 0),
  signing_key_id        text,
  joined_date           date not null default current_date,
  suspended_reason      text,
  notes                 text
);

create table if not exists public.store_apps (
  app_id           text primary key,
  name             text not null,
  developer_email  text not null references public.developer_accounts (email),
  version          text not null,
  channel          text not null default 'stable' check (channel in ('stable', 'beta', 'nightly')),
  status           text not null default 'draft'
                   check (status in ('draft', 'in_review', 'published', 'rejected', 'suspended')),
  categories       text[] not null default '{}',
  permissions      text[] not null default '{}',
  size_mb          integer not null default 0,
  sha256           text,
  icon_url         text,
  description      text,
  downloads        bigint not null default 0,
  signature_verified boolean not null default false,
  submitted_date   timestamptz,
  reviewed_by      text,
  review_notes     text,
  updated_at       timestamptz not null default now()
);
create index if not exists store_apps_published_idx on public.store_apps (status, channel);

create table if not exists public.limit_policies (
  id                      uuid primary key default gen_random_uuid(),
  name                    text not null,
  scope                   text not null default 'global' check (scope in ('global', 'tier', 'developer')),
  tier                    text,
  developer_email         text,
  max_apps                integer,
  max_size_mb             integer,
  max_downloads_per_day   integer,
  max_api_calls_per_day   integer,
  max_builds_per_day      integer,
  is_active               boolean not null default true,
  notes                   text,
  created_at              timestamptz not null default now()
);

create table if not exists public.review_events (
  id              uuid primary key default gen_random_uuid(),
  app_id          text not null references public.store_apps (app_id) on delete cascade,
  developer_email text not null,
  action          text not null check (action in ('approve', 'reject', 'suspend', 'resubmit', 'update')),
  reason          text,
  actor           text not null,
  previous_status text,
  new_status      text,
  created_at      timestamptz not null default now()
);
create index if not exists review_events_app_idx on public.review_events (app_id, created_at desc);

-- ------------------------------------------------------------------ rules --
alter table public.profiles          enable row level security;
alter table public.studio_projects   enable row level security;
alter table public.install_records   enable row level security;
alter table public.developer_accounts enable row level security;
alter table public.store_apps        enable row level security;
alter table public.limit_policies    enable row level security;
alter table public.review_events     enable row level security;

drop policy if exists profiles_own on public.profiles;
create policy profiles_own on public.profiles
  for all using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists projects_own on public.studio_projects;
create policy projects_own on public.studio_projects
  for all using (auth.uid() = owner) with check (auth.uid() = owner);

drop policy if exists installs_own on public.install_records;
create policy installs_own on public.install_records
  for all using (auth.uid() = owner) with check (auth.uid() = owner);

-- Anyone may read what the store publishes; only the service role writes it.
drop policy if exists store_apps_read on public.store_apps;
create policy store_apps_read on public.store_apps
  for select using (status = 'published');

drop policy if exists store_apps_write on public.store_apps;
create policy store_apps_write on public.store_apps
  for all to service_role using (true) with check (true);

-- A developer sees their own account and applications, and nothing else.
drop policy if exists developer_accounts_own on public.developer_accounts;
create policy developer_accounts_own on public.developer_accounts
  for select using (lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));

drop policy if exists developer_accounts_admin on public.developer_accounts;
create policy developer_accounts_admin on public.developer_accounts
  for all to service_role using (true) with check (true);

drop policy if exists store_apps_developer on public.store_apps;
create policy store_apps_developer on public.store_apps
  for select using (lower(developer_email) = lower(coalesce(auth.jwt() ->> 'email', '')));

drop policy if exists limit_policies_read on public.limit_policies;
create policy limit_policies_read on public.limit_policies
  for select to authenticated using (is_active);

drop policy if exists limit_policies_admin on public.limit_policies;
create policy limit_policies_admin on public.limit_policies
  for all to service_role using (true) with check (true);

drop policy if exists review_events_read on public.review_events;
create policy review_events_read on public.review_events
  for select using (lower(developer_email) = lower(coalesce(auth.jwt() ->> 'email', '')));

drop policy if exists review_events_admin on public.review_events;
create policy review_events_admin on public.review_events
  for all to service_role using (true) with check (true);

-- Keep updated_at honest without the client having to remember.
create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$ begin new.updated_at := now(); return new; end; $$;

drop trigger if exists profiles_touch on public.profiles;
create trigger profiles_touch before update on public.profiles
  for each row execute function public.touch_updated_at();

drop trigger if exists projects_touch on public.studio_projects;
create trigger projects_touch before update on public.studio_projects
  for each row execute function public.touch_updated_at();

drop trigger if exists store_apps_touch on public.store_apps;
create trigger store_apps_touch before update on public.store_apps
  for each row execute function public.touch_updated_at();
