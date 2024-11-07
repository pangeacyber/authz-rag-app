from __future__ import annotations

from pathlib import Path
from typing import Any, override

import click
from dotenv import load_dotenv
from googleapiclient.discovery import Resource as GoogleResource  # type: ignore[import-untyped]
from googleapiclient.discovery import build
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_community.vectorstores import FAISS
from langchain_core.prompts.chat import ChatPromptTemplate
from langchain_googledrive.retrievers import GoogleDriveRetriever  # type: ignore[import-untyped]
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pangea import PangeaConfig
from pangea.services import AuthZ
from pangea.services.authz import Resource, Subject, Tuple
from pydantic import SecretStr

from authz_rag_app.auth_server import prompt_authn
from authz_rag_app.authz_retriever import AuthzRetriever

load_dotenv(override=True)

GDRIVE_ROLE_TO_AUTHZ_ROLE = {
    "owner": "owner",
    "reader": "reader",
    "writer": "editor",
}
"""Map Google Drive roles to AuthZ File Drive schema roles."""

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "human",
            """You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that the user may not be authorized to know the answer. Use three sentences maximum and keep the answer concise.
Question: {input}
Context: {context}
Answer:""",
        ),
    ]
)


class SecretStrParamType(click.ParamType):
    name = "secret"

    @override
    def convert(self, value: Any, param: click.Parameter | None = None, ctx: click.Context | None = None) -> SecretStr:
        if isinstance(value, SecretStr):
            return value

        return SecretStr(value)


SECRET_STR = SecretStrParamType()


@click.command()
@click.option(
    "--google-drive-folder-id",
    type=str,
    required=True,
    help="The ID of the Google Drive folder to fetch documents from.",
)
@click.option(
    "--authn-client-token",
    envvar="PANGEA_AUTHN_CLIENT_TOKEN",
    type=str,
    required=True,
    help="Pangea AuthN Client API token. May also be set via the `PANGEA_AUTHN_CLIENT_TOKEN` environment variable.",
)
@click.option(
    "--authn-hosted-login",
    envvar="PANGEA_AUTHN_HOSTED_LOGIN",
    type=str,
    required=True,
    help="Pangea AuthN Hosted Login URL. May also be set via the `PANGEA_AUTHN_HOSTED_LOGIN` environment variable.",
)
@click.option(
    "--authz-token",
    envvar="PANGEA_AUTHZ_TOKEN",
    type=SECRET_STR,
    required=True,
    help="Pangea AuthZ API token. May also be set via the `PANGEA_AUTHZ_TOKEN` environment variable.",
)
@click.option(
    "--pangea-domain",
    envvar="PANGEA_DOMAIN",
    default="aws.us.pangea.cloud",
    show_default=True,
    required=True,
    help="Pangea API domain. May also be set via the `PANGEA_DOMAIN` environment variable.",
)
@click.option("--model", default="gpt-4o-mini", show_default=True, required=True, help="OpenAI model.")
@click.option(
    "--openai-api-key",
    envvar="OPENAI_API_KEY",
    type=SECRET_STR,
    required=True,
    help="OpenAI API key. May also be set via the `OPENAI_API_KEY` environment variable.",
)
def main(
    *,
    google_drive_folder_id: str,
    authn_client_token: str,
    authn_hosted_login: str,
    authz_token: SecretStr,
    pangea_domain: str,
    model: str,
    openai_api_key: SecretStr,
) -> None:
    # Ingest documents from Google Drive.
    retriever = GoogleDriveRetriever(
        folder_id=google_drive_folder_id,
        gdrive_api_file=Path("credentials.json"),
        gsheet_mode="elements",
        mode="documents",
        num_results=-1,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
        template="gdrive-all-in-folder",
    )
    sheets = retriever.invoke("")  # Fetch all documents.

    # Set up permissions.
    authz = AuthZ(token=authz_token.get_secret_value(), config=PangeaConfig(domain=pangea_domain))
    permissions: GoogleResource = build("drive", "v3", credentials=retriever.credentials).permissions()
    authz.tuple_create(
        [
            Tuple(
                subject=Subject(type="user", id=permission["emailAddress"]),
                relation=GDRIVE_ROLE_TO_AUTHZ_ROLE[permission["role"]],
                resource=Resource(type="file", id=sheet.metadata["id"]),
            )
            for sheet in sheets
            for permission in permissions.list(fileId=sheet.metadata["id"], fields="permissions(emailAddress, role)")
            .execute()
            .get("permissions", [])
            if "emailAddress" in permission
        ]
    )

    # Login via Pangea AuthN.
    check_result = prompt_authn(
        authn_client_token=authn_client_token, authn_hosted_login=authn_hosted_login, pangea_domain=pangea_domain
    )
    click.echo()
    click.echo(f"Authenticated as {check_result.owner} ({check_result.identity}).")  # type: ignore[attr-defined]
    click.echo()

    # Set up vector store.
    embeddings_model = OpenAIEmbeddings(api_key=openai_api_key)
    vectorstore = FAISS.from_documents(documents=sheets, embedding=embeddings_model)
    retriever = AuthzRetriever(
        vectorstore=vectorstore,
        username=check_result.owner,  # type: ignore[attr-defined]
        token=authz_token,
        domain=pangea_domain,
    )

    # Set up chain.
    llm = ChatOpenAI(model=model, temperature=0.1, api_key=openai_api_key)
    qa_chain = create_stuff_documents_chain(llm, PROMPT)
    rag_chain = create_retrieval_chain(retriever, qa_chain)

    # Prompt loop.
    while True:
        prompt = click.prompt("Ask a question about PTO availability", type=str)
        click.echo(rag_chain.invoke({"input": prompt})["answer"])
        click.echo()


if __name__ == "__main__":
    main()
