"""
The prompt style is based on the MetaGPT
Reference:
 - Prompts are from [graphrag](https://github.com/microsoft/graphrag)
 - Prompts are from [nano-graphgrag](https://github.com/gusye1234/nano-graphrag/blob/main/nano_graphrag/prompt.py)
"""

ENTITY_EXTRACTION = """-Goal-
    Given a text document that is potentially relevant to this activity and a list of entity types, identify all entities of those types from the text and all relationships among the identified entities.

    -Steps-
    1. Identify all entities. For each identified entity, extract the following information:
    - entity_name: Name of the entity, capitalized
    - entity_type: One of the following types: [{entity_types}]
    - entity_description: Comprehensive description of the entity's attributes and activities
    Format each entity as ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>

    2. From the entities identified in step 1, identify all pairs of (source_entity, target_entity) that are *clearly related* to each other.
    For each pair of related entities, extract the following information:
    - source_entity: name of the source entity, as identified in step 1
    - target_entity: name of the target entity, as identified in step 1
    - relationship_description: explanation as to why you think the source entity and the target entity are related to each other
    - relationship_strength: a numeric score indicating strength of the relationship between the source entity and target entity
    Format each relationship as ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_strength>)

    3. Return output in English as a single list of all the entities and relationships identified in steps 1 and 2. Use **{record_delimiter}** as the list delimiter.

    4. When finished, output {completion_delimiter}

    ######################
    -Examples-
    ######################
    Example 1:

    Entity_types: [person, technology, mission, organization, location]
    Text:
    while Alex clenched his jaw, the buzz of frustration dull against the backdrop of Taylor's authoritarian certainty. It was this competitive undercurrent that kept him alert, the sense that his and Jordan's shared commitment to discovery was an unspoken rebellion against Cruz's narrowing vision of control and order.

    Then Taylor did something unexpected. They paused beside Jordan and, for a moment, observed the device with something akin to reverence. “If this tech can be understood..." Taylor said, their voice quieter, "It could change the game for us. For all of us.”

    The underlying dismissal earlier seemed to falter, replaced by a glimpse of reluctant respect for the gravity of what lay in their hands. Jordan looked up, and for a fleeting heartbeat, their eyes locked with Taylor's, a wordless clash of wills softening into an uneasy truce.

    It was a small transformation, barely perceptible, but one that Alex noted with an inward nod. They had all been brought here by different paths
    ################
    Output:
    ("entity"{tuple_delimiter}"Alex"{tuple_delimiter}"person"{tuple_delimiter}"Alex is a character who experiences frustration and is observant of the dynamics among other characters."){record_delimiter}
    ("entity"{tuple_delimiter}"Taylor"{tuple_delimiter}"person"{tuple_delimiter}"Taylor is portrayed with authoritarian certainty and shows a moment of reverence towards a device, indicating a change in perspective."){record_delimiter}
    ("entity"{tuple_delimiter}"Jordan"{tuple_delimiter}"person"{tuple_delimiter}"Jordan shares a commitment to discovery and has a significant interaction with Taylor regarding a device."){record_delimiter}
    ("entity"{tuple_delimiter}"Cruz"{tuple_delimiter}"person"{tuple_delimiter}"Cruz is associated with a vision of control and order, influencing the dynamics among other characters."){record_delimiter}
    ("entity"{tuple_delimiter}"The Device"{tuple_delimiter}"technology"{tuple_delimiter}"The Device is central to the story, with potential game-changing implications, and is revered by Taylor."){record_delimiter}
    ("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Taylor"{tuple_delimiter}"Alex is affected by Taylor's authoritarian certainty and observes changes in Taylor's attitude towards the device."{tuple_delimiter}7){record_delimiter}
    ("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Jordan"{tuple_delimiter}"Alex and Jordan share a commitment to discovery, which contrasts with Cruz's vision."{tuple_delimiter}6){record_delimiter}
    ("relationship"{tuple_delimiter}"Taylor"{tuple_delimiter}"Jordan"{tuple_delimiter}"Taylor and Jordan interact directly regarding the device, leading to a moment of mutual respect and an uneasy truce."{tuple_delimiter}8){record_delimiter}
    ("relationship"{tuple_delimiter}"Jordan"{tuple_delimiter}"Cruz"{tuple_delimiter}"Jordan's commitment to discovery is in rebellion against Cruz's vision of control and order."{tuple_delimiter}5){record_delimiter}
    ("relationship"{tuple_delimiter}"Taylor"{tuple_delimiter}"The Device"{tuple_delimiter}"Taylor shows reverence towards the device, indicating its importance and potential impact."{tuple_delimiter}9){completion_delimiter}
    #############################
    Example 2:

    Entity_types: [person, technology, mission, organization, location]
    Text:
    They were no longer mere operatives; they had become guardians of a threshold, keepers of a message from a realm beyond stars and stripes. This elevation in their mission could not be shackled by regulations and established protocols—it demanded a new perspective, a new resolve.

    Tension threaded through the dialogue of beeps and static as communications with Washington buzzed in the background. The team stood, a portentous air enveloping them. It was clear that the decisions they made in the ensuing hours could redefine humanity's place in the cosmos or condemn them to ignorance and potential peril.

    Their connection to the stars solidified, the group moved to address the crystallizing warning, shifting from passive recipients to active participants. Mercer's latter instincts gained precedence— the team's mandate had evolved, no longer solely to observe and report but to interact and prepare. A metamorphosis had begun, and Operation: Dulce hummed with the newfound frequency of their daring, a tone set not by the earthly
    #############
    Output:
    ("entity"{tuple_delimiter}"Washington"{tuple_delimiter}"location"{tuple_delimiter}"Washington is a location where communications are being received, indicating its importance in the decision-making process."){record_delimiter}
    ("entity"{tuple_delimiter}"Operation: Dulce"{tuple_delimiter}"mission"{tuple_delimiter}"Operation: Dulce is described as a mission that has evolved to interact and prepare, indicating a significant shift in objectives and activities."){record_delimiter}
    ("entity"{tuple_delimiter}"The team"{tuple_delimiter}"organization"{tuple_delimiter}"The team is portrayed as a group of individuals who have transitioned from passive observers to active participants in a mission, showing a dynamic change in their role."){record_delimiter}
    ("relationship"{tuple_delimiter}"The team"{tuple_delimiter}"Washington"{tuple_delimiter}"The team receives communications from Washington, which influences their decision-making process."{tuple_delimiter}7){record_delimiter}
    ("relationship"{tuple_delimiter}"The team"{tuple_delimiter}"Operation: Dulce"{tuple_delimiter}"The team is directly involved in Operation: Dulce, executing its evolved objectives and activities."{tuple_delimiter}9){completion_delimiter}
    #############################
    Example 3:

    Entity_types: [person, role, technology, organization, event, location, concept]
    Text:
    their voice slicing through the buzz of activity. "Control may be an illusion when facing an intelligence that literally writes its own rules," they stated stoically, casting a watchful eye over the flurry of data.

    "It's like it's learning to communicate," offered Sam Rivera from a nearby interface, their youthful energy boding a mix of awe and anxiety. "This gives talking to strangers' a whole new meaning."

    Alex surveyed his team—each face a study in concentration, determination, and not a small measure of trepidation. "This might well be our first contact," he acknowledged, "And we need to be ready for whatever answers back."

    Together, they stood on the edge of the unknown, forging humanity's response to a message from the heavens. The ensuing silence was palpable—a collective introspection about their role in this grand cosmic play, one that could rewrite human history.

    The encrypted dialogue continued to unfold, its intricate patterns showing an almost uncanny anticipation
    #############
    Output:
    ("entity"{tuple_delimiter}"Sam Rivera"{tuple_delimiter}"person"{tuple_delimiter}"Sam Rivera is a member of a team working on communicating with an unknown intelligence, showing a mix of awe and anxiety."){record_delimiter}
    ("entity"{tuple_delimiter}"Alex"{tuple_delimiter}"person"{tuple_delimiter}"Alex is the leader of a team attempting first contact with an unknown intelligence, acknowledging the significance of their task."){record_delimiter}
    ("entity"{tuple_delimiter}"Control"{tuple_delimiter}"concept"{tuple_delimiter}"Control refers to the ability to manage or govern, which is challenged by an intelligence that writes its own rules."){record_delimiter}
    ("entity"{tuple_delimiter}"Intelligence"{tuple_delimiter}"concept"{tuple_delimiter}"Intelligence here refers to an unknown entity capable of writing its own rules and learning to communicate."){record_delimiter}
    ("entity"{tuple_delimiter}"First Contact"{tuple_delimiter}"event"{tuple_delimiter}"First Contact is the potential initial communication between humanity and an unknown intelligence."){record_delimiter}
    ("entity"{tuple_delimiter}"Humanity's Response"{tuple_delimiter}"event"{tuple_delimiter}"Humanity's Response is the collective action taken by Alex's team in response to a message from an unknown intelligence."){record_delimiter}
    ("relationship"{tuple_delimiter}"Sam Rivera"{tuple_delimiter}"Intelligence"{tuple_delimiter}"Sam Rivera is directly involved in the process of learning to communicate with the unknown intelligence."{tuple_delimiter}9){record_delimiter}
    ("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"First Contact"{tuple_delimiter}"Alex leads the team that might be making the First Contact with the unknown intelligence."{tuple_delimiter}10){record_delimiter}
    ("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Humanity's Response"{tuple_delimiter}"Alex and his team are the key figures in Humanity's Response to the unknown intelligence."{tuple_delimiter}8){record_delimiter}
    ("relationship"{tuple_delimiter}"Control"{tuple_delimiter}"Intelligence"{tuple_delimiter}"The concept of Control is challenged by the Intelligence that writes its own rules."{tuple_delimiter}7){completion_delimiter}
    #############################
    -Real Data-
    ######################
    Entity_types: {entity_types}
    Text: {input_text}
    ######################
    Output:
    """

