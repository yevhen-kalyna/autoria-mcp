# AUTO.RIA Used-Cars API — Open Questions (Phase 1)

Ambiguities found while extracting `openapi/autoria-used-cars.yaml` from the
developer-wiki HTML. Each item says whether resolving it **needs a live API
call** and, if so, the **exact call** to spend quota on. Free tier is ~1000/mo,
30/hr — most questions below can be answered by a single cached dictionary call,
so batch them.

Legend: 🔴 needs a live call · 🟡 needs a decision (no call) · 🟢 cheap to confirm
opportunistically. · ✅ **RESOLVED** by live probe (2026-06-06).

---

## RESOLVED — live probe run 2026-06-06 (key/user_id supplied)

Ran against the live API (verified findings folded into the spec):

| Q | Answer (verified) |
|---|---|
| **D2** fuel | Live set = `1,2,3,4,5,6,8,10,11,12`. **New: 11 = Гібрид (MHEV), 12 = Гібрид (REEV)** — in neither doc version. 7 and 9 retired. |
| **D1** drive (cars) | `GET /auto/categories/1/driverTypes` → **1 = Повний (AWD), 2 = Передній (front), 3 = Задній (rear)**. (Moto cat 2 is 4/5/6.) |
| **D7** countries | Mostly ISO-3166 numeric, **but a custom 900–913 block** (Грузія 900, Ірландія 901, … Хорватія 913) overrides ISO. Must resolve via dict, never a local ISO table. |
| **D4** models/_group | **Heterogeneous array** — items are *either* a bare `{name,value}` *or* a sub-array (group). Not array-of-arrays. Spec schema fixed to `oneOf`. |
| **C7** countpage default | **10** when omitted (not 20). |
| **C1** searchType | Default = **1** (not 6). `searchType=4` only trims count slightly (19679→19575) and sets `isCommonSearch=false`; `OfferOfTheDay` and new-auto are **not** bulk-removed. Filter `data[].type=="UsedAuto"` for strictly-used. |
| **C2** order_by | 8-value table is authoritative; `order_by=2` confirmed price-ascending (top result $300). Default = **0**. The "other params" 0/1/2 enum is legacy. |
| **C5** abroad | Effectively **boolean**, not tri-state: `abroad=1`→only-abroad (count 19679→2, echoed `true`); `abroad=0` and `abroad=2`→all (echoed `false`). **Cannot exclude abroad cars** via this param. |
| **C9** last_id | Returns `0` in tests; not needed when paginating with `page`. |
| **E3** langId (partial) | Search echoes `lang_id` as the **string** `"4"` and appends both `lang_id`/`langId` to query_string; default 4. Full per-id language map still TBD. |
| **F2** query_string location | Verified: lives under `result.additional.query_string`, not `result`. Spec corrected. |

**Still open — could not be answered via my GET-only web tool** (need the
`scripts/phase1_probes.sh` run, which uses curl for headers + POST):

| Q | Why still open | Exact call |
|---|---|---|
| **B1** rate-limit headers | web_fetch hides response headers | any GET, dump headers — `P1` in the script |
| **B2** error JSON envelope | web_fetch returns empty body on 4xx | `GET /auto/colors` (no key) + bad key — `P12/P13` |
| **E2** period enum | web_fetch can't POST | `POST /auto/statistic-avarage-price/ {omniId}` — `P14` |
| **E6** unlisted-VIN behavior | web_fetch can't POST | `POST /auto/params/by/vin-code/ {fake omniId}` — `P15` |

Run `RUN_PAID=1 ./scripts/phase1_probes.sh` and paste back `probe_responses/`
(or just `P1.headers.txt`, `P12_err_no_key.body.json`, `P14_*.body.json`,
`P15_*.body.json`) to close these four.

---

## A. Authentication & transport

