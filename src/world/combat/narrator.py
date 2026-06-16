"""Re-export shim — get_or_create_narrator_persona now lives in world.scenes.narrator."""

from world.scenes.narrator import NARRATOR_PERSONA_NAME, get_or_create_narrator_persona

__all__ = ["NARRATOR_PERSONA_NAME", "get_or_create_narrator_persona"]
