import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_ROOT = _REPO_ROOT / "src"

# 开发时优先使用仓库 src，避免 site-packages 里旧版 metaforge 覆盖新路由逻辑
import sys

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def _load_dotenv() -> None:
    env_path = _REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    except ImportError:
        pass


_load_dotenv()

import uvicorn
import math
import time
import uuid
import asyncio
import motor.motor_asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from contextlib import asynccontextmanager

# === 核心算法导入 ===
from metaforge.problems.benchmark_loader import load_job_shop_instance
from metaforge.utils.compare_solvers import compare_solvers, run_single_solver
from metaforge.utils.objectives import get_objectives_schema
from metaforge.utils.solver_registry import get_solver_catalog, resolve_solver_id
from metaforge.problems.jobshop import JobShopProblem, Job, Task
from metaforge.utils.mongodb import create_motor_client, get_database, ping_mongodb, get_mongo_url, get_mongo_db_name
from metaforge.utils.delivery_prediction import (
    build_commitment_changes,
    compute_delivery_predictions,
)
from metaforge.utils.material_constraints import (
    build_material_report_for_schedule,
    check_jobs_material_static,
    compute_material_arrival_delays,
    simulate_schedule_materials,
)
from metaforge.services.agv_dispatch import (
    DispatchConfig,
    dispatch_agv_global,
    persist_dispatch_result,
)

BASE_DIR = Path(__file__).resolve().parent

# ==========================================
# 1. 数据库配置 (必须放在最前面！)
# ==========================================
MONGO_URL = get_mongo_url("mongodb://localhost:27017")
MONGO_DB_NAME = get_mongo_db_name("metaforge_mes")
client = create_motor_client(MONGO_URL)
db = get_database(client, MONGO_DB_NAME)  # 数据库名

# 定义所有集合 (确保在 lifespan 之前定义)
orders_collection = db.work_orders
routing_templates_collection = db.routing_templates
schedule_tasks_collection = db.schedule_tasks
maintenance_collection = db.maintenance_orders

_schedule_executor = ThreadPoolExecutor(max_workers=2)
_schedule_tasks_mem: Dict[str, Dict[str, Any]] = {}
agv_fleet_collection = db.agv_fleet
agv_tasks_collection = db.agv_tasks
staff_collection = db.staff_roster
material_collection = db.materials_inventory
tool_collection = db.tools_library
machine_collection = db.machines_layout
execution_collection = db.production_execution


# ==========================================
# 2. 生命周期管理器 (Lifespan)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Lifespan] 系统启动序列开始...")
    try:
        await ping_mongodb(client)
        print(f"[OK] MongoDB 已连接: url={MONGO_URL}, db={MONGO_DB_NAME}")
    except Exception as e:
        print(f"[ERR] MongoDB 连接失败: url={MONGO_URL}, db={MONGO_DB_NAME}, err={e}")
        raise

    from metaforge.tools.load_all import load_all_tools

    load_all_tools()
    print("[OK] Tool 注册表已加载")

    import metaforge.orchestrator.router as _router_mod
    import metaforge.orchestrator.execution_trace as _trace_mod

    print(f"[OK] 意图路由模块: {_router_mod.__file__}")
    print(f"[OK] 路由版本: {getattr(_router_mod, 'ROUTER_BUILD_ID', '?')}")
    print(f"[OK] Trace 模块: {_trace_mod.__file__}")

    import os
    from metaforge.orchestrator.session import configure_mongo_store, session_store_mode
    from metaforge.services.persist_store import configure_mongo_persist
    from metaforge.services.plan_store import configure_plan_store

    if session_store_mode() == "mongo":
        from pymongo import MongoClient

        sync_client = MongoClient(MONGO_URL)
        sync_db = sync_client[MONGO_DB_NAME]
        sessions_coll = sync_db["orchestrator_sessions"]
        hitl_coll = sync_db["hitl_pending"]
        configure_mongo_store(sessions_coll)
        configure_mongo_persist(hitl_coll)
        configure_plan_store(sync_db["work_orders"])
        try:
            sessions_coll.create_index("expires_at_ts")
            hitl_coll.create_index("expires_at_ts")
        except Exception as idx_err:
            print(f"[WARN] Session/HITL 索引: {idx_err}")
        print("[OK] Session + HITL 使用 MongoDB 持久化 (sync PyMongo)")
    else:
        e2e_mode = os.getenv("AGENT_E2E", "").strip().lower() in ("1", "true", "yes")
        if e2e_mode:
            from metaforge.services.plan_store_memory import InMemoryPlanCollection

            configure_plan_store(InMemoryPlanCollection())
            print("[OK] 计划库 Tool 使用 E2E 内存存储 (AGENT_E2E=1)")
        else:
            from pymongo import MongoClient

            try:
                sync_client = MongoClient(MONGO_URL)
                configure_plan_store(sync_client[MONGO_DB_NAME]["work_orders"])
                print("[OK] 计划库 Tool 已绑定 MongoDB work_orders")
            except Exception as pe:
                print(f"[WARN] plan_store 未配置: {pe}")
        print("[OK] Session + HITL 使用内存存储 (SESSION_STORE=memory)")

    # --- A. 初始化 AGV ---
    try:
        count = await agv_fleet_collection.count_documents({})
        if count == 0:
            print("[Lifespan] 初始化 AGV 车队数据...")
            default_fleet = [
                {"agv_id": 1, "location": -1, "status": "idle"},
                {"agv_id": 2, "location": -1, "status": "idle"},
                {"agv_id": 3, "location": -1, "status": "idle"},
                {"agv_id": 4, "location": -1, "status": "idle"}
            ]
            await agv_fleet_collection.insert_many(default_fleet)
    except Exception as e:
        print(f"[WARN] AGV 初始化失败: {e}")

    # --- B. 初始化员工 (Staff) ---
    try:
        s_count = await staff_collection.count_documents({})
        if s_count == 0:
            print("[Lifespan] 初始化员工花名册...")
            default_staff = [
                {"id": 1, "name": "张三", "role": "组长", "skills": ["管理", "数控"], "shift": "早班", "level": "L3", "is_active": True},
                {"id": 2, "name": "李四", "role": "操作员", "skills": ["数控", "装配"], "shift": "早班", "level": "L2", "is_active": True},
                {"id": 3, "name": "王五", "role": "操作员", "skills": ["数控"], "shift": "早班", "level": "L2", "is_active": True},
                {"id": 4, "name": "赵六", "role": "操作员", "skills": ["数控", "磨床"], "shift": "中班", "level": "L2", "is_active": True},
                {"id": 5, "name": "钱七", "role": "操作员", "skills": ["数控"], "shift": "中班", "level": "L1", "is_active": True},
                {"id": 6, "name": "孙八", "role": "质检", "skills": ["质检"], "shift": "早班", "level": "L2", "is_active": False},
                {"id": 7, "name": "周九", "role": "操作员", "skills": ["数控", "装配"], "shift": "晚班", "level": "L2", "is_active": True},
                {"id": 8, "name": "吴十", "role": "实习生", "skills": ["辅助"], "shift": "早班", "level": "L1", "is_active": True},
            ]
            await staff_collection.insert_many(default_staff)
        else:
            staff_skill_defaults = {
                1: {"skills": ["管理", "数控"], "shift": "早班", "level": "L3"},
                2: {"skills": ["数控", "装配"], "shift": "早班", "level": "L2"},
                3: {"skills": ["数控"], "shift": "早班", "level": "L2"},
                4: {"skills": ["数控", "磨床"], "shift": "中班", "level": "L2"},
                5: {"skills": ["数控"], "shift": "中班", "level": "L1"},
                6: {"skills": ["质检"], "shift": "早班", "level": "L2"},
                7: {"skills": ["数控", "装配"], "shift": "晚班", "level": "L2"},
                8: {"skills": ["辅助"], "shift": "早班", "level": "L1"},
            }
            for sid, patch in staff_skill_defaults.items():
                await staff_collection.update_one(
                    {"id": sid, "skills": {"$exists": False}},
                    {"$set": patch},
                )
    except Exception as e:
        print(f"[WARN] 员工初始化失败: {e}")

    # --- C. 初始化物料库存 ---
    try:
        from metaforge.services.materials_inventory import ensure_default_materials

        n = await ensure_default_materials(material_collection)
        if n:
            print(f"[Lifespan] 已初始化默认物料 {n} 条 (materials_inventory)")
    except Exception as e:
        print(f"[WARN] 物料初始化失败: {e}")

    # --- D. 初始化机器布局 (3D 真实坐标) ---
    # [关键修复] 这里的缩进已经调整，不再位于 except 块内部
    try:
        # 1. 检查是否存在旧数据
        m_count = await machine_collection.count_documents({})

        # # 2. 强制重置逻辑 (确保3D布局生效)
        # if m_count > 0:
        #     # 如果你想保留旧数据，注释掉下面两行；但在开发3D功能时建议开启
        #     print("♻️ [Lifespan] 检测到旧机器数据，正在重置为 3D 布局...")
        #     await machine_collection.drop()
        if m_count == 0:
            print("[Lifespan] 正在初始化 3D 布局...")
            default_machines = []
            for i in range(12):
                row = i // 6
                col = i % 6
                z = -50 if row == 0 else 50
                x = (col - 2.5) * 50

                default_machines.append({
                    "id": i,
                    "name": f"Machine-{i}",
                    "x": x,
                    "y": 7.5,
                    "z": z,
                    "status": "idle"
                })
            await machine_collection.insert_many(default_machines)
            print(f"[OK] [Lifespan] 成功写入 {len(default_machines)} 台机器坐标。")

    except Exception as e:
        print(f"[WARN] 机器布局初始化失败: {e}")

    # ----------------------
    # 3. 启动完成，挂起
    # ----------------------
    yield

    # ----------------------
    # 4. 关闭逻辑 (Shutdown)
    # ----------------------
    print("[Lifespan] 系统关闭")


# ==========================================
# 3. 实例化 FastAPI
# ==========================================
app = FastAPI(lifespan=lifespan)

# 托管前端构建产物：/assets/*
dist_assets_dir = BASE_DIR / "templates" / "dist" / "assets"
if dist_assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(dist_assets_dir)), name="assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)




# === 数据模型定义 ===

class BomLine(BaseModel):
    material_id: str
    quantity_per_unit: float = 1.0
    consume_mode: str = "job_start"  # job_start | per_hour


class TaskData(BaseModel):
    machine_id: Optional[int] = None
    machine_options: Optional[List[int]] = None
    machine_group: Optional[str] = None
    duration: int = 1
    name: Optional[str] = None
    quantity: Optional[int] = None
    setup_time: Optional[float] = None
    unit_time: Optional[float] = None


class JobData(BaseModel):
    name: str
    priority: int = 10  # 默认优先级10，100为加急
    due_date: Optional[float] = None  # 可选：业务交期（不填则按工时自动估算）
    quantity: Optional[int] = None
    material_arrival: Optional[float] = None  # 物料就绪后才可开工（由 enforce 或手工填写）
    bom: Optional[List[BomLine]] = None
    tasks: List[TaskData]


class RoutingTemplateSchema(BaseModel):
    name: str
    description: Optional[str] = None
    tasks: List[TaskData]
    created_at: datetime = Field(default_factory=datetime.now)


from metaforge.agent.scheduling_agent import SchedulingAgent, STRATEGY_TEMPLATES


# 更新数据库存储模型，支持保存排程结果和图片
class WorkOrderSchema(BaseModel):
    plan_name: str
    jobs: List[JobData] = []
    created_at: datetime = Field(default_factory=datetime.now)
    status: str = "pending"

    # 新增字段：允许存储排程算法的计算结果
    schedule_result: Optional[Dict[str, Any]] = None

    # 新增字段：存储 Base64 图片字符串
    chart_image: Optional[str] = None


