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

## Provenance and verification status

The current files were **drafted from general knowledge to exercise the pipeline and the
retrieval evaluation**. They are not yet verified against official broadcaster pages.
Before any public launch every file must be checked (dates, episode counts, cast/character
names, OST credits) and the `links` filled with official pages; the `manual` source has
trust_level 50 for exactly this reason. Intentional test cases inside the data:

- `김원석` appears twice on purpose: `kim-won-seok` (director, 시그널) and `kim-won-seok-writer`
  (writer, 태양의 후예) — a homonym that must stay two persons.
- People shared across dramas reuse one `external_id` (김고은, 서강준, 조진웅, 이동휘, 고경표,
  박보검, 이성경, 김은숙, 이응복) so re-ingests resolve deterministically.

Rules:

- `external_id` on persons/songs is optional but strongly recommended: it makes
  re-ingests match deterministically instead of by name.
- Only official links (broadcaster / OTT / official OST). Leave `links` empty
  rather than guessing a URL.
- One file per drama. File name = `external_id`.json.

## OST

2026-09-28부터 OST는 `ost_enrich_kowiki` DAG가 한국어 위키백과에서 채운다. 이 seed 파일들의 손으로 적은 OST 초안은 그 소스로 대체됐다(발행 시 kowiki 트랙과 제목이 같으면 같은 곡으로 병합).
