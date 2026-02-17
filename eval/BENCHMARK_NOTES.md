# Benchmark Notes

## Dataset Issues

### HotpotQA_200 q15 — Typo: "country" vs "county"

**Question**: "Brown State Fishing Lake is in a country that has a population of how many inhabitants?"
**Gold**: 9,984

The question says "country" but the answer (9,984) is the **county** population of Brown County, Kansas. Source text:
- "Brown State Fishing Lake... is a protected area in **Brown County**, Kansas"
- "Brown County... the county population was **9,984**"

The agent found 9,984 at step 7 of 20, correctly noted *"the question asks about the country's population, not the county"*, and rejected its own correct answer. It then burned 13 more tool calls searching for the US national population (not in the dataset). This is a dataset bug, not a system failure.

## EM vs Substantive Accuracy (Formatting Mismatches)

These are questions where the agent found the correct answer but EM=0 due to gold-string formatting:

| Q | Predicted | Gold | Issue |
|---|-----------|------|-------|
| q1 | Chief of Protocol of the United States | Chief of Protocol | Over-specified (source has full title) |
| q4 | Greenwich Village | Greenwich Village, New York City | Under-specified (agent stripped context) |
| q7 | 3,677 | 3,677 seated | Missing unit from source span |
| q10 | Kansas Song (We're From Kansas) | Kansas Song | Included parenthetical from source |
| q14 | 1986 to 2013 | from 1986 to 2013 | Missing preposition |
| q15 | *(failed to answer)* | 9,984 | Dataset typo: "country" vs "county" |
| q19 | Robert Erskine Childers | Robert Erskine Childers DSC | Missing honorific |
| q24 | IFFHS World's Best Goalkeeper | World's Best Goalkeeper | Included org prefix from source |
| q25 | Lee Hazlewood | Barton Lee Hazlewood | Used common name, gold wants full legal name |
| q28 | yes | Henry J. Kaiser | Misread as yes/no — question ends with "?" but expects entity |
| q31 | Fujioka, Gunma, Japan | Fujioka, Gunma | Over-specified (added country) |
| q32 | Charles Nungesser | Charles Eugène | Wrong name variant |

Note: q28 is borderline — the question genuinely reads like yes/no verification but gold expects a name.

## Retrieval/Comprehension Failures

### q21 — Wrong entity in relationship chain

**Question**: "This singer of A Rather Blustery Day also voiced what hedgehog?"
**Gold**: Sonic | **Predicted**: Dr. Robotnik | **EM**: 0, **F1**: 0.00

The agent correctly found Jim Cummings as the singer. The critical source text (chunk_214) says:
> "He is known for voicing the title character from 'Darkwing Duck', **Dr. Robotnik from 'Sonic the Hedgehog'**, and Pete."

The question asks "what hedgehog?" — the answer is **Sonic** (the hedgehog the show is named after), not Dr. Robotnik (the villain). The agent picked the character name mentioned in the source text rather than recognizing that "Sonic the Hedgehog" is the hedgehog's name.

12 tool calls total. The agent searched extensively (5 chunk_text_search, 3 entity_vdb_search, relationship_onehop, entity_onehop) but kept finding the same chunk_214 with the Dr. Robotnik reference. The entity VDB didn't have a separate "Sonic" entity to disambiguate.

**Root cause**: The source text's phrasing "Dr. Robotnik from 'Sonic the Hedgehog'" makes it ambiguous whether the agent should extract the character name or the show name. The question asks "what hedgehog" but the hedgehog (Sonic) appears as a show title, not as a character name in the source.

### q23 — Exhausted tools, never submitted answer

**Question**: "Which performance act has a higher instrument to person ratio, Badly Drawn Boy or Wolf Alice?"
**Gold**: Badly Drawn Boy | **Predicted**: *(never called submit_answer)* | **EM**: 0, **F1**: 0.14

22 tool calls including `auto_compose` and `execute_method` (bug — these shouldn't be available in fixed mode, now fixed).

The agent found clear data for Wolf Alice:
> "Wolf Alice are a **four-piece alternative rock band**... Ellie Rowsell (vocals, guitar), Joff Oddie (guitars, vocals), Theo Ellis (bass), and Joel Amey (drums, vocals)."

For Badly Drawn Boy, it found:
> "Damon Michael Gough... known by the stage name Badly Drawn Boy, is an English **indie singer-songwriter and multi-instrumentalist**."

The agent correctly identified that Badly Drawn Boy is a solo multi-instrumentalist (1 person, many instruments = high ratio) and Wolf Alice is 4 people with ~5 instrument roles. But it couldn't find explicit numerical data and spiraled through increasingly desperate searches for band composition.

**Root cause**: The agent had enough information to reason through the answer but lacked confidence to commit without explicit numbers. A forced submit_answer at max_turns would have likely gotten this right.

### q29 — Wrong entity among similar alternatives

**Question**: "What is the name for the adventure in 'Tunnels and Trolls', a game designed by Ken St. Andre?"
**Gold**: Arena of Khazan | **Predicted**: Crusaders of Khazan | **EM**: 0, **F1**: 0.67

Only 4 tool calls — the agent found an answer quickly but it was the wrong one. The VDB search returned "Crusaders of Khazan" as the top entity. Source text (chunk_290):
> "**Crusaders of Khazan** is a computer adaptation of the tabletop role-playing game 'Tunnels and Trolls'..."

The agent treated "computer adaptation" as synonymous with "adventure" and stopped searching. It never found the separate "Arena of Khazan" entity/chunk.

**Root cause**: The entity VDB returned the wrong Khazan-related entity first, and the agent didn't search further after finding a plausible-looking match. The source text for Crusaders explicitly says "computer adaptation" not "adventure" — a more careful reading would have prompted further search.

## Bug Fixes During Benchmarking

### BENCHMARK_MODE pipeline shortcuts leak (fixed 2026-02-16)

`auto_compose`, `execute_method`, and `list_methods` were available in BENCHMARK_MODE=1 (fixed mode) due to `if BENCHMARK_MODE < 2:` guard. This allowed the agent in q23 to call these pipeline shortcuts, wasting turns. Fixed: all pipeline shortcuts now require `not BENCHMARK_MODE` (mode 0 only). BENCHMARK_MODE levels simplified to 0 (all tools) vs 1+ (retrieval-only).
