"""Guard the historical eval against LLIS lessons dated before the mishap they describe."""

import json
import re

import pytest

from lore.data.llis import OUT_PATH
from lore.data.reports import load_reports

# Short names as they appear in lesson titles, keyed by report id.
ALIASES = {
    "apollo1_as204": ["Apollo 1", "Apollo 204", "AS-204"],
    "apollo13": ["Apollo 13"],
    "challenger_rogers_v1": ["Challenger", "51-L"],
    "hubble_optics": ["Hubble"],
    "lewis": ["Lewis Spacecraft"],
    "soho": ["SOHO"],
    "wire": ["WIRE", "Wide-Field Infrared Explorer"],
    "mco_phase1": ["Mars Climate Orbiter", "MCO"],
    "mpl_ds2": ["Mars Polar Lander", "MPL", "Deep Space 2"],
    "contour": ["CONTOUR"],
    "columbia_caib_v1": ["Columbia Accident", "STS-107"],
    "noaa_n_prime": ["NOAA N-Prime", "NOAA-N"],
    "genesis": ["Genesis"],
    "dart": ["DART"],
    "glory_t9": ["Glory"],
    "oco_glory_2019": ["Orbiting Carbon Observatory", "OCO"],
}
MISHAP_WORDS = re.compile(r"\b(mishap|loss|lost|failure|accident|investigation board)\b", re.I)


@pytest.mark.skipif(not OUT_PATH.exists(), reason="run python -m lore.data.llis first")
def test_no_lesson_predates_the_mishap_it_describes():
    lessons = [json.loads(line) for line in OUT_PATH.read_text(encoding="utf-8").splitlines()]
    reports = {r.id: r for r in load_reports()}
    leaks = []
    for report_id, names in ALIASES.items():
        mishap = reports[report_id].mishap_date.isoformat()
        pattern = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
        for lesson in lessons:
            title = lesson["title"]
            if pattern.search(title) and MISHAP_WORDS.search(title) and lesson["date"] < mishap:
                leaks.append((lesson["lesson_number"], lesson["date"], title))
    assert not leaks, f"lessons dated before their mishap (add to llis_date_overrides): {leaks}"
