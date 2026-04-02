# Oracle Diagnostic Report

**Date**: 2026-04-01 19:49
**Questions analyzed**: 17

## Failure Family Summary

| Family | Count | Fix Class | Description |
|--------|-------|-----------|-------------|
| **QUERY_FORMULATION** | 9 | prompt, retrieval_config, harness | Right tool, wrong query — answer in corpus but query didn't match |
| **INTERMEDIATE_ENTITY_ERROR** | 6 | routing, harness, graph, retrieval_config | Unknown |
| **CONTROL_FLOW** | 1 | harness | Atom lifecycle issue — early stopping, stagnation, repeated queries |
| **RETRIEVAL_RANKING** | 1 | corpus | Right tool and query, answer in results but ranked too low or not selected |

## Optimal Strategy Summary

- **text_search**: 9 questions
- **vdb_search**: 8 questions

## Per-Question Diagnosis

### 2hop__13548_13529

**Question**: When was the person who Messi's goals in Copa del Rey compared to get signed by Barcelona?
**Gold**: June 1982
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question: 'When was the person who Messi's goals in Copa del Rey compared to get signed by Barcelona?' into sub-questions. The primary sub-question is: 'Who is the person whose Copa del Rey goals are compared to Messi's?'. A secondary sub-question is: 'When was that person signed by Barcelona?'.
2. Execute `entity_search(semantic, 'Messi Copa del Rey goals comparison')` to identify the person. This should ideally return 'Diego Maradona'.
3. Once Diego Maradona is identified, use `entity_info(profile, 'diego maradona')` to get his description and relationships.
4. Alternatively, if the comparison is not directly stated in entity info, use `chunk_retrieve(text, 'Messi goals Copa del Rey Diego Maradona')` or `relationship_search(graph, 'diego maradona')` to confirm the comparison and find his signing date.
5. Once Diego Maradona is confirmed as the person, and their signing date by Barcelona is found, use `chunk_retrieve(text, 'Diego Maradona signed by Barcelona')` to find the date.
**Divergence**: Tool call [3] `chunk_retrieve` and subsequent calls like [4] `entity_search` and [5] `entity_info` failed to correctly identify Diego Maradona as the person whose goals were compared to Messi's. The agent's queries were too broad or poorly formulated for the available evidence. For instance, the `chunk_retrieve` query in [3] included 'signed by Barcelona' which is part of the second hop, not the first. The `entity_search` in [4] found 'diego maradona' but subsequent `entity_info` and `chunk_retrieve` calls failed to confirm the specific comparison context needed for A1.
**Root cause**: The agent failed to correctly formulate queries to establish the intermediate entity (the person compared to Messi) and then extract the specific fact about that entity's signing date.
**Fix**: [harness] Improve the agent's ability to break down multi-hop questions into distinct atomic steps and to formulate precise, context-aware queries for each step. Specifically, refine query generation for intermediate entity identification, ensuring that queries target the *comparison* aspect first before looking for signing details.

- **Chunk search**: FOUND in 2 chunks
  - Chunk: FC Barcelona (content)
  - Chunk: Lin Chih-chieh (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (1 hops): copa del rey → diego maradona
- **Agent**: 7 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'chunk_retrieve': 2, 'entity_search': 1, 'entity_info': 1, 'relationship_search': 1}
  - Queries: ["When was the person who Messi's goals in Copa del ", 'Messi Copa del Rey goals compared to Barcelona sig']

### 3hop1__9285_5188_23307

**Question**: What month did the Tripartite discussions begin between Britain, France, and the country where, despite being headquartered in the nation called the nobilities commonwealth, the top-ranking Warsaw Pact operatives originated?
**Gold**: mid-June
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Decompose the question into: a) Identify 'the country where, despite being headquartered in the nation called the nobilities commonwealth, the top-ranking Warsaw Pact operatives originated'. b) Identify the start month of the Tripartite discussions between Britain, France, and this country. 2. For step 1a: Use entity_search to find entities related to 'nobilities commonwealth' and 'Warsaw Pact origin country'. Use entity_info on the commonwealth entity to confirm it's the Polish–Lithuanian Commonwealth. Then, use relationship_search or entity_search with 'Poland' to confirm it's the origin country. 3. For step 1b: Use chunk_retrieve(semantic, 'Tripartite discussions Britain France Poland start month') to find the date. 4. If found, use reason(answer, context) to synthesize the final answer.
**Divergence**: Tool call [6]: chunk_retrieve(method='text', query_text='Tripartite discussions Britain France Poland began month', top_k='5'). The agent used a text retrieval query for atom3, but the optimal strategy would have been to use semantic chunk retrieval given the nuance of 'Tripartite discussions' potentially being ambiguous and requiring understanding of context rather than exact keyword match. It also failed to leverage the fact that 'Poland' was identified in a previous step, which could have been used to narrow down the search.
**Root cause**: The agent failed to correctly identify and retrieve the specific information about the Tripartite discussions after identifying the involved country, likely due to a combination of suboptimal query formulation for text retrieval and not leveraging previously identified entities effectively.
**Fix**: [retrieval_config] Improve the default strategy for text retrieval when dealing with multi-hop questions. When an intermediate entity is resolved (e.g., 'Poland'), the system should automatically incorporate this entity into subsequent retrieval queries for related facts, possibly by reformulating queries or prioritizing semantic search over keyword search for more abstract concepts like 'discussions'.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Molotov–Ribbentrop Pact (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): commonwealth → united states → new jersey → j
- **Agent**: 10 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 2, 'chunk_retrieve': 3, 'entity_search': 2, 'entity_info': 1, 'submit_answer': 1}
  - Queries: ['What month did the Tripartite discussions begin be', 'nobilities commonwealth Warsaw Pact headquarters o', 'Tripartite discussions Britain France Poland']

