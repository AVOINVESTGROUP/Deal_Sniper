"""Адаптеры реальных источников автомобильных объявлений."""

from src.sources.carswitch import CarSwitchSource
from src.sources.dubicars import DubiCarsSource

__all__ = ["CarSwitchSource", "DubiCarsSource"]
