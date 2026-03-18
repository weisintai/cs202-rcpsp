from __future__ import annotations

from ..models import Instance


def resource_intensity(instance: Instance) -> list[float]:
    values = [0.0] * instance.n_activities
    for activity in range(instance.n_activities):
        intensity = 0.0
        for resource in range(instance.n_resources):
            capacity = instance.capacities[resource]
            if capacity == 0:
                continue
            intensity += instance.demands[activity][resource] / capacity
        values[activity] = intensity
    return values
