-- DARSI backend — seed 11 campus POIs (T3.4.2)
-- Names are EXACT copies of the Unity scene POI GameObject names
-- (Map Space/NavigationContent/POIs/...) so navigate resolves end-to-end:
-- WebView sends poiId=name -> POIManager.FindBestMatchWithContext exact-match.
--
-- building/floor/status are typed manually here as a BOOTSTRAP. Once the Unity
-- sync tool (T3.4-L2) exists, Unity becomes the source of truth for name/category/
-- building/floor per ADR-014 and this manual seed is superseded.
--
-- Floor guessed from room numbering (1xx = Lantai 1, 2xx = Lantai 2); adjust to
-- the real map when known. Single building for the demo map.

INSERT INTO pois (name, category, building, floor, status, is_popular, synonyms) VALUES
    ('Perpustakaan',   'Umum',        'Gedung A', 'Lantai 1', 'Buka',  true,  ARRAY['perpus', 'library']),
    ('BAAK',           'Administrasi', 'Gedung A', 'Lantai 1', 'Buka',  true,  ARRAY['administrasi', 'akademik']),
    ('Mushola',        'Umum',        'Gedung A', 'Lantai 1', 'Buka',  true,  ARRAY['musholla', 'masjid', 'sholat']),
    ('Lab 102',        'Laboratorium', 'Gedung A', 'Lantai 1', 'Buka',  false, ARRAY['laboratorium 102']),
    ('Lab 103',        'Laboratorium', 'Gedung A', 'Lantai 1', 'Buka',  false, ARRAY['laboratorium 103']),
    ('Ruang Dosen',    'Administrasi', 'Gedung A', 'Lantai 1', 'Buka',  false, ARRAY['dosen']),
    ('MMB Studio',     'Laboratorium', 'Gedung A', 'Lantai 1', 'Buka',  false, ARRAY['studio', 'multimedia']),
    ('Lab Teori 201',  'Laboratorium', 'Gedung A', 'Lantai 2', 'Buka',  false, ARRAY['lab teori 201', 'kelas 201']),
    ('Lab Teori 202',  'Laboratorium', 'Gedung A', 'Lantai 2', 'Antre', false, ARRAY['lab teori 202', 'kelas 202']),
    ('Lab Teori 203',  'Laboratorium', 'Gedung A', 'Lantai 2', 'Buka',  false, ARRAY['lab teori 203', 'kelas 203']),
    ('Lab Mikrotik',   'Laboratorium', 'Gedung A', 'Lantai 2', 'Penuh', true,  ARRAY['mikrotik', 'jaringan', 'network'])
ON CONFLICT (name) DO NOTHING;
