from __future__ import annotations

import logging

from googleapiclient.discovery import Resource as GoogleResource  # type: ignore[import-untyped]
from googleapiclient.discovery import build
from langchain_googledrive.utilities.google_drive import (  # type: ignore[import-untyped]
    GoogleDriveAPIWrapper,
    GoogleDriveUtilities,
)
from pangea import PangeaConfig
from pangea.services import AuthZ
from pangea.services.authz import Resource, Subject, Tuple
from pydantic import SecretStr

logger = logging.getLogger(__name__)


GDRIVE_ROLE_TO_AUTHZ_ROLE = {
    "owner": "owner",
    "reader": "reader",
    "writer": "editor",
}
"""Map Google Drive roles to AuthZ File Drive schema roles."""


class PangeaAuthZGoogleDriveAPIWrapper(GoogleDriveAPIWrapper):
    """Google Drive search with Pangea AuthZ user-based access control."""

    _authz: AuthZ
    _permissions: GoogleResource

    def __init__(self, *, user_id: str, token: SecretStr, domain: str = "aws.us.pangea.cloud", **kwargs) -> None:
        super().__init__(**kwargs)

        self._authz = AuthZ(token=token.get_secret_value(), config=PangeaConfig(domain=domain))
        self._subject = Subject(type="user", id=user_id)

        self._permissions = build("drive", "v3", credentials=self.credentials).permissions()

    def run(self, query: str) -> str:
        snippets = []
        logger.debug(f"{query=}")
        for document in self.lazy_get_relevant_documents(query=query, num_results=self.num_results):
            # Check if user is authorized to read this file.
            file_id = document.metadata["id"]
            self._cache_permissions(file_id)
            response = self._authz.check(
                subject=self._subject, action="read", resource=Resource(type="file", id=file_id)
            )

            # Do not include the document if the user does not have access to
            # it.
            if response.result is None or not response.result.allowed:
                logger.info(
                    f"User {self._subject.id} is not authorized to read from {document.metadata['name']} ({file_id})."
                )
                continue

            content = document.page_content

            if (
                self.mode in ["snippets", "snippets-markdown"]
                and "summary" in document.metadata
                and document.metadata["summary"]
            ):
                content = document.metadata["summary"]

            if self.mode == "snippets":
                snippets.append(
                    f"Name: {document.metadata['name']}\n"
                    f"Source: {document.metadata['source']}\n" + f"Summary: {content}"
                )
            elif self.mode == "snippets-markdown":
                snippets.append(
                    f"[{document.metadata['name']}]" f"({document.metadata['source']})<br/>\n" + f"{content}"
                )
            elif self.mode == "documents":
                snippets.append(
                    f"Name: {document.metadata['name']}\n"
                    f"Source: {document.metadata['source']}\n" + f"Summary: "
                    f"{GoogleDriveUtilities._snippet_from_page_content(content)}"
                )
            elif self.mode == "documents-markdown":
                snippets.append(
                    f"[{document.metadata['name']}]"
                    f"({document.metadata['source']})<br/>"
                    + f"{GoogleDriveUtilities._snippet_from_page_content(content)}"
                )
            else:
                raise ValueError(f"Invalid mode `{self.mode}`")

        if not len(snippets):
            return "No document found"

        return "\n\n".join(snippets)

    def _cache_permissions(self, file_id: str) -> None:
        permissions: list[dict[str, str]] = (
            self._permissions.list(fileId=file_id, fields="permissions(emailAddress, role)")
            .execute()
            .get("permissions", [])
        )
        tuples = [
            Tuple(
                subject=Subject(type="user", id=permission["emailAddress"]),
                relation=GDRIVE_ROLE_TO_AUTHZ_ROLE[permission["role"]],
                resource=Resource(type="file", id=file_id),
            )
            for permission in permissions
            if "emailAddress" in permission
        ]
        self._authz.tuple_create(tuples)