class CompareRequest(BaseModel):
    solvers: List[str]
    benchmark_file: Optional[str] = None
    custom_data: Optional[List[JobData]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None
    enforce_material: bool = False
    solver_params: Optional[Dict[str, Dict[str, Any]]] = None


class SingleSolverRunRequest(BaseModel):
    benchmark_file: Optional[str] = None
    custom_data: Optional[List[JobData]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None
    enforce_material: bool = False
    solver_params: Optional[Dict[str, Any]] = None


class OrchestratorRequest(BaseModel):
    message: str = ""
    intent: Optional[str] = None
    context: Dict[str, Any] = {}
    params: Dict[str, Any] = {}


class AgentRunRequest(BaseModel):
    """单 Agent 执行请求（结构化参数，Phase 3 再接 NL）。"""
    message: str = ""
    params: Dict[str, Any] = {}
    custom_data: Optional[List[JobData]] = None
    benchmark_file: Optional[str] = None
    plan_id: Optional[str] = None
    random_seed: Optional[int] = None
    weights: Optional[Dict[str, float]] = None
    enforce_material: Optional[bool] = None


class AgentScheduleRequest(BaseModel):
    """智能排程 Agent 统一入口（多智能体路由用）。"""
    message: str
    custom_data: Optional[List[JobData]] = None
    benchmark_file: Optional[str] = None
    plan_id: Optional[str] = None
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    strategy_id: Optional[str] = None
    enforce_material: Optional[bool] = None
    random_seed: Optional[int] = None
    parse_only: bool = False
    async_run: bool = False


class MaterialCheckRequest(BaseModel):
    jobs: List[JobData]


class MaterialPredictRequest(BaseModel):
    schedule_data: List[Dict[str, Any]]
    jobs: Optional[List[JobData]] = None


class InsertRescheduleRequest(BaseModel):
    base_jobs: List[JobData]
    insert_job: JobData
    freeze_time: float = 0.0
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    mode: str = "local_repair"  # local_repair | global
    random_seed: Optional[int] = None


class MachineBreakdownRequest(BaseModel):
    base_jobs: List[JobData]
    machine_id: int
    breakdown_start: float
    breakdown_duration: float
    freeze_time: Optional[float] = None
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None
    baseline_gantt: Optional[List[Dict[str, Any]]] = None
    baseline_solver: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


# [新增] 能耗配置模型
class DowntimeBlock(BaseModel):
    machine_id: int
    start: float
    end: float
    label: Optional[str] = "downtime"


class ResourceConfig(BaseModel):
    machine_powers: Dict[str, float]
    hourly_prices: List[float]
    maintenance_limits: Dict[str, float]
    downtime_blocks: Optional[List[DowntimeBlock]] = None


class DueDateChangeItem(BaseModel):
    job_name: str
    new_due_date: float


class DueDateRescheduleRequest(BaseModel):
    base_jobs: List[JobData]
    due_date_changes: List[DueDateChangeItem]
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None


class PlannedDowntimeRequest(BaseModel):
    base_jobs: List[JobData]
    downtime_blocks: List[DowntimeBlock]
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None


class MaterialDelayRequest(BaseModel):
    base_jobs: List[JobData]
    job_name: str
    delay_hours: float
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None


class PriorityChangeItem(BaseModel):
    job_name: str
    new_priority: int


class PriorityChangeRequest(BaseModel):
    base_jobs: List[JobData]
    changes: List[PriorityChangeItem]
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None


class OrderCancelRequest(BaseModel):
    base_jobs: List[JobData]
    job_names: List[str]
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None


class QuantityChangeItem(BaseModel):
    job_name: str
    new_quantity: int


class QuantityChangeRequest(BaseModel):
    base_jobs: List[JobData]
    changes: List[QuantityChangeItem]
    solvers: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    random_seed: Optional[int] = None


# === 辅助函数 ===
def fix_id(doc):
    doc["id"] = str(doc.pop("_id"))
    return doc

# === 路由 ===

@app.get("/")
def read_root():
    # 默认优先返回新前端构建产物
    dist_index = BASE_DIR / "templates" / "dist" / "index.html"
    if dist_index.exists():
        return FileResponse(str(dist_index))

    # 兼容旧版页面（仅兜底）
    html_path = BASE_DIR / "templates" / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return {"message": "MetaForge Backend Running"}


@app.get("/new-ui")
def read_new_ui():
    """新前端独立入口（迁移中），避免影响旧版生产页面。"""
    dist_index = BASE_DIR / "templates" / "dist" / "index.html"
    if dist_index.exists():
        return FileResponse(str(dist_index))
    return {"error": "New UI build not found. Please run frontend build first."}


@app.get("/new-ui/{full_path:path}")
def read_new_ui_spa(full_path: str):
    """
    SPA history fallback:
    访问 /new-ui/aps、/new-ui/reports 等前端路由时，统一返回 index.html。
    """
    dist_index = BASE_DIR / "templates" / "dist" / "index.html"
    if dist_index.exists():
        return FileResponse(str(dist_index))
    return {"error": "New UI build not found. Please run frontend build first."}


@app.get("/api/benchmarks")
def get_benchmarks():
    bench_dir = BASE_DIR / "data" / "benchmarks"
    if not bench_dir.exists(): return {"files": []}
    files = [f.name for f in bench_dir.glob("*.txt")]
    return {"files": sorted(files)}


# --- [新增] 能耗管理相关 API ---

@app.get("/api/resources/config")
async def get_resource_config():
    """
    获取能耗配置：机器功率 + 分时电价。
    如果数据库中不存在配置，则自动初始化默认值。
    """
    config_coll = db.resource_config
    config = await config_coll.find_one({"_id": "global_config"})

    if not config:
        from metaforge.services.resource_config import default_resource_config

        default_data = default_resource_config()
        await config_coll.insert_one(default_data)
        config = default_data

    return config


@app.put("/api/resources/config")
async def update_resource_config(config: ResourceConfig):
    """更新能耗/停机窗口等资源参数（_id 固定为 global_config）。"""
    doc = {"_id": "global_config", **config.model_dump()}
    await db.resource_config.replace_one({"_id": "global_config"}, doc, upsert=True)
    return {"status": "success", "config": doc}


# --- 数据库 API ---

# 1. 保存工单 (支持多模态数据)
@app.post("/api/db/save")
async def save_work_order(order: WorkOrderSchema):
    doc = order.dict()
    new_order = await orders_collection.insert_one(doc)
    return {"status": "success", "id": str(new_order.inserted_id)}


# 2. 获取列表 (包含图片字段)
@app.get("/api/db/list")
async def list_work_orders():
    orders = []
    cursor = orders_collection.find().sort("created_at", -1)
    async for doc in cursor:
        orders.append(fix_id(doc))
    return orders


class WorkOrderUpdate(BaseModel):
    plan_name: Optional[str] = None
    jobs: Optional[List[JobData]] = None
    status: Optional[str] = None


class SchedulePersistRequest(BaseModel):
    """将多算法排程结果写入计划（分析报表、导入排程可恢复）。"""
    schedule_results: Dict[str, Any]
    interpretation: Optional[Dict[str, Any]] = None
    delivery_assessment: Optional[Dict[str, Any]] = None
    impact_summary: Optional[Dict[str, Any]] = None
    jobs: Optional[List[Any]] = None
    status: Optional[str] = "done"


class ProposeScheduleRequest(BaseModel):
    """HITL：首次直接落库，已有排程则返回 pending_confirm。"""
    plan_id: str
    schedule_results: Dict[str, Any]
    interpretation: Optional[Dict[str, Any]] = None
    delivery_assessment: Optional[Dict[str, Any]] = None
    impact_summary: Optional[Dict[str, Any]] = None
    jobs: Optional[List[Any]] = None
    plan_name: Optional[str] = None


# 2b. 获取单条计划（含 schedule_results）
@app.get("/api/db/get/{oid}")
async def get_work_order(oid: str):
    from metaforge.services import plan_store

    doc, err = plan_store.get_plan(oid)
    if err or not doc:
        raise HTTPException(status_code=404, detail=err or "plan not found")
    return doc


# 3. 更新计划（名称 / 工单）
@app.put("/api/db/update/{oid}")
async def update_work_order(oid: str, body: WorkOrderUpdate):
    from metaforge.services import plan_store

    jobs_payload = None
    if body.jobs is not None:
        jobs_payload = [
            j.model_dump() if hasattr(j, "model_dump") else j.dict() for j in body.jobs
        ]
    doc, err = plan_store.update_plan(
        plan_id=oid,
        plan_name=body.plan_name,
        jobs=jobs_payload,
    )
    if err or not doc:
        raise HTTPException(status_code=404 if err == "plan not found" else 400, detail=err or "update failed")
    if body.status:
        doc2, err2 = plan_store.update_status(plan_id=oid, status=body.status)
        if not err2 and doc2:
            doc = doc2
    if doc and "_id" in doc:
        doc = fix_id(doc)
    from metaforge.services.plan_store import wrap_plan_api_response

    return wrap_plan_api_response(doc)


# 3b. 保存排程结果到计划
@app.put("/api/db/schedule/{oid}")
async def save_plan_schedule(oid: str, body: SchedulePersistRequest):
    from metaforge.services.plan_schedule import save_schedule_results

    doc, err = save_schedule_results(
        oid,
        body.schedule_results,
        interpretation=body.interpretation,
        delivery_assessment=body.delivery_assessment,
        impact_summary=body.impact_summary,
        jobs=body.jobs,
        status=body.status or "done",
    )
    if err or not doc:
        raise HTTPException(status_code=404 if err == "plan not found" else 400, detail=err or "save failed")
    from metaforge.services.plan_store import wrap_plan_api_response

    return wrap_plan_api_response(doc)


@app.post("/api/db/propose_schedule")
async def db_propose_schedule(req: ProposeScheduleRequest):
    """看板/助手共用：有计划排程时 HITL propose，否则直接写入。"""
    from metaforge.services.plan_schedule import persist_schedule_with_hitl
    from metaforge.services.plan_store import wrap_plan_api_response

    kind, payload = persist_schedule_with_hitl(
        req.plan_id,
        req.schedule_results,
        interpretation=req.interpretation,
        delivery_assessment=req.delivery_assessment,
        impact_summary=req.impact_summary,
        jobs=req.jobs,
        plan_name=req.plan_name,
        status="done",
    )
    if kind == "error":
        raise HTTPException(status_code=400, detail=(payload or {}).get("error", "propose failed"))
    if kind == "saved":
        return wrap_plan_api_response((payload or {}).get("plan"))
    return {
        "status": "pending_confirm",
        "pending_action": payload,
    }


# 4. 删除工单
@app.delete("/api/db/delete/{oid}")
async def delete_work_order(oid: str):
    result = await orders_collection.delete_one({"_id": ObjectId(oid)})
    if result.deleted_count == 1:
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Order not found")


# 4. 更新状态
@app.post("/api/db/status/{oid}")
async def update_order_status(oid: str, update: StatusUpdate):
    try:
        result = await orders_collection.update_one(
            {"_id": ObjectId(oid)},
            {"$set": {"status": update.status}}
        )
        if result.modified_count == 1:
            return {"status": "success"}
        return {"status": "no_change"}
    except Exception as e:
        print(f"Update error: {e}")
        return {"error": str(e)}


# 5. 看板统计
@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    total_orders = await orders_collection.count_documents({})
    completed = await orders_collection.count_documents({"status": "done"})
    pending = await orders_collection.count_documents({"status": "pending"})

    pipeline = [
        {"$unwind": "$jobs"},
        {"$unwind": "$jobs.tasks"},
        {"$count": "total_ops"}
    ]
    aggr = await orders_collection.aggregate(pipeline).to_list(1)
    total_ops = aggr[0]["total_ops"] if aggr else 0

    return {
        "total_orders": total_orders,
        "completed": completed,
        "pending": pending,
        "total_ops": total_ops,
        "active_machines": 12
    }


class ExecutionStartRequest(BaseModel):
    plan_id: str
    solver_id: str
    sim_speed: float = 60.0


@app.get("/api/execution/state")
async def execution_state():
    from metaforge.services.production_execution import get_state

    return await get_state(execution_collection)


@app.post("/api/execution/start")
async def execution_start(req: ExecutionStartRequest):
    from metaforge.services.production_execution import start_execution

    try:
        doc = await start_execution(
            execution_collection,
            orders_collection,
            plan_id=req.plan_id,
            solver_id=req.solver_id,
            sim_speed=req.sim_speed,
        )
        return doc
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/execution/start_from_package")
async def execution_start_from_package(body: Dict = Body(...)):
    from metaforge.services.package_to_execution import start_from_package

    try:
        return await start_from_package(
            execution_collection,
            orders_collection,
            package=body.get("package"),
            run_id=body.get("run_id"),
            plan_id=body.get("plan_id"),
            persist_plan=bool(body.get("persist_plan", True)),
            sim_speed=float(body.get("sim_speed") or 60),
            jobs=body.get("jobs"),
            plan_name=body.get("plan_name") or "Package 推荐计划",
            candidates=body.get("candidates") or body.get("candidate_schedules"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/execution/pause")
async def execution_pause():
    from metaforge.services.production_execution import pause_execution

    try:
        return await pause_execution(execution_collection)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/execution/resume")
async def execution_resume():
    from metaforge.services.production_execution import resume_execution

    try:
        return await resume_execution(execution_collection)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/execution/reset")
async def execution_reset():
    from metaforge.services.production_execution import reset_execution

    await reset_execution(execution_collection)
    from metaforge.services.production_execution import idle_state

    return idle_state()


# --- 排程 API ---


def _resolve_task_duration(task: TaskData, job_quantity: Optional[int] = None) -> int:
    from metaforge.utils.problem_builder import resolve_task_duration

    return resolve_task_duration(task, job_quantity=job_quantity)


def _build_problem_from_custom_jobs(custom_jobs: List[JobData], *, instance_name: str = "Custom Plan"):
    from metaforge.utils.problem_builder import build_problem_from_custom_jobs

    return build_problem_from_custom_jobs(custom_jobs, instance_name=instance_name)


def _apply_downtime_blocks(problem: JobShopProblem, resource_config: Optional[Dict[str, Any]]) -> None:
    from metaforge.utils.problem_builder import apply_downtime_blocks

    apply_downtime_blocks(problem, resource_config)


def _mongo_loop_unusable(exc: BaseException) -> bool:
    return "Event loop is closed" in str(exc)


async def _fetch_resource_config() -> Optional[Dict[str, Any]]:
    try:
        return await db.resource_config.find_one({"_id": "global_config"})
    except Exception as e:
        if _mongo_loop_unusable(e):
            from metaforge.services.resource_config import default_resource_config

            return default_resource_config()
        print(f"[WARN] 读取 resource_config 失败: {e}")
        return None


async def _fetch_materials_catalog() -> List[Dict[str, Any]]:
    from copy import deepcopy

    from metaforge.services.materials_inventory import (
        DEFAULT_MATERIALS,
        fetch_materials_catalog,
    )

    try:
        return await fetch_materials_catalog(material_collection, ensure=True)
    except Exception as e:
        if _mongo_loop_unusable(e):
            return deepcopy(DEFAULT_MATERIALS)
        print(f"[WARN] 读取 materials_catalog 失败: {e}")
        return deepcopy(DEFAULT_MATERIALS)


def _apply_material_enforcement(jobs: List[JobData], inventory: Dict[str, float]) -> Dict[str, Any]:
    delays, notes = compute_material_arrival_delays(jobs, inventory)
    for i, job in enumerate(jobs):
        if delays[i] > 0:
            base = float(job.material_arrival or 0.0)
            job.material_arrival = base + delays[i]
    return {"delays": delays, "notes": notes}


def _run_comparison_blocking(
    req: CompareRequest,
    resource_config: Optional[Dict[str, Any]],
    material_catalog: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    job_name_map = {}
    job_priority_map = {}
    jobs_data: Optional[List[JobData]] = None
    material_enforcement = None
    material_check = None

    if req.custom_data:
        jobs_data = [j.model_copy(deep=True) for j in req.custom_data]
        if req.enforce_material and material_catalog:
            inventory = {m["id"]: float(m.get("current_stock", 0)) for m in material_catalog}
            material_enforcement = _apply_material_enforcement(jobs_data, inventory)
        if material_catalog:
            inventory = {m["id"]: float(m.get("current_stock", 0)) for m in material_catalog}
            names = {m["id"]: m.get("name", m["id"]) for m in material_catalog}
            safe = {m["id"]: float(m.get("safe_level", 0)) for m in material_catalog}
            material_check = check_jobs_material_static(
                jobs_data, inventory, material_names=names, safe_levels=safe
            )
        problem, job_name_map, job_priority_map = _build_problem_from_custom_jobs(
            jobs_data,
            instance_name="Custom Plan",
        )
    elif req.benchmark_file:
        file_path = BASE_DIR / "data" / "benchmarks" / req.benchmark_file
        if not file_path.exists():
            return {"error": "File not found"}
        problem = load_job_shop_instance(str(file_path), format="orlib")
    else:
        return {"error": "No data provided"}

    _apply_downtime_blocks(problem, resource_config)

    results = compare_solvers(
        req.solvers,
        problem,
        weights=req.weights,
        resource_config=resource_config,
        random_seed=req.random_seed,
        solver_params=req.solver_params,
    )

    name_map = job_name_map if req.custom_data else {}
    for res in results.values():
        gantt = res.get("gantt_data") or []
        if req.custom_data:
            for item in gantt:
                jid = item["job_id"]
                if jid in job_name_map:
                    item["job_name"] = job_name_map[jid]
                if jid in job_priority_map:
                    item["priority"] = job_priority_map[jid]
                else:
                    item["priority"] = 10
        cv = (res.get("metrics") or {}).get("machine_busy_cv")
        res["delivery_predictions"] = compute_delivery_predictions(
            gantt,
            problem,
            job_name_map=name_map,
            machine_busy_cv=cv,
        )
        if jobs_data and material_catalog:
            res["material_report"] = build_material_report_for_schedule(
                gantt, jobs_data, material_catalog
            )

    payload: Dict[str, Any] = {"status": "success", "data": results}
    if material_check is not None:
        payload["material_check"] = material_check
    if material_enforcement is not None:
        payload["material_enforcement"] = material_enforcement
    return payload


def _schedule_task_update(task_id: str, patch: Dict[str, Any]) -> None:
    current = _schedule_tasks_mem.get(task_id, {})
    current.update(patch)
    _schedule_tasks_mem[task_id] = current


def _run_async_comparison_worker(
    task_id: str,
    req: CompareRequest,
    resource_config: Optional[Dict[str, Any]],
    material_catalog: Optional[List[Dict[str, Any]]],
) -> None:
    started = time.time()
    try:
        _schedule_task_update(task_id, {"status": "running", "started_at": datetime.now().isoformat()})
        result = _run_comparison_blocking(req, resource_config, material_catalog)
        elapsed = round(time.time() - started, 4)
        if result.get("error"):
            _schedule_task_update(
                task_id,
                {"status": "failed", "error": result["error"], "runtime_sec": elapsed, "finished_at": datetime.now().isoformat()},
            )
        else:
            _schedule_task_update(
                task_id,
                {"status": "completed", "result": result, "runtime_sec": elapsed, "finished_at": datetime.now().isoformat()},
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        _schedule_task_update(
            task_id,
            {
                "status": "failed",
                "error": str(e),
                "runtime_sec": round(time.time() - started, 4),
                "finished_at": datetime.now().isoformat(),
            },
        )


@app.post("/api/run")
async def run_comparison(req: CompareRequest):
    try:
        resource_config = await _fetch_resource_config()
        material_catalog = await _fetch_materials_catalog() if req.custom_data else None
        return _run_comparison_blocking(req, resource_config, material_catalog)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@app.post("/api/run/async")
async def run_comparison_async(req: CompareRequest):
    """提交异步排程任务，返回 task_id；通过 status/result 轮询。"""
    task_id = str(uuid.uuid4())
    resource_config = await _fetch_resource_config()
    material_catalog = await _fetch_materials_catalog() if req.custom_data else None
    _schedule_tasks_mem[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "solvers": req.solvers,
    }
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        _schedule_executor,
        _run_async_comparison_worker,
        task_id,
        req,
        resource_config,
        material_catalog,
    )
    try:
        await schedule_tasks_collection.insert_one(
            {
                "task_id": task_id,
                "status": "pending",
                "created_at": datetime.now(),
                "request": req.model_dump(),
            }
        )
    except Exception as e:
        print(f"[WARN] schedule task 落库失败: {e}")
    return {"status": "accepted", "task_id": task_id}


@app.get("/api/run/status/{task_id}")
async def get_run_status(task_id: str):
    task = _schedule_tasks_mem.get(task_id)
    if not task:
        doc = await schedule_tasks_collection.find_one({"task_id": task_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task_id": task_id,
            "status": doc.get("status", "unknown"),
            "runtime_sec": doc.get("runtime_sec"),
            "error": doc.get("error"),
        }
    return {
        "task_id": task_id,
        "status": task.get("status", "unknown"),
        "runtime_sec": task.get("runtime_sec"),
        "error": task.get("error"),
    }


@app.get("/api/run/result/{task_id}")
async def get_run_result(task_id: str):
    task = _schedule_tasks_mem.get(task_id)
    if not task:
        doc = await schedule_tasks_collection.find_one({"task_id": task_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Task not found")
        if doc.get("status") != "completed":
            return {"status": doc.get("status", "unknown"), "data": None, "error": doc.get("error")}
        return doc.get("result") or {"status": "completed", "data": None}
    status = task.get("status")
    if status != "completed":
        return {"status": status, "data": None, "error": task.get("error")}
    result = task.get("result") or {}
    try:
        await schedule_tasks_collection.update_one(
            {"task_id": task_id},
            {
                "$set": {
                    "status": "completed",
                    "result": result,
                    "runtime_sec": task.get("runtime_sec"),
                    "finished_at": datetime.now(),
                }
            },
            upsert=True,
        )
    except Exception:
        pass
    return result


def _job_completion_map(schedule_data: List[Dict[str, Any]]) -> Dict[int, float]:
    comp = {}
    for op in schedule_data:
        jid = int(op["job_id"])
        comp[jid] = max(float(op["end"]), comp.get(jid, 0.0))
    return comp


def _merge_repaired_schedule(
    frozen_ops: List[Dict[str, Any]],
    repaired_ops: List[Dict[str, Any]],
    residual_index_to_job_id: Dict[int, int],
) -> List[Dict[str, Any]]:
    merged = [dict(op) for op in frozen_ops]
    for op in repaired_ops:
        item = dict(op)
        residual_idx = int(item["job_id"])
        item["job_id"] = int(residual_index_to_job_id.get(residual_idx, residual_idx))
        merged.append(item)
    merged.sort(key=lambda x: (float(x.get("start", 0)), int(x.get("job_id", 0)), int(x.get("operation_id", 0))))
    return merged


@app.post("/api/events/insert_order_reschedule")
async def insert_order_reschedule(req: InsertRescheduleRequest):
    """插单 + 重排（local_repair / global），复用 dispatch 并读取 MES 执行基准。"""
    try:
        if not req.base_jobs:
            return {"error": "base_jobs is empty"}
        exec_doc = await _execution_doc_for_dispatch()
        envelope = {
            "event_type": "insert_order",
            "base_jobs": [j.model_dump() for j in req.base_jobs],
            "params": {
                "insert_job": req.insert_job.model_dump(),
                "freeze_time": req.freeze_time,
                "mode": req.mode,
            },
            "reschedule_options": {
                "solvers": req.solvers,
                "weights": req.weights,
                "random_seed": req.random_seed,
            },
            "production_execution": exec_doc if exec_doc.get("status") in ("running", "paused") else None,
        }
        if exec_doc.get("status") in ("running", "paused"):
            envelope["reschedule_options"]["baseline_gantt"] = exec_doc.get("baseline_gantt")
            envelope["reschedule_options"]["baseline_solver"] = exec_doc.get("baseline_solver")
        return await _event_dispatch_from_request(envelope)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@app.post("/api/events/machine_breakdown_reschedule")
async def machine_breakdown_reschedule(req: MachineBreakdownRequest):
    """设备故障：R0/R1/R2 恢复重排（优先使用 MES 执行基准甘特）。"""
    try:
        from metaforge.services.production_execution import get_state, tick_sim_time

        exec_doc = await get_state(execution_collection)
        if exec_doc.get("status") in ("running", "paused"):
            exec_doc = await tick_sim_time(execution_collection, exec_doc)

        opts: Dict[str, Any] = {
            "solvers": req.solvers,
            "weights": req.weights,
            "random_seed": req.random_seed,
        }
        bl_gantt = req.baseline_gantt or exec_doc.get("baseline_gantt")
        bl_solver = req.baseline_solver or exec_doc.get("baseline_solver")
        if bl_gantt:
            opts["baseline_gantt"] = bl_gantt
        if bl_solver:
            opts["baseline_solver"] = bl_solver

        base_jobs = [j.model_dump() for j in req.base_jobs]
        envelope = {
            "event_type": "machine_breakdown",
            "base_jobs": base_jobs,
            "params": {
                "machine_id": req.machine_id,
                "breakdown_start": req.breakdown_start,
                "breakdown_duration": req.breakdown_duration,
                "freeze_time": req.freeze_time,
            },
            "reschedule_options": opts,
            "production_execution": exec_doc if exec_doc.get("status") in ("running", "paused") else None,
        }
        return await _event_dispatch_from_request(envelope)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@app.get("/api/tools/registry")
async def get_tools_registry():
    """Tool 能力目录（供 Agent / LLM function calling）。"""
    from metaforge.tools.registry import list_tools

    return {"tools": list_tools()}


@app.get("/api/agents/registry")
async def get_agents_registry():
    from metaforge.agents.registry_meta import list_agents

    return {"agents": list_agents()}


def _agent_request_from_body(req: AgentRunRequest) -> "AgentRequest":
    from metaforge.agents.base import AgentRequest

    ctx: Dict[str, Any] = {
        "custom_data": req.custom_data,
        "benchmark_file": req.benchmark_file,
        "plan_id": req.plan_id,
        "random_seed": req.random_seed,
        "weights": req.weights,
        "enforce_material": req.enforce_material,
        "extras": {},
    }
    return AgentRequest(message=req.message, params=dict(req.params or {}), context=ctx)


@app.get("/api/orchestrator/session/{session_id}")
async def get_orchestrator_session(session_id: str):
    from metaforge.orchestrator.session import session_to_api_dict

    data = session_to_api_dict(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="session not found or expired")
    return data


@app.get("/api/orchestrator/session/{session_id}/artifacts")
async def get_orchestrator_session_artifacts(session_id: str):
    """返回会话内 artifacts（含 schedule_results），供前端报表页兜底加载。"""
    from metaforge.orchestrator.session import get_session
    from metaforge.services.schedule_summary import normalize_schedule_results
    from metaforge.utils.bson_safe import to_bson_safe

    s = get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found or expired")
    artifacts = to_bson_safe(dict(s.get("artifacts") or {}))
    sr = normalize_schedule_results(artifacts.get("schedule_results"))
    if sr:
        artifacts["schedule_results"] = sr
    return {
        "session_id": session_id,
        "last_agent_id": s.get("last_agent_id"),
        "artifacts": artifacts,
        "schedule_results": sr or {},
    }


@app.get("/api/orchestrator/route-debug")
async def orchestrator_route_debug(message: str = ""):
    """开发用：查看当前进程加载的路由逻辑与 intent 结果。"""
    import metaforge.orchestrator.router as router_mod
    from metaforge.orchestrator.router import resolve_agent_route

    route = resolve_agent_route(message)
    return {
        "message": message,
        "route": route,
        "router_module": getattr(router_mod, "__file__", ""),
    }


async def _enrich_orchestrator_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """合并 plan_id / custom_data，供助手与编排自动带入工单。"""
    out = dict(ctx or {})
    extras = dict(out.get("extras") or {})
    out["extras"] = extras

    if out.get("plan_id") and not out.get("custom_data"):
        try:
            oid = ObjectId(str(out["plan_id"]))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="无效的 plan_id") from exc
        doc = await orders_collection.find_one({"_id": oid})
        if not doc:
            raise HTTPException(status_code=404, detail="未找到计划")
        jobs_raw = doc.get("jobs") or []
        out["custom_data"] = [JobData(**j) for j in jobs_raw]
        extras.setdefault("plan_name", doc.get("plan_name", ""))
        extras["loaded_plan_id"] = str(doc["_id"])
        extras["plan_job_count"] = len(jobs_raw)

    raw = out.get("custom_data")
    if raw and isinstance(raw, list) and len(raw) and isinstance(raw[0], dict):
        out["custom_data"] = [JobData(**j) for j in raw]

    return out


def _attach_schedule_summary(out: Dict[str, Any]) -> None:
    from metaforge.services.schedule_summary import build_schedule_summary, normalize_schedule_results

    artifacts = out.get("artifacts") or {}
    sr = normalize_schedule_results(artifacts.get("schedule_results"))
    if sr:
        artifacts["schedule_results"] = sr
        out["artifacts"] = artifacts
    summary = build_schedule_summary(sr)
    if summary:
        out["schedule_summary"] = summary


def attach_schedule_results_for_client(out: Dict[str, Any]) -> None:
    """SSE/JSON 响应：顶层 schedule_results / impact_report，便于前端读取。"""
    from metaforge.services.schedule_summary import normalize_schedule_results

    _attach_schedule_summary(out)
    artifacts = out.get("artifacts") or {}
    sr = normalize_schedule_results(artifacts.get("schedule_results"))
    if sr:
        out["schedule_results"] = sr
    impact = artifacts.get("impact_report") or (artifacts.get("impact_summary") or {}).get(
        "impact_report"
    )
    if impact:
        out["impact_report"] = impact
    ig = artifacts.get("impact_gantt")
    if ig:
        out["impact_gantt"] = ig


_AUTO_PERSIST_AGENT_IDS = frozenset({"scheduling", "events"})


async def _maybe_persist_schedule_to_plan(
    ctx: Dict[str, Any],
    artifacts: Dict[str, Any],
    *,
    agent_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """编排/Agent 排程或重排成功后落库：首次直接写，覆盖已有排程则 HITL pending。"""
    if agent_id and agent_id not in _AUTO_PERSIST_AGENT_IDS:
        return None

    from metaforge.services.plan_schedule import persist_schedule_with_hitl
    from metaforge.services.schedule_summary import normalize_schedule_results

    schedule_results = normalize_schedule_results((artifacts or {}).get("schedule_results"))
    if schedule_results and artifacts is not None:
        artifacts["schedule_results"] = schedule_results
    if not schedule_results:
        return None
    plan_id = ctx.get("plan_id") or (ctx.get("extras") or {}).get("loaded_plan_id")
    if not plan_id:
        active = (artifacts or {}).get("active_plan") or {}
        plan_id = active.get("plan_id")
    if not plan_id:
        return None

    impact_summary = (artifacts or {}).get("impact_summary")
    impact_report = (artifacts or {}).get("impact_report")
    if not impact_summary and impact_report:
        from metaforge.services.plan_schedule import build_impact_summary_payload

        impact_summary = build_impact_summary_payload(impact_report)

    updated_jobs = (artifacts or {}).get("updated_jobs")
    if updated_jobs is None and (artifacts or {}).get("production_execution", {}).get("jobs_snapshot"):
        updated_jobs = artifacts["production_execution"]["jobs_snapshot"]

    plan_name = (
        (artifacts or {}).get("active_plan", {}).get("plan_name")
        or ctx.get("plan_name")
        or (ctx.get("extras") or {}).get("plan_name")
    )

    kind, payload = persist_schedule_with_hitl(
        str(plan_id),
        schedule_results,
        interpretation=(artifacts or {}).get("interpretation"),
        delivery_assessment=(artifacts or {}).get("delivery_assessment"),
        impact_summary=impact_summary,
        jobs=updated_jobs,
        plan_name=plan_name,
        status="done",
    )
    if kind == "saved":
        return {"saved_plan_id": payload.get("plan_id")}
    if kind == "pending":
        pending = dict(payload or {})
        if artifacts is not None:
            artifacts["pending_persist"] = {
                "confirm_token": pending.get("confirm_token"),
                "expires_at": pending.get("expires_at"),
                "preview": pending.get("preview"),
            }
        return {"pending_action": pending}
    if kind == "error":
        print(f"[plan_schedule] persist skipped: {(payload or {}).get('error')}")
    return None


def _apply_schedule_persist_outcome(out: Dict[str, Any], persist_out: Optional[Dict[str, Any]]) -> None:
    if not persist_out:
        return
    if persist_out.get("pending_action"):
        pending = persist_out["pending_action"]
        out["status"] = "pending_confirm"
        out["pending_action"] = pending
        summary = pending.get("summary_zh")
        if summary:
            base = (out.get("summary_zh") or "").strip()
            out["summary_zh"] = f"{base} {summary}".strip() if base else summary
        return
    saved = persist_out.get("saved_plan_id")
    if saved:
        out["schedule_saved_to_plan_id"] = saved


async def _hydrate_plan_schedule_into_context(ctx: Dict[str, Any], areq) -> None:
    """将计划库已有排程注入 artifacts，避免 commitment 等误触发新排程。"""
    arts = areq.context.setdefault("artifacts", {})
    if arts.get("schedule_results"):
        return
    plan_id = ctx.get("plan_id") or (ctx.get("extras") or {}).get("loaded_plan_id")
    if not plan_id:
        return
    try:
        oid = ObjectId(str(plan_id))
    except Exception:
        return
    doc = await orders_collection.find_one({"_id": oid})
    if not doc:
        return
    from metaforge.services.schedule_summary import normalize_schedule_results

    sr = normalize_schedule_results(doc.get("schedule_results"))
    if not sr:
        single = doc.get("schedule_result")
        if isinstance(single, dict) and single.get("gantt_data"):
            sid = single.get("id") or single.get("algorithm") or "saved"
            sr = {sid: {**single, "id": sid}}
    if sr:
        arts["schedule_results"] = sr


async def _prepare_orchestrator_areq(
    req: OrchestratorRequest,
    agent_id: str,
    areq,
    ctx: Dict[str, Any],
    params: Dict[str, Any],
):
    """为 Agent.run 补齐物料、资源、计划加载等上下文。"""
    if ctx.get("confirm_token") and "confirm_token" not in params:
        params = {**params, "confirm_token": ctx["confirm_token"]}
        areq.params = params

    if agent_id in ("commitment", "kitting", "whatif"):
        await _hydrate_plan_schedule_into_context(ctx, areq)

    if agent_id == "kitting" and areq.context.get("custom_data"):
        areq.context.setdefault("extras", {})
        extras = areq.context["extras"]
        material_catalog = extras.get("material_catalog")
        if material_catalog is None:
            material_catalog = await _fetch_materials_catalog()
        if material_catalog:
            extras["material_catalog"] = material_catalog
            extras.setdefault(
                "inventory",
                {m["id"]: float(m.get("current_stock", 0)) for m in material_catalog},
            )
            extras.setdefault(
                "material_names",
                {m["id"]: m.get("name", m["id"]) for m in material_catalog},
            )

    if agent_id in ("events", "whatif", "scheduling"):
        areq.context.setdefault("extras", {})
        try:
            cfg = await _fetch_resource_config()
            from metaforge.services.resource_config import effective_resource_config

            areq.context["extras"]["resource_config"] = effective_resource_config(cfg)
        except Exception:
            from metaforge.services.resource_config import default_resource_config

            areq.context["extras"]["resource_config"] = default_resource_config()

    if agent_id == "events":
        areq.context.setdefault("extras", {})
        try:
            exec_state = await _execution_doc_for_dispatch()
            if exec_state.get("status") in ("running", "paused"):
                areq.context["extras"]["production_execution"] = exec_state
        except Exception:
            pass

    if agent_id == "scheduling":
        areq.context.setdefault("extras", {})
        if req.context.get("plan_id") and not areq.context.get("custom_data"):
            try:
                oid = ObjectId(req.context["plan_id"])
            except Exception as exc:
                raise HTTPException(status_code=400, detail="无效的 plan_id") from exc
            doc = await orders_collection.find_one({"_id": oid})
            if doc and doc.get("jobs"):
                areq.context["custom_data"] = [JobData(**j) for j in doc["jobs"]]
                areq.context["extras"]["loaded_plan_id"] = str(doc["_id"])
                areq.context["extras"]["plan_name"] = doc.get("plan_name", "未命名计划")
        if not areq.context["extras"].get("resource_config"):
            try:
                cfg = await _fetch_resource_config()
                from metaforge.services.resource_config import effective_resource_config

                areq.context["extras"]["resource_config"] = effective_resource_config(cfg)
            except Exception:
                from metaforge.services.resource_config import default_resource_config

                areq.context["extras"]["resource_config"] = default_resource_config()

    return areq


@app.post("/api/orchestrator/preview")
async def orchestrator_preview(req: OrchestratorRequest):
    """预览路由与执行计划（不跑 Tool），供前端「思考过程」展示。"""
    from metaforge.orchestrator.preview import build_orchestrator_preview
    from metaforge.orchestrator.session import apply_session_to_context

    session_id = (req.context or {}).get("session_id")
    ctx = await _enrich_orchestrator_context(apply_session_to_context(session_id, dict(req.context or {})))
    try:
        return build_orchestrator_preview(
            req.message,
            req.intent,
            context=ctx,
            params=req.params,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/orchestrator/stream")
async def orchestrator_stream(req: OrchestratorRequest):
    """SSE 流式返回思考过程（路由 / 计划 / 逐步执行）。"""
    from starlette.responses import StreamingResponse

    from metaforge.orchestrator.preview import build_orchestrator_preview
    from metaforge.orchestrator.session import apply_session_to_context, persist_after_run
    from metaforge.orchestrator.stream import iter_orchestrator_sse, sse_event
    from metaforge.services.persist_store import confirm_and_persist

    session_id = (req.context or {}).get("session_id")
    ctx = await _enrich_orchestrator_context(apply_session_to_context(session_id, dict(req.context or {})))
    params = dict(req.params or {})

    async def event_gen():
        try:
            if ctx.get("confirm_token") and "confirm_token" not in params:
                params["confirm_token"] = ctx["confirm_token"]

            if req.intent:
                from metaforge.orchestrator.router import resolve_agent_route

                route = resolve_agent_route(req.message, req.intent, ctx)
                agent_id = route["agent_id"]
            else:
                route = {}
                agent_id = ""

            if agent_id == "scheduling" and params.get("confirm_token"):
                preview = build_orchestrator_preview(
                    req.message, req.intent, context=ctx, params=params
                )
                route = preview.get("route") or route
                preview_trace = list(preview.get("trace") or [])
                for block in preview_trace:
                    yield sse_event({"event": "trace_block", "block": block})
                result = await confirm_and_persist(params["confirm_token"], orders_collection)
                if result.get("error"):
                    yield sse_event({"event": "error", "detail": result["error"]})
                    return
                out = {
                    "status": "success",
                    "agent": "scheduling",
                    "agent_id": "scheduling",
                    "summary_zh": "排程结果已写入数据库。",
                    "artifacts": result,
                    "plan": [],
                    "execution_trace": preview_trace,
                    "router_planner": route.get("router"),
                    "session_id": persist_after_run(
                        session_id,
                        agent_id="scheduling",
                        request_context=ctx,
                        response={"status": "success", "agent_id": "scheduling"},
                    ),
                }
                yield sse_event({"event": "done", "data": out})
                return

            async def prepare_areq(route, agent, areq, _preview_trace):
                return await _prepare_orchestrator_areq(req, route["agent_id"], areq, ctx, params)

            def run_agent_fn(agent, areq, preview_trace, route, on_step_start, on_step_done):
                return agent.run(areq, on_step_start=on_step_start, on_step_done=on_step_done)

            async def finalize_out(out, route, preview_trace, agent_id, areq):
                if out.get("status") == "success":
                    attach_schedule_results_for_client(out)
                    await _maybe_sync_events_agent_response(out, areq)
                    arts = out.get("artifacts") or {}
                    if not arts.get("pending_persist") and not out.get("pending_action"):
                        saved = await _maybe_persist_schedule_to_plan(
                            areq.context,
                            arts,
                            agent_id=agent_id,
                        )
                        _apply_schedule_persist_outcome(out, saved)
                try:
                    from metaforge.services.audit_log import log_agent_action

                    log_agent_action(
                        action="orchestrator_stream",
                        agent_id=agent_id or "",
                        message=req.message,
                        status=str(out.get("status") or ""),
                        session_id=session_id,
                        plan_id=areq.context.get("plan_id"),
                    )
                except Exception:
                    pass
                out["session_id"] = persist_after_run(
                    session_id,
                    agent_id=agent_id,
                    request_context=areq.context,
                    response=out,
                )
                return out

            async for chunk in iter_orchestrator_sse(
                req.message,
                req.intent,
                ctx,
                params,
                prepare_areq=prepare_areq,
                run_agent_fn=run_agent_fn,
                finalize_out=finalize_out,
            ):
                yield chunk
        except HTTPException as e:
            yield sse_event({"event": "error", "detail": e.detail})
        except ValueError as e:
            yield sse_event({"event": "error", "detail": str(e)})
        except Exception as e:
            yield sse_event({"event": "error", "detail": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/orchestrator/run")
async def orchestrator_run(req: OrchestratorRequest):
    from metaforge.agents.base import AgentRequest
    from metaforge.orchestrator.execution_trace import merge_run_trace
    from metaforge.orchestrator.preview import build_orchestrator_preview
    from metaforge.orchestrator.router import get_agent, resolve_agent_route
    from metaforge.orchestrator.session import apply_session_to_context, persist_after_run
    from metaforge.services.persist_store import confirm_and_persist

    session_id = (req.context or {}).get("session_id")
    ctx = await _enrich_orchestrator_context(apply_session_to_context(session_id, dict(req.context or {})))

    try:
        preview = build_orchestrator_preview(
            req.message,
            req.intent,
            context=ctx,
            params=req.params,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    route = preview.get("route") or resolve_agent_route(req.message, req.intent, ctx)
    agent_id = preview.get("agent_id")
    preview_trace: List[Dict[str, Any]] = list(preview.get("trace") or [])

    if route.get("out_of_scope") or preview.get("status") == "out_of_scope":
        out = {
            "status": "out_of_scope",
            "agent_id": None,
            "summary_zh": route.get("guidance_zh") or preview.get("summary_zh") or "",
            "scope_category": route.get("scope_category"),
            "execution_trace": preview_trace,
            "router_planner": route.get("router"),
            "router_intent": route.get("intent"),
            "router_reason_zh": route.get("reason_zh"),
        }
        out["session_id"] = persist_after_run(
            session_id,
            agent_id="",
            request_context=ctx,
            response=out,
        )
        return out

    params = dict(req.params or {})
    if ctx.get("confirm_token") and "confirm_token" not in params:
        params["confirm_token"] = ctx["confirm_token"]

    if agent_id == "scheduling" and params.get("confirm_token"):
        result = await confirm_and_persist(params["confirm_token"], orders_collection)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        out = {
            "status": "success",
            "agent": "scheduling",
            "agent_id": "scheduling",
            "summary_zh": "排程结果已写入数据库。",
            "artifacts": result,
            "plan": [],
        }
        out["execution_trace"] = preview_trace
        out["router_planner"] = route.get("router")
        out["session_id"] = persist_after_run(
            session_id,
            agent_id="scheduling",
            request_context=ctx,
            response=out,
        )
        return out

    try:
        agent = get_agent(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    areq = AgentRequest(message=req.message, params=params, context=ctx)
    areq = await _prepare_orchestrator_areq(req, agent_id, areq, ctx, params)

    resp = agent.run(areq)
    out = resp.to_dict()
    out["agent_id"] = agent_id
    active = (out.get("artifacts") or {}).get("active_plan")
    if active:
        out["plan_id"] = active.get("plan_id")
        areq.context["plan_id"] = active.get("plan_id")
        jobs = active.get("jobs")
        if jobs:
            areq.context["custom_data"] = jobs
    out["router_planner"] = route.get("router")
    if route.get("intent"):
        out["router_intent"] = route["intent"]
    reason = route.get("reason_zh") or route.get("rule_reason_zh")
    if reason:
        out["router_reason_zh"] = reason
    if route.get("llm_error"):
        out["router_llm_error"] = route["llm_error"]
    out["execution_trace"] = merge_run_trace(preview_trace, out.get("plan") or [])
    if out.get("status") == "success":
        attach_schedule_results_for_client(out)
        await _maybe_sync_events_agent_response(out, areq)
        arts = out.get("artifacts") or {}
        if not arts.get("pending_persist") and not out.get("pending_action"):
            saved = await _maybe_persist_schedule_to_plan(
                ctx, arts, agent_id=agent_id
            )
            _apply_schedule_persist_outcome(out, saved)
    try:
        from metaforge.services.audit_log import log_agent_action

        log_agent_action(
            action="orchestrator_run",
            agent_id=agent_id or "",
            message=req.message,
            status=str(out.get("status") or ""),
            session_id=session_id,
            plan_id=ctx.get("plan_id"),
        )
    except Exception:
        pass
    out["session_id"] = persist_after_run(
        session_id,
        agent_id=agent_id,
        request_context=areq.context,
        response=out,
    )
    return out


async def _hydrate_scheduling_agent_request(req: AgentRunRequest, areq):
    """为 scheduling 直连补齐计划工单、资源与落库确认。"""
    from metaforge.services.resource_config import default_resource_config, effective_resource_config

    areq.context.setdefault("extras", {})
    token = (req.params or {}).get("confirm_token")
    if token:
        return areq

    if req.plan_id and not areq.context.get("custom_data"):
        try:
            oid = ObjectId(req.plan_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="无效的 plan_id") from exc
        doc = await orders_collection.find_one({"_id": oid})
        if not doc or not doc.get("jobs"):
            raise HTTPException(status_code=404, detail="未找到计划或计划无工单数据")
        areq.context["custom_data"] = [JobData(**j) for j in doc["jobs"]]
        areq.context["extras"]["loaded_plan_id"] = str(doc["_id"])
        areq.context["extras"]["plan_name"] = doc.get("plan_name", "未命名计划")
    elif req.custom_data and req.plan_id:
        areq.context["extras"]["loaded_plan_id"] = req.plan_id

    try:
        cfg = await _fetch_resource_config()
        areq.context["extras"]["resource_config"] = effective_resource_config(cfg)
    except Exception:
        areq.context["extras"]["resource_config"] = default_resource_config()
    return areq


@app.post("/api/agents/scheduling/run")
async def agents_scheduling_run(req: AgentRunRequest):
    from metaforge.agents.scheduling import SchedulingAgentRunner
    from metaforge.services.persist_store import confirm_and_persist

    params = dict(req.params or {})
    token = params.get("confirm_token")
    if token:
        result = await confirm_and_persist(token, orders_collection)
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {
            "status": "success",
            "agent": "scheduling",
            "agent_id": "scheduling",
            "summary_zh": "排程结果已写入数据库。",
            "artifacts": result,
        }

    if req.custom_data is not None and params.get("skip_parse") is None:
        params["skip_parse"] = False
    req.params = params
    areq = _agent_request_from_body(req)
    areq = await _hydrate_scheduling_agent_request(req, areq)
    agent = SchedulingAgentRunner()
    return agent.run(areq).to_dict()


@app.post("/api/agents/commitment/run")
async def agents_commitment_run(req: AgentRunRequest):
    from metaforge.agents.commitment import CommitmentAgentRunner

    agent = CommitmentAgentRunner()
    return agent.run(_agent_request_from_body(req)).to_dict()


@app.post("/api/agents/kitting/run")
async def agents_kitting_run(req: AgentRunRequest):
    from metaforge.agents.kitting import KittingAgentRunner

    areq = _agent_request_from_body(req)
    if req.custom_data and "inventory" not in areq.context.get("extras", {}):
        material_catalog = await _fetch_materials_catalog()
        if material_catalog:
            areq.context.setdefault("extras", {})
            areq.context["extras"]["inventory"] = {
                m["id"]: float(m.get("current_stock", 0)) for m in material_catalog
            }
            areq.context["extras"]["material_names"] = {
                m["id"]: m.get("name", m["id"]) for m in material_catalog
            }
            areq.context["extras"]["material_catalog"] = material_catalog
    agent = KittingAgentRunner()
    return agent.run(areq).to_dict()


@app.post("/api/agents/events/run")
async def agents_events_run(req: AgentRunRequest):
    from metaforge.agents.events import EventsAgentRunner

    areq = _agent_request_from_body(req)
    areq.context.setdefault("extras", {})
    try:
        areq.context["extras"]["resource_config"] = await _fetch_resource_config()
    except Exception:
        pass
    try:
        exec_state = await _execution_doc_for_dispatch()
        if exec_state.get("status") in ("running", "paused"):
            areq.context["extras"]["production_execution"] = exec_state
    except Exception:
        pass
    agent = EventsAgentRunner()
    out = agent.run(areq).to_dict()
    out["agent_id"] = "events"
    if out.get("status") == "success":
        await _maybe_sync_events_agent_response(out, areq)
    return out


async def _execution_doc_for_dispatch() -> Dict[str, Any]:
    from metaforge.services.production_execution import get_state, tick_sim_time

    exec_doc = await get_state(execution_collection)
    if exec_doc.get("status") in ("running", "paused"):
        exec_doc = await tick_sim_time(execution_collection, exec_doc)
    return exec_doc or {}


async def _sync_execution_after_reschedule(
    data: Dict[str, Any],
    envelope: Dict[str, Any],
) -> None:
    from metaforge.services.production_execution import sync_execution_after_event_reschedule

    await sync_execution_after_event_reschedule(execution_collection, data, envelope)


async def _maybe_sync_events_agent_response(out: Dict[str, Any], areq) -> None:
    """Agent/编排 events 成功后与看板 REST 一样写回 MES 执行态。"""
    agent_id = out.get("agent_id") or out.get("agent")
    if agent_id != "events" or out.get("status") != "success":
        return
    artifacts = out.get("artifacts") or {}
    envelope = artifacts.get("event_envelope")
    if not isinstance(envelope, dict) or not envelope.get("event_type"):
        return
    impact = artifacts.get("impact_report") or (artifacts.get("impact_summary") or {}).get(
        "impact_report"
    )
    results = artifacts.get("schedule_results")
    if not impact and not results:
        return
    exec_doc = (areq.context.get("extras") or {}).get("production_execution")
    if not exec_doc or exec_doc.get("status") not in ("running", "paused"):
        return
    env = dict(envelope)
    env["production_execution"] = exec_doc
    data = {
        "results": results,
        "impact_report": impact,
        "updated_jobs": artifacts.get("updated_jobs"),
    }
    await _sync_execution_after_reschedule(data, env)
    if data.get("production_execution"):
        artifacts["production_execution"] = data["production_execution"]
        out["production_execution"] = data["production_execution"]


async def _event_dispatch_from_request(envelope: Dict[str, Any]) -> Dict[str, Any]:
    from metaforge.services.event_reschedule import dispatch_event_reschedule

    resource_config = await _fetch_resource_config()
    opts = envelope.get("reschedule_options") or {}
    opts["resource_config"] = resource_config
    envelope["reschedule_options"] = opts
    raw = dispatch_event_reschedule(envelope)
    if raw.get("error"):
        return raw
    data = raw.get("data") or {}
    exec_doc = envelope.get("production_execution") or {}
    if exec_doc.get("status") in ("running", "paused"):
        await _sync_execution_after_reschedule(data, envelope)
    return raw


@app.post("/api/events/planned_downtime")
async def planned_downtime_reschedule(req: PlannedDowntimeRequest):
    envelope = {
        "event_type": "planned_downtime",
        "base_jobs": req.base_jobs,
        "params": {"downtime_blocks": [b.model_dump() for b in req.downtime_blocks]},
        "reschedule_options": {
            "solvers": req.solvers,
            "weights": req.weights,
            "random_seed": req.random_seed,
        },
    }
    return await _event_dispatch_from_request(envelope)


@app.post("/api/events/material_delay")
async def material_delay_reschedule(req: MaterialDelayRequest):
    envelope = {
        "event_type": "material_delay",
        "base_jobs": req.base_jobs,
        "params": {"job_name": req.job_name, "delay_hours": req.delay_hours},
        "reschedule_options": {
            "solvers": req.solvers,
            "weights": req.weights,
            "random_seed": req.random_seed,
        },
    }
    return await _event_dispatch_from_request(envelope)


@app.post("/api/events/priority_change")
async def priority_change_reschedule(req: PriorityChangeRequest):
    envelope = {
        "event_type": "priority_change",
        "base_jobs": req.base_jobs,
        "params": {"changes": [c.model_dump() for c in req.changes]},
        "reschedule_options": {
            "solvers": req.solvers,
            "weights": req.weights,
            "random_seed": req.random_seed,
        },
    }
    return await _event_dispatch_from_request(envelope)


@app.post("/api/events/order_cancel")
async def order_cancel_reschedule(req: OrderCancelRequest):
    envelope = {
        "event_type": "order_cancel",
        "base_jobs": req.base_jobs,
        "params": {"job_names": req.job_names},
        "reschedule_options": {
            "solvers": req.solvers,
            "weights": req.weights,
            "random_seed": req.random_seed,
        },
    }
    return await _event_dispatch_from_request(envelope)


class ProposeSaveRequest(BaseModel):
    plan_id: str
    schedule_result: Dict[str, Any]
    delivery_assessment: Optional[Dict[str, Any]] = None
    plan_name: Optional[str] = None
    interpretation: Optional[Dict[str, Any]] = None


class ConfirmSaveRequest(BaseModel):
    confirm_token: str


@app.post("/api/db/propose_save")
async def db_propose_save(req: ProposeSaveRequest):
    from metaforge.services.persist_store import propose_persist

    return propose_persist(
        plan_id=req.plan_id,
        schedule_result=req.schedule_result,
        delivery_assessment=req.delivery_assessment,
        plan_name=req.plan_name,
        interpretation=req.interpretation,
    )


@app.post("/api/db/confirm_save")
async def db_confirm_save(req: ConfirmSaveRequest):
    from metaforge.services.persist_store import confirm_and_persist

    result = await confirm_and_persist(req.confirm_token, orders_collection)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/agents/whatif/run")
async def agents_whatif_run(req: AgentRunRequest):
    from metaforge.agents.whatif import WhatifAgentRunner

    areq = _agent_request_from_body(req)
    areq.context.setdefault("extras", {})
    try:
        areq.context["extras"]["resource_config"] = await _fetch_resource_config()
    except Exception:
        pass
    agent = WhatifAgentRunner()
    return agent.run(areq).to_dict()


@app.post("/api/agents/plans/run")
async def agents_plans_run(req: AgentRunRequest):
    from metaforge.agents.plans import PlansAgentRunner

    agent = PlansAgentRunner()
    return agent.run(_agent_request_from_body(req)).to_dict()


@app.post("/api/agents/pipeline/run")
async def agents_pipeline_run_deprecated(req: AgentRunRequest):
    """已废弃：pipeline 合并入 scheduling。请使用 /api/agents/scheduling/run。"""
    req.params = {**(req.params or {}), "persist_after": True}
    return await agents_scheduling_run(req)


def _planning_enabled() -> bool:
    return os.getenv("PLANNING_STRATEGY_V1", "1").strip() not in ("0", "false", "False")


def _planning_collab_enabled() -> bool:
    return os.getenv("PLANNING_COLLAB_V1", "1").strip() not in ("0", "false", "False")


def _require_planning():
    if not _planning_enabled():
        raise HTTPException(status_code=404, detail="planning strategy v1 disabled")


def _require_planning_collab():
    if not _planning_collab_enabled():
        raise HTTPException(status_code=404, detail="planning collab v1 disabled")


@app.get("/api/planning/strategy/presets")
async def planning_strategy_presets():
    _require_planning()
    from metaforge.strategy.presets import list_presets

    return {"presets": list_presets()}


@app.get("/api/planning/constraints/catalog")
async def planning_constraints_catalog():
    _require_planning()
    from metaforge.strategy.catalog import (
        HARD_CONSTRAINT_TYPES,
        SOFT_CONSTRAINT_TYPES,
        SOFT_FOLDS_INTO,
        list_constraint_catalog,
    )

    return {
        "catalog": list_constraint_catalog(),
        "hard_types": sorted(HARD_CONSTRAINT_TYPES),
        "soft_types": sorted(SOFT_CONSTRAINT_TYPES),
        "soft_folds_into": dict(SOFT_FOLDS_INTO),
    }


@app.post("/api/planning/strategy/generate")
async def planning_strategy_generate(body: Dict[str, Any] = Body(...)):
    _require_planning()
    from metaforge.strategy.generator import generate_strategy

    strategy, meta = generate_strategy(
        user_goal=body.get("user_goal") or "",
        jobs=body.get("jobs") or [],
        machines=body.get("machines") or [],
        llm_client=body.get("llm_client"),
        workers=body.get("workers"),
        tools=body.get("tools"),
        allow_simulated=body.get("allow_simulated", True),
    )
    return {"strategy": strategy.to_dict(), "meta": meta}


@app.post("/api/planning/strategy/validate")
async def planning_strategy_validate(body: Dict[str, Any] = Body(...)):
    _require_planning()
    from metaforge.strategy.guardrails import validate_strategy
    from metaforge.strategy.models import SchedulingStrategy

    raw = body.get("strategy")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="strategy must be an object")
    strategy = SchedulingStrategy.from_dict(raw)
    ok, errors, fixed = validate_strategy(
        strategy,
        jobs=body.get("jobs") or [],
        machines=body.get("machines") or [],
        workers=body.get("workers"),
        tools=body.get("tools"),
        allow_simulated=body.get("allow_simulated", True),
    )
    return {"ok": ok, "errors": errors, "strategy": fixed.to_dict()}


@app.post("/api/planning/strategy/evaluate")
async def planning_strategy_evaluate(body: Dict[str, Any] = Body(...)):
    _require_planning()
    from metaforge.strategy.evaluator import evaluate_candidates
    from metaforge.strategy.models import SchedulingStrategy

    raw = body.get("strategy")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="strategy must be an object")
    strategy = SchedulingStrategy.from_dict(raw)
    evaluation = evaluate_candidates(
        strategy,
        list(body.get("candidates") or []),
        jobs=body.get("jobs") or [],
    )
    return evaluation


@app.post("/api/planning/run")
async def planning_run(body: Dict[str, Any] = Body(...)):
    _require_planning()
    from metaforge.strategy.pipeline import run_planning

    try:
        return run_planning(
            user_goal=body.get("user_goal") or "",
            jobs=body.get("jobs") or [],
            machines=body.get("machines") or [],
            skip_strategy_hitl=bool(body.get("skip_strategy_hitl", False)),
            llm_client=body.get("llm_client"),
            problem=body.get("problem"),
            workers=body.get("workers"),
            tools=body.get("tools"),
            allow_simulated=body.get("allow_simulated", True),
            preset_id=body.get("preset_id"),
            strategy=body.get("strategy"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/planning/collab/analyze")
async def planning_collab_analyze(body: Dict[str, Any] = Body(...)):
    _require_planning_collab()
    from metaforge.planning_collab.supervisor import run_collab_analyze

    return run_collab_analyze(
        user_goal=body.get("user_goal") or "",
        jobs=body.get("jobs") or [],
        machines=body.get("machines") or [],
        llm_client=body.get("llm_client"),
        parallel=bool(body.get("parallel", True)),
    )


@app.post("/api/planning/collab/run")
async def planning_collab_run(body: Dict[str, Any] = Body(...)):
    _require_planning_collab()
    from metaforge.planning_collab.supervisor import run_collab

    return run_collab(
        user_goal=body.get("user_goal") or "",
        jobs=body.get("jobs") or [],
        machines=body.get("machines") or [],
        skip_strategy_hitl=bool(body.get("skip_strategy_hitl", False)),
        llm_client=body.get("llm_client"),
        problem=body.get("problem"),
        parallel=bool(body.get("parallel", True)),
    )


@app.get("/api/planning/collab/runs/{run_id}")
async def planning_collab_get_run(run_id: str):
    _require_planning_collab()
    from metaforge.planning_collab.supervisor import get_collab_run

    run = get_collab_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="collab run not found")
    return run


@app.get("/api/planning/runs/{run_id}")
async def planning_get_run(run_id: str):
    _require_planning()
    from metaforge.strategy.run_state import get_run

    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.post("/api/planning/runs/{run_id}/strategy/approve")
async def planning_strategy_approve(run_id: str, body: Dict[str, Any] = Body(default={})):
    _require_planning()
    from metaforge.strategy.hitl import approve_strategy
    from metaforge.strategy.pipeline import resume_planning

    out = approve_strategy(run_id)
    if out.get("status") == "FAILED":
        raise HTTPException(status_code=400, detail=out.get("error") or "approve failed")
    if out.get("status") == "RUNNING":
        out = resume_planning(run_id, problem=body.get("problem"))
    return out


@app.post("/api/planning/runs/{run_id}/strategy/reject")
async def planning_strategy_reject(run_id: str, body: Dict[str, Any] = Body(default={})):
    _require_planning()
    from metaforge.strategy.hitl import reject_strategy

    return reject_strategy(run_id, reason=body.get("reason") or "")


@app.post("/api/planning/runs/{run_id}/strategy/edit_and_approve")
async def planning_strategy_edit_and_approve(run_id: str, body: Dict[str, Any] = Body(...)):
    _require_planning()
    from metaforge.strategy.hitl import edit_and_approve
    from metaforge.strategy.pipeline import resume_planning
    from metaforge.strategy.run_state import get_run

    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    raw = body.get("strategy")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="strategy must be an object")
    out = edit_and_approve(
        run_id,
        raw,
        jobs=body.get("jobs") or run.get("jobs") or [],
        machines=body.get("machines") or run.get("machines") or [],
        workers=body.get("workers"),
        tools=body.get("tools"),
        allow_simulated=body.get("allow_simulated", True),
    )
    if out.get("status") == "RUNNING":
        out = resume_planning(run_id, problem=body.get("problem"))
    return out


@app.post("/api/events/quantity_change")
async def quantity_change_reschedule(req: QuantityChangeRequest):
    envelope = {
        "event_type": "quantity_change",
        "base_jobs": req.base_jobs,
        "params": {"changes": [c.model_dump() for c in req.changes]},
        "reschedule_options": {
            "solvers": req.solvers,
            "weights": req.weights,
            "random_seed": req.random_seed,
        },
    }
    return await _event_dispatch_from_request(envelope)


@app.get("/api/strategy/templates")
async def get_strategy_templates():
    return {"templates": STRATEGY_TEMPLATES}


_scheduling_agent = SchedulingAgent()


@app.get("/api/agent/info")
async def get_scheduling_agent_info():
    """多智能体路由：查询排程 Agent 能力与接口说明。"""
    return SchedulingAgent.capabilities()


@app.post("/api/agent/schedule")
async def scheduling_agent_run(req: AgentScheduleRequest):
    """
    智能排程 Agent 统一入口。

    多智能体系统把用户的自然语言排程需求转发到此接口即可；
    Agent 解析算法、目标权重与物料选项后调用现有排程引擎。
    """
    custom_data = req.custom_data
    benchmark_file = req.benchmark_file

    if req.plan_id and not custom_data:
        try:
            oid = ObjectId(req.plan_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="无效的 plan_id") from exc
        doc = await orders_collection.find_one({"_id": oid})
        if not doc or not doc.get("jobs"):
            raise HTTPException(status_code=404, detail="未找到计划或计划无工单数据")
        custom_data = [JobData(**j) for j in doc["jobs"]]

    from metaforge.scheduling.resolve_intent import resolve_schedule_intent

    interpretation = resolve_schedule_intent(
        {
            "message": req.message,
            "solvers": req.solvers,
            "weights": req.weights,
            "strategy_id": req.strategy_id,
            "enforce_material": req.enforce_material,
            "benchmark_file": benchmark_file,
        },
        benchmark_file=benchmark_file,
    )
    planner = interpretation.get("planner", "rule")

    if req.parse_only:
        return {
            "status": "parsed",
            "agent": SchedulingAgent.agent_id,
            "planner": planner,
            "interpretation": interpretation,
        }

    bench = interpretation.get("benchmark_file") if not custom_data else None
    if not custom_data and not bench:
        return {
            "status": "need_data",
            "agent": SchedulingAgent.agent_id,
            "planner": planner,
            "interpretation": interpretation,
            "message_zh": "请提供 custom_data、benchmark_file 或 plan_id 之一后再执行排程",
        }

    compare_req = CompareRequest(
        solvers=interpretation["solvers"],
        custom_data=custom_data,
        benchmark_file=bench,
        weights=interpretation["weights"],
        random_seed=req.random_seed,
        enforce_material=interpretation["enforce_material"],
    )

    if req.async_run:
        async_resp = await run_comparison_async(compare_req)
        return {
            "status": "submitted",
            "agent": SchedulingAgent.agent_id,
            "planner": planner,
            "interpretation": interpretation,
            "task_id": async_resp.get("task_id"),
            "poll": {
                "status": f"/api/run/status/{async_resp.get('task_id')}",
                "result": f"/api/run/result/{async_resp.get('task_id')}",
            },
        }

    try:
        resource_config = await _fetch_resource_config()
        material_catalog = await _fetch_materials_catalog() if compare_req.custom_data else None
        run_result = _run_comparison_blocking(compare_req, resource_config, material_catalog)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "agent": SchedulingAgent.agent_id,
            "planner": planner,
            "interpretation": interpretation,
            "error": str(e),
        }

    if run_result.get("error"):
        return {
            "status": "error",
            "agent": SchedulingAgent.agent_id,
            "planner": planner,
            "interpretation": interpretation,
            "error": run_result["error"],
        }

    return {
        "status": "success",
        "agent": SchedulingAgent.agent_id,
        "planner": planner,
        "interpretation": interpretation,
        **run_result,
    }


@app.get("/api/llm/status")
async def llm_status():
    import os
    from metaforge.orchestrator.session import session_store_mode, use_mongo_store

    plan_agents = [x.strip() for x in os.getenv("LLM_PLAN_AGENTS", "scheduling,events").split(",") if x.strip()]
    import metaforge.orchestrator.router as router_mod

    return {
        "enabled": os.getenv("LLM_ENABLED") == "1",
        "model": os.getenv("ZHIPU_MODEL", "glm-4.5-air"),
        "has_api_key": bool(os.getenv("ZHIPU_API_KEY")),
        "fallback": os.getenv("LLM_FALLBACK", "rule"),
        "llm_router": os.getenv("LLM_ROUTER", "glm"),
        "plan_enabled": os.getenv("LLM_PLAN_ENABLED", "1") == "1",
        "plan_agents": plan_agents,
        "session_store": session_store_mode(),
        "session_persisted": use_mongo_store(),
        "router_module": getattr(router_mod, "__file__", ""),
        "router_build_id": getattr(router_mod, "ROUTER_BUILD_ID", ""),
    }


@app.get("/api/mcp/status")
async def mcp_status():
    from metaforge.orchestrator.mcp_adapter import list_mcp_tools, mcp_enabled

    return {
        "enabled": mcp_enabled(),
        "server_url_configured": bool((__import__("os").getenv("MCP_SERVER_URL") or "").strip()),
        "tools": list_mcp_tools(),
    }


@app.get("/api/objectives/schema")
async def get_objectives_schema_api():
    """多目标指标与综合评分公式（Agent / 前端共用）。"""
    return get_objectives_schema()


@app.get("/api/solvers/catalog")
async def get_solvers_catalog(family: Optional[str] = None):
    """
    求解器目录：算法说明、优化模式、NL 关键词、默认参数等。
    供 Agent 语义/关键词匹配及前端动态展示。
    """
    try:
        catalog = get_solver_catalog(family=family)
        catalog["objectives_ref"] = "/api/objectives/schema"
        return catalog
    except Exception as e:
        return {"error": str(e), "solvers": []}


async def _prepare_problem_async(req: SingleSolverRunRequest):
    jobs_data = None
    material_check = None
    material_enforcement = None

    if req.custom_data:
        jobs_data = [j.model_copy(deep=True) for j in req.custom_data]
        material_catalog = await _fetch_materials_catalog()
        if req.enforce_material and material_catalog:
            inventory = {m["id"]: float(m.get("current_stock", 0)) for m in material_catalog}
            material_enforcement = _apply_material_enforcement(jobs_data, inventory)
        if material_catalog:
            inventory = {m["id"]: float(m.get("current_stock", 0)) for m in material_catalog}
            names = {m["id"]: m.get("name", m["id"]) for m in material_catalog}
            safe = {m["id"]: float(m.get("safe_level", 0)) for m in material_catalog}
            material_check = check_jobs_material_static(
                jobs_data, inventory, material_names=names, safe_levels=safe
            )
        problem, job_name_map, job_priority_map = _build_problem_from_custom_jobs(
            jobs_data, instance_name="Custom Plan"
        )
        return problem, jobs_data, job_name_map, job_priority_map, material_check, material_enforcement

    if req.benchmark_file:
        file_path = BASE_DIR / "data" / "benchmarks" / req.benchmark_file
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Benchmark file not found")
        problem = load_job_shop_instance(str(file_path), format="orlib")
        return problem, None, {}, {}, None, None

    raise HTTPException(status_code=400, detail="No data provided: custom_data or benchmark_file required")


@app.post("/api/solvers/{solver_id}/run")
async def run_single_solver_api(solver_id: str, req: SingleSolverRunRequest):
    """运行单个求解器（Agent 试探 / 单算法诊断）。"""
    try:
        sid = resolve_solver_id(solver_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    try:
        resource_config = await _fetch_resource_config()
        problem, jobs_data, job_name_map, job_priority_map, material_check, material_enforcement = (
            await _prepare_problem_async(req)
        )
        _apply_downtime_blocks(problem, resource_config)

        sr = run_single_solver(
            sid,
            problem,
            weights=req.weights,
            resource_config=resource_config,
            random_seed=req.random_seed,
            solver_params=req.solver_params,
        )

        gantt = sr.gantt_data
        if jobs_data:
            for item in gantt:
                jid = item["job_id"]
                if jid in job_name_map:
                    item["job_name"] = job_name_map[jid]
                if jid in job_priority_map:
                    item["priority"] = job_priority_map[jid]

        if jobs_data:
            catalog = await _fetch_materials_catalog()
            if catalog:
                sr.meta["material_report"] = build_material_report_for_schedule(gantt, jobs_data, catalog)

        cv = sr.metrics.get("machine_busy_cv")
        sr.meta["delivery_predictions"] = compute_delivery_predictions(
            gantt, problem, job_name_map=job_name_map if jobs_data else {}, machine_busy_cv=cv
        )

        payload = {
            "status": "success",
            "solver_id": sid,
            "result": sr.to_api_dict(),
            "delivery_predictions": sr.meta.get("delivery_predictions"),
            "bottleneck_report": sr.meta.get("bottleneck_report"),
            "material_report": sr.meta.get("material_report"),
        }
        if material_check is not None:
            payload["material_check"] = material_check
        if material_enforcement is not None:
            payload["material_enforcement"] = material_enforcement
        return payload
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@app.post("/api/routing/save")
async def save_routing_template(template: RoutingTemplateSchema):
    doc = template.model_dump()
    result = await routing_templates_collection.insert_one(doc)
    return {"status": "success", "id": str(result.inserted_id)}


@app.get("/api/routing/list")
async def list_routing_templates():
    cursor = routing_templates_collection.find().sort("created_at", -1)
    items = []
    async for doc in cursor:
        items.append(fix_id(doc))
    return {"items": items}


@app.delete("/api/routing/delete/{oid}")
async def delete_routing_template(oid: str):
    try:
        result = await routing_templates_collection.delete_one({"_id": ObjectId(oid)})
        if result.deleted_count == 1:
            return {"status": "success"}
        return {"status": "not_found"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/events/due_date_reschedule")
async def due_date_reschedule(req: DueDateRescheduleRequest):
    """批量修改工单交期后全局重排，并输出承诺变化对比。"""
    try:
        if not req.base_jobs:
            return {"error": "base_jobs is empty"}
        if not req.due_date_changes:
            return {"error": "due_date_changes is empty"}
        exec_doc = await _execution_doc_for_dispatch()
        envelope = {
            "event_type": "due_date_change",
            "base_jobs": [j.model_dump() for j in req.base_jobs],
            "params": {"due_date_changes": [c.model_dump() for c in req.due_date_changes]},
            "reschedule_options": {
                "solvers": req.solvers,
                "weights": req.weights,
                "random_seed": req.random_seed,
            },
            "production_execution": exec_doc if exec_doc.get("status") in ("running", "paused") else None,
        }
        if exec_doc.get("status") in ("running", "paused"):
            envelope["reschedule_options"]["baseline_gantt"] = exec_doc.get("baseline_gantt")
            envelope["reschedule_options"]["baseline_solver"] = exec_doc.get("baseline_solver")
        return await _event_dispatch_from_request(envelope)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}



@app.post("/api/staffing/analyze")
async def analyze_staffing(schedule_data: List[Dict[str, Any]]):
    """
    分析排程数据，计算每小时的人力需求
    假设：1 台运行中的机器 = 1 名具备数控技能的操作员
    """
    from metaforge.services.staff_dispatch import staff_can_operate

    if not schedule_data:
        return {"timeline": [], "stats": {}}

    # 1. 确定整体时间跨度
    max_end_time = max(task['end'] for task in schedule_data)
    time_horizon = int(max_end_time) + 2  # 多预留一点缓冲

    # 2. 初始化时间桶 (Time Buckets)
    # index 0 代表 T0-T1 时段, index 1 代表 T1-T2 时段...
    staffing_profile = [0] * time_horizon
    machine_details = [[] for _ in range(time_horizon)]  # 记录每个时刻具体是哪些机器在跑

    # 3. 遍历任务，填充时间桶
    for task in schedule_data:
        start_t = int(task['start'])
        end_t = int(task['end'])

        # 处理时间跨度，例如 2.5 -> 5.5，算作 T2, T3, T4, T5 都有负载
        # 这里向下取整作为索引，覆盖的时间段都+1
        # 注意：如果 task.end 是整数且等于 start_t，需要避免索引越界(虽不太可能)
        if end_t == start_t: end_t += 1

        for t in range(start_t, math.ceil(task['end'])):
            if t < time_horizon:
                staffing_profile[t] += 1
                machine_details[t].append(task['machine_id'])

    # 4. 计算统计指标
    max_staff = max(staffing_profile) if staffing_profile else 0
    avg_staff = sum(staffing_profile) / len(staffing_profile) if staffing_profile else 0
    total_man_hours = sum(staffing_profile)  # 积分面积

    # 5. 格式化输出供 ECharts 使用
    timeline_data = []
    for t in range(time_horizon):
        timeline_data.append({
            "time": t,
            "count": staffing_profile[t],
            "machines": sorted(list(set(machine_details[t])))  # 去重并排序
        })

    staff_docs = await staff_collection.find({"is_active": True}).to_list(100)
    skilled_active = sum(1 for s in staff_docs if staff_can_operate(s, 0))

    return {
        "timeline": timeline_data,
        "stats": {
            "max_peak": max_staff,
            "avg_load": round(avg_staff, 2),
            "total_hours": total_man_hours,
            "skilled_active": skilled_active,
            "peak_shortage": max(0, max_staff - skilled_active),
        }
    }


class StaffDispatchBody(BaseModel):
    schedule_data: List[Dict[str, Any]]
    sim_time: float = 0


@app.post("/api/staffing/dispatch")
async def staffing_dispatch(body: StaffDispatchBody):
    """按甘特时刻预览人员派工（机台值守 / 待命 / 巡检）及孪生坐标。"""
    from metaforge.services.staff_dispatch import build_staff_dispatch_preview

    staff = await staff_collection.find().sort("id", 1).to_list(100)
    machines = await machine_collection.find().sort("id", 1).to_list(200)
    return build_staff_dispatch_preview(
        body.schedule_data or [],
        staff,
        machines,
        float(body.sim_time or 0),
    )


# === 员工管理 API ===

@app.get("/api/staff/list")
async def get_staff_list():
    """获取所有员工列表"""
    staff = await staff_collection.find().sort("id", 1).to_list(100)
    for s in staff:
        s["_id"] = str(s["_id"])
    return staff

class StaffStatusUpdate(BaseModel):
    is_active: bool

@app.post("/api/staff/toggle/{uid}")
async def toggle_staff_status(uid: int, update: StaffStatusUpdate):
    """切换员工状态 (在岗/请假)"""
    await staff_collection.update_one(
        {"id": uid},
        {"$set": {"is_active": update.is_active}}
    )
    return {"status": "success"}


@app.post("/api/logistics/generate")
async def generate_logistics_tasks(schedule_data: List[Dict[str, Any]]):
    current_fleet_db = await agv_fleet_collection.find().to_list(length=100)
    machine_docs = await machine_collection.find().to_list(200)
    machine_pos = {
        int(m["id"]): (float(m.get("x", 0.0)), float(m.get("z", 0.0)))
        for m in machine_docs
        if m.get("id") is not None
    }
    cfg = DispatchConfig(w_balance=0.5, w_empty=0.4, w_order=0.1, travel_time_cost=0.5)
    dispatched_tasks, fleet_state = dispatch_agv_global(
        schedule_data=schedule_data or [],
        fleet_docs=current_fleet_db,
        machine_pos=machine_pos,
        cfg=cfg,
    )
    persisted = await persist_dispatch_result(
        agv_tasks_collection=agv_tasks_collection,
        agv_fleet_collection=agv_fleet_collection,
        dispatched_tasks=dispatched_tasks,
        fleet_state=fleet_state,
    )
    return {
        "tasks": dispatched_tasks,
        "fleet_status": persisted["fleet_status"],
        "batch_id": persisted["batch_id"],
    }


class LogisticsDispatchRequest(BaseModel):
    task_id: str


@app.post("/api/logistics/dispatch")
async def dispatch_logistics_task(body: LogisticsDispatchRequest):
    task_id = (body.task_id or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")

    task = await agv_tasks_collection.find_one({"task_id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task.get("dispatched"):
        return {"status": "ok", "already_dispatched": True}

    agv_id = int(task.get("assigned_agv", 0) or 0)
    now = datetime.now()
    await agv_tasks_collection.update_one(
        {"_id": task["_id"]},
        {
            "$set": {
                "dispatched": True,
                "dispatch_status": "dispatched",
                "dispatched_at": now,
            }
        },
    )
    if agv_id > 0:
        await agv_fleet_collection.update_one(
            {"agv_id": agv_id},
            {
                "$set": {
                    "status": "busy",
                    "location": int(task.get("to_machine", -1)),
                    "last_updated": now,
                }
            },
            upsert=True,
        )
    return {"status": "ok", "task_id": task_id, "assigned_agv": agv_id}


@app.post("/api/logistics/complete")
async def complete_logistics_task(body: LogisticsDispatchRequest):
    task_id = (body.task_id or "").strip()
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")

    task = await agv_tasks_collection.find_one({"task_id": task_id})
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    agv_id = int(task.get("assigned_agv", 0) or 0)
    now = datetime.now()
    await agv_tasks_collection.update_one(
        {"_id": task["_id"]},
        {
            "$set": {
                "dispatch_status": "done",
                "completed_at": now,
            }
        },
    )
    if agv_id > 0:
        await agv_fleet_collection.update_one(
            {"agv_id": agv_id},
            {
                "$set": {
                    "status": "idle",
                    "last_updated": now,
                }
            },
            upsert=True,
        )
    return {"status": "ok", "task_id": task_id, "assigned_agv": agv_id}


@app.get("/api/logistics/batches")
async def list_logistics_batches(limit: int = 20):
    lim = max(1, min(int(limit or 20), 100))
    pipeline = [
        {
            "$group": {
                "_id": "$batch_id",
                "created_at": {"$max": "$created_at"},
                "task_count": {"$sum": 1},
            }
        },
        {"$sort": {"created_at": -1}},
        {"$limit": lim},
    ]
    rows = await agv_tasks_collection.aggregate(pipeline).to_list(length=lim)
    return {
        "batches": [
            {
                "batch_id": str(r.get("_id") or ""),
                "created_at": r.get("created_at"),
                "task_count": int(r.get("task_count") or 0),
            }
            for r in rows
            if r.get("_id")
        ]
    }


@app.get("/api/logistics/tasks")
async def list_logistics_tasks(
    batch_id: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    lim = max(1, min(int(limit or 200), 1000))
    off = max(0, int(offset or 0))
    q: Dict[str, Any] = {}
    if (batch_id or "").strip():
        q["batch_id"] = batch_id.strip()
    total = await agv_tasks_collection.count_documents(q)
    docs = (
        await agv_tasks_collection.find(q)
        .sort([("pickup_time", 1), ("dispatch_rank", 1)])
        .skip(off)
        .limit(lim)
        .to_list(length=lim)
    )
    tasks = []
    for d in docs:
        tasks.append(
            {
                "id": d.get("task_id"),
                "task_id": d.get("task_id"),
                "batch_id": d.get("batch_id"),
                "job_name": d.get("job_name"),
                "from_machine": d.get("from_machine"),
                "to_machine": d.get("to_machine"),
                "assigned_agv": d.get("assigned_agv"),
                "pickup_time": d.get("pickup_time"),
                "delivery_deadline": d.get("delivery_deadline"),
                "dispatch_rank": d.get("dispatch_rank"),
                "route": d.get("route") or [],
                "score": d.get("score"),
                "score_breakdown": d.get("score_breakdown") or {},
                "is_seamless": bool(d.get("is_seamless")),
                "dispatched": bool(d.get("dispatched")),
                "dispatch_status": str(d.get("dispatch_status") or "pending"),
            }
        )
    agv_docs = await agv_fleet_collection.find().sort("agv_id", 1).to_list(length=200)
    fleet_status = [
        {
            "id": int(x.get("agv_id")),
            "location": x.get("location", -1),
            "status": x.get("status", "idle"),
            "free_at": 0,
        }
        for x in agv_docs
        if x.get("agv_id") is not None
    ]
    return {
        "tasks": tasks,
        "fleet_status": fleet_status,
        "pagination": {
            "total": int(total),
            "limit": lim,
            "offset": off,
        },
    }


@app.get("/api/logistics/layout")
async def get_logistics_layout():
    """车间机台平面坐标，供 AGV 路径图使用。"""
    docs = await machine_collection.find().sort("id", 1).to_list(length=200)
    return {
        "machines": [
            {
                "id": int(m["id"]),
                "name": m.get("name", f"Machine-{m['id']}"),
                "x": float(m.get("x", 0.0)),
                "y": float(m.get("y", 7.5)),
                "z": float(m.get("z", 0.0)),
            }
            for m in docs
            if m.get("id") is not None
        ]
    }


@app.get("/api/logistics/kpi")
async def get_logistics_kpi(batch_id: Optional[str] = None):
    """按批次汇总 AGV KPI（准时率 / 无缝衔接率 / 平均空驶成本）。"""
    q: Dict[str, Any] = {}
    bid = (batch_id or "").strip()
    if bid:
        q["batch_id"] = bid
    else:
        latest = await agv_tasks_collection.find_one(sort=[("created_at", -1)])
        if latest and latest.get("batch_id"):
            q["batch_id"] = latest["batch_id"]
    docs = await agv_tasks_collection.find(q).to_list(length=10000)
    total = len(docs)
    scored = [d for d in docs if d.get("score") is not None]
    on_time = 0
    empty_sum = 0.0
    empty_n = 0
    for d in scored:
        bd = d.get("score_breakdown") or {}
        if float(bd.get("order_penalty") or 0.0) <= 0:
            on_time += 1
        ec = bd.get("empty_cost")
        if ec is not None:
            empty_sum += float(ec)
            empty_n += 1
    seamless = sum(1 for d in docs if d.get("is_seamless"))
    status = {"pending": 0, "dispatched": 0, "done": 0}
    for d in docs:
        st = str(d.get("dispatch_status") or "pending")
        if st not in status:
            st = "pending"
        status[st] += 1
    return {
        "batch_id": q.get("batch_id"),
        "total": total,
        "scored_count": len(scored),
        "on_time_rate": (on_time / len(scored)) if scored else None,
        "seamless_rate": (seamless / total) if total else None,
        "avg_empty_cost": (empty_sum / empty_n) if empty_n else None,
        "status": status,
    }


# === 物料 JIT 预测 API ===

@app.get("/api/materials/list")
async def get_materials():
    return await _fetch_materials_catalog()


@app.post("/api/materials/check_jobs")
async def check_jobs_material(req: MaterialCheckRequest):
    """排程前 BOM 静态预检（总需求 vs 当前库存）。"""
    db_materials = await _fetch_materials_catalog()
    inventory = {m["id"]: float(m.get("current_stock", 0)) for m in db_materials}
    names = {m["id"]: m.get("name", m["id"]) for m in db_materials}
    safe = {m["id"]: float(m.get("safe_level", 0)) for m in db_materials}
    report = check_jobs_material_static(
        req.jobs, inventory, material_names=names, safe_levels=safe
    )
    return {"status": "success", "report": report}


@app.post("/api/materials/predict")
async def predict_materials(body: MaterialPredictRequest):
    """根据排程甘特 + 工单 BOM 仿真库存时间线。"""
    db_materials = await _fetch_materials_catalog()
    schedule_data = body.schedule_data

    if body.jobs:
        jobs = body.jobs
    else:
        # 无 BOM 时回退：按 job_id 模分配默认物料（兼容旧演示）
        max_jid = max((int(t.get("job_id", 0)) for t in schedule_data), default=0)
        jobs = []
        for jid in range(max_jid + 1):
            if jid % 3 == 0:
                bom = [BomLine(material_id="MAT_STEEL", quantity_per_unit=10.0, consume_mode="per_hour")]
            elif jid % 3 == 1:
                bom = [BomLine(material_id="MAT_ALUM", quantity_per_unit=8.0, consume_mode="per_hour")]
            else:
                bom = [BomLine(material_id="MAT_PLASTIC", quantity_per_unit=5.0, consume_mode="per_hour")]
            jobs.append(
                JobData(
                    name=f"Job-{jid}",
                    priority=10,
                    tasks=[TaskData(machine_id=0, duration=1)],
                    bom=bom,
                )
            )

    report = build_material_report_for_schedule(schedule_data, jobs, db_materials)
    sim = report.get("simulation") or {}
    return {
        "timeline": sim.get("timeline", []),
        "shortages": sim.get("shortages", []),
        "safe_warnings": sim.get("safe_warnings", []),
        "feasible": report.get("feasible", True),
        "has_safe_warning": report.get("has_safe_warning", False),
        "report": report,
    }


class RestockRequest(BaseModel):
    amount: float

@app.post("/api/materials/restock/{mid}")
async def restock_material(mid: str, req: RestockRequest):
    """
    自定义补货接口
    接收前端传来的 amount，增加到当前库存中
    """
    # 使用 $inc (increment) 原子操作增加库存
    await material_collection.update_one(
        {"id": mid},
        {"$inc": {"current_stock": req.amount}}
    )
    return {"status": "success", "added": req.amount}


# === 数字孪生可视化 API ===
@app.get("/api/digital_twin/snapshot")
async def get_digital_twin_snapshot(
    plan_id: Optional[str] = None,
    solver_id: Optional[str] = None,
    sim_time: Optional[float] = None,
):
    from bson import ObjectId

    from metaforge.services.digital_twin import (
        build_agv_snapshot,
        build_machines_snapshot,
        build_staff_snapshot,
    )
    from metaforge.services.production_execution import (
        extract_solver_result,
        gantt_makespan,
        get_state,
    )
    from metaforge.services.schedule_summary import resolve_plan_schedule_map

    db_machines = await machine_collection.find().to_list(100)
    if not db_machines:
        return {"machines": [], "agvs": [], "staff": [], "meta": {"status": "empty"}}

    meta_info: Dict[str, Any] = {
        "status": "simulation",
        "plan_name": "随机演示 (未选计划)",
        "current_time": 0,
        "total_time": 0,
        "time_unit": "h",
    }
    machines_snapshot: List[Dict[str, Any]] = []
    gantt: List[Dict[str, Any]] = []
    makespan = 0.0
    current_sim_time = 0.0

    execution = await get_state(execution_collection)

    # === 模式 1：MES 当前执行计划（最高优先级）===
    if execution.get("status") in ("running", "paused"):
        gantt = list(execution.get("baseline_gantt") or [])
        makespan = float(execution.get("makespan") or gantt_makespan(gantt))
        current_sim_time = float(execution.get("sim_time") or 0)
        meta_info.update(
            {
                "status": "execution",
                "plan_name": execution.get("plan_name", "当前执行"),
                "plan_id": execution.get("plan_id"),
                "current_time": round(current_sim_time, 2),
                "total_time": round(makespan, 2),
                "sim_speed": execution.get("sim_speed", 60),
                "execution_status": execution.get("status"),
                "baseline_solver": execution.get("baseline_solver"),
            }
        )
        machines_snapshot = build_machines_snapshot(db_machines, gantt, current_sim_time)

    # === 模式 2：看板所选计划预览（未执行时）===
    elif (plan_id or "").strip() and (solver_id or "").strip():
        try:
            oid = ObjectId(plan_id.strip())
        except Exception:
            raise HTTPException(status_code=400, detail="invalid plan_id")
        order = await orders_collection.find_one({"_id": oid})
        if not order:
            raise HTTPException(status_code=404, detail="plan not found")
        try:
            entry = extract_solver_result(resolve_plan_schedule_map(order), solver_id.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        gantt = list(entry.get("gantt_data") or [])
        makespan = float(entry.get("best_score") or gantt_makespan(gantt))
        current_sim_time = max(0.0, float(sim_time if sim_time is not None else 0))
        if makespan > 0:
            current_sim_time = min(current_sim_time, makespan)
        meta_info.update(
            {
                "status": "preview",
                "plan_name": order.get("plan_name", "未命名计划"),
                "plan_id": str(order.get("_id", "")),
                "baseline_solver": solver_id.strip(),
                "current_time": round(current_sim_time, 2),
                "total_time": round(makespan, 2),
            }
        )
        machines_snapshot = build_machines_snapshot(db_machines, gantt, current_sim_time)

    # === 模式 3：最近排程计划自动回放（兼容旧行为）===
    else:
        latest_order = await orders_collection.find_one(
            {"schedule_result": {"$ne": None}},
            sort=[("created_at", -1)],
        )
        if latest_order:
            sr = latest_order.get("schedule_result") or {}
            gantt = list(sr.get("gantt_data") or [])
            makespan = float(sr.get("makespan") or sr.get("best_score") or gantt_makespan(gantt) or 100)
            loop_duration = makespan + 10
            current_sim_time = min((time.time() * 5) % loop_duration, makespan)
            meta_info.update(
                {
                    "status": "playback",
                    "plan_name": latest_order.get("plan_name", "未命名计划"),
                    "plan_id": str(latest_order.get("_id", "")),
                    "current_time": round(current_sim_time, 1),
                    "total_time": round(makespan, 1),
                }
            )
            machines_snapshot = build_machines_snapshot(db_machines, gantt, current_sim_time)
        else:
            current_ts = int(time.time())
            for m in db_machines:
                is_running = ((current_ts // 5) + int(m["id"])) % 3 != 0
                machines_snapshot.append(
                    {
                        "id": m["id"],
                        "x": m["x"],
                        "y": float(m.get("y", 7.5)),
                        "z": m["z"],
                        "status": "running" if is_running else "idle",
                        "current_job": "",
                    }
                )

    agv_data = await build_agv_snapshot(agv_fleet_collection, db_machines)
    staff_data = await build_staff_snapshot(
        staff_collection,
        db_machines,
        gantt=gantt if gantt else None,
        sim_time=current_sim_time,
    )

    return {
        "machines": machines_snapshot,
        "agvs": agv_data,
        "staff": staff_data,
        "meta": meta_info,
    }
if __name__ == "__main__":
    import socket
    from pathlib import Path

    _root = Path(__file__).resolve().parent.parent
    _reload_dirs = [str(_root / "tests"), str(_root / "src")]
    _host = os.getenv("METAFORGE_HOST", "127.0.0.1")
    _port = int(os.getenv("METAFORGE_PORT", "8008"))
    _reload = os.getenv("METAFORGE_RELOAD", "0") == "1"

    def _port_in_use(port: int) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((_host, port))
            return False
        except OSError:
            return True
        finally:
            s.close()

    if _port_in_use(_port):
        print(
            f"[ERROR] 端口 {_port} 已被占用。"
            "请先运行: .\\scripts\\cleanup_backend.ps1"
            f"  然后访问 http://{_host}:{_port}/new-ui/"
        )
        raise SystemExit(1)

    print(f"MetaForge Backend (FastAPI+Motor) running on http://{_host}:{_port}")
    print(f"  统一入口: http://{_host}:{_port}/new-ui/")
    print(f"  reload={_reload}  METAFORGE_RELOAD=1 可开启热重载（开发慎用，易堆积僵尸进程）")
    uvicorn.run(
        "main:app",
        host=_host,
        port=_port,
        reload=_reload,
        reload_dirs=_reload_dirs if _reload else None,
    )