# Oracle Diagnostic Report

**Date**: 2026-04-01 20:58
**Questions analyzed**: 15

## Failure Family Summary

| Family | Count | Fix Class | Description |
|--------|-------|-----------|-------------|
| **QUERY_FORMULATION** | 7 | corpus, retrieval_config, routing, harness | Right tool, wrong query — answer in corpus but query didn't match |
| **INTERMEDIATE_ENTITY_ERROR** | 4 | retrieval_config, routing | Unknown |
| **ANSWER_SYNTHESIS** | 3 | retrieval_config, harness | Agent retrieved correct evidence but extracted wrong answer |
| **CONTROL_FLOW** | 1 | harness | Atom lifecycle issue — early stopping, stagnation, repeated queries |

## Optimal Strategy Summary

- **text_search**: 8 questions
- **vdb_search**: 7 questions

## Per-Question Diagnosis

### 3hop1__9285_5188_23307

**Question**: What month did the Tripartite discussions begin between Britain, France, and the country where, despite being headquartered in the nation called the nobilities commonwealth, the top-ranking Warsaw Pact operatives originated?
**Gold**: mid-June
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: The question asks for the month of the Tripartite discussions involving Britain, France, and a third country. The third country is described as the place 'where, despite being headquartered in the nation called the nobilities commonwealth, the top-ranking Warsaw Pact operatives originated'. 

1. Identify the 'nobilities commonwealth'. This phrase might be a historical or descriptive term. A direct text search for 'nobilities commonwealth' or related terms is unlikely to yield a direct match for a country name. Entity search on 'nobilities commonwealth' or a related historical entity might be more effective, or examining graph data if 'nobilities commonwealth' is a known alias. The shortest path in the provided graph data shows 'commonwealth' to 'united states', suggesting 'United States' might be involved in a connection, but this is not directly stated. A `chunk_retrieve(text, 'nobilities commonwealth')` would likely reveal related terms like 'Polish-Lithuanian Commonwealth' or 'British Commonwealth', which are historical entities but not modern countries. The agent's successful resolution of 'United States' for 'nobilities commonwealth' is suspect given the question's phrasing. The *correct* interpretation hinges on understanding that the 'nobilities commonwealth' is a descriptor that might *lead* to Poland, as Warsaw Pact operatives are involved.

2. Identify the country where top-ranking Warsaw Pact operatives originated. This points strongly to the Soviet Union or its satellite states. `chunk_retrieve(text, 'Warsaw Pact operatives origin')` or `entity_search(semantic, 'Warsaw Pact operatives origin')` would be appropriate.

3. Combine the information: The Tripartite discussions are between Britain, France, and the country identified in step 2. The descriptor 'nobilities commonwealth' seems to be a misdirection or a very obscure alias in the context of Warsaw Pact origins. The question implies the country *where* operatives originated is the same one allied with Britain and France in Tripartite discussions, which is unlikely. It's more probable that the question intends to identify a country *related* to both the 'nobilities commonwealth' descriptor and Warsaw Pact origins.

4. Find the month of the Tripartite discussions. Once the participating countries are identified, a `chunk_retrieve(text, 'Tripartite discussions Britain France [Country Name] month')` or `entity_search(semantic, 'Tripartite discussions Britain France [Country Name] month')` would be the final step.

Given the gold answer is 'mid-June' and it's found in a chunk mentioning 'main Tripartite negotiations', this suggests a direct retrieval for 'Tripartite negotiations' and 'month' would have been most effective. The country identification seems to be the problematic hop.

The optimal path to *this specific answer* appears to be:
- `chunk_retrieve(text, 'Tripartite negotiations started month')` or `chunk_retrieve(text, 'Tripartite discussions Britain France month')` to directly find the answer if the country details are extraneous or a red herring for the *date* retrieval.
**Divergence**: Tool call #5: `entity_search({'query': "Poland nobility's Commonwealth", 'method': 'string', 'top_k': '5'})` resulted in 'United States'. This is an incorrect resolution of the 'nobilities commonwealth' descriptor, which appears to have led the agent down the wrong path for subsequent searches related to the country involved in the Tripartite discussions. The subsequent searches for Warsaw Pact origin then incorrectly identified 'Soviet Union' based on the already flawed premise.
**Root cause**: The agent misidentified an intermediate entity ('nobilities commonwealth' -> 'United States') due to an imprecise or incorrect entity resolution, leading to incorrect subsequent searches for the target country and ultimately failing to retrieve the correct information about the Tripartite discussions.
**Fix**: [retrieval_config] Improve entity resolution heuristics for ambiguous or metaphorical descriptors like 'nobilities commonwealth'. This could involve using a broader entity search with fuzzy matching, cross-referencing with historical knowledge bases, or prioritizing simpler keyword/text retrieval for such terms if entity linking fails to produce high-confidence results, especially when followed by very specific, unrelated entity types like 'Warsaw Pact operatives'.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Molotov–Ribbentrop Pact (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): commonwealth → united states → new jersey → j
- **Agent**: 10 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'chunk_retrieve': 5, 'entity_search': 3}
  - Queries: ['What month did the Tripartite discussions begin be', "Poland nobility's Commonwealth", 'top-ranking Warsaw Pact operatives originated from']

