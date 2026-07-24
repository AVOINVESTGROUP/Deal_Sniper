"""Адаптеры реальных источников автомобильных объявлений."""

from src.sources.cars24 import Cars24Source
from src.sources.carswitch import CarSwitchSource
from src.sources.dubicars import DubiCarsSource

__all__ = ["Cars24Source", "CarSwitchSource", "DubiCarsSource"]
