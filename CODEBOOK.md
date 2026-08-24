# Codebook — UPF marketing audit, Phase 1

The definitions in this file are the source of truth for the three labelled
variables. The system prompts in `src/puppets/agents.py` (the 3-agent flow —
one focused agent per variable) are *compiled artifacts* of this document:
when a prompt disagrees with it, the prompt is wrong and gets corrected here
first, then there.

The agent prompts cannot silently diverge on substance: `agents.py`
imports `HAS_FOOD_EXCLUSIONS` and `NOVA_CLASSIFICATION` from `schema.py`
rather than restating them, and a test pins that both flows compose the same
text. What differs between the two is call shape only — one combined call
per unit vs. up to three single-field calls — never the definitions below.

It is written to be usable by a human coder with no access to the code, because
the same definitions have to serve three audiences — the model, a second human
coder for reliability checks, and a reviewer reading the methods section.

---

## Unit of analysis

The unit is always one **bundle** of images, and its size — not the labelling
mode — is what decides the unit of analysis:

| Bundle size | Unit | `is_ad` means |
|---|---|---|
| 1 | One screenshot | Advertising is present **in this frame**, or the video is disclosed sponsored content |
| >1 | One video, given as consecutive sampled frames | Advertising is present in **any** frame of the video, or the video is disclosed sponsored content |

These are not interchangeable. A video whose 3rd of 5 sampled frames is a
mid-roll ad yields `is_ad = 1` once when its 5 frames are one bundle, but
`1, 1, 0, 0, 0` — or whatever the sampling caught — when each frame is its own
bundle of one. Any downstream proportion must state which unit it is over, and
the two must never be pooled.

Sponsorship disclosure is an honest exception to the per-frame unit: a
`#ad` in the title or description is a property of the whole video, not of
any one frame, so every sampled frame of a disclosed video is `is_ad = 1`
under bundles of one even though no frame shows a commercial. This is a deliberate
crack in "judge only what is visible in this frame" — the text metadata is
attached to the unit being labelled, not inferred from it, so it does not
violate the visibility rule the same way prior knowledge of a channel would.

**Scope caveat.** This disclosure rule is implemented only in
`agents._AD_SYSTEM_META` (the 3-agent flow's metadata-aware ad_agent
prompt) and only fires when a caller supplies `VideoMeta` — today, only
`benchmarks.execute` on the gold-benchmark path. `app.py`'s upload flow never
constructs `VideoMeta`, so live/production runs do not apply this rule.

---

## Variables

### `is_ad` — advertising content present

**1** — either of the following:

- the frame shows commercial advertising content:
  - pre-roll, mid-roll, or post-roll video ads
  - banner or overlay ads
  - sponsored or promoted placements in the feed or search results
  - shopping panels / product shelves
- the video is disclosed sponsored content: the title or description contains
  `#ad`, `#sponsored`, "paid promotion", or "includes paid promotion" — even
  when nothing commercial is visible in the frame. Disclosure text is metadata
  attached to the video, not something inferred, and a creator's own
  disclosure that a video is a paid placement is stronger evidence of
  advertising than the absence of an on-screen banner.
- the **speech** discloses or performs a commercial promotion, as heard in the
  video's audio — even when nothing commercial is visible in any frame and the
  title and description say nothing. This is the case the audio channel exists
  to catch: an undisclosed sponsorship is, by construction, one with no `#ad`
  in its metadata and often nothing to see. Qualifying speech is:
  - explicit sponsorship language: "sponsored by", "thanks to X for
    sponsoring", "paid partnership", "this video is brought to you by";
  - discount or affiliate mechanics: a promo or discount code, "use my code",
    "link in the description", "link in my bio", "my affiliate link";
  - gifted-product language: "they sent me this";
  - self-promotion: the speaker promoting their own merchandise, course, app,
    book, brand or paid membership.

**0** — organic content with no advertising in frame, no sponsorship
disclosure in the title or description, and no promotion in the speech: a
normal video playing, the home feed, search results, the comments section,
channel pages.

**Boundary notes**

