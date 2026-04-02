# Oracle Diagnostic Report

**Date**: 2026-04-02 05:17
**Questions analyzed**: 14

## Failure Family Summary

| Family | Count | Fix Class | Description |
|--------|-------|-----------|-------------|
| **QUERY_FORMULATION** | 5 | routing, harness, retrieval_config | Right tool, wrong query — answer in corpus but query didn't match |
| **CONTROL_FLOW** | 3 | routing, harness | Atom lifecycle issue — early stopping, stagnation, repeated queries |
| **INTERMEDIATE_ENTITY_ERROR** | 3 | harness, retrieval_config, corpus | Unknown |
| **TOOL_SELECTION** | 1 | retrieval_config | Answer findable by simpler tool, agent used complex one |
| **RETRIEVAL_RANKING** | 1 | retrieval_config | Right tool and query, answer in results but ranked too low or not selected |
| **ANSWER_SYNTHESIS** | 1 | routing | Agent retrieved correct evidence but extracted wrong answer |

## Optimal Strategy Summary

- **vdb_search**: 7 questions
- **text_search**: 7 questions

## Per-Question Diagnosis

### 3hop1__9285_5188_23307

**Question**: What month did the Tripartite discussions begin between Britain, France, and the country where, despite being headquartered in the nation called the nobilities commonwealth, the top-ranking Warsaw Pact operatives originated?
**Gold**: mid-June
**Predicted**: June
**Family**: `CONTROL_FLOW` (high) — source: llm
**Heuristic said**: `ANSWER_SYNTHESIS` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Decompose the question to identify the 'country where the top-ranking Warsaw Pact operatives originated' and the 'nation called the nobilities commonwealth'. 2. Use `chunk_retrieve(semantic, 'nation called the nobilities commonwealth')` to identify Poland. 3. Use `chunk_retrieve(semantic, 'country where top-ranking Warsaw Pact operatives originated')` to identify USSR. 4. Realize Poland and USSR are distinct and the question implies they refer to the same entity, which is a contradiction. Re-evaluate based on the phrase 'despite being headquartered in the nation called the nobilities commonwealth'. This suggests the country where operatives originated is *not* the nobilities commonwealth, but the latter is its headquarters nation. 5. Identify Poland as the 'nation called the nobilities commonwealth' using `chunk_retrieve(semantic, 'nobilities commonwealth')`. 6. Identify the country where Warsaw Pact operatives originated by searching for information related to Warsaw Pact and its origins, or by using entity search on Warsaw Pact and traversing relationships. A likely query would be `chunk_retrieve(semantic, 'Warsaw Pact operatives originated')`. This would ideally lead to information about countries associated with the Warsaw Pact, and potentially the *origin* of operatives. Given the context, and the provided gold answer's reference to 'Molotov–Ribbentrop Pact', the intent is likely to find a country strongly associated with the Warsaw Pact. If Poland is the headquarters, and the question asks about where *originates*, it might be a different country or a nuance of Poland. 7. The crucial piece is that Tripartite discussions are between Britain, France, and *that country*. The question is poorly phrased, implying the 'country where operatives originated' is the *same* country as the 'nation called the nobilities commonwealth'. The optimal path involves recognizing this ambiguity or contradiction and prioritizing the 'nation called the nobilities commonwealth' as the subject of the Tripartite talks. 8. Once Poland is identified as the target country for the Tripartite discussions, use `chunk_retrieve(semantic, 'Tripartite discussions Britain France Poland start month')` to find the answer. The gold answer chunk states: "In mid-June, the main Tripartite negotiations started."
**Divergence**: Tool call [22] which resulted in a ValueError: 'TODO 'a3' cannot be marked done with 'Soviet Union'. Current evidence supports 'Poland' instead.'. This indicates a control flow issue where the agent incorrectly resolved 'a3' and then failed to correct it or submit the correct answer based on its findings.
**Root cause**: The agent incorrectly processed the relationship between 'nobilities commonwealth' and the country of origin for Warsaw Pact operatives, leading to a control flow error in marking intermediate entities as resolved.
**Fix**: [routing] Improve the agent's ability to handle ambiguous or contradictory information in the question, particularly when entities are described with conflicting attributes. Implement a more robust mechanism for the agent to re-evaluate intermediate entity resolutions when subsequent steps reveal inconsistencies.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Molotov–Ribbentrop Pact (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): commonwealth → united states → new jersey → j
- **Agent**: 10 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 3, 'chunk_retrieve': 4, 'reason': 1, 'submit_answer': 1}
  - Queries: ['What month did the Tripartite discussions begin be']

