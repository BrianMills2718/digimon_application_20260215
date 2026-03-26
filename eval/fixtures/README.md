# Eval Fixtures

Question ID sets for targeted benchmark iteration. Use with `--questions-file`.

## Canonical Sets

| File | Purpose | Questions |
|------|---------|-----------|
| `musique_19q_diagnostic_ids.txt` | Original 19q diagnostic set from March 23 | 19 |
| `musique_50q_both_fail_ids.txt` | Questions where both baseline AND GraphRAG fail (50q run) | 25 |
| `musique_both_fail_frozen.json` | Frozen both-fail with gold/predicted/tools (19q, older) | 8 |

## Iteration Subsets

| File | Purpose |
|------|---------|
| `musique_2hop_both_fail.txt` | 2-hop failures from 50q (most actionable) |
| `musique_3hop_both_fail.txt` | 3-hop failures from 50q |
| `musique_4hop_both_fail.txt` | 4-hop failures from 50q |
| `musique_regressions.txt` | Questions where baseline passes but GraphRAG fails |
| `musique_5q_regressions.txt` | Earlier regression set (19q, superseded by above) |
| `musique_5q_failing_diagnostic.txt` | Early iteration subset (superseded) |
| `musique_1q_battle.txt` | Single question for targeted testing |
| `musique_3q_fixable.txt` | Early fixable subset (superseded) |

## Usage

```bash
# Run specific question set
make bench-musique  # uses musique_19q_diagnostic_ids.txt

# Or specify directly
python eval/run_agent_benchmark.py --questions-file eval/fixtures/musique_2hop_both_fail.txt ...
```
