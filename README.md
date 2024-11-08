# Authenticating Users for Access Control with RAG for LangChain in Python

An example Python app demonstrating how to integrate Pangea's [AuthN][]
and [AuthZ][] services into a LangChain app to filter out RAG documents based on
user permissions.

## Prerequisites

- Python v3.12 or greater.
- pip v24.2 or [uv][] v0.4.29.
- A [Pangea account][Pangea signup] with AuthN and AuthZ enabled.
- An [OpenAI API key][OpenAI API keys].
- A Google Cloud project with the [Google Drive API][] and [Google Sheets API][]
  enabled.
- A Google Drive folder containing spreadsheets
  - Note down the ID of the folder for later (see [the LangChain docs][retrieve-the-google-docs]
    for a guide on how to get the ID from the URL).
  - Each spreadsheet should be named after a user and have a two rows (examples below)

- Two Google Identities (ie. Alice and Bob)
  - One user (ie Alice) will act as the admin and own the folder and have full access to all spreadsheets within
  - The other user (ie Bob) will act as an employee with read access to the folder and their single spreadsheet

Alice PTO

| Employee    | Hours |
| -------- | ------- |
| Alice  | 25    |

Bob PTO

| Employee    | Hours |
| -------- | ------- |
| Bob  | 100    |


## Setup

### Pangea AuthN

After activating AuthN:

1. Under AuthN > General> Signup Settings, enable "Allow Signups". This way
   users won't need to be manually added.
2. Under AuthN > General > Redirect (Callback) Settings,
   add `http://localhost:3000` as a redirect.
3. Under AuthN > General > Social (OAuth), enable Google.
4. Under AuthN > Overview, note the "Client Token" and "Hosted Login" values for
   later.

### Pangea AuthZ

This app assumes that the authorization schema is set to the built-in
[File Drive][reset-authorization-schema] schema.

Under AuthZ > Overview, note the "Default Token" value for later.

### Repository

```shell
git clone https://github.com/pangeacyber/authz-rag-app.git
cd authz-rag-app
```

If using pip:

```shell
python -m venv .venv
source .venv/bin/activate
pip install .
```

Or, if using uv:

```shell
uv sync
source .venv/bin/activate
```

Then [authorize credentials for a desktop application][authorize-credentials-for-a-desktop-application].
Save the downloaded JSON file as `credentials.json` and place it inside the
`authz-rag-app` directory.

## Usage

```
Usage: python -m authz_rag_app [OPTIONS]

Options:
  --google-drive-folder-id TEXT  The ID of the Google Drive folder to fetch
                                 documents from.  [required]
  --authn-client-token TEXT      Pangea AuthN Client API token. May also be
                                 set via the `PANGEA_AUTHN_CLIENT_TOKEN`
                                 environment variable.  [required]
  --authn-hosted-login TEXT      Pangea AuthN Hosted Login URL. May also be
                                 set via the `PANGEA_AUTHN_HOSTED_LOGIN`
                                 environment variable.  [required]
  --authz-token SECRET           Pangea AuthZ API token. May also be set via
                                 the `PANGEA_AUTHZ_TOKEN` environment
                                 variable.  [required]
  --pangea-domain TEXT           Pangea API domain. May also be set via the
                                 `PANGEA_DOMAIN` environment variable.
                                 [default: aws.us.pangea.cloud; required]
  --model TEXT                   OpenAI model.  [default: gpt-4o-mini;
                                 required]
  --openai-api-key SECRET        OpenAI API key. May also be set via the
                                 `OPENAI_API_KEY` environment variable.
                                 [required]
  --help                         Show this message and exit.
```

1.  Set the following environments variables (or pass the values as command-line
    arguments):

    - `PANGEA_AUTHN_CLIENT_TOKEN`
    - `PANGEA_AUTHN_HOSTED_LOGIN`
    - `PANGEA_AUTHZ_TOKEN`
    - `OPENAI_API_KEY`

1.  Run the app, passing the ID of the Google Drive folder that was set up
    earlier (this sample uses a fake value):

    ```bash
    python -m authz_rag_app --google-drive-folder-id 1yucgL9WGgWZdM1TOuKkeghlPizuzMYb5
    ```

1.  A new tab will open in the system's default web browser where one can perform
    login via Google. Log in as the user who has Editor access to the Google
    Drive folder. The tab may be closed once the login flow is complete.
1.  Another tab will open to login via Pangea AuthN. Select the
    "Continue with Google" option and log in again. The Google user selected here
    does not need to be the same as the one used in the previous step, but if
    that user is picked then all documents will be available in the subsequent
    steps, which would not illustrate any access control. Instead, choose one of
    the accounts that only has Reader access to their own PTO spreadsheet.
    Again, the tab may be closed once the login flow is complete.
1.  Then a chat prompt will appear:

    ```
    Ask a question about PTO availability:
    ```

1.  Whoever logged in during step 4 can ask about their PTO balance. For
    example, if Alice has 21 days remaining according to their Google Sheet, and
    they logged in above, they might do:

    ```
    Ask a question about PTO availability: How many PTO days do I have left?
    You have 21 PTO days left.
    ```

1.  But if they try to ask for another employee's balance, like Bob's, the
    answer will not be disclosed:

    ```
    Ask a question about PTO availability: How much PTO does Bob have left?
    The context does not provide information about Bob's Paid Time Off (PTO)
    balance. Therefore, I cannot determine how much PTO Bob has left. You may
    not be authorized to know the answer.
    ```

## Cleanup & Debugging

- After login, the Google token is stored in `token.json`. If you encounter "access denied" errors, delete `token.json` before you try again.
- The file authorization policy is cached in Pangea AuthZ. If you change your Google Drive folder or create new files, visit [Pangea AuthZ Settings][Pangea AuthZ Settings] to reset your authorization schema.


[AuthN]: https://pangea.cloud/docs/authn/
[AuthZ]: https://pangea.cloud/docs/authz/
[Pangea AuthZ Settings]: https://console.pangea.cloud/service/authz/settings
[Vault]: https://pangea.cloud/docs/vault/
[Pangea signup]: https://pangea.cloud/signup
[reset-authorization-schema]: https://dev.pangea.cloud/docs/authz/general#reset-authorization-schema
[langchain-python-service-authn]: https://github.com/pangeacyber/langchain-python-service-authn
[OpenAI API keys]: https://platform.openai.com/api-keys
[uv]: https://docs.astral.sh/uv/
[Google Drive API]: https://console.cloud.google.com/flows/enableapi?apiid=drive.googleapis.com
[Google Sheets API]: https://console.cloud.google.com/flows/enableapi?apiid=sheets.googleapis.com
[retrieve-the-google-docs]: https://python.langchain.com/docs/integrations/retrievers/google_drive/#retrieve-the-google-docs
[authorize-credentials-for-a-desktop-application]: https://developers.google.com/drive/api/quickstart/python#authorize_credentials_for_a_desktop_application