### 2hop__511454_120259

**Question**: When was Lady Godiva's birthplace abolished?
**Gold**: 918
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question into 'Where was Lady Godiva born?' and 'When was that birthplace abolished?'. 2. To find Lady Godiva's birthplace, use `entity_search(semantic, 'Lady Godiva')` or `chunk_retrieve(text, 'Lady Godiva birthplace')` to find text or entities related to her birth. 3. Once Lady Godiva's birthplace is identified as Mercia, use `entity_search(semantic, 'Mercia abolished')` or `chunk_retrieve(text, 'Mercia abolition date')` to find when Mercia ceased to exist. 4. Alternatively, if Mercia is identified as an entity in the graph, use `entity_info(profile, 'Mercia')` to find its historical end date or use `entity_traverse(onehop, 'Mercia')` to find related entities that might lead to its abolition date. 5. Finally, use `reason(answer, context)` to synthesize the date from the retrieved information.
**Divergence**: Tool call #7: `entity_search({'query': 'Mercia abolished', 'method': 'semantic', 'top_k': '10'})`. The agent correctly identified Mercia as the birthplace and then searched for its abolition. However, the search results were not directly relevant, and the agent did not have a fallback or strategy to use other tools like `chunk_retrieve` with the correct keywords or to explore graph connections related to Mercia's end.
**Root cause**: The agent failed to effectively bridge the entity 'Mercia' to its abolition date, either by formulating a better query for `entity_search`/`chunk_retrieve` or by utilizing graph traversal tools to find the relevant historical information.
**Fix**: [retrieval_config] Improve the query formulation for semantic searches targeting historical entities and events, possibly by adding temporal or event-related keywords (e.g., 'Mercia end date', 'fall of Mercia', 'Mercia dissolved') or by adding a step to re-query with different keyword combinations if initial semantic searches fail to yield direct results.

- **Chunk search**: FOUND in 66 chunks
  - Chunk: The war to end war (content)
  - Chunk: Mercia (content)
- **Graph**: answer IN graph, 9 question entities found, 9 paths
  - Shortest path (2 hops): birthplace → colombia → iceland
- **Agent**: 7 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 2}
  - Queries: ["When was Lady Godiva's birthplace abolished?", 'Lady Godiva born', 'Lady Godiva']

### 4hop2__71753_648517_70784_79935

**Question**: When was the region immediately north of the region where Israel is located and the location of the Battle of Qurah and Umm al Maradim created?
**Gold**: 1930
**Predicted**: (empty)
**Family**: `TOOL_SELECTION` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question into sub-questions: a) What is the region immediately north of Israel? b) What is the location of the Battle of Qurah and Umm al Maradim? c) When was the region identified in (a) and the location identified in (b) created? 
2. For sub-question a), use `chunk_retrieve(semantic, 'region north of Israel')` to find entities like 'Syria' or 'Lebanon'.
3. For sub-question b), use `chunk_retrieve(semantic, 'location of Battle of Qurah and Umm al Maradim')` to find the specific location, likely in Jordan or Saudi Arabia, potentially requiring entity disambiguation.
4. Once both locations are identified, use `chunk_retrieve(text, 'When was [location from step 2] created?')` and `chunk_retrieve(text, 'When was [location from step 3] created?')`. The gold answer '1930' appears in chunks related to the creation of the Kingdom of Saudi Arabia, suggesting a connection to the region where the battle took place. The prompt implies the *creation* date of these regions, not necessarily their first mention. Therefore, a targeted text search using keywords like 'created', 'established', 'founded' for the identified locations and their historical context would be most effective.
5. The provided gold answer suggests that the relevant creation date (1930) is associated with the establishment of the Kingdom of Saudi Arabia. This implies that the region of the Battle of Qurah and Umm al Maradim is the key to finding the creation date.
**Divergence**: The agent failed to effectively use `chunk_retrieve` tools and instead relied heavily on graph-based tools (`entity_search`, `entity_traverse`, `relationship_search`). It identified 'the levant' as the region for Israel but did not proceed to find the region *north* of it effectively. It also struggled to find the location of the battle. Crucially, it never attempted a text search for the creation date.
**Root cause**: The agent prematurely prioritized graph traversal over simpler text retrieval for finding geographic entities and their associated creation dates, failing to leverage the corpus's textual evidence where the answer was explicitly stated.
**Fix**: [retrieval_config] Prioritize `chunk_retrieve(semantic, ...)` and `chunk_retrieve(text, ...)` for geographic and temporal fact retrieval. Agents should be guided to attempt direct text retrieval first for questions involving explicit dates or known entities that have textual descriptions, before resorting to graph traversal.

