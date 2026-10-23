from datetime import timedelta

from dotenv import load_dotenv
from garminconnect import Garmin as GarminClient
from notion_client import Client as NotionClient

from src.helpers import get_garmin_client, get_notion_client

# Garmin activity typeKeys that count as runs. Everything else is skipped.
RUN_TYPE_KEYS = {"running", "trail_running", "track_running", "treadmill_running"}

# Default value for the "Type" select when a run is first created. Change it in Notion afterwards.
DEFAULT_RUN_TYPE = "Easy"

RUNNING_ICON = "https://img.icons8.com/?size=100&id=k1l1XFkME39t&format=png&color=000000"


def get_all_activities(garmin_client: GarminClient, limit: int = 1000) -> list[dict]:
    return garmin_client.get_activities(0, limit)


def is_run(activity: dict) -> bool:
    return activity.get("activityType", {}).get("typeKey") in RUN_TYPE_KEYS


def format_date(activity: dict) -> str:
    # startTimeLocal is the wall-clock time on the watch ("2026-10-21 06:45:12"), so the date is the
    # day you actually ran, regardless of timezone. We only keep the date part.
    return activity["startTimeLocal"].split(" ")[0]


def format_duration(seconds: float) -> str:
    # 2712 -> "45:12", 5025 -> "1:23:45"
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_pace(average_speed: float) -> str:
    # Garmin's averageSpeed is in m/s. Returns min/km as "5:30" (no unit suffix).
    if not average_speed or average_speed <= 0:
        return ""
    total_seconds = int(round(1000 / average_speed))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes}:{secs:02d}"


def build_properties(activity: dict) -> dict:
    moving_seconds = activity.get("duration") or activity.get("movingDuration") or 0

    properties = {
        "Activity Name": {"title": [{"text": {"content": activity.get("activityName") or "Run"}}]},
        "Date": {"date": {"start": format_date(activity)}},
        "Moving Time": {"rich_text": [{"text": {"content": format_duration(moving_seconds)}}]},
        "Distance": {"number": round((activity.get("distance") or 0) / 1000, 2)},
        "Pace": {"rich_text": [{"text": {"content": format_pace(activity.get("averageSpeed", 0))}}]},
        "Type": {"select": {"name": DEFAULT_RUN_TYPE}},
        # Not mapped on purpose: Zone (formula), Shoes (manual relation).
    }

    average_hr = activity.get("averageHR")
    if average_hr:
        properties["Heart Rate"] = {"number": round(average_hr)}

    # Only present if you typed a description/notes on the activity in Garmin Connect.
    description = (activity.get("description") or "").strip()
    if description:
        # Notion caps a single rich text block at 2000 characters.
        properties["Description"] = {"rich_text": [{"text": {"content": description[:2000]}}]}

    return properties


def activity_exists(notion_client: NotionClient, database_id: str, activity: dict) -> bool:
    # Date is date-only and there is no Garmin ID column, so match on same day + same distance.
    # This keeps working if you rename the run or change its Type in Notion.
    query = notion_client.databases.query(
        database_id=database_id,
        filter={
            "and": [
                {"property": "Date", "date": {"equals": format_date(activity)}},
                {"property": "Distance", "number": {"equals": round((activity.get("distance") or 0) / 1000, 2)}},
            ]
        },
        page_size=1,
    )
    return bool(query["results"])


def create_activity(notion_client: NotionClient, database_id: str, activity: dict) -> None:
    notion_client.pages.create(
        parent={"database_id": database_id},
        properties=build_properties(activity),
        icon={"type": "external", "external": {"url": RUNNING_ICON}},
    )


def main():
    load_dotenv()

    garmin_client, garmin_configuration = get_garmin_client()
    notion_client, notion_dbs = get_notion_client()

    database_id = notion_dbs.activities

    activities = get_all_activities(garmin_client, garmin_configuration.activity_fetch_limit)

    # Oldest first so new rows get created in chronological order.
        # Oldest first so new rows get created in chronological order.
    for activity in reversed(activities):
        name = activity.get('activityName')
        type_key = activity.get('activityType', {}).get('typeKey')

        if not is_run(activity):
            print(f"Skipped (not a run): {name} [{type_key}]")
            continue

        # Create-only: existing rows are never touched, so anything you edit in Notion
        # (Type, Description, Shoes, etc.) is never overwritten by the sync.
        if activity_exists(notion_client, database_id, activity):
            print(f"Skipped (already in Notion): {format_date(activity)} - {name}")
            continue

        create_activity(notion_client, database_id, activity)
        print(f"Created: {format_date(activity)} - {name}")


if __name__ == '__main__':
    main()
