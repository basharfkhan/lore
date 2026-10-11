# Label adjudication: grade-2 disagreements

The LLM judge and the draft labels disagree on these documents, and at least one of them says
**2 (direct precursor)**. For each, read the lesson (linked) and write the grade you believe in
the `your grade` column: 2 same failure mechanism, 1 contributing factor or clearly applicable
practice, 0 not relevant. Rows for mishap reports are marked: the judge saw only one excerpt.

25 rows. Source: evals/results/judge_calibration.json.

## Mars Climate Orbiter lost during Mars orbit insertion

**What actually happened:** Ground software supplied thruster impulse data in English units where the navigation team's models expected metric, so small-force trajectory effects were mis-modelled across a contractor/navigation interface that was never verified, and trajectory discrepancies were not escalated.

| document | draft | judge | judge's reason | your grade |
|---|---|---|---|---|
| [llis-577: Verify CAD/CAM Software Compatibility Between Organizations ](https://llis.nasa.gov/lesson/577) | 1 | 2 | Describes data files exchanged between organizations using incompatible software conventions producing silent, undetected errors, and urges inter-organizational data-format verification—the same mechanism as the unit-mismatched thruster data files. | 1 |

## Genesis sample return capsule parachutes failed to deploy

**What actually happened:** The acceleration switches that start the parachute sequence were designed in an inverted orientation, an error inherited-design reviews and drawing inspections missed because the planned functional test was replaced by inspection.

| document | draft | judge | judge's reason | your grade |
|---|---|---|---|---|
| [llis-1197: Deep Space 2 Telecom Hardware-Software Interaction (1999)](https://llis.nasa.gov/lesson/1197) | 0 | 2 | Documents a planned subsystem test being deleted for schedule reasons, allowing a design/logic error to escape—precisely the mechanism of replacing the planned functional test with inspection. | 1 |
| [llis-1398: SWIFT Power Control Board Harness Wire Reversal](https://llis.nasa.gov/lesson/1398) | 0 | 2 | Same root cause pattern: a reversed/inverted wiring error survived because documentation review and the planned safe-to-mate functional verification were shortcut for schedule rather than performed. | 1 |
| [llis-16: Reversed Installation of a Check Valve Spring (Main Propulsi](https://llis.nasa.gov/lesson/16) | 1 | 2 | Describes exactly the same class of failure—a critical component installed/oriented backwards that escaped detection until a dedicated inspection/test point was added. | 2 |
| [llis-271: Mars Observer Pressure Modulator Infrared Radiometer (PMIRR)](https://llis.nasa.gov/lesson/271) | 0 | 2 | Directly describes an inherited flight-proven design accepted on heritage without in-depth verification, where the original design analysis itself was flawed—the same root cause as the inherited inverted g-switch. | 1 |
| [llis-312: ACTS Pyro Separation Band Anomaly (Shuttle Orbiter)](https://llis.nasa.gov/lesson/312) | 1 | 2 | An embedded pyrotechnic-initiation circuit design error survived comprehensive design reviews and verification because the tests validated the erroneous design rather than the end function — essentially the same root cause as the inverted acceleration switches. | 0 |
| [llis-342: Critical Hardware Functional Verification](https://llis.nasa.gov/lesson/342) | 1 | 2 | States directly that safety-critical pyro deployment hardware must undergo rigorous end-to-end functional verification rather than review-based acceptance, addressing the exact verification gap that hid the inverted switch design. | 0 |
| [llis-346: Use of Heritage Designs on the Mars Observer](https://llis.nasa.gov/lesson/346) | 2 | 1 | Warns that heritage subsystems reused without requalification for a new multi-year mission can be inappropriate, a contributing factor but focused on environmental mismatch rather than an undetected inherited design error missed by inspection. | |
| [llis-492: Galileo High Gain Antenna (HGA) Failure (1991)](https://llis.nasa.gov/lesson/492) | 0 | 2 | Same root cause pattern: a deployment mechanism inherited from an earlier program where inheritance and design reviews failed to reveal a latent design flaw that was never verified by adequate testing, leading to deployment failure. | |
| [llis-634: Transient Start-up Performance of the WIRE Pyro Electronics ](https://llis.nasa.gov/lesson/634) | 1 | 2 | Pyrotechnic initiation electronics contained a design error that subsystem/system functional verification failed to catch because there was no end-to-end test in as-flown configuration — the same root cause as the unverified parachute-firing g-switch. | |
| [llis-637: Wide-Field Infrared Explorer (WIRE) Mishap Investigation Boa](https://llis.nasa.gov/lesson/637) | 1 | 2 | The WIRE board report attributes loss to a pyro-firing logic design error that escaped verification, the same class of inadequately tested parachute/pyro initiation avionics design flaw. | |
| [llis-938: Probable Scenario for Mars Polar Lander Mission Loss (1998)](https://llis.nasa.gov/lesson/938) | 1 | 2 | Same mechanism class: an entry/landing-critical sensor with a wiring error and an untested failure mode, where the full functional deployment test that would have exposed it was not run, causing mission loss. | |
| report-contour (report, judge saw one excerpt) | 1 | 2 | Names 'Project Reliance on Analysis by Similarity' (heritage) without verification as a mishap root cause, the same root cause that let the inverted inherited acceleration switches escape detection. | |

## NOAA N-Prime satellite fell off its turnover cart

**What actually happened:** Another program had removed the bolts securing the shared turnover cart's adapter plate without recording it, and the operations team moved the satellite without verifying the cart configuration as the procedure required.

| document | draft | judge | judge's reason | your grade |
|---|---|---|---|---|
| [llis-1089: TOPEX/POSEIDON Spacecraft Handling Anomaly Special Review Bo](https://llis.nasa.gov/lesson/1089) | 2 | 1 | Spacecraft handling mishap with a test-support fixture during a routine move, highlighting handling-fixture adequacy and procedural discipline, but the cause was lift/CG instability rather than unverified shared-cart configuration. | |
| [llis-119: Solid Rocket Motor (SRM) Segment and Handling Ring Mating](https://llis.nasa.gov/lesson/119) | 1 | 2 | Nearly identical precursor: bolts were removed from the segment handling/lifting fixture without work authorization or record, and the segment was hoisted and rotated to horizontal before anyone noticed the missing hardware. | |
| [llis-1213: Configuration Control at All Levels of Change](https://llis.nasa.gov/lesson/1213) | 2 | 1 | Highlights undocumented/uncommunicated hardware changes escaping configuration control, a contributing factor to the unrecorded bolt removal, but the mechanism described is an EVA checklist mismatch. | |
| [llis-240: Pneumatic Explosion](https://llis.nasa.gov/lesson/240) | 0 | 2 | Nearly identical mechanism: bolts removed during other work and not replaced or recorded, and the next crew operated the hardware without verifying assembly completeness. | |
| [llis-267: TOPEX/POSEIDON Near-Drop Incident](https://llis.nasa.gov/lesson/267) | 2 | 1 | Warns that handling fixtures inherited from another program must be re-verified for the current configuration and load, a preventive practice for shared GSE but a different (stability/CG) mechanism. | |
| [llis-521: Inspection Oversights Led to Model Failure](https://llis.nasa.gov/lesson/521) | 0 | 2 | Describes the same mechanism—required fasteners missing from hardware and multiple inspections failing to detect the missing fasteners before use, leading to failure. | |
| [llis-918: Evolution of Mission Requirements for Support Equipment](https://llis.nasa.gov/lesson/918) | 1 | 2 | Same mechanism: flight hardware dropped from shared ground handling fixture that was in an unassessed configuration (a securing pin removed) with procedures that failed to require verification of fixture configuration. | |
| [llis-991: Planning and Conduct of Hazardous Tests Require Extra Precau](https://llis.nasa.gov/lesson/991) | 0 | 2 | Directly parallel: ground support equipment at a contractor I&T facility was disassembled/reinstalled and maintained without records or verification, and crews deviated from the formal procedure, causing hardware damage. | |

## Space Shuttle Columbia broke up during re-entry

**What actually happened:** Foam shed from the external tank during ascent struck and breached a wing leading-edge panel; recurring foam strikes had been accepted as in-family, and engineering concerns about the damage did not reach decision makers.

| document | draft | judge | judge's reason | your grade |
|---|---|---|---|---|
| report-challenger_rogers_v1 (report, judge saw one excerpt) | 2 | 1 | Describes how critically the orbiter depends on its thermal protection, with leading-edge entry temperatures near 2,750°F, underscoring the consequence of a breached leading edge without describing the foam-strike mechanism or the flawed acceptance process. | |

## Mars Polar Lander lost during descent

**What actually happened:** A transient touchdown-sensor signal generated when the landing legs deployed was latched by flight software and shut the descent engines off at altitude; the requirement to ignore the transient never reached the software, and testing did not catch it.

| document | draft | judge | judge's reason | your grade |
|---|---|---|---|---|
| [llis-403: Thrusters Fired on Launch Pad (1975)](https://llis.nasa.gov/lesson/403) | 2 | 1 | Flight software logic active during a phase where it should have been inhibited caused unintended propulsion actuation, a closely related practice (phase-constrained enabling) though not the transient-latching mechanism. | |
| [llis-637: Wide-Field Infrared Explorer (WIRE) Mishap Investigation Boa](https://llis.nasa.gov/lesson/637) | 0 | 2 | The WIRE board report documents inadvertent actuation caused by unconsidered transient signals latching control logic into a false state and undetected by subsystem/system testing — the same failure pattern as the touchdown-sensor transient. | |
| report-wire (report, judge saw one excerpt) | 1 | 2 | Describes the same class of root cause: an unmodeled electrical transient causing premature actuation that testing failed to reveal because non-flight simulators produced false-positive results. | |