- **Chunk search**: FOUND in 86 chunks
  - Chunk: History of Saudi Arabia (content)
  - Chunk: Swimming at the Commonwealth Games (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): umm al maradim → iraq → england → arsenal
- **Agent**: 8 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'entity_info': 1, 'entity_traverse': 1, 'relationship_search': 1}
  - Queries: ['When was the region immediately north of the regio', 'Israel region', 'Battle of Qurah and Umm al Maradim location']

### 4hop1__94201_642284_131926_89261

**Question**: Where does the body of water by the city where the Southeast Library designer died empty into the Gulf of Mexico?
**Gold**: the Mississippi River Delta
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: 1. Identify the designer of the Southeast Library. 2. Find the city where the designer died. 3. Identify the body of water associated with that city. 4. Determine which body of water empties into the Gulf of Mexico. The final answer requires connecting the Mississippi River (associated with Minneapolis) to the Gulf of Mexico.
**Divergence**: Tool call [8]: entity_search(semantic, query='Minneapolis river Gulf of Mexico'). This query is too broad and unfocused. It resulted in entities like 'minneapolis saint paul minnesota' which don't directly help identify the river or its destination.
**Root cause**: The agent failed to effectively query for the specific body of water associated with Minneapolis that leads to the Gulf of Mexico after identifying Minneapolis as the death city.
**Fix**: [retrieval_config] Improve the agent's strategy for formulating downstream queries. After identifying Minneapolis, it should prioritize searching for rivers or bodies of water *in* Minneapolis, and then check their destination. For example, a more targeted subsequent query could be 'rivers in Minneapolis' followed by 'destination of Mississippi River'.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Mississippi River (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): southeast library → ralph rapson → minnesota → mississippi river
- **Agent**: 8 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 2, 'entity_info': 1}
  - Queries: ['Where does the body of water by the city where the', 'Southeast Library designer', 'Ralph Rapson death place']

### 4hop1__152562_5274_458768_33633

**Question**: When did the explorer reach the city where the headquarters of the only group larger than Vilaiyaadu Mankatha's record label is located?
**Gold**: August 3, 1769
**Predicted**: (empty)
**Family**: `CONTROL_FLOW` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Identify 'Vilaiyaadu Mankatha's record label using entity_search or relationship_search. 2. Find the group larger than that record label using relationship_search or entity_search. 3. Find the headquarters city of that larger group using entity_info or relationship_search. 4. Find the explorer and date associated with that city using chunk_retrieve.
**Divergence**: Tool call #25 - The agent incorrectly marked atom A1 as unresolved and failed to advance due to an apparent misunderstanding of the 'completed' status, despite `entity_search` in tool call #5 resolving 'Vilaiyaadu Mankatha' to 'Sony Music Entertainment'. This blocked further progress on identifying the larger group and its headquarters.
**Root cause**: The agent's control flow mechanism for marking atoms as resolved or unresolved was flawed, leading to a premature stop despite having sufficient information to identify intermediate entities.
**Fix**: [harness] Refine the atom lifecycle management in the agent's harness to correctly interpret successful entity resolution and allow progression even if exact text matches for specific sub-questions are not immediately found, as long as the core entity is identified and can be used for subsequent steps.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Santa Monica, California (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): vilaiyaadu mankatha → sony music entertainment → united states → us
- **Agent**: 12 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 2, 'entity_search': 3, 'chunk_retrieve': 2, 'relationship_search': 2, 'reason': 1, 'entity_info': 1}
  - Queries: ['When did the explorer reach the city where the hea', 'Vilaiyaadu Mankatha record label', 'Vilaiyaadu Mankatha']

### 3hop1__305282_282081_73772

