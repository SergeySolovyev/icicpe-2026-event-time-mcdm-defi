# ICICPE 2026 Submission Fields

Official submission portal: https://icicpe.org/215-2/

Scholarship form: https://docs.google.com/forms/d/e/1FAIpQLSfTpZc1daFXeJKDbR4btFKRINc0PA5-PArP1s4ygE1rr2Kdxw/viewform

Upload file:
`D:\DeFi\predictive-mcdm-defi\papers\icicpe-scopus-vol2-submission\submission_packet\Solovev_ICICPE2026_Event_Time_MCDM_DeFi.pdf`

LaTeX source archive, if requested:
`D:\DeFi\predictive-mcdm-defi\papers\icicpe-scopus-vol2-submission\submission_packet\Solovev_ICICPE2026_LaTeX_Source.zip`

## Paper

Title:
Event-Time MCDM Allocation across DeFi Lending Protocols: An HFT-Inspired Methodology with Walk-Forward Validation

Author:
Sergei Solovev

Affiliation:
WorldQuant University

Email:
sssolovjov@gmail.com

Corresponding author:
Sergei Solovev

Suggested discipline:
Computer Science

Suggested primary topic:
Blockchain related to Digital Currency Service and Its Application

Suggested secondary topics:
Artificial Intelligence and Data Mining; Big Data Infrastructure and Analysis

Keywords:
DeFi; decentralized finance; event-time strategy; gas-aware allocation; Cox proportional hazards; walk-forward bootstrap; multi-criteria decision making; high-frequency-trading microstructure; Ethereum mainnet

Short abstract for portal field:
This paper studies event-time, gas-aware allocation across the six largest Ethereum-L1 USDC lending protocols (Aave V3, Compound V3, Spark, Morpho Blue, Euler V2 and Fluid, together about 67% of roughly $54B TVL). Using a per-block panel on which all six protocols are switchable on a single grid, we compare passive allocation, a closed-form gas-aware threshold rule (T1), Ornstein-Uhlenbeck optimal stopping (T2), and Cox proportional-hazards (T3) decision policies. T1, about 50 lines of Python with no trained parameters, outperforms every passive single-protocol hold by 2.2 to 4.1 percentage points annualized across six non-overlapping three-month walk-forward windows (November 2024 to April 2026), with paired-bootstrap p at its 0.0001 resampling floor on all six contrasts (Holm correction computed in the companion reproduction notebook). We then report a post-hoc corrected negative result (an earlier in-sample positive finding was retracted after a leakage audit): the Cox hazards tier, trained strictly out-of-sample and actually executed in replay, does not beat T1. It loses by 5.97 basis points over the honest expanding-window walk-forward and wins 0 of 5 windows. The results suggest that the economically relevant edge in DeFi lending comes from event-time resolution and gas-adjusted switching costs rather than from a learned hazard layer or from slower polling cadences. We discuss limitations around venue depth and capacity, gas measurement, mempool features, and prospective deployment validation.

Cover note / comments to committee:
Dear ICICPE 2026 Program Committee,

Please consider the attached paper for the Computer Science track, primarily under "Blockchain related to Digital Currency Service and Its Application." The manuscript presents an event-time, gas-aware allocation methodology for DeFi lending protocols and reports walk-forward validation on Ethereum-L1 USDC lending markets. The submission lists WorldQuant University as the author's affiliation, as requested for WQU student/alumni participation.

Sincerely,
Sergei Solovev

## Scholarship Form Hints

Affiliation:
WorldQuant University

Advisor:
N/A, unless you have a specific WQU advisor to list.

Attendance mode:
Choose online or in-person according to your plan.

Before submitting, confirm:
- The manuscript is original.
- The manuscript is not currently under review elsewhere.
- WorldQuant University appears as the affiliation in the uploaded PDF.
- The uploaded file is the renamed PDF from this packet.
- If the portal asks for source files, upload the LaTeX source archive from this packet.
- The portal abstract above matches the PDF (2026-09-05 build): T3 is a post-hoc corrected negative result, reported as an out-of-sample LOSS of 5.97 bp
  (0/5 windows). The retracted "+7.03 bp, p = 0.015" claim must not reappear in any field.
