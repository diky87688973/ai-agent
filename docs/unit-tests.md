# 单元测试用例清单

共 **1247** 个用例（`python -m unittest discover -s tests -p "test_*.py"`）。

按测试文件分组；「测试目标」优先取方法 docstring，无则结合类 docstring 与方法名，再否则仅由方法名转写。

本文件由 `python scripts/gen_unit_tests_md.py` 生成；`--check` 在 CI 里校验是否漂移，**不要手改**。

## 目录

1. [test_app_context.py](#test_app_contextpy)（11）
2. [test_app_context_wiring.py](#test_app_context_wiringpy)（15）
3. [test_architecture_hygiene.py](#test_architecture_hygienepy)（11）
4. [test_attachments_autonomy.py](#test_attachments_autonomypy)（19）
5. [test_batch_f_tools.py](#test_batch_f_toolspy)（25）
6. [test_catalog.py](#test_catalogpy)（8）
7. [test_chat_shell.py](#test_chat_shellpy)（16）
8. [test_classic_adapter.py](#test_classic_adapterpy)（96）
9. [test_command_tools.py](#test_command_toolspy)（30）
10. [test_concurrency.py](#test_concurrencypy)（8）
11. [test_context_assembly.py](#test_context_assemblypy)（184）
12. [test_context_config_wiring.py](#test_context_config_wiringpy)（3）
13. [test_context_pipeline.py](#test_context_pipelinepy)（19）
14. [test_context_plumbing.py](#test_context_plumbingpy)（5）
15. [test_context_splice.py](#test_context_splicepy)（9）
16. [test_core.py](#test_corepy)（56）
17. [test_edited_files.py](#test_edited_filespy)（1）
18. [test_entry_layer.py](#test_entry_layerpy)（13）
19. [test_error_log.py](#test_error_logpy)（8）
20. [test_event_bus.py](#test_event_buspy)（9）
21. [test_fact_compat.py](#test_fact_compatpy)（4）
22. [test_file_safety.py](#test_file_safetypy)（24）
23. [test_file_size_format.py](#test_file_size_formatpy)（4）
24. [test_four_step_gate.py](#test_four_step_gatepy)（7）
25. [test_frame_shape_align.py](#test_frame_shape_alignpy)（6）
26. [test_gate_negative.py](#test_gate_negativepy)（53）
27. [test_goal_runner.py](#test_goal_runnerpy)（6）
28. [test_image_embed.py](#test_image_embedpy)（10）
29. [test_image_tool.py](#test_image_toolpy)（23）
30. [test_image_turns.py](#test_image_turnspy)（23）
31. [test_import_graph.py](#test_import_graphpy)（5）
32. [test_invest_tools.py](#test_invest_toolspy)（24）
33. [test_kb_plugin.py](#test_kb_pluginpy)（49）
34. [test_layout_min_width.py](#test_layout_min_widthpy)（2）
35. [test_mode_note.py](#test_mode_notepy)（12）
36. [test_model_provider.py](#test_model_providerpy)（24）
37. [test_plugin_contributions.py](#test_plugin_contributionspy)（30）
38. [test_plugin_http.py](#test_plugin_httppy)（18）
39. [test_plugins.py](#test_pluginspy)（23）
40. [test_protocol_contract.py](#test_protocol_contractpy)（13）
41. [test_quality_pipeline.py](#test_quality_pipelinepy)（12）
42. [test_readonly_tools.py](#test_readonly_toolspy)（25）
43. [test_resume_bridge.py](#test_resume_bridgepy)（6）
44. [test_run_registry.py](#test_run_registrypy)（13）
45. [test_session_context.py](#test_session_contextpy)（22）
46. [test_session_seq.py](#test_session_seqpy)（23）
47. [test_session_store.py](#test_session_storepy)（17）
48. [test_session_tools.py](#test_session_toolspy)（17）
49. [test_settings_panel.py](#test_settings_panelpy)（12）
50. [test_source_snapshot.py](#test_source_snapshotpy)（10）
51. [test_task_tools.py](#test_task_toolspy)（27）
52. [test_todo_context_prompt.py](#test_todo_context_promptpy)（19）
53. [test_tool_registry.py](#test_tool_registrypy)（17）
54. [test_tool_session_gate.py](#test_tool_session_gatepy)（1）
55. [test_usage_metrics.py](#test_usage_metricspy)（7）
56. [test_version_stamp.py](#test_version_stamppy)（4）
57. [test_web_frontend.py](#test_web_frontendpy)（5）
58. [test_web_shell.py](#test_web_shellpy)（50）
59. [test_web_ui_config.py](#test_web_ui_configpy)（4）
60. [test_write_gate.py](#test_write_gatepy)（16）
61. [test_write_path_keys_lifecycle.py](#test_write_path_keys_lifecyclepy)（4）
62. [test_write_path_tools.py](#test_write_path_toolspy)（30）

## test_app_context.py

共 11 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AppContextTest` | `test_dispose_all_clears_everything` | dispose_all 后全部服务被清理；旧句柄仍幂等。 |
| 2 | `AppContextTest` | `test_dispose_all_empty_ok` | 无注册时 dispose_all 为无操作。 |
| 3 | `AppContextTest` | `test_dispose_all_runs_in_reverse_registration_order` | dispose_all 按注册逆序调用 disposer（后注册先清理）。 |
| 4 | `AppContextTest` | `test_dispose_then_dispose_all_consistent` | 先单独注销一个，再 dispose_all：剩余全部清理、无残留。 |
| 5 | `AppContextTest` | `test_disposer_idempotent` | disposer 幂等：二次调用无副作用，且不阻挡同名再注册。 |
| 6 | `AppContextTest` | `test_disposer_removes_service` | disposer 调用后服务被注销。 |
| 7 | `AppContextTest` | `test_get_missing_raises` | 未注册服务解析抛 KeyError。 |
| 8 | `AppContextTest` | `test_none_value_service_fully_disposed` | None 值服务：dispose 后内部登记无残留；dispose_all 不遗漏。 |
| 9 | `AppContextTest` | `test_register_and_get` | 注册后可解析回同一对象。 |
| 10 | `AppContextTest` | `test_register_duplicate_rejected` | 重复注册被拒（防装配错误）。 |
| 11 | `AppContextTest` | `test_register_empty_name_rejected` | 空名称注册被拒。 |

## test_app_context_wiring.py

共 15 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AppAttributeDelegationTest` | `test_app_holds_no_duplicate_service_state` | 覆盖「App 属性即上下文快捷方式（无双份状态）」：app holds no duplicate service state |
| 2 | `AppAttributeDelegationTest` | `test_every_attribute_resolves_to_context_service` | 覆盖「App 属性即上下文快捷方式（无双份状态）」：every attribute resolves to context service |
| 3 | `AppAttributeDelegationTest` | `test_gate_still_resolves_through_session_registry` | 覆盖「App 属性即上下文快捷方式（无双份状态）」：gate still resolves through session registry |
| 4 | `AppAttributeDelegationTest` | `test_service_attributes_are_read_only` | 覆盖「App 属性即上下文快捷方式（无双份状态）」：service attributes are read only |
| 5 | `DisposeTest` | `test_dispose_clears_services_and_sessions` | 覆盖「进程停机释放」：dispose clears services and sessions |
| 6 | `DisposeTest` | `test_dispose_is_idempotent` | 覆盖「进程停机释放」：dispose is idempotent |
| 7 | `DisposeTest` | `test_dispose_releases_default_bucket_gate` | 顺序保证：默认桶门控是惰性造的，若先清容器则永远漏释放。 |
| 8 | `DisposeTest` | `test_runner_registered_and_mesh_activator_wired` | 覆盖「进程停机释放」：runner registered and mesh activator wired |
| 9 | `ProcessServiceRegistryTest` | `test_all_required_services_registered` | 覆盖「进程级服务登记」：all required services registered |
| 10 | `ProcessServiceRegistryTest` | `test_build_app_is_context_backed` | 覆盖「进程级服务登记」：build app is context backed |
| 11 | `ProcessServiceRegistryTest` | `test_compactor_factory_registered_by_default` | 压缩器在装配期就位。 |
| 12 | `ProcessServiceRegistryTest` | `test_context_and_compactor_factories_default_on` | 上下文管线与压缩器**默认装配**。 |
| 13 | `ProcessServiceRegistryTest` | `test_duplicate_registration_still_rejected` | 覆盖「进程级服务登记」：duplicate registration still rejected |
| 14 | `ProcessServiceRegistryTest` | `test_optional_services_registered_when_injected` | 覆盖「进程级服务登记」：optional services registered when injected |
| 15 | `ProcessServiceRegistryTest` | `test_store_absent_when_not_injected` | store 未注入时不登记（会话持久化是可选面）。 |

## test_architecture_hygiene.py

共 11 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `GateSinglePathAstTest` | `test_content_tools_assign_attr` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：content tools assign attr |
| 2 | `GateSinglePathAstTest` | `test_fallback_gate_attribute` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：fallback gate attribute |
| 3 | `GateSinglePathAstTest` | `test_gate_resolver_call_attr` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：gate resolver call attr |
| 4 | `GateSinglePathAstTest` | `test_innocuous_code_passes` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：innocuous code passes |
| 5 | `GateSinglePathAstTest` | `test_preview_tools_keyword` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：preview tools keyword |
| 6 | `GateSinglePathAstTest` | `test_preview_tools_tuple_unpack` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：preview tools tuple unpack |
| 7 | `GateSinglePathAstTest` | `test_register_write_path_keys_call` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：register write path keys call |
| 8 | `GateSinglePathAstTest` | `test_tool_path_keys_name` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：tool path keys name |
| 9 | `GateSinglePathAstTest` | `test_unregister_write_path_keys_import_alias` | 覆盖「负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住」：unregister write path keys import alias |
| 10 | `QualityGateShimAstTest` | `test_comment_mention_passes` | 覆盖「A class whose instances are single test cases」：comment mention passes |
| 11 | `QualityGateShimAstTest` | `test_import_quality_gate_caught` | 覆盖「A class whose instances are single test cases」：import quality gate caught |

## test_attachments_autonomy.py

共 19 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AutonomyTest` | `test_live_state_roundtrip` | 覆盖「自主模式的存储与续跑判定」：live state roundtrip |
| 2 | `AutonomyTest` | `test_no_auto_continue_means_no_continue` | 覆盖「自主模式的存储与续跑判定」：no auto continue means no continue |
| 3 | `AutonomyTest` | `test_per_conversation` | 覆盖「自主模式的存储与续跑判定」：per conversation |
| 4 | `AutonomyTest` | `test_runner_auto_continue_check_used` | `SessionRunner(auto_continue=...)` 被真正查询；判断函数抛错必须原样抛出，不得吞掉。 |
| 5 | `NormalizeImagesTest` | `test_accepts_valid_image` | 覆盖「服务端 images 校验」：accepts valid image |
| 6 | `NormalizeImagesTest` | `test_caps_at_max_images` | 覆盖「服务端 images 校验」：caps at max images |
| 7 | `NormalizeImagesTest` | `test_drops_empty_or_missing_data` | 覆盖「服务端 images 校验」：drops empty or missing data |
| 8 | `NormalizeImagesTest` | `test_drops_non_dict_and_non_list` | 覆盖「服务端 images 校验」：drops non dict and non list |
| 9 | `NormalizeImagesTest` | `test_drops_non_image_mime` | 覆盖「服务端 images 校验」：drops non image mime |
| 10 | `NormalizeImagesTest` | `test_keeps_valid_when_mixed_with_invalid` | 非法项静默丢弃，不连累合法项（附件是增强项）。 |
| 11 | `NormalizeImagesTest` | `test_mime_is_lowercased` | 覆盖「服务端 images 校验」：mime is lowercased |
| 12 | `UserContentTest` | `test_derive_messages_builds_multimodal_user_message` | 覆盖「附件 → 多模态 content」：derive messages builds multimodal user message |
| 13 | `UserContentTest` | `test_derive_messages_without_attachments_stays_string` | 覆盖「附件 → 多模态 content」：derive messages without attachments stays string |
| 14 | `UserContentTest` | `test_image_only_has_no_empty_text_part` | 纯截图提问：不得插入空文本段。 |
| 15 | `UserContentTest` | `test_invalid_attachment_ignored` | 覆盖「附件 → 多模态 content」：invalid attachment ignored |
| 16 | `UserContentTest` | `test_no_attachments_is_plain_string` | 覆盖「附件 → 多模态 content」：no attachments is plain string |
| 17 | `UserContentTest` | `test_text_and_image_parts` | 覆盖「附件 → 多模态 content」：text and image parts |
| 18 | `VisionDegradeTest` | `test_any_model_keeps_image_parts` | 图片一律原样下发 —— 不按模型名猜能力、不做降级剥图。 |
| 19 | `VisionDegradeTest` | `test_image_only_message_is_not_empty` | 覆盖「图片一律原样下发：没有任何按模型名降级剥图的分支」：image only message is not empty |

## test_batch_f_tools.py

共 25 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `GithubApiTest` | `test_create_pr_payload_and_url` | 覆盖「github_api」：create pr payload and url |
| 2 | `GithubApiTest` | `test_login_required_and_param_validation` | 覆盖「github_api」：login required and param validation |
| 3 | `GithubApiTest` | `test_update_pr_requires_a_field` | 覆盖「github_api」：update pr requires a field |
| 4 | `IpGeolocateTest` | `test_private_ip_normalized_to_export_lookup` | 覆盖「ip 定位」：private ip normalized to export lookup |
| 5 | `IpGeolocateTest` | `test_public_ip_path_with_loopback_variants` | 覆盖「ip 定位」：public ip path with loopback variants |
| 6 | `IpGeolocateTest` | `test_success_false_structured_error` | 覆盖「ip 定位」：success false structured error |
| 7 | `ReviewConclusionTest` | `test_call_is_submit_not_format_check` | 调用即提交：没有"仅格式校验"档；返回里不含 dry_run。 |
| 8 | `ReviewConclusionTest` | `test_cancel_preview_and_invalid` | 覆盖「review 提交与解锁（经 ToolTurnContext.session.gate）」：cancel preview and invalid |
| 9 | `ReviewConclusionTest` | `test_confirm_unlock_and_review_done` | 覆盖「review 提交与解锁（经 ToolTurnContext.session.gate）」：confirm unlock and review done |
| 10 | `ReviewConclusionTest` | `test_short_conclusion_and_missing_file_name_rejected` | 覆盖「review 提交与解锁（经 ToolTurnContext.session.gate）」：short conclusion and missing file name rejected |
| 11 | `SkillManageToolTest` | `test_copy_missing_source` | 覆盖「skill_manage 工具」：copy missing source |
| 12 | `SkillManageToolTest` | `test_copy_preview_and_executor` | 覆盖「skill_manage 工具」：copy preview and executor |
| 13 | `SkillManageToolTest` | `test_list_read_and_lookup_error` | 覆盖「skill_manage 工具」：list read and lookup error |
| 14 | `SkillsLibraryTest` | `test_copy_plan_execute_and_conflict` | 覆盖「Skills 库」：copy plan execute and conflict |
| 15 | `SkillsLibraryTest` | `test_scan_list_and_matching` | 覆盖「Skills 库」：scan list and matching |
| 16 | `SkillsLibraryTest` | `test_truncation_and_incremental_rescan` | 覆盖「Skills 库」：truncation and incremental rescan |
| 17 | `SkillsListNeverDoublesTest` | `test_auto_load_count_ignores_duplicate_entries` | 覆盖「清单翻倍防线：库内出现重复条目时，清单仍只列一份」：auto load count ignores duplicate entries |
| 18 | `SkillsListNeverDoublesTest` | `test_concurrent_rescan_replaces_the_list` | 覆盖「清单翻倍防线：库内出现重复条目时，清单仍只列一份」：concurrent rescan replaces the list |
| 19 | `SkillsListNeverDoublesTest` | `test_different_path_spelling_counts_once` | 同一文件的两种路径写法不能让 `len(list_skills())` 变成两倍。 |
| 20 | `SkillsListNeverDoublesTest` | `test_duplicate_entries_do_not_double_the_catalog` | 覆盖「清单翻倍防线：库内出现重复条目时，清单仍只列一份」：duplicate entries do not double the catalog |
| 21 | `SkillsListNeverDoublesTest` | `test_rescan_does_not_append_twice` | 覆盖「清单翻倍防线：库内出现重复条目时，清单仍只列一份」：rescan does not append twice |
| 22 | `WeatherTest` | `test_cn_alias_direct_resolution` | 覆盖「天气查询」：cn alias direct resolution |
| 23 | `WeatherTest` | `test_coordinates_and_days_clamp` | 覆盖「天气查询」：coordinates and days clamp |
| 24 | `WeatherTest` | `test_location_not_found` | 覆盖「天气查询」：location not found |
| 25 | `WeatherTest` | `test_scoring_prefers_exact_and_major` | 覆盖「天气查询」：scoring prefers exact and major |

## test_catalog.py

共 8 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CatalogDisplayTest` | `test_every_tool_has_display` | 覆盖「目录带 `display`（中文名 + 图标），来源是工具自己的声明」：every tool has display |
| 2 | `CatalogDisplayTest` | `test_render_includes_display` | 覆盖「目录带 `display`（中文名 + 图标），来源是工具自己的声明」：render includes display |
| 3 | `CheckCatalogTest` | `test_corrupt_file_detected` | 覆盖「校验器：缺失 / 损坏 / 漂移三式检出（仓库零漂移由 CI 的 check_catalog 守…」：corrupt file detected |
| 4 | `CheckCatalogTest` | `test_drift_detected` | 篡改三式（删 echo / 改 commit_write / 增 ghost）逐一被定位。 |
| 5 | `CheckCatalogTest` | `test_missing_file_detected` | 覆盖「校验器：缺失 / 损坏 / 漂移三式检出（仓库零漂移由 CI 的 check_catalog 守…」：missing file detected |
| 6 | `RenderCatalogTest` | `test_render_deterministic` | 同一装配集两次渲染逐字节一致；LF 换行、无 CRLF。 |
| 7 | `RenderCatalogTest` | `test_render_sorted_and_complete` | JSON 可解析；工具按名称排序；四个字段齐全。 |
| 8 | `RenderCatalogTest` | `test_write_catalog_roundtrip` | 写出文件与渲染文本逐字节一致（临时目录），无 CRLF。 |

## test_chat_shell.py

共 16 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChatArgParsingTest` | `test_build_session_accepts_parsed_args` | 覆盖「入口参数在装配之前解析：缺配置时 `--help` 仍可用」：build session accepts parsed args |
| 2 | `ChatArgParsingTest` | `test_help_exits_before_building_app` | 覆盖「入口参数在装配之前解析：缺配置时 `--help` 仍可用」：help exits before building app |
| 3 | `ChatArgParsingTest` | `test_session_and_text_are_parsed` | 覆盖「入口参数在装配之前解析：缺配置时 `--help` 仍可用」：session and text are parsed |
| 4 | `ChatConfirmRoundTripTest` | `test_default_bucket_gate_cannot_confirm_named_session` | 反面：默认桶门控确认不了具名会话的预览。 |
| 5 | `ChatConfirmRoundTripTest` | `test_preview_tool_names_include_write_path_tools` | 覆盖「端到端：壳层确认回调 → 模型凭同一 ID 提交（真实文件落盘）」：preview tool names include write path tools |
| 6 | `ChatConfirmRoundTripTest` | `test_shell_confirm_releases_preview_and_commit_lands` | 覆盖「端到端：壳层确认回调 → 模型凭同一 ID 提交（真实文件落盘）」：shell confirm releases preview and commit lands |
| 7 | `ChatExitReleaseTest` | `test_main_releases_session_on_exit` | 覆盖「交互壳退出时释放会话运行态」：main releases session on exit |
| 8 | `ChatExitReleaseTest` | `test_released_session_reparses_clean` | 释放后同 cid 重新解析得到干净上下文（红灯 / 待 review 不残留）。 |
| 9 | `ChatGateWiringTest` | `test_build_session_returns_named_conversation` | 覆盖「壳层门控解析：必须是会话自己的门控，不是默认桶」：build session returns named conversation |
| 10 | `ChatGateWiringTest` | `test_engine_runs_on_same_conversation_id` | 覆盖「壳层门控解析：必须是会话自己的门控，不是默认桶」：engine runs on same conversation id |
| 11 | `ChatGateWiringTest` | `test_gate_is_the_conversation_gate_not_default_bucket` | 覆盖「壳层门控解析：必须是会话自己的门控，不是默认桶」：gate is the conversation gate not default bucket |
| 12 | `ExplicitReleaseTest` | `test_close_all_clears_registry` | 覆盖「会话上下文显式释放（不引入自动淘汰）」：close all clears registry |
| 13 | `ExplicitReleaseTest` | `test_release_does_not_touch_persisted_records` | 释放只丢进程内运行态：会话记录（事实源）不受影响。 |
| 14 | `ExplicitReleaseTest` | `test_release_drops_only_that_conversation` | 覆盖「会话上下文显式释放（不引入自动淘汰）」：release drops only that conversation |
| 15 | `ExplicitReleaseTest` | `test_release_unknown_and_blank_are_safe` | 覆盖「会话上下文显式释放（不引入自动淘汰）」：release unknown and blank are safe |
| 16 | `ExplicitReleaseTest` | `test_web_release_conversation_reduces_active_count` | 关闭会话 API 调用 release 后 active_count 下降。 |

## test_classic_adapter.py

共 96 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `HistoryAttachmentReplayTest` | `test_attachment_id_is_recomputable` | id 必须**从事实派生**：刷新前后一致，否则浏览器不会重试那张失败的图。 |
| 2 | `HistoryAttachmentReplayTest` | `test_history_items_carry_attachments_and_had_images` | 覆盖「带附件的会话刷新后必须**能再看图**」：history items carry attachments and had images |
| 3 | `HistoryAttachmentReplayTest` | `test_history_replays_each_reasoning_before_its_tools` | 思考定稿在 `model_message.reasoning_content`，刷新后按轮插回工具卡前面。 |
| 4 | `HistoryAttachmentReplayTest` | `test_history_tool_canceled_stays_distinct_from_failed` | 停止是独立终态，刷新后标题才能和失败分开上色。 |
| 5 | `HistoryAttachmentReplayTest` | `test_history_tool_done_keeps_images` | 刷新后看图条目仍带着像素，展开面板才能把图画出来。 |
| 6 | `HistoryAttachmentReplayTest` | `test_inline_multimodal_content_is_also_accepted` | 兜底形态：content 直接是多模态数组时也要解出附件。 |
| 7 | `HistoryAttachmentReplayTest` | `test_plain_text_message_is_unaffected` | 覆盖「带附件的会话刷新后必须**能再看图**」：plain text message is unaffected |
| 8 | `InboundContractTest` | `test_attachment_ignores_invalid_images` | `images` 里没有可用 base64 时不登记（经典界面只在数组非空时才重建附件条）。 |
| 9 | `InboundContractTest` | `test_attachment_missing_is_404` | 覆盖「老入参 → 内核 → 老返回体」：attachment missing is 404 |
| 10 | `InboundContractTest` | `test_attachment_returns_image_bytes_not_json` | 经典界面用 `<img src>` 直接引用（il.js:7），所以必须返回字节而不是 JSON。 |
| 11 | `InboundContractTest` | `test_health_model_is_in_allowed_list` | `model` 必须在 `allowed_models` 里，否则经典界面白名单校验丢弃它 → 顶栏永远加载中。 |
| 12 | `InboundContractTest` | `test_history_carries_context_layout_at_top_level` | `context_layout` 在**顶层**，`applyContextLayoutFromHistory` 读那里。 |
| 13 | `InboundContractTest` | `test_history_rejects_bad_id` | 覆盖「老入参 → 内核 → 老返回体」：history rejects bad id |
| 14 | `InboundContractTest` | `test_history_returns_items_for_bubbles` | `items` 是刷新页面渲染气泡与工具卡的**唯一**来源（`renderHistoryItems`）。 |
| 15 | `InboundContractTest` | `test_history_returns_ok_true` | 回显必须带 `ok:true`，否则经典界面直接 return、整段历史不渲染。 |
| 16 | `InboundContractTest` | `test_invalid_conversation_id_rejected_on_write` | 覆盖「老入参 → 内核 → 老返回体」：invalid conversation id rejected on write |
| 17 | `InboundContractTest` | `test_sessions_read_id_not_conversation_id` | 经典界面读 `s.id`（agent-ui.js:309 附近）；`conversation_id` 不是它要的名字。 |
| 18 | `InboundContractTest` | `test_title_never_raises` | 覆盖「老入参 → 内核 → 老返回体」：title never raises |
| 19 | `InboundContractTest` | `test_ui_state_get_returns_only_client_independent_state` | GET 只回**与客户端无关**的那部分：哪些会话在跑。 |
| 20 | `InboundContractTest` | `test_ui_state_put_stores_nothing` | PUT 收到布局也**不落盘**；旧前端不会因此报错。 |
| 21 | `InboundContractTest` | `test_ui_state_put_writes_no_layout_file` | 确认没有留下布局文件（服务端不该有客户端状态的副本）。 |
| 22 | `InboundContractTest` | `test_usage_accumulates_across_events` | 覆盖「老入参 → 内核 → 老返回体」：usage accumulates across events |
| 23 | `InboundContractTest` | `test_usage_accumulator_uses_different_field_names` | 累计端点用 `total_*`，与 SSE 的 `prompt_tokens` **不是一套**（agent-ui.js:1176）。 |
| 24 | `OutboundContractTest` | `test_approval_suspension_is_not_a_choice_card` | 审批挂起发 `approval_required`，不发选项卡。 |
| 25 | `OutboundContractTest` | `test_assistant_delta_uses_delta_field` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：assistant delta uses delta field |
| 26 | `OutboundContractTest` | `test_assistant_only_on_final_message_with_content` | 工具调用轮没有正文，发空 `assistant` 会让经典界面渲染一个空气泡。 |
| 27 | `OutboundContractTest` | `test_audio_never_emitted` | `audio` 事件永远不该出现：TTS 不在能力面内。 |
| 28 | `OutboundContractTest` | `test_cancel_on_confirm_modal_records_a_declined_result` | 模态点「取消」（空 `confirm`）**当作拒绝作答、记成工具结果**， 与在端点里就地 `return 200 {"confirmed": False}` 行为不同。 |
| 29 | `OutboundContractTest` | `test_cancel_without_pending_does_not_start_an_empty_turn` | 没有挂起调用时的取消**不得**起新回合。 |
| 30 | `OutboundContractTest` | `test_chat_bubble_layout_puts_image_above_text` | 图文气泡：**图片在上、文字在下**。 |
| 31 | `OutboundContractTest` | `test_confirm_card_comes_from_the_kernel_fact` | 待确认卡由内核专用事实 `turn_awaiting_user` 驱动。 |
| 32 | `OutboundContractTest` | `test_context_layout_is_flat_with_segments` | `lastContextLayout = ev` 整包存下，所以 segments 在**顶层**（agent-ui.js:157）。 |
| 33 | `OutboundContractTest` | `test_failed_run_type_switch_does_not_emit_mode_changed` | 失败时不能报"模式已切换"——那会让按钮显示一个并未生效的模式。 |
| 34 | `OutboundContractTest` | `test_incomplete_awaiting_fact_is_ignored` | 缺 `call_id` 或缺选项的事实不发卡（残缺数据不猜、不半渲染）。 |
| 35 | `OutboundContractTest` | `test_llm_request_model_is_never_empty` | 请求快照里的 `params.model` 不能是空串。 |
| 36 | `OutboundContractTest` | `test_malformed_arguments_do_not_break_the_stream` | `arguments` 不是对象时按空对象处理（经典界面只把它 JSON 化显示，不校验）。 |
| 37 | `OutboundContractTest` | `test_model_message_with_content_emits_response_done_and_assistant` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：model message with content emits response done and assistant |
| 38 | `OutboundContractTest` | `test_only_a_real_suspension_asks_the_user` | **只有工具真挂起**才发 `user_confirm_required`——经典界面收到它就弹模态。 |
| 39 | `OutboundContractTest` | `test_plain_failure_is_not_mistaken_for_confirm` | 普通失败不得被判成待确认——否则每个报错都会弹出确认框。 |
| 40 | `OutboundContractTest` | `test_reasoning_delta_requires_round` | `round` 必须与 `lastLlm.round` 相等，否则经典界面丢弃（agent-ui.js:1674）。 |
| 41 | `OutboundContractTest` | `test_reasoning_is_not_promoted_into_chat_area` | 思考内容不经对话区填充（它属于右侧步骤卡）。 |
| 42 | `OutboundContractTest` | `test_run_type_query_does_not_emit_mode_changed` | 查询模式不该发 `mode_changed`（会把按钮刷成同一个值，纯噪声）。 |
| 43 | `OutboundContractTest` | `test_run_type_switch_emits_mode_changed` | `run_type` 切模式后必须补 `mode_changed`，否则经典界面的模式按钮停在旧值。 |
| 44 | `OutboundContractTest` | `test_step_started_emits_llm_round_then_request` | `llm_round` 是 `reasoning_*` / `llm_request` 的**前置**（agent-ui.js:1685）。 |
| 45 | `OutboundContractTest` | `test_todo_list_rides_on_tool_end` | 清单**没有独立事件**，挂在 `tool_end.todo_list_data` 上（agent-ui.js:160）。 |
| 46 | `OutboundContractTest` | `test_tool_call_becomes_tool_start_with_call_id` | `tool_call_id` 是配对的唯一键；空则后续 `tool_end` 被整个忽略（agent-ui.js:2013）。 |
| 47 | `OutboundContractTest` | `test_tool_call_does_not_pre_empt_the_confirm_card` | `tool_call` 期**不发**待确认卡——卡片由内核事实驱动，避免重复发两张。 |
| 48 | `OutboundContractTest` | `test_tool_call_without_id_is_skipped` | 没有 id 就配不上 tool_end，宁可一条都不发（发了就是永远转圈的卡）。 |
| 49 | `OutboundContractTest` | `test_tool_done_images_ride_beside_preview` | 看图的像素走 `images`，不写进 `preview` 文本。 |
| 50 | `OutboundContractTest` | `test_tool_result_preview_is_json_string` | `preview` 必须是 **JSON 字符串**（经典界面会 `JSON.parse`，agent-ui.js:2022）。 |
| 51 | `OutboundContractTest` | `test_tool_result_without_start_is_skipped` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：tool result without start is skipped |
| 52 | `OutboundContractTest` | `test_turn_ended_emits_done` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：turn ended emits done |
| 53 | `OutboundContractTest` | `test_turn_started_emits_conversation_first` | `conversation` 必须发，且要带头。 |
| 54 | `OutboundContractTest` | `test_unknown_kernel_event_is_ignored_not_raised` | 观察面纪律：翻译不认识的事件不能把事件流打断。 |
| 55 | `OutboundContractTest` | `test_usage_must_be_nested` | 用量**嵌套在 `usage` 键下**：经典界面读 `ev.usage.prompt_tokens`（agent-ui.js:156）。 |
| 56 | `OutboundContractTest` | `test_user_confirm_multi_flag_passes_through` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：user confirm multi flag passes through |
| 57 | `OutboundContractTest` | `test_write_gate_confirm_id_does_not_fake_a_confirmation` | `confirm_id` 是**写盘门控的二阶提交锁**：门控给预览类工具的 **成功结果**挂上它，意思是"锁已建好，模型接着调提交工具并把 `confirm_id` 传回来"。 用户交互**不发生在这一步**（解锁入口是 `review_conclusion`）。 |
| 58 | `ResumeContractTest` | `test_cursor_prefers_header_then_query` | `Last-Event-ID`（浏览器自动带）优先于 `?last_event_id=`；非法值回落 -1。 |
| 59 | `ResumeContractTest` | `test_latest_seq_reports_global_log_end` | `latest_seq` 是**全局**最大坐标；空仓库返回 -1。 |
| 60 | `ResumeContractTest` | `test_replay_frames_carry_seq` | 回放的帧必须带坐标，否则浏览器重连时没有游标可用。 |
| 61 | `ResumeContractTest` | `test_replay_never_leaks_seq_into_frame_payloads` | `_seq` 是位置元数据，不该以原名出现在给前端的帧里（会污染契约）。 |
| 62 | `ResumeContractTest` | `test_replay_only_targets_given_channel` | 续传只补**这一条**连接：别的连接的队列不能被塞进历史。 |
| 63 | `ResumeContractTest` | `test_replay_respects_cursor` | `seq > after` 且不重复补游标那一帧。 |
| 64 | `ResumeContractTest` | `test_sse_id_line_is_emitted_for_seq_frames` | SSE 的 `id:` 行是浏览器重连带 `Last-Event-ID` 的唯一来源。 |
| 65 | `SubscriptionLifecycleTest` | `test_bus_subscription_reaches_channels` | 端到端：事件经**真总线**发布 → 翻译 → 到达连接队列。 |
| 66 | `SubscriptionLifecycleTest` | `test_dispose_is_idempotent` | 覆盖「适配层对事件总线的订阅必须**按需**，不能是常驻观察者」：dispose is idempotent |
| 67 | `SubscriptionLifecycleTest` | `test_no_subscription_without_clients` | 覆盖「适配层对事件总线的订阅必须**按需**，不能是常驻观察者」：no subscription without clients |
| 68 | `SubscriptionLifecycleTest` | `test_subscribe_on_first_client_and_release_on_last` | 覆盖「适配层对事件总线的订阅必须**按需**，不能是常驻观察者」：subscribe on first client and release on last |
| 69 | `UiBundleTest` | `test_each_model_call_opens_its_own_card` | 多趟往返时每轮各起一卡（工具前后各一张）。 |
| 70 | `UiBundleTest` | `test_inline_html_contains_all_five_scripts` | 漏注入 `image-lightbox.js` 会让 `window.AIA` 缺失 → 附件四条链路**静默**失效。 |
| 71 | `UiBundleTest` | `test_inline_html_has_no_placeholders_left` | 覆盖「素材与内联打包」：inline html has no placeholders left |
| 72 | `UiBundleTest` | `test_light_hljs_sheet_is_scoped` | 两套高亮配色同页共存，浅色那套必须限定在 `[data-ui-theme="light"]` 下。 |
| 73 | `UiBundleTest` | `test_llm_call_start_opens_a_step_card` | **步骤卡必须起得来**。 |
| 74 | `UiBundleTest` | `test_reasoning_stays_out_of_the_chat_area` | **思考内容不能出现在对话区**（它属于右侧步骤卡）。 |
| 75 | `UiBundleTest` | `test_tool_tag_shows_final_state_immediately` | 工具结束时**立刻**写标签终态。 |
| 76 | `UiBundleTest` | `test_tts_entry_is_gone` | TTS 的**入口元素**应从素材里删掉。 |
| 77 | `UsageSemanticsTest` | `test_put_overwrites_instead_of_accumulating` | 覆盖语义：连报两次累计值，第二次必须**替换**而不是相加。 |
| 78 | `UserConfirmRoundTripTest` | `test_agree_mints_approval_id_for_the_option` | 同意：结果是「同意」加宿主签发的 approval_id，并记下 option_id。 |
| 79 | `UserConfirmRoundTripTest` | `test_cancel_posts_empty_confirm_and_submits_nothing` | 模态的「取消」发空 `confirm`：不能把它当成一次用户发言送出去。 |
| 80 | `UserConfirmRoundTripTest` | `test_choice_is_filled_back_as_the_tool_result` | 直通：用户的选择被写成**那次 `user_confirm` 调用的返回值**，不是新用户发言。 |
| 81 | `UserConfirmRoundTripTest` | `test_confirm_id_and_text_together_do_both` | 两者同时给：门控解锁 + 选择回填（同一个端点的两类语义）。 |
| 82 | `UserConfirmRoundTripTest` | `test_confirm_text_does_not_answer_an_approval` | 选项文本不能冒充审批结果，待审批保持原样。 |
| 83 | `UserConfirmRoundTripTest` | `test_invalid_conversation_id_rejected` | 覆盖「确认的**回路**：用户在模态里选完，选择必须真的送到模型」：invalid conversation id rejected |
| 84 | `UserConfirmRoundTripTest` | `test_mesh_failure_reports_error_without_raising` | `mesh` 不可用时给结构化错误，不要抛——确认端点是 UI 的关键路径。 |
| 85 | `UserConfirmRoundTripTest` | `test_reject_returns_disagree_and_stores_nothing` | 驳回：结果是「不同意」，不签发通行证。 |
| 86 | `UserConfirmRoundTripTest` | `test_write_gate_confirm_id_still_works` | 带 `confirm_id` 的写盘确认走内核既有的门控解锁，不经 mesh。 |
| 87 | `WireHygieneTest` | `test_channel_emits_heartbeat_when_idle` | 空闲时发心跳（经典界面靠它判连接存活）；非 `data:` 行经典界面会安全忽略。 |
| 88 | `WireHygieneTest` | `test_cid_exempt_set_is_exactly_two` | 契约豁免的事件必须在前端先接住，否则会被静默丢掉。 |
| 89 | `WireHygieneTest` | `test_detach_stops_delivery` | 覆盖「传输层铁律：帧格式与 `conversation_id`」：detach stops delivery |
| 90 | `WireHygieneTest` | `test_every_frame_carries_valid_conversation_id` | 没带合法 cid 的帧会被经典界面**整包静默丢弃**（agent-ui.js:100/146）。 |
| 91 | `WireHygieneTest` | `test_frame_without_cid_is_dropped_silently` | 入站事件没有 cid 时直接丢，不要造一个假 cid 塞给前端。 |
| 92 | `WireHygieneTest` | `test_frames_broadcast_to_every_channel` | **广播**而非共享队列：两个标签页必须各自收到完整事件流。 |
| 93 | `WireHygieneTest` | `test_heartbeat_is_cid_exempt` | 覆盖「传输层铁律：帧格式与 `conversation_id`」：heartbeat is cid exempt |
| 94 | `WireHygieneTest` | `test_normalize_cid_matches_ui_rule` | 经典界面的规则是 `/^[A-Za-z0-9_-]{8,128}$/`（agent-ui.js:8）。 |
| 95 | `WireHygieneTest` | `test_sse_payload_is_single_line_data_frame` | 帧格式必须是 `data: <单行 json>\n\n`（agent-ui.js:94-98）。 |
| 96 | `WireHygieneTest` | `test_tool_script_mapping_covers_known_tools` | 工具名要翻成经典界面认识的 `script`，否则图标与中文名退化成默认。 |

## test_command_tools.py

共 30 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CancelKillsProcessTest` | `test_cancel_kills_the_child_process_and_returns_quickly` | 覆盖「**停止要真的停子进程**：只退出内核循环不够」：cancel kills the child process and returns quickly |
| 2 | `CancelWiringTest` | `test_scope_without_cancel_check_is_safe` | 没传入检查函数时 `canceled()` 必须是 False；检查函数自己出错必须把异常抛出去。 |
| 3 | `CancelWiringTest` | `test_tool_port_passes_the_cancel_check_into_the_scope` | 覆盖「停止检查必须**从模块一路带到工具**（装配层，不是工具自己猜）」：tool port passes the cancel check into the scope |
| 4 | `CommandSafetyUnitTest` | `test_blacklist_del_with_advice` | 覆盖「机制层单测」：blacklist del with advice |
| 5 | `CommandSafetyUnitTest` | `test_blacklist_disk_and_acl` | 覆盖「机制层单测」：blacklist disk and acl |
| 6 | `CommandSafetyUnitTest` | `test_blacklist_multiword` | 覆盖「机制层单测」：blacklist multiword |
| 7 | `CommandSafetyUnitTest` | `test_blacklist_path_and_exe` | 覆盖「机制层单测」：blacklist path and exe |
| 8 | `CommandSafetyUnitTest` | `test_content_base64` | 覆盖「机制层单测」：content base64 |
| 9 | `CommandSafetyUnitTest` | `test_content_redirect_source` | 覆盖「机制层单测」：content redirect source |
| 10 | `CommandSafetyUnitTest` | `test_content_sed_i` | 覆盖「机制层单测」：content sed i |
| 11 | `CommandSafetyUnitTest` | `test_decode_output_gbk` | 覆盖「机制层单测」：decode output gbk |
| 12 | `CommandSafetyUnitTest` | `test_process_registry_and_kill` | 覆盖「机制层单测」：process registry and kill |
| 13 | `CommandSafetyUnitTest` | `test_resolve_shell` | 覆盖「机制层单测」：resolve shell |
| 14 | `CommandSafetyUnitTest` | `test_safe_mode_chars` | 覆盖「机制层单测」：safe mode chars |
| 15 | `CommandSafetyUnitTest` | `test_sanitize_ansi_and_cr` | 覆盖「机制层单测」：sanitize ansi and cr |
| 16 | `CommandSafetyUnitTest` | `test_sanitize_blank_collapse_and_truncate` | 覆盖「机制层单测」：sanitize blank collapse and truncate |
| 17 | `CommandToolsTest` | `test_run_blacklisted` | 覆盖「工具层：run_command（经管道唯一入口）」：run blacklisted |
| 18 | `CommandToolsTest` | `test_run_blacklisted_even_safe_mode_off` | 覆盖「工具层：run_command（经管道唯一入口）」：run blacklisted even safe mode off |
| 19 | `CommandToolsTest` | `test_run_cwd` | 覆盖「工具层：run_command（经管道唯一入口）」：run cwd |
| 20 | `CommandToolsTest` | `test_run_echo` | 覆盖「工具层：run_command（经管道唯一入口）」：run echo |
| 21 | `CommandToolsTest` | `test_run_exit_code` | 覆盖「工具层：run_command（经管道唯一入口）」：run exit code |
| 22 | `CommandToolsTest` | `test_run_safe_mode_blocks_chars` | 覆盖「工具层：run_command（经管道唯一入口）」：run safe mode blocks chars |
| 23 | `CommandToolsTest` | `test_run_safe_mode_off_allows_chain` | 覆盖「工具层：run_command（经管道唯一入口）」：run safe mode off allows chain |
| 24 | `CommandToolsTest` | `test_run_script_content_check` | 覆盖「工具层：run_command（经管道唯一入口）」：run script content check |
| 25 | `CommandToolsTest` | `test_run_timeout_kills` | 覆盖「工具层：run_command（经管道唯一入口）」：run timeout kills |
| 26 | `PythonInlineTest` | `test_inline_cwd_and_restore` | 覆盖「工具层：python_inline（经管道唯一入口）」：inline cwd and restore |
| 27 | `PythonInlineTest` | `test_inline_exception_captured` | 覆盖「工具层：python_inline（经管道唯一入口）」：inline exception captured |
| 28 | `PythonInlineTest` | `test_inline_prints` | 覆盖「工具层：python_inline（经管道唯一入口）」：inline prints |
| 29 | `PythonInlineTest` | `test_inline_prints_push_progress` | 覆盖「工具层：python_inline（经管道唯一入口）」：inline prints push progress |
| 30 | `PythonInlineTest` | `test_inline_system_exit` | 覆盖「工具层：python_inline（经管道唯一入口）」：inline system exit |

## test_concurrency.py

共 8 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextSourcesContentionTest` | `test_collect_sees_a_consistent_snapshot` | 覆盖「注入源注册表：并发注册/卸载后条目数与版本号仍然自洽」：collect sees a consistent snapshot |
| 2 | `ContextSourcesContentionTest` | `test_register_and_dispose_are_balanced` | 覆盖「注入源注册表：并发注册/卸载后条目数与版本号仍然自洽」：register and dispose are balanced |
| 3 | `LiveStateContentionTest` | `test_distinct_conversations_do_not_interfere` | 覆盖「实时状态：不同会话互不串写；同一会话的并发写不丢结构」：distinct conversations do not interfere |
| 4 | `LiveStateContentionTest` | `test_same_conversation_writes_stay_well_formed` | 覆盖「实时状态：不同会话互不串写；同一会话的并发写不丢结构」：same conversation writes stay well formed |
| 5 | `PendingStoreContentionTest` | `test_capacity_is_never_exceeded` | 覆盖「预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立」：capacity is never exceeded |
| 6 | `PendingStoreContentionTest` | `test_confirm_is_visible_to_concurrent_peek` | 覆盖「预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立」：confirm is visible to concurrent peek |
| 7 | `PendingStoreContentionTest` | `test_same_path_keeps_exactly_one_latest` | 覆盖「预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立」：same path keeps exactly one latest |
| 8 | `PendingStoreContentionTest` | `test_take_is_exactly_once` | 覆盖「预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立」：take is exactly once |

## test_context_assembly.py

共 184 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AssemblyShape` | `test_assembles_appends_tail` | 覆盖「头部 + 对话 + 尾部，顺序固定」：assembles appends tail |
| 2 | `AssemblyShape` | `test_assembles_ignores_non_dict_tail` | 覆盖「头部 + 对话 + 尾部，顺序固定」：assembles ignores non dict tail |
| 3 | `AssemblyShape` | `test_assembles_is_detached_from_pipeline` | 覆盖「头部 + 对话 + 尾部，顺序固定」：assembles is detached from pipeline |
| 4 | `AssemblyShape` | `test_assembles_without_tail` | 覆盖「头部 + 对话 + 尾部，顺序固定」：assembles without tail |
| 5 | `AssemblyShape` | `test_covered_end_beyond_length` | 覆盖「头部 + 对话 + 尾部，顺序固定」：covered end beyond length |
| 6 | `AssemblyShape` | `test_covered_end_drops_prefix` | 覆盖「头部 + 对话 + 尾部，顺序固定」：covered end drops prefix |
| 7 | `AssemblyShape` | `test_covered_end_zero_keeps_all` | 覆盖「头部 + 对话 + 尾部，顺序固定」：covered end zero keeps all |
| 8 | `AssemblyShape` | `test_dialogue_keeps_fact_order` | 覆盖「头部 + 对话 + 尾部，顺序固定」：dialogue keeps fact order |
| 9 | `AssemblyShape` | `test_dialogue_with_tool_pair` | 覆盖「头部 + 对话 + 尾部，顺序固定」：dialogue with tool pair |
| 10 | `AssemblyShape` | `test_empty_everything` | 覆盖「头部 + 对话 + 尾部，顺序固定」：empty everything |
| 11 | `AssemblyShape` | `test_full_headers_come_first_in_order` | 覆盖「头部 + 对话 + 尾部，顺序固定」：full headers come first in order |
| 12 | `AssemblyShape` | `test_header_change_is_visible_immediately` | 覆盖「头部 + 对话 + 尾部，顺序固定」：header change is visible immediately |
| 13 | `AssemblyShape` | `test_headers_include_summaries_after_kb` | 覆盖「头部 + 对话 + 尾部，顺序固定」：headers include summaries after kb |
| 14 | `AssemblyShape` | `test_less_headers_still_ordered` | 覆盖「头部 + 对话 + 尾部，顺序固定」：less headers still ordered |
| 15 | `AssemblyShape` | `test_mode_chunk_never_in_assembly` | 覆盖「头部 + 对话 + 尾部，顺序固定」：mode chunk never in assembly |
| 16 | `AssemblyShape` | `test_set_dialogue_replaces_previous` | 覆盖「头部 + 对话 + 尾部，顺序固定」：set dialogue replaces previous |
| 17 | `AssemblyShape` | `test_summary_can_be_cleared` | 覆盖「头部 + 对话 + 尾部，顺序固定」：summary can be cleared |
| 18 | `AssemblyShape` | `test_summary_order_follows_input_order` | 覆盖「头部 + 对话 + 尾部，顺序固定」：summary order follows input order |
| 19 | `AssemblyShape` | `test_summary_replacement_takes_effect` | 覆盖「头部 + 对话 + 尾部，顺序固定」：summary replacement takes effect |
| 20 | `AssemblyShape` | `test_two_summaries_both_kept` | 覆盖「头部 + 对话 + 尾部，顺序固定」：two summaries both kept |
| 21 | `CompactionContext` | `test_instruction_appears_once` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：instruction appears once |
| 22 | `CompactionContext` | `test_instruction_is_last_and_system` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：instruction is last and system |
| 23 | `CompactionContext` | `test_mode_change_does_not_affect_request` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：mode change does not affect request |
| 24 | `CompactionContext` | `test_no_new_input_path` | 没有新输入时，尾部只有模式一条；压缩请求 = 整份剔掉它 + 指令。 |
| 25 | `CompactionContext` | `test_prefix_equals_normal_request_minus_last_two` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：prefix equals normal request minus last two |
| 26 | `CompactionContext` | `test_summary_present_in_head` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：summary present in head |
| 27 | `CompactionContext` | `test_system_field_is_carried` | `system` 字段与平常请求同一个值（留空即从第一条起就不同）。 |
| 28 | `CompactionContext` | `test_tool_path_prefix_equals_normal_minus_last_one` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：tool path prefix equals normal minus last one |
| 29 | `CompactionContext` | `test_tool_path_request_shape` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：tool path request shape |
| 30 | `CompactionContext` | `test_tools_are_forwarded` | 工具定义是前缀的一部分：摘要请求必须带上同一份。 |
| 31 | `CompactionContext` | `test_user_path_drops_mode` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：user path drops mode |
| 32 | `CompactionContext` | `test_user_path_drops_new_input` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：user path drops new input |
| 33 | `CompactionContext` | `test_user_path_request_shape` | 覆盖「压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令」：user path request shape |
| 34 | `CompactionLoop` | `test_below_threshold_no_request` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：below threshold no request |
| 35 | `CompactionLoop` | `test_compressed_count_matches_step` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：compressed count matches step |
| 36 | `CompactionLoop` | `test_covered_end_advances` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：covered end advances |
| 37 | `CompactionLoop` | `test_degenerate_summary_is_rejected` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：degenerate summary is rejected |
| 38 | `CompactionLoop` | `test_empty_dialogue_returns_none` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：empty dialogue returns none |
| 39 | `CompactionLoop` | `test_no_context_returns_none` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：no context returns none |
| 40 | `CompactionLoop` | `test_no_summarize_fn_returns_none` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：no summarize fn returns none |
| 41 | `CompactionLoop` | `test_pending_does_not_enter_range` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：pending does not enter range |
| 42 | `CompactionLoop` | `test_provider_failure_is_released` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：provider failure is released |
| 43 | `CompactionLoop` | `test_reassembled_request_shape` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：reassembled request shape |
| 44 | `CompactionLoop` | `test_report_keys` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：report keys |
| 45 | `CompactionLoop` | `test_restore_from_events_rebuilds_state` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：restore from events rebuilds state |
| 46 | `CompactionLoop` | `test_restore_ignores_backwards_covered_end` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：restore ignores backwards covered end |
| 47 | `CompactionLoop` | `test_restore_ignores_other_events` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：restore ignores other events |
| 48 | `CompactionLoop` | `test_second_compaction_appends_second_summary` | 第二次压缩产出的摘要**追加**在已有摘要之后，不合并、不替换。 |
| 49 | `CompactionLoop` | `test_summary_appended_with_bridge` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：summary appended with bridge |
| 50 | `CompactionLoop` | `test_summary_messages_are_system` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：summary messages are system |
| 51 | `CompactionLoop` | `test_summary_text_comes_from_model` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：summary text comes from model |
| 52 | `CompactionLoop` | `test_view_messages_drops_covered` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：view messages drops covered |
| 53 | `Invariants` | `test_every_request_ends_with_instruction` | 覆盖「任何一条压缩请求都必须满足的硬约束」：every request ends with instruction |
| 54 | `Invariants` | `test_every_request_has_all_kb` | 覆盖「任何一条压缩请求都必须满足的硬约束」：every request has all kb |
| 55 | `Invariants` | `test_every_request_has_all_skills` | 覆盖「任何一条压缩请求都必须满足的硬约束」：every request has all skills |
| 56 | `Invariants` | `test_every_request_has_system_prompt` | 覆盖「任何一条压缩请求都必须满足的硬约束」：every request has system prompt |
| 57 | `Invariants` | `test_head_prefix_is_identical_across_requests` | 覆盖「任何一条压缩请求都必须满足的硬约束」：head prefix is identical across requests |
| 58 | `Invariants` | `test_instruction_text_is_stable` | 覆盖「任何一条压缩请求都必须满足的硬约束」：instruction text is stable |
| 59 | `Invariants` | `test_no_request_has_mode` | 覆盖「任何一条压缩请求都必须满足的硬约束」：no request has mode |
| 60 | `Invariants` | `test_summaries_survive_every_request` | 覆盖「任何一条压缩请求都必须满足的硬约束」：summaries survive every request |
| 61 | `LayoutFromMessages` | `test_dialogue_starts_at_the_first_user` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：dialogue starts at the first user |
| 62 | `LayoutFromMessages` | `test_empty_input` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：empty input |
| 63 | `LayoutFromMessages` | `test_given_system_text_is_used_and_not_double_counted` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：given system text is used and not double counted |
| 64 | `LayoutFromMessages` | `test_head_first_message_is_the_system_prompt` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：head first message is the system prompt |
| 65 | `LayoutFromMessages` | `test_last_head_message_is_the_summary` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：last head message is the summary |
| 66 | `LayoutFromMessages` | `test_mode_is_split_out` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：mode is split out |
| 67 | `LayoutFromMessages` | `test_mode_not_counted_as_dialogue` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：mode not counted as dialogue |
| 68 | `LayoutFromMessages` | `test_no_mode_means_no_mode_segment` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：no mode means no mode segment |
| 69 | `LayoutFromMessages` | `test_remaining_is_last` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：remaining is last |
| 70 | `LayoutFromMessages` | `test_total_equals_segments_sum` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：total equals segments sum |
| 71 | `LayoutPayload` | `test_budget_never_below_used` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：budget never below used |
| 72 | `LayoutPayload` | `test_last_segment_is_remaining` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：last segment is remaining |
| 73 | `LayoutPayload` | `test_no_tail_means_no_mode_segment` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：no tail means no mode segment |
| 74 | `LayoutPayload` | `test_payload_shape` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：payload shape |
| 75 | `LayoutPayload` | `test_pct_sums_to_100` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：pct sums to 100 |
| 76 | `LayoutPayload` | `test_tail_becomes_mode_segment` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：tail becomes mode segment |
| 77 | `LayoutPayload` | `test_total_matches_segments_minus_remaining` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：total matches segments minus remaining |
| 78 | `LayoutWithHead` | `test_dialogue_does_not_include_head` | 覆盖「兜底带装配出来的头部：能分清 Skills / 知识库 / 摘要」：dialogue does not include head |
| 79 | `LayoutWithHead` | `test_mode_splits_from_dialogue` | 覆盖「兜底带装配出来的头部：能分清 Skills / 知识库 / 摘要」：mode splits from dialogue |
| 80 | `LayoutWithHead` | `test_plugin_segments_are_one_row_each` | 同一插件两段各成一行，段名与数量都按描述来。 |
| 81 | `LayoutWithHead` | `test_total_equals_sum_without_remaining` | 覆盖「兜底带装配出来的头部：能分清 Skills / 知识库 / 摘要」：total equals sum without remaining |
| 82 | `LayoutWithHead` | `test_without_head_falls_back_to_position` | 不传 head：只能按位置猜，插件段落一律归到摘要之后的那一堆。 |
| 83 | `MaskIsHard` | `test_excerpt_never_touches_the_masked_tail` | 覆盖「遮盖的轮一律原样保留；压缩只在它前面发生」：excerpt never touches the masked tail |
| 84 | `MaskIsHard` | `test_excerpt_starts_at_zero` | 覆盖「遮盖的轮一律原样保留；压缩只在它前面发生」：excerpt starts at zero |
| 85 | `MaskIsHard` | `test_region_excludes_every_system_message` | 压缩区域落在对话段里，一条 system 都不含。 |
| 86 | `MaskIsHard` | `test_region_tool_chain_closed` | 覆盖「遮盖的轮一律原样保留；压缩只在它前面发生」：region tool chain closed |
| 87 | `MaskIsHard` | `test_single_turn_is_compressed_when_nothing_else_can_be` | 只有 1 轮：遮盖前面没东西可压 → **连它一起压**（压到 0 轮）。 |
| 88 | `MaskSurvivesOverflow` | `test_mask_invariant_over_random_shapes` | 随机形态：任何一次压缩之后，被遮盖的轮数必须 ≥ 配置值。 |
| 89 | `MaskSurvivesOverflow` | `test_masked_last_turn_stays_when_it_is_huge` | **核心**：末尾那一轮自己就吃满预算，仍然不许压它。 |
| 90 | `MaskSurvivesOverflow` | `test_only_masked_turns_still_get_compressed` | 只有被遮盖的轮 → **连它一起压**（压不动就是超上限失败）。 |
| 91 | `MaskSurvivesOverflow` | `test_reserve_two_keeps_two_turns` | 覆盖「内层管线：超阈值时遮盖仍然不被压」：reserve two keeps two turns |
| 92 | `MaskSurvivesOverflow` | `test_reserve_zero_means_no_mask` | 覆盖「内层管线：超阈值时遮盖仍然不被压」：reserve zero means no mask |
| 93 | `OrdinaryRequestNeverRewritesHistory` | `test_adding_a_turn_does_not_touch_earlier_messages` | 加一轮 → 前缀逐字节不变（只有末尾多出来）。 |
| 94 | `OrdinaryRequestNeverRewritesHistory` | `test_compression_only_drops_a_prefix` | 压缩之后对话段 = 原序列的一个后缀（不是被改写过的版本）。 |
| 95 | `OrdinaryRequestNeverRewritesHistory` | `test_tool_traffic_survives_set_dialogue` | 覆盖「普通请求只做追加：已发过的消息逐字节不变（改中间一条 = 缓存从那里起全废）」：tool traffic survives set dialogue |
| 96 | `PluginSegmentCountAlignmentTest` | `test_collect_segments_counts_match_items` | 覆盖「段与自报数量必须逐条对齐：错位是静默的，只在浮层上显示成离谱的数字」：collect segments counts match items |
| 97 | `PluginSegmentCountAlignmentTest` | `test_missing_reported_count_falls_back_to_one` | 覆盖「段与自报数量必须逐条对齐：错位是静默的，只在浮层上显示成离谱的数字」：missing reported count falls back to one |
| 98 | `PluginSegmentCountAlignmentTest` | `test_short_count_table_does_not_borrow_neighbours` | 数量表比来源表短时，多出来的段按自身条数算，不拿别的段的数字。 |
| 99 | `PluginSegmentsImmutableTest` | `test_assignment_is_rejected` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：assignment is rejected |
| 100 | `PluginSegmentsImmutableTest` | `test_containers_are_tuples` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：containers are tuples |
| 101 | `PluginSegmentsImmutableTest` | `test_source_lists_are_copied` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：source lists are copied |
| 102 | `PluginSegmentsImmutableTest` | `test_tuple_containers_reject_mutation` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：tuple containers reject mutation |
| 103 | `PluginSegmentsImmutableTest` | `test_wrong_arity_is_rejected_loudly` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：wrong arity is rejected loudly |
| 104 | `RandomShapeInvariants` | `test_compaction_range_never_splits_a_turn` | ① 压缩区间首尾都必须落在用户轮边界上。 |
| 105 | `RandomShapeInvariants` | `test_compaction_range_tool_chain_always_closed` | ② 压缩区间内的工具链必须闭合（否则切出残链）。 |
| 106 | `ReasoningReplayBudgetTest` | `test_config_default_matches_constant` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：config default matches constant |
| 107 | `ReasoningReplayBudgetTest` | `test_dialogue_segment_uses_the_budget` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：dialogue segment uses the budget |
| 108 | `ReasoningReplayBudgetTest` | `test_messages_clip_does_not_mutate_input` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：messages clip does not mutate input |
| 109 | `ReasoningReplayBudgetTest` | `test_negative_keeps_everything` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：negative keeps everything |
| 110 | `ReasoningReplayBudgetTest` | `test_positive_keeps_both_ends_and_marks_the_gap` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：positive keeps both ends and marks the gap |
| 111 | `ReasoningReplayBudgetTest` | `test_short_text_untouched` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：short text untouched |
| 112 | `ReasoningReplayBudgetTest` | `test_zero_drops_everything` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：zero drops everything |
| 113 | `RemainingCapacityTest` | `test_budget_zero_would_make_remaining_zero` | 不传预算（= 老装配点的行为）剩余容量就是 0 —— 这条守着别再退回去。 |
| 114 | `RemainingCapacityTest` | `test_old_snapshot_is_rescaled_on_read` | 事件里那份 `budget=已用` 的旧快照，渲染时按当前预算补正。 |
| 115 | `RemainingCapacityTest` | `test_rescale_falls_back_when_budget_unknown` | 拿不到预算时按"已用"归一（不再更差），段序与字段不变。 |
| 116 | `RemainingCapacityTest` | `test_snapshot_carries_the_budget` | 覆盖「「剩余容量」按压缩阈值算，不是按"已用"算 —— 否则界面那条永远是 0%」：snapshot carries the budget |
| 117 | `SegmentCountSemantics` | `test_dialogue_counts_user_turns_not_messages` | 覆盖「`count` 的计「个」口径按段定：头部按 system 条数，对话按用户轮数」：dialogue counts user turns not messages |
| 118 | `SegmentCountSemantics` | `test_layout_from_messages_counts_turns_too` | 覆盖「`count` 的计「个」口径按段定：头部按 system 条数，对话按用户轮数」：layout from messages counts turns too |
| 119 | `SegmentCountSemantics` | `test_system_prompt_counts_messages` | 覆盖「`count` 的计「个」口径按段定：头部按 system 条数，对话按用户轮数」：system prompt counts messages |
| 120 | `SegmentFieldParity` | `test_both_paths_expose_the_same_fields` | 覆盖「分段快照（内核事件）与兜底重算（适配层）必须给同一套字段」：both paths expose the same fields |
| 121 | `SegmentFieldParity` | `test_layout_event_forwards_every_field` | 适配层转发分段事件时不筛字段（白名单漏一个 = 前端少一样东西）。 |
| 122 | `SegmentKeysAndCounts` | `test_keys_and_labels` | 覆盖「段 key 与数量口径：插件段一律 `plugin:<插件名>`」：keys and labels |
| 123 | `SegmentKeysAndCounts` | `test_plugin_may_declare_more_than_one_segment` | 同一插件两段：数量按位置对上，不会互相覆盖。 |
| 124 | `SegmentOrderMatchesAssembly` | `test_header_order_is_system_plugins_summary` | 覆盖「分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画」：header order is system plugins summary |
| 125 | `SegmentOrderMatchesAssembly` | `test_layout_payload_keeps_the_same_order` | 覆盖「分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画」：layout payload keeps the same order |
| 126 | `SegmentOrderMatchesAssembly` | `test_segment_order_matches_header_order` | 覆盖「分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画」：segment order matches header order |
| 127 | `SegmentOrderMatchesAssembly` | `test_summary_sits_before_dialogue` | 覆盖「分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画」：summary sits before dialogue |
| 128 | `SegmentTokens` | `test_dialogue_split_into_two_segments` | 覆盖「逐段统计与段名」：dialogue split into two segments |
| 129 | `SegmentTokens` | `test_segments_sum_equals_assembled_total` | 关键一致性：分段之和 == 装配出来的消息总量（同估算器）。 |
| 130 | `SegmentTokens` | `test_summary_segment_counts_both_summaries` | 覆盖「逐段统计与段名」：summary segment counts both summaries |
| 131 | `SegmentTokens` | `test_system_segment_matches_its_message` | 覆盖「逐段统计与段名」：system segment matches its message |
| 132 | `SkillInjectionIntoRequest` | `test_empty_segments_leave_head_empty` | 覆盖「Skills 作为插件段落注入：顺序、压缩请求同源、整体重建」：empty segments leave head empty |
| 133 | `SkillInjectionIntoRequest` | `test_plugin_segments_are_not_duplicated_across_passes` | `set_plugin_segments` 是整体重建：多跑几趟不会累积。 |
| 134 | `SkillInjectionIntoRequest` | `test_plugin_segments_sit_after_system_prompt` | 覆盖「Skills 作为插件段落注入：顺序、压缩请求同源、整体重建」：plugin segments sit after system prompt |
| 135 | `SkillInjectionIntoRequest` | `test_plugin_segments_used_by_compaction_request` | 插件段落属头部：压缩请求必须带上同一份。 |
| 136 | `SkillInjectionIntoRequest` | `test_segment_stats_follow_the_plugin` | 分段统计里两段都挂在插件名下，段名与数量由插件给。 |
| 137 | `SkillInjectionIntoRequest` | `test_summary_sits_after_plugin_segments` | 覆盖「Skills 作为插件段落注入：顺序、压缩请求同源、整体重建」：summary sits after plugin segments |
| 138 | `SkillProgressiveDisclosure` | `test_auto_load_empty_when_no_auto_load_dir` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：auto load empty when no auto load dir |
| 139 | `SkillProgressiveDisclosure` | `test_auto_load_excludes_normal_skills` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：auto load excludes normal skills |
| 140 | `SkillProgressiveDisclosure` | `test_auto_load_messages_carry_bodies` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：auto load messages carry bodies |
| 141 | `SkillProgressiveDisclosure` | `test_registry_excludes_auto_load_skill` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：registry excludes auto load skill |
| 142 | `SkillProgressiveDisclosure` | `test_registry_excludes_skill_bodies` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：registry excludes skill bodies |
| 143 | `SkillProgressiveDisclosure` | `test_registry_is_absent_when_no_skills` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：registry is absent when no skills |
| 144 | `SkillProgressiveDisclosure` | `test_registry_lists_names_and_descriptions` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：registry lists names and descriptions |
| 145 | `SkillProgressiveDisclosure` | `test_skill_manager_lists_normal_skills_only` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：skill manager lists normal skills only |
| 146 | `SourceOrderDeclaration` | `test_kernel_pipeline_follows_the_same_order` | 真管线：Skills 两段 → 知识库 → 摘要 → 对话。 |
| 147 | `SourceOrderDeclaration` | `test_no_rank_sorts_last` | 没有位次的（应用级来源，不属于任何插件）排在插件段之后。 |
| 148 | `SourceOrderDeclaration` | `test_rank_beats_registration` | 先注册知识库（位次 1）、后注册 Skills（位次 0），组装仍是 Skills 在前。 |
| 149 | `SourceOrderDeclaration` | `test_same_rank_keeps_registration_order` | 覆盖「注入源的组装顺序：插件段按**插件清单位次**排，注册先后不影响结果」：same rank keeps registration order |
| 150 | `StripRules` | `test_empty` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：empty |
| 151 | `StripRules` | `test_empty_mode_note_and_no_marker` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：empty mode note and no marker |
| 152 | `StripRules` | `test_kb_never_stripped` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：kb never stripped |
| 153 | `StripRules` | `test_mode_in_the_middle_untouched` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：mode in the middle untouched |
| 154 | `StripRules` | `test_mode_removed_by_exact_text` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：mode removed by exact text |
| 155 | `StripRules` | `test_mode_removed_by_marker_fallback` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：mode removed by marker fallback |
| 156 | `StripRules` | `test_new_input_removed_before_mode` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：new input removed before mode |
| 157 | `StripRules` | `test_new_input_removed_when_last` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：new input removed when last |
| 158 | `StripRules` | `test_non_dict_entry` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：non dict entry |
| 159 | `StripRules` | `test_only_last_user_removed` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：only last user removed |
| 160 | `StripRules` | `test_previous_reply_is_kept` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：previous reply is kept |
| 161 | `StripRules` | `test_summary_never_stripped` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：summary never stripped |
| 162 | `StripRules` | `test_system_prompt_never_stripped` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：system prompt never stripped |
| 163 | `StripRules` | `test_tool_result_is_kept` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：tool result is kept |
| 164 | `StripRules` | `test_two_trailing_systems_both_stripped` | 覆盖「`_context_without_new_input` / `_strip_mode_tail…」：two trailing systems both stripped |
| 165 | `TailShape` | `test_mode_is_last` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：mode is last |
| 166 | `TailShape` | `test_mode_is_system_role` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：mode is system role |
| 167 | `TailShape` | `test_mode_swap_changes_only_the_last_entry` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：mode swap changes only the last entry |
| 168 | `TailShape` | `test_mode_text_is_exact` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：mode text is exact |
| 169 | `TailShape` | `test_neither` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：neither |
| 170 | `TailShape` | `test_new_input_is_user_role` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：new input is user role |
| 171 | `TailShape` | `test_no_mode_means_input_is_last` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：no mode means input is last |
| 172 | `TailShape` | `test_no_new_input_means_mode_follows_dialogue` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：no new input means mode follows dialogue |
| 173 | `TailShape` | `test_plan_mode_text_is_exact` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：plan mode text is exact |
| 174 | `TailShape` | `test_tool_result_tail` | 覆盖「尾部 = 本轮新输入 + 执行模式（模式永远最后）」：tool result tail |
| 175 | `TurnAtomicity` | `test_floor_before_first_user` | 覆盖「轮边界的定位与向下取整」：floor before first user |
| 176 | `TurnAtomicity` | `test_floor_beyond_end` | 覆盖「轮边界的定位与向下取整」：floor beyond end |
| 177 | `TurnAtomicity` | `test_floor_inside_turn_goes_back` | 覆盖「轮边界的定位与向下取整」：floor inside turn goes back |
| 178 | `TurnAtomicity` | `test_floor_on_boundary_is_identity` | 覆盖「轮边界的定位与向下取整」：floor on boundary is identity |
| 179 | `TurnAtomicity` | `test_is_boundary` | 覆盖「轮边界的定位与向下取整」：is boundary |
| 180 | `TurnAtomicity` | `test_tool_chain_balanced_missing_result` | 覆盖「轮边界的定位与向下取整」：tool chain balanced missing result |
| 181 | `TurnAtomicity` | `test_tool_chain_balanced_ok` | 覆盖「轮边界的定位与向下取整」：tool chain balanced ok |
| 182 | `TurnAtomicity` | `test_tool_chain_balanced_orphan_result` | 覆盖「轮边界的定位与向下取整」：tool chain balanced orphan result |
| 183 | `TurnAtomicity` | `test_turn_spans` | 覆盖「轮边界的定位与向下取整」：turn spans |
| 184 | `TurnAtomicity` | `test_turn_starts` | 覆盖「轮边界的定位与向下取整」：turn starts |

## test_context_config_wiring.py

共 3 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextFactoryCarriesEveryContextSettingTest` | `test_factory_passes_every_pipeline_setting` | 覆盖「`_default_context_factory` 必须把 [context] 的每一项都传给…」：factory passes every pipeline setting |
| 2 | `ContextFactoryCarriesEveryContextSettingTest` | `test_pipeline_gets_the_configured_values` | 覆盖「`_default_context_factory` 必须把 [context] 的每一项都传给…」：pipeline gets the configured values |
| 3 | `SegmentEventCarriesTheWindowTest` | `test_event_has_window_and_budget` | 覆盖「分段快照必须带上模型窗口：界面按它算占用率」：event has window and budget |

## test_context_pipeline.py

共 19 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChunksAndFlattenTest` | `test_flat_messages_to_user_rounds` | 覆盖「数据模型与展平」：flat messages to user rounds |
| 2 | `ChunksAndFlattenTest` | `test_round_and_chunk_append_semantics` | 覆盖「数据模型与展平」：round and chunk append semantics |
| 3 | `ChunksAndFlattenTest` | `test_seven_chunks_order_and_add` | 覆盖「数据模型与展平」：seven chunks order and add |
| 4 | `CodeDefaultsMatchTemplateTest` | `test_every_default_matches_template` | 覆盖「代码里的默认值必须与 `config.ini.example` 一致」：every default matches template |
| 5 | `DefaultConfigValues` | `test_compactor_signature_matches_config` | 覆盖「配置默认值与机制层常量必须一致（三处口径：config.py / 管线常量 / 压缩器签名）」：compactor signature matches config |
| 6 | `DefaultConfigValues` | `test_other_context_defaults` | 覆盖「配置默认值与机制层常量必须一致（三处口径：config.py / 管线常量 / 压缩器签名）」：other context defaults |
| 7 | `DefaultConfigValues` | `test_summary_token_threshold_default` | 覆盖「配置默认值与机制层常量必须一致（三处口径：config.py / 管线常量 / 压缩器签名）」：summary token threshold default |
| 8 | `ExcerptTest` | `test_adjust_back_extends_over_tool_chain` | 覆盖「摘要取段与工具链完整性」：adjust back extends over tool chain |
| 9 | `ExcerptTest` | `test_adjust_extends_end_for_open_results` | 覆盖「摘要取段与工具链完整性」：adjust extends end for open results |
| 10 | `MaxPassesConfigTest` | `test_app_carries_the_value` | 覆盖「`[agent] max_passes`：一回合的操作次数上限，可配」：app carries the value |
| 11 | `MaxPassesConfigTest` | `test_bad_value_falls_back` | 写错不该让回合跑不起来：非法值回落默认，0/负数按 1。 |
| 12 | `MaxPassesConfigTest` | `test_config_value_wins` | 覆盖「`[agent] max_passes`：一回合的操作次数上限，可配」：config value wins |
| 13 | `MaxPassesConfigTest` | `test_default_is_64` | 覆盖「`[agent] max_passes`：一回合的操作次数上限，可配」：default is 64 |
| 14 | `MaxPassesConfigTest` | `test_engine_carries_the_value` | 覆盖「`[agent] max_passes`：一回合的操作次数上限，可配」：engine carries the value |
| 15 | `MemoryAndEstimateTest` | `test_append_new_msg_and_append_msg` | 覆盖「待并摘要 / 估算 / 统计 / 追加」：append new msg and append msg |
| 16 | `MemoryAndEstimateTest` | `test_pending_mem_flow` | 覆盖「待并摘要 / 估算 / 统计 / 追加」：pending mem flow |
| 17 | `MemoryAndEstimateTest` | `test_round_count` | 覆盖「待并摘要 / 估算 / 统计 / 追加」：round count |
| 18 | `MemoryAndEstimateTest` | `test_token_estimates` | 覆盖「待并摘要 / 估算 / 统计 / 追加」：token estimates |
| 19 | `RebuildTest` | `test_rebuild_from_messages` | 覆盖「时序重建（走 MVP 路径）」：rebuild from messages |

## test_context_plumbing.py

共 5 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextPlumbingTest` | `test_context_does_not_leak_outside_the_call` | 调用结束即还原：工具轮次上下文不跨调用泄漏。 |
| 2 | `ContextPlumbingTest` | `test_missing_contexts_degrade_instead_of_failing` | 没有 app/session（脚本直建引擎）时仍能跑，只是相关字段为空。 |
| 3 | `ContextPlumbingTest` | `test_service_lookup_from_tool_round` | 全局能力经上下文解析（不必在构造期注入）。 |
| 4 | `ContextPlumbingTest` | `test_session_state_reachable_from_tool_round` | 会话态（门控 / 实时状态 / 待确认）直接从会话上下文取。 |
| 5 | `ContextPlumbingTest` | `test_tool_sees_all_three_contexts` | 覆盖「三级上下文在工具轮次内可用」：tool sees all three contexts |

## test_context_splice.py

共 9 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AwaitingFactTest` | `test_pending_call_is_discoverable_from_facts` | 覆盖「挂起信息落盘与"待解决"判定（宿主靠它知道有调用等人）」：pending call is discoverable from facts |
| 2 | `AwaitingFactTest` | `test_pending_state_is_readable_from_facts_not_from_session_context` | 挂起状态**从事实源可读** —— 判定"有待解决的调用"只凭事实就够。 |
| 3 | `ContextSpliceTest` | `test_no_staging_table_is_needed` | ② 恢复路径上**不需要**外部结果暂存表之类的东西：事实源里只有工具结果。 |
| 4 | `ContextSpliceTest` | `test_no_user_message_is_inserted_on_resume` | 恢复轮**没有用户输入**：绝不能凭空多一条 user 消息——那会让请求序列非法。 |
| 5 | `ContextSpliceTest` | `test_real_store_carries_the_splice` | ③ 用**现有真实存储**：确认那一刻写下结果事实就完成了拼接。 |
| 6 | `ContextSpliceTest` | `test_repeated_terminal_folds_to_one_tool_message` | 同一 `call_id` 的终态写两次时，派生对话里只有一条 tool 消息。 |
| 7 | `ContextSpliceTest` | `test_spliced_result_lands_exactly_after_the_tool_call` | ① 拼接后 `tool` 紧跟带 `tool_calls` 的 `assistant`——不插任何用户消息。 |
| 8 | `ContextSpliceTest` | `test_stale_empty_input_in_old_records_is_tolerated` | **第二道防线**：会话记录里存着空的 `input_claimed` 时，派生仍必须给出合法序列。 |
| 9 | `ResumeSpliceNamingTest` | `test_written_fact_name_is_the_one_kernel_consumes` | 覆盖「`_splice_resume` 必须写**内核当前认的结果事实名**」：written fact name is the one kernel consumes |

## test_core.py

共 56 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ArchitectureTest` | `test_abandoned_consumer_is_reported` | 消费者中途放弃迭代时，宿主给出 `abandoned` 而不是留一个 None 结论。 |
| 2 | `ArchitectureTest` | `test_data_never_rides_on_the_return_value` | 数据只走事件：一趟跑完后事实与事件一一对应。 |
| 3 | `ArchitectureTest` | `test_events_stream_out_incrementally` | **流式**：事件在产出那一刻就让出去，不是等回合跑完再一次性返回。 |
| 4 | `ArchitectureTest` | `test_every_module_returns_an_outcome_on_every_path` | **每个模块的每条路径都必须 return `Outcome`**。 |
| 5 | `ArchitectureTest` | `test_halt_stops_the_chain_immediately` | 覆盖「内核自身的架构约束（判据在真实模块上重验）」：halt stops the chain immediately |
| 6 | `ArchitectureTest` | `test_host_knows_nothing_about_module_semantics` | 宿主只遍历与读四态：一条完全陌生的链也照跑。 |
| 7 | `ArchitectureTest` | `test_ports_expose_no_writable_public_fields` | 覆盖「内核自身的架构约束（判据在真实模块上重验）」：ports expose no writable public fields |
| 8 | `ArchitectureTest` | `test_runaway_chain_hits_the_guard` | 永远要求续行的模块撞护栏而不是死循环（那是模块 bug，不该拖死宿主）。 |
| 9 | `ArchitectureTest` | `test_swap_a_module_without_touching_others` | 换掉模型模块的实现，其余模块与宿主零改动。 |
| 10 | `ArchitectureTest` | `test_unknown_module_return_is_a_loud_error` | 覆盖「内核自身的架构约束（判据在真实模块上重验）」：unknown module return is a loud error |
| 11 | `BasicTurnTest` | `test_failed_tool_result_reaches_the_model_as_error` | 工具失败与成功同形：`{"ok":false,"error":…}`（来自结果事实）。 |
| 12 | `BasicTurnTest` | `test_failed_tool_with_data_keeps_envelope` | 失败附带 data 时仍是顶层 ok/error/data。 |
| 13 | `BasicTurnTest` | `test_message_sequence_is_valid_for_the_model` | 覆盖「纯文本回合：输入 → 模型 → 收尾」：message sequence is valid for the model |
| 14 | `BasicTurnTest` | `test_model_sees_the_real_tool_result_not_null` | **模型必须看到工具的真实结果**——不能是 `null`。 |
| 15 | `BasicTurnTest` | `test_no_input_means_no_user_message` | 无新输入时不发 `input_claimed`（恢复轮的前提）。 |
| 16 | `BasicTurnTest` | `test_simple_answer_completes_in_one_pass` | 覆盖「纯文本回合：输入 → 模型 → 收尾」：simple answer completes in one pass |
| 17 | `BasicTurnTest` | `test_usage_is_emitted_when_provided` | 覆盖「纯文本回合：输入 → 模型 → 收尾」：usage is emitted when provided |
| 18 | `CancelTest` | `test_cancel_check_error_propagates` | 停止检查自己出错必须把异常抛出去，不得装成「未取消」。 |
| 19 | `CancelTest` | `test_canceled_batch_keeps_the_model_history_valid` | 补占位的根本理由：`assistant(tool_calls)` 必须配齐 tool 响应，否则下一轮请求被 API 拒。 |
| 20 | `CancelTest` | `test_no_cancel_check_means_no_stop` | 不传停止检查（脚本直建）时行为不变。 |
| 21 | `CancelTest` | `test_stop_before_any_tool_marks_all_as_canceled` | **入口检查点**就被叫停：连模型都不叫，工具一个都不启动。 |
| 22 | `CancelTest` | `test_stop_is_recorded_as_stopped_not_paused` | `stopped` ≠ `paused` ≠ `halted`：三者语义不同，观察面靠它分辨。 |
| 23 | `CancelTest` | `test_stop_mid_batch_pads_the_remaining` | 跑到第 2 个调用前被叫停：第 1 个已完成，**剩余全部补终态**。 |
| 24 | `ContextSegmentsEventTest` | `test_dialogue_segment_grows_with_the_turn` | 对话段按真实内容估：把输入加大，近期记忆段必须变大。 |
| 25 | `ContextSegmentsEventTest` | `test_event_is_emitted_once_per_model_call` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：event is emitted once per model call |
| 26 | `ContextSegmentsEventTest` | `test_every_segment_has_label_and_pct` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：every segment has label and pct |
| 27 | `ContextSegmentsEventTest` | `test_last_segment_is_remaining` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：last segment is remaining |
| 28 | `ContextSegmentsEventTest` | `test_payload_has_segments_and_total` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：payload has segments and total |
| 29 | `ContextSegmentsEventTest` | `test_tool_round_emits_a_fresh_snapshot` | 工具轮会再装配一次 → 再发一条快照（分段随之变化）。 |
| 30 | `ContextSegmentsEventTest` | `test_total_is_the_sum_of_segments_without_remaining` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：total is the sum of segments without remaining |
| 31 | `DedupOnFailureTest` | `test_failure_then_success_keeps_each_fact_once` | 真实装配路径：连续失败 K=1..3 → 每个事实仍只落一行。 |
| 32 | `DedupOnFailureTest` | `test_pending_queue_deduplicates_by_seq` | `_put_pending` 收到"已经排队过"的事件时不重复入队。 |
| 33 | `DedupOnFailureTest` | `test_retry_after_failure_never_duplicates_rows` | 同一事件 **重复投递多次** → 磁盘上仍只有一份。 |
| 34 | `DurableRetryTest` | `test_failed_flush_survives_new_engine_each_turn` | 连续两次落盘失败 + 每回合新引擎 → **三回合的发言都要在磁盘上**。 |
| 35 | `DurableRetryTest` | `test_no_failure_path_stays_clean` | 不失败时行为不变（防止"为了重试"污染正常路径）。 |
| 36 | `DurableRetryTest` | `test_retry_does_not_duplicate_rows_or_coordinates` | 重试**不能**造副本：`turn_started` 次数 = 回合数，坐标无重复。 |
| 37 | `InfrastructureTest` | `test_events_carry_a_storage_coordinate` | 事实必须带全局存储坐标 `_seq` —— 否则浏览器收不到 `id:`。 |
| 38 | `InfrastructureTest` | `test_facts_are_flushed_incrementally_not_only_at_turn_end` | 事实**按趟增量落盘**：不能攒到回合末尾（那会丢掉整回合）。 |
| 39 | `InfrastructureTest` | `test_ports_log_is_readonly` | `ports.log` 必须是**只读视图** —— 否则模块能绕过 `emit` 写秘密事实。 |
| 40 | `InfrastructureTest` | `test_seq_does_not_stick_after_a_replay` | 适配层的存储坐标**每事件独立** —— 回放一次不能让之后所有帧粘住旧坐标。 |
| 41 | `InfrastructureTest` | `test_suspend_emits_exactly_one_tool_end` | 挂起时同一 `tool_call_id` **只能有一帧 `tool_end`**。 |
| 42 | `PortConflictTest` | `test_second_bind_on_same_port_raises` | 覆盖「端口被占时 `create_server` **必须抛错**」：second bind on same port raises |
| 43 | `StoreIntegrationTest` | `test_facts_persist_and_reload` | 覆盖「写入的事实能落进现有 `SessionStore`，且重启后能重建」：facts persist and reload |
| 44 | `SuspendBatchTest` | `test_placeholder_says_why_not_just_null` | 占位内容要**说明原因**，不能是空串或 `null`。 |
| 45 | `SuspendBatchTest` | `test_request_sequence_stays_valid_when_user_talks_instead_of_answering` | 挂起后用户**不答确认、直接发新消息** → 请求序列仍必须合法。 |
| 46 | `SuspendBatchTest` | `test_suspend_mid_batch_gives_the_rest_a_terminal_fact` | 一条消息要求 [ask_user(c1), echo(c2)]，c1 挂起时 **c2 必须有终态事实**。 |
| 47 | `SuspendResumeTest` | `test_resume_needs_no_memory_state` | 恢复不依赖任何内存游标：丢掉宿主与模块，仅凭事实重建即可。 |
| 48 | `SuspendResumeTest` | `test_resume_splices_result_and_model_continues` | 覆盖「工具需要外部输入 → 挂起（终态）；用户作答 → 拼接结果 → 新一轮」：resume splices result and model continues |
| 49 | `SuspendResumeTest` | `test_second_splice_would_duplicate_so_delivery_is_once` | 拼接没有幂等性：同一 `call_id` 交两次即非法。宿主须写前查重。 |
| 50 | `SuspendResumeTest` | `test_suspend_is_terminal_and_writes_no_tool_result` | 覆盖「工具需要外部输入 → 挂起（终态）；用户作答 → 拼接结果 → 新一轮」：suspend is terminal and writes no tool result |
| 51 | `SuspendResumeTest` | `test_suspended_call_is_not_retried_within_the_turn` | 覆盖「工具需要外部输入 → 挂起（终态）；用户作答 → 拼接结果 → 新一轮」：suspended call is not retried within the turn |
| 52 | `ToolLoopTest` | `test_tool_call_then_model_continues` | 覆盖「工具调用驱动多趟：**续行由事实末端表达，不需要谁发续行信号**」：tool call then model continues |
| 53 | `ToolLoopTest` | `test_tool_is_not_executed_twice` | 覆盖「工具调用驱动多趟：**续行由事实末端表达，不需要谁发续行信号**」：tool is not executed twice |
| 54 | `ToolLoopTest` | `test_two_round_trips` | 覆盖「工具调用驱动多趟：**续行由事实末端表达，不需要谁发续行信号**」：two round trips |
| 55 | `WiringTest` | `test_factory_receives_every_dependency_it_is_given` | `_build_engine` 收到的依赖必须真的传进引擎（防"收了不用"）。 |
| 56 | `WiringTest` | `test_live_events_carry_a_storage_coordinate_through_app_session` | 经 `App.session` 跑一轮，**总线上的事件必须带 `_seq`**。 |

## test_edited_files.py

共 1 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `EditedFilesPageTest` | `test_list_is_assembled_on_the_live_stream_only` | 覆盖「A class whose instances are single test cases」：list is assembled on the live stream only |

## test_entry_layer.py

共 13 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `BuildShellAppTest` | `test_default_data_root_is_used_when_omitted` | 覆盖「`build_shell_app`：默认按配置建 provider；给了就原样用」：default data root is used when omitted |
| 2 | `BuildShellAppTest` | `test_given_provider_and_store_are_used` | 覆盖「`build_shell_app`：默认按配置建 provider；给了就原样用」：given provider and store are used |
| 3 | `BuildShellAppTest` | `test_missing_config_raises_with_actionable_message` | 覆盖「`build_shell_app`：默认按配置建 provider；给了就原样用」：missing config raises with actionable message |
| 4 | `BuildShellAppTest` | `test_provider_is_built_from_config` | 覆盖「`build_shell_app`：默认按配置建 provider；给了就原样用」：provider is built from config |
| 5 | `CliEntryTest` | `test_builds_app_with_provider_from_config` | 覆盖「`agent.entry.cli`：配置检查在入口做，`chat.main` 只拿到 app 工…」：builds app with provider from config |
| 6 | `CliEntryTest` | `test_main_delegates_to_chat_main` | 覆盖「`agent.entry.cli`：配置检查在入口做，`chat.main` 只拿到 app 工…」：main delegates to chat main |
| 7 | `CliEntryTest` | `test_missing_config_returns_none` | 覆盖「`agent.entry.cli`：配置检查在入口做，`chat.main` 只拿到 app 工…」：missing config returns none |
| 8 | `HeadlessEntryTest` | `test_main_defaults_to_smoke_text` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一轮并打印」：main defaults to smoke text |
| 9 | `HeadlessEntryTest` | `test_main_passes_first_argument_and_uses_factory` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一轮并打印」：main passes first argument and uses factory |
| 10 | `HeadlessEntryTest` | `test_run_prints_one_line_per_event` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一轮并打印」：run prints one line per event |
| 11 | `WebMainTest` | `test_args_are_forwarded_to_shell_serve` | 覆盖「`agent.entry.web.main`：解析参数 → 装配 → 交给壳；配置缺失返回 2」：args are forwarded to shell serve |
| 12 | `WebMainTest` | `test_config_missing_returns_2` | 覆盖「`agent.entry.web.main`：解析参数 → 装配 → 交给壳；配置缺失返回 2」：config missing returns 2 |
| 13 | `WebMainTest` | `test_empty_fs_root_passes_none` | 覆盖「`agent.entry.web.main`：解析参数 → 装配 → 交给壳；配置缺失返回 2」：empty fs root passes none |

## test_error_log.py

共 8 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `BuildAppErrorLogTest` | `test_build_app_registers_and_binds` | 覆盖「A class whose instances are single test cases」：build app registers and binds |
| 2 | `ErrorLogWriteTest` | `test_report_string_without_exc_type` | 覆盖「A class whose instances are single test cases」：report string without exc type |
| 3 | `ErrorLogWriteTest` | `test_report_writes_jsonl` | 覆盖「A class whose instances are single test cases」：report writes jsonl |
| 4 | `ErrorLogWriteTest` | `test_write_failure_does_not_raise` | 覆盖「A class whose instances are single test cases」：write failure does not raise |
| 5 | `ErrorReportFacadeTest` | `test_bound_sink_receives_call` | 覆盖「A class whose instances are single test cases」：bound sink receives call |
| 6 | `ErrorReportFacadeTest` | `test_sink_exception_does_not_raise` | 覆盖「A class whose instances are single test cases」：sink exception does not raise |
| 7 | `ToolPipelineErrorLogTest` | `test_await_user_not_reported` | 覆盖「A class whose instances are single test cases」：await user not reported |
| 8 | `ToolPipelineErrorLogTest` | `test_tool_exception_not_reported` | 覆盖「A class whose instances are single test cases」：tool exception not reported |

## test_event_bus.py

共 9 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `EngineEventSinkTest` | `test_sink_exception_does_not_break_turn` | 覆盖「引擎侧接线：回合事件流同步旁路发布」：sink exception does not break turn |
| 2 | `EngineEventSinkTest` | `test_turn_events_published_to_bus` | 覆盖「引擎侧接线：回合事件流同步旁路发布」：turn events published to bus |
| 3 | `EventBusTest` | `test_dispose_all` | 覆盖「总线本体：分发 / 过滤 / 隔离 / 生命周期」：dispose all |
| 4 | `EventBusTest` | `test_disposer_idempotent` | 覆盖「总线本体：分发 / 过滤 / 隔离 / 生命周期」：disposer idempotent |
| 5 | `EventBusTest` | `test_publish_dispatches_in_order` | 覆盖「总线本体：分发 / 过滤 / 隔离 / 生命周期」：publish dispatches in order |
| 6 | `EventBusTest` | `test_snapshot_iteration` | 覆盖「总线本体：分发 / 过滤 / 隔离 / 生命周期」：snapshot iteration |
| 7 | `EventBusTest` | `test_subscribe_validation` | 覆盖「总线本体：分发 / 过滤 / 隔离 / 生命周期」：subscribe validation |
| 8 | `EventBusTest` | `test_subscriber_exception_isolated` | 覆盖「总线本体：分发 / 过滤 / 隔离 / 生命周期」：subscriber exception isolated |
| 9 | `EventBusTest` | `test_type_filter` | 覆盖「总线本体：分发 / 过滤 / 隔离 / 生命周期」：type filter |

## test_fact_compat.py

共 4 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ClassicToolResultTest` | `test_await_user_intermediate_result_does_not_reach_the_model` | 标了 `await_user` 的**中间**结果不交给模型（按定义还没返回）。 |
| 2 | `ClassicToolResultTest` | `test_cancel_without_a_closing_terminal_still_reaches_the_model` | 取消只写下 tool_failed、没有第二条终态时，模型仍要看到取消，而不是被请去重问。 |
| 3 | `ClassicToolResultTest` | `test_new_format_result_is_not_duplicated` | 新格式（`tool_done` + `tool_ended`）下**不得**因为认 `tool_result` 而多一条。 |
| 4 | `ClassicToolResultTest` | `test_user_answer_survives_in_the_tool_message` | 覆盖「**历史记录里的 `tool_result` 结果事实必须仍被消费**」：user answer survives in the tool message |

## test_file_safety.py

共 24 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `LayoutTest` | `test_broken_metadata_only_affects_its_own_version` | 覆盖「结构：`<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：broken metadata only affects its own version |
| 2 | `LayoutTest` | `test_create_returns_none_for_missing_file` | 覆盖「结构：`<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：create returns none for missing file |
| 3 | `LayoutTest` | `test_directory_names_carry_no_filename` | 目录名一律是短码 + 时间戳 —— 不塞文件名，也就不出现一串 `_`。 |
| 4 | `LayoutTest` | `test_files_are_grouped_by_path_hash` | 同一文件的所有版本在同一个哈希目录下。 |
| 5 | `LayoutTest` | `test_list_for_is_newest_first` | 覆盖「结构：`<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：list for is newest first |
| 6 | `LayoutTest` | `test_long_diff_is_clipped_and_marked` | 超长 diff 截断后要**标明**截断了 —— 静默截断会被读成"改动就这么点"。 |
| 7 | `LayoutTest` | `test_read_returns_the_bytes_that_were_backed_up` | 覆盖「结构：`<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：read returns the bytes that were backed up |
| 8 | `LayoutTest` | `test_same_second_versions_keep_chronological_order` | 同一秒内的多次改动必须能排出先后 —— 时间戳要精确到毫秒。 |
| 9 | `LayoutTest` | `test_two_different_files_never_share_a_group` | 中文名不同的两个文件必须各自一组（净化方案下会互相分不开）。 |
| 10 | `LayoutTest` | `test_unknown_mod_id_is_none` | 覆盖「结构：`<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：unknown mod id is none |
| 11 | `LayoutTest` | `test_versions_are_self_describing` | 覆盖「结构：`<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：versions are self describing |
| 12 | `PathHashTest` | `test_different_paths_differ` | 覆盖「A class whose instances are single test cases」：different paths differ |
| 13 | `PathHashTest` | `test_hash_is_short_hex` | 覆盖「A class whose instances are single test cases」：hash is short hex |
| 14 | `PathHashTest` | `test_same_path_same_hash` | 覆盖「A class whose instances are single test cases」：same path same hash |
| 15 | `PruneTest` | `test_prune_ignores_stray_files_at_the_root` | 覆盖「按版本目录名里的日期段清理；某文件的版本清空后收掉它的哈希目录」：prune ignores stray files at the root |
| 16 | `PruneTest` | `test_prune_keeps_the_group_while_any_version_survives` | 覆盖「按版本目录名里的日期段清理；某文件的版本清空后收掉它的哈希目录」：prune keeps the group while any version survives |
| 17 | `PruneTest` | `test_prune_leaves_unparseable_version_names` | 版本名不含合法日期时不动 —— 可能是人工放进来的。 |
| 18 | `PruneTest` | `test_prune_on_missing_root_is_noop` | 覆盖「按版本目录名里的日期段清理；某文件的版本清空后收掉它的哈希目录」：prune on missing root is noop |
| 19 | `PruneTest` | `test_prune_removes_older_than_retention` | 覆盖「按版本目录名里的日期段清理；某文件的版本清空后收掉它的哈希目录」：prune removes older than retention |
| 20 | `PruneTest` | `test_prune_removes_the_group_once_all_versions_are_gone` | 覆盖「按版本目录名里的日期段清理；某文件的版本清空后收掉它的哈希目录」：prune removes the group once all versions are gone |
| 21 | `RecycleTest` | `test_move_puts_the_file_under_a_day_directory` | 覆盖「A class whose instances are single test cases」：move puts the file under a day directory |
| 22 | `RecycleTest` | `test_target_for_sanitizes_the_name` | 覆盖「A class whose instances are single test cases」：target for sanitizes the name |
| 23 | `VersionTimeTextTest` | `test_returns_empty_when_format_does_not_match` | 覆盖「A class whose instances are single test cases」：returns empty when format does not match |
| 24 | `VersionTimeTextTest` | `test_reverse_parses_the_timestamp` | 覆盖「A class whose instances are single test cases」：reverse parses the timestamp |

## test_file_size_format.py

共 4 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `FileSizeFormatTest` | `test_bad_values_are_empty` | 覆盖「A class whose instances are single test cases」：bad values are empty |
| 2 | `FileSizeFormatTest` | `test_never_uses_byte_unit` | 任何大小都不出现"字节"。 |
| 3 | `FileSizeFormatTest` | `test_rounds_before_choosing_the_unit` | 先舍入再定单位 —— 否则 1048575 会显示成 `1024 KB`。 |
| 4 | `FileSizeFormatTest` | `test_sub_kilobyte_becomes_decimal_kb` | 覆盖「A class whose instances are single test cases」：sub kilobyte becomes decimal kb |

## test_four_step_gate.py

共 7 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `FourStepGateTest` | `test_happy_path_four_steps` | 四步全流程：预览 → 确认 → 提交（真实写入）→ 重读。 |
| 2 | `FourStepGateTest` | `test_no_preview_denied` | 无预览的直接提交被拒。 |
| 3 | `FourStepGateTest` | `test_pending_cap_evicts_oldest` | 未提交预览满额时，新登记挤掉最旧的一条。 |
| 4 | `FourStepGateTest` | `test_reread_required_for_next_edit` | 写后未重读前，再次提交被拒；read 后放行。 |
| 5 | `FourStepGateTest` | `test_same_path_keeps_only_latest_preview` | 同一写目标再次预览时，旧 confirm_id 被挤掉。 |
| 6 | `FourStepGateTest` | `test_snapshot_binding_and_single_use` | 提交内容以快照为准；confirm_id 一次性。 |
| 7 | `FourStepGateTest` | `test_unconfirmed_preview_denied` | 协议顺序：预览后未确认即提交，被拒。 |

## test_frame_shape_align.py

共 6 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `HistoryContractTest` | `test_items_carry_tool_role_for_cards` | 工具卡靠 `items` 里的 `tool` 角色重建（气泡之外还有卡片要恢复）。 |
| 2 | `HistoryContractTest` | `test_no_events_field` | 逐条老事件不再随回显下发 —— 浏览器不读它，而它按事件条数增长。 |
| 3 | `HistoryContractTest` | `test_payload_carries_only_what_the_page_reads` | 只给回显需要的三样：`ok` / `items` / `context_layout` / `todo_list`。 |
| 4 | `SseFrameContractTest` | `test_every_frame_carries_cid` | 覆盖「SSE 帧的契约」：every frame carries cid |
| 5 | `SseFrameContractTest` | `test_frames_are_single_line_json` | 一帧一行 JSON（SSE 的 `data:` 行按行发，不能含裸换行）。 |
| 6 | `SseFrameContractTest` | `test_seq_never_leaks_into_frame_payloads` | 内核坐标只用于 SSE 的 `id:` 行，不能留在帧载荷里。 |

## test_gate_negative.py

共 53 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AcceptanceSkipGateTest` | `test_duplicates_do_not_count_twice` | 覆盖「验收 skip：预算上限与白名单都必须能触发」：duplicates do not count twice |
| 2 | `AcceptanceSkipGateTest` | `test_non_whitelisted_fails` | 覆盖「验收 skip：预算上限与白名单都必须能触发」：non whitelisted fails |
| 3 | `AcceptanceSkipGateTest` | `test_over_budget_fails` | 覆盖「验收 skip：预算上限与白名单都必须能触发」：over budget fails |
| 4 | `AcceptanceSkipGateTest` | `test_whitelisted_within_budget_passes` | 覆盖「验收 skip：预算上限与白名单都必须能触发」：whitelisted within budget passes |
| 5 | `ApplicabilityGateTest` | `test_short_reason_fails` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则」：short reason fails |
| 6 | `ApplicabilityGateTest` | `test_unknown_rule_id_fails` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则」：unknown rule id fails |
| 7 | `ApplicabilityGateTest` | `test_well_formed_row_passes` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则」：well formed row passes |
| 8 | `ArchitectureHygieneGateTest` | `test_cross_layer_private_import_fails` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：cross layer private import fails |
| 9 | `ArchitectureHygieneGateTest` | `test_plugin_name_in_core_fails` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：plugin name in core fails |
| 10 | `ArchitectureHygieneGateTest` | `test_quality_gate_real_module_passes` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：quality gate real module passes |
| 11 | `ArchitectureHygieneGateTest` | `test_quality_gate_shim_import_fails` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：quality gate shim import fails |
| 12 | `ArchitectureHygieneGateTest` | `test_same_layer_private_import_passes` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：same layer private import passes |
| 13 | `CommentStyleGateTest` | `test_clean_comment_passes` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：clean comment passes |
| 14 | `CommentStyleGateTest` | `test_command_to_reader_fails` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：command to reader fails |
| 15 | `CommentStyleGateTest` | `test_string_literal_is_not_comment` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：string literal is not comment |
| 16 | `CommentStyleGateTest` | `test_todo_comment_fails` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：todo comment fails |
| 17 | `ComplexityGateTest` | `test_registered_big_file_only_reports_doc_drift` | 覆盖「复杂度：未登记的超阈值文件必须失败」：registered big file only reports doc drift |
| 18 | `ComplexityGateTest` | `test_unregistered_big_file_fails` | 覆盖「复杂度：未登记的超阈值文件必须失败」：unregistered big file fails |
| 19 | `ConfigDriftGateTest` | `test_real_file_extra_key_reports_line_number` | 覆盖「配置漂移：模板缺键/多键、真实文件多键都要失败」：real file extra key reports line number |
| 20 | `ConfigDriftGateTest` | `test_template_extra_key_fails` | 覆盖「配置漂移：模板缺键/多键、真实文件多键都要失败」：template extra key fails |
| 21 | `ConfigDriftGateTest` | `test_template_missing_key_fails` | 覆盖「配置漂移：模板缺键/多键、真实文件多键都要失败」：template missing key fails |
| 22 | `ConfigDriftGateTest` | `test_valid_pair_passes` | 覆盖「配置漂移：模板缺键/多键、真实文件多键都要失败」：valid pair passes |
| 23 | `ConfirmWordingGateTest` | `test_compliant_wording_passes` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：compliant wording passes |
| 24 | `ConfirmWordingGateTest` | `test_explanatory_wording_fails` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：explanatory wording fails |
| 25 | `ConfirmWordingGateTest` | `test_gate_without_next_step_fails` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：gate without next step fails |
| 26 | `ConfirmWordingGateTest` | `test_missing_unlock_tool_fails` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：missing unlock tool fails |
| 27 | `ConfirmWordingGateTest` | `test_vague_wording_fails` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：vague wording fails |
| 28 | `CoverageGateTest` | `test_at_or_above_floor_passes` | 覆盖「覆盖率：低于下限、缺数据都要失败」：at or above floor passes |
| 29 | `CoverageGateTest` | `test_below_floor_fails` | 覆盖「覆盖率：低于下限、缺数据都要失败」：below floor fails |
| 30 | `CoverageGateTest` | `test_missing_group_fails` | 覆盖「覆盖率：低于下限、缺数据都要失败」：missing group fails |
| 31 | `GeneratedArtifactDriftTest` | `test_ci_workflow_byte_drift_fails` | 覆盖「生成物门禁：手改 CI / 单测清单必须被 --check 抓到」：ci workflow byte drift fails |
| 32 | `GeneratedArtifactDriftTest` | `test_ci_workflow_current_is_clean` | 覆盖「生成物门禁：手改 CI / 单测清单必须被 --check 抓到」：ci workflow current is clean |
| 33 | `GeneratedArtifactDriftTest` | `test_render_contains_every_gate_and_acceptance` | 覆盖「生成物门禁：手改 CI / 单测清单必须被 --check 抓到」：render contains every gate and acceptance |
| 34 | `GeneratedArtifactDriftTest` | `test_unit_tests_md_drift_fails` | 覆盖「生成物门禁：手改 CI / 单测清单必须被 --check 抓到」：unit tests md drift fails |
| 35 | `ImportDirectionGateTest` | `test_composition_root_import_fails` | 覆盖「A2：向上导入与反向依赖装配根都必须被抓到」：composition root import fails |
| 36 | `ImportDirectionGateTest` | `test_downward_import_passes` | 覆盖「A2：向上导入与反向依赖装配根都必须被抓到」：downward import passes |
| 37 | `ImportDirectionGateTest` | `test_type_checking_annotation_is_allowed` | 覆盖「A2：向上导入与反向依赖装配根都必须被抓到」：type checking annotation is allowed |
| 38 | `ImportDirectionGateTest` | `test_upward_import_fails` | 覆盖「A2：向上导入与反向依赖装配根都必须被抓到」：upward import fails |
| 39 | `PythonFloorGateTest` | `test_ordinary_function_passes` | 覆盖「3.11 / 3.12 语法必须在 3.10 下限门禁里报出来」：ordinary function passes |
| 40 | `PythonFloorGateTest` | `test_pep695_generic_fails` | 覆盖「3.11 / 3.12 语法必须在 3.10 下限门禁里报出来」：pep695 generic fails |
| 41 | `ReadmeGateTest` | `test_acceptance_count_drift_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：acceptance count drift fails |
| 42 | `ReadmeGateTest` | `test_consistent_readme_passes` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：consistent readme passes |
| 43 | `ReadmeGateTest` | `test_gate_count_drift_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：gate count drift fails |
| 44 | `ReadmeGateTest` | `test_missing_marker_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：missing marker fails |
| 45 | `ReadmeGateTest` | `test_step_count_drift_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：step count drift fails |
| 46 | `ReadmeGateTest` | `test_test_count_drift_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：test count drift fails |
| 47 | `ReadmeGateTest` | `test_unknown_data_dir_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：unknown data dir fails |
| 48 | `SilentExceptGateTest` | `test_bare_pass_is_silent` | 覆盖「静默异常：预算判据与"静默/留痕"的语义判定」：bare pass is silent |
| 49 | `SilentExceptGateTest` | `test_budget_at_limit_passes` | 覆盖「静默异常：预算判据与"静默/留痕"的语义判定」：budget at limit passes |
| 50 | `SilentExceptGateTest` | `test_budget_overflow_fails` | 覆盖「静默异常：预算判据与"静默/留痕"的语义判定」：budget overflow fails |
| 51 | `SilentExceptGateTest` | `test_explicit_logging_is_not_silent` | 覆盖「静默异常：预算判据与"静默/留痕"的语义判定」：explicit logging is not silent |
| 52 | `UiJsGateTest` | `test_defined_helper_passes` | 覆盖「UI JS：调用未定义的辅助函数必须被抓到」：defined helper passes |
| 53 | `UiJsGateTest` | `test_undefined_helper_call_fails` | 覆盖「UI JS：调用未定义的辅助函数必须被抓到」：undefined helper call fails |

## test_goal_runner.py

共 6 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CancelTest` | `test_auto_rounds_are_capped` | 目标写歪时不能无限烧下去。 |
| 2 | `CancelTest` | `test_cancel_stops_goal_continuation` | 取消后必须停 —— 不判取消位就是死循环。 |
| 3 | `CancelTest` | `test_goal_rounds_counter_advances` | 界面要显示"已自动推进 N 轮"，计数必须真的在涨。 |
| 4 | `ContinuationTextTest` | `test_active_goal_wins_over_hardcoded_prompt` | 覆盖「`_next_continuation_text` 的判定表（不启线程，直接问）」：active goal wins over hardcoded prompt |
| 5 | `ContinuationTextTest` | `test_goal_absent_falls_back_to_autonomy_switch` | 覆盖「`_next_continuation_text` 的判定表（不启线程，直接问）」：goal absent falls back to autonomy switch |
| 6 | `ContinuationTextTest` | `test_paused_and_done_stop_even_when_autonomy_on` | **目标说了算**：暂停/达成后不能再被自主开关顶回去。 |

## test_image_embed.py

共 10 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `DerivedMessageShrinksTest` | `test_derived_message_carries_a_shrunk_image` | 端到端：进事实的是原图，**派生给模型的**是缩过的。 |
| 2 | `DerivedMessageShrinksTest` | `test_derived_message_keeps_plain_text_shape_when_no_attachment` | 覆盖「A class whose instances are single test cases」：derived message keeps plain text shape when no attachment |
| 3 | `EmbedBudgetTest` | `test_broken_base64_is_skipped` | 覆盖「A class whose instances are single test cases」：broken base64 is skipped |
| 4 | `EmbedBudgetTest` | `test_over_budget_becomes_skipped_not_dropped` | 超预算必须**可察觉**：进 skipped，由调用方转占位。 |
| 5 | `EmbedBudgetTest` | `test_within_budget_is_embedded` | 覆盖「A class whose instances are single test cases」：within budget is embedded |
| 6 | `ShrinkImageTest` | `test_extreme_aspect_ratio_survives` | 横幅截图（本仓的真实用例：492×42 的工具条）不该被搞坏。 |
| 7 | `ShrinkImageTest` | `test_garbage_bytes_are_returned_as_is` | 判据：缩放是优化，解不开就**原样发**，不能让图片发不出去。 |
| 8 | `ShrinkImageTest` | `test_large_image_is_shrunk_to_max_side` | 覆盖「A class whose instances are single test cases」：large image is shrunk to max side |
| 9 | `ShrinkImageTest` | `test_mime_is_detected_from_content` | 官方以文件**实际内容**判格式，所以我们也按内容判。 |
| 10 | `ShrinkImageTest` | `test_small_image_is_left_alone` | 本来就小的图不该被重编码 —— 白白损失质量。 |

## test_image_tool.py

共 23 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `BuildToolPartsTest` | `test_over_budget_reports_note` | 超预算不能静默丢 —— 工具得能告诉模型"有图但没带上"。 |
| 2 | `BuildToolPartsTest` | `test_parts_and_no_note_within_budget` | 覆盖「工具附件 → 块 + 超限说明（工具侧的正文不该被占位文字污染）」：parts and no note within budget |
| 3 | `DescribeImageTest` | `test_gif_size` | 覆盖「尺寸解析不依赖 Pillow —— 它是可选依赖，报尺寸是基本功能」：gif size |
| 4 | `DescribeImageTest` | `test_png_size` | 覆盖「尺寸解析不依赖 Pillow —— 它是可选依赖，报尺寸是基本功能」：png size |
| 5 | `DescribeImageTest` | `test_unknown_bytes_report_no_mime` | 非图片内容：报**空 mime**、尺寸 0，不抛。 |
| 6 | `PipelineCarriesAttachmentsTest` | `test_attachments_survive_pipeline` | 覆盖「管道把返回值上的附件搬进结果信封，工具不必自己知道 call_id」：attachments survive pipeline |
| 7 | `PipelineCarriesAttachmentsTest` | `test_plain_return_has_no_attachments` | 普通返回值（dict / 字符串）不该凭空多出附件字段。 |
| 8 | `ReadImageToolTest` | `test_default_keeps_original_size` | 默认不缩放：按图定位坐标的场景不能悄悄改尺寸。 |
| 9 | `ReadImageToolTest` | `test_empty_file_raises` | 覆盖「工具本体：成功给附件，失败给结构化错误」：empty file raises |
| 10 | `ReadImageToolTest` | `test_empty_path_raises` | 覆盖「工具本体：成功给附件，失败给结构化错误」：empty path raises |
| 11 | `ReadImageToolTest` | `test_explicit_max_side_reports_scale` | 显式缩放时必须回报换算比例 —— 否则模型按图上像素操作会全错。 |
| 12 | `ReadImageToolTest` | `test_missing_file_raises` | 覆盖「工具本体：成功给附件，失败给结构化错误」：missing file raises |
| 13 | `ReadImageToolTest` | `test_non_image_raises` | 按内容判定：改了扩展名的文本文件不该被当成图片发出去。 |
| 14 | `ReadImageToolTest` | `test_projection_keeps_tool_chosen_size` | 进模型的那一份不再二次缩放：摘要里的实发尺寸就是模型看到的尺寸。 |
| 15 | `ReadImageToolTest` | `test_reads_png_and_summarizes` | 覆盖「工具本体：成功给附件，失败给结构化错误」：reads png and summarizes |
| 16 | `StripProtectsToolImagesTest` | `test_excess_tool_image_is_stripped` | 超出总量闸的老工具图要被剥掉：不限量会随会话线性膨胀。 |
| 17 | `StripProtectsToolImagesTest` | `test_newest_user_image_wins_over_tool_image` | 配额只够一张时，留给**用户刚发的那张** —— 工具图是模型自己请求的， 用户刚发的图才是它这轮要回答的对象。 |
| 18 | `StripProtectsToolImagesTest` | `test_old_tool_image_survives_turn_window` | 轮次窗口**不**剥工具图：老工具图不是"重复内联的老用户图"， 它只由总量闸管。窗口只影响用户图。 |
| 19 | `StripProtectsToolImagesTest` | `test_tool_image_counts_toward_max` | 工具图占总量配额：不限量会让请求体随会话线性膨胀。 |
| 20 | `StripProtectsToolImagesTest` | `test_tool_image_with_no_user_images_survives` | 纯工具图（用户没发图）必须留着 —— 否则模型永远看不到工具读的图。 |
| 21 | `ToolContentTest` | `test_empty_text_with_image_gets_placeholder` | 空正文 + 有图：补一句说明，而不是发一个只有图片的 content。 |
| 22 | `ToolContentTest` | `test_no_attachments_keeps_string` | 没图时**保持字符串**：多模态数组会让请求体无谓变大，也改变既有形态。 |
| 23 | `ToolContentTest` | `test_with_image_becomes_array` | 覆盖「工具消息 content 的三态：无图 / 有图 / 只有图」：with image becomes array |

## test_image_turns.py

共 23 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ConfigWiringTest` | `test_app_carries_the_value` | 覆盖「配置项 `[context] image_turns` / `image_max` 一路到模型模…」：app carries the value |
| 2 | `ConfigWiringTest` | `test_default_config_value` | 覆盖「配置项 `[context] image_turns` / `image_max` 一路到模型模…」：default config value |
| 3 | `ConfigWiringTest` | `test_module_receives_the_value` | 覆盖「配置项 `[context] image_turns` / `image_max` 一路到模型模…」：module receives the value |
| 4 | `DefaultNoStripTest` | `test_default_is_noop` | 覆盖「缺省不剥：不传窗口参数时一条都不动，消息前缀恒定（KV 缓存因此可复用）」：default is noop |
| 5 | `DefaultNoStripTest` | `test_narrow_window_strips` | 配小 image_turns 即按用户轮剥图。 |
| 6 | `StripByTotalCapTest` | `test_cap_and_turns_apply_together` | 轮数先裁掉窗口外，窗口内再按总量裁。 |
| 7 | `StripByTotalCapTest` | `test_cap_keeps_the_most_recent_turn_first` | 五张的额度：最近一轮三张全保，剩两张给倒数第二轮，最老的一轮全舍。 |
| 8 | `StripByTotalCapTest` | `test_default_call_applies_no_cap` | 默认两道上限都大到不起作用：20 张图一张不剥。 |
| 9 | `StripByTotalCapTest` | `test_default_cap_is_sentinel` | 覆盖「轮数之外的第二道闸：总数上限，**最近一轮优先**」：default cap is sentinel |
| 10 | `StripByTotalCapTest` | `test_negative_cap_means_no_limit` | 覆盖「轮数之外的第二道闸：总数上限，**最近一轮优先**」：negative cap means no limit |
| 11 | `StripByTotalCapTest` | `test_oldest_turn_is_dropped_whole_before_touching_newer` | 覆盖「轮数之外的第二道闸：总数上限，**最近一轮优先**」：oldest turn is dropped whole before touching newer |
| 12 | `StripByTotalCapTest` | `test_one_turn_over_the_cap_keeps_the_tail_of_that_turn` | 一轮本身就超上限：留靠后的那几张（同一轮内后发的更可能是"这张图"）。 |
| 13 | `StripByTotalCapTest` | `test_placeholder_counts_the_dropped_blocks` | 覆盖「轮数之外的第二道闸：总数上限，**最近一轮优先**」：placeholder counts the dropped blocks |
| 14 | `StripByTotalCapTest` | `test_within_cap_touches_nothing` | 覆盖「轮数之外的第二道闸：总数上限，**最近一轮优先**」：within cap touches nothing |
| 15 | `StripByTotalCapTest` | `test_zero_cap_drops_everything` | 覆盖「轮数之外的第二道闸：总数上限，**最近一轮优先**」：zero cap drops everything |
| 16 | `StripByTurnTest` | `test_default_sentinel_disables_stripping` | 模块默认值也是哨兵值：不传参数时等于不剥。 |
| 17 | `StripByTurnTest` | `test_image_only_turn_keeps_a_placeholder` | 被剥的那轮如果只有图没有字，占位不能是空串（空 content 会被 API 拒）。 |
| 18 | `StripByTurnTest` | `test_keeps_only_recent_turns` | 覆盖「按轮保留，不是按张」：keeps only recent turns |
| 19 | `StripByTurnTest` | `test_negative_means_no_limit` | 覆盖「按轮保留，不是按张」：negative means no limit |
| 20 | `StripByTurnTest` | `test_one_turn_with_three_images_counts_as_one_turn` | 一轮三张 = 一轮；不该因为张数多就把这一轮挤掉。 |
| 21 | `StripByTurnTest` | `test_text_only_messages_are_untouched` | 覆盖「按轮保留，不是按张」：text only messages are untouched |
| 22 | `StripByTurnTest` | `test_within_limit_is_untouched` | 覆盖「按轮保留，不是按张」：within limit is untouched |
| 23 | `StripByTurnTest` | `test_zero_turns_drops_every_image` | 覆盖「按轮保留，不是按张」：zero turns drops every image |

## test_import_graph.py

共 5 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `DependencyGraphTest` | `test_entry_is_the_top_layer` | 覆盖「当前仓库必须零违规、零强连通分量」：entry is the top layer |
| 2 | `DependencyGraphTest` | `test_entry_may_import_the_composition_root` | 入口层是唯一允许导入装配根的地方（这正是它存在的理由）。 |
| 3 | `DependencyGraphTest` | `test_no_cycles` | 覆盖「当前仓库必须零违规、零强连通分量」：no cycles |
| 4 | `DependencyGraphTest` | `test_no_direction_violations` | 覆盖「当前仓库必须零违规、零强连通分量」：no direction violations |
| 5 | `DependencyGraphTest` | `test_shell_does_not_import_the_composition_root` | 运行期导入壳层不应把装配根拉进 `sys.modules`。 |

## test_invest_tools.py

共 24 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `BatchERegistrationTest` | `test_archive_declares_write_path_keys` | 覆盖「工具注册链路（六个来源共 12 件）+ 门控预览名单一致性」：archive declares write path keys |
| 2 | `BatchERegistrationTest` | `test_batch_e_plugins_register` | 覆盖「工具注册链路（六个来源共 12 件）+ 门控预览名单一致性」：batch e plugins register |
| 3 | `FileSearchTest` | `test_context_and_gitignore` | 覆盖「大目录内容搜索」：context and gitignore |
| 4 | `FileSearchTest` | `test_limit` | 覆盖「大目录内容搜索」：limit |
| 5 | `FindInFileTest` | `test_literal_or_and_occurrence` | 覆盖「单文件定位」：literal or and occurrence |
| 6 | `FindInFileTest` | `test_not_found_and_out_of_range` | 覆盖「单文件定位」：not found and out of range |
| 7 | `FindInFileTest` | `test_regex_invalid` | 覆盖「单文件定位」：regex invalid |
| 8 | `FindInFileTest` | `test_region_and_rowcols` | 覆盖「单文件定位」：region and rowcols |
| 9 | `OcrAndArchiveTest` | `test_archive_list_create_extract` | 覆盖「image_ocr / archive」：archive list create extract |
| 10 | `OcrAndArchiveTest` | `test_archive_unknown_format` | 覆盖「image_ocr / archive」：archive unknown format |
| 11 | `OcrAndArchiveTest` | `test_ocr_region_validation_and_dependency` | 覆盖「image_ocr / archive」：ocr region validation and dependency |
| 12 | `RegexLocateTest` | `test_directory_recursive_and_glob` | 覆盖「单文件/目录正则定位」：directory recursive and glob |
| 13 | `RegexLocateTest` | `test_invalid_regex_and_limit` | 覆盖「单文件/目录正则定位」：invalid regex and limit |
| 14 | `RegexLocateTest` | `test_limit_truncation` | 覆盖「单文件/目录正则定位」：limit truncation |
| 15 | `SystemToolsTest` | `test_env_probe_shape` | 覆盖「env_probe / unified_diagnose / git_workspace」：env probe shape |
| 16 | `SystemToolsTest` | `test_git_workspace_modes` | 覆盖「env_probe / unified_diagnose / git_workspace」：git workspace modes |
| 17 | `SystemToolsTest` | `test_unified_diagnose_red_green` | 覆盖「env_probe / unified_diagnose / git_workspace」：unified diagnose red green |
| 18 | `TextDataToolsTest` | `test_data_table_csv_actions` | 覆盖「text_diff / data_table」：data table csv actions |
| 19 | `TextDataToolsTest` | `test_data_table_xlsx_dependency_path` | 覆盖「text_diff / data_table」：data table xlsx dependency path |
| 20 | `TextDataToolsTest` | `test_text_diff_file_vs_text` | 覆盖「text_diff / data_table」：text diff file vs text |
| 21 | `WebToolsTest` | `test_fetch_acceptance_failure_keeps_data` | 覆盖「web_fetch / web_fetch_render」：fetch acceptance failure keeps data |
| 22 | `WebToolsTest` | `test_fetch_invalid_scheme` | 覆盖「web_fetch / web_fetch_render」：fetch invalid scheme |
| 23 | `WebToolsTest` | `test_fetch_ok_and_checks` | 覆盖「web_fetch / web_fetch_render」：fetch ok and checks |
| 24 | `WebToolsTest` | `test_render_dependency_path` | 覆盖「web_fetch / web_fetch_render」：render dependency path |

## test_kb_plugin.py

共 49 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextSourcesTest` | `test_exception_isolated` | 覆盖「A class whose instances are single test cases」：exception isolated |
| 2 | `ContextSourcesTest` | `test_order_and_disposer` | 覆盖「A class whose instances are single test cases」：order and disposer |
| 3 | `ContextSourcesTest` | `test_validation_and_empty_filter` | 覆盖「A class whose instances are single test cases」：validation and empty filter |
| 4 | `InjectionTest` | `test_pipeline_refresh_and_replace` | 覆盖「A class whose instances are single test cases」：pipeline refresh and replace |
| 5 | `InjectionTest` | `test_turn_end_to_end_injection` | 覆盖「A class whose instances are single test cases」：turn end to end injection |
| 6 | `KBConfigTest` | `test_config_lives_in_the_plugin_directory` | 配置跟着插件走，不在内核的 `config.ini` 里。 |
| 7 | `KBConfigTest` | `test_disabled_kb_returns_empty` | 覆盖「本插件配置（`plugins/knowledge/plugin-config.ini`）读取」：disabled kb returns empty |
| 8 | `KBConfigTest` | `test_existing_dir_enables` | 覆盖「本插件配置（`plugins/knowledge/plugin-config.ini`）读取」：existing dir enables |
| 9 | `KBConfigTest` | `test_missing_file_disables` | 覆盖「本插件配置（`plugins/knowledge/plugin-config.ini`）读取」：missing file disables |
| 10 | `KBConfigTest` | `test_missing_section_disables` | 覆盖「本插件配置（`plugins/knowledge/plugin-config.ini`）读取」：missing section disables |
| 11 | `KBConfigTest` | `test_nonexistent_dir_disables_without_error` | 覆盖「本插件配置（`plugins/knowledge/plugin-config.ini`）读取」：nonexistent dir disables without error |
| 12 | `KBConfigTest` | `test_values_tolerate_quotes_and_blank_lines` | 覆盖「本插件配置（`plugins/knowledge/plugin-config.ini`）读取」：values tolerate quotes and blank lines |
| 13 | `KBRuntimeTest` | `test_build_skips_over_limit_after_check` | 覆盖「A class whose instances are single test cases」：build skips over limit after check |
| 14 | `KBRuntimeTest` | `test_build_system_messages_and_count` | 覆盖「A class whose instances are single test cases」：build system messages and count |
| 15 | `KBRuntimeTest` | `test_disabled_when_root_missing` | 覆盖「A class whose instances are single test cases」：disabled when root missing |
| 16 | `KBRuntimeTest` | `test_file_allowed_size_and_hidden` | 覆盖「A class whose instances are single test cases」：file allowed size and hidden |
| 17 | `KBRuntimeTest` | `test_get_checked_single_cid_recovery` | 覆盖「A class whose instances are single test cases」：get checked single cid recovery |
| 18 | `KBRuntimeTest` | `test_list_files_excludes_hidden_and_pycache` | 覆盖「A class whose instances are single test cases」：list files excludes hidden and pycache |
| 19 | `KBRuntimeTest` | `test_persist_and_reload` | 覆盖「A class whose instances are single test cases」：persist and reload |
| 20 | `KBRuntimeTest` | `test_read_text_plain_and_bad_bytes` | 覆盖「A class whose instances are single test cases」：read text plain and bad bytes |
| 21 | `KBRuntimeTest` | `test_read_text_xlsx_fake_lib` | 覆盖「A class whose instances are single test cases」：read text xlsx fake lib |
| 22 | `KBRuntimeTest` | `test_read_text_xlsx_missing_lib` | 覆盖「A class whose instances are single test cases」：read text xlsx missing lib |
| 23 | `KBRuntimeTest` | `test_safe_resolve_boundaries` | 覆盖「A class whose instances are single test cases」：safe resolve boundaries |
| 24 | `KBRuntimeTest` | `test_set_checked_replace_filter_clear` | 覆盖「A class whose instances are single test cases」：set checked replace filter clear |
| 25 | `KnowledgeExtraSuffixesTest` | `test_config_key_is_read_and_used` | 覆盖「配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名」：config key is read and used |
| 26 | `KnowledgeExtraSuffixesTest` | `test_extra_extends_the_whitelist` | 覆盖「配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名」：extra extends the whitelist |
| 27 | `KnowledgeExtraSuffixesTest` | `test_missing_key_keeps_default_whitelist` | 覆盖「配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名」：missing key keeps default whitelist |
| 28 | `KnowledgeExtraSuffixesTest` | `test_parse_forms` | 覆盖「配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名」：parse forms |
| 29 | `KnowledgeTextOnlyTest` | `test_binary_is_neither_listed_nor_selectable` | 覆盖「知识库只收文本类文件：非文本不列、不可勾（读出来是替换字符与 NUL，白占预算）」：binary is neither listed nor selectable |
| 30 | `KnowledgeTextOnlyTest` | `test_runtime_rejects_binary_check` | 覆盖「知识库只收文本类文件：非文本不列、不可勾（读出来是替换字符与 NUL，白占预算）」：runtime rejects binary check |
| 31 | `KnowledgeTextOnlyTest` | `test_text_suffix_rules` | 覆盖「知识库只收文本类文件：非文本不列、不可勾（读出来是替换字符与 NUL，白占预算）」：text suffix rules |
| 32 | `PluginConfigIsolationTest` | `test_each_plugin_reads_its_own_config_file` | 覆盖「内核 `config.ini` 只含内核设置；插件设置在插件自己目录下的 plugin-conf…」：each plugin reads its own config file |
| 33 | `PluginConfigIsolationTest` | `test_kernel_templates_have_no_plugin_section` | 覆盖「内核 `config.ini` 只含内核设置；插件设置在插件自己目录下的 plugin-conf…」：kernel templates have no plugin section |
| 34 | `PluginConfigIsolationTest` | `test_skills_dir_comes_from_its_own_config` | 覆盖「内核 `config.ini` 只含内核设置；插件设置在插件自己目录下的 plugin-conf…」：skills dir comes from its own config |
| 35 | `PluginPanelRenderContractTest` | `test_knowledge_panel_matches_composite_dom_id` | 壳层广播的 panel 是 `knowledge__kb`，不能只认逻辑 id `kb`。 |
| 36 | `PluginPanelRenderContractTest` | `test_open_pane_broadcasts_panel_opened` | 覆盖「插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动」：open pane broadcasts panel opened |
| 37 | `PluginPanelRenderContractTest` | `test_open_plugin_panel_passes_its_plugin_name` | 覆盖「插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动」：open plugin panel passes its plugin name |
| 38 | `PluginPanelRenderContractTest` | `test_panel_has_a_refresh_button_on_the_subtitle` | 小标题右侧一个刷新：知识库目录是外部目录，不重开面板也要能取到新文件。 |
| 39 | `PluginPanelRenderContractTest` | `test_panels_render_on_the_event` | 覆盖「插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动」：panels render on the event |
| 40 | `PluginPanelRenderContractTest` | `test_refresh_handler_re_renders` | 覆盖「插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动」：refresh handler re renders |
| 41 | `PluginSourceContractTest` | `test_disposer_removes_the_source` | 覆盖「插件注入源的契约：注册进「知识库」段、每回合刷新、disposer 后消失」：disposer removes the source |
| 42 | `PluginSourceContractTest` | `test_plugin_sources_do_not_touch_the_kernel` | 插件来源只经注册表进出；内核不持有插件对象。 |
| 43 | `PluginSourceContractTest` | `test_segments_carry_their_own_name_and_prefix` | 段名与注入前缀由来源声明：内核不解释正文是什么。 |
| 44 | `PluginSourceContractTest` | `test_source_is_refreshed_every_turn` | 注入源每回合都重读：第 2 回合改内容，请求里立刻反映。 |
| 45 | `PluginSourceContractTest` | `test_source_text_lands_in_the_knowledge_block` | 覆盖「插件注入源的契约：注册进「知识库」段、每回合刷新、disposer 后消失」：source text lands in the knowledge block |
| 46 | `PluginSourceContractTest` | `test_two_sources_of_one_plugin_stay_separate` | 同一插件可以贡献多段：数量按位置对，不互相覆盖。 |
| 47 | `SkillsConfigSourceTest` | `test_plugin_dir_has_no_own_config` | 覆盖「Skills 设置只有工程 config.ini 一处来源（插件目录下没有同名配置）」：plugin dir has no own config |
| 48 | `SkillsConfigSourceTest` | `test_reader_reads_the_project_config` | 覆盖「Skills 设置只有工程 config.ini 一处来源（插件目录下没有同名配置）」：reader reads the project config |
| 49 | `SkillsConfigSourceTest` | `test_reader_takes_a_given_ini` | 覆盖「Skills 设置只有工程 config.ini 一处来源（插件目录下没有同名配置）」：reader takes a given ini |

## test_layout_min_width.py

共 2 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChatMinWidthTest` | `test_not_smaller_than_measured` | 覆盖「对话区最小宽度：两处同值 + 不小于实测下界」：not smaller than measured |
| 2 | `ChatMinWidthTest` | `test_two_places_agree` | 覆盖「对话区最小宽度：两处同值 + 不小于实测下界」：two places agree |

## test_mode_note.py

共 12 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ModeIsNotPersistedTest` | `test_mode_note_is_system_role` | 模式说明不是用户发言：控制台里它不该被当成用户消息。 |
| 2 | `ModeIsNotPersistedTest` | `test_no_event_carries_the_mode_note` | 覆盖「模式说明只存在于发给模型的那一份：不落记录、不发事件」：no event carries the mode note |
| 3 | `ModeTailShapeTest` | `test_empty_note_changes_nothing` | 覆盖「模式说明是请求的**最后一条**，且不改动别处」：empty note changes nothing |
| 4 | `ModeTailShapeTest` | `test_input_list_is_not_mutated` | 覆盖「模式说明是请求的**最后一条**，且不改动别处」：input list is not mutated |
| 5 | `ModeTailShapeTest` | `test_note_is_appended_last` | 覆盖「模式说明是请求的**最后一条**，且不改动别处」：note is appended last |
| 6 | `ModeTailShapeTest` | `test_note_works_after_multimodal_tail` | 最后一条是多模态数组时也必须能附加（不能拼坏它的结构）。 |
| 7 | `ModeTailShapeTest` | `test_switching_mode_changes_only_the_tail` | 覆盖「模式说明是请求的**最后一条**，且不改动别处」：switching mode changes only the tail |
| 8 | `SystemPromptHasNoModeTest` | `test_explicit_system_prompt_gets_no_note` | 调用方自己给的系统提示：模式怎么表达由他决定，不另加。 |
| 9 | `SystemPromptHasNoModeTest` | `test_mode_note_still_differs_per_mode` | 覆盖「模式段必须从系统提示词里出去」：mode note still differs per mode |
| 10 | `SystemPromptHasNoModeTest` | `test_resolved_system_prompt_has_no_mode` | 覆盖「模式段必须从系统提示词里出去」：resolved system prompt has no mode |
| 11 | `SystemPromptHasNoModeTest` | `test_split_helper_drops_the_mode_section` | 覆盖「模式段必须从系统提示词里出去」：split helper drops the mode section |
| 12 | `SystemPromptHasNoModeTest` | `test_switching_mode_keeps_system_prompt_byte_identical` | 覆盖「模式段必须从系统提示词里出去」：switching mode keeps system prompt byte identical |

## test_model_provider.py

共 24 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AvailableModelsWireTest` | `test_current_model_is_always_in_the_list` | `model` 必须在清单里，否则 UI 的白名单校验会丢弃它（顶栏永远"加载中"）。 |
| 2 | `AvailableModelsWireTest` | `test_health_lists_all_configured_models` | 覆盖「`/health` 的 `allowed_models` 必须给出**完整清单**」：health lists all configured models |
| 3 | `AvailableModelsWireTest` | `test_shell_health_also_lists_all_models` | 覆盖「`/health` 的 `allowed_models` 必须给出**完整清单**」：shell health also lists all models |
| 4 | `ImagesAlwaysReachTheWireTest` | `test_image_block_survives_into_the_payload` | 覆盖「图片一律原样发给模型 —— 不按模型名猜能力、不做降级剥图」：image block survives into the payload |
| 5 | `ImagesAlwaysReachTheWireTest` | `test_plain_text_message_is_untouched` | 覆盖「图片一律原样发给模型 —— 不按模型名猜能力、不做降级剥图」：plain text message is untouched |
| 6 | `ReasonNotReplayedTest` | `test_cut_drops_everything_before_it` | 覆盖「历史推理不回传：它必然未命中缓存，回传等于每轮多算几万 token」：cut drops everything before it |
| 7 | `ReasonNotReplayedTest` | `test_cut_none_keeps_everything` | 覆盖「历史推理不回传：它必然未命中缓存，回传等于每轮多算几万 token」：cut none keeps everything |
| 8 | `ReasonNotReplayedTest` | `test_original_messages_are_not_mutated` | 覆盖「历史推理不回传：它必然未命中缓存，回传等于每轮多算几万 token」：original messages are not mutated |
| 9 | `ReasonNotReplayedTest` | `test_provider_passes_the_boundary_and_defaults_to_stripping` | 覆盖「历史推理不回传：它必然未命中缓存，回传等于每轮多算几万 token」：provider passes the boundary and defaults to stripping |
| 10 | `ReasonNotReplayedTest` | `test_tool_calls_survive_the_cut` | 覆盖「历史推理不回传：它必然未命中缓存，回传等于每轮多算几万 token」：tool calls survive the cut |
| 11 | `RequestLevelModelTest` | `test_effort_still_reaches_the_wire` | 推理档位照常透传到请求载荷。 |
| 12 | `RequestLevelModelTest` | `test_empty_request_model_falls_back_to_instance_default` | 空串 = 不指定 ⇒ 用实例默认模型，既有调用方行为不变。 |
| 13 | `RequestLevelModelTest` | `test_local_model_check_is_per_requested_model` | 本地模型的判定同理：默认是云端、本次选本地时不能照旧下发推理档位。 |
| 14 | `RequestLevelModelTest` | `test_request_model_wins_over_instance_default` | 覆盖「A class whose instances are single test cases」：request model wins over instance default |
| 15 | `RequestLevelModelTest` | `test_whitespace_is_treated_as_unspecified` | 覆盖「A class whose instances are single test cases」：whitespace is treated as unspecified |
| 16 | `SessionModelSelectionTest` | `test_choice_survives_a_new_process` | 换一个 LiveState 实例（= 换进程）后选择仍在 —— 靠落盘，不靠内存。 |
| 17 | `SessionModelSelectionTest` | `test_empty_clears_the_choice` | 覆盖「会话级模型选择：选中即生效、可读回、**跨进程仍在**」：empty clears the choice |
| 18 | `SessionModelSelectionTest` | `test_read_only_is_never_used` | **只读**会话（`is_read_only` 的 cid）不落盘 —— 同 todo 的白名单纪律。 |
| 19 | `SessionModelSelectionTest` | `test_select_then_read_back` | 覆盖「会话级模型选择：选中即生效、可读回、**跨进程仍在**」：select then read back |
| 20 | `TurnStartAssemblyTest` | `test_model_module_marks_turn_start` | 覆盖「装配时把"本轮起点"标出来，provider 才有裁的依据」：model module marks turn start |
| 21 | `TurnStartAssemblyTest` | `test_port_default_keeps_everything` | 覆盖「装配时把"本轮起点"标出来，provider 才有裁的依据」：port default keeps everything |
| 22 | `UserFacingTextTest` | `test_500_and_503_name_the_model_server` | 覆盖「用户可见的文案不得混入内部术语」：500 and 503 name the model server |
| 23 | `UserFacingTextTest` | `test_deepseek_official_error_codes_are_mapped` | 与 https://api-docs.deepseek.com/quick_start/error_codes 七码对齐。 |
| 24 | `UserFacingTextTest` | `test_http_hints_are_user_facing_and_history_free` | 覆盖「用户可见的文案不得混入内部术语」：http hints are user facing and history free |

## test_plugin_contributions.py

共 30 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContributionRegistryTest` | `test_action_explicit_panel` | 覆盖「A class whose instances are single test cases」：action explicit panel |
| 2 | `ContributionRegistryTest` | `test_action_register_and_dispose` | 覆盖「A class whose instances are single test cases」：action register and dispose |
| 3 | `ContributionRegistryTest` | `test_boot_script_register_and_dispose` | 覆盖「A class whose instances are single test cases」：boot script register and dispose |
| 4 | `ContributionRegistryTest` | `test_boot_script_rejects_escape` | 覆盖「A class whose instances are single test cases」：boot script rejects escape |
| 5 | `ContributionRegistryTest` | `test_ctx_segment_style_register_and_dispose` | 覆盖「A class whose instances are single test cases」：ctx segment style register and dispose |
| 6 | `ContributionRegistryTest` | `test_drop_plugin_removes_every_kind` | 覆盖「A class whose instances are single test cases」：drop plugin removes every kind |
| 7 | `ContributionRegistryTest` | `test_panel_duplicate_rejected` | 覆盖「A class whose instances are single test cases」：panel duplicate rejected |
| 8 | `ContributionRegistryTest` | `test_panel_explicit_script_wins` | 覆盖「A class whose instances are single test cases」：panel explicit script wins |
| 9 | `ContributionRegistryTest` | `test_panel_register_and_dispose` | 覆盖「A class whose instances are single test cases」：panel register and dispose |
| 10 | `ContributionRegistryTest` | `test_panel_script_file_builds_asset_url` | 覆盖「A class whose instances are single test cases」：panel script file builds asset url |
| 11 | `ContributionRegistryTest` | `test_panel_script_file_rejects_escape` | 覆盖「A class whose instances are single test cases」：panel script file rejects escape |
| 12 | `ContributionRegistryTest` | `test_route_duplicate_rejected` | 覆盖「A class whose instances are single test cases」：route duplicate rejected |
| 13 | `ContributionRegistryTest` | `test_route_exact_match` | 覆盖「A class whose instances are single test cases」：route exact match |
| 14 | `ContributionRegistryTest` | `test_route_exact_wins_over_parameter` | 同时声明 `tasks` 与 `tasks/:sid` 时，`tasks` 不能被参数路由抢走。 |
| 15 | `ContributionRegistryTest` | `test_route_methods_supported` | 覆盖「A class whose instances are single test cases」：route methods supported |
| 16 | `ContributionRegistryTest` | `test_route_multi_segment_parameter` | 覆盖「A class whose instances are single test cases」：route multi segment parameter |
| 17 | `ContributionRegistryTest` | `test_route_path_parameter` | 覆盖「A class whose instances are single test cases」：route path parameter |
| 18 | `ContributionRegistryTest` | `test_route_rejects_bad_parameter_name` | 覆盖「A class whose instances are single test cases」：route rejects bad parameter name |
| 19 | `ContributionRegistryTest` | `test_route_rejects_bad_paths` | 覆盖「A class whose instances are single test cases」：route rejects bad paths |
| 20 | `ContributionRegistryTest` | `test_route_rejects_bad_plugin_and_method` | 覆盖「A class whose instances are single test cases」：route rejects bad plugin and method |
| 21 | `ContributionRegistryTest` | `test_route_segment_count_must_match` | 覆盖「A class whose instances are single test cases」：route segment count must match |
| 22 | `ExternalPluginRootAssetTest` | `test_plugin_asset_uses_tracked_root` | 覆盖「外部 path= 插件：资产根走 plugin_root，而不是 plugins_dir/<na…」：plugin asset uses tracked root |
| 23 | `PluginAssetUrlTest` | `test_asset_rel_parsing` | 覆盖「面板脚本资产路径的解析（壳层按它取文件）」：asset rel parsing |
| 24 | `PluginContextContributionTest` | `test_ctx_add_context_source_returns_disposer` | 覆盖「A class whose instances are single test cases」：ctx add context source returns disposer |
| 25 | `PluginContextContributionTest` | `test_ctx_namespaces_contributions_by_plugin` | 覆盖「A class whose instances are single test cases」：ctx namespaces contributions by plugin |
| 26 | `PluginContextContributionTest` | `test_data_dir_is_per_plugin_and_created` | 覆盖「A class whose instances are single test cases」：data dir is per plugin and created |
| 27 | `PluginContextContributionTest` | `test_data_dir_none_without_host_root` | 覆盖「A class whose instances are single test cases」：data dir none without host root |
| 28 | `PluginContextContributionTest` | `test_data_dir_path_is_absolute` | 覆盖「A class whose instances are single test cases」：data dir path is absolute |
| 29 | `PluginContextContributionTest` | `test_data_dir_sanitizes_plugin_name` | 覆盖「A class whose instances are single test cases」：data dir sanitizes plugin name |
| 30 | `PluginContextContributionTest` | `test_register_fail_after_add_panel_rolls_back` | register 在 add_panel 之后抛错 → 面板不得留在贡献表。 |

## test_plugin_http.py

共 18 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `PluginHttpTest` | `test_404_lists_available_endpoints` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：404 lists available endpoints |
| 2 | `PluginHttpTest` | `test_asset_rejects_escape` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：asset rejects escape |
| 3 | `PluginHttpTest` | `test_asset_rejects_non_whitelisted_type` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：asset rejects non whitelisted type |
| 4 | `PluginHttpTest` | `test_asset_served_as_javascript` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：asset served as javascript |
| 5 | `PluginHttpTest` | `test_checked_files_reach_the_context` | 经插件的勾选端点写进去的文件，必须真的变成注入上下文的系统消息。 |
| 6 | `PluginHttpTest` | `test_delete_removes` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：delete removes |
| 7 | `PluginHttpTest` | `test_get_list_and_path_parameter` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：get list and path parameter |
| 8 | `PluginHttpTest` | `test_handler_exception_does_not_kill_shell` | 插件端点抛错应变成 500，而不是打挂服务。 |
| 9 | `PluginHttpTest` | `test_panel_script_served_as_javascript` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：panel script served as javascript |
| 10 | `PluginHttpTest` | `test_panel_style_served_as_css` | 插件的样式表由插件自己提供、按面板声明送达。 |
| 11 | `PluginHttpTest` | `test_panels_and_actions_expose_script_url` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：panels and actions expose script url |
| 12 | `PluginHttpTest` | `test_parameter_route_does_not_capture_wrong_method` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：parameter route does not capture wrong method |
| 13 | `PluginHttpTest` | `test_plugin_panel_logic_lives_in_the_plugin` | 面板的脚本与样式都在插件目录里，壳层不掺和插件面板的渲染。 |
| 14 | `PluginHttpTest` | `test_plugin_style_source_declares_its_own_classes` | 样式确实在插件里：插件目录下有自己的样式表。 |
| 15 | `PluginHttpTest` | `test_post_creates_and_receives_body_and_query` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：post creates and receives body and query |
| 16 | `PluginHttpTest` | `test_put_updates_via_path_parameter` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：put updates via path parameter |
| 17 | `PluginHttpTest` | `test_shell_public_stylesheet_does_not_carry_plugin_styles` | 壳层的公共**样式表**里不该出现插件专属的样式规则。 |
| 18 | `PluginHttpTest` | `test_unknown_path_and_plugin_are_404` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：unknown path and plugin are 404 |

## test_plugins.py

共 23 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AppWiringTest` | `test_build_app_empty_whitelist_noop` | 覆盖「A class whose instances are single test cases」：build app empty whitelist noop |
| 2 | `AppWiringTest` | `test_build_app_loads_whitelisted_plugin` | 覆盖「A class whose instances are single test cases」：build app loads whitelisted plugin |
| 3 | `ConfigParseTest` | `test_get_plugins_parse` | 清单解析只做解析：`[plugin:<名字>]` 节，节里没有字段也合法。 |
| 4 | `ConfigParseTest` | `test_load_logs_source_integrity` | 装载时 stderr 须留下入口文件来源与完整性摘要。 |
| 5 | `ConfigParseTest` | `test_load_manifest_resolves_paths_and_reports_errors` | 装载方把 `path` 落到自己的插件根，并把配置错误变成报告。 |
| 6 | `ConfigParseTest` | `test_tree_only_rejects_external_path` | plugin_tree_only 打开时，清单里的树外 path 不得装载。 |
| 7 | `PluginGateTest` | `test_gate_rollback_on_register_error` | 覆盖「插件门控接缝：注册期可加检查扩展点（pre-gate）」：gate rollback on register error |
| 8 | `PluginGateTest` | `test_missing_pipeline_guards_and_post_observer` | 覆盖「插件门控接缝：注册期可加检查扩展点（pre-gate）」：missing pipeline guards and post observer |
| 9 | `PluginGateTest` | `test_pre_gate_blocks_then_unload_releases` | 覆盖「插件门控接缝：注册期可加检查扩展点（pre-gate）」：pre gate blocks then unload releases |
| 10 | `PluginHostTest` | `test_broken_import_isolated` | 覆盖「加载器行为（临时目录造插件）」：broken import isolated |
| 11 | `PluginHostTest` | `test_discover_filters` | 覆盖「加载器行为（临时目录造插件）」：discover filters |
| 12 | `PluginHostTest` | `test_discover_missing_dir` | 覆盖「加载器行为（临时目录造插件）」：discover missing dir |
| 13 | `PluginHostTest` | `test_load_enabled_filters_by_whitelist` | 覆盖「加载器行为（临时目录造插件）」：load enabled filters by whitelist |
| 14 | `PluginHostTest` | `test_missing_register_reports_error` | 覆盖「加载器行为（临时目录造插件）」：missing register reports error |
| 15 | `PluginHostTest` | `test_module_namespace_and_unload` | 覆盖「加载器行为（临时目录造插件）」：module namespace and unload |
| 16 | `PluginHostTest` | `test_plugin_tool_runs_via_pipeline` | 覆盖「加载器行为（临时目录造插件）」：plugin tool runs via pipeline |
| 17 | `PluginHostTest` | `test_register_raises_rolls_back` | 覆盖「加载器行为（临时目录造插件）」：register raises rolls back |
| 18 | `PluginHostTest` | `test_register_via_ctx_returns_none` | 覆盖「加载器行为（临时目录造插件）」：register via ctx returns none |
| 19 | `PluginHostTest` | `test_reload_skips_loaded` | 覆盖「加载器行为（临时目录造插件）」：reload skips loaded |
| 20 | `PluginHostTest` | `test_reports_accumulate` | 覆盖「加载器行为（临时目录造插件）」：reports accumulate |
| 21 | `PluginHostTest` | `test_returned_disposer_list_reverse_order` | 覆盖「加载器行为（临时目录造插件）」：returned disposer list reverse order |
| 22 | `PluginHostTest` | `test_unknown_name_reports_error` | 覆盖「加载器行为（临时目录造插件）」：unknown name reports error |
| 23 | `PluginHostTest` | `test_unload_all_idempotent` | 覆盖「加载器行为（临时目录造插件）」：unload all idempotent |

## test_protocol_contract.py

共 13 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AssetReusePolicyTest` | `test_media_and_markdown_rendering_is_frontend_side` | 后端载荷不含 HTML——工具结果与事件均为结构化数据。 |
| 2 | `AssetReusePolicyTest` | `test_media_embedding_uses_markdown_syntax` | 媒体以 Markdown 图片语法嵌入，非 base64 / HTML。 |
| 3 | `EventVocabularyTest` | `test_frontend_consumed_set_is_fully_mapped` | 映射表覆盖 FRONTEND_CONSUMED，无悬空类型。 |
| 4 | `EventVocabularyTest` | `test_ignored_source_types_are_explicitly_dropped` | 覆盖「词汇表与映射完整性」：ignored source types are explicitly dropped |
| 5 | `EventVocabularyTest` | `test_no_source_type_mapped_to_unknown_new_event` | 覆盖「词汇表与映射完整性」：no source type mapped to unknown new event |
| 6 | `KernelEventEmissionTest` | `test_core_structural_events_emitted` | 覆盖「内核真实产出的事件序列满足前端契约」：core structural events emitted |
| 7 | `KernelEventEmissionTest` | `test_event_envelope_is_type_plus_data` | 载荷为统一信封（type + data），前端 JSON.parse 后按 type 分派。 |
| 8 | `KernelEventEmissionTest` | `test_every_event_carries_conversation_id` | 单流多路复用依赖每个事件绑定 conversation_id。 |
| 9 | `KernelEventEmissionTest` | `test_tool_and_message_events_emitted` | 覆盖「内核真实产出的事件序列满足前端契约」：tool and message events emitted |
| 10 | `SessionIsolationContractTest` | `test_confirm_id_is_session_scoped` | 确认端点须按 cid 解析门控，不得落默认桶。 |
| 11 | `SessionIsolationContractTest` | `test_events_of_two_sessions_carry_distinct_cids` | 覆盖「多会话隔离与门控确认按 cid 解析（前端分派契约的后端前提）」：events of two sessions carry distinct cids |
| 12 | `UiStateContractTest` | `test_transient_ui_state_is_per_session` | 模式 / 折叠态归 live_state（按 cid），不落全局单例。 |
| 13 | `UiStateContractTest` | `test_usage_and_reasoning_are_provider_side` | 用量经 usage 事件；推理档位属 provider 请求参数。 |

## test_quality_pipeline.py

共 12 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `QualityPipelineTest` | `test_apply_patch_channel` | apply_patch：写之前解锁的另一份仍可提交；同一路径写之后才解锁的要先 review。 |
| 2 | `QualityPipelineTest` | `test_assistant_claim_fixed` | 无证据声称"已修复"会被拦下。 |
| 3 | `QualityPipelineTest` | `test_intent_evidence_gate` | debug 意图下无证据拒写；采证后放行。 |
| 4 | `QualityPipelineTest` | `test_intent_switch_resets_evidence` | 切换意图重置证据状态。 |
| 5 | `QualityPipelineTest` | `test_large_delete_flag` | 大删除检测置红灯。 |
| 6 | `QualityPipelineTest` | `test_large_diff_blocked` | 单次替换过大被拒、拆分后放行。 |
| 7 | `QualityPipelineTest` | `test_path_format_equivalent` | 反斜杠/正斜杠路径等价。 |
| 8 | `QualityPipelineTest` | `test_path_required` | 空路径被拒。 |
| 9 | `QualityPipelineTest` | `test_post_write_checks_json` | JSON 文件本地检查。 |
| 10 | `QualityPipelineTest` | `test_post_write_checks_py` | Python 文件本地检查：坏→红灯，修复→转绿。 |
| 11 | `QualityPipelineTest` | `test_report_structure` | 质量报告结构。 |
| 12 | `QualityPipelineTest` | `test_review_clears_large_delete_not_diag` | 大删除因 review 解除；诊断红灯不解除。 |

## test_readonly_tools.py

共 25 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `GlobFilesToolTest` | `test_entry_type_dir` | 目录过滤。 |
| 2 | `GlobFilesToolTest` | `test_invalid_entry_type_raises` | 非法 entry_type 抛 ValueError。 |
| 3 | `GlobFilesToolTest` | `test_limit_truncation` | limit 截断并标记。 |
| 4 | `GlobFilesToolTest` | `test_non_recursive` | 非递归仅当前层。 |
| 5 | `GlobFilesToolTest` | `test_path_not_dir_raises` | path 指向文件而非目录时抛 ValueError。 |
| 6 | `GlobFilesToolTest` | `test_recursive_default` | 默认递归；**/ 前缀剥除。 |
| 7 | `GrepFilesToolTest` | `test_binary_file_skipped` | 含 NUL 字节的文件被跳过（二进制嗅探）。 |
| 8 | `GrepFilesToolTest` | `test_limit_truncation` | limit 截断并标记。 |
| 9 | `GrepFilesToolTest` | `test_literal_hits` | 字面命中（含子目录；相对路径输出）。 |
| 10 | `GrepFilesToolTest` | `test_missing_pattern_raises` | 缺少 pattern 抛 ValueError。 |
| 11 | `GrepFilesToolTest` | `test_no_match` | 无命中：空结果不截断。 |
| 12 | `GrepFilesToolTest` | `test_or_separator` | 字面模式 \| 为 OR 分隔。 |
| 13 | `GrepFilesToolTest` | `test_path_not_dir_raises` | path 指向文件而非目录时抛 ValueError。 |
| 14 | `GrepFilesToolTest` | `test_regex_and_ignore_case` | 正则 + 忽略大小写（三个文件行首均命中：alpha / Alpha / alpha deep）。 |
| 15 | `ReadFileToolTest` | `test_empty_file` | 空文件：返回空内容与 0 行，不报错。 |
| 16 | `ReadFileToolTest` | `test_invalid_range_raises` | start 超出总行数时抛 ValueError。 |
| 17 | `ReadFileToolTest` | `test_max_chars_truncation` | max_chars 截断并标记。 |
| 18 | `ReadFileToolTest` | `test_missing_file_raises` | 文件不存在抛 FileNotFoundError（管道回灌）。 |
| 19 | `ReadFileToolTest` | `test_missing_path_raises` | 缺少 path 抛 ValueError。 |
| 20 | `ReadFileToolTest` | `test_range_clamped_to_end` | line_end 超界时 clamp 到文件尾。 |
| 21 | `ReadFileToolTest` | `test_read_full_text` | 全文读取。 |
| 22 | `ReadFileToolTest` | `test_read_line_range` | 行区间切片（1-based 闭区间）。 |
| 23 | `RegistryPipelineIntegrationTest` | `test_register_and_execute_via_pipeline` | 三工具注册进 ToolRegistry；经 ToolPipeline.execute 驱动 read_file。 |
| 24 | `RegistryPipelineIntegrationTest` | `test_tool_error_structured` | 工具异常：管道捕获为 ok=False 回灌。 |
| 25 | `RegistryPipelineIntegrationTest` | `test_unknown_tool_via_pipeline` | 未注册工具名：管道结构化回灌（不抛异常）。 |

## test_resume_bridge.py

共 6 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ResumeBridgeTest` | `test_host_holds_no_suspend_state` | 宿主**不保存挂起游标**：它的实例字段里没有"停在哪"这类信息。 |
| 2 | `ResumeBridgeTest` | `test_model_sees_the_result_on_the_next_pass` | 回灌后工具模块返回 `next`，宿主再跑一趟 → 模型才看得到结果。 |
| 3 | `ResumeBridgeTest` | `test_recovers_after_restart` | ③ **重启后仍能恢复**：丢掉宿主与全部模块对象，只从事实重建。 |
| 4 | `ResumeBridgeTest` | `test_result_is_not_delivered_twice` | 回灌不会重复：`tool_result` 已存在就不再发（同一调用只交一次）。 |
| 5 | `ResumeBridgeTest` | `test_resume_delivers_the_result_as_an_ordinary_tool_result` | ② 回灌就是**一次普通的 tool_result**，没有特殊规则。 |
| 6 | `ResumeBridgeTest` | `test_suspend_is_terminal_and_resume_is_a_new_run` | ① 挂起即终态；恢复是**新一轮宿主循环**，不是回到旧循环。 |

## test_run_registry.py

共 13 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `DrainWindowTest` | `test_drain_never_exposes_idle_window` | `end_run` 返回下一条时，占位必须**一次都没松过**。 |
| 2 | `DrainWindowTest` | `test_drain_then_release` | 队列空时才释放。 |
| 3 | `FileRunRegistryTest` | `test_broken_file_is_treated_as_not_running` | 坏文件不能让读取方崩，也不能把垃圾当成"在跑"。 |
| 4 | `FileRunRegistryTest` | `test_build_switches_implementation_by_directory` | 覆盖「落盘实现：跨实例可见 + 崩溃自愈」：build switches implementation by directory |
| 5 | `FileRunRegistryTest` | `test_stale_entry_self_heals` | 崩溃残留（进程被 kill，心跳停）：超过存活期后应被判为过期并清掉。 |
| 6 | `FileRunRegistryTest` | `test_state_is_visible_across_instances` | **核心诉求**：另一个实例（另一个 registry 对象）能看到"在跑"。 |
| 7 | `FileRunRegistryTest` | `test_touch_keeps_long_run_alive` | 长任务靠续心跳保活（否则 120 秒的 ping 会被误判成已结束）。 |
| 8 | `InMemoryRunRegistryTest` | `test_claim_release_renew` | 覆盖「纯内存实现：单实例语义」：claim release renew |
| 9 | `InMemoryRunRegistryTest` | `test_running_cids_snapshot` | 覆盖「纯内存实现：单实例语义」：running cids snapshot |
| 10 | `PidAliveTest` | `test_claim_then_running_is_true_in_this_process` | `claim()` 之后 `running()` 必须为 True（记录里写的是本进程 pid）。 |
| 11 | `PidAliveTest` | `test_invalid_pid_forms_are_dead` | 非法形态不抛异常，一律判死（None / 0 / 负数 / 非数字）。 |
| 12 | `PidAliveTest` | `test_live_pid_is_alive` | 当前进程的 pid 必须判活 —— 这是最直接的判据。 |
| 13 | `PidAliveTest` | `test_nonexistent_pid_is_dead` | 不存在的 pid 必须判死，否则过期记录永远不回收。 |

## test_session_context.py

共 22 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AppWiringTest` | `test_app_exposes_session_contexts` | 覆盖「装配接线（app.py 经注册表按会话解析门控）」：app exposes session contexts |
| 2 | `AppWiringTest` | `test_commit_rejected_when_confirm_lands_in_other_session` | 覆盖「装配接线（app.py 经注册表按会话解析门控）」：commit rejected when confirm lands in other session |
| 3 | `AppWiringTest` | `test_default_bucket_gate_is_canonical` | 覆盖「装配接线（app.py 经注册表按会话解析门控）」：default bucket gate is canonical |
| 4 | `AppWiringTest` | `test_engine_session_runs_on_its_own_gate` | 覆盖「装配接线（app.py 经注册表按会话解析门控）」：engine session runs on its own gate |
| 5 | `AppWiringTest` | `test_gate_for_is_per_conversation` | 覆盖「装配接线（app.py 经注册表按会话解析门控）」：gate for is per conversation |
| 6 | `AppWiringTest` | `test_preview_and_confirm_land_in_same_session_gate` | 覆盖「装配接线（app.py 经注册表按会话解析门控）」：preview and confirm land in same session gate |
| 7 | `ExclusiveGateTest` | `test_gates_are_distinct_instances` | 覆盖「门控每会话独占，跨会话不串扰」：gates are distinct instances |
| 8 | `ExclusiveGateTest` | `test_intent_and_red_light_not_shared` | 覆盖「门控每会话独占，跨会话不串扰」：intent and red light not shared |
| 9 | `ExclusiveGateTest` | `test_preview_snapshot_not_visible_across_sessions` | 覆盖「门控每会话独占，跨会话不串扰」：preview snapshot not visible across sessions |
| 10 | `ExclusiveGateTest` | `test_review_and_reread_state_not_shared` | 覆盖「门控每会话独占，跨会话不串扰」：review and reread state not shared |
| 11 | `IsolationKeyTest` | `test_bucket_key_rules` | 覆盖「会话隔离键」：bucket key rules |
| 12 | `IsolationKeyTest` | `test_empty_and_blank_share_default_bucket` | 覆盖「会话隔离键」：empty and blank share default bucket |
| 13 | `IsolationKeyTest` | `test_whitespace_normalised_but_case_preserved` | 覆盖「会话隔离键」：whitespace normalised but case preserved |
| 14 | `LazyLifecycleTest` | `test_gate_factory_called_once_per_conversation` | 覆盖「懒创建语义」：gate factory called once per conversation |
| 15 | `LazyLifecycleTest` | `test_get_is_readonly_no_side_effect` | 覆盖「懒创建语义」：get is readonly no side effect |
| 16 | `LazyLifecycleTest` | `test_no_context_until_resolved` | 覆盖「懒创建语义」：no context until resolved |
| 17 | `LevelSeparationTest` | `test_session_context_holds_only_session_level_state` | 覆盖「三级上下文不混放」：session context holds only session level state |
| 18 | `ResolutionPathTest` | `test_resolve_uses_current_session_scope` | 覆盖「单解析路径（core.session_scope）」：resolve uses current session scope |
| 19 | `SharedContainerTest` | `test_gate_factory_required` | 覆盖「live / inbox 为装配级共享容器」：gate factory required |
| 20 | `SharedContainerTest` | `test_live_and_inbox_shared_by_reference` | 覆盖「live / inbox 为装配级共享容器」：live and inbox shared by reference |
| 21 | `SharedContainerTest` | `test_shared_live_is_still_partitioned_by_cid` | 覆盖「live / inbox 为装配级共享容器」：shared live is still partitioned by cid |
| 22 | `ThreadSafetyTest` | `test_concurrent_first_use_yields_single_context` | 覆盖「线程安全」：concurrent first use yields single context |

## test_session_seq.py

共 23 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `SeqAssignmentTest` | `test_blank_lines_do_not_shift_positions` | 空行不占号：否则"下一个序号"会随空白漂移。 |
| 2 | `SeqAssignmentTest` | `test_conversation_id_is_not_persisted` | 会话 ID 由文件名承载，落盘行里不存；读回时按会话补进载荷。 |
| 3 | `SeqAssignmentTest` | `test_line_count_matches_next_seq` | `line_count` 就是"下一个可用序号"——`App._seq_next` 靠它播种。 |
| 4 | `SeqAssignmentTest` | `test_load_still_returns_plain_events` | `load()` 的返回形状**不变**（既有调用方与测试都按纯事件列表用）。 |
| 5 | `SeqAssignmentTest` | `test_seq_continues_across_appends` | 跨批连续：第二批接着第一批的号，不从头开始（约 500 行一批的 flush 依赖此）。 |
| 6 | `SeqAssignmentTest` | `test_seq_is_written_to_each_line` | 覆盖「写入即定位：序号按会话日志位置连续编」：seq is written to each line |
| 7 | `SeqAssignmentTest` | `test_seq_lives_in_payload_and_top_level_only` | 坐标在落盘行里只占顶层 `seq` 一处；**业务字段不被污染**。 |
| 8 | `SeqEmptyAndErrorTest` | `test_allocate_seq_survives_restart_without_collision` | 重启后重新构造 store 也不能从 0 重发号（否则与磁盘上的坐标撞号）。 |
| 9 | `SeqEmptyAndErrorTest` | `test_append_after_external_edit_does_not_collide` | 外部插入行后追加，新事件**不与既有坐标撞号**（全局分配器在存储层，不受文件行数影响）。 |
| 10 | `SeqEmptyAndErrorTest` | `test_append_empty_batch_writes_nothing` | 覆盖「A class whose instances are single test cases」：append empty batch writes nothing |
| 11 | `SeqEmptyAndErrorTest` | `test_coordinates_are_global_across_conversations` | 坐标**跨会话单调**：这是续传游标能只用一条流一个光标的前提。 |
| 12 | `SeqEmptyAndErrorTest` | `test_encrypted_mode_round_trips_seq` | 加密模式下 seq 也必须能读回（它写在明文里，再整体加密）。 |
| 13 | `SeqEmptyAndErrorTest` | `test_non_object_json_lines_do_not_produce_events` | 合法但非对象的行（`"foo"` / `123`）不产生事件，也不影响已有事件的坐标。 |
| 14 | `SeqEmptyAndErrorTest` | `test_tail_across_uses_one_cursor_for_all_conversations` | `tail_across`：一个游标跨会话续传，按坐标升序。 |
| 15 | `SeqEmptyAndErrorTest` | `test_unparseable_line_is_skipped` | 坏行跳过不渲染；**已有事件仍保留各自的落盘坐标**（坐标来自字段，不靠数位置）。 |
| 16 | `SeqMissingTest` | `test_appended_rows_use_global_seq` | 继续追加时新行用**全局坐标**，必然大于同文件里的补号。 |
| 17 | `SeqMissingTest` | `test_coordinates_stay_unique_and_monotonic` | 覆盖「缺坐标的行按**行位置**补号 —— 手写或外部工具产生的日志也要能读」：coordinates stay unique and monotonic |
| 18 | `SeqMissingTest` | `test_missing_seq_falls_back_to_line_position` | 没有坐标的行按行位置补号——足以让"刷新后全量回放"工作。 |
| 19 | `SeqTailTest` | `test_bad_conversation_id_raises_like_load` | 非法 cid 仍要拒绝（防路径穿越）——坐标功能不能成为绕过口。 |
| 20 | `SeqTailTest` | `test_missing_conversation_is_empty_not_error` | 覆盖「`tail_from` 是续传的读取原语」：missing conversation is empty not error |
| 21 | `SeqTailTest` | `test_tail_from_beyond_end_is_empty` | 覆盖「`tail_from` 是续传的读取原语」：tail from beyond end is empty |
| 22 | `SeqTailTest` | `test_tail_from_is_exclusive` | `seq > after` —— 严格大于，游标自身那帧不会重复补。 |
| 23 | `SeqTailTest` | `test_tail_from_negative_returns_everything` | 覆盖「`tail_from` 是续传的读取原语」：tail from negative returns everything |

## test_session_store.py

共 17 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ConversationIdTest` | `test_new_id_is_valid` | 覆盖「会话 ID 校验与生成」：new id is valid |
| 2 | `ConversationIdTest` | `test_valid_and_invalid` | 覆盖「会话 ID 校验与生成」：valid and invalid |
| 3 | `CrossProcessAppendTest` | `test_concurrent_appends_all_visible_after_load` | 读回来也要是 100 条 —— 行数够但解析丢片同样是数据丢失。 |
| 4 | `CrossProcessAppendTest` | `test_concurrent_appends_lose_nothing` | 4 进程 × 25 条并发写同一会话 → 100 条全在，且每行都是合法 JSON。 |
| 5 | `CryptoTest` | `test_concurrent_key_init` | 并发首用（多线程多实例）不双建密钥；各文件均可解密。 |
| 6 | `CryptoTest` | `test_key_reuse_across_instances` | 覆盖「加密 envelope / 模式 / 算法 / 密钥」：key reuse across instances |
| 7 | `CryptoTest` | `test_mixed_plain_and_encrypted` | 覆盖「加密 envelope / 模式 / 算法 / 密钥」：mixed plain and encrypted |
| 8 | `CryptoTest` | `test_roundtrip_local_encrypted` | 覆盖「加密 envelope / 模式 / 算法 / 密钥」：roundtrip local encrypted |
| 9 | `CryptoTest` | `test_tamper_detected` | 覆盖「加密 envelope / 模式 / 算法 / 密钥」：tamper detected |
| 10 | `CryptoTest` | `test_unknown_mode_falls_back_none` | 覆盖「加密 envelope / 模式 / 算法 / 密钥」：unknown mode falls back none |
| 11 | `LayoutTest` | `test_layout_single_file_per_session` | 覆盖「落盘布局」：layout single file per session |
| 12 | `WriteReadTest` | `test_append_empty_noop` | 覆盖「/ ：写入与读取语义」：append empty noop |
| 13 | `WriteReadTest` | `test_corrupt_line_skipped` | 覆盖「/ ：写入与读取语义」：corrupt line skipped |
| 14 | `WriteReadTest` | `test_invalid_cid_rejected` | 覆盖「/ ：写入与读取语义」：invalid cid rejected |
| 15 | `WriteReadTest` | `test_invalid_utf8_bytes_tolerated` | 非法 UTF-8 字节行跳过，其余事件照常读回。 |
| 16 | `WriteReadTest` | `test_missing_file_returns_empty` | 覆盖「/ ：写入与读取语义」：missing file returns empty |
| 17 | `WriteReadTest` | `test_roundtrip_plaintext` | 覆盖「/ ：写入与读取语义」：roundtrip plaintext |

## test_session_tools.py

共 17 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CreateListTest` | `test_create_alias_name_persona_tags` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：create alias name persona tags |
| 2 | `CreateListTest` | `test_create_batch_count_and_prefix` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：create batch count and prefix |
| 3 | `CreateListTest` | `test_create_single_and_meta` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：create single and meta |
| 4 | `CreateListTest` | `test_list_status_and_sort` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：list status and sort |
| 5 | `MeshCoreTest` | `test_end_run_drains_queue` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：end run drains queue |
| 6 | `MeshCoreTest` | `test_inbox_fifo_and_size` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：inbox fifo and size |
| 7 | `MeshCoreTest` | `test_persistence_roundtrip_and_tolerance` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：persistence roundtrip and tolerance |
| 8 | `MeshCoreTest` | `test_session_exists_registry_and_callback` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：session exists registry and callback |
| 9 | `MeshCoreTest` | `test_submit_paths` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：submit paths |
| 10 | `MeshCoreTest` | `test_upsert_get_list_roundtrip` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：upsert get list roundtrip |
| 11 | `MultisendBroadcastTest` | `test_broadcast_filters_and_envelope` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：broadcast filters and envelope |
| 12 | `MultisendBroadcastTest` | `test_multisend_partial_and_all_failed` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：multisend partial and all failed |
| 13 | `RunnerE2ETest` | `test_trigger_and_drain` | 覆盖「运行器端到端：触发执行、系统提示注入、队列抽干」：trigger and drain |
| 14 | `SendTest` | `test_send_custom_thread_and_channel` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：send custom thread and channel |
| 15 | `SendTest` | `test_send_queued_envelope_and_wrap` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：send queued envelope and wrap |
| 16 | `SendTest` | `test_send_sender_identity_from_registry` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：send sender identity from registry |
| 17 | `SendTest` | `test_send_validations` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：send validations |

## test_settings_panel.py

共 12 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ApplyHostTest` | `test_apply_updates_provider_and_limits` | 覆盖「A class whose instances are single test cases」：apply updates provider and limits |
| 2 | `IniEditTest` | `test_append_does_not_duplicate_a_section` | 覆盖「A class whose instances are single test cases」：append does not duplicate a section |
| 3 | `IniEditTest` | `test_remove_section_leaves_commented_header` | 覆盖「A class whose instances are single test cases」：remove section leaves commented header |
| 4 | `IniEditTest` | `test_update_keeps_comments_and_other_sections` | 覆盖「A class whose instances are single test cases」：update keeps comments and other sections |
| 5 | `PluginSettingsTest` | `test_enable_and_disable_edit_the_manifest` | 覆盖「A class whose instances are single test cases」：enable and disable edit the manifest |
| 6 | `PluginSettingsTest` | `test_missing_plugin_is_not_enabled` | 覆盖「A class whose instances are single test cases」：missing plugin is not enabled |
| 7 | `PluginSettingsTest` | `test_plugin_config_roundtrip_rejects_a_bad_name` | 覆盖「A class whose instances are single test cases」：plugin config roundtrip rejects a bad name |
| 8 | `PluginSettingsTest` | `test_unknown_route` | 覆盖「A class whose instances are single test cases」：unknown route |
| 9 | `SaveHostTest` | `test_catalog_echoes_the_key_from_the_file` | 覆盖「A class whose instances are single test cases」：catalog echoes the key from the file |
| 10 | `SaveHostTest` | `test_invalid_number_does_not_write` | 覆盖「A class whose instances are single test cases」：invalid number does not write |
| 11 | `SaveHostTest` | `test_save_rewrites_the_key_and_keeps_the_comment` | 覆盖「A class whose instances are single test cases」：save rewrites the key and keeps the comment |
| 12 | `SettingsPageAssetsTest` | `test_gear_and_settings_script_are_inlined` | 覆盖「A class whose instances are single test cases」：gear and settings script are inlined |

## test_source_snapshot.py

共 10 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChainPassDropsSnapshotTest` | `test_halted_pass_still_drops_the_snapshot` | 覆盖「一趟开始时收集，结束时丢掉；同一趟里多次装配只收集一次」：halted pass still drops the snapshot |
| 2 | `ChainPassDropsSnapshotTest` | `test_one_pass_collects_once_and_drops_when_the_pass_ends` | 覆盖「一趟开始时收集，结束时丢掉；同一趟里多次装配只收集一次」：one pass collects once and drops when the pass ends |
| 3 | `CollectOncePerPassTest` | `test_bump_forces_recollection` | 覆盖「注入源在一趟装配里只被收集一次」：bump forces recollection |
| 4 | `CollectOncePerPassTest` | `test_disposing_a_source_bumps_version` | 覆盖「注入源在一趟装配里只被收集一次」：disposing a source bumps version |
| 5 | `CollectOncePerPassTest` | `test_explicit_refresh_always_recollects` | 覆盖「注入源在一趟装配里只被收集一次」：explicit refresh always recollects |
| 6 | `CollectOncePerPassTest` | `test_pass_builds_at_start_and_drops_at_end` | 覆盖「注入源在一趟装配里只被收集一次」：pass builds at start and drops at end |
| 7 | `CollectOncePerPassTest` | `test_registering_a_source_bumps_by_itself` | 覆盖「注入源在一趟装配里只被收集一次」：registering a source bumps by itself |
| 8 | `CollectOncePerPassTest` | `test_repeated_assembly_shares_one_snapshot` | 覆盖「注入源在一趟装配里只被收集一次」：repeated assembly shares one snapshot |
| 9 | `SegmentsStayAlignedTest` | `test_alignment_after_repeated_assembly` | 覆盖「段表与数量表必须逐条对齐（错位会让浮层显示别人的数字）」：alignment after repeated assembly |
| 10 | `SegmentsStayAlignedTest` | `test_repeated_assembly_does_not_grow_rows` | 覆盖「段表与数量表必须逐条对齐（错位会让浮层显示别人的数字）」：repeated assembly does not grow rows |

## test_task_tools.py

共 27 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ApprovalConfirmTest` | `test_rejects_blank_or_forged_id` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：rejects blank or forged id |
| 2 | `ApprovalConfirmTest` | `test_suspend_is_remembered_on_the_session` | 挂起信封进会话上下文，回合结束只清待审批，不清已签发的通行证。 |
| 3 | `ApprovalConfirmTest` | `test_suspends_with_approval_envelope` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：suspends with approval envelope |
| 4 | `ModeGateTest` | `test_execute_requires_todo` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：execute requires todo |
| 5 | `ModeGateTest` | `test_plan_blocks_commands` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：plan blocks commands |
| 6 | `ModeGateTest` | `test_plan_blocks_commit` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：plan blocks commit |
| 7 | `RunTypeTest` | `test_auto_clears_override` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：auto clears override |
| 8 | `RunTypeTest` | `test_invalid_value_falls_back_to_query` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：invalid value falls back to query |
| 9 | `RunTypeTest` | `test_query_default_auto` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：query default auto |
| 10 | `RunTypeTest` | `test_requires_session_scope` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：requires session scope |
| 11 | `RunTypeTest` | `test_switch_and_query` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：switch and query |
| 12 | `SessionScopeTest` | `test_scope_set_and_restored` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：scope set and restored |
| 13 | `TaskSleepAutonomousTest` | `test_goal_shapes` | 目标工具：建 / 查 / 改 / 暂停 / 恢复 / 达成 / 删，以及触发文案的语义。 |
| 14 | `TaskSleepAutonomousTest` | `test_sleep_bounds` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：sleep bounds |
| 15 | `TaskSleepAutonomousTest` | `test_sleep_ok_and_clamp` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：sleep ok and clamp |
| 16 | `TodoListTest` | `test_add_remove_replace` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：add remove replace |
| 17 | `TodoListTest` | `test_check_uncheck_and_bounds` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：check uncheck and bounds |
| 18 | `TodoListTest` | `test_create_and_shape` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：create and shape |
| 19 | `TodoListTest` | `test_create_replaces_and_validates` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：create replaces and validates |
| 20 | `TodoListTest` | `test_no_list_unknown_and_query_close` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：no list unknown and query close |
| 21 | `TodoListTest` | `test_persistence_reload` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：persistence reload |
| 22 | `TodoListTest` | `test_persistence_tolerance_and_cid_defense` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：persistence tolerance and cid defense |
| 23 | `UserConfirmTest` | `test_confirm_roundtrip` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：confirm roundtrip |
| 24 | `UserConfirmTest` | `test_envelope_still_works_without_tty` | 无 TTY 时不给 interactive，必须照常返回待确认信封（宿主 UI 负责交互）。 |
| 25 | `UserConfirmTest` | `test_interactive_without_tty_gives_actionable_error` | 无 TTY 时 interactive 必须给出可照做的指引，而不是"未读取到用户输入"。 |
| 26 | `UserConfirmTest` | `test_pending_envelope` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：pending envelope |
| 27 | `UserConfirmTest` | `test_validations` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：validations |

## test_todo_context_prompt.py

共 19 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextLayoutTest` | `test_budget_is_used_for_pct` | 给了预算就按预算算百分比——这样上下文条才反映"还剩多少空间"。 |
| 2 | `ContextLayoutTest` | `test_budget_never_below_used` | 预算小于已用时按已用算——各段之和不得超过 100%。 |
| 3 | `ContextLayoutTest` | `test_chunks_plus_remainder` | 覆盖「上下文分段」：chunks plus remainder |
| 4 | `ContextLayoutTest` | `test_counts_present` | 覆盖「上下文分段」：counts present |
| 5 | `ContextLayoutTest` | `test_labels_are_chinese_names` | 覆盖「上下文分段」：labels are chinese names |
| 6 | `ContextLayoutTest` | `test_pct_sums_to_100` | 覆盖「上下文分段」：pct sums to 100 |
| 7 | `SystemPromptTest` | `test_blank_explicit_falls_back` | 覆盖「基础系统提示词」：blank explicit falls back |
| 8 | `SystemPromptTest` | `test_coding_and_tooling_disciplines_present` | 系统提示必须含「改前必读」/「大文件局部读」/「失败处理」等纪律条目。 |
| 9 | `SystemPromptTest` | `test_explicit_prompt_wins` | 覆盖「基础系统提示词」：explicit prompt wins |
| 10 | `SystemPromptTest` | `test_mode_section_differs` | 覆盖「基础系统提示词」：mode section differs |
| 11 | `SystemPromptTest` | `test_non_empty_by_default` | 系统提示不得为空——空提示让模型只凭 schema 猜纪律。 |
| 12 | `SystemPromptTest` | `test_preview_write_tools_line_tracks_registry` | 预览写类名单随 registry 增减，不手写固定串。 |
| 13 | `SystemPromptTest` | `test_tool_summary_propagates_registry_errors` | 覆盖「基础系统提示词」：tool summary propagates registry errors |
| 14 | `SystemPromptTest` | `test_tool_summary_shape` | 覆盖「基础系统提示词」：tool summary shape |
| 15 | `SystemPromptTest` | `test_unknown_mode_falls_back_to_auto` | 覆盖「基础系统提示词」：unknown mode falls back to auto |
| 16 | `TodoProgressTest` | `test_check_then_all_done` | 覆盖「清单进度字段」：check then all done |
| 17 | `TodoProgressTest` | `test_close_has_no_items` | 关闭清单只回 `{close: True}`——前端据此隐藏并清未读。 |
| 18 | `TodoProgressTest` | `test_create_reports_progress` | 覆盖「清单进度字段」：create reports progress |
| 19 | `TodoProgressTest` | `test_uncheck_revokes_all_done` | 覆盖「清单进度字段」：uncheck revokes all done |

## test_tool_registry.py

共 17 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ToolDisplayDeclarationTest` | `test_defaults_are_empty` | 覆盖「工具自带展示信息（label / icon）：界面不维护工具名表」：defaults are empty |
| 2 | `ToolDisplayDeclarationTest` | `test_display_list_shape` | 覆盖「工具自带展示信息（label / icon）：界面不维护工具名表」：display list shape |
| 3 | `ToolDisplayDeclarationTest` | `test_plugin_carries_display_fields` | 覆盖「工具自带展示信息（label / icon）：界面不维护工具名表」：plugin carries display fields |
| 4 | `ToolRegistryTest` | `test_builtin_echo_integrates` | 内置 echo 样板与注册表集成。 |
| 5 | `ToolRegistryTest` | `test_dispose_all_clears_everything` | dispose_all 清空全部；旧句柄仍幂等。 |
| 6 | `ToolRegistryTest` | `test_dispose_all_empty_ok` | 无注册时 dispose_all 无操作。 |
| 7 | `ToolRegistryTest` | `test_disposer_idempotent_and_reregister` | disposer 幂等；注销后同名可再注册。 |
| 8 | `ToolRegistryTest` | `test_disposer_removes_plugin` | disposer 调用后插件被注销。 |
| 9 | `ToolRegistryTest` | `test_execute_contract` | execute 返回裸值（管道负责包装信封）。 |
| 10 | `ToolRegistryTest` | `test_get_missing_returns_none` | 未注册解析返回 None（管道转为"未知工具"回灌）。 |
| 11 | `ToolRegistryTest` | `test_parallel_safe_predeclared` | parallel_safe 可声明并随声明导出。 |
| 12 | `ToolRegistryTest` | `test_register_and_get` | 注册后可解析回同一实例。 |
| 13 | `ToolRegistryTest` | `test_register_duplicate_rejected` | 重复注册被拒。 |
| 14 | `ToolRegistryTest` | `test_register_empty_name_rejected` | 空名称注册被拒。 |
| 15 | `ToolRegistryTest` | `test_register_non_callable_execute_rejected` | execute 不可调用注册被拒。 |
| 16 | `ToolRegistryTest` | `test_register_non_dict_parameters_rejected` | parameters 非 dict 注册被拒。 |
| 17 | `ToolRegistryTest` | `test_schemas_sorted_and_snapshot` | 声明导出：按名称排序、含 parallel_safe、快照与实例解耦。 |

## test_tool_session_gate.py

共 1 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ToolSessionGateTest` | `test_execute_fills_session_gate` | 覆盖「经 ToolPort 执行时，工具所见 gate 与会话注册表一致」：execute fills session gate |

## test_usage_metrics.py

共 7 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `UiReadsTheOfficialFieldsTest` | `test_accumulators_only_add_official_values` | 覆盖「界面读的字段名与契约一致；命中率只用官方两个值算」：accumulators only add official values |
| 2 | `UiReadsTheOfficialFieldsTest` | `test_hit_rate_uses_only_the_official_pair` | 覆盖「界面读的字段名与契约一致；命中率只用官方两个值算」：hit rate uses only the official pair |
| 3 | `UiReadsTheOfficialFieldsTest` | `test_ui_reads_the_official_names` | 覆盖「界面读的字段名与契约一致；命中率只用官方两个值算」：ui reads the official names |
| 4 | `UsageFieldsAreOfficialTest` | `test_contract_lists_the_official_fields` | 覆盖「官方字段一路原样：事件 → 转发 → 界面读取」：contract lists the official fields |
| 5 | `UsageFieldsAreOfficialTest` | `test_outbound_forwards_them_unchanged` | 覆盖「官方字段一路原样：事件 → 转发 → 界面读取」：outbound forwards them unchanged |
| 6 | `UsageFieldsAreOfficialTest` | `test_unknown_extra_fields_are_dropped_not_invented` | 覆盖「官方字段一路原样：事件 → 转发 → 界面读取」：unknown extra fields are dropped not invented |
| 7 | `WindowComesFromKernelTest` | `test_pipeline_reports_the_configured_window` | 覆盖「用量环分母 = 内核给的模型窗口，不是写死的常量」：pipeline reports the configured window |

## test_version_stamp.py

共 4 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `VersionStampTest` | `test_frontend_has_two_unescaped_stamp_regexes` | 前端两处取时刻（建标题 / 补文件段）正则同形，且不得写成 `\\d`。 |
| 2 | `VersionStampTest` | `test_frontend_regex_matches_backend_directory_names` | 后端现造的版本目录名必须被前端正则命中，且取到的是**时间**那一段。 |
| 3 | `VersionStampTest` | `test_node_agrees_with_python` | 把 JS 那段真跑一遍，结果与 Python 侧一致（防止只改了注释没改代码）。 |
| 4 | `VersionStampTest` | `test_unparseable_ids_are_empty` | 覆盖「A class whose instances are single test cases」：unparseable ids are empty |

## test_web_frontend.py

共 5 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChannelBackpressureTest` | `test_close_returns_none_and_stops_accepting` | 覆盖「SSE 连接队列、心跳、慢消费者、关闭语义」：close returns none and stops accepting |
| 2 | `ChannelBackpressureTest` | `test_concurrent_push_and_pop_is_safe` | 覆盖「SSE 连接队列、心跳、慢消费者、关闭语义」：concurrent push and pop is safe |
| 3 | `ChannelBackpressureTest` | `test_frames_arrive_in_order` | 覆盖「SSE 连接队列、心跳、慢消费者、关闭语义」：frames arrive in order |
| 4 | `ChannelBackpressureTest` | `test_idle_returns_heartbeat_not_none` | 覆盖「SSE 连接队列、心跳、慢消费者、关闭语义」：idle returns heartbeat not none |
| 5 | `ChannelBackpressureTest` | `test_slow_consumer_drops_oldest_keeps_latest` | 队列满时丢最旧一帧——保证流不断且最终状态可见。 |

## test_web_shell.py

共 50 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ConcurrencyTest` | `test_concurrent_send_returns_409` | 覆盖「同会话并发 409；停止请求可下发」：concurrent send returns 409 |
| 2 | `ConcurrencyTest` | `test_stop_cancels_a_running_turn` | 停止是真取消：经 SessionRunner 的停止检查，让内核在检查点停下。 |
| 3 | `ConcurrencyTest` | `test_stop_endpoint_shape` | 覆盖「同会话并发 409；停止请求可下发」：stop endpoint shape |
| 4 | `DateGroupTest` | `test_groups_by_natural_day` | 覆盖「会话日期分组」：groups by natural day |
| 5 | `DateGroupTest` | `test_older_is_grouped_by_date` | 覆盖「会话日期分组」：older is grouped by date |
| 6 | `DirBrowseDriveRootTest` | `test_drive_root_parent_is_drives_layer` | 覆盖「可见根是**盘根**时（默认情形），相对路径不能被钉死在盘根」：drive root parent is drives layer |
| 7 | `DirBrowseDriveRootTest` | `test_relative_path_prefers_concrete_workspace_root` | 覆盖「可见根是**盘根**时（默认情形），相对路径不能被钉死在盘根」：relative path prefers concrete workspace root |
| 8 | `DirBrowseQueryTest` | `test_dir_browse_single_char_path_not_truncated` | `_query()` 必须返回整串：路由若用 `[0]` 取首字符，值会被截断。 |
| 9 | `DirBrowseQueryTest` | `test_ui_state_roundtrip` | 覆盖「路径查询串按整串解析，不按首字符」：ui state roundtrip |
| 10 | `EndpointTest` | `test_health_endpoint` | 覆盖「端点清单可达性与显著错误码」：health endpoint |
| 11 | `EndpointTest` | `test_media_endpoint_guards_root` | 覆盖「端点清单可达性与显著错误码」：media endpoint guards root |
| 12 | `EndpointTest` | `test_media_missing_file_404` | 覆盖「端点清单可达性与显著错误码」：media missing file 404 |
| 13 | `EndpointTest` | `test_pages_and_assets_served` | 覆盖「端点清单可达性与显著错误码」：pages and assets served |
| 14 | `EndpointTest` | `test_send_rejects_bad_input` | 覆盖「端点清单可达性与显著错误码」：send rejects bad input |
| 15 | `EndpointTest` | `test_unknown_path_404` | 覆盖「端点清单可达性与显著错误码」：unknown path 404 |
| 16 | `FileViewerContractTest` | `test_absolute_path_inside_root_is_accepted` | 工具参数常给绝对路径；落在 fs_root 内必须能直接打开。 |
| 17 | `FileViewerContractTest` | `test_absolute_path_outside_root_is_forbidden` | 覆盖「文件读取端点的路径解析与越界边界」：absolute path outside root is forbidden |
| 18 | `FileViewerContractTest` | `test_binary_is_reported_not_dumped` | 覆盖「文件读取端点的路径解析与越界边界」：binary is reported not dumped |
| 19 | `FileViewerContractTest` | `test_list_absolute_path_inside_root` | 覆盖「文件读取端点的路径解析与越界边界」：list absolute path inside root |
| 20 | `FileViewerContractTest` | `test_list_outside_root_is_forbidden` | 覆盖「文件读取端点的路径解析与越界边界」：list outside root is forbidden |
| 21 | `FileViewerContractTest` | `test_list_returns_entries_with_rel_and_type` | 覆盖「文件读取端点的路径解析与越界边界」：list returns entries with rel and type |
| 22 | `FileViewerContractTest` | `test_missing_file_inside_root_is_404_not_403` | 不存在的文件与越界必须分开报告：预览期未落盘的文件是 404，不是越权。 |
| 23 | `FileViewerContractTest` | `test_relative_path_reads_text` | 覆盖「文件读取端点的路径解析与越界边界」：relative path reads text |
| 24 | `FileViewerContractTest` | `test_traversal_cannot_escape_roots` | 穿越语义：不允许**逃出**可见根（不是"禁止 `..`"）。 |
| 25 | `MultiRootFileViewerTest` | `test_absolute_path_in_first_root` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：absolute path in first root |
| 26 | `MultiRootFileViewerTest` | `test_absolute_path_in_second_root` | 第二个根同样可达——单根实现会把它判成越界。 |
| 27 | `MultiRootFileViewerTest` | `test_list_reports_rel_against_matched_root` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：list reports rel against matched root |
| 28 | `MultiRootFileViewerTest` | `test_missing_in_a_root_is_404_not_403` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：missing in a root is 404 not 403 |
| 29 | `MultiRootFileViewerTest` | `test_outside_all_roots_is_forbidden` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：outside all roots is forbidden |
| 30 | `MultiRootFileViewerTest` | `test_relative_path_resolves_against_each_root` | 相对路径逐个根试：命中哪个根就用哪个。 |
| 31 | `MultiRootFileViewerTest` | `test_roots_are_resolved_and_deduplicated_by_normalize` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：roots are resolved and deduplicated by normalize |
| 32 | `SseContractTest` | `test_derived_title_truncates_and_flattens` | 覆盖「/ ：单流多路复用与事件信封」：derived title truncates and flattens |
| 33 | `SseContractTest` | `test_dir_browse_drives_layer` | `path=_drives_` 返回「计算机」层。 |
| 34 | `SseContractTest` | `test_dir_browse_item_shape_and_ordering` | 条目形状 {name,type,ext,path}；目录排前。 |
| 35 | `SseContractTest` | `test_dir_browse_missing_path_falls_back` | 访问不到的路径回落（不报错）——补全不能因为一个坏路径卡死。 |
| 36 | `SseContractTest` | `test_dir_browse_relative_path_uses_workspace_base` | 相对路径应基于可见根解析，且**不得落到盘根**。 |
| 37 | `SseContractTest` | `test_dir_browse_root_parent_is_drives` | 盘符根的 parent 是 `_drives_`，可从盘根回到计算机层。 |
| 38 | `SseContractTest` | `test_every_frame_carries_conversation_id` | 覆盖「/ ：单流多路复用与事件信封」：every frame carries conversation id |
| 39 | `SseContractTest` | `test_health_reports_model_for_header` | `/health` 须给出 model / allowed_models（顶栏模型名与模型菜单）。 |
| 40 | `SseContractTest` | `test_history_and_sessions_endpoints` | 覆盖「/ ：单流多路复用与事件信封」：history and sessions endpoints |
| 41 | `SseContractTest` | `test_reasoning_effort_is_per_conversation` | 会话级档位不串会话：改一个不影响另一个（另一个回全局默认）。 |
| 42 | `SseContractTest` | `test_reasoning_effort_rejects_invalid` | 非法档位拒设且**保留原值**；缺 cid 报错。 |
| 43 | `SseContractTest` | `test_reasoning_effort_roundtrip` | 推理档位 GET/PUT 往返。 |
| 44 | `SseContractTest` | `test_sessions_carry_date_group` | 会话名录须带 date_group（会话菜单按它插分组标题）。 |
| 45 | `SseContractTest` | `test_sessions_carry_derived_title_not_raw_id` | 会话名录须带派生标题（首条用户输入），否则侧栏只能显示裸 UUID。 |
| 46 | `SseContractTest` | `test_sessions_sorted_by_recent_activity` | 覆盖「/ ：单流多路复用与事件信封」：sessions sorted by recent activity |
| 47 | `SseContractTest` | `test_turn_events_reach_the_stream` | 覆盖「/ ：单流多路复用与事件信封」：turn events reach the stream |
| 48 | `SseContractTest` | `test_two_sessions_do_not_cross` | 覆盖「/ ：单流多路复用与事件信封」：two sessions do not cross |
| 49 | `WriteGateOverWebTest` | `test_confirm_is_session_scoped` | 覆盖「写盘门控闭环经 Web 层 —— **三步写盘**（预览 → review 解锁 → 提交落盘）」：confirm is session scoped |
| 50 | `WriteGateOverWebTest` | `test_unconfirmed_commit_rejected_then_review_unlocks` | 覆盖「写盘门控闭环经 Web 层 —— **三步写盘**（预览 → review 解锁 → 提交落盘）」：unconfirmed commit rejected then review unlocks |

## test_web_ui_config.py

共 4 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `WebUiConfigTest` | `test_blank_value_keeps_the_default` | 覆盖「A class whose instances are single test cases」：blank value keeps the default |
| 2 | `WebUiConfigTest` | `test_classic_page_wires_the_placeholder` | 配置注入与工具卡拆分：占位符、开关属性、工具视图脚本进包。 |
| 3 | `WebUiConfigTest` | `test_missing_file_defaults_items_on_steps_off` | 覆盖「A class whose instances are single test cases」：missing file defaults items on steps off |
| 4 | `WebUiConfigTest` | `test_only_digit_one_turns_a_flag_on` | 覆盖「A class whose instances are single test cases」：only digit one turns a flag on |

## test_write_gate.py

共 16 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `WriteGateTest` | `test_already_reviewed_previews_commit_together` | 两份预览都先解锁，再连续提交：第二份不被第一份落盘挡下。 |
| 2 | `WriteGateTest` | `test_commit_consumes_id_once` | 提交凭 ID 且一次性：同一 ID 二次提交被拒。 |
| 3 | `WriteGateTest` | `test_commit_creates_parent_dirs` | 提交：目标父目录不存在时自动创建。 |
| 4 | `WriteGateTest` | `test_commit_missing_id_rejected` | 缺 confirm_id：提交被拒。 |
| 5 | `WriteGateTest` | `test_commit_without_confirm_rejected` | 预览后未确认即提交：被拒；确认后凭同一 ID 提交成功。 |
| 6 | `WriteGateTest` | `test_commit_without_preview_rejected` | 无预览直提交（伪造 ID）：被拒，文件不落盘；不产生记账。 |
| 7 | `WriteGateTest` | `test_consecutive_reviews_then_consecutive_commits` | 两个不同文件先各自 review_conclusion，再连续 commit_write，两份都落盘。 |
| 8 | `WriteGateTest` | `test_cross_file_review_gate` | 写后未 review 跨文件：被拒；review_done 后放行。 |
| 9 | `WriteGateTest` | `test_diagnose_red_and_recovery` | 写坏语法 → 红灯回灌；修复后转绿。 |
| 10 | `WriteGateTest` | `test_full_four_steps` | 预览 → 确认 → 凭 ID 提交 → 重读：真实文件走通完整四步。 |
| 11 | `WriteGateTest` | `test_large_overwrite_flags_red` | 提交覆盖既有大文件（大幅缩水）：大删除红灯 + 报告回灌 red。 |
| 12 | `WriteGateTest` | `test_preview_does_not_write` | 预览：不落盘，返回字节数、存在标记与 confirm_id。 |
| 13 | `WriteGateTest` | `test_red_light_limits_scope` | 红灯未清时，改其他文件被拒（限面）。 |
| 14 | `WriteGateTest` | `test_reread_required_before_second_edit` | 写后未重读前再次提交：被拒；重读后放行。 |
| 15 | `WriteGateTest` | `test_write_missing_content_rejected` | 缺 content：工具报错经管道结构化回灌。 |
| 16 | `WriteGateTest` | `test_write_missing_path_rejected` | 缺 path：工具报错经管道结构化回灌。 |

## test_write_path_keys_lifecycle.py

共 4 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `WritePathKeysLifecycleTest` | `test_drop_plugin_removes_skill_manage_from_registry` | 覆盖「A class whose instances are single test cases」：drop plugin removes skill manage from registry |
| 2 | `WritePathKeysLifecycleTest` | `test_gate_lookup_tracks_registry` | 覆盖「A class whose instances are single test cases」：gate lookup tracks registry |
| 3 | `WritePathKeysLifecycleTest` | `test_plugin_context_rollback_drops_tool_from_registry` | 覆盖「A class whose instances are single test cases」：plugin context rollback drops tool from registry |
| 4 | `WritePathKeysLifecycleTest` | `test_resolve_uses_declared_keys_not_default_path` | 覆盖「A class whose instances are single test cases」：resolve uses declared keys not default path |

## test_write_path_tools.py

共 30 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `WritePathToolsTest` | `test_backup_mode_reflects_the_replace_mode` | `replace_in_file` 的 mode 要区分字面替换与行区间替换，不能一律写成工具名。 |
| 2 | `WritePathToolsTest` | `test_backup_of_a_patch_records_the_patch_diff` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：backup of a patch records the patch diff |
| 3 | `WritePathToolsTest` | `test_backup_records_what_the_write_changed` | 写盘触发的备份要记下「这一版改了什么」。 |
| 4 | `WritePathToolsTest` | `test_cross_file_review_block` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：cross file review block |
| 5 | `WritePathToolsTest` | `test_delete_file_dir_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：delete file dir rejected |
| 6 | `WritePathToolsTest` | `test_delete_file_missing_is_already_absent` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：delete file missing is already absent |
| 7 | `WritePathToolsTest` | `test_delete_file_to_recycle` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：delete file to recycle |
| 8 | `WritePathToolsTest` | `test_file_ops_copy_and_overwrite_refused` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：file ops copy and overwrite refused |
| 9 | `WritePathToolsTest` | `test_file_ops_source_missing_is_not_already_applied` | copy/move/rename：源不在一律 source_missing（ok=false），不得因目标已在改判。 |
| 10 | `WritePathToolsTest` | `test_file_undo_requires_path` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：file undo requires path |
| 11 | `WritePathToolsTest` | `test_file_undo_restore_and_list` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：file undo restore and list |
| 12 | `WritePathToolsTest` | `test_patch_commit_applies` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch commit applies |
| 13 | `WritePathToolsTest` | `test_patch_context_mismatch_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch context mismatch rejected |
| 14 | `WritePathToolsTest` | `test_patch_missing_target_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch missing target rejected |
| 15 | `WritePathToolsTest` | `test_patch_outside_root_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch outside root rejected |
| 16 | `WritePathToolsTest` | `test_patch_preview_stats_no_write` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch preview stats no write |
| 17 | `WritePathToolsTest` | `test_patch_second_needs_review` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch second needs review |
| 18 | `WritePathToolsTest` | `test_read_write_slice_and_backup` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：read write slice and backup |
| 19 | `WritePathToolsTest` | `test_replace_commit_applies` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace commit applies |
| 20 | `WritePathToolsTest` | `test_replace_expected_mismatch_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace expected mismatch rejected |
| 21 | `WritePathToolsTest` | `test_replace_line_mode` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace line mode |
| 22 | `WritePathToolsTest` | `test_replace_old_absent_never_already_applied` | old 字面未命中一律 old_text_not_found；不得因 new 已在或删除语义改判。 |
| 23 | `WritePathToolsTest` | `test_replace_old_text_not_found` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace old text not found |
| 24 | `WritePathToolsTest` | `test_replace_preview_no_write` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace preview no write |
| 25 | `WritePathToolsTest` | `test_replace_same_text_already_applied` | 同值替换不得发空 diff 的 confirm_id。 |
| 26 | `WritePathToolsTest` | `test_replace_stale_file_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace stale file rejected |
| 27 | `WritePathToolsTest` | `test_reread_block_before_second_write` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：reread block before second write |
| 28 | `WritePathToolsTest` | `test_undo_backup_records_what_the_rollback_undid` | 回滚前的留档也要记 diff —— 否则"回滚"这一动作本身无迹可查。 |
| 29 | `WritePathToolsTest` | `test_write_file_same_content_already_applied` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：write file same content already applied |
| 30 | `WritePathToolsTest` | `test_write_file_trailing_newline_only_shows_diff` | 仅差结尾换行时预览不得空 diff（splitlines 曾吃掉 \n）。 |