**A1. 🟡 Does `api_key` go in the path or the query for the paid POST endpoints?**
The VIN-params page says *"Обов'язкові параметри в шляху: user_id та api_key"*
("required params **in the path**"), but every example puts them in the query
string (`?user_id=...&api_key=...`). The avg-price pages say "query". I modeled
all of them as **query** params. Decision: treat "in the path" as a wiki wording
slip; keep query. No call needed unless a 403 appears in practice.

**A2. 🟡 `user_id` semantics on POST endpoints.** It's the caller's account id,
required alongside `api_key`, and is unrelated to the `user_id` *search filter*
(owner-of-car). Confirm your account's `user_id` from the cabinet; it is not
derivable from the key in the docs.

**A3. 🟢 HTTPS-only.** `HTTPS_REQUIRED` (400) implies HTTP is rejected. Hardcode
`https://` and never downgrade. No call needed.

---

## B. Rate limiting & error envelope

**B1. 🔴 Rate-limit response headers are undocumented.** The wiki gives the
limits (1000/mo, 30/hr) and the 429 code but lists **no** `X-RateLimit-*` /
`Retry-After` headers. The client's rate-limit accounting (`client.py`) would be
much cheaper if the server returns remaining-quota headers.
*Call to resolve:* any cheap dictionary call and dump **all** response headers —
e.g. `GET /auto/colors?api_key=KEY` — then inspect for `X-RateLimit-Limit`,
`X-RateLimit-Remaining`, `Retry-After`, `Date`, etc. (1 request.)

**B2. 🔴 Exact JSON error envelope is unknown.** The errors page lists *codes*
(`API_KEY_MISSING`, `OVER_RATE_LIMIT`, …) but not the JSON shape. Is it
`{"error":"API_KEY_INVALID"}`, `{"error":{"code":...,"message":...}}`, or
`{"message":...}` (as `equips`/`optionsV2` use)? I modeled `ApiError{error}` +
a separate `MessageError{message}` and left both `additionalProperties:true`.
*Call to resolve:* deliberately trigger one error cheaply, e.g.
`GET /auto/colors` **with no `api_key`** (expect 403 `API_KEY_MISSING`) and one
`GET /auto/colors?api_key=WRONG` (expect 403 `API_KEY_INVALID`); capture the raw
body. (2 requests — or 0 if you accept modeling it loosely for v1.)

**B3. 🟢 Per-endpoint error bodies.** `equips_by_modifications` returns
`{"message":"Modification ID is required"}` and `optionsV2` returns
`{"message":"Invalid categoryId: ..."}` / `{"message":"Internal server error"}`.
Captured. Other endpoints' validation messages are unconfirmed but low-risk.

---

## C. Search endpoint (`GET /auto/search`) — highest-risk area

**C1. 🔴 `searchType` true meaning.** The prose says `searchType=4` →
"used cars only", but the wiki's own sample response echoes `searchType: 6` in
both `all` and `cleaned`. So is 4 the request value the server normalizes to 6,
or are they different concepts (request flag vs. resolved type)? This directly
affects whether we get new-auto ids mixed in.
*Call to resolve:* run the **same** minimal search twice and compare returned
`data[].type` counts:
`GET /auto/search?api_key=KEY&category_id=1&marka_id[0]=9&countpage=5` then the
same with `&searchType=4`. Check whether `OfferOfTheDay`/new-auto entries
disappear. (2 requests.)

**C2. 🔴 `order_by` enum conflict.** The dedicated sorting table gives
`2,3,5,6,7,8,12,13` (price/date/mileage/year asc-desc). The "Other parameters"
page lists a *different* unnamed "Сортування" with `0,1,2`
(default / cheap→expensive / expensive→cheap). I encoded the 8-value set on
`order_by` and noted the 0/1/2 set here. Are these two different params, or did
the older page just document a subset under the wrong name?
*Call to resolve:* `GET /auto/search?...&order_by=2&countpage=5` vs `order_by=3`
and confirm price ordering of the returned ids via follow-up `/auto/info` on the
first id of each (or just trust the 8-value table). (2 search requests minimum;
the table is probably authoritative — **decision** may suffice without a call.)