### 2hop__170823_120171

**Question**: What year did the publisher of Labyrinth end?
**Gold**: 1986
**Predicted**: (empty)
**Family**: `CONTROL_FLOW` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: 1. Use `reason(decompose, 'What year did the publisher of Labyrinth end?')` to break the question into sub-questions. 2. Identify 'Labyrinth' using `entity_search(semantic, 'Labyrinth')` or `chunk_retrieve(text, 'Labyrinth')`. 3. Once 'Labyrinth' is identified as 'Pan's Labyrinth', find its publisher using `chunk_retrieve(text, "publisher of Pan's Labyrinth")` or `entity_info(profile, 'Pan\'s Labyrinth')` to find relationships to publishers. 4. Identify the publisher as 'Acornsoft'. 5. Find the end year of 'Acornsoft' using `chunk_retrieve(text, 'Acornsoft end year')` or `entity_info(profile, 'Acornsoft')` to find its description or relationships, and extract the year.
**Divergence**: Tool call [18]: The agent called `entity_search(string, 'Acornsoft')`. This call successfully identified 'Acornsoft' (organization) as a potential entity. However, the agent then failed to proceed to find the end year of Acornsoft. Instead, it entered a stagnation loop and submitted an empty answer.
**Root cause**: The agent successfully identified the publisher 'Acornsoft' but failed to retrieve and synthesize the final piece of information (its end year) before reaching a system-imposed stagnation limit.
**Fix**: [harness] Adjust the stagnation detection logic or the maximum number of allowed turns for questions requiring multiple retrieval steps, especially when intermediate entities are found but the final piece of information is still missing.

- **Chunk search**: FOUND in 138 chunks
  - Chunk: Ferdinand Daučík (content)
  - Chunk: Acornsoft (content)
- **Graph**: answer IN graph, 6 question entities found, 9 paths
  - Shortest path (4 hops): labyrinth → 1984 → league → atl tico madrid → ferdinand dau  k
- **Agent**: 7 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 2}
  - Queries: ['What year did the publisher of Labyrinth end?', 'Labyrinth', "Pan's Labyrinth"]

### 2hop__511454_120259

**Question**: When was Lady Godiva's birthplace abolished?
**Gold**: 918
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: 1. Use `reason(decompose, 'When was Lady Godiva's birthplace abolished?')` to break the question into sub-questions. Expected sub-question 1: 'What was Lady Godiva's birthplace?'. 2. Use `entity_search(semantic, 'Lady Godiva')` to find the entity for Lady Godiva. 3. Use `entity_info(profile, 'Lady Godiva')` to find her birthplace entity. 4. If the birthplace is an entity, use `entity_info(profile, birthplace_entity)` to get its description and relationships. If the birthplace is a string (e.g., a place name), use `chunk_retrieve(text, 'abolition of [birthplace name]')` or `chunk_retrieve(semantic, 'abolition of [birthplace name]')` to find relevant information about its abolition. If the question implies a historical event tied to a specific year, `chunk_retrieve(text, '918')` should be used given the gold answer is '918'.
**Divergence**: Tool call [4] chunk_retrieve({'method': 'semantic', 'query_text': 'Lady Godiva birthplace', 'top_k': '5'}) failed because the query was too broad and did not directly address the 'abolition' aspect. Tool call [6] chunk_retrieve({'method': 'by_ids', 'top_k': '5', 'chunk_ids': "['chunk_472']"}) failed because it retrieved information about Lady Godiva's life, not the abolition of her birthplace. The agent never specifically searched for the year '918' in conjunction with the concept of abolition or the birthplace.
**Root cause**: The agent failed to formulate queries that directly targeted the temporal aspect ('abolished') and the specific year ('918') related to the birthplace, instead focusing too much on identifying the birthplace itself.
**Fix**: [retrieval_config] Enhance the query reformulation logic to prioritize temporal aspects and numerical year searches when keywords like 'when' or 'abolished' are present in the question. Specifically, if a year is found in the gold answer, try to retrieve chunks containing that year along with keywords from the question.

- **Chunk search**: FOUND in 66 chunks
  - Chunk: The war to end war (content)
  - Chunk: Mercia (content)
- **Graph**: answer IN graph, 9 question entities found, 9 paths
  - Shortest path (2 hops): birthplace → colombia → iceland
- **Agent**: 7 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 2}
  - Queries: ["When was Lady Godiva's birthplace abolished?", 'Lady Godiva birthplace', 'Godiva Countess of Leicester birthplace']