- In-video sponsor segments ("this video is brought to you by…") are
  advertising when the sponsor's product or branding is in frame, **or** when
  the title or description carries a disclosure per the rule above. The two
  triggers are independent: a sponsor segment with the product in frame but no
  `#ad` tag is still `is_ad = 1` on visual grounds, and a video with a `#ad`
  tag but no visible product is still `is_ad = 1` on disclosure grounds.
- Creator merchandise promotion counts as advertising, spoken or shown. This
  is the self-promotion clause above: the audit measures marketing exposure,
  and a plug for the speaker's own product is marketing whether or not anyone
  paid them for it.
- A favourable opinion about a product, with no payment, code, link or
  sponsorship language, is **not** advertising. "I love this cereal, I eat it
  every week" is a person talking about food — `has_food` is what records
  that. Naming a brand out loud is not on its own a promotion; the promotion
  has to be disclosed or performed. This boundary is the one the audio channel
  is most likely to get wrong in the permissive direction, which is why it is
  stated as an explicit exclusion rather than left implied.
- The three triggers — visible advertising, metadata disclosure, spoken
  promotion — are independent, and any one of them is sufficient. Evidence
  from one channel is never cancelled by silence in another: a video with a
  spoken sponsor read and clean metadata is `is_ad = 1`, and the audio channel
  can only ever raise `is_ad` to 1, never lower it to 0.
- A channel's own end-screen promoting its other videos does **not** count —
  it is not commercial advertising for a product, and does not itself carry a
  sponsorship disclosure.

### `has_food` — food or drink present

**1** — any food or drink intended for human consumption is visible, or is the
subject of the content: packaged products, prepared dishes, ingredients,
beverages, or a food or drink brand's logo/branding.

**0** — otherwise.

**Exclusions (codebook cases 1 and 5).** Two tests, in this order.

**Test 1 — is real food being depicted at all?** Food or drink counts when it
is depicted as something people actually eat or drink, or is the branding of
such a product. This test does not care about medium. Filmed and photographed
food counts. **Still artwork counts too**: a drawing, illustration or painting
of food is a depiction of food, and being hand-drawn rather than photographed
never disqualifies it on its own.

**Test 2 — for moving imagery only, does the food exist?** Animation, CGI, 3D
rendering and game-engine output carry one extra requirement: they count only
when the food shown is a food that exists in the real world. An animated or
rendered version of an everyday food, or of a real brand's product, counts. A
dish invented for a fictional setting, with no real-world counterpart, does
not — however convincingly it is animated or rendered.

The asymmetry is deliberate. A still drawing of food reads as a depiction of
that kind of food; moving imagery is where wholly invented foods are
routinely presented as if real, and those generate no real-world marketing
exposure and have no NOVA group.

Do not count, in any medium:

- food that exists only inside a video game or other virtual world — items,
  pickups, crafting ingredients, or food rendered in gameplay footage —
  regardless of how photorealistic the rendering is, and regardless of
  whether the frame is an ad for the game or organic gameplay / let's-play
  content (codebook case 3). A cooking or restaurant *simulator* is not food
  content.
- food-shaped sprites, characters or props that function as game assets
  rather than as food
- food-shaped UI icons or emoji
- food used only as a metaphor or mascot for something else

Genre is never the test: real food physically filmed in a gaming creator's
video — a creator eating on camera, a real snack brand's sponsor segment —
still counts as `has_food = 1`. Gaming and animated content are not exempt
from food labelling.

**Open: real brands inside games.** A real food brand advertised *inside* a
game world — a Coca-Cola billboard in a racing game, an in-game McDonald's
tie-in item, an energy-drink brand on an esports overlay — sits between case
2 (brand marks count) and case 3 (virtual food does not) and is not yet
decided. Do not guess; flag `disputed` and route it here for adjudication.

**Inclusion, brand marks (codebook case 2).** A real food or drink brand's logo
counts as `has_food = 1` **even when no product is visible**. Brand marks are
themselves the marketing exposure being measured; requiring a depicted product
would systematically undercount exactly the sponsorship and banner formats the
audit exists to capture.

These two rules look contradictory and are not. The distinction is whether
real food or a real food brand is being depicted — a brand mark on a banner,
or a drawing of an ordinary dish — as against food that is a game asset, an
icon, a metaphor, or an animated invention with no real-world counterpart.

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

