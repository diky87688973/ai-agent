"""声明式可视化工具；结果由既有工具事实流持久化。"""
from __future__ import annotations

from agent.capabilities.registry import ToolPlugin
from agent.core.context import SERVICE_BACKGROUND_TASKS, SERVICE_STORE
from agent.core.event_name import TOOL_DONE
from agent.core.session_scope import current_context

from .validation import KINDS, validate_document


class VisualizeTool(ToolPlugin):
    name = "visualize"
    label = "可视化"
    icon = "📊"
    parallel_safe = False
    description = (
        "在对话中创建或替换可交互面板。panel_id 在所属会话内唯一，revision 从1开始逐次加1；"
        "面板默认只展示内容，视图编辑由用户开启。label只写名称，不重复数值或百分比。"
        "成功后只需简短自然语言结论，不重复参数、panel_id、revision或源码；控件选项标签应面向用户。"
        "同一 panel_id/revision 重试必须提供相同内容，否则拒绝。operation=upsert 创建/替换，"
        "失败调用不产生修订：修正失败参数时仍使用原revision，只有成功后才递增。"
        "operation=remove 移除（data={}，其余字段仍须提供）。summary 是无头入口可读的文字摘要。"
        "kind: proportion/tasks/mermaid/flow/progress/bar/line/donut/timeline/gantt/waterfall/controls/table。"
        "data 形状：flow={nodes:[{id,label}],edges:[{source,target}]}；"
        "比例图会自动标原值和百分比，例如label=研发,value=50；不要把label写成研发50(50%)来重复标注。"
        "flow边只允许source和target，不能增加label等字段；条件文字可放节点标签或改用Mermaid。"
        "progress={items:[{label,value,total}]}；proportion/bar={items:[{label,value}]}；"
        "line={labels:[文本],series:[{label,values:[数值]}]}；"
        "table={columns:[{key,label}],rows:[{列key:标量}]}。"
        "tasks={batch:已有后台批次,task_ids:[已有任务ID]}实时读取任务服务，不估造百分比；"
        "mermaid={code:flowchart或sequenceDiagram定义}，不允许HTML/链接/配置指令，"
        "也不允许style/classDef/linkStyle/click，使用默认主题即可；"
        "timeline={unit,events:[{label,at,detail}]}；gantt={unit,tasks:[{label,start,end,status}]}；"
        "waterfall={unit,items:[{label,start,end,status}]}，status=waiting/running/succeeded/failed/cancelled；"
        "controls={fields:[{id,label,type,value,...}]}，type=select/tabs需要options:[{value,label}]，"
        "type=toggle使用布尔value，type=range需要min/max/step与数值value。"
        "提供完整数据，不提供 HTML、代码、链接或样式。每次调用记录修订事实，不改写历史。"
        "流程最多60节点/120边，项目最多100项，折线最多200点/8线，表格最多500行/20列。"
        "用户可以筛选、排序、缩放、选择和导出；选择经用户正常发送后才进入模型输入。"
    )
    parameters = {
        "panel_id": {"type": "string", "description": "会话内稳定面板ID，1–64位字母数字下划线或短横线"},
        "revision": {"type": "integer", "minimum": 1, "description": "从1开始的连续修订号"},
        "operation": {"type": "string", "enum": ["upsert", "remove"]},
        "kind": {"type": "string", "enum": list(KINDS), "description": "组件类型"},
        "title": {"type": "string", "maxLength": 120, "description": "明确的可视化标题"},
        "summary": {"type": "string", "maxLength": 2000, "description": "不依赖图形也能理解的文字摘要"},
        "data": {"type": "object", "description": "与 kind 对应的数据，形状及边界见工具说明"},
    }

    def execute(self, arguments: dict) -> dict:
        document = validate_document(arguments)
        turn = current_context()
        store = turn.service(SERVICE_STORE) if turn is not None else None
        if store is None or not turn.conversation_id:
            raise ValueError("可视化面板必须通过会话工具管道创建")
        display = {"version": 1, "id": document["panel_id"], "revision": document["revision"],
                   "operation": document["operation"], "type": "visualization." + document["kind"],
                   "title": document["title"], "summary": document["summary"], "data": document["data"]}
        previous = None
        for event in store.load(turn.conversation_id):
            if event.type != TOOL_DONE or event.data.get("name") != self.name:
                continue
            result = event.data.get("data")
            candidate = result.get("display") if isinstance(result, dict) else None
            if isinstance(candidate, dict) and candidate.get("id") == display["id"]:
                if previous is None or candidate["revision"] > previous["revision"]:
                    previous = candidate
        if previous is not None and display == previous:
            return {"display": display}
        expected = previous["revision"] + 1 if previous else 1
        if display["revision"] != expected:
            raise ValueError(f"面板 {display['id']} 的下一修订必须为 {expected}；同一修订不允许修改内容")
        if display["operation"] == "remove" and (previous is None or previous["operation"] == "remove"):
            raise ValueError("不能移除不存在或已移除的面板")
        if document["kind"] == "tasks" and document["operation"] == "upsert":
            manager = turn.service(SERVICE_BACKGROUND_TASKS)
            if manager is None:
                raise ValueError("后台任务服务不可用")
            rows = manager.list_tasks(turn.conversation_id, document["data"]["batch"])["tasks"]
            if not set(document["data"]["task_ids"]).issubset({row["task_id"] for row in rows}):
                raise ValueError("任务必须属于当前会话的已有批次")
        return {"display": display}


def make_tool(ctx) -> VisualizeTool:
    return VisualizeTool()