### 4hop2__71753_648517_70784_79935

**Question**: When was the region immediately north of the region where Israel is located and the location of the Battle of Qurah and Umm al Maradim created?
**Gold**: 1930
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Identify the region where Israel is located using `entity_search(semantic, 'Israel')`. 2. Find the region immediately north of Israel using `entity_traverse(onehop, <Israel_region_entity>)` or `chunk_retrieve(semantic, 'region north of Israel')`. 3. Identify the location of the Battle of Qurah and Umm al Maradim using `entity_search(semantic, 'Battle of Qurah and Umm al Maradim')`. 4. Determine the overlap or common region between the result of step 2 and step 3. 5. Search for the creation date of this overlapping region using `chunk_retrieve(text, 'creation date of <region_name>')` or `entity_info(profile, <region_name>)`.
**Divergence**: Tool call #3: entity_search({'query': 'region where Israel is located', 'method': 'semantic', 'top_k': '5'}) which returned irrelevant results like 'western europe latin america and north america' and 'southern district of israel'. This indicates a failure in correctly identifying the region associated with Israel semantically.
**Root cause**: The agent failed to correctly identify the geographical region associated with Israel, leading to subsequent incorrect retrieval steps.
**Fix**: [retrieval_config] Improve the semantic search embedding model or fine-tune it for geographical entity recognition, particularly for political and historical regions, to better distinguish between Israel and unrelated or too-broad geographical areas.

- **Chunk search**: FOUND in 86 chunks
  - Chunk: History of Saudi Arabia (content)
  - Chunk: Swimming at the Commonwealth Games (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): umm al maradim → iraq → england → arsenal
- **Agent**: 7 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 4, 'chunk_retrieve': 1}
  - Queries: ['When was the region immediately north of the regio', 'region where Israel is located', 'Battle of Qurah and Umm al Maradim']

### 4hop1__94201_642284_131926_89261

**Question**: Where does the body of water by the city where the Southeast Library designer died empty into the Gulf of Mexico?
**Gold**: the Mississippi River Delta
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Use `entity_search(semantic, 'Southeast Library designer')` to find Ralph Rapson. 2. Use `entity_info(profile, 'Ralph Rapson')` to find the city where he died (Minneapolis). 3. Use `entity_search(semantic, 'body of water in Minneapolis')` to find the Mississippi River. 4. Use `chunk_retrieve(semantic, 'Mississippi River empty into Gulf of Mexico')` to find the Mississippi River Delta.
**Divergence**: Tool call 3: `entity_search({'query': 'Southeast Library designer died city', 'method': 'semantic', 'top_k': '5'})` failed to identify Ralph Rapson as the designer and incorrectly focused on the city where he died, leading to a dead end.
**Root cause**: The agent's initial entity resolution for the 'Southeast Library designer' was too broad and did not effectively identify the correct intermediate entity, leading to a cascade of incorrect searches.
**Fix**: [harness] Improve the agent's ability to resolve ambiguous entity names by prioritizing more specific entity types and relationship types in the initial search queries, and potentially adding a disambiguation step if multiple plausible entities are returned.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Mississippi River (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): southeast library → ralph rapson → minnesota → mississippi river
- **Agent**: 7 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 1, 'entity_info': 1}
  - Queries: ['Where does the body of water by the city where the', 'Southeast Library designer died city', 'Southeast Library designer']

### 4hop1__152562_5274_458768_33633

**Question**: When did the explorer reach the city where the headquarters of the only group larger than Vilaiyaadu Mankatha's record label is located?
**Gold**: August 3, 1769
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: 1. Decompose the question: "When did the explorer reach the city where the headquarters of the only group larger than Vilaiyaadu Mankatha's record label is located?" into sub-questions. The key entities and relations are: 'Vilaiyaadu Mankatha', 'record label', 'group larger than', 'headquarters', 'city', 'explorer', 'date'.
2. Find Vilaiyaadu Mankatha's record label: Use `entity_search` or `relationship_search` on 'Vilaiyaadu Mankatha' to find its record label. The gold answer is 'Sony Music Entertainment'.
3. Find the group larger than Vilaiyaadu Mankatha's record label: This is the most challenging part. The question implies a comparison of group sizes. The agent needs to find entities related to 'Sony Music Entertainment' and then search for information about other groups, specifically identifying one that is 'larger'. This step likely requires `entity_search` or `chunk_retrieve` using terms like 'Sony Music Entertainment group size', 'largest music group', etc. The gold answer implies this larger group's headquarters is in Santa Monica.
4. Find the headquarters city of that group: Once the larger group is identified, find its headquarters. For example, if 'Sony Music Entertainment' is the larger group, find its headquarters city. The gold path implies Santa Monica is the headquarters city.
5. Find the explorer and date associated with that city: Once the city (Santa Monica) is identified, find information about explorers reaching it and the date. The gold answer 'August 3, 1769' is found in the corpus related to Santa Monica and explorer Gaspar de Portolà.
**Divergence**: Tool call #15: `chunk_retrieve({'method': 'semantic', 'query_text': '"only group larger than" "Sony Music Entertainment" group', 'top_k': '10'})`. The agent attempted to find the larger group but failed because the query was too specific and the necessary comparative information was likely not indexed or retrievable with that exact phrasing. The subsequent steps to find the city and date were not reached.
**Root cause**: The agent failed to effectively identify the intermediate entity representing the 'only group larger than Vilaiyaadu Mankatha's record label' due to a poorly formulated query that did not match available evidence for this comparative fact.
**Fix**: [retrieval_config] Improve the agent's ability to handle comparative queries. This could involve: 1) Enhancing the semantic search index to better capture comparative statements. 2) Developing a more robust query formulation strategy that tries variations of comparative phrases (e.g., 'largest music group', 'top music labels by size', 'music groups by revenue', etc.) when initial attempts fail. 3) Augmenting the graph with explicit 'size' or 'rank' properties for entities like record labels.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Santa Monica, California (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): vilaiyaadu mankatha → sony music entertainment → united states → us
- **Agent**: 12 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'resources': 1, 'todo_write': 2, 'chunk_retrieve': 3, 'entity_search': 3, 'relationship_search': 1, 'entity_traverse': 1}
  - Queries: ['When did the explorer reach the city where the hea', 'Vilaiyaadu Mankatha record label', 'Vilaiyaadu Mankatha']

