-- DARSI — setup Supabase (migrasi dari FastAPI/Railway ke PostgREST + RLS + RPC).
-- Jalankan SEKALI di Supabase SQL Editor pada project baru. Idempoten (aman diulang).
-- Menggantikan seluruh darsi-backend/app (FastAPI pensiun) — tak ada server yang di-host.
--
-- Urutan penting: tabel → kategori(owner) → FK → RLS → fungsi RPC.

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. TABEL (dari schema.sql; tanpa fitur proprietary — tetap portable ADR-001/014)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists pois (
    id          bigint generated always as identity primary key,
    unity_id    text not null unique,                 -- SATU kunci identitas: POIData.poiId (GUID)
    name        text not null,                        -- atribut tampilan, sengaja TIDAK unik (ADR-021)
    category    text not null,
    building    text,                                 -- owned by Unity/POIData (ADR-014)
    floor       text,                                 -- owned by Unity/POIData (ADR-014)
    status      text not null default 'Buka'
                    check (status in ('Buka','Antre','Penuh')),  -- owned by backend (ADR-014)
    is_popular  boolean not null default false,
    synonyms    text[] not null default '{}',
    description text not null default '',
    photos      text[] not null default '{}',
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table if not exists presence (
    user_id     text primary key,     -- client-trusted (ADR-017), belum ada identitas terverifikasi
    invisible   boolean not null default false,
    updated_at  timestamptz not null default now()
);

create index if not exists idx_pois_category   on pois (category);
create index if not exists idx_pois_name_lower on pois (lower(name));

-- updated_at auto-refresh saat UPDATE
create or replace function set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end;
$$ language plpgsql;
drop trigger if exists trg_pois_updated_at on pois;
create trigger trg_pois_updated_at before update on pois
    for each row execute function set_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. KATEGORI = SATU PEMILIK (ADR-021). Dulu frozenset diduplikasi di backend+WebView.
--    Kini DB pemiliknya; pois.category FK ke sini → kategori invalid ditolak di boundary
--    untuk SEMUA penulis (termasuk sync). Gantikan validasi manual di app.
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists poi_categories (name text primary key);
insert into poi_categories (name) values
    ('IGD'),('Poliklinik'),('Farmasi'),('Laboratorium'),('Radiologi'),
    ('Rawat Inap'),('Kamar Operasi'),('ICU'),('Ruang Bersalin'),('Fisioterapi'),
    ('Pendaftaran'),('Kasir'),('Informasi'),('BPJS'),('Rekam Medis'),
    ('Musholla'),('Toilet'),('Kantin'),('ATM'),('Parkir'),('Ruang Tunggu'),
    ('Lift'),('Tangga'),('Pintu Masuk'),
    ('Umum'),('Administrasi')
on conflict (name) do nothing;

-- FK pois.category → poi_categories(name). DB baru = tak ada baris, aman dipasang.
do $$ begin
    alter table pois add constraint pois_category_fk
        foreign key (category) references poi_categories(name);
exception when duplicate_object then null; end $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. RLS — anon key aman di bundle KARENA ini.
-- ─────────────────────────────────────────────────────────────────────────────
alter table pois            enable row level security;
alter table presence        enable row level security;
alter table poi_categories  enable row level security;

-- pois & kategori: baca publik. Tulis pois HANYA via sync_pois() (service_role bypass RLS).
drop policy if exists "pois public read" on pois;
create policy "pois public read" on pois for select to anon using (true);

drop policy if exists "categories public read" on poi_categories;
create policy "categories public read" on poi_categories for select to anon using (true);

-- presence: anon boleh baca + upsert. CATATAN: user_id client-trusted (ADR-017) — sama
-- terbukanya dgn API lama, BUKAN regresi. Perketat saat MyRSIy terbitkan token verifiable.
drop policy if exists "presence read"   on presence;
drop policy if exists "presence insert" on presence;
drop policy if exists "presence update" on presence;
create policy "presence read"   on presence for select to anon using (true);
create policy "presence insert" on presence for insert to anon with check (true);
create policy "presence update" on presence for update to anon using (true) with check (true);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. RPC search_pois — satu-satunya baca yang tak bisa PostgREST murni:
--    substring ILIKE pada elemen array `synonyms`. Bentuk balikan = kontrak ApiPoi
--    (unity_id AS id) agar WebView tak berubah. popular/categories cukup PostgREST langsung.
-- ─────────────────────────────────────────────────────────────────────────────
create or replace function search_pois(q text default '', category text default '')
returns table (
    id text, name text, category text, building text, floor text,
    status text, is_popular boolean, description text, photos text[]
)
language sql stable security invoker set search_path = public
as $$
    select p.unity_id as id, p.name, p.category, p.building, p.floor,
           p.status, p.is_popular, p.description, p.photos
    from pois p
    where (search_pois.q = '' or p.name ilike '%'||search_pois.q||'%'
           or exists (select 1 from unnest(p.synonyms) s where s ilike '%'||search_pois.q||'%'))
      and (search_pois.category = '' or search_pois.category = 'Semua'
           or p.category = search_pois.category)
    order by p.name;
$$;
grant execute on function search_pois(text, text) to anon;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. RPC sync_pois — pengganti POST /api/poi/sync (Unity Editor push).
--    Dipanggil dgn service_role key (Editor-only). All-or-nothing: kategori tak dikenal
--    → FK violation → seluruh transaksi batal (fail-loud, sejalan perilaku lama).
--    Cocok HANYA lewat unity_id; `name` sengaja tak unik (ADR-021).
-- ─────────────────────────────────────────────────────────────────────────────
create or replace function sync_pois(payload jsonb)
returns jsonb
language plpgsql security invoker set search_path = public
as $$
declare
    rec jsonb;
    existing bigint;
    created int := 0;
    updated int := 0;
begin
    for rec in select * from jsonb_array_elements(payload)
    loop
        select id into existing from pois where unity_id = rec->>'id';
        if existing is null then
            insert into pois (unity_id, name, category, building, floor, synonyms)
            values (rec->>'id', rec->>'name', rec->>'category',
                    coalesce(rec->>'building',''), coalesce(rec->>'floor',''),
                    array(select jsonb_array_elements_text(rec->'synonyms')));
            created := created + 1;
        else
            update pois set
                unity_id = rec->>'id', name = rec->>'name', category = rec->>'category',
                building = coalesce(rec->>'building',''), floor = coalesce(rec->>'floor',''),
                synonyms = array(select jsonb_array_elements_text(rec->'synonyms'))
            where id = existing;
            updated := updated + 1;
        end if;
    end loop;
    return jsonb_build_object('synced', created+updated, 'created', created, 'updated', updated);
end;
$$;
-- Browser TAK boleh panggil ini. Hanya service_role (bypass RLS, dipakai Unity Editor).
revoke all on function sync_pois(jsonb) from public, anon;
