# A gift's resonance is the resonance of its woven thread

Whether a gift manifests as **Abyssal, Celestial, or Primal is set by the resonance of the thread
woven into it**, not by a fixed property of the gift — so the same gift (e.g. *Travel*) reads as a
different affinity for different wielders, which is what turns the (gift × resonance) pair into real
per-character specialization. This **supersedes** the current model where `Gift.resonances` is a
fixed authored M2M consumed directly at cast time (power terms, resonance-environment, defilement);
those sites must instead read the wielder's gift-thread resonance. We rejected innately-aligned gifts
because fixed alignment makes every wielder of a gift identical — the opposite of the
dazzling-combinations goal. Combined with the character's path, this resonance also drives how the
gift's techniques specialize — see the shared specialization engine (ADR-0055).

> Status: accepted · Source: design discussion 2026-06-27 · Confidence: verify against code — changes `Gift.resonances` consumers in `world/magic/services`
