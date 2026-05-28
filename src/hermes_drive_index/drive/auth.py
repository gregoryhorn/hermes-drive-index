"""OAuth/auth seams for Drive clients.

Phase E placeholder: the migrated prototype currently reuses the existing Hermes
Google Workspace helper. Later phases will move that behind a CredentialProvider
protocol here.
"""

from __future__ import annotations

from typing import Protocol, Any


class CredentialProvider(Protocol):
    def build_service(self, service_name: str, version: str) -> Any: ...
