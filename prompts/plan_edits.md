# Edit Planning Prompt

You are an expert UGC video editor specialising in viral social media content for venues, restaurants, and nightlife.

You have analysed a folder of raw clips from a cocktail making class at **Turmbar Hamburg**. Below is a JSON array of clip analysis results. Your job is to plan exactly **3 distinct video edits**, each approximately 30 seconds long, each matching one of the creative briefs below.

## Clip analyses:
{CLIP_ANALYSES}

---

## The 3 required edits:

### Cut 1 — "I didn't know I could do this"
- **Vibe:** Soft, personal, aspirational. The creator feels surprised by their own competence.
- **Script direction:** Opens uncertain, builds to confident. Feels like a personal revelation.
- **Hook clip:** Prioritise a close-up of hands shaking a cocktail — ideally showing some hesitation or concentration. If none exists, use the most intimate/personal close-up available.
- **Transition:** fade

### Cut 2 — "Hamburg's most underrated evening"
- **Vibe:** High energy, FOMO, fast cuts. Makes the viewer feel like they're missing out right now.
- **Script direction:** Punchy, declarative, moves fast. Opens on venue atmosphere.
- **Hook clip:** Prioritise a wide shot of the venue — moody bar lighting, bottles, atmosphere. Then cut fast to a reaction shot (first sip, surprise, delight).
- **Transition:** cut

### Cut 3 — "What they don't tell you about cocktail classes"
- **Vibe:** Curiosity-driven, conversational, relatable. Self-deprecating humour.
- **Script direction:** List format ("number one… number two…"), ends on a positive payoff.
- **Hook clip:** Prioritise a moment of something going slightly wrong — a spill, a laugh, an awkward moment. Instantly relatable opener.
- **Transition:** cut

---

## Your task:

Return a JSON object with exactly 3 cuts, one per brief above. Each cut must:
- Start with the best available hook clip for that brief
- Use a different subset and ordering of clips from the others
- Have tight trims — keep clips punchy, no dead air

Return a JSON object in exactly this format:

```json
{
  "cuts": [
    {
      "id": "cut_1",
      "name": "i_didnt_know_i_could_do_this",
      "hook": "One sentence describing the viral hook strategy",
      "vibe": "One sentence describing the overall feel and target audience emotion",
      "target_duration": 30,
      "clips": ["IMG_6682.MOV", "IMG_6699.MOV", "IMG_6642.MOV"],
      "trim": {
        "IMG_6682.MOV": {"start": 0, "end": 8},
        "IMG_6699.MOV": {"start": 2, "end": 7},
        "IMG_6642.MOV": {"start": 0, "end": 5}
      },
      "transition": "fade"
    }
  ]
}
```

Rules:
- `clips` must be ordered — first clip is the hook/opener
- `trim.start` and `trim.end` are in seconds. Keep cuts tight and energetic.
- `transition` is one of: `cut` | `fade`
- Total duration of trimmed clips should approximately match 30 seconds
- Only use filenames that exist in the clip analyses provided
- The `name` for each cut must match: `i_didnt_know_i_could_do_this`, `hamburgs_most_underrated_evening`, `what_they_dont_tell_you`
- Return ONLY the JSON object, no preamble or explanation
