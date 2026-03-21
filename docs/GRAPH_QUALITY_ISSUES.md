# Graph Quality Issues

Issues found during MuSiQue benchmark iteration that need graph-level fixes.

## Entity Description Gaps

| Entity | Issue | Impact |
|--------|-------|--------|
| `godiva` | Empty description — no birthplace/origin info | Agent must infer Mercia via 2-hop (Godiva → Leofric → Earl of Mercia), stochastic |
| `saint peter s basilica` vs `st  peter s basilica` | Duplicate entities with different neighbors | Fixed with alias expansion, but canonicalization at build time would be better |

## Missing Relationships

| Expected Edge | Source Chunk | Impact |
|---------------|-------------|--------|
| `godiva → born_in → mercia` | chunk_84 (Leofric, Earl of Mercia, and his wife Godiva) | Agent sometimes picks Leicester or Croyland Abbey instead |
| `james watt → worked_at → university of glasgow` | chunk_439 | Fixed by HyPE — VDB search now bridges vocabulary gap |

## Entity Canonicalization Needed

The graph has duplicate entities that should be merged:
- `saint peter s basilica` / `st  peter s basilica` / `the papal basilica of st  peter in the vatican`
- Likely many more — need systematic dedup pass (RAKG VectJudge+SameJudge pattern)

## Chunk Linkage Gaps

| Chunk | Content | Missing Link |
|-------|---------|-------------|
| chunk_608 | "council members and mayor serve four-year terms" | Not linked to Tucson entity — agent can't find it via graph traversal |

## Recommendations

1. **Entity description enrichment**: After graph build, fill empty descriptions from chunk text
2. **Entity canonicalization**: RAKG-style VectJudge+SameJudge to merge duplicate entities
3. **Relationship extraction improvement**: Extract born_in/worked_at/educated_at as explicit edges
4. **HyPE (implemented)**: Bridges vocabulary gaps at VDB search time