### 3hop1__305282_282081_73772

**Question**: When was the start of the battle of the birthplace of the performer of III?
**Gold**: December 14, 1814
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (medium) — source: heuristic_fallback
**Optimal strategy**: vdb_search
**Fix**: [prompt] Answer is in 1 chunks but agent's queries (['When was the start of the battle of the birthplace of the performer of III?', 'III performer', '"III" film performer']) didn't surface it. The queries may not match the chunk content.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Battle of New Orleans (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (4 hops): birthplace → colombia → united states → new jersey → b
- **Agent**: 8 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 3, 'entity_info': 1}
  - Queries: ['When was the start of the battle of the birthplace', 'III performer', '"III" film performer']

### 2hop__655505_110949

**Question**: What is the Till dom ensamma performer's birth date?
**Gold**: 11 September 1962
**Predicted**: 1962
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: The question asks for the birth date of the performer of 'Till dom ensamma'. The optimal path is to first identify the performer of 'Till dom ensamma' and then find their birth date. This can be achieved by using `entity_search(semantic, 'Till dom ensamma performer')` to find the performer's name, followed by `entity_info(profile, 'Mauro Scocco')` or `chunk_retrieve(text, 'Mauro Scocco birth date')` to get the birth date. The gold answer is found in a chunk directly mentioning 'Mauro Scocco (born 11 September 1962)'.
**Divergence**: Tool call [3] `entity_search(semantic, 'Till dom ensamma performer')` failed to return the correct entity. It returned generic terms like '14th song', 'swedish dansband competition', etc., instead of the performer's name, Mauro Scocco. Subsequently, tool call [4] `chunk_retrieve(text, 'Till dom ensamma performer birth date')` used a query that, while related, did not directly yield the full answer, retrieving only '1962' and the song title, missing the full date and the performer's name.
**Root cause**: The agent's entity search query for identifying the performer was too broad and failed to find the specific entity 'Mauro Scocco', which was crucial for linking to the birth date information.
**Fix**: [harness] Improve the entity search query formulation within the agent's retrieval strategy. Instead of relying solely on 'Till dom ensamma performer', consider a query that specifically targets known entities related to songs or performers, such as 'artist of Till dom ensamma' or if an intermediate step identifies 'Till dom ensamma' as a song, then search for 'performer of song Till dom ensamma'. Alternatively, use a more robust method for entity disambiguation or entity linking for the identified song.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Mauro Scocco (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (4 hops): till dom ensamma → mauro scocco → united states → new jersey → b
- **Agent**: 5 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 1, 'chunk_retrieve': 1, 'submit_answer': 1}
  - Queries: ["What is the Till dom ensamma performer's birth dat", 'Till dom ensamma performer']

### 2hop__619265_45326

**Question**: How many episodes are in season 5 of the series with The Bag or the Bat?
**Gold**: 12
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Use `reason(decompose, 'How many episodes are in season 5 of the series with The Bag or the Bat?')` to break down the question. 2. Atom a1: 'What series has "The Bag or the Bat" as one of its episodes?' should be resolved using `chunk_retrieve(text, query='"The Bag or the Bat" episode series')` to identify 'Ray Donovan'. 3. Atom a2: 'What is season 5 of Ray Donovan?' should be resolved by first identifying 'Ray Donovan' as an entity, then searching for information about its seasons. This would ideally involve `entity_info(profile, 'Ray Donovan')` to get general information and then a targeted search like `chunk_retrieve(text, query='Ray Donovan season 5 episodes')` or potentially `entity_search(semantic, query='Ray Donovan season 5')` if season entities are well-defined. 4. Atom a3: 'How many episodes are in season 5 of Ray Donovan?' should be answered by retrieving the episode count for 'Ray Donovan season 5' using `chunk_retrieve(text, query='Ray Donovan season 5 episode count')` or `relationship_search(graph, entity='Ray Donovan season 5')` if season information is linked. The gold answer '12' is present in the corpus.
**Divergence**: Tool call 5 and 6. The agent incorrectly identifies 'italy' as the resolution for 'season 5 of Ray Donovan' in tool call 6 (`entity_search(string, query='Ray Donovan season 5')`). This is likely due to poor string matching or entity resolution in the knowledge graph. The previous tool call 5 also failed to find relevant information, suggesting the search terms for Ray Donovan season 5 were not effective.
**Root cause**: The agent failed to correctly resolve intermediate entities, specifically 'season 5 of Ray Donovan', leading to incorrect search paths and failure to retrieve the target information.
**Fix**: [graph] Improve the entity resolution and linking for TV series seasons within the knowledge graph. Ensure that searches for entities like 'Ray Donovan season 5' correctly link to season-specific information rather than unrelated entities like geographical locations.

