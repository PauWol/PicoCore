
def stats_from_samples(self, samples:list[float]) -> tuple[int, float, float, float, float]:
    """Return (count, mean, var, minv, maxv). var is population variance."""
    if not samples:
        return 0, None, None, None, None
    n = len(samples)
    mn = min(samples)
    mx = max(samples)
    mean = sum(samples) / n
    s2 = sum(i * i for i in samples)
    var = (s2 / n) - (mean * mean)
    if var < 0:
        var = 0.0
    return n, mean, var, mn, mx