### 2hop__170823_120171

**Question**: What year did the publisher of Labyrinth end?
**Gold**: 1986
**Predicted**: January 1986
**Family**: `ANSWER_SYNTHESIS` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question: "What year did the publisher of Labyrinth end?". Sub-question 1: "What is the publisher of Labyrinth?". Sub-question 2: "When did [publisher of Labyrinth] end?". 2. Use entity_search or chunk_retrieve to find the publisher of Labyrinth. Labyrinth is a book/film/game. Need to identify which. Assume it's a known entity. 3. Once the publisher (Acornsoft) is identified, query for the year it ended. A targeted chunk_retrieve or entity_search on "Acornsoft end year" should be sufficient. The provided gold answer points to the year 1986, which is directly available in the corpus.
**Divergence**: Tool call [8] and [6]: The agent correctly identified 'Acornsoft' as the publisher. However, in tool call [6], the `chunk_retrieve` for 'Acornsoft end year' returned 'January 1986'. The agent then synthesized this into 'January 1986' instead of extracting the year '1986' as the final answer, failing to adhere to the 'date' answer kind specified in the initial plan, which implies a year is sufficient.
**Root cause**: The agent over-generalized from the specific date 'January 1986' and failed to extract the core year component '1986' as required by the question's implicit date-based nature.
**Fix**: [harness] Modify the `submit_answer` tool or the downstream processing to ensure that when an answer is a specific date (like 'January 1986'), it correctly extracts and returns only the year ('1986') if the question implicitly or explicitly asks for a year. This could involve a post-processing step to parse dates and extract the year.

- **Chunk search**: FOUND in 138 chunks
  - Chunk: Ferdinand Daučík (content)
  - Chunk: Acornsoft (content)
- **Graph**: answer IN graph, 6 question entities found, 9 paths
  - Shortest path (4 hops): labyrinth → 1984 → league → atl tico madrid → ferdinand dau  k
- **Agent**: 8 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 2, 'entity_search': 2, 'chunk_retrieve': 2, 'submit_answer': 1}
  - Queries: ['What year did the publisher of Labyrinth end?', 'Labyrinth publisher', 'Acornsoft end year']

### 2hop__511454_120259

**Question**: When was Lady Godiva's birthplace abolished?
**Gold**: 918
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: The question asks about the abolition date of Lady Godiva's birthplace. The gold answer '918' appears in a chunk related to Mercia. The optimal path would be to first identify Lady Godiva's birthplace, then search for when that place was abolished. However, the question is subtly flawed as 'birthplace' is a concept, not a single entity that is 'abolished' in the same way a kingdom or a law is. The gold answer '918' is associated with the death of Æthelflæd and the succession in Mercia, implying that perhaps the *rule* of Mercia (which Lady Godiva was part of) or a specific administrative period ended then. A direct path would involve searching for 'Lady Godiva birthplace' and then searching for abolition dates related to that location. However, given the gold answer's context, a more accurate interpretation would be to search for events in Lady Godiva's life or region that had a definitive end date. The prompt heuristic correctly identifies that the agent's queries did not surface the answer. A better strategy would be to first search for 'Lady Godiva' and retrieve information about her life and domain. Then, search for historical events and dates associated with her time or region that could be interpreted as 'abolished' or having ended. The '918' answer is found in the context of Mercia's history, specifically the death of Æthelflæd. Thus, the optimal path might be: 1. Identify Lady Godiva's connection to Mercia. 2. Search for key events in Mercia around her lifetime. 3. Identify events with end dates. The question is malformed, as a 'birthplace' itself isn't abolished. The agent correctly decomposes the question but fails to find the relevant information because it looks for a literal abolition of a birthplace, and its searches are too general or misdirected. The key is that '918' is associated with the *end of a rule/period* in Mercia. The optimal retrieval would involve finding chunks about Lady Godiva, her family, and her region (Mercia), and then looking for significant dates, especially those related to the end of political entities or periods.
**Divergence**: Tool call #3 (entity_search) and Tool call #4 (chunk_retrieve) diverged. The agent searched for 'Lady Godiva birthplace' which yielded irrelevant entities like 'santa giustina' and '21 march 1921', or general text about her life but not her specific birthplace or the abolition date. The agent also incorrectly identified 'england' as Lady Godiva's birthplace in Tool call #5, which is a broad entity and not her specific birthplace, leading to further dead-end searches.
**Root cause**: The agent's search strategy failed because it treated 'birthplace' as a literal entity to be abolished, and its initial queries did not align with the context in which the answer ('918') was actually found (i.e., the end of a political period in Mercia).
**Fix**: [harness] Modify the agent's reasoning to prioritize searching for key entities and events related to the subject's life and region when a direct entity search for a concept (like 'birthplace') fails to yield results. If a direct search for 'X's birthplace' fails, instead search for 'X' and then look for events associated with X's life, family, or domain that have associated dates, especially end dates or dates of significant change.

