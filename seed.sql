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

-- description = display-only copy for the WebView detail sheet (ADR-014, backend-owned).
-- photos left empty for now — UI renders a placeholder; fill with real URLs once
-- campus photos exist.
INSERT INTO pois (name, category, building, floor, status, is_popular, synonyms, description) VALUES
    ('Perpustakaan',   'Umum',        'Gedung A', 'Lantai 1', 'Buka',  true,  ARRAY['perpus', 'library'],
        'Perpustakaan kampus dengan koleksi buku teknik, ruang baca, dan area belajar bersama.'),
    ('BAAK',           'Administrasi', 'Gedung A', 'Lantai 1', 'Buka',  true,  ARRAY['administrasi', 'akademik'],
        'Biro Administrasi Akademik dan Kemahasiswaan — layanan surat, legalisir, transkrip, dan urusan akademik mahasiswa.'),
    ('Mushola',        'Umum',        'Gedung A', 'Lantai 1', 'Buka',  true,  ARRAY['musholla', 'masjid', 'sholat'],
        'Tempat ibadah dengan area wudhu. Tersedia perlengkapan sholat.'),
    ('Lab 102',        'Laboratorium', 'Gedung A', 'Lantai 1', 'Buka',  false, ARRAY['laboratorium 102'],
        'Laboratorium komputer lantai 1 untuk kegiatan praktikum.'),
    ('Lab 103',        'Laboratorium', 'Gedung A', 'Lantai 1', 'Buka',  false, ARRAY['laboratorium 103'],
        'Laboratorium komputer lantai 1 untuk kegiatan praktikum.'),
    ('Ruang Dosen',    'Administrasi', 'Gedung A', 'Lantai 1', 'Buka',  false, ARRAY['dosen'],
        'Ruang kerja dosen — tempat menemui dosen pembimbing atau konsultasi akademik.'),
    ('MMB Studio',     'Laboratorium', 'Gedung A', 'Lantai 1', 'Buka',  false, ARRAY['studio', 'multimedia'],
        'Studio multimedia broadcasting untuk produksi audio-video dan praktikum media.'),
    ('Lab Teori 201',  'Laboratorium', 'Gedung A', 'Lantai 2', 'Buka',  false, ARRAY['lab teori 201', 'kelas 201'],
        'Ruang kelas teori di lantai 2 untuk perkuliahan reguler.'),
    ('Lab Teori 202',  'Laboratorium', 'Gedung A', 'Lantai 2', 'Antre', false, ARRAY['lab teori 202', 'kelas 202'],
        'Ruang kelas teori di lantai 2 untuk perkuliahan reguler.'),
    ('Lab Teori 203',  'Laboratorium', 'Gedung A', 'Lantai 2', 'Buka',  false, ARRAY['lab teori 203', 'kelas 203'],
        'Ruang kelas teori di lantai 2 untuk perkuliahan reguler.'),
    ('Lab Mikrotik',   'Laboratorium', 'Gedung A', 'Lantai 2', 'Penuh', true,  ARRAY['mikrotik', 'jaringan', 'network'],
        'Laboratorium jaringan dengan perangkat MikroTik untuk praktikum jaringan komputer.')
ON CONFLICT (name) DO NOTHING;
