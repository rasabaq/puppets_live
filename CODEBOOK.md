# Codebook — UPF marketing audit, Phase 1

The definitions in this file are the source of truth for the labelled
variables — the binary ones (an ad sub-flag per `schema.AD_SUBVARIABLES`,
plus `has_food` and `is_upf`) and the descriptive ones (`food_category`,
`brands`, `foods`). The system prompts in `src/puppets/agents.py` (one
focused agent per variable) are *compiled artifacts* of this document: when a
prompt disagrees with it, the prompt is wrong and gets corrected here first,
then there.

The agent prompts cannot silently diverge on substance: `agents.py`
imports `HAS_FOOD_EXCLUSIONS` and `NOVA_CLASSIFICATION` from `schema.py`
rather than restating them, and a test pins that both flows compose the same
text. What differs between the two is call shape only — one combined call
per unit vs. up to six single-field calls — never the definitions below.

It is written to be usable by a human coder with no access to the code, because
the same definitions have to serve three audiences — the model, a second human
coder for reliability checks, and a reviewer reading the methods section.

---

## Unit of analysis

The unit is always one **bundle** of images, and its size — not the labelling
mode — is what decides the unit of analysis:

| Bundle size | Unit | An ad sub-flag means |
|---|---|---|
| 1 | One screenshot | The trigger is present **in this frame** |
| >1 | One video, given as consecutive sampled frames | The trigger is present in **any** frame of the video |

These are not interchangeable. A video whose 3rd of 5 sampled frames carries a
platform disclosure banner yields `ad_paid_promotion = 1` once when its 5
frames are one bundle, but `1, 1, 0, 0, 0` — or whatever the sampling caught —
when each frame is its own bundle of one. Any downstream proportion must
state which unit it is over, and the two must never be pooled.

The per-frame rule above is the default for a visual trigger like
`ad_paid_promotion`. A future sub-variable whose trigger lives in text rather
than frames (a metadata `#ad` hashtag, say) would be an honest exception to
it, the same way a text-based trigger always is: the property belongs to the
whole video, not to any one frame, so every sampled frame of such a video
would carry the same value under bundles of one even though no frame itself
shows anything. That is a deliberate crack in "judge only what is visible in
this frame" for a variable whose evidence is not, in fact, only what is
visible in the frame.

---

## Variables

## Advertising: a family of sub-variables

Advertising used to be one collapsed flag, `is_ad`, that answered "is this
unit advertising at all" by OR-ing together every trigger that could make
that true: a visible ad slot, a metadata disclosure, a spoken sponsor read.
That collapse cost information the audit actually wants — a video is
disclosed three different ways with three different reliabilities, and
pooling them into one bit erases which trigger fired.

Advertising is now decomposed into several **independent binary
sub-variables**, one per trigger, each scored on its own and each
independently reportable. There is no longer a stored `is_ad` column;
`brands` (below) is gated on **any** sub-variable being 1, computed at
analysis time, not on a variable that exists in the data.

There are now four sub-variables, registered in this order in
`schema.AD_SUBVARIABLES`: `ad_paid_promotion`, `ad_paid_advertising`,
`ad_brand_owned`, `ad_undisclosed`. Each was added the same way — one
sub-variable section here, one registry entry, no other code change — which
is the payoff of decomposing `is_ad` in the first place: a fifth sub-variable
would cost exactly the same, one section plus one entry.

Three of the four (`ad_paid_promotion`, `ad_brand_owned`, `ad_undisclosed`)
read frames plus title/description, and — where a transcript is present —
the transcript. `ad_paid_advertising` is the one exception: it is
**visual-only**, judged from frames alone, no metadata and no transcript.
See its own section for why.

**Audio status.** The transcript channel referenced above is currently
inert. `Config.audio_escalation` is disabled and raises if set, so no unit's
`transcript` is ever populated today — every spec that is written to consume
one is judging on frames and metadata alone until that channel is
re-enabled. This is stated in each affected section below rather than
implied.

### `ad_paid_promotion` — platform-distributed advertising

**1** — the unit **is** commercial content distributed through the
**platform's own advertising system**: the creator or an advertiser paid the
platform for distribution. This covers a boosted or promoted post, a
platform ad placement, and an in-feed "Sponsored" or "Promoted" slot —
anywhere the platform itself is the distribution mechanism, as opposed to a
disclosure rendered on top of organic content.

**0** — everything else, including ordinary organic content that merely
carries a disclosure (see `ad_paid_advertising`, which is the variable for a
platform-rendered disclosure banner on an otherwise organic post — a
different fact from this one).

Evidence: frames, plus title/description and transcript where present (see
"Audio status" above — transcript is not live today).

### `ad_paid_advertising` — the platform's own disclosure banner

This is the platform's own disclosure mechanism, and the definition is
narrow on purpose — it is the sharpest edge in this codebook, because the
two things it distinguishes look similar on screen and are not the same
fact.

**1** — the **platform's own rendered** paid-promotion disclosure banner is
visible in any frame of the unit:

- TikTok's "Paid partnership with X" banner;
- YouTube's "Includes paid promotion" label.

