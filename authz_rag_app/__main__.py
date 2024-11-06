from __future__ import annotations

from typing import Any, override

import click
from dotenv import load_dotenv
from google.auth.credentials import TokenState
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_googledrive.tools.google_drive.tool import GoogleDriveSearchTool  # type: ignore[import-untyped]
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from authz_rag_app.auth_server import prompt_authn
from authz_rag_app.authz_google_drive import PangeaAuthZGoogleDriveAPIWrapper

load_dotenv(override=True)

PROMPT = PromptTemplate.from_template(
    """Answer the following questions about PTO availability as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
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
    "--google-credentials",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Path to a JSON file containing Google service account credentials.",
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
    google_credentials: str,
    authn_client_token: str,
    authn_hosted_login: str,
    authz_token: SecretStr,
    pangea_domain: str,
    model: str,
    openai_api_key: SecretStr,
) -> None:
    # Authenticate with Google Drive.
    parsed_gdrive_cred = service_account.Credentials.from_service_account_file(
        google_credentials, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    parsed_gdrive_cred.refresh(Request())
    assert parsed_gdrive_cred.token_state == TokenState.FRESH

    # Login via Pangea AuthN.
    check_result = prompt_authn(
        authn_client_token=authn_client_token, authn_hosted_login=authn_hosted_login, pangea_domain=pangea_domain
    )
    click.echo(f"Authenticated as {check_result.owner} ({check_result.identity}).")  # type: ignore[attr-defined]
    click.echo()

    # Set up Pangea AuthZ + Google Drive tool.
    google_drive = GoogleDriveSearchTool(
        api_wrapper=PangeaAuthZGoogleDriveAPIWrapper(
            user_id=check_result.owner,  # type: ignore[attr-defined]
            token=authz_token,
            domain=pangea_domain,
            credentials=parsed_gdrive_cred,
            folder_id=google_drive_folder_id,
            gsheet_mode="elements",
            mode="documents",
            num_results=-1,
            template="gdrive-all-in-folder",
        )
    )
    tools = [google_drive]
    llm = ChatOpenAI(model=model, api_key=openai_api_key, temperature=0)
    agent = create_react_agent(tools=tools, llm=llm, prompt=PROMPT)
    agent_executor = AgentExecutor(agent=agent, tools=tools)

    # Prompt loop.
    while True:
        prompt = click.prompt("Ask a question about PTO availability", type=str)
        click.echo(agent_executor.invoke({"input": prompt})["output"])
        click.echo()


if __name__ == "__main__":
    main()
