"""Data-source labels. Anything that is not LIVE kRPC data must be shown as such."""

from enum import Enum


class DataSource(Enum):
    LIVE = "LIVE"
    MOCK = "MOCK"