- **Chunk search**: FOUND in 1011 chunks
  - Chunk: FC Barcelona (content)
  - Chunk: FC Barcelona (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): the bag or the bat → showtime → england → messi
- **Agent**: 7 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'chunk_retrieve': 2, 'entity_search': 2, 'relationship_search': 1}
  - Queries: ['How many episodes are in season 5 of the series wi', 'The Bag or the Bat episode series', 'Ray Donovan season 5']

### 4hop3__754156_88460_30152_20999

**Question**: How were the people from whom new coins were a proclamation of independence by the Somali Muslim Ajuran Empire expelled from the country between Thailand and A Lim's country?
**Gold**: The dynasty regrouped and defeated the Portuguese
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: The question asks about people expelled from a country between Thailand and 'A Lim's country', where new coins were a proclamation of independence by the Somali Muslim Ajuran Empire. First, identify the 'people' and the context of 'new coins' and 'proclamation of independence' related to the Somali Muslim Ajuran Empire. This could be done using `chunk_retrieve(text, 'Somali Muslim Ajuran Empire coins proclamation of independence')`. This should surface 'the Portuguese'. Then, identify the country mentioned in relation to Thailand and 'A Lim's country'. The phrase 'A Lim's country' is ambiguous and likely requires entity search or linking. A `entity_search(semantic, 'A Lim country')` followed by `entity_info(profile, 'a lim')` could resolve this. Once 'Laos' is identified as the country, a final retrieval step would be `chunk_retrieve(text, 'Portuguese expelled from Laos')` to confirm the expulsion context. The gold answer is 'The dynasty regrouped and defeated the Portuguese', which is directly available in a chunk. Thus, the optimal path is primarily `chunk_retrieve` based, with entity resolution for geographical clarity.
**Divergence**: Tool call #4 (`chunk_retrieve({'method': 'text', 'query_text': "country between Thailand and A Lim's country", 'top_k': '5'})`) and subsequent entity resolution tools (#5, #6). The initial chunk retrieval for the country was too vague, and while 'A Lim's country' was eventually resolved to 'Laos' via entity search, the core question about the *expulsion* from that country by the identified 'people' (the Portuguese) was never adequately addressed by the retrieval strategy.
**Root cause**: The agent failed to connect the expelled entity (Portuguese) with the location (Laos) and the specific expulsion event due to a fragmented retrieval strategy that did not synthesize information across multiple successful but isolated retrievals.
**Fix**: [harness] The harness should prioritize synthesizing information from successful but seemingly disconnected retrievals. After identifying 'the Portuguese' (from a1) and 'Laos' (from a2), the harness should have automatically triggered a new query like `chunk_retrieve(text, 'Portuguese expelled from Laos')` to bridge the gap, rather than halting or producing fragmented results. The current control flow does not effectively combine results from different atoms when the overall question requires it.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Myanmar (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): somali muslim ajuran empire → indian ocean → australia → group
- **Agent**: 7 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'chunk_retrieve': 3, 'entity_search': 1, 'entity_info': 1}
  - Queries: ['How were the people from whom new coins were a pro', 'A Lim country']

### 2hop__199513_801817

