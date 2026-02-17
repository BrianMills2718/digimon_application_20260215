# HotpotQA Dataset Errata

Gold answers that are incorrect or unsupported by the provided corpus.

## HotpotQA_200

### q21 — Gold answer "Sonic" is wrong
- **Question**: "This singer of A Rather Blustery Day also voiced what hedgehog?"
- **Gold**: Sonic
- **Correct**: Dr. Robotnik (not a hedgehog)
- **Evidence**: Corpus doc 214 says "He is known for voicing...Dr. Robotnik from 'Sonic the Hedgehog'". Cummings voiced Robotnik (a human villain), not Sonic. The question presupposes he voiced a hedgehog, but the corpus contradicts this. Dataset authors likely extracted "Sonic" from the franchise name without reading which character he actually voiced.

### q32 — Gold answer "Charles Eugène" is wrong
- **Question**: "Which French ace pilot and adventurer fly L'Oiseau Blanc"
- **Gold**: Charles Eugène
- **Correct**: Charles Nungesser
- **Evidence**: Corpus says "Charles Eugène Jules Marie Nungesser" (full name) and "Charles Nungesser and François Coli" flew L'Oiseau Blanc. The gold answer extracted just the first two given names — nobody refers to him as "Charles Eugène." His common name is Charles Nungesser.

### q15 — Question says "country" but means "county"
- **Question**: "Brown State Fishing Lake is in a country that has a population of how many inhabitants?"
- **Gold**: 9,984
- **Issue**: Brown State Fishing Lake is in a **county**, not a country. The question says "country" which is wrong. 9,984 is the county population. Any agent reasoning correctly about "country" would look for a national population, not a county one.
