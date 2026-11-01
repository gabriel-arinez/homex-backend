"""ASR-OPT-04 preregistered isolated profiles; no operational configuration."""

from copy import deepcopy

VOCABULARY = "melamina tapacanto rieles telescópicos gavetero credenza mesón nogal haya atril"
PROMPT = (
    "Mobiliario a medida: melamina, tapacanto, rieles telescópicos, "
    "gavetero, credenza, mesón, nogal, haya, atril."
)
PROFILES = {
    "baseline": {},
    "hotwords": {"hotwords": VOCABULARY},
    "initial_prompt": {"initial_prompt": PROMPT},
    "beam3": {"beam_size": 3},
    "no_previous_text": {"condition_on_previous_text": False},
}


def kwargs(profile):
    if profile not in PROFILES:
        raise ValueError("Perfil fuera del preregistro")
    return {"language": "es", **deepcopy(PROFILES[profile])}