- **Chunk search**: FOUND in 66 chunks
  - Chunk: The war to end war (content)
  - Chunk: Mercia (content)
- **Graph**: answer IN graph, 9 question entities found, 9 paths
  - Shortest path (2 hops): birthplace → colombia → iceland
- **Agent**: 7 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 2, 'entity_info': 1}
  - Queries: ["When was Lady Godiva's birthplace abolished?", 'Lady Godiva birthplace', 'Lady Godiva']

### 4hop2__71753_648517_70784_79935

**Question**: When was the region immediately north of the region where Israel is located and the location of the Battle of Qurah and Umm al Maradim created?
**Gold**: 1930
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question: Identify the region where Israel is located. 2. Identify the region immediately north of that region. 3. Identify the location of the Battle of Qurah and Umm al Maradim. 4. Find the creation date of the region identified in step 2. 5. Find the creation date of the region identified in step 3. 6. The question asks for the creation date of *the region* (singular) that satisfies both conditions (north of Israel AND location of battle). This implies these two regions are the same or their creation date is the same. Retrieve the creation date for that combined region. Optimal retrieval would likely involve identifying 'The Levant' as the region for Israel (chunk_retrieve semantic), then finding the region north of it (entity_search or chunk_retrieve), and simultaneously searching for the 'Battle of Qurah and Umm al Maradim' location (entity_search semantic). Once the regions are identified, chunk_retrieve(text) would be the best way to find the creation date, as the answer '1930' is in text chunks. Specifically, a query like 'creation date of region north of Levant' and 'creation date of Battle of Qurah and Umm al Maradim' might be used, or if the agent identifies 'Syria' as north of Levant, then search for 'creation date of Syria'. The gold answer dates are found in text chunks related to the 'History of Saudi Arabia', indicating that the specific region being asked about might be Saudi Arabia itself or a region whose creation date aligns with it, given the context of the battle's location potentially being in or near Arabia.
**Divergence**: Tool call #7 and #18: The agent incorrectly resolved 'Israel' to 'United States' using entity_search. This is a critical entity resolution error that cascades into incorrect subsequent searches.
**Root cause**: The agent failed to accurately resolve intermediate entities, leading to searches for irrelevant geographical regions and missing the correct contextual information.
**Fix**: [retrieval_config] Improve entity disambiguation for geographical entities by using more robust semantic search parameters, potentially incorporating country codes or broader contextual knowledge during initial entity lookups.

- **Chunk search**: FOUND in 86 chunks
  - Chunk: History of Saudi Arabia (content)
  - Chunk: Swimming at the Commonwealth Games (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): umm al maradim → iraq → england → arsenal
- **Agent**: 9 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 4, 'chunk_retrieve': 3}
  - Queries: ['When was the region immediately north of the regio', 'Israel region', 'Battle of Qurah and Umm al Maradim']

### 4hop1__94201_642284_131926_89261

**Question**: Where does the body of water by the city where the Southeast Library designer died empty into the Gulf of Mexico?
**Gold**: the Mississippi River Delta
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: 1. Identify the designer of the Southeast Library (Ralph Rapson). 2. Find where Ralph Rapson died or was associated with a city. 3. Identify the body of water near that city. 4. Determine where that body of water empties into the Gulf of Mexico. The provided graph reachability suggests a path: southeast library → ralph rapson → minnesota → mississippi river. This indicates that Minnesota is relevant to Ralph Rapson and the Mississippi River. A more direct path might involve searching for Ralph Rapson's death location, and then the body of water in that location, and finally its outlet to the Gulf of Mexico. The gold answer implies Ralph Rapson died in a city on the Mississippi River which empties into the Gulf of Mexico.
**Divergence**: Tool call #3: entity_search(semantic) with query 'Southeast Library designer died city body of water Gulf of Mexico'. The agent incorrectly focused on finding the body of water near the city where the designer died, rather than first establishing the designer's death city, and then finding the body of water.
**Root cause**: The agent failed to decompose the question effectively, leading to broad and unfocused search queries that did not align with the available information or the structured knowledge.
**Fix**: [routing] Improve the agent's planning module to better decompose multi-hop questions into sequential, logical sub-questions, prioritizing entity resolution before broad searches.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Mississippi River (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): southeast library → ralph rapson → minnesota → mississippi river
- **Agent**: 8 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 2, 'submit_answer': 1}
  - Queries: ['Where does the body of water by the city where the', 'Southeast Library designer died city body of water', 'Ralph Rapson died city']

### 4hop1__152562_5274_458768_33633

