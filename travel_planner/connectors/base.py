from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..schemas import SourceStatus


@dataclass(slots=True)
class SourceCheck:
    source: str
    state: str
    detail: str
    checked_at: datetime

    def to_status(self) -> SourceStatus:
        return SourceStatus(
            source=self.source,
            state=self.state,  # type: ignore[arg-type]
            detail=self.detail,
            checked_at=self.checked_at,
        )


class ConnectorError(RuntimeError):
    """Recoverable connector error."""
