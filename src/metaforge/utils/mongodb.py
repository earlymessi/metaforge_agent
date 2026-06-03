from __future__ import annotations

import os
from typing import Optional

import motor.motor_asyncio


def get_mongo_url(default: str = "mongodb://localhost:27017") -> str:
    """
    MongoDB 连接串优先从环境变量读取，便于部署/测试环境切换。

    - MONGO_URL: 例如 mongodb://user:pass@host:27017/?authSource=admin
    """
    return os.getenv("MONGO_URL", default).strip()


def get_mongo_db_name(default: str = "metaforge") -> str:
    """
    MongoDB 数据库名优先从环境变量读取。

    - MONGO_DB_NAME: 例如 metaforge_mes
    """
    return os.getenv("MONGO_DB_NAME", default).strip()


def create_motor_client(
    mongo_url: Optional[str] = None,
    *,
    server_selection_timeout_ms: int = 3000,
    connect_timeout_ms: int = 3000,
) -> motor.motor_asyncio.AsyncIOMotorClient:
    url = (mongo_url or get_mongo_url()).strip()
    return motor.motor_asyncio.AsyncIOMotorClient(
        url,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
        connectTimeoutMS=connect_timeout_ms,
    )


async def ping_mongodb(client: motor.motor_asyncio.AsyncIOMotorClient) -> None:
    # Mongo 官方推荐的连通性检测：db.admin.command("ping")
    await client.admin.command("ping")


def get_database(
    client: motor.motor_asyncio.AsyncIOMotorClient,
    db_name: Optional[str] = None,
):
    return client[db_name or get_mongo_db_name()]

