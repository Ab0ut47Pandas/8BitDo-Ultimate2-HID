"""Shared statistics for saved controller captures. No device access."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import statistics
import struct


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def distribution(values):
    values = sorted(set(values))
    steps = [b-a for a, b in zip(values, values[1:])]
    return dict(unique=len(values), min=min(values) if values else None,
                max=max(values) if values else None, adjacent_step_gcd=math.gcd(*steps),
                common_adjacent_steps=Counter(steps).most_common(5))


def cadence(ticks, frequency):
    gaps = [(b-a)*1000/frequency for a, b in zip(ticks, ticks[1:])]
    return dict(events=len(ticks),
                observed_hz=(len(ticks)-1)*frequency/(ticks[-1]-ticks[0]) if len(ticks)>1 else None,
                median_interval_ms=statistics.median(gaps) if gaps else None,
                p95_interval_ms=sorted(gaps)[int(.95*(len(gaps)-1))] if gaps else None)