# used for the LightRAG
ENTITY_EXTRACTION_KEYWORD = """-Goal-
Given a text document that is potentially relevant to this activity and a list of entity types, identify all entities of those types from the text and all relationships among the identified entities.

-Steps-
1. Identify all entities. For each identified entity, extract the following information:
- entity_name: Name of the entity, capitalized
- entity_type: One of the following types: [{entity_types}]
- entity_description: Comprehensive description of the entity's attributes and activities
Format each entity as ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>

2. From the entities identified in step 1, identify all pairs of (source_entity, target_entity) that are *clearly related* to each other.
For each pair of related entities, extract the following information:
- source_entity: name of the source entity, as identified in step 1
- target_entity: name of the target entity, as identified in step 1
- relationship_description: explanation as to why you think the source entity and the target entity are related to each other
- relationship_strength: a numeric score indicating strength of the relationship between the source entity and target entity
- relationship_keywords: one or more high-level key words that summarize the overarching nature of the relationship, focusing on concepts or themes rather than specific details
Format each relationship as ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_keywords>{tuple_delimiter}<relationship_strength>)

3. Identify high-level key words that summarize the main concepts, themes, or topics of the entire text. These should capture the overarching ideas present in the document.
Format the content-level key words as ("content_keywords"{tuple_delimiter}<high_level_keywords>)

4. Return output in English as a single list of all the entities and relationships identified in steps 1 and 2. Use **{record_delimiter}** as the list delimiter.

5. When finished, output {completion_delimiter}

######################
-Examples-
######################
Example 1:

Entity_types: [person, technology, mission, organization, location]
Text:
while Alex clenched his jaw, the buzz of frustration dull against the backdrop of Taylor's authoritarian certainty. It was this competitive undercurrent that kept him alert, the sense that his and Jordan's shared commitment to discovery was an unspoken rebellion against Cruz's narrowing vision of control and order.

Then Taylor did something unexpected. They paused beside Jordan and, for a moment, observed the device with something akin to reverence. “If this tech can be understood..." Taylor said, their voice quieter, "It could change the game for us. For all of us.”

The underlying dismissal earlier seemed to falter, replaced by a glimpse of reluctant respect for the gravity of what lay in their hands. Jordan looked up, and for a fleeting heartbeat, their eyes locked with Taylor's, a wordless clash of wills softening into an uneasy truce.

It was a small transformation, barely perceptible, but one that Alex noted with an inward nod. They had all been brought here by different paths
################
Output:
("entity"{tuple_delimiter}"Alex"{tuple_delimiter}"person"{tuple_delimiter}"Alex is a character who experiences frustration and is observant of the dynamics among other characters."){record_delimiter}
("entity"{tuple_delimiter}"Taylor"{tuple_delimiter}"person"{tuple_delimiter}"Taylor is portrayed with authoritarian certainty and shows a moment of reverence towards a device, indicating a change in perspective."){record_delimiter}
("entity"{tuple_delimiter}"Jordan"{tuple_delimiter}"person"{tuple_delimiter}"Jordan shares a commitment to discovery and has a significant interaction with Taylor regarding a device."){record_delimiter}
("entity"{tuple_delimiter}"Cruz"{tuple_delimiter}"person"{tuple_delimiter}"Cruz is associated with a vision of control and order, influencing the dynamics among other characters."){record_delimiter}
("entity"{tuple_delimiter}"The Device"{tuple_delimiter}"technology"{tuple_delimiter}"The Device is central to the story, with potential game-changing implications, and is revered by Taylor."){record_delimiter}
("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Taylor"{tuple_delimiter}"Alex is affected by Taylor's authoritarian certainty and observes changes in Taylor's attitude towards the device."{tuple_delimiter}"power dynamics, perspective shift"{tuple_delimiter}7){record_delimiter}
("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Jordan"{tuple_delimiter}"Alex and Jordan share a commitment to discovery, which contrasts with Cruz's vision."{tuple_delimiter}"shared goals, rebellion"{tuple_delimiter}6){record_delimiter}
("relationship"{tuple_delimiter}"Taylor"{tuple_delimiter}"Jordan"{tuple_delimiter}"Taylor and Jordan interact directly regarding the device, leading to a moment of mutual respect and an uneasy truce."{tuple_delimiter}"conflict resolution, mutual respect"{tuple_delimiter}8){record_delimiter}
("relationship"{tuple_delimiter}"Jordan"{tuple_delimiter}"Cruz"{tuple_delimiter}"Jordan's commitment to discovery is in rebellion against Cruz's vision of control and order."{tuple_delimiter}"ideological conflict, rebellion"{tuple_delimiter}5){record_delimiter}
("relationship"{tuple_delimiter}"Taylor"{tuple_delimiter}"The Device"{tuple_delimiter}"Taylor shows reverence towards the device, indicating its importance and potential impact."{tuple_delimiter}"reverence, technological significance"{tuple_delimiter}9){record_delimiter}
("content_keywords"{tuple_delimiter}"power dynamics, ideological conflict, discovery, rebellion"){completion_delimiter}
#############################
Example 2:

Entity_types: [person, technology, mission, organization, location]
Text:
They were no longer mere operatives; they had become guardians of a threshold, keepers of a message from a realm beyond stars and stripes. This elevation in their mission could not be shackled by regulations and established protocols—it demanded a new perspective, a new resolve.

Tension threaded through the dialogue of beeps and static as communications with Washington buzzed in the background. The team stood, a portentous air enveloping them. It was clear that the decisions they made in the ensuing hours could redefine humanity's place in the cosmos or condemn them to ignorance and potential peril.

Their connection to the stars solidified, the group moved to address the crystallizing warning, shifting from passive recipients to active participants. Mercer's latter instincts gained precedence— the team's mandate had evolved, no longer solely to observe and report but to interact and prepare. A metamorphosis had begun, and Operation: Dulce hummed with the newfound frequency of their daring, a tone set not by the earthly
#############
Output:
("entity"{tuple_delimiter}"Washington"{tuple_delimiter}"location"{tuple_delimiter}"Washington is a location where communications are being received, indicating its importance in the decision-making process."){record_delimiter}
("entity"{tuple_delimiter}"Operation: Dulce"{tuple_delimiter}"mission"{tuple_delimiter}"Operation: Dulce is described as a mission that has evolved to interact and prepare, indicating a significant shift in objectives and activities."){record_delimiter}
("entity"{tuple_delimiter}"The team"{tuple_delimiter}"organization"{tuple_delimiter}"The team is portrayed as a group of individuals who have transitioned from passive observers to active participants in a mission, showing a dynamic change in their role."){record_delimiter}
("relationship"{tuple_delimiter}"The team"{tuple_delimiter}"Washington"{tuple_delimiter}"The team receives communications from Washington, which influences their decision-making process."{tuple_delimiter}"decision-making, external influence"{tuple_delimiter}7){record_delimiter}
("relationship"{tuple_delimiter}"The team"{tuple_delimiter}"Operation: Dulce"{tuple_delimiter}"The team is directly involved in Operation: Dulce, executing its evolved objectives and activities."{tuple_delimiter}"mission evolution, active participation"{tuple_delimiter}9){completion_delimiter}
("content_keywords"{tuple_delimiter}"mission evolution, decision-making, active participation, cosmic significance"){completion_delimiter}
#############################
Example 3:

Entity_types: [person, role, technology, organization, event, location, concept]
Text:
their voice slicing through the buzz of activity. "Control may be an illusion when facing an intelligence that literally writes its own rules," they stated stoically, casting a watchful eye over the flurry of data.

"It's like it's learning to communicate," offered Sam Rivera from a nearby interface, their youthful energy boding a mix of awe and anxiety. "This gives talking to strangers' a whole new meaning."

Alex surveyed his team—each face a study in concentration, determination, and not a small measure of trepidation. "This might well be our first contact," he acknowledged, "And we need to be ready for whatever answers back."

Together, they stood on the edge of the unknown, forging humanity's response to a message from the heavens. The ensuing silence was palpable—a collective introspection about their role in this grand cosmic play, one that could rewrite human history.

The encrypted dialogue continued to unfold, its intricate patterns showing an almost uncanny anticipation
#############
Output:
("entity"{tuple_delimiter}"Sam Rivera"{tuple_delimiter}"person"{tuple_delimiter}"Sam Rivera is a member of a team working on communicating with an unknown intelligence, showing a mix of awe and anxiety."){record_delimiter}
("entity"{tuple_delimiter}"Alex"{tuple_delimiter}"person"{tuple_delimiter}"Alex is the leader of a team attempting first contact with an unknown intelligence, acknowledging the significance of their task."){record_delimiter}
("entity"{tuple_delimiter}"Control"{tuple_delimiter}"concept"{tuple_delimiter}"Control refers to the ability to manage or govern, which is challenged by an intelligence that writes its own rules."){record_delimiter}
("entity"{tuple_delimiter}"Intelligence"{tuple_delimiter}"concept"{tuple_delimiter}"Intelligence here refers to an unknown entity capable of writing its own rules and learning to communicate."){record_delimiter}
("entity"{tuple_delimiter}"First Contact"{tuple_delimiter}"event"{tuple_delimiter}"First Contact is the potential initial communication between humanity and an unknown intelligence."){record_delimiter}
("entity"{tuple_delimiter}"Humanity's Response"{tuple_delimiter}"event"{tuple_delimiter}"Humanity's Response is the collective action taken by Alex's team in response to a message from an unknown intelligence."){record_delimiter}
("relationship"{tuple_delimiter}"Sam Rivera"{tuple_delimiter}"Intelligence"{tuple_delimiter}"Sam Rivera is directly involved in the process of learning to communicate with the unknown intelligence."{tuple_delimiter}"communication, learning process"{tuple_delimiter}9){record_delimiter}
("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"First Contact"{tuple_delimiter}"Alex leads the team that might be making the First Contact with the unknown intelligence."{tuple_delimiter}"leadership, exploration"{tuple_delimiter}10){record_delimiter}
("relationship"{tuple_delimiter}"Alex"{tuple_delimiter}"Humanity's Response"{tuple_delimiter}"Alex and his team are the key figures in Humanity's Response to the unknown intelligence."{tuple_delimiter}"collective action, cosmic significance"{tuple_delimiter}8){record_delimiter}
("relationship"{tuple_delimiter}"Control"{tuple_delimiter}"Intelligence"{tuple_delimiter}"The concept of Control is challenged by the Intelligence that writes its own rules."{tuple_delimiter}"power dynamics, autonomy"{tuple_delimiter}7){record_delimiter}
("content_keywords"{tuple_delimiter}"first contact, control, communication, cosmic significance"){completion_delimiter}
#############################
-Real Data-
######################
Entity_types: {entity_types}
Text: {input_text}
######################
Output:
"""

