#!/usr/bin/env python3
"""OpenClaw Lite Agent prototype.

目标：面向手机/平板/PC，提供轻量化文档办公 + 事项管理能力。
- 每个用户独立目录 + SQLite，避免数据互相干扰。
- 模型调用留空，通过 ModelAdapter 注入。
- 仅保留与文档和时间管理强相关能力。
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DATA_ROOT = Path(__file__).parent / "data"


@dataclass
class ModelRequest:
    capability: str
    prompt: str
    context: dict[str, Any]


class ModelAdapter:
    """模型适配器（留空给接入方实现）"""

    def call(self, req: ModelRequest) -> str:
        raise NotImplementedError(
            "请在 ModelAdapter.call 中接入你的自用模型，返回文本结果。"
        )


class DemoMockAdapter(ModelAdapter):
    """演示用 mock，方便本地看原型效果。"""

    def call(self, req: ModelRequest) -> str:
        return f"[mock:{req.capability}] {req.prompt[:120]}"


class UserSandbox:
    def __init__(self, user_id: str):
        safe_user = "".join(ch for ch in user_id if ch.isalnum() or ch in ("-", "_"))
        if not safe_user:
            raise ValueError("invalid user_id")
        self.user_id = safe_user
        self.root = DATA_ROOT / safe_user
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "workspace.db"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    due_at TEXT,
                    status TEXT NOT NULL,
                    reminder_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS docs (
                    doc_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )


class OpenClawLiteAgent:
    """仅保留文档办公与事项管理主链路的智能体。"""

    def __init__(self, model: ModelAdapter):
        self.model = model

    # ----- 事项管理 -----
    def create_task(self, user: UserSandbox, title: str, due_at: str | None = None) -> dict[str, Any]:
        now = datetime.utcnow()
        reminder_at = None
        if due_at:
            due_dt = datetime.fromisoformat(due_at)
            reminder_at = (due_dt - timedelta(minutes=30)).isoformat()

        task = {
            "task_id": str(uuid.uuid4()),
            "title": title,
            "due_at": due_at,
            "status": "todo",
            "reminder_at": reminder_at,
            "created_at": now.isoformat(),
        }
        with sqlite3.connect(user.db_path) as conn:
            conn.execute(
                "INSERT INTO tasks(task_id,title,due_at,status,reminder_at,created_at) VALUES (?,?,?,?,?,?)",
                tuple(task.values()),
            )
        return task

    def list_due_reminders(self, user: UserSandbox, now_iso: str | None = None) -> list[dict[str, Any]]:
        now_iso = now_iso or datetime.utcnow().isoformat()
        with sqlite3.connect(user.db_path) as conn:
            rows = conn.execute(
                """
                SELECT task_id,title,due_at,status,reminder_at,created_at
                FROM tasks
                WHERE reminder_at IS NOT NULL AND reminder_at <= ? AND status='todo'
                ORDER BY reminder_at ASC
                """,
                (now_iso,),
            ).fetchall()
        keys = ["task_id", "title", "due_at", "status", "reminder_at", "created_at"]
        return [dict(zip(keys, row)) for row in rows]

    # ----- 文档办公 -----
    def create_or_update_doc(
        self, user: UserSandbox, title: str, content: str, tags: list[str] | None = None
    ) -> dict[str, Any]:
        now = datetime.utcnow().isoformat()
        doc = {
            "doc_id": str(uuid.uuid4()),
            "title": title,
            "content": content,
            "tags": json.dumps(tags or [], ensure_ascii=False),
            "updated_at": now,
        }
        with sqlite3.connect(user.db_path) as conn:
            conn.execute(
                "INSERT INTO docs(doc_id,title,content,tags,updated_at) VALUES (?,?,?,?,?)",
                tuple(doc.values()),
            )
        return doc

    def smart_write(self, prompt: str, context: dict[str, Any] | None = None) -> str:
        return self.model.call(
            ModelRequest(capability="doc_generation", prompt=prompt, context=context or {})
        )

    def long_translate(self, text: str, target_lang: str = "zh") -> str:
        prompt = f"Translate into {target_lang}:\n{text}"
        return self.model.call(ModelRequest(capability="long_translation", prompt=prompt, context={}))

    def av_summary(self, transcript: str) -> str:
        prompt = f"Summarize this audio/video transcript with action items:\n{transcript}"
        return self.model.call(ModelRequest(capability="audio_video_summary", prompt=prompt, context={}))


class APIServer(BaseHTTPRequestHandler):
    agent = OpenClawLiteAgent(DemoMockAdapter())

    def _json(self, status: int, body: dict[str, Any]) -> None:
        out = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or "{}")
            user = UserSandbox(payload.get("user_id", ""))
        except Exception as exc:
            self._json(400, {"error": f"bad request: {exc}"})
            return

        try:
            if self.path == "/v1/task/create":
                task = self.agent.create_task(user, payload["title"], payload.get("due_at"))
                self._json(200, task)
            elif self.path == "/v1/task/reminders":
                data = self.agent.list_due_reminders(user)
                self._json(200, {"items": data})
            elif self.path == "/v1/doc/create":
                doc = self.agent.create_or_update_doc(
                    user, payload["title"], payload["content"], payload.get("tags")
                )
                self._json(200, doc)
            elif self.path == "/v1/doc/write":
                text = self.agent.smart_write(payload["prompt"], payload.get("context"))
                self._json(200, {"result": text})
            elif self.path == "/v1/doc/translate":
                text = self.agent.long_translate(payload["text"], payload.get("target_lang", "zh"))
                self._json(200, {"result": text})
            elif self.path == "/v1/doc/av-summary":
                text = self.agent.av_summary(payload["transcript"])
                self._json(200, {"result": text})
            else:
                self._json(404, {"error": "not found"})
        except KeyError as exc:
            self._json(400, {"error": f"missing field: {exc}"})
        except Exception as exc:
            self._json(500, {"error": str(exc)})


def run() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    port = int(os.getenv("OPENCLAW_PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), APIServer)
    print(f"OpenClaw Lite prototype running on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