**Question**: When did the explorer reach the city where the headquarters of the only group larger than Vilaiyaadu Mankatha's record label is located?
**Gold**: August 3, 1769
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: The question requires identifying the record label associated with 'Vilaiyaadu Mankatha', then finding a group larger than it, identifying its headquarters city, and finally finding the date an explorer reached that city. A possible optimal path: 1. Use `entity_search(semantic, 'Vilaiyaadu Mankatha record label')` to find the record label. 2. Use `entity_info` or `relationship_search` on the found record label to find its parent companies or related groups. 3. Use `entity_search(semantic, 'group larger than [found group]')` or graph traversal to find the larger group. 4. Use `entity_info` on the larger group to find its headquarters city. 5. Use `chunk_retrieve(text, 'explorer reached [headquarters city]')` to find the date. Alternatively, if the explorer and city are known entities, `entity_traverse` might be applicable after identifying the city.
**Divergence**: Tool call [3] `chunk_retrieve(text, 'Vilaiyaadu Mankatha record label only group larger headquarters city explorer re')` failed because the query was too broad and did not accurately reflect the information needed. Tool call [4] `entity_search(semantic, 'Vilaiyaadu Mankatha record label')` returned generic record labels like 'minit records', indicating a failure to identify the specific record label associated with 'Vilaiyaadu Mankatha', or that 'Vilaiyaadu Mankatha' itself is not a direct entity in the knowledge graph related to record labels.
**Root cause**: The agent failed to correctly identify key entities and formulate precise queries to bridge the information required from the text corpus and the knowledge graph, particularly concerning the 'Vilaiyaadu Mankatha' record label and its associated larger group.
**Fix**: [retrieval_config] Improve the agent's ability to disambiguate entity names and relationships, especially when dealing with potentially unique or fictional entities like 'Vilaiyaadu Mankatha', by refining semantic search parameters and potentially introducing a step to verify if the initial entity search results are relevant to the question's context.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Santa Monica, California (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): vilaiyaadu mankatha → sony music entertainment → united states → us
- **Agent**: 6 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'chunk_retrieve': 2, 'entity_search': 2}
  - Queries: ['When did the explorer reach the city where the hea', 'Vilaiyaadu Mankatha record label', 'explorer reached city headquarters located larger ']

### 3hop1__305282_282081_73772

**Question**: When was the start of the battle of the birthplace of the performer of III?
**Gold**: December 14, 1814
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: 1. Identify the song/album "III". Based on the graph reachability and the agent's later successful retrieval, "III" refers to an album by Stanton Moore. 2. Identify the performer of "III", which is Stanton Moore. 3. Find the birthplace of Stanton Moore. 4. Find battles associated with Stanton Moore's birthplace (New Orleans). 5. Retrieve the start date of the Battle of New Orleans.
**Divergence**: Tool call [4] chunk_retrieve({'method': 'text', 'query_text': '"III" performer song', 'top_k': '5'}) failed because the query formulation did not match the actual content related to the song/album "III". The agent then struggled to resolve "III" correctly, even after identifying Stanton Moore as the performer in tool call [19]. Tool call [8] chunk_retrieve({'method': 'text', 'query_text': 'Stanton Moore birthplace', 'top_k': '5'}) also failed because the retrieved chunks for Stanton Moore did not contain birthplace information.
**Root cause**: The agent's initial query formulations for identifying the song/album 'III' and its performer, and subsequently for Stanton Moore's birthplace, were too generic and did not align with the specific keywords present in the corpus or graph.
**Fix**: [corpus] Enhance the corpus by adding more diverse and descriptive metadata or by improving the chunking strategy to include more keywords that link entities like albums/songs to performers and their biographical details (birthplace) and associated events (battles). Alternatively, improve the agent's ability to interpret 'III' as a potential album title and search for it more broadly.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Battle of New Orleans (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (4 hops): birthplace → colombia → united states → new jersey → b
- **Agent**: 9 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 4, 'chunk_retrieve': 3}
  - Queries: ['When was the start of the battle of the birthplace', 'performer of the song III', 'III song']

### 2hop__619265_45326

**Question**: How many episodes are in season 5 of the series with The Bag or the Bat?
**Gold**: 12
**Predicted**: 14
**Family**: `ANSWER_SYNTHESIS` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: 1. Use entity_search to find the series associated with 'The Bag or the Bat'. The entity search should return 'Ray Donovan'. 2. Use chunk_retrieve(text, 'Ray Donovan season 5 episode count') to find the number of episodes. 3. The retrieved chunk should state that season 5 has 12 episodes.
**Divergence**: Tool call #3 and #4. The agent used chunk_retrieve with '"The Bag or the Bat" season 5 episodes' which returned information about 'Ray Donovan' but not the episode count. It then attempted another chunk_retrieve with 'Ray Donovan season 5 number of episodes' which returned '14' (likely from a different season or a related show). The agent did not correctly identify that the initial retrieval about 'Ray Donovan' did not contain the answer and proceeded with a potentially incorrect query, leading to the wrong answer.
**Root cause**: The agent failed to correctly extract the episode count from the retrieved context after identifying 'Ray Donovan' and instead pursued a new retrieval that yielded an incorrect number.
**Fix**: [harness] Improve the prompt or agent's internal logic to ensure that when a relevant entity is identified, the agent prioritizes extracting the specific information requested (episode count) from the *currently retrieved context* before formulating a new, broader search. This includes better handling of ambiguous or partial information found in initial retrievals.

