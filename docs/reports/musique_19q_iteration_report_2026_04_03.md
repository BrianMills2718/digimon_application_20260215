# Benchmark Iteration Report

- Dataset: `MuSiQue`
- Model: `openrouter/openai/gpt-5.4-mini`
- Runs: `5`
- Question count: `19`
- Mean LLM_EM: `43.16%`
- Sample stdev: `12.00` pts
- Range: `31.58%` to `57.89%`
- Total cost across runs: `$5.8416`

## Run Distribution

| Run | LLM_EM | EM | Completed | Cost | Artifact |
|-----|--------|----|-----------|------|----------|
| 1 | 31.58% | 26.32% | 19 | $0.7994 | `MuSiQue_gpt-5-4-mini_consolidated_20260402T113854Z.json` |
| 2 | 57.89% | 42.11% | 19 | $1.2194 | `MuSiQue_gpt-5-4-mini_consolidated_20260403T003635Z.json` |
| 3 | 52.63% | 47.37% | 19 | $1.0704 | `MuSiQue_gpt-5-4-mini_consolidated_20260403T010250Z.json` |
| 4 | 42.11% | 31.58% | 19 | $1.4809 | `MuSiQue_gpt-5-4-mini_consolidated_20260403T040050Z.json` |
| 5 | 31.58% | 21.05% | 19 | $1.2715 | `MuSiQue_gpt-5-4-mini_consolidated_20260403T045308Z.json` |

## Stability Summary

- Stable pass: `3` questions
- Stochastic: `11` questions
- Stable fail: `5` questions

## Per-Question Stability

| Question ID | Pass Rate | Classification | Latest Pred | Gold | Distinct Predictions |
|-------------|-----------|----------------|-------------|------|----------------------|
| 2hop__13548_13529 | 60.0% (3/5) | stochastic | `2009` | `June 1982` | `June 1982`, `2002`, `2009` |
| 2hop__170823_120171 | 100.0% (5/5) | stable_pass | `1986` | `1986` | `1986`, `January 1986` |
| 2hop__199513_801817 | 0.0% (0/5) | stable_fail | `` | `Nazareth` | ``, `Nauvoo, Illinois`, `not stated` |
| 2hop__354635_174222 | 0.0% (0/5) | stable_fail | `Adelphia Communications Corporation` | `Time Warner Cable` | `Adelphia Communications Corporation`, `Comcast`, `` |
| 2hop__511296_577502 | 100.0% (5/5) | stable_pass | `Maria Shriver` | `Maria Shriver` | `Maria Shriver` |
| 2hop__511454_120259 | 20.0% (1/5) | stochastic | `unknown` | `918` | ``, `918`, `1870`, `1974` |
| 2hop__619265_45326 | 40.0% (2/5) | stochastic | `52` | `12` | `12`, `52`, `` |
| 2hop__655505_110949 | 100.0% (5/5) | stable_pass | `11 September 1962` | `11 September 1962` | `11 September 1962` |
| 2hop__731956_126089 | 80.0% (4/5) | stochastic | `Johan Remkes` | `Johan Remkes` | `Johan Remkes`, `` |
| 2hop__766973_770570 | 80.0% (4/5) | stochastic | `` | `Rockland County` | `Rockland County`, `` |
| 3hop1__136129_87694_124169 | 20.0% (1/5) | stochastic | `unknown` | `1952` | `Saint Peter`, ``, `1952`, `unknown` |
| 3hop1__305282_282081_73772 | 20.0% (1/5) | stochastic | `1861` | `December 14, 1814` | ``, `December 14, 1814`, `2006`, `January 8, 1815` |
| 3hop1__820301_720914_41132 | 0.0% (0/5) | stable_fail | `2` | `22` | `1`, ``, `0`, `2` |
| 3hop1__849312_503371_21711 | 80.0% (4/5) | stochastic | `1416` | `built in the 15th century` | `15th century`, ``, `1416` |
| 3hop1__9285_5188_23307 | 40.0% (2/5) | stochastic | `July` | `mid-June` | `June`, `July`, `March` |
| 4hop1__152562_5274_458768_33633 | 20.0% (1/5) | stochastic | `2011` | `August 3, 1769` | ``, `Universal Music Group`, `August 3, 1769`, `Heidelberg` |
| 4hop1__94201_642284_131926_89261 | 60.0% (3/5) | stochastic | `Mississippi River` | `the Mississippi River Delta` | `Mississippi River`, ``, `Minneapolis`, `Mississippi River delta` |
| 4hop2__71753_648517_70784_79935 | 0.0% (0/5) | stable_fail | `1961` | `1930` | `1961`, ``, `1921`, `January 21, 1991` |
| 4hop3__754156_88460_30152_20999 | 0.0% (0/5) | stable_fail | `Myanmar` | `The dynasty regrouped and defeated the Portuguese` | ``, `Laos`, `expelled by the Portuguese`, `economically independent` |

## Latest-Run Failure Families

| Failure Class | Count | Representative IDs |
|---------------|-------|--------------------|
| none | 10 | `2hop__13548_13529`, `3hop1__9285_5188_23307`, `2hop__511454_120259`, `4hop2__71753_648517_70784_79935`, `4hop1__152562_5274_458768_33633` |
| retrieval | 2 | `2hop__766973_770570`, `2hop__199513_801817` |
| composability | 1 | `3hop1__136129_87694_124169` |
