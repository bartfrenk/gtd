# pyright: reportAny = false, reportUnknownVariableType = false, reportExplicitAny = false
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any, Literal, Self, final, override

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel

from gtd.core import Inbox, Item, Status

TASKS_SCOPES = ["https://www.googleapis.com/auth/tasks.readonly"]

_STATUS_BY_TASK_STATUS = {
    "needsAction": Status.TODO,
    "completed": Status.DONE,
}


class Config(BaseModel):
    kind: Literal["tasks"] = "tasks"
    title: str
    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls, title: str) -> Self:
        return cls(
            title=title,
            client_id=os.environ["CLIENT_ID"],
            client_secret=os.environ["CLIENT_SECRET"],
            refresh_token=os.environ["REFRESH_TOKEN"],
        )

    def service(self) -> Any:
        credentials = Credentials(
            token=None,
            refresh_token=self.refresh_token,
            client_id=self.client_id,
            client_secret=self.client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=TASKS_SCOPES,
        )
        return build("tasks", "v1", credentials=credentials)


@final
class TasksInbox(Inbox):
    def __init__(self, title: str, service: Any) -> None:
        self._title = title
        self._service = service

    @classmethod
    def from_config(cls, config: Config) -> Self:
        return cls(config.title, config.service())

    @override
    async def get_items(self, status: set[Status] | None = None) -> AsyncIterator[Item]:
        for task in self._fetch_tasks():
            item = self._to_item(task)
            if status is None or item.status in status:
                yield item

    def _fetch_tasks(self) -> list[dict[str, Any]]:
        tasklist_id = self._find_tasklist_id()
        response = (
            self._service.tasks()
            .list(tasklist=tasklist_id, showCompleted=True, showHidden=True)
            .execute()
        )
        return response.get("items", [])

    @staticmethod
    def _to_item(task: dict[str, Any]) -> Item:
        return Item(
            title=task["title"],
            description=task.get("notes"),
            status=_STATUS_BY_TASK_STATUS.get(task["status"], Status.TODO),
        )

    def _find_tasklist_id(self) -> str:
        tasklists = self._service.tasklists().list().execute().get("items", [])
        matches = [tasklist for tasklist in tasklists if tasklist["title"] == self._title]
        if len(matches) == 0:
            raise LookupError(f"No task list found with title {self._title!r}")
        if len(matches) > 1:
            raise LookupError(f"Multiple task lists found with title {self._title!r}")
        return matches[0]["id"]
