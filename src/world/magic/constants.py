"""
Constants for the resonance and facets system.

This module defines the 24 curated resonances organized into:
- 8 Celestial/Abyssal pairs (moral poles - virtue vs vice)
- 4 Primal pairs (morally neutral natural states)

Note: ResonanceAffinity enum is defined in world.mechanics.constants
since it's used by the ModifierType model.
"""

# Celestial Resonances (8 virtues)
# Each tuple: (name, description)
CELESTIAL_RESONANCES: list[tuple[str, str]] = [
    ("Bene", "Give freely, sacrifice for others"),
    ("Liberare", "Free others from bonds and oppression"),
    ("Fidelis", "Keep bonds, maintain loyalty and faith"),
    ("Misera", "Show mercy, spare enemies at personal risk"),
    ("Fortis", "Stand firm with courage despite danger"),
    ("Honoris", "Conduct oneself with honor and fairness"),
    ("Verax", "Seek and speak truth"),
    ("Copperi", "Maintain hope in the face of despair"),
]

# Abyssal Resonances (8 vices - opposites of celestial)
# Each tuple: (name, description)
ABYSSAL_RESONANCES: list[tuple[str, str]] = [
    ("Praedari", "Ruthlessly take what is wanted"),
    ("Dominari", "Control and dominate others"),
    ("Perfidus", "Betray bonds for personal gain"),
    ("Maligna", "Harm others with malicious intent"),
    ("Tremora", "Break others through fear and terror"),
    ("Saevus", "Act with brutal savagery"),
    ("Insidia", "Deceive and manipulate others"),
    ("Despari", "Crush hope and spread despair"),
]

# Celestial/Abyssal pairs (virtue vs vice opposites)
# Each tuple: (celestial_name, abyssal_name)
CELESTIAL_ABYSSAL_PAIRS: list[tuple[str, str]] = [
    ("Bene", "Praedari"),
    ("Liberare", "Dominari"),
    ("Fidelis", "Perfidus"),
    ("Misera", "Maligna"),
    ("Fortis", "Tremora"),
    ("Honoris", "Saevus"),
    ("Verax", "Insidia"),
    ("Copperi", "Despari"),
]

# Primal Resonances (8 morally neutral natural states)
# Each tuple: (name, description)
PRIMAL_RESONANCES: list[tuple[str, str]] = [
    ("Firma", "Lasting, durable, steady"),
    ("Vola", "Fleeting, swift, ephemeral"),
    ("Audax", "Reckless, bold, instinctive action"),
    ("Medita", "Patient, planned, calculating"),
    ("Arderi", "Emotionally driven, passionate, expressive"),
    ("Sereni", "Controlled, calm, reserved"),
    ("Fera", "Natural, instinctive, wild"),
    ("Civitas", "Trained, civilized, refined"),
]

# Primal pairs (neutral opposites)
# Each tuple: (first_name, second_name)
PRIMAL_PAIRS: list[tuple[str, str]] = [
    ("Firma", "Vola"),
    ("Audax", "Medita"),
    ("Arderi", "Sereni"),
    ("Fera", "Civitas"),
]