Both platforms set this **same** variable. It is not split into a
per-platform field: the fact being recorded is "the platform itself
disclosed a paid partnership here", and which platform did the disclosing is
not a second dimension this variable tracks.

**0** — everything else, including each of the following, which look like a
disclosure but are **not** this variable:

- a **creator-added** on-screen "PAID PARTNERSHIP" graphic that the creator
  made or overlaid themselves, rather than one the platform rendered;
- a **sponsor's own overlay or bug** placed in the video;
- a caption the creator **typed themselves** stating the video is sponsored;
- an `#ad` hashtag in the title or description — a creator-typed disclosure
  is not the platform's own banner; if it also carries a promo code or a
  bare call-to-action, it may still trigger `ad_undisclosed` on its own
  terms, but it does not set this variable;
- a spoken sponsor read in the audio.

None of the five above are judgement calls that land on 0 within this
variable's scope — they are outside its scope entirely. Coding one of them
as `ad_paid_advertising = 0` is correct; coding it as evidence *against*
advertising in general would be wrong, because the video may still be
disclosed sponsored content, just not through the channel this variable
measures.

**Worked example — the boundary most likely to be got wrong.** A creator
posts a video with a hand-drawn "SPONSORED" banner they added themselves in
their editing software, sitting in the corner of every frame. There is no
TikTok or YouTube-rendered disclosure label anywhere in the unit.
`ad_paid_advertising = 0`. The creator has disclosed a sponsorship — clearly,
prominently, in good faith — but not through the mechanism this variable
measures. The two are easy to conflate because they serve the same
real-world purpose (telling the viewer this is paid content) and often sit
in the same corner of the frame; the test is not "did the creator disclose"
but "did the **platform's own UI** render this specific banner".

**Frame-unit rule.** The banner visible in **any** frame of the bundle sets
this flag to 1 for the whole unit — the same rule `is_ad` used before this
decomposition, and the general per-frame rule stated under "Unit of
analysis" above.

**Evidence: visual only.** Unlike the other three sub-variables,
`ad_paid_advertising` is judged from **frames alone** — no title, no
description, no transcript. The thing this variable records is a banner the
platform renders directly on screen, so the frames show it or they don't;
metadata and speech have nothing to add to that question, and admitting them
would only invite the creator-typed and spoken-disclosure confusions the
worked example above warns against.

### `ad_brand_owned` — the posting account is the brand

**1** — the account posting the content **is** the advertised brand itself:
the posting account and the brand match. **0** — otherwise, including an
independent creator, reviewer, or fan account featuring the brand.

There is deliberately **no** channel/account metadata field feeding this
variable. It is an **inference from visible identity cues** — an on-screen
handle, a watermark, a logo bug, the account name as shown in frame — read
together with the description and, where present, the transcript, not a
lookup against a channel record.

Evidence: frames, title/description, and transcript where present (see
"Audio status" above — transcript is not live today).

### `ad_undisclosed` — undisclosed commercial intent

**1** when **any** of the following is present:

- a discount, affiliate, or promo code is shown in frame, or mentioned in
  the description or spoken;
- a direct call to action — "buy now", "link in my bio/description" — with
  **no** disclosure alongside it;
- a hashtag, @mention or tag that **both** names an actual commercial brand
  **and** functions to promote it;
- a platform shopping or product shelf attached to the unit — YouTube's
  "View products" panel.

**0** — none of the four triggers above fired.

**The tag trigger needs a brand *and* a promotion.** A hashtag, @mention or
tag fires this variable only when the thing it names is an actual commercial
brand and the reference works to promote that brand. Only a hashtag,
@mention or tag can fire it at all: a brand name written in ordinary prose
in the title or description is none of those things and cannot fire it —
which is what keeps `Philadelphia`, named in the prose title of a
`Queso philadelphia casero` recipe, at `0`.

A tag **promotes** a brand when it points the audience *at* that brand: the
brand's own account is @mentioned or tagged, or the tag sits alongside a
code, a link or a credit sending viewers to it. A hashtag that only indexes
a topic, a category or a recipe so the post can be found does not promote,
even when the subject matter is a brand's own product — `#cologne`,
`#desksetup`, `#homedecor`, `#salsabigmac`, and `#apple` or `#macbook` on a
video about a MacBook are all `0`. Naming a brand is not on its own a
promotion. A creator's own merchandise, shop,
course, app, book or paid membership is a brand like any other here, and
promoting it counts.

**Every trigger must relate to what the unit is about.** All four triggers
above — codes, calls to action, brand tags and shopping shelves alike —
count only when they relate to the **subject of this unit**, judged from the
frames and the title/description together. A code, a link or a tag pointing at something
the unit is not about — an unrelated store, an off-topic page, boilerplate
repeated on every upload — is not a promotion *of this unit*.

Relatedness is to the **subject**, not to a visible object. A brand's own
account tagged as the ingredient of the dish being made relates to the unit
and counts,
even when its packaging never appears in any frame: a recipe video that
credits `@safecatchfoods` as the tuna in the dish is a `1`, with or without
the can on screen.

Evidence: frames, title/description, and transcript where present (see
"Audio status" above).

