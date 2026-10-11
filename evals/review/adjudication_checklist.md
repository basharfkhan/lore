# Label adjudication (checklist version)

For each row, open the lesson and answer two yes/no questions, **A** and **B**, which are stated
at the top of each section. Write `y` or `n` in each column. You do not pick a grade: both yes
is a 2, one yes is a 1, neither is a 0.

Answer `y` only if the lesson is really about that thing, not if it just mentions it in passing.
If you cannot decide, write `?` and move on.

Rows you already graded show your earlier answer; fill in A and B for those too so every row
is graded the same way. Mishap reports are left out (the judge saw only one excerpt of each).

## Mars Climate Orbiter lost during Mars orbit insertion

**What actually happened:** Ground software supplied thruster impulse data in English units where the navigation team's models expected metric, so small-force trajectory effects were mis-modelled across a contractor/navigation interface that was never verified, and trajectory discrepancies were not escalated.

- **A:** Is the lesson about this? Data or quantities passed between two teams, organisations or pieces of software, where the conventions did not match or the interface was never verified.
- **B:** Is the lesson about this? Small forces from thrusters or attitude control affecting the trajectory or navigation.

| lesson | A (y/n) | B (y/n) | your earlier grade |
|---|---|---|---|
| [llis-577: Verify CAD/CAM Software Compatibility Between Organizations Before Pro](https://llis.nasa.gov/lesson/577) | y | n | 1 |

## Genesis sample return capsule parachutes failed to deploy

**What actually happened:** The acceleration switches that start the parachute sequence were designed in an inverted orientation, an error inherited-design reviews and drawing inspections missed because the planned functional test was replaced by inspection.

- **A:** Is the lesson about this? A part, sensor or connection that was designed, installed or wired backwards, inverted or in the wrong orientation or polarity.
- **B:** Is the lesson about this? An error that escaped because a functional test was skipped or replaced by review or inspection, or because an inherited design was trusted without being re-verified.

| lesson | A (y/n) | B (y/n) | your earlier grade |
|---|---|---|---|
| [llis-1197: Deep Space 2 Telecom Hardware-Software Interaction (1999)](https://llis.nasa.gov/lesson/1197) | n | y | 1 |
| [llis-1398: SWIFT Power Control Board Harness Wire Reversal](https://llis.nasa.gov/lesson/1398) | y | y | 2 |
| [llis-16: Reversed Installation of a Check Valve Spring (Main Propulsion), Subse](https://llis.nasa.gov/lesson/16) | y | n | 1 |
| [llis-271: Mars Observer Pressure Modulator Infrared Radiometer (PMIRR) Cooler Fa](https://llis.nasa.gov/lesson/271) | n | y | 1 |
| [llis-312: ACTS Pyro Separation Band Anomaly (Shuttle Orbiter)](https://llis.nasa.gov/lesson/312) | n | n | 0 |
| [llis-342: Critical Hardware Functional Verification](https://llis.nasa.gov/lesson/342) | n | n | 0 |
| [llis-346: Use of Heritage Designs on the Mars Observer](https://llis.nasa.gov/lesson/346) | n | y | 1 |
| [llis-492: Galileo High Gain Antenna (HGA) Failure (1991)](https://llis.nasa.gov/lesson/492) | n | y | 1 |
| [llis-634: Transient Start-up Performance of the WIRE Pyro Electronics (1999)](https://llis.nasa.gov/lesson/634) | n |y | 1 |
| [llis-637: Wide-Field Infrared Explorer (WIRE) Mishap Investigation Board](https://llis.nasa.gov/lesson/637) | n | y| 1 |
| [llis-938: Probable Scenario for Mars Polar Lander Mission Loss (1998)](https://llis.nasa.gov/lesson/938) |n |y | 1 |

## NOAA N-Prime satellite fell off its turnover cart

**What actually happened:** Another program had removed the bolts securing the shared turnover cart's adapter plate without recording it, and the operations team moved the satellite without verifying the cart configuration as the procedure required.

- **A:** Is the lesson about this? Hardware or support equipment left in a changed or unsafe state by earlier work that was not recorded or communicated.
- **B:** Is the lesson about this? The next team moved or operated it without checking its configuration first.

| lesson | A (y/n) | B (y/n) | your earlier grade |
|---|---|---|---|
| [llis-1089: TOPEX/POSEIDON Spacecraft Handling Anomaly Special Review Board Final ](https://llis.nasa.gov/lesson/1089) | n | n | 0 |
| [llis-119: Solid Rocket Motor (SRM) Segment and Handling Ring Mating](https://llis.nasa.gov/lesson/119) | y | y | 2 |
| [llis-1213: Configuration Control at All Levels of Change](https://llis.nasa.gov/lesson/1213) | y | n | 1 |
| [llis-240: Pneumatic Explosion](https://llis.nasa.gov/lesson/240) | y | y | 2 |
| [llis-267: TOPEX/POSEIDON Near-Drop Incident](https://llis.nasa.gov/lesson/267) | n | n | 0 |
| [llis-521: Inspection Oversights Led to Model Failure](https://llis.nasa.gov/lesson/521) | y | n | 1 |
| [llis-918: Evolution of Mission Requirements for Support Equipment](https://llis.nasa.gov/lesson/918) | n | n | 0 |
| [llis-991: Planning and Conduct of Hazardous Tests Require Extra Precautions (200](https://llis.nasa.gov/lesson/991) | y | y | 2 |

## Mars Polar Lander lost during descent

**What actually happened:** A transient touchdown-sensor signal generated when the landing legs deployed was latched by flight software and shut the descent engines off at altitude; the requirement to ignore the transient never reached the software, and testing did not catch it.

- **A:** Is the lesson about this? A false, spurious or transient signal or input (often at a deployment, power-up or similar event).
- **B:** Is the lesson about this? Logic, software or a circuit that acted on an input it should have ignored, because it was not filtered, inhibited or limited to the right mission phase.

| lesson | A (y/n) | B (y/n) | your earlier grade |
|---|---|---|---|
| [llis-403: Thrusters Fired on Launch Pad (1975)](https://llis.nasa.gov/lesson/403) | n | y | 1 |
| [llis-637: Wide-Field Infrared Explorer (WIRE) Mishap Investigation Board](https://llis.nasa.gov/lesson/637) | y | y | 2 |