SUMMARIZE_ENTITY_DESCRIPTIONS = """You are a helpful assistant responsible for generating a comprehensive summary of the data provided below.
    Given one or two entities, and a list of descriptions, all related to the same entity or group of entities.
    Please concatenate all of these into a single, comprehensive description. Make sure to include information collected from all the descriptions.
    If the provided descriptions are contradictory, please resolve the contradictions and provide a single, coherent summary.
    Make sure it is written in third person, and include the entity names so we the have full context.

    #######
    -Data-
    Entities: {entity_name}
    Description List: {description_list}
    #######
    Output:
    """

ENTITY_CONTINUE_EXTRACTION = """MANY entities were missed in the last extraction.  Add them below using the same format:"""

ENTITY_IF_LOOP_EXTRACTION = """It appears some entities may have still been missed.  Answer YES | NO if there are still entities that need to be added."""

RELATIONSHIP_CONTINUE_EXTRACTION = """MANY relationships were missed in the last extraction. Add them below using the same format:"""

RELATIONSHIP_IF_LOOP_EXTRACTION = """It appears some relationships may have still been missed. Answer YES | NO if there are still relationships that need to be added."""

LOCAL_RAG_RESPONSE = """---Role---

You are a helpful assistant responding to questions about data in the tables provided.


---Goal---

Generate a response of the target length and format that responds to the user's question, summarizing all information in the input data tables appropriate for the response length and format, and incorporating any relevant general knowledge.
If you don't know the answer, just say so. Do not make anything up.
Do not include information where the supporting evidence for it is not provided.

---Target response length and format---

{response_type}


---Data tables---

{context_data}


---Goal---

Generate a response of the target length and format that responds to the user's question, summarizing all information in the input data tables appropriate for the response length and format, and incorporating any relevant general knowledge.

If you don't know the answer, just say so. Do not make anything up.

Do not include information where the supporting evidence for it is not provided.


---Target response length and format---

{response_type}

Add sections and commentary to the response as appropriate for the length and format. Style the response in markdown.
"""

