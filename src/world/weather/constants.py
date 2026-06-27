"""Constants for the weather system (#1522)."""

# Global per-month temperature shift applied on top of every region's flat climate
# baseline (#1522). The IC clock's month (``game_clock`` → ``get_ic_now().month``)
# indexes this curve; the value is *added* to a climate's signed ``temperature`` before
# it decomposes onto the COLD/HEAT exposure axes. A smooth build-and-lower curve:
# coldest in deep winter (Jan), hottest in high summer (Jul), crossing neutral in the
# shoulder months. Because the shift is global and the baseline is per-region, a
# temperate region crosses into real COLD in winter while a tropical region's high
# baseline keeps it warm year-round ("no real winter") for free.
#
# PLACEHOLDER magnitudes — the *shape* matches the design; the numbers are a later
# author-tuning pass (grep PLACEHOLDER). Moisture has no monthly curve: its seasonal
# variation rides on the weather layer (rain-type weather is season-gated), not here.
MONTH_TEMPERATURE_SHIFT: dict[int, int] = {
    1: -50,  # January — coldest
    2: -35,  # February — very cold
    3: -15,  # March — cool
    4: 5,  # April — warming
    5: 20,  # May — warmer
    6: 35,  # June — hot
    7: 45,  # July — hottest
    8: 35,  # August — hot
    9: 15,  # September — less warm
    10: 0,  # October — neutral
    11: -15,  # November — cooler
    12: -35,  # December — very cold
}
