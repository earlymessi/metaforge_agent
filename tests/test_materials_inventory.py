"""物料主数据自愈与 predict 兜底。"""

import pytest

from metaforge.tools.material.predict import _catalog_from_jobs_bom


def test_catalog_from_jobs_bom():
    jobs = [
        {
            "name": "J1",
            "bom": [{"material_id": "MAT_STEEL", "quantity_per_unit": 2}],
        }
    ]
    cat = _catalog_from_jobs_bom(jobs)
    assert len(cat) == 1
    assert cat[0]["id"] == "MAT_STEEL"


def test_ensure_default_materials_on_empty_collection():
    import asyncio
    from metaforge.services.materials_inventory import (
        DEFAULT_MATERIALS,
        ensure_default_materials,
        fetch_materials_catalog,
    )

    class _FakeColl:
        def __init__(self):
            self.docs = []

        async def count_documents(self, _filter=None):
            return len(self.docs)

        async def insert_many(self, items):
            self.docs.extend(items)

        async def find(self):
            class _Cur:
                def __init__(self, docs):
                    self._docs = docs

                async def to_list(self, _n):
                    return list(self._docs)

            return _Cur(self.docs)

    coll = _FakeColl()

    async def _run():
        n = await ensure_default_materials(coll)
        assert n == len(DEFAULT_MATERIALS)
        listed = await fetch_materials_catalog(coll, ensure=True)
        assert len(listed) == len(DEFAULT_MATERIALS)

    asyncio.run(_run())
