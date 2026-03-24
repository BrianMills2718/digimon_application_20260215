# Pre-Analysis: 8 Both-Fail Questions

Pre-analyzing before graph rebuild completes. For each question: what entities must be in the graph, what's the reasoning chain, and where might GraphRAG have an advantage?

## Question-by-Question Analysis

### 1. 2hop__170823_120171 — "What year did the publisher of Labyrinth end?"
**Chain**: Labyrinth (film/book) → publisher → year publisher ended
**Entities needed**: "Labyrinth", the publisher entity, the publisher's end date
**Graph advantage**: If the graph has Labyrinth → publisher edge, the chain is direct.
**Why both failed**: Both got close (1985, 1990 vs gold 1986). This is a precision issue — the right fact is in the corpus but the wrong year is being extracted. May be an answer synthesis issue, not retrieval.
**Diagnosis plan**: Check if "Labyrinth" entity exists, check if publisher edge exists, check if chunk with "1986" is retrievable.

### 2. 2hop__511454_120259 — "When was Lady Godiva's birthplace abolished?"
**Chain**: Lady Godiva → birthplace (Coventry? No — the gold answer 918 suggests an Anglo-Saxon entity) → when abolished
**Entities needed**: "Lady Godiva", her birthplace, the abolition date
**Graph advantage**: Entity→birthplace→abolition is a classic multi-hop chain.
**Why both failed**: Gold is 918 (very early). GraphRAG said 1795, baseline said 1974. Both found modern dates, not the medieval one. The birthplace might be the Kingdom of Mercia (abolished 918).
**Diagnosis plan**: Check if "Lady Godiva" → birthplace edge exists. Check if birthplace links to an "abolished" date. Key: the chain is Lady Godiva → Mercia → abolished 918.

### 3. 4hop2__71753_648517_70784_79935 — "When was the region immediately north of..." (Israel + Battle of Qurah)
**Chain**: Israel → region (Middle East) → north of that → Battle of Qurah location → when created
**Entities needed**: Israel, Middle East, the specific northern region, Battle of Qurah, Umm al Maradim
**Graph advantage**: Multi-hop geographic reasoning — graph edges encode "north of" and "located in" relationships.
**Why both failed**: 4-hop, complex geographic reasoning. Both got close (1961, 1967 vs 1930). The chain is long and ambiguous.
**Diagnosis plan**: This is the hardest type. Check if geographic containment edges exist.

### 4. 4hop1__152562_5274_458768_33633 — "When did the explorer reach the city where..."
**Chain**: Vilaiyaadu Mankatha → record label → larger group → HQ city → explorer who reached it → when
**Entities needed**: Vilaiyaadu Mankatha, its record label, the parent group, the HQ city, the explorer
**Graph advantage**: Long chain where each hop narrows to a specific entity.
**Why both failed**: 4-hop, the chain involves an obscure Tamil film song. Very specific knowledge.
**Diagnosis plan**: Check if "Vilaiyaadu Mankatha" entity exists at all.

### 5. 3hop1__305282_282081_73772 — "When was the start of the battle of the birthplace of the performer of III?"
**Chain**: III (song/album) → performer → birthplace → battle of that place → start date
**Entities needed**: "III" (ambiguous — many things named III), its performer, performer's birthplace, the battle
**Graph advantage**: If "III" is linked to its performer, the chain follows. Gold is Dec 14, 1814 — Battle of New Orleans area.
**Why both failed**: GraphRAG got Jan 8 1815 (close! that's the main battle date, but the gold wants Dec 14 1814 which is when it started). This is a near-miss — the agent found the right battle but picked the wrong date within it.
**Diagnosis plan**: This might improve with the prompt's date guidance. The old prompt had "pick the earliest date in a range."

### 6. 2hop__655505_110949 — "What is the Till dom ensamma performer's birth date?"
**Chain**: "Till dom ensamma" (Swedish song) → performer → birth date
**Entities needed**: "Till dom ensamma", the performer (Pernilla Wahlgren based on GraphRAG's pred)
**Graph advantage**: Simple 2-hop if the song→performer edge exists.
**Why both failed**: GraphRAG found the performer name (Pernilla Wahlgren) but returned the name instead of the birth date! This is an answer synthesis error, not a retrieval error. The agent had the right entity but didn't complete the second hop.
**Diagnosis plan**: Check if Pernilla Wahlgren's birth date (11 Sep 1962) is in a retrievable chunk. If yes, this is a pure synthesis fix — the agent just needs to do one more step.

### 7. 4hop3__754156_88460_30152_20999 — "How were the people from whom new coins were..."
**Chain**: Somali Ajuran Empire → coins/independence → expelled people → country between Thailand and A Lim's country → how expelled
**Entities needed**: Ajuran Empire, Portuguese (expelled), the country (Malaysia/Myanmar?), the expulsion method
**Graph advantage**: Very complex multi-hop with indirect references.
**Why both failed**: 4-hop with obscure references. Baseline gave up. GraphRAG got a wrong answer.
**Diagnosis plan**: Check if "Ajuran Empire" and "Portuguese" entities exist with relationship.

### 8. 2hop__199513_801817 — "What is the birthplace of the person after whom São José dos Campos was named?"
**Chain**: São José dos Campos → named after (Saint Joseph) → birthplace (Nazareth)
**Entities needed**: "São José dos Campos", "Saint Joseph"/"Joseph", "Nazareth"
**Graph advantage**: If the graph has the naming relationship, this is straightforward.
**Why both failed**: Both said Bethlehem or Jerusalem — common biblical geography confusion. The corpus text probably mentions Nazareth as Joseph's birthplace but all three answers are plausible associations.
**Diagnosis plan**: Check if the chunk text specifically says "Nazareth" as Joseph's birthplace. If it does, this is a retrieval precision issue.

## Summary: Expected Failure Families

| Family | Count | Questions |
|--------|-------|-----------|
| **Answer synthesis** (right entity, wrong final answer) | 3 | #5 (near-miss date), #6 (returned name not date), #1 (close year) |
| **Chain too long** (4+ hops, obscure entities) | 3 | #3, #4, #7 |
| **Entity resolution** (right concept, wrong specific fact) | 2 | #2 (wrong century), #8 (biblical geography) |

## Key Insight

3 of 8 failures are NOT retrieval failures — the agent found the right entities but synthesized the wrong answer. These should improve with:
- The v2.0 prompt's grounding emphasis ("quote from source text")
- The "pick earliest date" guidance (question #5)
- The retry strategies (question #6 — one more hop would solve it)

The remaining 5 may need better graph coverage (passage nodes helping with entity co-occurrence) or are genuinely hard 4-hop questions.
