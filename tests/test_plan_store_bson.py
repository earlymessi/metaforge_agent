"""plan_store 写入 MongoDB 前须序列化 Pydantic / dataclass 工单。"""

from pydantic import BaseModel

from metaforge.services import plan_store


class _Task(BaseModel):
    machine_id: int
    machine_options: list[int]
    duration: int
    name: str


class _Job(BaseModel):
    name: str
    priority: int = 10
    tasks: list[_Task]


class _FakeColl:
    def __init__(self):
        self.last_doc = None

    def insert_one(self, doc):
        self.last_doc = doc

        class _R:
            inserted_id = "507f1f77bcf86cd799439011"

        return _R()


def test_create_plan_serializes_pydantic_jobs():
    coll = _FakeColl()
    plan_store.configure_plan_store(coll)
    job = _Job(
        name="订单104",
        priority=100,
        tasks=[_Task(machine_id=2, machine_options=[2], duration=6, name="卷料冲压")],
    )
    doc, err = plan_store.create_plan(plan_name="计划a", jobs=[job])
    assert err is None
    assert doc is not None
    stored = coll.last_doc["jobs"]
    assert isinstance(stored, list)
    assert stored[0]["name"] == "订单104"
    assert stored[0]["tasks"][0]["machine_id"] == 2
    assert not isinstance(stored[0], _Job)


def test_wrap_plan_api_response_preserves_operation_status():
    from metaforge.services.plan_store import wrap_plan_api_response

    out = wrap_plan_api_response(
        {"id": "abc", "plan_name": "计划a", "status": "pending", "jobs": []}
    )
    assert out["status"] == "success"
    assert out["plan_status"] == "pending"
    assert out["id"] == "abc"
