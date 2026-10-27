**English** | [中文](plugin-subprocess-isolation.zh.md)

# Evaluation: plugin subprocess isolation (not implemented)

Status: not implemented (evaluation memo)
Related: [Plugin trust model](../subsystems/plugins.md#插件信任模型)

## Motivation

In-process loading places plugins at the same trust level as local code. If untrusted plugins are to be part of the product, a process boundary is required: crash isolation, narrower permissions, and resource quotas.

## Cost (under the current architecture)

- **Tool API**: `PluginContext` directly references the `ToolRegistry`, the tool pipeline, and the event bus; crossing a process boundary requires RPC and serialization contracts.
- **Performance**: each tool call incurs one extra process round trip; cold start and handle inheritance cost more on Windows.
- **Windows**: process and user isolation primitives differ from Linux, doubling the test matrix.
- **UI assets**: panel scripts still load into the browser's same-origin context; process isolation does not cover the frontend.

## Conclusion

A subprocess sandbox is not implemented. Priority goes to the trust-model documentation, load-time source and integrity logging, and an optional switch that restricts loading to paths inside the `plugins/` tree. Subprocess isolation requires a separate RFC defining the tool-call protocol and the Windows support scope.