**Why `null` and not `0`.** If `0` meant both "no food" and "food, but not
ultra-processed", every UPF proportion computed downstream would have a
corrupted denominator: the share of *food-containing* content that is UPF is a
different quantity from the share of *all* content that is UPF, and only the
nullable coding lets both be recovered. This rule is enforced in code — see
`pipeline._apply_labels`, which forces `is_upf = None` whenever
`has_food = 0`, rather than trusting the model to comply.

---

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
| 1 | 2026-08-10 | Mobile game ad using candy sprites (Candy Crush) | `is_ad=1`, `has_food=0`, `is_upf=null` | Game assets are not consumable products and generate no food-marketing exposure. The product being advertised is a game. Counting it would inflate the food-content denominator with content that markets something else entirely. | `tests/fixtures/gold/images/12.jpeg` |
| 2 | 2026-08-10 | Real food/drink brand logo, no product visible (e.g. Coca-Cola on a banner) | `has_food=1`, `is_upf` per the brand's product | Brand marks are the mechanism of marketing exposure under study; requiring a depicted product would undercount sponsorship and banner formats. | *(needs fixture)* |
| 3 | 2026-08-10 | In-game food in organic gameplay footage (Starfield food cube review; Cooking Clash VR) | `has_food=0`, `is_upf=null` | Principle: the test is whether the food exists as a real consumable product, not whether it looks like food or serves another product. Virtual food generates no real-world food-marketing exposure and cannot be assigned a NOVA group, which is defined over industrial processing of actual foodstuffs. Applies to organic gameplay as well as game ads — case 1's ad framing was too narrow. | `tests/fixtures/gold/images/Screenshot From 2026-08-10 10-53-30.png` (and unit 15) |
| 4 | 2026-08-13 | Sponsorship disclosed in title/description text, re-audited against the gold set's `description` backfill | `is_ad=1` regardless of frame content | Principle: a `#ad`/`#sponsored`/"paid promotion" disclosure is evidence about the whole video, not about any one frame, so it broadens `is_ad` even when nothing commercial is visible. Auditing the 21-row gold set's newly backfilled descriptions against this rule found **no** row whose title or description carries the disclosure text — none needed re-coding. The rule is written down for the next batch, not because this one exercised it. | *(none — no fixture currently exercises this rule; needs a disclosed-sponsorship example)* |
| 6 | 2026-08-13 | Sponsorship disclosed only in speech — "this video is sponsored by X", a discount code read aloud — with nothing commercial in frame and no disclosure in the title or description | `is_ad=1` | Principle: a disclosure is evidence about the whole video regardless of which channel carries it, so speech is a third independent trigger alongside frame content and metadata. This is the *target* phenomenon of the audit rather than an incidental case: an undeclared ad is by definition one the metadata does not declare, so restricting `is_ad` to what is visible or written systematically misses exactly the population of interest. The converse is also ruled: an unpaid favourable mention with no code, link or sponsorship language is not advertising, so that the rule cannot be satisfied by brand-name detection alone. | *(needs fixtures — 15 of 21 rows now carry an audio track, but none of their rationales mention spoken disclosure; this rule is still unexercised. Still needs one audio-only sponsorship and one enthusiastic unpaid brand mention.)* |
| 5 | 2026-08-13 | Non-photographic food: a still illustration of an ordinary dish, versus an animated/rendered dish invented for a fictional setting | Still artwork: `has_food=1`. Animated or rendered invented food: `has_food=0`, `is_upf=null` | Principle: medium decides *which* test applies, not the answer. A drawing, illustration or painting of food is a depiction of food and counts on its own — hand-drawn is not a disqualifier. Moving imagery (animation, CGI, 3D, game engines) carries the extra requirement that the depicted food exist in reality, because that is where invented foods are routinely presented as if real; invented food generates no real-world marketing exposure and has no NOVA group. Generalises case 3 beyond game worlds without making rendering technique disqualifying on its own. | *(needs fixtures — a still food illustration, and an animated invented dish)* |

---

## Changelog

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