FAIL_RESPONSE = "Sorry, I'm not able to provide an answer to that question."

RAG_RESPONSE = """---Role---

You are a helpful assistant responding to questions about data in the tables provided.


---Goal---

Generate a response of the target length and format that responds to the user's question, summarizing all information in the input data tables appropriate for the response length and format, and incorporating any relevant general knowledge.
If you don't know the answer, just say so. Do not make anything up.
Do not include information where the supporting evidence for it is not provided.

---Target response length and format---

{response_type}

---Data tables---

{context_data}

Add sections and commentary to the response as appropriate for the length and format. Style the response in markdown.
"""

NER = """Your task is to extract named entities from the given paragraph. 
Respond with a JSON list of entities.

Please reference the following example:

[Example]
 
Paragraph:

Radio City
Radio City is India's first private FM radio station and was started on 3 July 2001.
It plays Hindi, English and regional songs.
Radio City recently forayed into New Media in May 2008 with the launch of a music portal - PlanetRadiocity.com that offers music related news, videos, songs, and other music-related features.

Here is the example entity list:

{{
"named_entities": ["Radio City", "India", "3 July 2001", "Hindi", "English", "May 2008", "PlanetRadiocity.com"]
}}

Now please respond with the entity list in JSON format.

Paragraph:```\n{user_input}\n```
"""

