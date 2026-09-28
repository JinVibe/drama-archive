-- Catalog dump for generate_golden.py: one JSON array of published dramas.
--   docker compose exec -T postgres psql -U dramamemory -d dramamemory -tA -f evals/retrieval/dump_catalog.sql > dump.json
SELECT json_agg(row_to_json(t)) FROM (
  SELECT d.slug,
         d.title_ko AS title,
         d.title_en,
         EXTRACT(YEAR FROM d.start_date)::int AS year,
         b.code AS broadcaster,
         COALESCE((SELECT array_agg(a.alias) FROM drama_alias a WHERE a.drama_id = d.id), '{}') AS aliases,
         COALESCE((SELECT array_agg(g.code) FROM drama_genre dg JOIN genre g ON g.id = dg.genre_id WHERE dg.drama_id = d.id), '{}') AS genres,
         COALESCE((SELECT json_agg(json_build_object('name', p.name_ko, 'type', c.credit_type, 'character', c.character_name))
                     FROM credit c JOIN person p ON p.id = c.person_id
                    WHERE c.drama_id = d.id AND p.status = 'PUBLISHED'), '[]') AS credits
    FROM drama d LEFT JOIN broadcaster b ON b.id = d.broadcaster_id
   WHERE d.status = 'PUBLISHED'
   ORDER BY d.id
) t;
