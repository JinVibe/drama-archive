-- Where drama.broadcaster_id came from when the source record had none.
--   NULL              set by the publishing source record (or never set)
--   'kowiki:category' inferred from the Korean Wikipedia article's categories
--                     ("SBS 금토드라마", "tvN 수목드라마", ...) by synopsis_enrich_kowiki
--   'kowiki:none'     checked, no usable category — skip on later runs
ALTER TABLE drama ADD COLUMN broadcaster_source VARCHAR(30);