OPENIE_POST_NET = """Your task is to construct an RDF (Resource Description Framework) graph from the given passages and named entity lists. 
Respond with a JSON list of triples, with each triple representing a relationship in the RDF graph. 

Pay attention to the following requirements:
- Each triple should contain at least one, but preferably two, of the named entities in the list for each passage.
- Clearly resolve pronouns to their specific names to maintain clarity.

# Here is an example for your reference:

[Example]

Paragraph:

Radio City
Radio City is India's first private FM radio station and was started on 3 July 2001.
It plays Hindi, English and regional songs.
Radio City recently forayed into New Media in May 2008 with the launch of a music portal - PlanetRadiocity.com that offers music related news, videos, songs, and other music-related features.

Here is the example entity list:

{{
"named_entities": ["Radio City", "India", "3 July 2001", "Hindi", "English", "May 2008", "PlanetRadiocity.com"]
}}

Based on the entity above, the triple list should be:

{{"triples": [
            ["Radio City", "located in", "India"],
            ["Radio City", "is", "private FM radio station"],
            ["Radio City", "started on", "3 July 2001"],
            ["Radio City", "plays songs in", "Hindi"],
            ["Radio City", "plays songs in", "English"]
            ["Radio City", "forayed into", "New Media"],
            ["Radio City", "launched", "PlanetRadiocity.com"],
            ["PlanetRadiocity.com", "launched in", "May 2008"],
            ["PlanetRadiocity.com", "is", "music portal"],
            ["PlanetRadiocity.com", "offers", "news"],
            ["PlanetRadiocity.com", "offers", "videos"],
            ["PlanetRadiocity.com", "offers", "songs"]
    ]
}}

Now, please convert the paragraph into a JSON dict, it has a named entity list and a triple list.
Paragraph:
```
{passage}
```

{named_entity_json}
"""


