def preview_sample_indices(*, frame_count: int, sample_count: int) -> list[int]:
    if frame_count <= 1:
        return [0] * sample_count
    indices: list[int] = []
    for offset in range(1, sample_count + 1):
        position = (frame_count - 1) * (offset / (sample_count + 1))
        indices.append(max(0, min(frame_count - 1, int(round(position)))))
    return indices


def unique_sample_indices(*, frame_count: int, sample_count: int) -> list[int]:
    if frame_count <= 0:
        return []
    safe_sample_count = max(1, min(sample_count, frame_count))
    step = frame_count / (safe_sample_count + 1)
    indices = []
    for sample_index in range(safe_sample_count):
        candidate = int(round((sample_index + 1) * step))
        indices.append(max(0, min(frame_count - 1, candidate)))
    return sorted(set(indices))
