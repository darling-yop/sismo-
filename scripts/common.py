"""Shared fixtures for the reproducible data and the section 16 cases."""

from domain.models import Zone
from services.scenario import Scenario

STATIONS = ["EST-A", "EST-B", "EST-C"]
ZONES = [Zone("Valle Central", 200.0, 200.0, 500.0, 500.0, True),
         Zone("Costa", 500.0, 0.0, 1000.0, 400.0, False),
         Zone("Altiplano", 0.0, 600.0, 400.0, 1000.0, True)]
CLOCK = "2026-09-07T12:00:00Z"
OLD = "2026-09-01T00:00:00Z"       # > 72 h before CLOCK
YOUNG = "2026-09-07T00:00:00Z"     # 12 h before CLOCK


def zones_json():
    return [{"name": z.name, "x1": z.x1, "y1": z.y1, "x2": z.x2, "y2": z.y2,
             "populated": z.populated} for z in ZONES]


def new_scenario(stress=False):
    sc = Scenario(zones=ZONES, stations=STATIONS)
    if stress:
        sc.set_stress(True)
    return sc


def ev(i, m, h=10.0, x=900.0, y=900.0, t="2026-09-07T10:00:00Z", st="EST-A"):
    return dict(event_id=i, m=m, depth=h, x=x, y=y, time=t, station=st)


def add(sc, i, m, h=10.0, x=900.0, y=900.0, t="2026-09-07T10:00:00Z", st="EST-A"):
    return sc.create_event(i, m, h, x, y, t, st)