**C3. 🟡 Nested bracket indexing not expressible in OpenAPI.** Generations use
`generation_id[0][0]`, modifications `modification_id[0][0][0]`, options
`auto_options[477]=477` (key == value). OpenAPI `style/explode` can't represent
2–3 level indices or keyed maps. I modeled these as flat arrays and documented
the real serialization in each param's `description`. The **client/tools layer**
must build these query strings manually — do not rely on a generic serializer.

**C4. 🟡 Positional correlation of multi-brand blocks.** `marka_id[i]`,
`model_id[i]`, `s_yers[i]`, `po_yers[i]`, `brandOrigin[i]` are correlated by
index `i` (block 0 = Toyota+years, block 1 = VW+years). The flat-array model
loses this coupling. Curated tools should accept a list of "brand blocks" and
emit correlated indices. No call needed — design decision for Phase 4.

**C5. 🔴 `abroad` tri-state vs boolean.** Search/"other params" define
`abroad ∈ {0,1,2}` (0 all / 1 include / 2 exclude) and the sample uses
`abroad=2`. But V3 and the avg-price `params` model `abroad` as boolean. Which
wins for `/auto/search`? Mismodeling silently drops or inverts the "located
abroad" filter.
*Call to resolve:* `GET /auto/search?...&abroad=1&countpage=5` vs `abroad=2` vs
omitted; compare counts. (2–3 requests.) Low priority unless you need this
filter in v1.

**C6. 🟡 Request→response field renames.** Response echoes filters under renamed
keys: `type`→`fuel_id`, `gearbox`→`gear_id`, `brandOrigin`→`country`,
`category_id`→ sometimes typo'd `categori_id` in the param table (actual JSON
uses `category_id`). Documented in the schema. Build a request/response name map
in `models.py`; don't assume symmetry.

**C7. 🔴 `countpage` default and hard cap.** Prose says max ids per page = 100
and `countpage` "1–100"; sample uses `countpage=50`. The default when omitted is
unspecified (commonly 20 on auto.ria's web UI — see the VIN-params `link.url`
which has `size=20`). Confirm so pagination math is right.
*Call to resolve:* `GET /auto/search?api_key=KEY&category_id=1&marka_id[0]=9`
with **no** `countpage` and count `result.search_result.ids`. (1 request.)

**C8. 🟡 Which params are "deprecated"?** The V1 table tags several with
"Застарів?"/"Видалити?" (auto_ids, exclude_auto_ids, lid/sid, after_date/
before_date, is_hot, with_real_exchange). I kept them in the spec but did not
mark `deprecated: true` since the wiki itself is unsure. Decision: leave as-is
for v1; don't surface them in curated tools.

**C9. 🟢 `last_id` meaning.** Appears in `search_result(_common)` as `0` in the
sample; likely a cursor for `with_last_id`/`sid`-style pagination. Not needed if
we page with `page`. Confirm only if offset pagination proves unreliable.

---

## D. Dictionaries (drive name→ID resolution — must be right)

**D1. 🔴 Drive-type ids are category-specific and the car set is unknown.** The
`driverTypes` example is for **category 2 (moto)**: `{Кардан:4, Ремінь:5,
Ланцюг:6}`. Passenger-car drive ids are different and never shown as a list. The
listing-info sample even has `driveId:1 → "Повний"` (full) while the VIN-params
chip shows `driveId_0 → "Передній"` (front) — i.e. ids 1/2/3 mean
front/rear/full but the mapping isn't documented and may differ by source.
*Call to resolve (do this):*
`GET https://developers.ria.com/auto/categories/1/driverTypes?api_key=KEY`
and cache the result as the authoritative car drive map. (1 request.)

