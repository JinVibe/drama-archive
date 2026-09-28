-- Where a drama's OST rows came from when they were not in the publishing source record.
--   NULL           not enriched (or OST came with the source record)
--   'kowiki'       tracks parsed from the Korean Wikipedia article's OST section
--   'kowiki:none'  article checked, no parsable OST section — skip on later runs
ALTER TABLE drama ADD COLUMN ost_source VARCHAR(30);