**Question**: When was the start of the battle of the birthplace of the performer of III?
**Gold**: December 14, 1814
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Decompose the question: 'Who is the performer of III?', 'Where is the birthplace of that performer?', 'What battle occurred at that birthplace?', 'When did that battle start?'. 2. For 'Who is the performer of III?', search for entities related to 'III' and identify its performer. The entity search for 'iii' (string match) correctly identified it as an album by Stanton Moore. Use `entity_info` or `chunk_retrieve` with 'Stanton Moore' to find his related works or information about 'III'. 3. Once Stanton Moore is identified as the performer associated with 'III', find his birthplace. Use `entity_search` for 'Stanton Moore's birthplace' or `entity_info` and then `entity_search` for the birthplace. 4. Once the birthplace is identified (e.g., New Orleans), use `entity_search` or `chunk_retrieve` with the birthplace name and 'battle' to find relevant battles. 5. Once the battle (Battle of New Orleans) is identified, use `chunk_retrieve` with the battle name and 'start date' or similar to find the start date.
**Divergence**: Tool call [3] `entity_search(semantic, query='III performer')` and subsequent calls [4] `chunk_retrieve(text, query_text='III performer')`. The initial semantic search for 'III performer' was too broad and did not directly yield the correct entity or information. The agent then correctly identified that 'III' itself might be the entity in call [5] `entity_search(string, query='III')`, which surfaced 'iii' as an album by Stanton Moore. However, it failed to pivot effectively to find information about Stanton Moore or his album 'III' to establish him as the 'performer'. Instead, it continued searching for 'iii album performer' semantically, which was also unfruitful.
**Root cause**: The agent struggled to correctly identify and link the entity 'III' to its performer, Stanton Moore, and then to his associated birthplace and events.
**Fix**: [retrieval_config] Improve the routing logic to better handle ambiguous entities like 'III'. When a string search for an entity like 'iii' (album) is successful, the system should prioritize searching for related entities (like the album's artist/performer) using `entity_info` or `relationship_search` before resorting to broad semantic searches on the original query terms.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Battle of New Orleans (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (4 hops): birthplace → colombia → united states → new jersey → b
- **Agent**: 7 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 2}
  - Queries: ['When was the start of the battle of the birthplace', 'III performer', 'III']

### 2hop__619265_45326

**Question**: How many episodes are in season 5 of the series with The Bag or the Bat?
**Gold**: 12
**Predicted**: (empty)
**Family**: `RETRIEVAL_RANKING` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Use `reason(decompose, ...)` to break the question into "What series is 'The Bag or the Bat' in?" and "How many episodes are in season 5 of that series?". 2. Use `entity_search(semantic, 'The Bag or the Bat')` or `chunk_retrieve(text, 'The Bag or the Bat')` to identify the series. The corpus indicates this is 'Ray Donovan'. 3. Use `entity_search(semantic, 'Ray Donovan season 5 episodes')` or `chunk_retrieve(text, 'Ray Donovan season 5 episodes')` to find the episode count for season 5. The gold answer is 12.
**Divergence**: Tool call [6] chunk_retrieve({'method': 'text', 'query_text': 'Ray Donovan season 5 episodes', 'top_k': '10', 'entity_names': "['Ray Donovan']"}) failed because the retrieved chunks discussed 'The Sopranos' and 'Heroes of Mandalore' instead of 'Ray Donovan'. This indicates a retrieval ranking or corpus issue where the query returned irrelevant documents, or the relevant document was not sufficiently ranked.
**Root cause**: The agent failed to retrieve accurate information for the second sub-question due to a combination of poor retrieval ranking and potentially irrelevant noisy results returned by the `chunk_retrieve` tool, even after identifying the correct series.
**Fix**: [retrieval_config] Improve the ranking algorithm for `chunk_retrieve` to better handle noisy queries with specific entity constraints, or implement a re-ranking step that filters out clearly irrelevant documents based on keywords from the entity search result ('Ray Donovan').

- **Chunk search**: FOUND in 1011 chunks
  - Chunk: FC Barcelona (content)
  - Chunk: FC Barcelona (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): the bag or the bat → showtime → england → messi
- **Agent**: 8 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 3}
  - Queries: ['How many episodes are in season 5 of the series wi', 'The Bag or the Bat', 'Ray Donovan season 5 episodes']

### 4hop3__754156_88460_30152_20999

