import os
from dataclasses import dataclass

from notion_client import Client

@dataclass(frozen=True)
class NotionDatabases:
    activities: str


def get_notion_client() -> tuple[Client, NotionDatabases]:
    print("Initializing Notion client...")

    notion_databases = NotionDatabases(
        activities=os.getenv("NOTION_DB_ID"),
    )

    notion_token = os.getenv("NOTION_TOKEN")
    notion_client = Client(auth=notion_token)

    print("Notion client initialized.")

    return notion_client, notion_databases