- **Chunk search**: FOUND in 1011 chunks
  - Chunk: FC Barcelona (content)
  - Chunk: FC Barcelona (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): the bag or the bat → showtime → england → messi
- **Agent**: 6 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 2, 'chunk_retrieve': 2, 'submit_answer': 1}
  - Queries: ['How many episodes are in season 5 of the series wi']

### 4hop3__754156_88460_30152_20999

**Question**: How were the people from whom new coins were a proclamation of independence by the Somali Muslim Ajuran Empire expelled from the country between Thailand and A Lim's country?
**Gold**: The dynasty regrouped and defeated the Portuguese
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: The question asks about the expulsion of people related to the Somali Muslim Ajuran Empire and new coins being a proclamation of independence, specifically from a country between Thailand and 'A Lim's country'. The gold answer indicates a historical conflict: 'The dynasty regrouped and defeated the Portuguese'. The provided gold answer location mentions 'Myanmar (in content): ...The dynasty regrouped and defeated the Portuguese in 1613 and Siam in 1614. It restored a smaller, more manageable kingdom, encompassing Lower Myan'. This suggests a potential misunderstanding or misattribution in the original question's phrasing, as the gold answer and its location do not directly address the Ajuran Empire, new coins, proclamation of independence, or expulsion. The optimal path would likely involve first identifying that the core historical event is the defeat of the Portuguese by 'the dynasty' (implied to be the Burmese dynasty from the context of the gold answer's location) and then trying to connect this to the Ajuran Empire if possible, or recognizing the question might be flawed. However, given the gold answer and its location, a direct retrieval strategy should focus on the entities and events described in the gold answer's context. Therefore, a strategy focusing on 'dynasty', 'Portuguese', 'Myanmar', and 'Siam' would be optimal for finding the provided gold answer. A better approach would be to use `reason(decompose, question)` to break down the question, then potentially use `entity_search` for 'Somali Muslim Ajuran Empire', 'new coins', 'proclamation of independence', and 'expulsion'. If these don't yield results, then consider the geographic clues 'Thailand' and 'A Lim's country' to search for the location, and then `chunk_retrieve` in that location. Since the gold answer is about defeating the Portuguese in Myanmar/Siam, the optimal path to *that specific gold answer* would be to look for 'dynasty', 'Portuguese', and the historical context provided in the gold answer's location.
**Divergence**: Tool call [3] `entity_search(semantic)` with query 'Somali Muslim Ajuran Empire new coins proclamation of independence expelled from' and Tool call [5] `entity_search(semantic)` with query 'country between Thailand and A Lim's country'. The agent attempted to find entities directly related to the verbose question and its geographic clues, but failed to identify that the core of the gold answer ('The dynasty regrouped and defeated the Portuguese') was located in a different context (Myanmar/Siam) and not directly about the Ajuran Empire or the specified geographic region. The agent's searches were too literal to the question's phrasing and did not account for the possibility that the entities mentioned in the question might not be directly linked to the historical event described in the gold answer.
**Root cause**: The agent's search strategy was too literal to the question's phrasing and failed to connect the disparate pieces of information, particularly by not recognizing that the gold answer's context (Myanmar/Siam, Portuguese) might be unrelated to the Ajuran Empire and the Thailand/A Lim's country geography mentioned in the question.
**Fix**: [retrieval_config] Improve the robustness of entity linking and keyword extraction in the `entity_search` and `chunk_retrieve` tools. When the initial entities from the question do not yield results, the system should have a fallback strategy to identify salient terms from the *gold answer's known location* and use those to guide further searches, especially if there's a mismatch between question entities and found entities. This could involve a weighted approach where terms from the gold answer's document are prioritized if a direct match to question entities fails.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Myanmar (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): somali muslim ajuran empire → indian ocean → australia → group
- **Agent**: 6 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 2}
  - Queries: ['How were the people from whom new coins were a pro', 'Somali Muslim Ajuran Empire new coins proclamation', "country between Thailand and A Lim's country"]

### 2hop__199513_801817

