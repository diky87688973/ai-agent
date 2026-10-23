# 静默异常治理

## 1. 目标

异常处理的目标不是“让门禁变绿”，而是让每一处失败都有明确归属：

- 调用方知道失败后拿到什么状态；
- 运行面能看到失败；
- 恢复范围被限制在局部；
- 测试能覆盖失败路径。

最终状态：

```text
except Exception / BaseException + pass/continue   0 处
无说明的静默 except                              0 处
IDIOMS 正则豁免表                               0 张
静默异常预算                                    0
```

## 2. 允许的异常处理

### 2.1 窄捕获 + 明确恢复

```python
try:
    text = path.read_text(encoding="utf-8")
except (OSError, UnicodeDecodeError) as exc:
    report_error("config.read", exc, path=str(path))
    return None
```

要求：

- 捕获类型尽量窄；
- 返回值必须是调用方能理解的明确状态；
- 不把失败伪装成“空数据”而不留痕。

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

### 2.4 插件/请求边界隔离

```python
except Exception as exc:
    report_error("plugin.load", exc, plugin=name)
    return PluginUnavailable(name)
```

宽捕获只允许出现在隔离边界，并且必须满足其一：

- 上报后返回明确状态；
- 转换成明确结果对象（如 `ToolResult(ok=False, error=...)`）；
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

最后一种只在“宽捕获 + 无上报”时禁止；窄捕获的明确缺省返回是允许的。

注释不能作为豁免。  
标签、正则、预算不能作为豁免。

## 4. 分层策略

| 层 | 策略 |
|---|---|
| `agent/core` | 不变量破坏快速失败；可选能力用窄捕获 + 明确状态 |
| `agent/mechanisms` | 权威状态写入不得静默；日志、指标等旁路可降级但必须上报 |
| `agent/capabilities` | 工具失败转成明确工具错误；批量处理逐项上报 |
| `agent/shell` | 请求边界转成用户可见错误；断连、队列空按控制流显式处理 |
| `plugins` | 插件失败隔离，上报后禁用或跳过，不污染主流程 |
| `scripts` / `tests` | 只允许窄捕获 + stderr 留痕或 `suppress(SpecificError)` |

## 5. 门禁

`scripts/check_silent_except.py` 只做 AST 结构检查，不再读取正则表或预算：

1. `except` 体只有 `pass`/`continue`：失败。
2. 裸 `except`：失败。
3. `except Exception`/`BaseException` + 无上报：失败。
4. 宽捕获 + `return`/赋值常量且无上报：失败。
5. 窄捕获 + 明确返回：允许。
6. `contextlib.suppress(SpecificError)`：允许。
7. `write_stderr` 兜底：允许。

门禁失败信息必须给出文件、行号、外层函数和违规原因。

门禁自身必须有合成代码测试：

```text
except Exception: pass                 → 失败
except OSError: pass                   → 失败
except Exception: report_error(...)    → 允许
except OSError: return None            → 允许
suppress(Exception)                    → 失败
suppress(OSError)                      → 允许
```

## 6. 迁移顺序

按失败影响排序，不按文件字母序：

1. 核心数据与状态：`session_store`、`run_registry`、`file_safety`、`fspaths`、`session_title`。
2. 持久化与队列：模型注册表、metadata、日志轮转、会话队列。
3. 外部输入解析：JSON、配置、编码、路径。
4. 旁路：进度、指标、可选能力、清理。
5. 测试与验收脚本。
6. `IDIOMS` 与 `SILENT_EXCEPT_IDIOM_BUDGET` 已删除。

每一批完成后：

- 跑受影响模块的单测；
- 跑 `check_silent_except.py`；
- 检查失败路径是否有测试；
- 更新本文件或质量门禁文档。

## 7. 验收

```text
python scripts/check_silent_except.py
python -m unittest tests.test_silent_except_gate
python -m unittest tests.test_gate_negative
```

必须满足：

- 静默 `pass/continue` 为 0；
- `IDIOMS` 不存在；
- 预算常量不存在；
- 门禁负例全部按预期失败；
- 关键持久化路径有故障注入测试；
- 全量 CI 通过（用户要求时执行）。

## 8. 回滚

按文件批次回滚，不整体回退：

- 每批改动前备份原文件；
- 每批只改异常处理和对应测试；
- 若出现行为回归，先恢复该批原文件，再缩小改动范围；
- 不回退已通过的其他批次。

## 9. 当前验收结果

```text
检查文件：334
检查 except：557
静默 pass/continue：0
IDIOMS：已删除
静默异常预算：已删除
单元测试：1786 通过，2 跳过
ruff：通过
架构约束：通过
复杂度：通过
配置一致性：通过
注释文案：通过
README / 单测文档：通过
```

宽捕获的两种允许出口：

```text
report_error(...) / write_stderr(...)
→ 有上报

显式构造错误结果 / 重新抛出
→ 有明确状态
```

不再允许注释、正则标签、预算余量作为豁免。
