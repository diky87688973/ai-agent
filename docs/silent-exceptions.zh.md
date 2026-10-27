[English](silent-exceptions.md) | **中文**

# 静默异常治理

## 1. 目标

异常处理让每一处失败都有明确归属，而不是让门禁变绿：

- 调用方知道失败后拿到什么状态；
- 运行面能看到失败；
- 恢复范围限制在局部；
- 测试覆盖失败路径。

目标状态：

```text
except Exception / BaseException + pass/continue：0
无上报的静默 except：0
IDIOMS 正则豁免表：0
静默异常预算：0
```

## 2. 允许的异常处理

### 2.1 窄捕获与明确恢复

```python
try:
    text = path.read_text(encoding="utf-8")
except (OSError, UnicodeDecodeError) as exc:
    report_error("config.read", exc, path=str(path))
    return None
```

要求：

- 捕获类型尽量窄，覆盖该失败即可；
- 返回值是调用方能理解的明确状态；
- 失败不得伪装成空数据而不留痕。

### 2.2 批量逐项处理

```python
except (OSError, ValueError) as exc:
    report_error("batch.item", exc, item=str(item))
    continue
```

允许 `continue`，但必须先上报；单独一个 `continue` 不允许。

### 2.3 清理与关闭

```python
with contextlib.suppress(OSError):
    handle.close()
```

只允许具体异常类型；`suppress(Exception)` 禁止。

### 2.4 插件与请求边界隔离

```python
except Exception as exc:
    report_error("plugin.load", exc, plugin=name)
    return PluginUnavailable(name)
```

宽捕获只允许出现在隔离边界，并且必须满足其一：

- 上报后返回明确状态；
- 转换成明确结果对象，例如对 `ToolResult(ok=False, error=...)` 的赋值；
- 包装后重新抛出。

### 2.5 最后兜底

日志系统自身失败时，允许一个集中、窄范围的兜底函数：

```python
def write_stderr(message: str) -> None:
    try:
        os.write(2, message.encode("utf-8", "replace"))
    except OSError:
        return
```

业务代码不得复制这个兜底。

## 3. 禁止的写法

```python
except Exception:
    pass

except Exception:
    continue

except BaseException:
    pass

except Exception:
    return None
```

最后一种只在宽捕获且无上报时禁止；窄捕获的明确缺省返回允许。

注释不构成豁免；标签、正则、预算也不构成豁免。

## 4. 分层策略

| 层 | 策略 |
|---|---|
| `agent/core` | 不变量破坏时快速失败；可选能力用窄捕获 + 明确状态 |
| `agent/mechanisms` | 权威状态写入不得静默；日志、指标等旁路可降级但必须上报 |
| `agent/capabilities` | 工具失败转成明确工具错误；批量处理逐项上报 |
| `agent/shell` | 请求边界转成用户可见错误；断连、空队列按控制流显式处理 |
| `plugins` | 插件失败隔离，上报后禁用或跳过，不影响主流程 |
| `scripts` / `tests` | 只允许窄捕获 + stderr 留痕，或 `suppress(SpecificError)` |

## 5. 门禁

`scripts/check_silent_except.py` 只做 AST 结构检查，不读取正则表或预算。它扫描 `agent/`、`tests/`、`scripts/`、`plugins/` 下的 `.py` 文件，跳过路径中含 `__pycache__` 或 `retired` 的文件。

1. `except` 体含 `pass`，或只有 `continue`：失败。
2. 裸 `except`：失败。
3. 宽捕获（`Exception`、`BaseException`，或包含其一的元组）既无上报也无转换：失败；只有一条 `return` 或赋值常量缺省值（如 `None`、空容器）的处理器同样失败。
4. 窄捕获 + 明确返回：允许。
5. `contextlib.suppress(SpecificError)`：允许；`suppress(Exception)`、`suppress(BaseException)`：失败。
6. `write_stderr` 兜底：允许。

上报形式是带至少两个位置参数的 `report_error(...)`、带至少一个位置参数的 `write_stderr(...)`，或 `print(..., file=sys.stderr)`。转换形式是 `raise`，或对 `ToolResult(...)` 调用的赋值；直接 `return ToolResult(...)` 不算转换。

脚本打印扫描文件数与检查的 except 数，再打印成功标记并以 0 退出。每处问题按 `[FAIL] 路径:行号 原因` 打印，脚本以 1 退出；无法解析的文件按其行号报语法错误。每条失败信息给出文件、行号与违规原因。

## 6. 整改顺序

按失败影响排序，不按文件字母序：

1. 核心数据与状态：`session_store`、`run_registry`、`file_safety`、`fspaths`、`session_title`。
2. 持久化与队列：模型注册表、metadata、日志轮转、会话队列。
3. 外部输入解析：JSON、配置、编码、路径。
4. 旁路：进度、指标、可选能力、清理。
5. 测试与验收脚本。

每一批完成后：

- 跑受影响模块的单测；
- 跑 `check_silent_except.py`；
- 检查失败路径是否有测试；
- 更新本文档或质量门禁文档。

## 7. 验收

```text
python scripts/check_silent_except.py
python -m unittest tests.test_silent_except_gate
python -m unittest tests.test_gate_negative
```

必须满足：

- 静默 `pass`/`continue` 为 0；
- `IDIOMS` 表不存在；
- 预算常量不存在；
- 门禁负例全部按预期失败；
- 关键持久化路径有故障注入测试；
- 全量 CI 通过（按需执行）。

## 8. 回滚

按文件批次回滚，不整体回退：

- 每批改动前备份原文件；
- 每批只改异常处理和对应测试；
- 出现行为回归时，先恢复该批原文件，再缩小改动范围；
- 不回退已通过的其他批次。

## 9. 验收结果

```text
扫描文件：400
检查 except：698
静默 pass/continue：0
IDIOMS 表：不存在
静默异常预算：不存在
```

`tests.test_silent_except_gate` 与 `tests.test_gate_negative` 通过；静默异常负例按预期让门禁失败。

宽捕获的两种允许出口：

```text
report_error(...) / write_stderr(...)
→ 有上报

重新抛出，或对明确结果对象的赋值
→ 有明确状态
```
