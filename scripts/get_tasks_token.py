from google_auth_oauthlib.flow import InstalledAppFlow

from gtd.tasks import TASKS_SCOPES


def main() -> None:
    client_id = input("Client ID: ")
    client_secret = input("Client secret: ")
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, TASKS_SCOPES)
    credentials = flow.run_local_server(port=0)
    print(credentials.refresh_token)


if __name__ == "__main__":
    main()
