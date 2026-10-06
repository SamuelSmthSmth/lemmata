-- Sync: each student's work, settings and history, one row per record.
--
-- The app's sync (ui/static/js/sync.js) pushes records
-- {store, key, data, modified, deleted} and pulls whatever changed after a
-- cursor.  This table keeps, per (student, store, key), the record with the
-- newest `modified`; `sync_push` decides that atomically, so two devices
-- cannot race, and returns the records it refused because a newer edit was
-- already here.  `seq` numbers every accepted write in order, per student,
-- so a pull from a cursor sees each change once.
--
-- Students read only their own rows (RLS), and write only through
-- `sync_push`.  Deleting the account deletes the rows (on delete cascade).

create sequence if not exists public.sync_seq;

create table if not exists public.sync_records (
  user_id    uuid    not null references auth.users (id) on delete cascade,
  store      text    not null check (store in ('files', 'snapshots', 'meta', 'packs', 'prefs')),
  key        text    not null check (char_length(key) between 1 and 512),
  data       jsonb,
  modified   bigint  not null,
  deleted    boolean not null default false,
  seq        bigint  not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, store, key)
);

create index if not exists sync_records_user_seq on public.sync_records (user_id, seq);

alter table public.sync_records enable row level security;

drop policy if exists "Students read their own records" on public.sync_records;
create policy "Students read their own records"
  on public.sync_records for select
  to authenticated
  using ((select auth.uid()) = user_id);

revoke all on public.sync_records from anon, authenticated;
grant select on public.sync_records to authenticated;

-- Push a batch.  A record is kept when it is at least as new as what is
-- here; otherwise its "store:key" is returned in `rejected`, and the device
-- keeps it until a pull shows it the newer edit.
create or replace function public.sync_push(records jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  uid uuid := auth.uid();
  rec jsonb;
  is_deleted boolean;
  kept int;
  rejected text[] := '{}';
begin
  if uid is null then
    raise exception 'Sign in to sync.' using errcode = '28000';
  end if;
  if jsonb_typeof(records) is distinct from 'array' or jsonb_array_length(records) > 500 then
    raise exception 'A push is an array of at most 500 records.' using errcode = '22023';
  end if;
  -- One push at a time per student, so `seq` is handed out in commit order
  -- and a pull never steps past a write that has not committed yet.
  perform pg_advisory_xact_lock(hashtextextended(uid::text, 0));
  for rec in select value from jsonb_array_elements(records) loop
    is_deleted := coalesce((rec ->> 'deleted')::boolean, false);
    if not is_deleted and octet_length((rec -> 'data')::text) > 5 * 1024 * 1024 then
      raise exception 'A record is limited to 5 MB (%:%).', rec ->> 'store', rec ->> 'key' using errcode = '54000';
    end if;
    insert into public.sync_records as r (user_id, store, key, data, modified, deleted, seq)
    values (
      uid,
      rec ->> 'store',
      rec ->> 'key',
      case when is_deleted then null else rec -> 'data' end,
      (rec ->> 'modified')::bigint,
      is_deleted,
      nextval('public.sync_seq')
    )
    on conflict (user_id, store, key) do update
      set data = excluded.data,
          modified = excluded.modified,
          deleted = excluded.deleted,
          seq = excluded.seq,
          updated_at = now()
      where r.modified <= excluded.modified;
    get diagnostics kept = row_count;
    if kept = 0 then
      rejected := rejected || ((rec ->> 'store') || ':' || (rec ->> 'key'));
    end if;
  end loop;
  return jsonb_build_object('rejected', to_jsonb(rejected));
end;
$$;

-- Delete the signed-in student's account and, by cascade, everything synced.
create or replace function public.delete_my_account()
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if auth.uid() is null then
    raise exception 'Sign in to delete your account.' using errcode = '28000';
  end if;
  delete from auth.users where id = auth.uid();
end;
$$;

revoke all on function public.sync_push(jsonb) from public, anon;
revoke all on function public.delete_my_account() from public, anon;
grant execute on function public.sync_push(jsonb) to authenticated;
grant execute on function public.delete_my_account() to authenticated;

-- Live changes to the other devices (Realtime applies the select policy).
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (
       select 1 from pg_publication_tables
       where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'sync_records'
     ) then
    alter publication supabase_realtime add table public.sync_records;
  end if;
end;
$$;