**Question**: What is the birthplace of the person after whom São José dos Campos was named?
**Gold**: Nazareth
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: The question requires two main steps: first, identifying the person after whom São José dos Campos was named, and second, finding that person's birthplace. The optimal path would start by searching for the namesake of 'São José dos Campos'. Given that the name 'São José' is a common Portuguese name, and the city is named after a saint (Saint Joseph), a robust strategy would involve searching for 'São José dos Campos namesake' using `chunk_retrieve(semantic, ...)` or `entity_search(semantic, ...)` to identify the specific Saint Joseph. Once 'Saint Joseph' is identified as the namesake, the next step would be to search for 'Saint Joseph birthplace' using `entity_info(profile, 'Saint Joseph')` to retrieve his description and relationships, or `entity_search(semantic, 'Saint Joseph birthplace')` to directly find the information. The corpus indicates that the answer 'Nazareth' is available in chunks related to 'Jesus of Nazareth', implying the namesake is indeed Saint Joseph, Jesus's earthly father, who is traditionally associated with Nazareth. The graph reachability shows a path involving 'the sisters of saint joseph of nazareth', which further corroborates that Saint Joseph of Nazareth is the likely namesake.
**Divergence**: Tool call [3] `chunk_retrieve({'method': 'text', 'query_text': 'São José dos Campos named after person birthplace', 'top_k': '5'})` and subsequent calls [4] `entity_search({'query': 'São José dos Campos named after person', 'method': 'semantic', 'top_k': '5'})`, [5] `chunk_retrieve({'method': 'semantic', 'query_text': 'São José dos Campos was named after who', 'top_k': '5'})` and [6] `entity_search({'query': 'São José dos Campos', 'method': 'string', 'top_k': '10'})` failed to identify the namesake person. The agent's queries were too general or did not align with the content that identifies Saint Joseph as the namesake, likely because it didn't explicitly link 'São José dos Campos' to 'Saint Joseph' or 'Nazareth' in its initial searches.
**Root cause**: The agent's initial retrieval queries were too broad and did not effectively bridge the gap between the city's name and the specific historical figure or concept it was named after, preventing it from accessing the relevant information about Saint Joseph and his birthplace.
**Fix**: [retrieval_config] Improve the agent's default query generation for entity naming questions. For instance, if a city name includes a common saint's name (e.g., 'São José'), the agent should consider querying for 'Saint Joseph birthplace' or 'Saint Joseph origin' alongside general searches for the city's namesake, and explicitly use `entity_search` or `chunk_retrieve` with terms like 'named after Saint Joseph'.

- **Chunk search**: FOUND in 6 chunks
  - Chunk: Sisters of St Joseph of Nazareth (content)
  - Chunk: Christian (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): the person → england → new zealand → the sisters of saint joseph of nazareth
- **Agent**: 6 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'chunk_retrieve': 2, 'entity_search': 2}
  - Queries: ['What is the birthplace of the person after whom Sã', 'São José dos Campos named after person', 'São José dos Campos']

### 3hop1__820301_720914_41132

**Question**: How many times did plague occur in the place where Crucifixion's creator died?
**Gold**: 22
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: The question asks about plague occurrences in the place where the creator of Crucifixion died. The optimal path involves: 1. Identifying the 'creator of Crucifixion'. The agent correctly identified that 'Crucifixion' refers to an event, not an artwork, and thus has no 'creator' in the typical sense. However, the graph reachability shows a path `crucifixion -> christianity -> england -> messi`. This suggests a potential misinterpretation of 'creator' or that 'Crucifixion' might be linked to a person indirectly. Upon closer inspection of the provided gold answer location, the number '22' is associated with 'FC Barcelona' and 'Lionel Messi' (who has a career starting in Barcelona). The question's phrasing 'Crucifixion's creator' might be a red herring or a malformed question where 'Crucifixion' is meant to refer to a person's life or significant event. If we assume the question implicitly points to Lionel Messi (given the gold answer and graph hint), then: 2. Find where Lionel Messi died. 3. Search for plague occurrences in that location. However, the gold answer '22' is associated with Barcelona winning championships, not plague occurrences. This indicates a severe misunderstanding or mismatch between the question and the available data/agent's interpretation. Given the gold answer '22' appearing in chunks about FC Barcelona's championship wins, and the question asking 'How many times did plague occur', the question is fundamentally unanswerable with the provided gold answer context. If we strictly follow the gold answer's context, the question is likely malformed, and the agent's failure stems from trying to answer a question based on flawed premises or a mismatch. Assuming the question *intended* to ask something related to the provided gold answer's context, the path would be: 1. Identify Lionel Messi as the key entity, given his association with Barcelona and the number 22. 2. Find information related to Lionel Messi and the number 22. 3. The number 22 refers to Barcelona's 22nd championship win. The question about plague is irrelevant to this context. Therefore, there is no clear optimal path to the gold answer '22' given the question's phrasing about plague.
**Divergence**: Tool call [3] (entity_search) and subsequent calls like [4] (chunk_retrieve), [5] (entity_search), [6] (relationship_search), [7] (entity_info), [8] (chunk_retrieve) all failed to resolve 'creator of Crucifixion' because 'Crucifixion' is an event, not an artwork. The agent's reasoning for A1 was correct in identifying this ambiguity, but it did not pivot to explore alternative interpretations or graph connections that might have led to the gold answer, especially given the unusual nature of the question.
**Root cause**: The agent failed because the core premise of the question ('creator of Crucifixion') is ill-defined in the knowledge base, leading to an inability to find a meaningful intermediate entity to connect to the location and plague information.
**Fix**: [harness] The agent's planning and reasoning should be enhanced to handle ambiguous or malformed questions by exploring multiple interpretations of entities (e.g., 'Crucifixion' as an event vs. artwork) or by using graph traversal from the most connected entities ('crucifixion') to find potential bridging concepts, especially when the initial direct search for a 'creator' fails. A more robust default behavior when a primary entity cannot be resolved would be to leverage graph reachability (like the provided `crucifixion -> christianity -> england -> messi` path) to find related concepts and try to re-frame the question.

- **Chunk search**: FOUND in 469 chunks
  - Chunk: FC Barcelona (content)
  - Chunk: FC Barcelona (content)
- **Graph**: answer IN graph, 10 question entities found, 6 paths
  - Shortest path (3 hops): crucifixion → christianity → england → messi