**Question**: How were the people from whom new coins were a proclamation of independence by the Somali Muslim Ajuran Empire expelled from the country between Thailand and A Lim's country?
**Gold**: The dynasty regrouped and defeated the Portuguese
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: The question asks about people related to the Ajuran Empire, their proclamation of independence via coins, and their expulsion from a country between Thailand and 'A Lim's country'. The optimal path would first identify the people associated with the Ajuran Empire and their coin proclamation. This could involve using `entity_search` for 'Ajuran Empire' and then `entity_info` or `relationship_search` to find related historical events or groups. Alternatively, a `chunk_retrieve(text, query)` with terms like 'Ajuran Empire coins independence' could directly find the relevant text. The gold answer 'The dynasty regrouped and defeated the Portuguese' suggests 'the Portuguese' are the expelled group. The key is to connect the Ajuran Empire to the Portuguese in the context of expulsion and independence. The corpus snippet shows 'The dynasty regrouped and defeated the Portuguese in 1613 and Siam in 1614', which directly links the Ajuran Empire (implied by 'the dynasty') to the Portuguese and a timeframe. The geographic part ('between Thailand and A Lim's country') seems to be a distractor or misinterpretation, as the answer relates to Myanmar and Siam. The agent should have prioritized grounding the historical actors and events (Ajuran Empire, coins, independence, expulsion, Portuguese) using `chunk_retrieve` or `entity_search` on these terms.
**Divergence**: Tool call [7] `chunk_retrieve({'method': 'text', 'query_text': 'Ajuran Empire new coins proclamation independence daimyos', 'top_k': '10'})` stated 'Atom a1 completed: Myanmar. Evidence refs: chunk_9813, chunk_4039. Advancing to a2.' This indicates a misinterpretation or premature completion of atom a1, and it seems to have incorrectly identified Myanmar as the answer to 'What country is between Thailand and A Lim's country?'. The subsequent calls like [9] `relationship_search` and [13] `chunk_retrieve` focused on 'Ajuran Empire' and eventually found 'the Portuguese' (Tool call [13]), but the initial geographic misstep and the subsequent focus on 'daimyos' (which is not in the gold answer or gold answer context) delayed and confused the retrieval process.
**Root cause**: The agent struggled to correctly interpret and ground the historical entities and events mentioned in the question, particularly by fixating on a geographically irrelevant sub-question and potentially misinterpreting candidate entities like 'daimyos'.
**Fix**: [routing] The routing logic for question decomposition needs to better prioritize grounding key historical entities and events before or in parallel with resolving potentially complex or ambiguous geographic constraints, especially when the geographic constraint doesn't seem to directly link to the core historical actors. If a geographic constraint is highly specific and doesn't align with initial entity searches, the system should flag it for review or try alternative interpretations of the geographic scope or the entities involved.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Myanmar (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): somali muslim ajuran empire → indian ocean → australia → group
- **Agent**: 13 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 2, 'entity_search': 5, 'chunk_retrieve': 3, 'relationship_search': 1, 'entity_info': 1}
  - Queries: ['How were the people from whom new coins were a pro', 'between Thailand Malaysia', 'A Lim country']

### 2hop__199513_801817

**Question**: What is the birthplace of the person after whom São José dos Campos was named?
**Gold**: Nazareth
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: The question asks for the birthplace of the person after whom São José dos Campos was named. First, identify the person: São José dos Campos is named after Saint Joseph. Then, find Saint Joseph's birthplace. The gold answer indicates Nazareth is the birthplace.
**Divergence**: Tool call [3] and [4]. The agent used entity_search and chunk_retrieve with queries like 'São José dos Campos named after' and 'São José dos Campos'. These queries were too broad or not specific enough to identify 'Saint Joseph' as the namesake, failing to connect the city to its namesake.
**Root cause**: The agent failed to identify the correct intermediate entity ('Saint Joseph') that links São José dos Campos to its namesake's birthplace due to ineffective query formulation for both entity and text retrieval.
**Fix**: [retrieval_config] Improve the keyword and semantic search queries to be more robust in identifying common namesakes, especially religious figures, and to better handle variations in entity names.

- **Chunk search**: FOUND in 6 chunks
  - Chunk: Sisters of St Joseph of Nazareth (content)
  - Chunk: Christian (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): the person → england → new zealand → the sisters of saint joseph of nazareth
- **Agent**: 7 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 1, 'entity_info': 1, 'relationship_search': 1}
  - Queries: ['What is the birthplace of the person after whom Sã', 'São José dos Campos named after', 'São José dos Campos']

### 3hop1__820301_720914_41132

