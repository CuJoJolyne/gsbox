"""Frequency counter for 3DGS attribute analysis.

Counts unique (R,G,B) triplets in scale/color/rotation channels
to estimate codebook compression potential.
"""
from typing import List, Tuple, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from ..core.splat_data import SplatData


class FrequencyCounter:
    """Counts frequency of 3-channel attribute triplets."""

    def __init__(self) -> None:
        self._freq: dict = {}
        self.total_count: int = 0

    def count_by_scale(self, data: 'SplatData') -> None:
        """Count frequency of (scale_x, scale_y, scale_z) encoded as uint8."""
        self.total_count = data.count
        encoded = np.empty((data.count, 3), dtype=np.uint8)
        for ax in range(3):
            encoded[:, ax] = np.clip(
                np.round((data.scale[:, ax].astype(np.float64) + 10.0) * 16.0), 0, 255
            ).astype(np.uint8)
        unique, counts = np.unique(
            encoded.view([('', np.uint8, 3)]), return_counts=True
        )
        for i in range(len(unique)):
            key = tuple(int(b) for b in unique[i][0])
            self._freq[key] = int(counts[i])

    def count_by_color(self, data: 'SplatData') -> None:
        """Count frequency of (R, G, B) color triplets."""
        self.total_count = data.count
        encoded = data.color[:, :3].copy()
        unique, counts = np.unique(
            encoded.view([('', np.uint8, 3)]), return_counts=True
        )
        for i in range(len(unique)):
            key = tuple(int(b) for b in unique[i][0])
            self._freq[key] = int(counts[i])

    def count_by_rotation(self, data: 'SplatData') -> None:
        """Count frequency of (rot_x, rot_y, rot_z) rotation triplets."""
        self.total_count = data.count
        encoded = data.rotation[:, 1:4].copy()
        unique, counts = np.unique(
            encoded.view([('', np.uint8, 3)]), return_counts=True
        )
        for i in range(len(unique)):
            key = tuple(int(b) for b in unique[i][0])
            self._freq[key] = int(counts[i])

    def get_top_n(self, top_n: int = 256) -> Tuple[List[Tuple[int, int, int]], List[int]]:
        """Return (keys, counts) sorted by descending frequency, limited to top_n."""
        sorted_items = sorted(self._freq.items(), key=lambda x: -x[1])
        if len(sorted_items) > top_n:
            sorted_items = sorted_items[:top_n]
        keys = [k for k, _ in sorted_items]
        counts = [v for _, v in sorted_items]
        return keys, counts

    def summary(self, top_n: int = 256) -> str:
        """Return a human-readable summary of compression potential."""
        keys, counts = self.get_top_n(top_n)
        covered = sum(counts)
        unique = len(keys)
        pct = 100.0 * covered / max(self.total_count, 1)
        old_bytes = self.total_count * 19
        new_bytes = unique * 3 + covered + (self.total_count - covered) * 4 + self.total_count * 16
        ratio = 100.0 * new_bytes / max(old_bytes, 1)
        return (
            f"covered: {covered}/{self.total_count} ({pct:.1f}%), "
            f"unique entries: {unique}, "
            f"compressed size: {ratio:.1f}% of original ({old_bytes} -> {new_bytes} bytes)"
        )

    def __len__(self) -> int:
        return len(self._freq)