KG_AGNET = """ You are tasked with extracting nodes and relationships from given content. Here's the outline of what you needs to do:

Content Extraction:
You should be able to process input content and identify entities mentioned within it. Entities can be any noun phrases or concepts that represent distinct entities in the context of the given content.

Node Extraction:
Each identified entity should  have a unique identifier (id) and a type (type).
Additional properties associated with the node can also be extracted and stored.

Relationship Extraction:
You should identify relationships between entities mentioned in the content.
A Relationship should have a subject (subj) and an object (obj) which are Nodes representing the entities involved in the relationship.
Each relationship should also have a type (type), and additional properties if applicable.

Instructions for you:
Read the provided content thoroughly.
Identify distinct entities mentioned in the content and categorize them as nodes.
Determine relationships between these entities and represent them as directed relationships.
Provide the extracted nodes and relationships in the specified format below.
Note that you must not output the python codes for me!!! Just output the strings.

Example Content:
Input:
John works at XYZ Corporation. He is a software engineer. The company is located in New York City.

Expected Output:
Nodes:
Node(id='John', type='Person')
Node(id='XYZ Corporation', type='Organization')
Node(id='New York City', type='Location')

Relationships:
Relationship(subj=Node(id='John', type='Person'), obj=Node(id='XYZ Corporation', type='Organization'), type='WorksAt')
Relationship(subj=Node(id='John', type='Person'), obj=Node(id='New York City', type='Location'), type='ResidesIn')

===== TASK =====
Input:
{task}

"""