**The asymmetry: `null`, not `0`, when another ad flag is already 1.**
`ad_undisclosed` is the only ad sub-flag that is nullable — the other three
are always `0` or `1`. Whenever `ad_paid_promotion`, `ad_paid_advertising`,
or `ad_brand_owned` is `1`, `ad_undisclosed` is forced to `null` rather than
being asked. `null` means "not applicable": the unit already carries a
disclosure, or is itself a platform ad, or is posted by the brand it
promotes, so the question "is this undisclosed?" does not arise for it. That
is a different fact from `0`, which means the question was asked and the
answer was no.

This suppression happens **after** judging, not instead of it: the judging
agent for `ad_undisclosed` only ever evaluates its own four triggers above
and has no visibility into the other three flags. The pipeline applies the
`null` override afterwards, once all four flags have resolved. For human
gold coding, a suppressed row may simply be left blank.

Because a suppression only ever happens when another flag is already `1`,
it can never flip the brand-gate OR from true to false — see the
`ad_undisclosed` note under `brands` below.

**This is the gate variable, and this is its definition:**

> Is any food or beverage product visually present, or verbally/textually
> referenced, in any of the 3 key frames or in the on-screen
> text/description/audio of the video? Yes/No. If "No", the remaining
> variables in this section are not coded.

`1` = Yes, `0` = No. When `has_food = 0`, `is_upf` and `food_category` are
`null`, not `0` — see the note under `is_upf`.

Apply the definition as written. It has no exclusions: the earlier
game-asset, UI-icon, metaphor/mascot and invented-dish carve-outs were
removed on 2026-08-25 (see the changelog). Anything that reads as a food or
beverage product counts, whatever the medium or setting.

**Two channels, either one sufficient.** Visual presence and verbal/textual
reference are independent routes to Yes. A food named in the on-screen text,
title, description or audio counts even when nothing edible is ever in shot,
and it need not be the subject of the content. Food in shot counts even when
nothing is said about it. Silence in one channel never cancels evidence from
the other.

**What the frames are.** The visual channel is scoped to the three sampled key
frames. Food that appears only between them, and is never referenced, is coded
`0` — the sampling did not observe it. The whole-video pipeline in
`video_testing/` has no such limit and sees the full video.

**Medium is not a test.** Filmed, photographed, drawn, animated and rendered
food all count equally, in any setting — including food in gameplay footage,
in a game world, or in an animated or fictional setting.

**Brand marks count.** A real food or drink brand's logo is Yes **even with no
product visible**, in either channel. Brand marks are themselves the marketing
exposure being measured; requiring a depicted product would undercount exactly
the sponsorship and banner formats this audit exists to capture. This also
settles the previously open case of real food brands advertised inside games:
under the current definition it is simply Yes.

### `is_upf` — the food is ultra-processed

Applies **only** when `has_food = 1`. Uses the NOVA framework.

**1** — the most prominent food or drink is ultra-processed (NOVA group 4):
industrial formulations such as soft drinks, packaged snacks, sweetened
cereals, confectionery, instant noodles, reconstituted meat products, packaged
breads and baked goods, sweetened dairy drinks, and most fast food.

**0** — unprocessed, minimally processed, a culinary ingredient, or simply
processed (NOVA groups 1–3): fresh or frozen fruit and vegetables, plain meat,
eggs, milk, dried legumes, rice, oils, cheese, freshly baked bread, canned
vegetables in brine.

**null** — `has_food = 0`, or the food cannot be identified well enough to
classify.

**Classify the food as it is consumed, not by its ingredients.** A
home-prepared dish is not NOVA 4 merely because it contains a processed
ingredient — a tuna salad made at home is not ultra-processed because there
is mayonnaise and ketchup in it.

**Why `null` and not `0`.** If `0` meant both "no food" and "food, but not
ultra-processed", every UPF proportion computed downstream would have a
corrupted denominator: the share of *food-containing* content that is UPF is a
different quantity from the share of *all* content that is UPF, and only the
nullable coding lets both be recovered. This rule is enforced in code — see
`pipeline._apply_labels`, which forces `is_upf = None` whenever
`has_food = 0`, rather than trusting the model to comply.

---

### `food_category` — dietary food group

Applies **only** when `has_food = 1`. Assigned by `category_agent`, which runs
alongside `upf_agent` and does not see its answer.

Exactly one of eight dietary food groups, for **the most prominent food or
drink in the unit** — the same product `is_upf` classifies, so the two
variables always describe one food from two angles.

| Value | Covers |
| --- | --- |
| `beverages` | Drinks, excluding milk and dairy drinks — soft and energy drinks, juices, waters, coffee, tea, and alcoholic drinks |
| `sweets_and_desserts` | Sweet treats and desserts — confectionery and chocolate, ice cream and edible ices, puddings and desserts, sugar, honey and syrups |
| `savoury_snacks` | Ready-to-eat savouries — crisps, extruded and popped snacks, savoury nuts, crackers eaten as a snack |
| `grains_and_bakery` | Cereal grains and everything baked from flour — bread, breakfast cereals, pasta, rice, cakes, biscuits, pastries and doughnuts |
| `fruits_and_vegetables` | Fruits and vegetables, including mushrooms, roots and tubers, pulses and legumes, seaweeds, and nuts and seeds |
| `protein_foods` | Meat, poultry and game, fish and seafood, and eggs |
| `dairy` | Milk and dairy products and their analogues — milk, yoghurt, cheese, cream, and dairy-based drinks |
| `prepared_and_other` | Prepared dishes and mixed meals as they are served, fats and oils, salts, spices, soups, sauces and salads, and foods for particular nutritional uses — and the residual for a food that fits none of the seven above |

