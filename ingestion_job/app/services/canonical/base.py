from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from ingestion_job.app.models.documents import RawDocument, CanonicalDocument

class CanonicalAdapter(ABC):
    @abstractmethod
    def can_handle(self, raw_doc: RawDocument) -> bool:
        pass

    @abstractmethod
    def process(self, raw_doc: RawDocument) -> CanonicalDocument:
        pass