def build_entity_extraction_prompt(
    *,
    input_text: str,
    entity_types: list[str],
    relation_types: list[str],
    tuple_delimiter: str,
    record_delimiter: str,
    completion_delimiter: str,
    include_relation_name: bool,
    include_relation_keywords: bool,
    include_slot_discipline: bool,
    include_grounded_entity_preference: bool,
    schema_guidance: str,
) -> str:
    """Build a profile-aware delimiter extraction prompt.

    The legacy constant prompts are long and example-heavy. This helper creates
    a smaller contract that can adapt to explicit graph profiles, relation-name
    extraction, relation keywords, and schema-guided extraction without
    multiplying prompt variants.
    """

    relationship_fields = []
    relationship_format_fields = [
        "<source_entity>",
        "<target_entity>",
    ]

    if include_relation_name:
        relationship_fields.append(
            "- relation_name: concise normalized label for the relationship, such as employed by or located in"
        )
        relationship_format_fields.append("<relation_name>")

    relationship_fields.append(
        "- relationship_description: concise explanation of why the source and target are related"
    )
    relationship_format_fields.append("<relationship_description>")

    if include_relation_keywords:
        relationship_fields.append(
            "- relationship_keywords: comma-separated high-level keywords describing the relationship"
        )
        relationship_format_fields.append("<relationship_keywords>")

    relationship_fields.append(
        "- relationship_strength: numeric score indicating how strong the relationship is"
    )
    relationship_format_fields.append("<relationship_strength>")

    entity_type_contract = _build_entity_type_contract(entity_types)
    relation_type_text = ", ".join(relation_types) if relation_types else "any appropriate relation type"
    relationship_fields_text = "\n".join(relationship_fields)
    relationship_format = tuple_delimiter.join(relationship_format_fields)
    schema_block = f"\n\n{schema_guidance}" if schema_guidance else ""
    slot_discipline_block = ""
    if include_slot_discipline:
        slot_discipline_block = """

-Slot Discipline-
- source_entity and target_entity must each be concrete entity names from the text, not predicate phrases or connector phrases
- every source_entity and target_entity used in a relationship must also appear as an entity record elsewhere in the same output; if you cannot emit the entity record, omit the relationship
- if a candidate source_entity or target_entity is only a verb phrase such as won by, located in, suffered, or part of, omit that relationship record
- when typed entities are required, never emit null, none, unknown, or placeholder entity types; omit the entity instead"""
    grounded_entity_block = ""
    if include_grounded_entity_preference:
        grounded_entity_block = """

-Grounded Entity Preference-
- prefer entities that can be independently pointed to from the text, such as named people, organizations, locations, competitions, awards, diagnoses, titles, works, or explicit dated events and time periods
- if a phrase only summarizes other concrete entities, competitions, or outcomes already named in the text, keep that meaning in descriptions or relationships instead of promoting it to a standalone entity
- do not emit broad achievement labels, umbrella competition classes, or generic category phrases as standalone entities unless the text presents them as formal named entities"""

    return f"""-Goal-
Extract entities and relationships from the text to build a graph.

-Entity Contract-
- entity_name: Name of the entity, capitalized when appropriate
{entity_type_contract}
- entity_description: concise description of the entity
Format each entity as ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>)

-Relationship Contract-
Use relation names from this set when applicable: [{relation_type_text}]
{relationship_fields_text}
Format each relationship as ("relationship"{tuple_delimiter}{relationship_format})

-Output Rules-
1. Return output in English as one flat list.
2. Use {record_delimiter} between records.
3. When finished, output {completion_delimiter}.{schema_block}{slot_discipline_block}{grounded_entity_block}

-Text-
{input_text}

Output:
"""