**null** — `has_food = 0`, or the food cannot be identified well enough to
place in any group. Same reasoning as the `is_upf` null: a group recorded
against a unit with no food would corrupt every denominator computed over
food-containing content.

**Why eight, and why these eight.** This is the granularity food-marketing
content analyses actually report at — the WHO Europe and INFORMAS marketing
monitoring protocols, and the Ofcom HFSS advertising studies. It replaced the
sixteen Codex Alimentarius GSFA categories, which were designed to regulate
food *additives* rather than to describe what an advertisement shows: GSFA
splits what this study pools (edible ices, confectionery and sweeteners were
three separate categories) and pools what it would want split (GSFA 12.0 held
salt, soups, sauces, salads and protein products in one bin). Sixteen options
also left a coder — human or model — with several defensible answers for a
single product, which arrives in the results as noise rather than as signal.

**This is orthogonal to `is_upf`.** `food_category` says *what kind* of food
the unit shows; `is_upf` says *how processed* it is. A packaged sweetened
breakfast cereal is `grains_and_bakery` **and** `is_upf = 1`; porridge oats
are `grains_and_bakery` **and** `is_upf = 0`. The two are recorded
independently precisely so they can be cross-tabulated — "which food groups
carry the UPF exposure" is the question this pairing exists to answer, and
inferring one from the other would destroy it.

That orthogonality is also why `grains_and_bakery` takes **all** bakery,
sweet or plain. A chocolate cake is a grain-based food that `is_upf` marks as
ultra-processed; splitting bakery by sweetness here would fold a processing
judgement into a what-is-it judgement and duplicate `is_upf` instead of
crossing with it.

**Classify the dish as it is served, not by its ingredients.** A composed or
cooked dish belongs in `prepared_and_other` even when its inputs obviously
fit another group: a burger is not `protein_foods`, a bread salad is not
`grains_and_bakery`, fries are not `fruits_and_vegetables`. The variable
records what was put in front of the viewer, not what went into making it.

**Choosing between two plausible groups.** Prefer the more specific one.
That preference settles *which* group a single food belongs to; it never
licenses breaking a dish down into its ingredients and grouping one of them
instead. `prepared_and_other` is where a composed dish belongs, and it is
also the residual for a single food that fits none of the other seven.

**Note it is not a binary label.** Unlike the ad sub-variables, `has_food` and
`is_upf`, this is a string enum, so it is deliberately not part of
`schema.LABEL_FIELDS` and does not appear in the binary
agreement/confusion-matrix machinery.

**Gold coded before the change.** `gold.load_gold` translates the retired GSFA
slugs to their successor on load (`gold._LEGACY_CATEGORIES`), so a gold CSV
labelled under the sixteen-category scheme keeps its coding. An unrecognised
slug is still an error, as before.

---

### `brands` — the brand that paid for the ad

Applies **only** when **any ad sub-flag is 1** — now an OR over all four:
`ad_paid_promotion`, `ad_paid_advertising`, `ad_brand_owned`,
`ad_undisclosed` — computed once by `pipeline.any_ad`, the single place this
OR lives. Assigned by `brand_agent`, which runs last of all, after every ad
sub-agent has a verdict.

`ad_undisclosed`'s `null`-when-another-flag-is-1 suppression (see its own
section above) cannot affect this gate: a suppression only ever happens
*because* one of the other three flags is already `1`, so the OR is true
either way — a suppressed `ad_undisclosed` never costs `brands` its trigger,
it is simply redundant with the flag that caused the suppression.

A list of **at most three** brand names, ordered by how strongly the payment
evidence points at them — the clearest payer first.

**The variable asks who paid, not what was on screen.** This is the whole
distinction. A supermarket haul can show forty brand marks and have no
sponsor at all; a plain talking-head video with no product in frame can be a
paid promotion for one. Brand *exposure* is measured by `has_food` and
`food_category`; `brands` measures the commercial arrangement behind the unit.

**A brand qualifies only on evidence of payment.** Any one of these is enough:

| Evidence | Example |
| --- | --- |
| Sponsorship disclosure naming the brand | "sponsored by X", "thanks to X", "paid partnership with X", "brought to you by X" |
| Discount or affiliate mechanic | a promo or discount code, "use my code", "link in the description" |
| Tagged or @-mentioned as the partner | `@brand` in the description, a partner tag |
| Gifted product | "thanks to X for sending me these" |
| The unit is an ad slot | pre-roll, mid-roll, banner, overlay or shopping panel — the brand being advertised in it |
| Self-promotion | the creator's own merchandise, course, app, book or paid membership |