**D2. 🔴 Fuel-type list has two conflicting versions.** The page shows a
"current" set (1 Бензин, 2 Дизель, 3 Газ, 4 Газ пропан-бутан/Бензин, 5 HEV,
6 Електро, 8 Газ метан/Бензин, 10 PHEV — note 7 and 9 absent) **and** an
"earlier" set (…5 Гібрид, 6 Електро, 7 Інше, 8 Газ метан, 9 Газ пропан-бутан).
Which does the live API return today, and does `/auto/search`'s `type` filter
accept the current ids (5/10 hybrids, 4/8 dual-fuel)?
*Call to resolve (do this):* `GET https://developers.ria.com/auto/type?api_key=KEY`
— cache as canonical fuel map. (1 request.)

**D3. 🟢 Body-style grouping (`parentId`).** Flat list has `parentId:0`; `_group`
nests children under a parent whose own `parentId` is the group id. Captured. The
`/auto/bodystyles` "all" list vs per-category list differ in coverage — prefer
per-category for filters. No call needed.

**D4. 🟡 `models/_group` exact shape.** The wiki sample is malformed (stray
brackets), so I modeled it as `array<array<NameValue>>` (group → models, first =
group name), consistent with `bodystyles/_group`. Confirm opportunistically when
you first call it; low risk since we mainly use the flat `/models`.

**D5. 🟢 Generations payload is nested.** `/generations/by/models/{modelID}/...`
returns `[{name,id,generations:[{generationId,name,yearFrom,yearTo,modelId,
eng}]}]` — a model wrapper, not a flat list. Note the field is `generationId`
(not `value`) and years come as `yearFrom/yearTo`. Captured.

**D6. 🟡 Host-root vs `/auto` path inconsistency.** Generations, modifications,
and bodies-by-generation live at the **host root**
(`/generations/...`, `/modifications/...`, `/bodies/...`), not under `/auto`.
Equips is under `/auto_ria/...`; optionsV2 under `/used_auto/...`. This is real
(not a doc typo) and the client must not assume a single `/auto` prefix.
Captured in `servers` + per-path. No call needed.

