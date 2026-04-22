from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Deque, Generic, TypeVar

T = TypeVar("T")


class RingBuffer(Generic[T]):
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")

        self._capacity = capacity
        self._items: Deque[T] = deque()
        self._dropped_total = 0
        self._lock = Lock()

    @property
    def dropped_total(self) -> int:
        with self._lock:
            return self._dropped_total

    def push(self, item: T) -> None:
        with self._lock:
            if len(self._items) >= self._capacity:
                self._items.popleft()
                self._dropped_total += 1
            self._items.append(item)

    def pop(self) -> T | None:
        with self._lock:
            if not self._items:
                return None
            return self._items.popleft()
