from brains.casual.brain import PROFILE as CASUAL_PROFILE
from brains.deep.brain import PROFILE as DEEP_PROFILE
from brains.profile import BrainProfile
from brains.smart.brain import PROFILE as SMART_PROFILE


BRAIN_PROFILES: dict[str, BrainProfile] = {
    profile.key: profile
    for profile in (CASUAL_PROFILE, SMART_PROFILE, DEEP_PROFILE)
}

__all__ = ["BRAIN_PROFILES", "BrainProfile"]

