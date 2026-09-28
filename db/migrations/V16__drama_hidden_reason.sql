-- Why a drama is HIDDEN, so the publish DAG can lift the right ones later:
--   'not_a_drama' / 'foreign'  discovery excluded it (lifted when it returns to the manifest)
--   'upcoming'                 start_date is in the future (lifted the day it airs)
--   NULL                       hidden by hand (never lifted automatically)
ALTER TABLE drama ADD COLUMN hidden_reason VARCHAR(40);