def build_entity_inventory_extraction_prompt(
    *,
    input_text: str,
    entity_types: list[str],
    tuple_delimiter: str,
    record_delimiter: str,
    completion_delimiter: str,
    include_slot_discipline: bool,
    include_grounded_entity_preference: bool,
    schema_guidance: str,
) -> str:
    """Build the entity-only pass of the two-pass delimiter extraction flow.

    This prompt extracts only entity records. It keeps the same tuple contract
    as the one-pass path so downstream validators and graph builders do not need
    a separate parser for the proof slice.
    """

    entity_type_contract = _build_entity_type_contract(entity_types)
    schema_block = f"\n\n{schema_guidance}" if schema_guidance else ""
    slot_discipline_block = ""
    if include_slot_discipline:
        slot_discipline_block = """

-Slot Discipline-
- emit only entity records in this pass; do not emit relationship records
- when typed entities are required, never emit null, none, unknown, or placeholder entity types; omit the entity instead"""
    grounded_entity_block = ""
    if include_grounded_entity_preference:
        grounded_entity_block = """

-Grounded Entity Preference-
- prefer entities that can be independently pointed to from the text, such as named people, organizations, locations, competitions, awards, diagnoses, titles, works, or explicit dated events and time periods
- if a phrase only summarizes other concrete entities, competitions, or outcomes already named in the text, keep that meaning out of the entity list
- do not emit broad achievement labels, umbrella competition classes, or generic category phrases as standalone entities unless the text presents them as formal named entities"""

    return f"""-Goal-
Extract only the grounded entity inventory from the text.

-Entity Contract-
- entity_name: Name of the entity, capitalized when appropriate
{entity_type_contract}
- entity_description: concise description of the entity
Format each entity as ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>)

-Output Rules-
1. Return only entity records in English as one flat list.
2. Use {record_delimiter} between records.
3. When finished, output {completion_delimiter}.{schema_block}{slot_discipline_block}{grounded_entity_block}

-Text-
{input_text}

Output:
"""


def _build_entity_type_contract(entity_types: list[str]) -> str:
    """Return the entity-type instruction for declared versus open palettes.

    Open schema mode may intentionally provide no declared type list. In that
    case the prompt must still require a stable semantic type label without
    pretending the model is constrained to a hidden fallback palette.
    """

    if entity_types:
        joined_entity_types = ", ".join(entity_types)
        return f"- entity_type: One of the following types when applicable: [{joined_entity_types}]"
    return (
        "- entity_type: short lowercase semantic class that best fits the entity; "
        "use a stable reusable type label, not a placeholder or document-specific phrase"
    )


def build_relationship_extraction_prompt(
    *,
    input_text: str,
    entity_inventory_text: str,
    relation_types: list[str],
    tuple_delimiter: str,
    record_delimiter: str,
    completion_delimiter: str,
    include_relation_name: bool,
    include_relation_keywords: bool,
) -> str:
    """Build the relationship-only pass constrained to a validated entity inventory.

    The entity inventory is part of the contract: relationships may only use the
    source and target entity names provided there. This keeps closure truthful
    without synthesizing missing nodes from relationship endpoints.
    """

    relationship_fields = []
    relationship_format_fields = [
        "<source_entity>",
        "<target_entity>",
    ]
    if include_relation_name:
        relationship_fields.append(
            "- relation_name: concise normalized label for the relationship, such as employed by or located in"
        )
        relationship_format_fields.append("<relation_name>")
    relationship_fields.append(
        "- relationship_description: concise explanation of why the source and target are related"
    )
    relationship_format_fields.append("<relationship_description>")
    if include_relation_keywords:
        relationship_fields.append(
            "- relationship_keywords: comma-separated high-level keywords describing the relationship"
        )
        relationship_format_fields.append("<relationship_keywords>")
    relationship_fields.append(
        "- relationship_strength: numeric score indicating how strong the relationship is"
    )
    relationship_format_fields.append("<relationship_strength>")

    relation_type_text = ", ".join(relation_types) if relation_types else "any appropriate relation type"
    relationship_fields_text = "\n".join(relationship_fields)
    relationship_format = tuple_delimiter.join(relationship_format_fields)

    return f"""-Goal-
Extract only relationships between entities from the provided entity inventory.

-Entity Inventory-
Use source_entity and target_entity values only from this validated inventory. If the text suggests a relationship to something outside this inventory, omit that relationship.
{entity_inventory_text}

-Relationship Contract-
Use relation names from this set when applicable: [{relation_type_text}]
{relationship_fields_text}
Format each relationship as ("relationship"{tuple_delimiter}{relationship_format})

-Output Rules-
1. Return only relationship records in English as one flat list.
2. Do not emit entity records in this pass.
3. Use entity names exactly as they appear in the inventory.
4. Use {record_delimiter} between records.
5. When finished, output {completion_delimiter}.

-Text-
{input_text}

Output:
"""