**Question**: How many times did plague occur in the place where Crucifixion's creator died?
**Gold**: 22
**Predicted**: (empty)
**Family**: `CONTROL_FLOW` (high) — source: heuristic_fallback
**Optimal strategy**: text_search
**Fix**: [harness] Gold answer appeared in tool results but agent submitted empty/no answer. Likely atom lifecycle or submit_answer rejection issue.

- **Chunk search**: FOUND in 469 chunks
  - Chunk: FC Barcelona (content)
  - Chunk: FC Barcelona (content)
- **Graph**: answer IN graph, 10 question entities found, 6 paths
  - Shortest path (3 hops): crucifixion → christianity → england → messi
- **Agent**: 7 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 1, 'submit_answer': 1}
  - Queries: ['How many times did plague occur in the place where', 'Crucifixion creator', 'Ted Key location death']

### 3hop1__136129_87694_124169

**Question**: What year did the Governor of the city where the basilica named after the same saint as the one that Mantua Cathedral is dedicated to die?
**Gold**: 1952
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question into sub-questions: A1: What saint is Mantua Cathedral dedicated to? A2: What city is the basilica named after that saint located in? A3: Who is the Governor of that city? A4: What year did that Governor die?
2. For A1, use `entity_search(semantic, 'Mantua Cathedral dedication')` or `chunk_retrieve(text, 'Mantua Cathedral dedication')` to find it's dedicated to Saint Peter.
3. For A2, use `entity_search(semantic, 'basilica Saint Peter')` or `chunk_retrieve(text, 'basilica Saint Peter city')` to find that St. Peter's Basilica is in Rome.
4. For A3, use `entity_search(semantic, 'Governor of Rome')` to find that the Governor of Vatican City (which is in Rome) is Camillo Serafini.
5. For A4, use `entity_info(profile, 'Camillo Serafini')` or `chunk_retrieve(text, 'Camillo Serafini death year')` to find his death year is 1952.
**Divergence**: Tool call [3], entity_search(semantic, 'Mantua Cathedral dedicated to'). The query was too broad, returning entities like 'saint corbinian' instead of the correct 'saint peter' and thus failing to resolve A1.
**Root cause**: The agent's initial entity search queries for intermediate entities were not precise enough, leading to incorrect or unresolved intermediate steps and a failure to identify the correct path.
**Fix**: [harness] Refine the agent's default query generation for entity searches. When a question involves an entity with a specific attribute (like dedication), the system should favor queries that directly probe that attribute, e.g., 'Mantua Cathedral dedication' instead of 'Mantua Cathedral dedicated to'. Also, improve the semantic search to better distinguish between similar-sounding entities when disambiguation is needed.

- **Chunk search**: FOUND in 81 chunks
  - Chunk: Member states of NATO (content)
  - Chunk: Estádio do Arruda (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): mantua cathedral → italy → england → arsenal
- **Agent**: 11 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 3, 'entity_search': 3, 'chunk_retrieve': 3, 'submit_answer': 1}
  - Queries: ['What year did the Governor of the city where the b', 'Mantua Cathedral dedicated to', 'Mantua Cathedral']

### 2hop__354635_174222

**Question**: What company succeeded the owner of Empire Sports Network?
**Gold**: Time Warner Cable
**Predicted**: (empty)
**Family**: `ANSWER_SYNTHESIS` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question into: 'Who owned Empire Sports Network?' and 'What company succeeded the owner of Empire Sports Network?'. 2. Use `entity_search(semantic, 'Empire Sports Network owner')` or `chunk_retrieve(text, 'Empire Sports Network owner')` to find the owner. The gold answer states Adelphia Communications Corporation. 3. Use `relationship_search(graph, 'adelphia')` or `chunk_retrieve(text, 'Adelphia succeeded by company')` to find the successor. The gold answer indicates 'Time Warner Cable' acquired systems from bankrupt Adelphia.
**Divergence**: Tool call #5: `chunk_retrieve({'method': 'text', 'query_text': 'Adelphia succeeded by company', 'top_k': '5', 'entity_names': "['Adelphia Communications Corporation']"})` failed to find the successor because the query was too generic and didn't leverage the direct relationship hint from tool call #8. Tool call #8 `relationship_search({'method': 'graph', 'entity_ids': "['adelphia']", 'top_k': '10'})` successfully found 'time warner cable' in step [8] of the trace, but the agent did not act on this information to resolve atom a2. Instead, it continued to try text retrieval and entity search, failing to synthesize the answer from the available graph information.
**Root cause**: The agent failed to synthesize the answer from available graph data, prioritizing further text retrieval even after a direct graph relationship indicated the correct successor.
**Fix**: [routing] Modify the agent's routing logic to prioritize using information from graph traversal tools (like relationship_search) when it directly links entities relevant to subsequent sub-questions, especially when text-based retrieval struggles.