- **Agent**: 9 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 2, 'relationship_search': 1, 'entity_info': 1}
  - Queries: ['How many times did plague occur in the place where', 'creator of Crucifixion', 'Crucifixion']

### 3hop1__136129_87694_124169

**Question**: What year did the Governor of the city where the basilica named after the same saint as the one that Mantua Cathedral is dedicated to die?
**Gold**: 1952
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question: Identify that Mantua Cathedral is dedicated to Saint Peter. 2. Find the basilica named after the same saint (Saint Peter). 3. Identify the city where this basilica is located (Vatican City). 4. Find the Governor of Vatican City. 5. Determine the death year of the Governor of Vatican City. Tool trace: reason(decompose, 'What year did the Governor of the city where the basilica named after the same saint as the one that Mantua Cathedral is dedicated to die?') -> atom a1: 'What saint is Mantua Cathedral dedicated to?' -> entity_search(semantic, 'Mantua Cathedral saint') -> get 'Saint Peter' -> atom a2: 'What basilica is named after Saint Peter?' -> entity_search(semantic, 'Basilica Saint Peter') -> get 'St. Peter's Basilica' -> atom a3: 'What city is St. Peter's Basilica in?' -> entity_info('St. Peter's Basilica') or entity_search(semantic, 'St. Peter's Basilica location') -> get 'Vatican City' -> atom a4: 'Who was the Governor of Vatican City?' -> entity_search(semantic, 'Governor of Vatican City') or entity_info('Vatican City') -> get 'Camillo Serafini' -> atom a5: 'When did Camillo Serafini die?' -> entity_info('Camillo Serafini') or chunk_retrieve(semantic, 'Camillo Serafini death year') -> get '1952'.
**Divergence**: Tool call [7]: The agent used entity_search('Mantua Cathedral') which returned 'roman catholic' as the dedication. While 'roman catholic' is related to religious institutions, it's not a specific saint's name. This incorrectly resolved atom a1 and led the agent down a path of searching for basilicas named 'roman catholic' instead of a specific saint.
**Root cause**: The agent's semantic search for the dedication of Mantua Cathedral incorrectly identified 'roman catholic' as the saint, leading to a chain of incorrect entity resolutions.
**Fix**: [retrieval_config] Improve the entity resolution models to better distinguish between religious affiliations/denominations and specific saint names when searching for dedications. This might involve fine-tuning the embedding models or adjusting ranking heuristics to prioritize specific named entities over broader categories in such contexts.

- **Chunk search**: FOUND in 81 chunks
  - Chunk: Member states of NATO (content)
  - Chunk: Estádio do Arruda (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): mantua cathedral → italy → england → arsenal
- **Agent**: 12 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 3, 'entity_search': 3, 'chunk_retrieve': 4, 'submit_answer': 1}
  - Queries: ['What year did the Governor of the city where the b', 'Mantua Cathedral dedicated to saint', 'Mantua Cathedral']

### 2hop__354635_174222

**Question**: What company succeeded the owner of Empire Sports Network?
**Gold**: Time Warner Cable
**Predicted**: (empty)
**Family**: `RETRIEVAL_RANKING` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question: 'Who owned Empire Sports Network?' and 'What company succeeded the owner of Empire Sports Network?'. 2. Use `entity_search(semantic, 'Empire Sports Network')` to find the entity for Empire Sports Network. 3. Use `entity_traverse(onehop, 'Empire Sports Network')` or `relationship_search(graph, 'Empire Sports Network')` to find its owner. 4. If the owner is identified as Adelphia Communications Corporation, use `chunk_retrieve(text, 'Adelphia Communications Corporation successor')` or `entity_search(semantic, 'Adelphia Communications Corporation successor')` to find the succeeding company. 5. Alternatively, after identifying Adelphia, `entity_traverse(onehop, 'Adelphia Communications Corporation')` could reveal its successor if directly linked. 6. The gold answer 'Time Warner Cable' is found in chunks mentioning Time Warner Cable acquiring assets from Adelphia. Thus, a query like `chunk_retrieve(text, 'Adelphia Communications Corporation acquired by Time Warner Cable')` or `entity_search(semantic, 'Time Warner Cable successor of Adelphia Communications Corporation')` would be optimal if the intermediate step is implicit. Given the gold answer, a more direct path would be: `entity_search(semantic, 'Empire Sports Network')` -> `entity_traverse(onehop, 'Empire Sports Network')` to find the owner -> `relationship_search(graph, owner)` to find successor OR `chunk_retrieve(text, 'owner of Empire Sports Network successor')`.
**Divergence**: Tool call #4 (chunk_retrieve). The agent searched for 'Adelphia Communications Corporation succeeded by company after bankruptcy', which is a reasonable query. However, the corpus likely did not contain a direct statement of succession. The subsequent `entity_search` also failed to yield a clear successor and returned ambiguous results. The agent then made a final `chunk_retrieve` that also failed to find the answer. The core issue is that the agent did not leverage the information present in the gold answer's chunk locations, which explicitly link Time Warner Cable's acquisition of assets from bankrupt Adelphia.
**Root cause**: The agent failed to connect the information about Time Warner Cable acquiring assets from Adelphia Communications Corporation, which is implicitly the succession relationship, due to the available graph not having a direct successor link and text retrieval failing to explicitly state the succession.
**Fix**: [corpus] Improve the corpus to explicitly state succession relationships for corporate acquisitions, especially where one company buys assets from a bankrupt entity. For example, ensure chunks include phrases like 'Time Warner Cable acquired the assets of bankrupt Adelphia Communications Corporation, effectively succeeding it in those business areas'. Alternatively, enhance retrieval to better infer succession from asset acquisition details.

