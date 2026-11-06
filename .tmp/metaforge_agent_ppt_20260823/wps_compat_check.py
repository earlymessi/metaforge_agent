import json
import os

from cli_anything.wps.utils.wps_backend import (
    close_document,
    find_wps,
    get_version,
    open_document,
    quit_app,
)

SOURCE = r"D:\Desktop\metaforge\deliverables\MetaForge_Agent_Interview_Academic_Light.pptx"
CHECK_COPY = r"D:\Desktop\metaforge\.tmp\metaforge_agent_ppt_20260823\MetaForge_Agent_Interview_Academic_Light_WPS_Check_OOXML.pptx"

app = None
doc = None
try:
    app = find_wps("impress")
    try:
        app.Visible = False
        app.DisplayAlerts = False
    except Exception:
        pass

    doc = open_document(app, SOURCE)
    slide_count = int(doc.Slides.Count)
    shape_counts = [int(doc.Slides.Item(i).Shapes.Count) for i in range(1, slide_count + 1)]
    # WPS Impress exposes SaveAs; 24 is Open XML Presentation (.pptx).
    doc.SaveAs(CHECK_COPY, 24)

    print(json.dumps({
        "wps_version": get_version(app),
        "slides": slide_count,
        "shape_counts": shape_counts,
        "saved_copy": CHECK_COPY,
        "saved_copy_exists": os.path.exists(CHECK_COPY),
        "saved_copy_bytes": os.path.getsize(CHECK_COPY) if os.path.exists(CHECK_COPY) else 0,
    }, ensure_ascii=False))
finally:
    if doc is not None:
        close_document(doc, save=False)
    if app is not None:
        quit_app(app, force=True)
