from register.observations import Observation
from sampling.protocols import ProtocolVersion


def grade_observation(observation: Observation, protocol: ProtocolVersion) -> bool:
    return observation.microns >= protocol.threshold_microns