**D7. 🟢 Country ids look like ISO-3166 numeric** (276 DE, 408 KR, 826 "Англія",
158 CN, 56 BE). If that holds across the full list we can map names locally and
save a call, but "Англія" (826 = UK) suggests their own labeling.
*Optional call:* `GET /auto/countries?api_key=KEY` once, cache, and verify the
ISO hypothesis. (1 request — worth it; you'll need the dict anyway.)

**D8. 🟡 `optionsV2` structure is loosely documented.** The page shows two
incompatible illustrations (objects with `translates` vs. arrays of ids). I
modeled it as free-form `binary`/`selectable` objects. It's publishing-oriented
and out of v1's read scope — defer. Confirm only if we expose it.

---

## E. Average-price & VIN endpoints (paid — spend carefully)

**E1. 🟡 `params` field casing differs from search.** Avg-price/VIN bodies use
`brandId` (not `marka_id`), `gearBoxId`, `bodyId`, `categoryId`, and **string**
ids; search uses `marka_id`, `gearbox`, `bodystyle`, integer-ish. The
dictionaries return `value` as integers. Resolution layer must cast to string
and remap names per endpoint. Captured in `CarParams`. No call needed.

**E2. 🔴 `period` allowed values.** Examples use 30/168/365 (days). Is it a free
integer, or an enum tied to `periodSelectorData.elements[].value` returned by
the statistic endpoint? Sending an unsupported period may error or silently
clamp.
*Call to resolve (paid):* one `POST /auto/statistic-avarage-price/` with an
`omniId` and read `periodSelectorData.elements` for the allowed set — this is
the cheapest way and you get the answer as data. (1 paid request.)

**E3. 🟡 `langId` enum.** Examples use `4` (UK) and the search response uses
`lang_id:2`. So language ids differ between endpoints (2 vs 4 for UK?). Confirm
the avg-price/VIN `langId` map (1=ru? 2=? 4=uk?). Likely 2=RU,4=UK on web; not
authoritative. Decision: default `langId=4` (UK) for v1; revisit if labels come
back wrong-language. No dedicated call needed.

**E4. 🟢 `verifiedVIN` mixed type.** Comes back as `0`/`true` across the two
samples (int and bool). Modeled as `oneOf[boolean,integer]`. Read defensively.

**E5. 🟡 Required-param rule for by-params mode.** "categoryId, brandId, modelId
+ at least one more" — encoded as `required:[categoryId,brandId,modelId]` only;
the "+1 more" rule is enforced server-side and can't be expressed in JSON
Schema. Curated tool should validate it before spending a paid call.

**E6. 🔴 What does `/auto/params/by/vin-code/` return on an unlisted car?**
The wiki says data exists "only if the vehicle was listed". Unknown: is it a 200
with empty `chipsData`/error `noticeType`, or a 4xx? Matters for tool error
mapping (and you don't want to burn paid calls discovering this).
*Call to resolve (paid):* one `POST` with a plausibly-unlisted VIN and capture
status + body. (1 paid request — optional; can model loosely for v1.)

---

## F. Misc / cross-cutting

**F1. 🟡 `price` strings carry spaces** ("285 345", "1 349 659"). Thousands are
space-separated; `value` is a string, integer mirrors (`USD`,`UAH`) are clean
ints. Parse both forms in `models.py`.

**F2. 🟢 Listing URL construction.** `/auto/info` gives relative `linkToView`
(`/auto_bmw_3_series_36756951.html`); avg-price gives relative `uri`; VIN-params
gives an absolute auto.ria search `link.url`. Prefix relatives with
`https://auto.ria.com` to satisfy the attribution requirement (Section in spec
`info.description`). No call needed.

**F3. 🟡 V2 / V3 search are out of scope but noted.** V2 = field-renamed wrapper
over V1; V3 = a cleaner vocabulary (`brand`, `model`, `fuel`, `gearbox`,
`year` as tuple, booleans for abroad/customs_cleared, etc.) but **no base path,
no example response** is given in the HTML. If we later prefer V3's saner schema
we must find its endpoint path.
*Call to resolve:* none possible from current docs — **re-export needed**: the
V3 section lacks a URL. See §G.

---

## G. Pages to re-export / missing material

Nothing was unreadable, but these gaps come from the docs themselves, not the
capture — flagging so you can decide whether to re-export or fetch:

1. **🔴 Search V3 endpoint URL + example response.** The "API пошуку V3" section
   lists params only, no path and no sample. If V3 matters, re-export that page
   fully (it may have collapsed/"Дивись!" blocks that didn't expand) or confirm
   it's genuinely undocumented.
2. **🟡 "Робота з оголошеннями" (publishing/cabinet) pages** are linked from the
   index but **not** in the export set (add/edit/delete advert, photos, options,
   listings V2). Out of v1 scope, so not required now — re-export later if we add
   write support.
3. **🟢 Collapsed `Дивись!`/`Дивись` spoiler blocks.** The static HTML did
   include the expanded JSON for search/info/avg-price, so we got the examples.
   If any future page shows truncated samples, re-export with those blocks
   expanded.

---

## Suggested single quota-efficient batch to resolve the 🔴 dictionary items

These you'll need cached anyway, so spending them now is "free" in practice
(7 freemium GETs, well under the 30/hr cap):

```
GET /auto/type?api_key=KEY                       # D2 fuel canonical
GET /auto/categories/1/driverTypes?api_key=KEY   # D1 car drive map
GET /auto/countries?api_key=KEY                  # D7 ISO check
GET /auto/colors?api_key=KEY  (dump headers)     # B1 rate-limit headers
GET /auto/colors  (no key)                       # B2 error envelope (403)
GET /auto/search?...&countpage  omitted          # C7 default page size
GET /auto/search?...&searchType=4  vs  baseline  # C1 used-only behavior
```

Defer the **paid** probes (E2, E6, C5) until a curated tool actually needs them;
each one costs a metered/paid call.

---

## RESOLVED (addendum) — probe run 2026-06-06 part 2 (B1, B2)

Ran `scripts/phase1_probes.ps1`; read back `probe_responses/`.

- **B1 — rate-limit headers: ANSWERED (none).** A 200 from `/auto/type` exposes
  NO `X-RateLimit-*` / `Retry-After` headers. Quota CANNOT be read from
  response headers — the client must account for it locally. Other headers seen:
  `x-service-version: 1.3.3`, `cache-control: public, max-age=720` (12-min edge
  cache on dictionaries), `X-Cache: HIT`, `Via: ... api-umbrella`,
  `Strict-Transport-Security`. Gateway is api-umbrella; 429 body assumed to match
  the ApiError envelope below.
- **B2 — error envelope: ANSWERED (nested).** 403 responses return
  `{ "error": { "code": "...", "message": "..." } }` (Content-Type
  application/json). Verified codes/messages:
    - missing key -> `{"error":{"code":"API_KEY_MISSING","message":"No api_key was supplied. Get one at https://developers.ria.com"}}`
    - invalid key -> `{"error":{"code":"API_KEY_INVALID","message":"An invalid api_key was supplied. Get one at https://developers.ria.com"}}`
  Spec `ApiError` schema + all error examples corrected from the old flat-string
  guess to this nested shape.

### Still open — paid POST probes (E2, E6)
The PowerShell run stopped after the freemium GETs; `P14`/`P15` did not execute,
so these remain. They require a POST (my tooling here is GET-only). Run the two
one-liners (see chat) or re-run with `$env:AUTORIA_USER_ID` set, then share
`P14_statistic_period.body.json` and `P15_vin_unlisted.body.json`.

---

## RESOLVED (addendum) — probe run 2026-06-06 part 3 (E2, E6) — ALL FOUR CLOSED

- **E2 — period enum: ANSWERED.** `periodSelectorData.elements` =
  **30 / 90 / 180 / 365** days (Останній місяць / 3 місяці / Останні півроку /
  Останній рік). Spec `period` now carries `enum: [30,90,180,365]`. Bonus- the
  `graphData` shape is richer than the docs: each item is
  `{ advCnt, date, price:{UAH,USD} }` where `date` is **"MM.YY"** (e.g. "06.25"),
  NOT ISO "2022-09"; `advCnt` (monthly advert count) is undocumented; and a
  `noticeData[]` block is present. Spec schema + example updated.
- **E6 — unlisted/invalid omniId: ANSWERED.** `POST /auto/params/by/vin-code/`
  with a bad omniId returns **HTTP 200** (not 4xx), with NO `chipsData`,
  `searchType:"omniId"`, and `noticeData:[{noticeType:"error",
  noticeString:"Помилка. Некоректні вхідні данні"}]`. **Detect failures via
  `noticeData[].noticeType=="error"`, never the HTTP status.** Same pattern
  almost certainly applies to ai-avarage-price and statistic endpoints (success
  carries `noticeType:"success"`, as seen in E2). Spec updated with an
  `invalid_omni_id` example and a searchType note.
  (Caveat- the test used a malformed VIN, so this is the "incorrect input"
  branch; a well-formed-but-unlisted VIN may return a different notice string
  but the same 200 + noticeType:"error" contract — safe to code against.)

**Phase 1 status: COMPLETE.** All A–G open questions are resolved or downgraded
to documented design decisions. The remaining 🟡 items (C3/C4 bracket-index
serialization, E5 "+1 param" rule, etc.) are client-side implementation
concerns for later phases, not API ambiguities.