**A brand does not qualify** because its product or logo is merely visible,
because the speaker likes it, or because the video is about it. Naming a brand
is not on its own a promotion — the same boundary the ad sub-variables draw,
which is why `brand_agent`'s prompt is built from
`agents.PROMOTION_MECHANICS` and `agents.NOT_A_PROMOTION`, the same mechanics
a future spoken-sponsorship sub-agent would use.

**Three distinct states, and they must not be collapsed:**

| Value | Meaning |
| --- | --- |
| `null` | `brand_agent` was never asked — no ad sub-flag was 1 — or the call failed. |
| `[]` | The unit **is** advertising, but no paying brand could be identified. |
| `["X", …]` | The identified payer(s), clearest first. |

The empty list is a finding, not a failure: an ad whose advertiser is never
named is a real and common outcome, and the share of ads that are
unattributable is itself a result about how disclosure works on the platform.
The prompt says so explicitly, twice, because a question that presupposes an
advertiser exists invites a guess — and a guessed sponsor is worse than no
sponsor.

**Free text, so names arrive unnormalised.** There is no fixed list to
validate against: the set of brands that sponsor content is open and changes
constantly. "Coca-Cola", "Coca Cola" and "Coke" therefore all arrive as
distinct strings, and canonicalising them is an **analysis step over the
finished corpus**, not something an agent labelling one unit in isolation
could do consistently. Entries are stripped of a leading `@`, de-duplicated
case-insensitively, and dropped if longer than 60 characters — the cap exists
because the failure mode of a free-text field is prose ("a fitness apparel
company whose logo appears on the left" is not a brand name).

**What evidence `brand_agent` sees.** The frames, the title and description,
and — where one exists — an audio transcript. Metadata is promoted from
corroboration to *primary* evidence for this variable, unlike every other
agent's: a payment is an arrangement, and arrangements are disclosed in words
far more reliably than they are depicted in pixels. A logo in frame is the
weakest signal here, not the strongest.

`brand_agent` is built to accept a transcript (`AgentSpec.uses_transcript`),
but nothing populates one today: the audio escalation channel that used to
produce a transcript for a promoted unit is currently disabled (see
`Config.audio_escalation` and the changelog) pending the spoken-sponsorship
sub-variable. Once that channel is rebuilt, an escalated unit is again
exactly the case where a transcript exists for a brand-eligible unit.

**Not a binary label.** Like `food_category`, `brands` is deliberately outside
`schema.LABEL_FIELDS` and the binary agreement/confusion-matrix machinery. It
is written to `labels.csv` JSON-encoded (`["Gymshark"]`), so that a brand name
containing a comma or an ampersand survives the flat table intact and `[]`
stays distinguishable from an empty cell.

### `foods` — foods and drinks visible on screen

Applies **only** when `has_food = 1`. Assigned by `foods_agent`, which runs
alongside `upf_agent` and `category_agent` — all three fire together on the
same gate, since all three describe the food a unit already has.

A list of **at most five** items, ordered by how prominent each is in the
frames — the most prominent first.

**The variable asks what is on screen, not what it means.** This is the
opposite question from `brands`. `brands` asks *who paid*, which visibility
alone never answers; `foods` asks *what is visible*, which visibility alone
*does* answer. There is no payment-style evidence test here: every distinct
food or drink item visible in the key frames qualifies, whether or not it is
the subject of the content and whether or not it is named in the title,
description or audio.

**Three distinct states, and they must not be collapsed:**

| Value | Meaning |
| --- | --- |
| `null` | `foods_agent` was never asked — `has_food ≠ 1` — or the call failed. |
| `[]` | Food **is** present, but nothing could be named specifically enough to list a single item. |
| `["X", …]` | The identified item(s), most prominent first. |

The empty list is a finding, not a failure — the same rule `brands` uses for
its own `[]`, and for the same reason: a unit where food is present but
unidentifiable is a real outcome, distinct from a unit where the question
never applied.

**Free text, so names arrive unnormalised.** Modelled on `brands`: there is
no fixed list to validate against, since the set of nameable foods is open.
"fries", "french fries" and "chips" therefore all arrive as distinct strings,
and canonicalising them is an analysis step over the finished corpus, not
something an agent labelling one unit in isolation could do consistently.
Entries are dropped if longer than 60 characters, for the same reason the cap
exists on `brands`: the failure mode of a free-text field is prose ("a
plated meal with several items arranged on it" is not a food name).

**Not a binary label, and not scored.** Like `brands`, `foods` is
deliberately outside `schema.LABEL_FIELDS` and the binary
agreement/confusion-matrix machinery, and is recorded in the gold set for
analysis only — `gold.score_predictions` never compares it, because an open
vocabulary makes agreement noise, not signal. It is written to `labels.csv`
JSON-encoded (`["pizza slice", "cola bottle"]`), the same encoding `brands`
uses and for the same reason: a food name containing a comma survives the
flat table intact and `[]` stays distinguishable from an empty cell.

## General decision rules

1. **Judge only what is visible.** Do not infer beyond the attached
   frames. Prior knowledge that a channel
   usually features food is not evidence about this screenshot.
2. **When genuinely ambiguous, prefer the conservative label** — `0`, or
   `null` for `is_upf`. Systematic under-counting is recoverable and
   reportable; a noisy inflated estimate is neither.
3. **Most prominent food wins.** With several foods in frame, classify the one
   that is most visually dominant or is the subject of the content. A fast-food
   meal with a side salad is `is_upf = 1`.
4. **Ambiguity is data.** A case you genuinely cannot decide gets flagged
   `disputed` in the gold set rather than force-labelled. A cluster of disputed
   cases of one kind means this codebook has a hole there.

---

## Adjudicated edge cases

Append-only. Every entry states a **principle**, not just a verdict — the
principle is what resolves the next twenty similar cases. Every entry should
also have a gold-set fixture, so a rule written down here is mechanically
checked from then on.

| # | Date | Case | Decision | Reasoning | Fixture |
|---|------|------|----------|-----------|---------|
| 1 | 2026-08-10 | ~~Mobile game ad using candy sprites (Candy Crush)~~ **(superseded 2026-08-25)** | **No longer in force.** `is_ad=1`, `has_food=0`, `is_upf=null` — superseded: the gate has no exclusions, so these units are now `has_food=1` | Game assets are not consumable products and generate no food-marketing exposure. The product being advertised is a game. Counting it would inflate the food-content denominator with content that markets something else entirely. | `tests/fixtures/gold/images/12.jpeg` |
| 2 | 2026-08-10 | Real food/drink brand logo, no product visible (e.g. Coca-Cola on a banner) | `has_food=1`, `is_upf` per the brand's product | Brand marks are the mechanism of marketing exposure under study; requiring a depicted product would undercount sponsorship and banner formats. | *(needs fixture)* |
| 3 | 2026-08-10 | ~~In-game food in organic gameplay footage (Starfield food cube review; Cooking Clash VR)~~ **(superseded 2026-08-25)** | **No longer in force.** `has_food=0`, `is_upf=null` — superseded: the gate has no exclusions, so these units are now `has_food=1` | Principle: the test is whether the food exists as a real consumable product, not whether it looks like food or serves another product. Virtual food generates no real-world food-marketing exposure and cannot be assigned a NOVA group, which is defined over industrial processing of actual foodstuffs. Applies to organic gameplay as well as game ads — case 1's ad framing was too narrow. | `tests/fixtures/gold/images/Screenshot From 2026-08-10 10-53-30.png` (and unit 15) |
| 4 | 2026-08-13 | Sponsorship disclosed in title/description text, re-audited against the gold set's `description` backfill | `is_ad=1` regardless of frame content | Principle: a `#ad`/`#sponsored`/"paid promotion" disclosure is evidence about the whole video, not about any one frame, so it broadens `is_ad` even when nothing commercial is visible. Auditing the 21-row gold set's newly backfilled descriptions against this rule found **no** row whose title or description carries the disclosure text — none needed re-coding. The rule is written down for the next batch, not because this one exercised it. | *(none — no fixture currently exercises this rule; needs a disclosed-sponsorship example)* |
| 6 | 2026-08-13 | Sponsorship disclosed only in speech — "this video is sponsored by X", a discount code read aloud — with nothing commercial in frame and no disclosure in the title or description | `is_ad=1` | Principle: a disclosure is evidence about the whole video regardless of which channel carries it, so speech is a third independent trigger alongside frame content and metadata. This is the *target* phenomenon of the audit rather than an incidental case: an undeclared ad is by definition one the metadata does not declare, so restricting `is_ad` to what is visible or written systematically misses exactly the population of interest. The converse is also ruled: an unpaid favourable mention with no code, link or sponsorship language is not advertising, so that the rule cannot be satisfied by brand-name detection alone. | *(needs fixtures — 15 of 21 rows now carry an audio track, but none of their rationales mention spoken disclosure; this rule is still unexercised. Still needs one audio-only sponsorship and one enthusiastic unpaid brand mention.)* |
| 5 | 2026-08-13 | ~~Non-photographic food: a still illustration of an ordinary dish, versus an animated/rendered dish invented for a fictional setting~~ **(superseded 2026-08-25)** | **No longer in force.** Still artwork: `has_food=1`. Animated or rendered invented food: `has_food=0`, `is_upf=null` — superseded: the gate has no exclusions, so these units are now `has_food=1` | Principle: medium decides *which* test applies, not the answer. A drawing, illustration or painting of food is a depiction of food and counts on its own — hand-drawn is not a disqualifier. Moving imagery (animation, CGI, 3D, game engines) carries the extra requirement that the depicted food exist in reality, because that is where invented foods are routinely presented as if real; invented food generates no real-world marketing exposure and has no NOVA group. Generalises case 3 beyond game worlds without making rendering technique disqualifying on its own. | *(needs fixtures — a still food illustration, and an animated invented dish)* |

---

## Changelog

- **2026-08-27** — Expanded the ad sub-variable family from one to four.
  `ad_paid_promotion` is redefined: it now means commercial content
  distributed through the **platform's advertising system** (a boosted or
  promoted post, a platform ad placement, an in-feed "Sponsored"/"Promoted"
  slot) rather than a rendered disclosure banner. The platform-banner
  meaning it used to carry moved to a new sub-variable,
  `ad_paid_advertising`, unchanged in substance from the old
  `ad_paid_promotion` definition. Two more sub-variables were added:
  `ad_brand_owned` (the posting account is the brand itself, inferred from
  visible identity cues — no channel/account metadata field exists) and
  `ad_undisclosed` (a promo/discount/affiliate code, an undisclosed direct
  call to action, or an explicit brand hashtag/@mention). `ad_undisclosed` is
  the only sub-flag that is nullable: it is forced to `null`, not `0`,
  whenever another ad flag is already `1`, applied by the pipeline after the
  judging agent's own triggers resolve — see its section above for why
  this cannot affect the `brands` gate. Each addition cost exactly one
  registry entry in `schema.AD_SUBVARIABLES` plus one codebook section, no
  changes to `pipeline.py`, `storage.py`, or app/gold/builder code — the
  payoff of the 2026-08-27-earlier decomposition below. `brands` continues to
  gate on **any** ad sub-flag being 1 (`pipeline.any_ad`), now an OR over all
  four. The audio escalation channel remains disabled
  (`Config.audio_escalation` raises if set), so the transcript three of the
  four specs are written to consume is `None` for every caller today; those
  specs are inert on that channel until audio is re-enabled. Benchmarks
  recorded before this date measured the single-sub-variable
  `ad_paid_promotion` (the old, banner-only meaning) and are not comparable
  to results under the new four-variable scheme.

- **2026-08-27 (earlier)** — Retired `is_ad` and replaced it with a
  registry-driven family of independent ad sub-variables
  (`schema.AD_SUBVARIABLES`). At that point there was exactly one,
  `ad_paid_promotion` — a platform-rendered paid-promotion disclosure banner
  (TikTok's "Paid partnership with X", YouTube's "Includes paid
  promotion") — which was strictly narrower than the old `is_ad`: a
  creator-made disclosure graphic, an `#ad` hashtag in the metadata, and a
  spoken sponsor read were all out of scope pending future sub-variables.
  `brands` gated on **any** ad sub-flag being 1 (`pipeline.any_ad`) rather
  than on a stored `is_ad`; there is no longer a stored `is_ad` column
  anywhere. The audio escalation channel, which used to flip `is_ad` on a
  spoken disclosure, was disabled in this pass, and `Config.audio_escalation`
  now raises rather than silently doing nothing if enabled. Benchmarks
  recorded before this date measured `is_ad`, a broader and differently-scoped
  construct, and are not comparable to `ad_paid_promotion` results. The
  design intent: adding another sub-variable should need one registry entry
  plus one codebook paragraph, no changes to `agents.py`, `pipeline.py`,
  `storage.py`, or any app/gold/builder code — realised the same day by the
  four-variable expansion above.

- **2026-08-25** — Replaced the `has_food` definition with the team's gate
  wording, and **removed its exclusions entirely**. The variable is now:
  "is any food or beverage product visually present, or verbally/textually
  referenced, in any of the 3 key frames or in the on-screen
  text/description/audio of the video?" Two changes, not one. First, a
  verbal or textual reference is now an independent route to `1` — a food
  named in on-screen text, title, description or audio counts with nothing
  edible in shot, and it no longer has to be the *subject* of the content, so
  the previous "passing mention does not count" rule is gone. Second, the
  game-asset, virtual/in-game, UI-icon, emoji, metaphor/mascot and
  invented-dish exclusions are removed, along with the still-artwork vs
  moving-imagery test pair: medium and setting no longer bear on the answer.
  This supersedes adjudicated cases 1, 3 and 5, resolves the open "real
  brands inside games" question to `1`, and inverts the expected label on the
  gold units those cases were built from (12, 15, 16), which need re-coding
  before the gold set is used again. Benchmarks recorded before this date
  measured a different construct and are not comparable.

- **2026-08-13** — Added spoken promotion as a third independent `is_ad`
  trigger (case 6), alongside visible advertising and metadata disclosure.
  Sponsorship language, discount or affiliate mechanics, gifted-product
  language, or self-promotion heard in the audio yields `is_ad = 1` even with
  nothing in frame and nothing in the title or description. Paired with an
  explicit exclusion — an unpaid favourable mention of a product is not
  advertising — so the rule cannot collapse into brand-name detection. The
  channels are independent and additive: audio can raise `is_ad` to 1, never
  lower it to 0. Implemented as a conditional escalation that runs only when
  the visual/metadata pass returns something other than 1; see
  `docs/audio-escalation-plan.md`. No fixture exercises the rule yet, so it is
  written down ahead of the evidence, like case 4.
- **2026-08-13** — Reworked the `has_food` exclusions from a game-only rule
  into two ordered tests (case 5). Test 1, applied to every medium: is real
  food being depicted at all? Still artwork passes it — a drawing or
  illustration of food is a depiction of food, and being hand-drawn is not on
  its own a reason to exclude. Test 2 applies only to moving imagery
  (animation, CGI, 3D rendering, game engines), which counts only when the
  food shown exists in the real world; an invented dish from a fictional
  setting stays `has_food = 0` however convincingly it is rendered. The
  previous wording had a single medium-independent "must exist" test, which
  wrongly excluded drawings of ordinary food. No change to the brand-mark
  inclusion (case 2), the virtual/in-game exclusion (case 3), or the
  gaming-genre clarification.
- **2026-08-14** — Collapsed the single/bundle split. `per_image` and
  `agent_per_image` are gone; a lone screenshot is a bundle of one, so the
  unit of analysis is now set by `--bundle-size` rather than by the mode. No
  definition changed, but every prompt was reworded once to hold for a unit of
  any size (`schema.UNIT_DEFINITION`), which moves every prompt fingerprint —
  records saved before this date are not comparable against later ones.
- **2026-08-14** — The single-pass `per_bundle` mode was dropped too, leaving
  `agent_per_bundle` as the only labelling flow. No definition changed.
- **2026-08-13** — Broadened `is_ad` to include disclosed sponsorship:
  `#ad`, `#sponsored`, "paid promotion", or "includes paid promotion" in the
  title or description now yields `is_ad = 1` even with no commercial content
  visible in frame. Reconciled the `per_image` unit-of-analysis entry, since a
  disclosure is a property of the whole video rather than of a given frame.
  Backfilled a `description` column into `tests/fixtures/gold/gold.csv` from
  the YouTube Data API and re-audited all 21 rows against the new rule; none
  qualified for re-coding (case 4).
- **2026-08-12** — Added a 3-agent labelling flow (`agents.py`,
  `agent_per_image` / `agent_per_bundle` modes): one focused, single-field
  agent per variable instead of one combined call. No definitions changed —
  `has_food` and NOVA classification text is imported from `schema.py` into
  `agents.py` so both prompt shapes stay substantively identical, guarded by
  a test.
- **2026-08-10** — Codebook extracted from `src/puppets/schema.py` into this
  document as the source of truth. Added the `has_food` exclusions rule
  (case 1) and the brand-mark inclusion rule (case 2) to both the `per_image`
  and `per_bundle` prompts via the shared `_HAS_FOOD_EXCLUSIONS` constant.
- **2026-08-10** — Added `has_food` case 3: virtual / in-game food is not
  food, regardless of how photorealistic it looks and regardless of whether
  the frame is a game ad or organic gameplay footage. Rewrote the case 1
  exclusions so the primary test is reality (does the food exist as a real,
  purchasable or edible product) rather than purpose (does the food imagery
  serve a non-food product) — the purpose framing missed organic gameplay
  content entirely, since it has no other product for the food to be serving.
  Left the treatment of real brands advertised inside games explicitly open.
  Also made explicit that rendering technique is never the test: a CGI or
  animated depiction of a real product or brand still counts as
  `has_food = 1`; only food with no real-world product behind it at all is
  excluded. An earlier, unqualified "rendered food is not food" phrasing
  would have wrongly zeroed out CGI-heavy real ads (e.g. a McDonald's or
  Coca-Cola spot with a CGI burger or drink).
- **2026-08-25** — Replaced the sixteen Codex Alimentarius GSFA categories in
  `food_category` with eight dietary food groups: `beverages`,
  `sweets_and_desserts`, `savoury_snacks`, `grains_and_bakery`,
  `fruits_and_vegetables`, `protein_foods`, `dairy`, `prepared_and_other`.
  GSFA is an additive-regulation taxonomy, not a description of what an ad
  shows — it split what this study pools and pooled what it would want split,
  and sixteen options left several defensible answers for one product, which
  reaches the results as noise rather than signal. Eight is the granularity
  the WHO Europe / INFORMAS marketing-monitoring protocols and the Ofcom HFSS
  advertising studies report at. `gold.load_gold` migrates the retired slugs
  on load (`gold._LEGACY_CATEGORIES`), so gold coded under the old scheme
  keeps its labelling; an unrecognised slug is still an error.
- **2026-08-24** — Added `food_category`, the Codex Alimentarius GSFA
  top-level food category (01.0–16.0), assigned by a new `category_agent`
  that runs only when `has_food = 1`. Added as a fourth agent rather than a
  second field on `food_agent`, so the `has_food` prompt and response schema
  stay byte-identical and existing `has_food` benchmarks remain comparable.
  Deliberately independent of `is_upf` — the two are cross-tabulated in
  analysis, not derived from each other — and deliberately outside
  `schema.LABEL_FIELDS`, which is the binary-label machinery.
- **2026-08-24** — Added `brands`, the brand or brands that paid for the
  promotion, assigned by a new `brand_agent` that runs only when
  `is_ad = 1`. A fifth agent rather than a second field on `ad_agent`, for
  the same reason `category_agent` was a fourth: the `is_ad` prompt and
  response schema stay byte-identical, so existing `is_ad` benchmarks remain
  comparable. Gated on `is_ad` and placed **after** the audio escalation,
  which is the only remaining step that can change `is_ad` — so an
  audio-promoted unit is still asked who paid, and is the one case where a
  transcript is available to answer with. Records payment, not exposure: `[]`
  means "advertising, payer unidentifiable" and is kept distinct from the
  `null` of "never asked". Outside `schema.LABEL_FIELDS`, like
  `food_category`. Benchmark scoring for it is not yet implemented — string
  agreement needs a normalised set-overlap measure, not the binary machinery.
