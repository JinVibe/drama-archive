# Curated seed data — `dramamemory.drama.v1`

Hand-written drama records that go through the **same** pipeline as scraped data
(raw snapshot → normalize → entity resolution → quality gate → gold). Nothing is
inserted into the canonical DB by hand.

Locally these files are served by the `seed` compose service (nginx) and ingested
through the `local_seed` source. The same files can be ingested via the `manual`
source from any https URL (e.g. raw.githubusercontent.com).

## Format

```jsonc
{
  "format": "dramamemory.drama.v1",
  "external_id": "tvn-2016-goblin",          // stable id within this source
  "title_ko": "도깨비",
  "title_en": "Guardian: The Lonely and Great God",
  "aliases": ["쓸쓸하고 찬란하神 도깨비", "Goblin"],
  "broadcaster": "tvN",                       // matched to broadcaster.code after normalization
  "start_date": "2016.12.02",                 // 2016-12-02 / 2016년 12월 2일 also accepted
  "end_date": "2017.01.21",
  "episode_count": 16,
  "runtime_minutes": 80,
  "genres": ["fantasy", "romance"],           // genre.code values
  "synopsis": "...",
  "credits": [
    {
      "person": {"external_id": "gong-yoo", "name_ko": "공유", "name_en": "Gong Yoo", "birth_date": "1979-07-10"},
      "type": "ACTOR",                         // ACTOR / DIRECTOR / WRITER / PRODUCER
      "character": "김신",
      "billing_order": 1,
      "main": true
    }
  ],
  "ost": [
    {"external_id": "goblin-ost-1", "title": "Stay With Me", "artists": ["찬열", "펀치"], "part_no": 1, "release_date": "2016-12-03"}
  ],
  "links": [
    {"provider": "tvn", "url": "https://...", "type": "BROADCASTER_PAGE"}   // official pages only
  ]
}
```

Rules:

- `external_id` on persons/songs is optional but strongly recommended: it makes
  re-ingests match deterministically instead of by name.
- Only official links (broadcaster / OTT / official OST). Leave `links` empty
  rather than guessing a URL.
- One file per drama. File name = `external_id`.json.