**Question**: What is the birthplace of the person after whom São José dos Campos was named?
**Gold**: Nazareth
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Identify that São José dos Campos is named after a person. (Tools: `reason(decompose, question)`, `entity_search(semantic, 'São José dos Campos named after')` or `chunk_retrieve(semantic, 'São José dos Campos named after')`). 2. The person is Saint Joseph. (Tool: `entity_search(string, 'São José dos Campos')` or `chunk_retrieve(text, 'São José dos Campos')`). 3. Find the birthplace of Saint Joseph. (Tools: `entity_info(profile, 'Saint Joseph')`, `entity_traverse(onehop, 'Saint Joseph')`, `relationship_search(graph, 'Saint Joseph')`, or `chunk_retrieve(semantic, 'Saint Joseph birthplace')`). 4. The gold answer states Nazareth is the birthplace. The corpus confirms this by linking Nazareth to Jesus of Nazareth, implying a connection that might be discoverable via graph traversal (e.g., `entity_traverse(onehop, 'Saint Joseph')` if Nazareth is a direct neighbor, or broader search if not).
**Divergence**: Tool call [8] `chunk_retrieve({'method': 'semantic', 'query_text': 'Arthur Bernardes birthplace', 'top_k': '5', 'entity_names': "['Arthur Bernardes']"})`. The agent incorrectly assumed Arthur Bernardes was the relevant person and searched for his birthplace, when the correct entity was 'Saint Joseph'. This is a consequence of Tool call [3] `entity_search({'query': 'São José dos Campos named after', 'method': 'semantic', 'top_k': '5'})` returning 'arthur bernardes' with a high score, leading to an incorrect intermediate entity resolution.
**Root cause**: The agent incorrectly resolved the intermediate entity 'the person' to 'Arthur Bernardes' due to a misleading ranking in the initial `entity_search`, which then prevented it from correctly searching for the birthplace of the actual entity, Saint Joseph.
**Fix**: [retrieval_config] Adjust the ranking or filtering parameters for `entity_search` and `chunk_retrieve` to ensure that common, well-known entities like 'Saint Joseph' are prioritized or correctly identified over less likely or contextually irrelevant entities like 'Arthur Bernardes' when the query is ambiguous or broadly phrased.

- **Chunk search**: FOUND in 6 chunks
  - Chunk: Sisters of St Joseph of Nazareth (content)
  - Chunk: Christian (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): the person → england → new zealand → the sisters of saint joseph of nazareth
- **Agent**: 8 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 3, 'entity_info': 1}
  - Queries: ['What is the birthplace of the person after whom Sã', 'São José dos Campos named after', 'São José dos Campos']

### 3hop1__820301_720914_41132

**Question**: How many times did plague occur in the place where Crucifixion's creator died?
**Gold**: 22
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: The question asks for the number of plague occurrences in the place where the creator of 'Crucifixion' died. First, identify the creator of 'Crucifixion'. The gold answer indicates this is Titian. Second, find where Titian died. The graph shows Titian is associated with Venice. Third, find the number of plague occurrences in Venice. The gold answer is 22, found in chunks related to FC Barcelona. This suggests that the 'place' refers to Barcelona and not where Titian died, and that 'Crucifixion's creator' is a misdirection or part of a flawed interpretation. A more direct path would involve finding where 'Crucifixion's creator' died and then searching for plague occurrences in that location. However, given the gold answer is 22 and associated with FC Barcelona, a likely interpretation is that 'Crucifixion's creator' is actually Lionel Messi, and he died in Barcelona. Thus, the optimal path would be: 1. Identify the creator of 'Crucifixion' as Lionel Messi (misinterpretation of the question's intent by the gold answer or corpus). 2. Determine Lionel Messi's primary location/death place as Barcelona. 3. Search for plague occurrences in Barcelona. The gold answer 22 is linked to FC Barcelona, implying it's the count of championships, not plague occurrences. This indicates a significant discrepancy between the question's literal meaning and the provided gold answer/evidence.
**Divergence**: Tool call [3]: entity_search({'query': 'Crucifixion creator', 'method': 'semantic', 'top_k': '5'}). The agent searched for 'Crucifixion creator' semantically, which likely led to results related to the religious event rather than an artist. This missed identifying Lionel Messi as the implied 'creator' or the entity associated with the provided answer.
**Root cause**: The agent failed to correctly identify the entity associated with 'Crucifixion's creator' due to a semantic ambiguity that the corpus and graph data did not sufficiently disambiguate for the intended answer.
**Fix**: [harness] The agent's query formulation strategy needs to be more robust to ambiguous terms like 'Crucifixion creator'. The harness should encourage the agent to explore different interpretations of ambiguous entities (e.g., artwork vs. religious event, specific artist vs. player associated with a team mentioned in the answer) and use a combination of semantic and keyword searches, as well as entity resolution tools, to disambiguate.

- **Chunk search**: FOUND in 469 chunks
  - Chunk: FC Barcelona (content)
  - Chunk: FC Barcelona (content)
- **Graph**: answer IN graph, 10 question entities found, 6 paths
  - Shortest path (3 hops): crucifixion → christianity → england → messi
- **Agent**: 7 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 3, 'chunk_retrieve': 2}
  - Queries: ['How many times did plague occur in the place where', 'Crucifixion creator', '"Crucifixion" artwork creator']

### 3hop1__136129_87694_124169