- **Chunk search**: FOUND in 2 chunks
  - Chunk: Windjammer Communications (content)
  - Chunk: Raleigh, North Carolina (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): empire sports network → new york → canada → war
- **Agent**: 8 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 2, 'entity_info': 1, 'relationship_search': 1}
  - Queries: ['What company succeeded the owner of Empire Sports ', 'Empire Sports Network owner', 'Adelphia successor company']

### 3hop1__849312_503371_21711

**Question**: When was the Palau de la Generalitat constructed in the city where Martin from the region where Perdiguera is located died?
**Gold**: built in the 15th century
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Identify the city where Martin from the region where Perdiguera is located died. This requires finding the region of Perdiguera (Aragon), then identifying 'Martin' associated with Aragon who died, and finally the city of his death. 2. Once the city is identified, find the construction date of the Palau de la Generalitat in that city.
**Divergence**: Tool call [7] chunk_retrieve({'method': 'semantic', 'query_text': 'Martin from Aragon died in city', 'top_k': '10', 'entity_names': "['Martin', 'Aragon']", 'document_collection_id': 'MuSiQue_chunks'}) failed because the corpus did not contain information about a 'Martin' from Aragon dying in a specific city, even though the question implies such a person exists and is relevant. The agent then incorrectly tried to search for 'Martin humane city died' in tool call [9] and [20].
**Root cause**: The agent failed to find the intermediate entity (Martin and his death city) because the available corpus lacked the necessary information, leading to a cascade of incorrect searches and an inability to bridge to the final answer.
**Fix**: [corpus] Augment the corpus with information linking historical figures (like Martin the Humane, if that was the intended subject) to their places of death, or add information that clarifies if such a person is not relevant to the corpus's scope.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Gothic architecture (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): palau de la generalitat → barcelona → england → 15th century
- **Agent**: 10 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'resources': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 3, 'relationship_search': 1}
  - Queries: ['When was the Palau de la Generalitat constructed i', 'Perdiguera region', 'Martin Aragon died city']

### 2hop__731956_126089

**Question**: Who was in charge of the place where Castricum is located?
**Gold**: Johan Remkes
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `RETRIEVAL_RANKING` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Use entity_search(semantic, 'Castricum') to find the entity for Castricum. 2. Use entity_traverse(onehop, 'Castricum') to find its direct neighbors. 3. Identify 'North Holland' as the administrative location from the neighbors. 4. Use entity_search(semantic, 'North Holland') or relationship_search('North Holland') to find related entities. 5. Use entity_traverse(onehop, 'North Holland') or entity_info('North Holland') to find the person in charge. The graph path shows 'Castricum' -> 'North Holland' -> 'Johan Remkes', suggesting a traversal approach is best. Alternatively, after finding 'North Holland', a chunk_retrieve(text, 'Who was in charge of North Holland?') could work.
**Divergence**: Tool call [5] where entity_search(string, 'Castricum') completed atom a1 with 'the beach'. This incorrectly identified the administrative location and prevented the agent from proceeding to find the person in charge of 'North Holland'. The agent should have used the results from the earlier semantic search and graph traversal for atom a1, specifically the 'north holland' neighbor.
**Root cause**: The agent incorrectly identified 'the beach' as the administrative location for Castricum, likely due to a misinterpretation of the entity_search results, which caused it to fail to connect to the correct administrative region and its leader.
**Fix**: [harness] The agent's control flow needs to be improved to better handle ambiguous or incorrect intermediate entity resolutions. It should prioritize graph traversal results for location-based sub-questions when semantic searches yield plausible but incorrect entities, and it should have a mechanism to re-evaluate or backtrack if subsequent steps lead to dead ends or nonsensical results.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: North Holland (content)
- **Graph**: answer IN graph, 8 question entities found, 6 paths
  - Shortest path (2 hops): castricum → north holland → johan remkes
- **Agent**: 6 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'entity_traverse': 1}
  - Queries: ['Who was in charge of the place where Castricum is ', 'Castricum', 'Castricum North Holland']