- **Chunk search**: FOUND in 2 chunks
  - Chunk: Windjammer Communications (content)
  - Chunk: Raleigh, North Carolina (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): empire sports network → new york → canada → war
- **Agent**: 6 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'chunk_retrieve': 3, 'entity_search': 1}
  - Queries: ['What company succeeded the owner of Empire Sports ', 'Adelphia Communications Corporation successor comp']

### 3hop1__849312_503371_21711

**Question**: When was the Palau de la Generalitat constructed in the city where Martin from the region where Perdiguera is located died?
**Gold**: built in the 15th century
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Identify the city where Palau de la Generalitat is located. (e.g., entity_search for 'Palau de la Generalitat city' or chunk_retrieve for 'Palau de la Generalitat location'). This should yield 'Barcelona'. 2. Identify the region where Perdiguera is located. (e.g., entity_search for 'Perdiguera region' or chunk_retrieve for 'Perdiguera located in region'). This should yield 'Aragon'. 3. Find 'Martin' associated with 'Aragon' and determine the city where he died. (e.g., entity_search for 'Martin Aragon died city' or chunk_retrieve for 'Martin of Aragon death place'). This should yield 'Martin the Humane' and then 'Barcelona'. 4. Combine the city from step 1 and step 3 (which is Barcelona) and retrieve the construction date of Palau de la Generalitat in that city. (e.g., chunk_retrieve for 'Palau de la Generalitat constructed Barcelona'). The gold answer 'built in the 15th century' is in a chunk mentioning 'Palau de la Generalitat in Barcelona, built in the 15th century'.
**Divergence**: Tool call [8] chunk_retrieve({'method': 'text', 'query_text': 'Martin the Humane died in city', 'top_k': '10', 'document_collection_id': 'MuSiQue_chunks'}) failed because the corpus did not contain this information. The agent then tried tool call [9] relationship_search and tool call [10] entity_search, but neither directly found the death city. The agent correctly identified Barcelona as a city associated with 'Martin the Humane' (via 'count of barcelona'), but failed to connect this back to the Palau de la Generalitat in Barcelona to get the construction date.
**Root cause**: The agent's reasoning path broke when it couldn't find the death city for Martin the Humane, preventing it from linking Martin's death city to Barcelona and subsequently retrieving the construction date for the Palau de la Generalitat in Barcelona.
**Fix**: [routing] When an intermediate entity resolution fails (e.g., finding the death city), the agent should be able to backtrack or re-evaluate connections. For instance, upon finding 'count of barcelona' for Martin the Humane, it should have immediately checked if 'Palau de la Generalitat' is also related to 'Barcelona' and searched for its construction date there, rather than getting stuck on the missing death city.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Gothic architecture (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): palau de la generalitat → barcelona → england → 15th century
- **Agent**: 10 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'resources': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 3, 'relationship_search': 1}
  - Queries: ['When was the Palau de la Generalitat constructed i', 'Perdiguera region', 'Martin Aragon died city']

### 2hop__511296_577502

**Question**: Who married the actor from Terminator?
**Gold**: Maria Shriver
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Decompose the question: "Who married the actor from Terminator?" into "Who is the actor from Terminator?" (a1) and "Who married [actor from a1]?" (a2). 2. For a1, use `entity_search(semantic, query='actor from Terminator')` or `chunk_retrieve(text, query='actor from Terminator')`. 3. Once Arnold Schwarzenegger is identified, for a2, use `entity_search(semantic, query='Arnold Schwarzenegger spouse')` or `chunk_retrieve(text, query='Arnold Schwarzenegger married')`. 4. The gold answer 'Maria Shriver' should be retrievable from the results of step 3.
**Divergence**: Tool call [3]: `entity_search(semantic, query='actor from Terminator married spouse')`. The query was too broad and combined aspects of both sub-questions, leading to irrelevant entity suggestions like 'rebecca romijn' and 'thai woman'. This missed the primary target entity for the first hop.
**Root cause**: The agent's initial query formulation for the first sub-question was too broad, causing it to miss the correct intermediate entity and thus failing to gather relevant evidence for subsequent steps.
**Fix**: [retrieval_config] Improve the agent's ability to decompose questions and generate targeted, specific queries for each atomic step, rather than combining multiple concepts in a single search query.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Chrétien DuBois (content)
- **Graph**: answer IN graph, 9 question entities found, 9 paths
  - Shortest path (3 hops): married → american → batman → arnold schwarzenegger
- **Agent**: 6 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 2}
  - Queries: ['Who married the actor from Terminator?', 'actor from Terminator married spouse', 'Arnold Schwarzenegger spouse married to']