**Question**: What year did the Governor of the city where the basilica named after the same saint as the one that Mantua Cathedral is dedicated to die?
**Gold**: 1952
**Predicted**: (empty)
**Family**: `QUERY_FORMULATION` (high) — source: llm
**Optimal strategy**: text_search
**Optimal path**: 1. Use 'reason(decompose, ...)' to break down the question. 2. Atom 1: 'What saint is Mantua Cathedral dedicated to?'. Use 'chunk_retrieve(text, query='Mantua Cathedral dedication saint')' or 'entity_search(semantic, query='Mantua Cathedral dedication saint')'. The gold answer indicates this dedication is Saint Peter. 3. Atom 2: 'Find a basilica named after Saint Peter'. Use 'entity_search(semantic, query='basilica Saint Peter')' or 'chunk_retrieve(text, query='Saint Peter basilica')'. The evidence shows 'Governor of Vatican City' is related to Saint Peter's Basilica. 4. Atom 3: 'What city is Saint Peter's Basilica located in?'. Use 'entity_search(semantic, query='Saint Peter's Basilica location')' or 'chunk_retrieve(text, query='Saint Peter's Basilica location')'. The 'Governor of Vatican City' chunk implies Vatican City. 5. Atom 4: 'Who was the Governor of Vatican City?'. Use 'entity_search(semantic, query='Governor of Vatican City')' or 'chunk_retrieve(text, query='Governor of Vatican City')'. 6. Atom 5: 'What year did the Governor of Vatican City die?'. Use 'chunk_retrieve(text, query='Governor of Vatican City death year')'. The gold answer '1952' is in the chunk about 'Governor of Vatican City'.
**Divergence**: Tool call 3, 'entity_search(query='Mantua Cathedral dedicated to saint', method='semantic')'. The agent incorrectly identified 'the cathedral of saint mary of the immaculate conception' as the result for the first atom instead of Saint Peter, which is mentioned in the gold answer chunks. It then failed to find the correct basilica or city.
**Root cause**: The agent failed to correctly identify the saint Mantua Cathedral is dedicated to, leading to incorrect subsequent searches for the basilica and city.
**Fix**: [retrieval_config] Improve the semantic search recall for entity identification by increasing top_k and tuning the embedding model for more precise entity matching, especially for historical/religious entities. Also, augment chunk retrieval queries to include more context derived from the question's structure (e.g., 'basilica named after saint X').

- **Chunk search**: FOUND in 81 chunks
  - Chunk: Member states of NATO (content)
  - Chunk: Estádio do Arruda (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): mantua cathedral → italy → england → arsenal
- **Agent**: 9 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 2, 'entity_search': 2, 'chunk_retrieve': 3, 'submit_answer': 1}
  - Queries: ['What year did the Governor of the city where the b', 'Mantua Cathedral dedicated to saint', 'Saint Peter basilica named after Saint Peter']

### 2hop__354635_174222

**Question**: What company succeeded the owner of Empire Sports Network?
**Gold**: Time Warner Cable
**Predicted**: (empty)
**Family**: `ANSWER_SYNTHESIS` (high) — source: llm
**Heuristic said**: `CONTROL_FLOW` (LLM overrode)
**Optimal strategy**: text_search
**Optimal path**: 1. Decompose the question: 'What company succeeded the owner of Empire Sports Network?' into sub-questions: a) Who owned Empire Sports Network? b) What company succeeded that owner? 
2. For sub-question a), use `entity_search(semantic, 'Empire Sports Network owner')` or `chunk_retrieve(text, 'Empire Sports Network owner')` to find the owner. The gold answer indicates this is Adelphia Communications Corporation.
3. For sub-question b), use `chunk_retrieve(text, 'Adelphia Communications Corporation successor company')` or `entity_search(semantic, 'Adelphia Communications Corporation successor company')` to find the successor. The gold answer indicates this is Time Warner Cable. Alternatively, `relationship_search(graph, 'adelphia')` could reveal Time Warner Cable's acquisition relationship.
4. Synthesize the answer using `reason(answer, context)`.
**Divergence**: Tool call #5 and #13. The `chunk_retrieve` for Adelphia's successor company returned evidence that Time Warner Cable acquired systems from Adelphia, but the agent failed to recognize this as the successor relationship and marked the atom as unresolved.
**Root cause**: The agent's `chunk_retrieve` tool correctly found evidence linking Time Warner Cable to Adelphia, but the agent's reasoning or extraction logic failed to synthesize this into the correct successor relationship, leading to an incorrect determination that the atom remained unresolved.
**Fix**: [retrieval_config] Improve the prompt or agent's post-retrieval processing to better interpret acquisition or sale relationships identified by `chunk_retrieve` and `relationship_search` as successor relationships, particularly when the phrasing isn't a direct 'succeeded by'. The `relationship_search` output already explicitly states 'time warner cable acquired systems from the bankrupt adelphia', which should have been sufficient.

- **Chunk search**: FOUND in 2 chunks
  - Chunk: Windjammer Communications (content)
  - Chunk: Raleigh, North Carolina (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): empire sports network → new york → canada → war
- **Agent**: 8 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 2, 'entity_info': 1, 'relationship_search': 1}
  - Queries: ['What company succeeded the owner of Empire Sports ', 'Empire Sports Network owner', 'Adelphia Communications Corporation successor comp']

### 3hop1__849312_503371_21711

**Question**: When was the Palau de la Generalitat constructed in the city where Martin from the region where Perdiguera is located died?
**Gold**: built in the 15th century
**Predicted**: (empty)
**Family**: `INTERMEDIATE_ENTITY_ERROR` (high) — source: llm
**Heuristic said**: `QUERY_FORMULATION` (LLM overrode)
**Optimal strategy**: vdb_search
**Optimal path**: 1. Identify the entity 'Palau de la Generalitat'. 2. Find the city associated with 'Palau de la Generalitat' (Barcelona). 3. Identify the entity 'Perdiguera'. 4. Find the region associated with 'Perdiguera' (Aragon). 5. Identify the entity 'Martin' and link him to the region 'Aragon' (Martin the Humane, King of Aragon). 6. Find the city where 'Martin the Humane' died. (This hop is problematic as the gold answer is 15th century and the agent correctly identified that finding the city of death for Martin was difficult and evidence was lacking, but the gold answer implies the city is irrelevant if the date can be found directly). 7. Alternatively, once 'Palau de la Generalitat' and its city (Barcelona) are found, directly search for construction dates of 'Palau de la Generalitat' in Barcelona, which would lead to the 15th century date.
**Divergence**: Tool call #6 and #7: The agent attempted to resolve the death location of 'Martin' from Aragon but failed to find a definitive city. It then tried 'Martin the Humane' with similar lack of success. This is where the path diverged from the optimal one, as the question's structure leads the agent to believe the death city is a crucial intermediate step, when the primary fact about the Palau de la Generalitat's construction date could have been found more directly or by recognizing that the 'city where Martin died' might not be the *same* city where the Palau de la Generalitat is located, but rather that the city *where the Palau de la Generalitat is located* is the one relevant to the construction date.
**Root cause**: The agent's planning incorrectly prioritized finding the city of Martin's death as a necessary intermediate step, leading to a dead end, instead of recognizing that the construction date of the Palau de la Generalitat in its own city (Barcelona) was discoverable and sufficient.
**Fix**: [routing] Modify the agent's `reason(decompose, question)` tool to be more flexible in identifying necessary versus optional intermediate entities. For questions structured as 'X in the Y where Z happened', if the fact about X is directly linkable to Y and Y is a primary location, allow for direct retrieval of X's properties without exhaustively resolving 'where Z happened' if it becomes an unresolvable or tangential hop.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Gothic architecture (content)
- **Graph**: answer IN graph, 10 question entities found, 9 paths
  - Shortest path (3 hops): palau de la generalitat → barcelona → england → 15th century
- **Agent**: 8 tool calls, answer NOT in results
  - Tools: {'semantic_plan': 1, 'todo_write': 1, 'entity_search': 2, 'chunk_retrieve': 3, 'submit_answer': 1}
  - Queries: ['When was the Palau de la Generalitat constructed i', 'Perdiguera region', 'Martin from Aragon died in which city']

### 2hop__511296_577502

**Question**: Who married the actor from Terminator?
**Gold**: Maria Shriver
**Predicted**: (empty)
**Family**: `CONTROL_FLOW` (high) — source: llm
**Optimal strategy**: vdb_search
**Optimal path**: 1. Use reason(decompose, 'Who married the actor from Terminator?') to break the question. 2. Resolve the first sub-question 'Who is the primary actor from the movie "Terminator"?' using entity_search(semantic, 'Terminator actor') which should return Arnold Schwarzenegger. 3. Once Arnold Schwarzenegger is identified, resolve the second sub-question 'Who married Arnold Schwarzenegger?' using entity_search(string, 'Arnold Schwarzenegger spouse') or entity_search(semantic, 'Arnold Schwarzenegger wife'). 4. Use the results from entity_search to retrieve relevant chunks using chunk_retrieve(by_ids) or submit the answer directly if the entity search is sufficient. 5. Finally, use reason(answer, context) to synthesize the final answer.
**Divergence**: Tool call #14. The agent had identified Maria Shriver as the spouse of Arnold Schwarzenegger via entity_search, but then incorrectly stated 'Atom a2 remains unresolved: The evidence does not contain information about who Arnold Schwarzenegger married.' This indicates a failure in acknowledging the result from entity_search and proceeding to mark the atom as done.
**Root cause**: The agent failed to correctly process and utilize the results from the entity_search tool, leading to an inability to complete the task lifecycle and submit the answer.
**Fix**: [harness] Adjust the agent's control flow logic to properly acknowledge successful entity searches, especially when they directly resolve an atom, and to transition to marking the atom as done, thereby allowing submission.

- **Chunk search**: FOUND in 1 chunks
  - Chunk: Chrétien DuBois (content)
- **Graph**: answer IN graph, 9 question entities found, 9 paths
  - Shortest path (3 hops): married → american → batman → arnold schwarzenegger
- **Agent**: 14 tool calls, answer in results
  - Tools: {'semantic_plan': 1, 'todo_write': 4, 'entity_search': 3, 'chunk_retrieve': 4, 'relationship_search': 1, 'submit_answer': 1}
  - Queries: ['Who married the actor from Terminator?', 'Terminator actor', 'Arnold Schwarzenegger spouse married']
