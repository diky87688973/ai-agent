# 单元测试用例清单

共 **2035** 个用例（`python -m unittest discover -s tests -p "test_*.py"`）。

按测试文件分组；「测试目标」优先取方法 docstring，无则结合类 docstring 与方法名，再否则仅由方法名转写。

本文件是生成的可读测试目录，不是事实源；事实源是 `tests/`。
由 `python scripts/gen_unit_tests_md.py` 生成；`--check` 在 CI 里校验是否漂移，直接改动会被下一次生成覆盖。

## 目录

1. [test_ai_speak_plugin.py](#test_ai_speak_pluginpy)（4）
2. [test_ai_speak_runtime.py](#test_ai_speak_runtimepy)（24）
3. [test_ai_speak_text.py](#test_ai_speak_textpy)（30）
4. [test_anthropic_provider.py](#test_anthropic_providerpy)（30）
5. [test_app_context.py](#test_app_contextpy)（11）
6. [test_app_context_wiring.py](#test_app_context_wiringpy)（15）
7. [test_architecture_hygiene.py](#test_architecture_hygienepy)（21）
8. [test_artifact_lock.py](#test_artifact_lockpy)（16）
9. [test_attachments_autonomy.py](#test_attachments_autonomypy)（21）
10. [test_auth_security.py](#test_auth_securitypy)（7）
11. [test_background_tasks.py](#test_background_taskspy)（16）
12. [test_batch_f_tools.py](#test_batch_f_toolspy)（23）
13. [test_catalog.py](#test_catalogpy)（8）
14. [test_classic_adapter.py](#test_classic_adapterpy)（110）
15. [test_cli_shell.py](#test_cli_shellpy)（20）
16. [test_command_tools.py](#test_command_toolspy)（30）
17. [test_concurrency.py](#test_concurrencypy)（11）
18. [test_config_values.py](#test_config_valuespy)（2）
19. [test_context_assembly.py](#test_context_assemblypy)（187）
20. [test_context_config_wiring.py](#test_context_config_wiringpy)（3）
21. [test_context_dump.py](#test_context_dumppy)（3）
22. [test_context_dump_skill.py](#test_context_dump_skillpy)（1）
23. [test_context_hooks.py](#test_context_hookspy)（3）
24. [test_context_pipeline.py](#test_context_pipelinepy)（18）
25. [test_context_plumbing.py](#test_context_plumbingpy)（5）
26. [test_context_splice.py](#test_context_splicepy)（9）
27. [test_conversation_queue.py](#test_conversation_queuepy)（6）
28. [test_core.py](#test_corepy)（58）
29. [test_coverage_gaps.py](#test_coverage_gapspy)（10）
30. [test_edited_files.py](#test_edited_filespy)（1）
31. [test_entry_layer.py](#test_entry_layerpy)（19）
32. [test_environment_info.py](#test_environment_infopy)（1）
33. [test_error_log.py](#test_error_logpy)（8）
34. [test_event_bus.py](#test_event_buspy)（9）
35. [test_fact_compat.py](#test_fact_compatpy)（4）
36. [test_file_safety.py](#test_file_safetypy)（24）
37. [test_file_size_format.py](#test_file_size_formatpy)（4）
38. [test_four_step_gate.py](#test_four_step_gatepy)（9）
39. [test_frame_shape_align.py](#test_frame_shape_alignpy)（6）
40. [test_frozen_data_root.py](#test_frozen_data_rootpy)（3）
41. [test_gate_negative.py](#test_gate_negativepy)（67）
42. [test_goal_runner.py](#test_goal_runnerpy)（6）
43. [test_gui_launcher.py](#test_gui_launcherpy)（8）
44. [test_history_page.py](#test_history_pagepy)（16）
45. [test_image_embed.py](#test_image_embedpy)（10）
46. [test_image_tool.py](#test_image_toolpy)（28）
47. [test_image_turns.py](#test_image_turnspy)（23）
48. [test_import_graph.py](#test_import_graphpy)（5）
49. [test_invest_tools.py](#test_invest_toolspy)（29）
50. [test_kb_plugin.py](#test_kb_pluginpy)（51）
51. [test_layout_min_width.py](#test_layout_min_widthpy)（2）
52. [test_mode_note.py](#test_mode_notepy)（13）
53. [test_model_catalog.py](#test_model_catalogpy)（23）
54. [test_model_provider.py](#test_model_providerpy)（41）
55. [test_model_window.py](#test_model_windowpy)（14）
56. [test_multi_model_plugin.py](#test_multi_model_pluginpy)（30）
57. [test_plugin_contributions.py](#test_plugin_contributionspy)（32）
58. [test_plugin_http.py](#test_plugin_httppy)（18）
59. [test_plugins.py](#test_pluginspy)（29）
60. [test_present_tool.py](#test_present_toolpy)（2）
61. [test_prompt_sections.py](#test_prompt_sectionspy)（2）
62. [test_prompt_tail.py](#test_prompt_tailpy)（5）
63. [test_protocol_contract.py](#test_protocol_contractpy)（13）
64. [test_provider_meta.py](#test_provider_metapy)（8）
65. [test_provider_router.py](#test_provider_routerpy)（14）
66. [test_quality_pipeline.py](#test_quality_pipelinepy)（18）
67. [test_queue_runner.py](#test_queue_runnerpy)（3）
68. [test_queued_input.py](#test_queued_inputpy)（4）
69. [test_readonly_tools.py](#test_readonly_toolspy)（33）
70. [test_resume_bridge.py](#test_resume_bridgepy)（6）
71. [test_rules_plugin.py](#test_rules_pluginpy)（12）
72. [test_run_registry.py](#test_run_registrypy)（13）
73. [test_scan_js_events.py](#test_scan_js_eventspy)（54）
74. [test_session_context.py](#test_session_contextpy)（22）
75. [test_session_seq.py](#test_session_seqpy)（23）
76. [test_session_store.py](#test_session_storepy)（17）
77. [test_session_tools.py](#test_session_toolspy)（17）
78. [test_settings_panel.py](#test_settings_panelpy)（21）
79. [test_silent_except_gate.py](#test_silent_except_gatepy)（10）
80. [test_source_snapshot.py](#test_source_snapshotpy)（10）
81. [test_subagent.py](#test_subagentpy)（17）
82. [test_task_tools.py](#test_task_toolspy)（27）
83. [test_todo_context_prompt.py](#test_todo_context_promptpy)（21）
84. [test_tool_arguments.py](#test_tool_argumentspy)（4）
85. [test_tool_registry.py](#test_tool_registrypy)（17）
86. [test_tool_resume.py](#test_tool_resumepy)（3）
87. [test_tool_session_gate.py](#test_tool_session_gatepy)（1）
88. [test_top_level_services.py](#test_top_level_servicespy)（2）
89. [test_update.py](#test_updatepy)（25）
90. [test_update_processes.py](#test_update_processespy)（2）
91. [test_usage_metrics.py](#test_usage_metricspy)（7）
92. [test_version_stamp.py](#test_version_stamppy)（4）
93. [test_visual_app_integration.py](#test_visual_app_integrationpy)（1）
94. [test_visual_context_integration.py](#test_visual_context_integrationpy)（2）
95. [test_visual_operator.py](#test_visual_operatorpy)（160）
96. [test_visual_operator_2.py](#test_visual_operator_2py)（21）
97. [test_wake_scheduler.py](#test_wake_schedulerpy)（16）
98. [test_web_auth.py](#test_web_authpy)（26）
99. [test_web_frontend.py](#test_web_frontendpy)（5）
100. [test_web_shell.py](#test_web_shellpy)（52）
101. [test_web_ui_config.py](#test_web_ui_configpy)（24）
102. [test_write_gate.py](#test_write_gatepy)（16）
103. [test_write_path_keys_lifecycle.py](#test_write_path_keys_lifecyclepy)（4）
104. [test_write_path_tools.py](#test_write_path_toolspy)（36）

## test_ai_speak_plugin.py

共 4 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AISpeakAppTest` | `test_loaded_wiring` | 覆盖「A class whose instances are single test cases」：loaded wiring |
| 2 | `AISpeakAppTest` | `test_publisher_tracks_connections` | 覆盖「A class whose instances are single test cases」：publisher tracks connections |
| 3 | `AISpeakAppTest` | `test_unload_clears_everything` | 覆盖「A class whose instances are single test cases」：unload clears everything |
| 4 | `AISpeakAppTest` | `test_voice_directive_is_in_request_tail` | 覆盖「A class whose instances are single test cases」：voice directive is in request tail |

## test_ai_speak_runtime.py

共 24 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ProviderTest` | `test_available_and_synthesize` | 覆盖「A class whose instances are single test cases」：available and synthesize |
| 2 | `ProviderTest` | `test_empty_audio` | 覆盖「A class whose instances are single test cases」：empty audio |
| 3 | `ProviderTest` | `test_missing_dependency` | 覆盖「A class whose instances are single test cases」：missing dependency |
| 4 | `ProviderTest` | `test_timeout` | 覆盖「A class whose instances are single test cases」：timeout |
| 5 | `RegistrationTest` | `test_config_and_status_routes` | 覆盖「A class whose instances are single test cases」：config and status routes |
| 6 | `RegistrationTest` | `test_register_and_dispose` | 覆盖「A class whose instances are single test cases」：register and dispose |
| 7 | `RuntimeTest` | `test_dispose_publishes_stop_and_blocks_enqueue` | 覆盖「A class whose instances are single test cases」：dispose publishes stop and blocks enqueue |
| 8 | `RuntimeTest` | `test_no_sse_stops_worker` | 覆盖「A class whose instances are single test cases」：no sse stops worker |
| 9 | `RuntimeTest` | `test_playback_wait_timeout_and_cancel` | 覆盖「A class whose instances are single test cases」：playback wait timeout and cancel |
| 10 | `RuntimeTest` | `test_publish_in_order_and_base64` | 覆盖「A class whose instances are single test cases」：publish in order and base64 |
| 11 | `RuntimeTest` | `test_queue_full_rejects_whole_batch` | 覆盖「A class whose instances are single test cases」：queue full rejects whole batch |
| 12 | `RuntimeTest` | `test_stop_clears_queue_and_publishes_stop` | 覆盖「A class whose instances are single test cases」：stop clears queue and publishes stop |
| 13 | `RuntimeTest` | `test_synthesis_failure_is_isolated` | 覆盖「A class whose instances are single test cases」：synthesis failure is isolated |
| 14 | `ToolTest` | `test_disconnected_publisher_fails` | 覆盖「A class whose instances are single test cases」：disconnected publisher fails |
| 15 | `ToolTest` | `test_invalid_message_fails_before_enqueue` | 覆盖「A class whose instances are single test cases」：invalid message fails before enqueue |
| 16 | `ToolTest` | `test_missing_provider_fails` | 覆盖「A class whose instances are single test cases」：missing provider fails |
| 17 | `ToolTest` | `test_missing_publisher_fails` | 覆盖「A class whose instances are single test cases」：missing publisher fails |
| 18 | `ToolTest` | `test_pipeline_envelope` | 覆盖「A class whose instances are single test cases」：pipeline envelope |
| 19 | `ToolTest` | `test_success_enqueues_segments` | 覆盖「A class whose instances are single test cases」：success enqueues segments |
| 20 | `ToolTest` | `test_sync_playback_releases_on_stop` | 覆盖「A class whose instances are single test cases」：sync playback releases on stop |
| 21 | `ToolTest` | `test_sync_playback_times_out_without_ack` | 覆盖「A class whose instances are single test cases」：sync playback times out without ack |
| 22 | `ToolTest` | `test_sync_playback_waits_for_frontend_ack` | 覆盖「A class whose instances are single test cases」：sync playback waits for frontend ack |
| 23 | `ToolTest` | `test_sync_synthesis_failure_is_not_reported_as_playback_failure` | 覆盖「A class whose instances are single test cases」：sync synthesis failure is not reported as playback failure |
| 24 | `ToolTest` | `test_tool_contract` | 覆盖「A class whose instances are single test cases」：tool contract |

## test_ai_speak_text.py

共 30 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ConfigTest` | `test_invalid_engine_and_voice_fail` | 覆盖「A class whose instances are single test cases」：invalid engine and voice fail |
| 2 | `ConfigTest` | `test_missing_file_uses_defaults` | 覆盖「A class whose instances are single test cases」：missing file uses defaults |
| 3 | `ConfigTest` | `test_values_and_limits` | 覆盖「A class whose instances are single test cases」：values and limits |
| 4 | `SpeechTextTest` | `test_bracket_and_book_title_quotes_are_dropped` | 各种引号都不发音：合成前统一清掉，不靠逐个列举。 |
| 5 | `SpeechTextTest` | `test_dates_and_identifiers_are_not_math` | 覆盖「A class whose instances are single test cases」：dates and identifiers are not math |
| 6 | `SpeechTextTest` | `test_math` | 覆盖「A class whose instances are single test cases」：math |
| 7 | `SpeechTextTest` | `test_non_speakable_symbols_are_dropped` | 覆盖「A class whose instances are single test cases」：non speakable symbols are dropped |
| 8 | `SpeechTextTest` | `test_percent` | 覆盖「A class whose instances are single test cases」：percent |
| 9 | `SpeechTextTest` | `test_quotes_and_apostrophes` | 覆盖「A class whose instances are single test cases」：quotes and apostrophes |
| 10 | `SpeechTextTest` | `test_thousands_separator_removed` | 覆盖「A class whose instances are single test cases」：thousands separator removed |
| 11 | `SplitTest` | `test_chinese_and_english_sentences` | 覆盖「A class whose instances are single test cases」：chinese and english sentences |
| 12 | `SplitTest` | `test_configured_limit_is_not_capped` | 覆盖「A class whose instances are single test cases」：configured limit is not capped |
| 13 | `SplitTest` | `test_message_limit` | 覆盖「A class whose instances are single test cases」：message limit |
| 14 | `SplitTest` | `test_numeric_separators_are_not_boundaries` | 覆盖「A class whose instances are single test cases」：numeric separators are not boundaries |
| 15 | `SplitTest` | `test_packing_respects_limit` | 覆盖「A class whose instances are single test cases」：packing respects limit |
| 16 | `SplitTest` | `test_quoted_end_is_a_boundary` | 覆盖「A class whose instances are single test cases」：quoted end is a boundary |
| 17 | `SplitTest` | `test_single_piece_over_limit` | 覆盖「A class whose instances are single test cases」：single piece over limit |
| 18 | `ValidationTest` | `test_bracket_quotes_pair_and_do_not_split` | 「」成对可用，且引号内的标点不切段。 |
| 19 | `ValidationTest` | `test_invisible_character_named_in_error` | 换行这类不可见字符以名字出现，不塞一个看不见的字符进报错。 |
| 20 | `ValidationTest` | `test_non_speakable_symbols_are_accepted` | 不发音的符号不在输入侧拦，交给合成前清洗。 |
| 21 | `ValidationTest` | `test_path_and_book_title_chars_allowed` | 文件名符号与书名号可以念，且不破坏切段。 |
| 22 | `ValidationTest` | `test_rejects_control_characters` | 控制字符会改变切段后各段拼接的含义，必须在输入侧拦住。 |
| 23 | `ValidationTest` | `test_rejects_empty_and_missing_end` | 覆盖「A class whose instances are single test cases」：rejects empty and missing end |
| 24 | `ValidationTest` | `test_rejects_empty_pairs` | 覆盖「A class whose instances are single test cases」：rejects empty pairs |
| 25 | `ValidationTest` | `test_rejects_leading_boundary` | 覆盖「A class whose instances are single test cases」：rejects leading boundary |
| 26 | `ValidationTest` | `test_rejects_math_context` | 覆盖「A class whose instances are single test cases」：rejects math context |
| 27 | `ValidationTest` | `test_rejects_percent_without_number` | 覆盖「A class whose instances are single test cases」：rejects percent without number |
| 28 | `ValidationTest` | `test_rejects_unmatched_book_title` | 书名号同样要求配对。 |
| 29 | `ValidationTest` | `test_rejects_unmatched_pairs` | 覆盖「A class whose instances are single test cases」：rejects unmatched pairs |
| 30 | `ValidationTest` | `test_reports_rule_in_error` | 报错要说明规则是什么，别只说这个字符不行。 |

## test_anthropic_provider.py

共 30 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `EndpointAndErrorTest` | `test_http_error_response_is_mapped` | 覆盖「A class whose instances are single test cases」：http error response is mapped |
| 2 | `EndpointAndErrorTest` | `test_http_errors_use_the_anthropic_table_and_keep_upstream_detail` | 覆盖「A class whose instances are single test cases」：http errors use the anthropic table and keep upstream detail |
| 3 | `EndpointAndErrorTest` | `test_messages_url_variants` | 覆盖「A class whose instances are single test cases」：messages url variants |
| 4 | `EndpointAndErrorTest` | `test_missing_credentials_fail_before_any_network_call` | 覆盖「A class whose instances are single test cases」：missing credentials fail before any network call |
| 5 | `EndpointAndErrorTest` | `test_stream_posts_headers_and_payload_then_parses_sse` | 覆盖「A class whose instances are single test cases」：stream posts headers and payload then parses sse |
| 6 | `EndpointAndErrorTest` | `test_stream_watchdog_stops_a_stalled_upstream` | 覆盖「A class whose instances are single test cases」：stream watchdog stops a stalled upstream |
| 7 | `MessageConversionTest` | `test_assistant_tool_calls_become_tool_use_blocks` | 覆盖「A class whose instances are single test cases」：assistant tool calls become tool use blocks |
| 8 | `MessageConversionTest` | `test_consecutive_tool_results_merge_into_one_user_message` | 覆盖「A class whose instances are single test cases」：consecutive tool results merge into one user message |
| 9 | `MessageConversionTest` | `test_dangling_tool_result_is_dropped` | 覆盖「A class whose instances are single test cases」：dangling tool result is dropped |
| 10 | `MessageConversionTest` | `test_disabled_thinking_does_not_replay_stored_blocks` | 思考关闭时不带 thinking 块：官方端点会拒“思考未开启却带块”。 |
| 11 | `MessageConversionTest` | `test_duplicate_tool_ids_are_suffixed_and_results_follow` | 覆盖「A class whose instances are single test cases」：duplicate tool ids are suffixed and results follow |
| 12 | `MessageConversionTest` | `test_image_urls_are_split_into_image_blocks` | 覆盖「A class whose instances are single test cases」：image urls are split into image blocks |
| 13 | `MessageConversionTest` | `test_leading_assistant_is_dropped` | 覆盖「A class whose instances are single test cases」：leading assistant is dropped |
| 14 | `MessageConversionTest` | `test_logic_shaped_tool_becomes_a_valid_object_schema` | `ToolRegistry.schemas()` 给的是属性映射，必须包装成 object schema。 |
| 15 | `MessageConversionTest` | `test_system_is_hoisted_and_user_text_becomes_a_block` | 覆盖「A class whose instances are single test cases」：system is hoisted and user text becomes a block |
| 16 | `MessageConversionTest` | `test_thinking_block_with_empty_text_is_still_replayed` | 正文为空、签名在的思考块也要回传。 |
| 17 | `MessageConversionTest` | `test_thinking_blocks_replay_only_within_the_current_turn` | 覆盖「A class whose instances are single test cases」：thinking blocks replay only within the current turn |
| 18 | `MessageConversionTest` | `test_thinking_is_enabled_only_when_the_budget_fits` | 覆盖「A class whose instances are single test cases」：thinking is enabled only when the budget fits |
| 19 | `MessageConversionTest` | `test_thinking_off_is_sent_as_disabled_not_omitted` | 覆盖「A class whose instances are single test cases」：thinking off is sent as disabled not omitted |
| 20 | `MessageConversionTest` | `test_tool_turn_without_thinking_blocks_disables_thinking` | 历史工具往返丢了 thinking 块就补不回来，本回合只能关掉思考，否则必被拒。 |
| 21 | `MessageConversionTest` | `test_tools_payload_accepts_both_declaration_shapes` | 覆盖「A class whose instances are single test cases」：tools payload accepts both declaration shapes |
| 22 | `StreamAssemblyTest` | `test_cache_fields_default_to_zero_when_absent` | 覆盖「A class whose instances are single test cases」：cache fields default to zero when absent |
| 23 | `StreamAssemblyTest` | `test_error_event_becomes_model_request_error` | 覆盖「A class whose instances are single test cases」：error event becomes model request error |
| 24 | `StreamAssemblyTest` | `test_invalid_tool_json_degrades_to_empty_arguments` | 覆盖「A class whose instances are single test cases」：invalid tool json degrades to empty arguments |
| 25 | `StreamAssemblyTest` | `test_meta_is_emitted_only_when_thinking_and_tools_coexist` | 覆盖「A class whose instances are single test cases」：meta is emitted only when thinking and tools coexist |
| 26 | `StreamAssemblyTest` | `test_missing_tool_id_gets_a_generated_one` | 覆盖「A class whose instances are single test cases」：missing tool id gets a generated one |
| 27 | `StreamAssemblyTest` | `test_ping_and_unknown_events_are_ignored` | 覆盖「A class whose instances are single test cases」：ping and unknown events are ignored |
| 28 | `StreamAssemblyTest` | `test_text_deltas_stream_through_and_usage_is_mapped` | 覆盖「A class whose instances are single test cases」：text deltas stream through and usage is mapped |
| 29 | `StreamAssemblyTest` | `test_thinking_and_tool_use_are_reassembled` | 覆盖「A class whose instances are single test cases」：thinking and tool use are reassembled |
| 30 | `StreamAssemblyTest` | `test_thinking_without_signature_is_skipped_with_a_warning` | 覆盖「A class whose instances are single test cases」：thinking without signature is skipped with a warning |

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
| 12 | `ProcessServiceRegistryTest` | `test_context_and_compactor_factories_default_on` | 上下文管线与压缩器默认装配。 |
| 13 | `ProcessServiceRegistryTest` | `test_duplicate_registration_still_rejected` | 覆盖「进程级服务登记」：duplicate registration still rejected |
| 14 | `ProcessServiceRegistryTest` | `test_optional_services_registered_when_injected` | 覆盖「进程级服务登记」：optional services registered when injected |
| 15 | `ProcessServiceRegistryTest` | `test_store_absent_when_not_injected` | store 未注入时不登记（会话持久化是可选面）。 |

## test_architecture_hygiene.py

共 21 个用例。

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
| 10 | `ModuleBoundaryAstTest` | `test_compactor_contract_import_passes` | 覆盖「A class whose instances are single test cases」：compactor contract import passes |
| 11 | `ModuleBoundaryAstTest` | `test_compactor_pipeline_import_caught` | 覆盖「A class whose instances are single test cases」：compactor pipeline import caught |
| 12 | `ModuleBoundaryAstTest` | `test_provider_concrete_sibling_caught` | 覆盖「A class whose instances are single test cases」：provider concrete sibling caught |
| 13 | `ModuleBoundaryAstTest` | `test_provider_neutral_imports_pass` | 覆盖「A class whose instances are single test cases」：provider neutral imports pass |
| 14 | `QualityGateShimAstTest` | `test_comment_mention_passes` | 覆盖「A class whose instances are single test cases」：comment mention passes |
| 15 | `QualityGateShimAstTest` | `test_import_quality_gate_caught` | 覆盖「A class whose instances are single test cases」：import quality gate caught |
| 16 | `SameLayerPrivateImportTest` | `test_private_same_layer_caught` | 覆盖「A class whose instances are single test cases」：private same layer caught |
| 17 | `SameLayerPrivateImportTest` | `test_public_same_layer_passes` | 覆盖「A class whose instances are single test cases」：public same layer passes |
| 18 | `SilentSystemPromptCheckTest` | `test_external_package_root_does_not_crash` | 覆盖「A class whose instances are single test cases」：external package root does not crash |
| 19 | `SilentSystemPromptCheckTest` | `test_nonstandard_indent_and_as_clause_caught` | 覆盖「A class whose instances are single test cases」：nonstandard indent and as clause caught |
| 20 | `TestMethodNameGateTest` | `test_bad_test_prefix_caught` | 覆盖「A class whose instances are single test cases」：bad test prefix caught |
| 21 | `TestMethodNameGateTest` | `test_public_test_prefix_passes` | 覆盖「A class whose instances are single test cases」：public test prefix passes |

## test_artifact_lock.py

共 16 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ArtifactLockTest` | `test_acquire_records_holder` | 覆盖「锁的互斥、回收与释放语义」：acquire records holder |
| 2 | `ArtifactLockTest` | `test_force_breaks_live_holder` | 覆盖「锁的互斥、回收与释放语义」：force breaks live holder |
| 3 | `ArtifactLockTest` | `test_half_written_lock_holds_until_grace_period` | 覆盖「锁的互斥、回收与释放语义」：half written lock holds until grace period |
| 4 | `ArtifactLockTest` | `test_half_written_lock_is_reclaimed_after_grace_period` | 覆盖「锁的互斥、回收与释放语义」：half written lock is reclaimed after grace period |
| 5 | `ArtifactLockTest` | `test_holder_with_dead_pid_is_reclaimed` | 覆盖「锁的互斥、回收与释放语义」：holder with dead pid is reclaimed |
| 6 | `ArtifactLockTest` | `test_parse_holder_rejects_garbage` | 覆盖「锁的互斥、回收与释放语义」：parse holder rejects garbage |
| 7 | `ArtifactLockTest` | `test_release_frees_lock_for_next_owner` | 覆盖「锁的互斥、回收与释放语义」：release frees lock for next owner |
| 8 | `ArtifactLockTest` | `test_release_is_idempotent` | 覆盖「锁的互斥、回收与释放语义」：release is idempotent |
| 9 | `ArtifactLockTest` | `test_release_keeps_foreign_lock` | 覆盖「锁的互斥、回收与释放语义」：release keeps foreign lock |
| 10 | `ArtifactLockTest` | `test_second_owner_is_rejected_with_holder_info` | 覆盖「锁的互斥、回收与释放语义」：second owner is rejected with holder info |
| 11 | `ArtifactLockTest` | `test_wait_succeeds_after_holder_releases` | 覆盖「锁的互斥、回收与释放语义」：wait succeeds after holder releases |
| 12 | `CoverageBusyTest` | `test_check_locked_skips_when_data_changes_during_measure` | 覆盖「有写者持锁时，覆盖率校验必须跳过而不是拿半份数据判失败」：check locked skips when data changes during measure |
| 13 | `CoverageBusyTest` | `test_main_skips_when_writer_holds_lock` | 覆盖「有写者持锁时，覆盖率校验必须跳过而不是拿半份数据判失败」：main skips when writer holds lock |
| 14 | `CoverageBusyTest` | `test_stamp_is_none_for_missing_file` | 覆盖「有写者持锁时，覆盖率校验必须跳过而不是拿半份数据判失败」：stamp is none for missing file |
| 15 | `CoveragePublishTest` | `test_build_command_writes_unique_data_file` | 覆盖「覆盖率数据先落独立文件再发布，读侧不会读到半份数据」：build command writes unique data file |
| 16 | `CoveragePublishTest` | `test_publish_replaces_target` | 覆盖「覆盖率数据先落独立文件再发布，读侧不会读到半份数据」：publish replaces target |

## test_attachments_autonomy.py

共 21 个用例。

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
| 15 | `UserContentTest` | `test_input_module_emits_attachment_reference` | 覆盖「附件 → 多模态 content」：input module emits attachment reference |
| 16 | `UserContentTest` | `test_invalid_attachment_ignored` | 覆盖「附件 → 多模态 content」：invalid attachment ignored |
| 17 | `UserContentTest` | `test_no_attachments_is_plain_string` | 覆盖「附件 → 多模态 content」：no attachments is plain string |
| 18 | `UserContentTest` | `test_text_and_image_parts` | 覆盖「附件 → 多模态 content」：text and image parts |
| 19 | `UserContentTest` | `test_user_content_keeps_attachment_reference` | 覆盖「附件 → 多模态 content」：user content keeps attachment reference |
| 20 | `VisionDegradeTest` | `test_any_model_keeps_image_parts` | 图片一律原样下发 —— 不按模型名猜能力、不做降级剥图。 |
| 21 | `VisionDegradeTest` | `test_image_only_message_is_not_empty` | 覆盖「图片一律原样下发：没有任何按模型名降级剥图的分支」：image only message is not empty |

## test_auth_security.py

共 7 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AuthSecurityTest` | `test_atomic_failure_leaves_no_target` | 覆盖「A class whose instances are single test cases」：atomic failure leaves no target |
| 2 | `AuthSecurityTest` | `test_audit_hot_path_does_not_spawn` | 覆盖「A class whose instances are single test cases」：audit hot path does not spawn |
| 3 | `AuthSecurityTest` | `test_directory_and_atomic_secret` | 覆盖「A class whose instances are single test cases」：directory and atomic secret |
| 4 | `AuthSecurityTest` | `test_missing_path_is_rejected` | 覆盖「A class whose instances are single test cases」：missing path is rejected |
| 5 | `AuthSecurityTest` | `test_widened_acl_is_rejected_immediately` | 覆盖「A class whose instances are single test cases」：widened acl is rejected immediately |
| 6 | `AuthSecurityTest` | `test_widened_directory_is_repaired` | 覆盖「A class whose instances are single test cases」：widened directory is repaired |
| 7 | `AuthSecurityTest` | `test_windows_timeout_is_security_error` | 覆盖「A class whose instances are single test cases」：windows timeout is security error |

## test_background_tasks.py

共 16 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `BackgroundTaskManagerTest` | `test_app_wires_manager_and_tool` | 覆盖「A class whose instances are single test cases」：app wires manager and tool |
| 2 | `BackgroundTaskManagerTest` | `test_argv_is_not_shell_interpreted` | 覆盖「A class whose instances are single test cases」：argv is not shell interpreted |
| 3 | `BackgroundTaskManagerTest` | `test_background_process_sees_user_paths` | 覆盖「A class whose instances are single test cases」：background process sees user paths |
| 4 | `BackgroundTaskManagerTest` | `test_batch_groups_tasks_and_filters_exact_id` | 覆盖「A class whose instances are single test cases」：batch groups tasks and filters exact id |
| 5 | `BackgroundTaskManagerTest` | `test_batch_returns_all_tasks_without_pagination` | 覆盖「A class whose instances are single test cases」：batch returns all tasks without pagination |
| 6 | `BackgroundTaskManagerTest` | `test_cancel_queued_task` | 覆盖「A class whose instances are single test cases」：cancel queued task |
| 7 | `BackgroundTaskManagerTest` | `test_completed_output_and_history` | 覆盖「A class whose instances are single test cases」：completed output and history |
| 8 | `BackgroundTaskManagerTest` | `test_cwd_outside_root_rejected` | 覆盖「A class whose instances are single test cases」：cwd outside root rejected |
| 9 | `BackgroundTaskManagerTest` | `test_env_allowlist_keeps_user_paths_excludes_secrets` | 覆盖「A class whose instances are single test cases」：env allowlist keeps user paths excludes secrets |
| 10 | `BackgroundTaskManagerTest` | `test_execution_timeout_and_running_cancel` | 覆盖「A class whose instances are single test cases」：execution timeout and running cancel |
| 11 | `BackgroundTaskManagerTest` | `test_label_required_but_not_unique` | 覆盖「A class whose instances are single test cases」：label required but not unique |
| 12 | `BackgroundTaskManagerTest` | `test_output_cursor_rebases_after_buffer_trim` | 覆盖「A class whose instances are single test cases」：output cursor rebases after buffer trim |
| 13 | `BackgroundTaskManagerTest` | `test_plan_mode_rejects_create` | 覆盖「A class whose instances are single test cases」：plan mode rejects create |
| 14 | `BackgroundTaskManagerTest` | `test_queue_capacity_and_cid_isolation` | 覆盖「A class whose instances are single test cases」：queue capacity and cid isolation |
| 15 | `BackgroundTaskManagerTest` | `test_system_notice_metadata_survives_queue_and_history` | 覆盖「A class whose instances are single test cases」：system notice metadata survives queue and history |
| 16 | `BackgroundTaskManagerTest` | `test_tool_dispatch_create_list_output_cancel` | 覆盖「A class whose instances are single test cases」：tool dispatch create list output cancel |

## test_batch_f_tools.py

共 23 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `IpGeolocateTest` | `test_private_ip_normalized_to_export_lookup` | 覆盖「ip 定位」：private ip normalized to export lookup |
| 2 | `IpGeolocateTest` | `test_public_ip_path_with_loopback_variants` | 覆盖「ip 定位」：public ip path with loopback variants |
| 3 | `IpGeolocateTest` | `test_success_false_structured_error` | 覆盖「ip 定位」：success false structured error |
| 4 | `ReviewConclusionTest` | `test_call_is_submit_not_format_check` | 调用即提交：没有"仅格式校验"档；返回里不含 dry_run。 |
| 5 | `ReviewConclusionTest` | `test_cancel_preview_and_invalid` | 覆盖「review 提交与解锁（经 ToolTurnContext.session.gate）」：cancel preview and invalid |
| 6 | `ReviewConclusionTest` | `test_confirm_unlock_and_review_done` | 覆盖「review 提交与解锁（经 ToolTurnContext.session.gate）」：confirm unlock and review done |
| 7 | `ReviewConclusionTest` | `test_short_conclusion_and_missing_file_name_rejected` | 覆盖「review 提交与解锁（经 ToolTurnContext.session.gate）」：short conclusion and missing file name rejected |
| 8 | `SkillsLibraryTest` | `test_scan_list_and_matching` | 覆盖「Skills 库」：scan list and matching |
| 9 | `SkillsLibraryTest` | `test_truncation_and_incremental_rescan` | 覆盖「Skills 库」：truncation and incremental rescan |
| 10 | `SkillsListNeverDoublesTest` | `test_auto_load_count_ignores_duplicate_entries` | 覆盖「清单翻倍防线：库内出现重复条目时，清单仍只列一份」：auto load count ignores duplicate entries |
| 11 | `SkillsListNeverDoublesTest` | `test_concurrent_rescan_replaces_the_list` | 覆盖「清单翻倍防线：库内出现重复条目时，清单仍只列一份」：concurrent rescan replaces the list |
| 12 | `SkillsListNeverDoublesTest` | `test_different_path_spelling_counts_once` | 同一文件的两种路径写法不能让 `len(list_skills())` 变成两倍。 |
| 13 | `SkillsListNeverDoublesTest` | `test_duplicate_entries_do_not_double_the_catalog` | 覆盖「清单翻倍防线：库内出现重复条目时，清单仍只列一份」：duplicate entries do not double the catalog |
| 14 | `SkillsListNeverDoublesTest` | `test_rescan_does_not_append_twice` | 覆盖「清单翻倍防线：库内出现重复条目时，清单仍只列一份」：rescan does not append twice |
| 15 | `SkillsSourceTest` | `test_catalog_separates_builtin_and_external` | 覆盖「内置根与外置根：合并、覆盖、auto_load」：catalog separates builtin and external |
| 16 | `SkillsSourceTest` | `test_external_overrides_builtin_and_both_auto_loads` | 覆盖「内置根与外置根：合并、覆盖、auto_load」：external overrides builtin and both auto loads |
| 17 | `SkillsSourceTest` | `test_resource_directory_section_has_both_sources` | 覆盖「内置根与外置根：合并、覆盖、auto_load」：resource directory section has both sources |
| 18 | `SkillsSourceTest` | `test_tool_description_does_not_embed_external_dir` | 覆盖「内置根与外置根：合并、覆盖、auto_load」：tool description does not embed external dir |
| 19 | `SkillsToolTest` | `test_list_read_and_lookup_error` | 覆盖「skills 工具」：list read and lookup error |
| 20 | `WeatherTest` | `test_cn_alias_direct_resolution` | 覆盖「天气查询」：cn alias direct resolution |
| 21 | `WeatherTest` | `test_coordinates_and_days_clamp` | 覆盖「天气查询」：coordinates and days clamp |
| 22 | `WeatherTest` | `test_location_not_found` | 覆盖「天气查询」：location not found |
| 23 | `WeatherTest` | `test_scoring_prefers_exact_and_major` | 覆盖「天气查询」：scoring prefers exact and major |

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

## test_classic_adapter.py

共 110 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `HistoryAttachmentReplayTest` | `test_attachment_id_is_recomputable` | id 必须从事实派生：刷新前后一致，否则浏览器不会重试那张失败的图。 |
| 2 | `HistoryAttachmentReplayTest` | `test_history_items_carry_attachments_and_had_images` | 覆盖「带附件的会话刷新后必须能再看图」：history items carry attachments and had images |
| 3 | `HistoryAttachmentReplayTest` | `test_history_items_carry_compaction_record` | 覆盖「带附件的会话刷新后必须能再看图」：history items carry compaction record |
| 4 | `HistoryAttachmentReplayTest` | `test_history_prefers_reasoning_time` | 思考卡只显示推理时长，不再用整次模型调用时长。 |
| 5 | `HistoryAttachmentReplayTest` | `test_history_replays_each_reasoning_before_its_tools` | 思考定稿在 `model_message.reasoning_content`，刷新后按轮插回工具卡前面。 |
| 6 | `HistoryAttachmentReplayTest` | `test_history_tool_canceled_stays_distinct_from_failed` | 停止是独立终态，刷新后标题才能和失败分开上色。 |
| 7 | `HistoryAttachmentReplayTest` | `test_history_tool_done_keeps_images` | 刷新后看图条目仍带着像素，展开面板才能把图画出来。 |
| 8 | `HistoryAttachmentReplayTest` | `test_history_tool_item_carries_elapsed_seconds` | 覆盖「带附件的会话刷新后必须能再看图」：history tool item carries elapsed seconds |
| 9 | `HistoryAttachmentReplayTest` | `test_inline_multimodal_content_is_also_accepted` | 兜底形态：content 直接是多模态数组时也要解出附件。 |
| 10 | `HistoryAttachmentReplayTest` | `test_plain_text_message_is_unaffected` | 覆盖「带附件的会话刷新后必须能再看图」：plain text message is unaffected |
| 11 | `InboundContractTest` | `test_attachment_ignores_invalid_images` | `images` 里没有可用 base64 时不登记（经典界面只在数组非空时才重建附件条）。 |
| 12 | `InboundContractTest` | `test_attachment_missing_is_404` | 覆盖「老入参 → 内核 → 老返回体」：attachment missing is 404 |
| 13 | `InboundContractTest` | `test_attachment_returns_image_bytes_not_json` | 经典界面用 `<img src>` 直接引用（il.js:7），所以必须返回字节而不是 JSON。 |
| 14 | `InboundContractTest` | `test_health_model_is_in_allowed_list` | `model` 必须在 `allowed_models` 里，否则经典界面白名单校验丢弃它 → 顶栏永远加载中。 |
| 15 | `InboundContractTest` | `test_history_cancels_suspended_tool_after_new_input` | 覆盖「老入参 → 内核 → 老返回体」：history cancels suspended tool after new input |
| 16 | `InboundContractTest` | `test_history_carries_context_layout_at_top_level` | `context_layout` 在顶层，`applyContextLayoutFromHistory` 读那里。 |
| 17 | `InboundContractTest` | `test_history_page_before_and_meta` | 覆盖「老入参 → 内核 → 老返回体」：history page before and meta |
| 18 | `InboundContractTest` | `test_history_rejects_bad_id` | 覆盖「老入参 → 内核 → 老返回体」：history rejects bad id |
| 19 | `InboundContractTest` | `test_history_returns_items_for_bubbles` | `items` 是刷新页面渲染气泡与工具卡的唯一来源（`renderHistoryItems`）。 |
| 20 | `InboundContractTest` | `test_history_returns_ok_true` | 回显必须带 `ok:true`，否则经典界面直接 return、整段历史不渲染。 |
| 21 | `InboundContractTest` | `test_history_todo_empty_when_none_active` | 没有清单（或已 `close`）时返回空数组，界面据此 `hideTodoList`。 |
| 22 | `InboundContractTest` | `test_history_todo_ignores_other_tools_items` | 检索结果的 `items`（`file` / `match`）不能进清单。 |
| 23 | `InboundContractTest` | `test_invalid_conversation_id_rejected_on_write` | 覆盖「老入参 → 内核 → 老返回体」：invalid conversation id rejected on write |
| 24 | `InboundContractTest` | `test_remember_attachments_merges_previous_pages` | 覆盖「老入参 → 内核 → 老返回体」：remember attachments merges previous pages |
| 25 | `InboundContractTest` | `test_sessions_read_id_not_conversation_id` | 经典界面读 `s.id`（`classic/js/chat/conversation.js` 的 `loadSessionRailList`）；`conversation_id` 不是它要的名字。 |
| 26 | `InboundContractTest` | `test_title_never_raises` | 覆盖「老入参 → 内核 → 老返回体」：title never raises |
| 27 | `InboundContractTest` | `test_ui_state_get_returns_only_client_independent_state` | GET 只回与客户端无关的那部分：哪些会话在跑。 |
| 28 | `InboundContractTest` | `test_ui_state_put_stores_nothing` | PUT 收到布局也不落盘；旧前端不会因此报错。 |
| 29 | `InboundContractTest` | `test_ui_state_put_writes_no_layout_file` | 确认没有留下布局文件（服务端不该有客户端状态的副本）。 |
| 30 | `InboundContractTest` | `test_usage_accumulates_across_events` | 覆盖「老入参 → 内核 → 老返回体」：usage accumulates across events |
| 31 | `InboundContractTest` | `test_usage_accumulator_uses_different_field_names` | 累计端点用 `total_*`，与 SSE 的 `prompt_tokens` 不是一套（`classic/js/chat/context-usage.js` 的 `loadUsageAccumulator`）。 |
| 32 | `InboundContractTest` | `test_usage_hydrates_from_facts_after_state_reset` | 覆盖「老入参 → 内核 → 老返回体」：usage hydrates from facts after state reset |
| 33 | `OutboundContractTest` | `test_approval_suspension_is_not_a_choice_card` | 审批挂起发 `approval_required`，不发选项卡。 |
| 34 | `OutboundContractTest` | `test_assistant_delta_uses_delta_field` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：assistant delta uses delta field |
| 35 | `OutboundContractTest` | `test_assistant_only_on_final_message_with_content` | 工具调用轮没有正文，发空 `assistant` 会让经典界面渲染一个空气泡。 |
| 36 | `OutboundContractTest` | `test_cancel_on_confirm_modal_records_a_declined_result` | 模态点「取消」（空 `confirm`）当作拒绝作答、记成工具结果， 与在端点里就地 `return 200 {"confirmed": False}` 行为不同。 |
| 37 | `OutboundContractTest` | `test_cancel_without_pending_does_not_start_an_empty_turn` | 没有挂起调用时的取消不得起新回合。 |
| 38 | `OutboundContractTest` | `test_chat_bubble_layout_puts_image_above_text` | 图文气泡：图片在上、文字在下。 |
| 39 | `OutboundContractTest` | `test_confirm_card_comes_from_the_kernel_fact` | 待确认卡由内核专用事实 `turn_awaiting_user` 驱动。 |
| 40 | `OutboundContractTest` | `test_context_compacted_emits_card_payload` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：context compacted emits card payload |
| 41 | `OutboundContractTest` | `test_context_layout_is_flat_with_segments` | `lastContextLayout = ev` 整包存下，所以 segments 在顶层（`classic/js/chat/stream.js` 的 `handleGlobalSseEvent`）。 |
| 42 | `OutboundContractTest` | `test_failed_run_type_switch_does_not_emit_mode_changed` | 失败时不能报"模式已切换"——那会让按钮显示一个并未生效的模式。 |
| 43 | `OutboundContractTest` | `test_incomplete_awaiting_fact_is_ignored` | 缺 `call_id` 或缺选项的事实不发卡（残缺数据不猜、不半渲染）。 |
| 44 | `OutboundContractTest` | `test_llm_request_model_is_never_empty` | 请求快照里的 `params.model` 不能是空串。 |
| 45 | `OutboundContractTest` | `test_malformed_arguments_do_not_break_the_stream` | `arguments` 不是对象时按空对象处理（经典界面只把它 JSON 化显示，不校验）。 |
| 46 | `OutboundContractTest` | `test_model_message_with_content_emits_response_done_and_assistant` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：model message with content emits response done and assistant |
| 47 | `OutboundContractTest` | `test_only_a_real_suspension_asks_the_user` | 只有工具真挂起才发 `user_confirm_required`——经典界面收到它就弹模态。 |
| 48 | `OutboundContractTest` | `test_plain_failure_is_not_mistaken_for_confirm` | 普通失败不得被判成待确认——否则每个报错都会弹出确认框。 |
| 49 | `OutboundContractTest` | `test_reasoning_delta_requires_round` | `round` 必须与 `lastLlm.round` 相等，否则经典界面丢弃（`classic/js/chat/llm-rounds.js` 的 `appendReasoningDelta`）。 |
| 50 | `OutboundContractTest` | `test_reasoning_is_not_promoted_into_chat_area` | 思考内容不经对话区填充（它属于右侧步骤卡）。 |
| 51 | `OutboundContractTest` | `test_run_type_query_does_not_emit_mode_changed` | 查询模式不该发 `mode_changed`（会把按钮刷成同一个值，纯噪声）。 |
| 52 | `OutboundContractTest` | `test_run_type_switch_emits_mode_changed` | `run_type` 切模式后必须补 `mode_changed`，否则经典界面的模式按钮停在旧值。 |
| 53 | `OutboundContractTest` | `test_step_started_emits_llm_round_then_request` | `llm_round` 是 `reasoning_*` / `llm_request` 的前置（`classic/js/chat/llm-rounds.js` 的 `addLlmRound`）。 |
| 54 | `OutboundContractTest` | `test_todo_list_rides_on_tool_end` | 清单没有独立事件，挂在 `tool_end.todo_list_data` 上（`classic/js/chat/stream.js` 的 `handleGlobalSseEvent`）。 |
| 55 | `OutboundContractTest` | `test_tool_call_becomes_tool_start_with_call_id` | `tool_call_id` 是配对的唯一键；空则后续 `tool_end` 被整个忽略（`classic/js/chat/llm-rounds.js` 的 `onToolStart`）。 |
| 56 | `OutboundContractTest` | `test_tool_call_does_not_pre_empt_the_confirm_card` | `tool_call` 期不发待确认卡——卡片由内核事实驱动，避免重复发两张。 |
| 57 | `OutboundContractTest` | `test_tool_call_without_id_is_skipped` | 没有 id 就配不上 tool_end，宁可一条都不发（发了就是永远转圈的卡）。 |
| 58 | `OutboundContractTest` | `test_tool_done_images_ride_beside_preview` | 看图的像素走 `images`，不写进 `preview` 文本。 |
| 59 | `OutboundContractTest` | `test_tool_end_carries_elapsed_seconds` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：tool end carries elapsed seconds |
| 60 | `OutboundContractTest` | `test_tool_result_preview_is_json_string` | `preview` 必须是 JSON 字符串（经典界面会 `JSON.parse`，`classic/js/tools/previews.js` 的 `fillToolPreview`）。 |
| 61 | `OutboundContractTest` | `test_tool_result_without_start_is_skipped` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：tool result without start is skipped |
| 62 | `OutboundContractTest` | `test_turn_ended_emits_done` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：turn ended emits done |
| 63 | `OutboundContractTest` | `test_turn_started_emits_conversation_first` | `conversation` 必须发，且要带头。 |
| 64 | `OutboundContractTest` | `test_unknown_kernel_event_is_ignored_not_raised` | 观察面纪律：翻译不认识的事件不能把事件流打断。 |
| 65 | `OutboundContractTest` | `test_usage_must_be_nested` | 用量嵌套在 `usage` 键下：经典界面读 `ev.usage.prompt_tokens`（`classic/js/chat/stream.js` 的 `handleGlobalSseEvent`）。 |
| 66 | `OutboundContractTest` | `test_user_confirm_multi_flag_passes_through` | 覆盖「内核事件 → 老事件。每条断言都对应经典界面真正读的字段」：user confirm multi flag passes through |
| 67 | `OutboundContractTest` | `test_vision_consent_keeps_plugin_confirmation_endpoint` | 视觉授权卡必须让前端 POST 到插件端点，而不是宿主 user-confirm。 |
| 68 | `OutboundContractTest` | `test_write_gate_confirm_id_does_not_fake_a_confirmation` | `confirm_id` 是写盘门控的二阶提交锁：门控给预览类工具的 成功结果挂上它，意思是"锁已建好，模型接着调提交工具并把 `confirm_id` 传回来"。 用户交互不发生在这一步（解锁入口是 `review_conclusion`）。 |
| 69 | `PluginEventTest` | `test_announce_broadcasts_to_channels` | 覆盖「插件事件出口：帧头固定、保留键拒绝、广播计数准确」：announce broadcasts to channels |
| 70 | `PluginEventTest` | `test_frame_rejects_reserved_and_bad_names` | 覆盖「插件事件出口：帧头固定、保留键拒绝、广播计数准确」：frame rejects reserved and bad names |
| 71 | `PluginEventTest` | `test_frame_shape_and_copy` | 覆盖「插件事件出口：帧头固定、保留键拒绝、广播计数准确」：frame shape and copy |
| 72 | `ResumeContractTest` | `test_cursor_prefers_header_then_query` | `Last-Event-ID`（浏览器自动带）优先于 `?last_event_id=`；非法值回落 -1。 |
| 73 | `ResumeContractTest` | `test_latest_seq_reports_global_log_end` | `latest_seq` 是全局最大坐标；空仓库返回 -1。 |
| 74 | `ResumeContractTest` | `test_replay_frames_carry_seq` | 回放的帧必须带坐标，否则浏览器重连时没有游标可用。 |
| 75 | `ResumeContractTest` | `test_replay_never_leaks_seq_into_frame_payloads` | `_seq` 是位置元数据，不该以原名出现在给前端的帧里（会污染契约）。 |
| 76 | `ResumeContractTest` | `test_replay_only_targets_given_channel` | 续传只补这一条连接：别的连接的队列不能被塞进历史。 |
| 77 | `ResumeContractTest` | `test_replay_respects_cursor` | `seq > after` 且不重复补游标那一帧。 |
| 78 | `ResumeContractTest` | `test_sse_id_line_is_emitted_for_seq_frames` | SSE 的 `id:` 行是浏览器重连带 `Last-Event-ID` 的唯一来源。 |
| 79 | `SubscriptionLifecycleTest` | `test_bus_subscription_reaches_channels` | 端到端：事件经真总线发布 → 翻译 → 到达连接队列。 |
| 80 | `SubscriptionLifecycleTest` | `test_dispose_is_idempotent` | 覆盖「适配层对事件总线的订阅必须按需，不能是常驻观察者」：dispose is idempotent |
| 81 | `SubscriptionLifecycleTest` | `test_no_subscription_without_clients` | 覆盖「适配层对事件总线的订阅必须按需，不能是常驻观察者」：no subscription without clients |
| 82 | `SubscriptionLifecycleTest` | `test_subscribe_on_first_client_and_release_on_last` | 覆盖「适配层对事件总线的订阅必须按需，不能是常驻观察者」：subscribe on first client and release on last |
| 83 | `UiBundleTest` | `test_each_model_call_opens_its_own_card` | 多趟往返时每回合各起一卡（工具前后各一张）。 |
| 84 | `UiBundleTest` | `test_inline_html_contains_all_five_scripts` | 漏注入 `image-lightbox.js` 会让 `window.AIA` 缺失 → 附件四条链路静默失效。 |
| 85 | `UiBundleTest` | `test_inline_html_has_no_placeholders_left` | 覆盖「素材与内联打包」：inline html has no placeholders left |
| 86 | `UiBundleTest` | `test_light_hljs_sheet_is_scoped` | 两套高亮配色同页共存，浅色那套必须限定在 `[data-ui-theme="light"]` 下。 |
| 87 | `UiBundleTest` | `test_llm_call_start_opens_a_step_card` | 步骤卡必须起得来。 |
| 88 | `UiBundleTest` | `test_plugin_event_bridges` | 插件事件经 DOM 事件交给插件；插件开关也派发 DOM 事件。 |
| 89 | `UiBundleTest` | `test_reasoning_stays_out_of_the_chat_area` | 思考内容不能出现在对话区（它属于右侧步骤卡）。 |
| 90 | `UiBundleTest` | `test_tool_tag_shows_final_state_immediately` | 工具结束时立刻写标签终态。 |
| 91 | `UsageSemanticsTest` | `test_put_overwrites_instead_of_accumulating` | 覆盖语义：连报两次累计值，第二次必须替换而不是相加。 |
| 92 | `UserConfirmRoundTripTest` | `test_agree_mints_approval_id_for_the_option` | 同意：结果是「同意」加宿主签发的 approval_id，并记下 option_id。 |
| 93 | `UserConfirmRoundTripTest` | `test_cancel_posts_empty_confirm_and_submits_nothing` | 模态的「取消」发空 `confirm`：不能把它当成一次用户发言送出去。 |
| 94 | `UserConfirmRoundTripTest` | `test_choice_is_filled_back_as_the_tool_result` | 直通：用户的选择被写成那次 `user_confirm` 调用的返回值，不是新用户发言。 |
| 95 | `UserConfirmRoundTripTest` | `test_confirm_id_and_text_together_do_both` | 两者同时给：门控解锁 + 选择回填（同一个端点的两类语义）。 |
| 96 | `UserConfirmRoundTripTest` | `test_confirm_text_does_not_answer_an_approval` | 选项文本不能冒充审批结果，待审批保持原样。 |
| 97 | `UserConfirmRoundTripTest` | `test_invalid_conversation_id_rejected` | 覆盖「确认的回路：用户在模态里选完，选择必须真的送到模型」：invalid conversation id rejected |
| 98 | `UserConfirmRoundTripTest` | `test_mesh_failure_reports_error_without_raising` | `mesh` 不可用时给结构化错误，不要抛——确认端点是 UI 的关键路径。 |
| 99 | `UserConfirmRoundTripTest` | `test_reject_returns_disagree_and_stores_nothing` | 驳回：结果是「不同意」，不签发通行证。 |
| 100 | `UserConfirmRoundTripTest` | `test_write_gate_confirm_id_still_works` | 带 `confirm_id` 的写盘确认走内核既有的门控解锁，不经 mesh。 |
| 101 | `WireHygieneTest` | `test_channel_emits_heartbeat_when_idle` | 空闲时发心跳（经典界面靠它判连接存活）；非 `data:` 行经典界面会安全忽略。 |
| 102 | `WireHygieneTest` | `test_cid_exempt_set_matches_contract` | 契约豁免的事件必须在前端先接住，否则会被静默丢掉。 |
| 103 | `WireHygieneTest` | `test_detach_stops_delivery` | 覆盖「传输层铁律：帧格式与 `conversation_id`」：detach stops delivery |
| 104 | `WireHygieneTest` | `test_every_frame_carries_valid_conversation_id` | 没带合法 cid 的帧会被经典界面整包静默丢弃（`classic/js/chat/stream.js` 的 `drainChatSseFromResponse`）。 |
| 105 | `WireHygieneTest` | `test_frame_without_cid_is_dropped_silently` | 入站事件没有 cid 时直接丢，不要造一个假 cid 塞给前端。 |
| 106 | `WireHygieneTest` | `test_frames_broadcast_to_every_channel` | 广播而非共享队列：两个标签页必须各自收到完整事件流。 |
| 107 | `WireHygieneTest` | `test_heartbeat_is_cid_exempt` | 覆盖「传输层铁律：帧格式与 `conversation_id`」：heartbeat is cid exempt |
| 108 | `WireHygieneTest` | `test_normalize_cid_matches_ui_rule` | 经典界面的规则是 `/^[A-Za-z0-9_-]{8,128}$/`（`classic/js/core/boot.js` 的 `normalizeConversationId`）。 |
| 109 | `WireHygieneTest` | `test_sse_payload_is_single_line_data_frame` | 帧格式必须是 `data: <单行 json>\n\n`（`classic/js/chat/stream.js` 的 `drainChatSseFromResponse`）。 |
| 110 | `WireHygieneTest` | `test_tool_script_mapping_covers_known_tools` | 工具名要翻成经典界面认识的 `script`，否则图标与中文名退化成默认。 |

## test_cli_shell.py

共 20 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChatArgParsingTest` | `test_build_session_accepts_parsed_args` | 覆盖「入口参数在装配之前解析：缺配置时 `--help` 仍可用」：build session accepts parsed args |
| 2 | `ChatArgParsingTest` | `test_help_exits_before_building_app` | 覆盖「入口参数在装配之前解析：缺配置时 `--help` 仍可用」：help exits before building app |
| 3 | `ChatArgParsingTest` | `test_session_and_text_are_parsed` | 覆盖「入口参数在装配之前解析：缺配置时 `--help` 仍可用」：session and text are parsed |
| 4 | `ChatConfirmRoundTripTest` | `test_default_bucket_gate_cannot_confirm_named_session` | 反面：默认桶门控确认不了具名会话的预览。 |
| 5 | `ChatConfirmRoundTripTest` | `test_preview_tool_names_include_write_path_tools` | 覆盖「端到端：壳层确认回调 → 模型凭同一 ID 提交（真实文件落盘）」：preview tool names include write path tools |
| 6 | `ChatConfirmRoundTripTest` | `test_shell_confirm_releases_preview_and_commit_lands` | 覆盖「端到端：壳层确认回调 → 模型凭同一 ID 提交（真实文件落盘）」：shell confirm releases preview and commit lands |
| 7 | `ChatExitReleaseTest` | `test_main_prints_session_on_exit` | 覆盖「交互壳退出时释放会话运行态」：main prints session on exit |
| 8 | `ChatExitReleaseTest` | `test_main_releases_session_on_exit` | 覆盖「交互壳退出时释放会话运行态」：main releases session on exit |
| 9 | `ChatExitReleaseTest` | `test_released_session_reparses_clean` | 释放后同 cid 重新解析得到干净上下文（红灯 / 待 review 不残留）。 |
| 10 | `ChatGateWiringTest` | `test_build_session_returns_named_conversation` | 覆盖「壳层门控解析：必须是会话自己的门控，不是默认桶」：build session returns named conversation |
| 11 | `ChatGateWiringTest` | `test_build_session_uses_shared_runner_engine` | 覆盖「壳层门控解析：必须是会话自己的门控，不是默认桶」：build session uses shared runner engine |
| 12 | `ChatGateWiringTest` | `test_engine_runs_on_same_conversation_id` | 覆盖「壳层门控解析：必须是会话自己的门控，不是默认桶」：engine runs on same conversation id |
| 13 | `ChatGateWiringTest` | `test_gate_is_the_conversation_gate_not_default_bucket` | 覆盖「壳层门控解析：必须是会话自己的门控，不是默认桶」：gate is the conversation gate not default bucket |
| 14 | `ChatToolEventTest` | `test_success_is_not_reported_as_failure` | 覆盖「工具事件显示：成功是 tool_done，失败才是 tool_failed」：success is not reported as failure |
| 15 | `ExplicitReleaseTest` | `test_close_all_clears_registry` | 覆盖「会话上下文显式释放（不引入自动淘汰）」：close all clears registry |
| 16 | `ExplicitReleaseTest` | `test_release_does_not_touch_persisted_records` | 释放只丢进程内运行态：会话记录（事实源）不受影响。 |
| 17 | `ExplicitReleaseTest` | `test_release_drops_only_that_conversation` | 覆盖「会话上下文显式释放（不引入自动淘汰）」：release drops only that conversation |
| 18 | `ExplicitReleaseTest` | `test_release_unknown_and_blank_are_safe` | 覆盖「会话上下文显式释放（不引入自动淘汰）」：release unknown and blank are safe |
| 19 | `ExplicitReleaseTest` | `test_web_release_conversation_reduces_active_count` | 关闭会话 API 调用 release 后 active_count 下降。 |
| 20 | `InvalidSessionCliTest` | `test_invalid_session_returns_clean_error` | 覆盖「A class whose instances are single test cases」：invalid session returns clean error |

## test_command_tools.py

共 30 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CancelKillsProcessTest` | `test_cancel_kills_the_child_process_and_returns_quickly` | 覆盖「停止要真的停子进程：只退出内核循环不够」：cancel kills the child process and returns quickly |
| 2 | `CancelWiringTest` | `test_scope_without_cancel_check_is_safe` | 没传入检查函数时 `canceled()` 必须是 False；检查函数自己出错必须把异常抛出去。 |
| 3 | `CancelWiringTest` | `test_tool_port_passes_the_cancel_check_into_the_scope` | 覆盖「停止检查必须从模块一路带到工具（装配层，不是工具自己猜）」：tool port passes the cancel check into the scope |
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

共 11 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AISpeakRuntimeContentionTest` | `test_many_threads_keep_every_segment` | 覆盖「AI说话运行时：多线程向同一会话入队不丢段、不重复、顺序可核」：many threads keep every segment |
| 2 | `ContextSourcesContentionTest` | `test_collect_sees_a_consistent_snapshot` | 覆盖「注入源注册表：并发注册/卸载后条目数与版本号仍然自洽」：collect sees a consistent snapshot |
| 3 | `ContextSourcesContentionTest` | `test_register_and_dispose_are_balanced` | 覆盖「注入源注册表：并发注册/卸载后条目数与版本号仍然自洽」：register and dispose are balanced |
| 4 | `LiveStateContentionTest` | `test_distinct_conversations_do_not_interfere` | 覆盖「实时状态：不同会话互不串写；同一会话的并发写不丢结构」：distinct conversations do not interfere |
| 5 | `LiveStateContentionTest` | `test_same_conversation_writes_stay_well_formed` | 覆盖「实时状态：不同会话互不串写；同一会话的并发写不丢结构」：same conversation writes stay well formed |
| 6 | `ModelCatalogContentionTest` | `test_provider_cache_is_keyed_by_entry_fingerprint` | 覆盖「模型目录：热替换期间快照不得混批，provider 缓存不得把旧实例交给新条目」：provider cache is keyed by entry fingerprint |
| 7 | `ModelCatalogContentionTest` | `test_snapshot_is_never_mixed_during_replacement` | 覆盖「模型目录：热替换期间快照不得混批，provider 缓存不得把旧实例交给新条目」：snapshot is never mixed during replacement |
| 8 | `PendingStoreContentionTest` | `test_capacity_is_never_exceeded` | 覆盖「预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立」：capacity is never exceeded |
| 9 | `PendingStoreContentionTest` | `test_confirm_is_visible_to_concurrent_peek` | 覆盖「预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立」：confirm is visible to concurrent peek |
| 10 | `PendingStoreContentionTest` | `test_same_path_keeps_exactly_one_latest` | 覆盖「预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立」：same path keeps exactly one latest |
| 11 | `PendingStoreContentionTest` | `test_take_is_exactly_once` | 覆盖「预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立」：take is exactly once |

## test_config_values.py

共 2 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ConfigValueFallbackTest` | `test_bad_numeric_values_fall_back_to_defaults` | 覆盖「A class whose instances are single test cases」：bad numeric values fall back to defaults |
| 2 | `ConfigValueFallbackTest` | `test_compression_threshold_coerces_bool_and_strings` | 覆盖「A class whose instances are single test cases」：compression threshold coerces bool and strings |

## test_context_assembly.py

共 187 个用例。

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
| 21 | `CompactionContext` | `test_instruction_appears_once` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：instruction appears once |
| 22 | `CompactionContext` | `test_instruction_is_last_and_system` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：instruction is last and system |
| 23 | `CompactionContext` | `test_mode_change_does_not_affect_request` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：mode change does not affect request |
| 24 | `CompactionContext` | `test_no_new_input_path` | 没有新输入时，尾部只有模式一条；压缩请求 = 整份剔掉它 + 指令。 |
| 25 | `CompactionContext` | `test_prefix_equals_normal_request_minus_last_two` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：prefix equals normal request minus last two |
| 26 | `CompactionContext` | `test_summary_present_in_head` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：summary present in head |
| 27 | `CompactionContext` | `test_system_field_is_carried` | `system` 字段与平常请求同一个值（留空即从第一条起就不同）。 |
| 28 | `CompactionContext` | `test_tool_path_prefix_equals_normal_minus_last_one` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：tool path prefix equals normal minus last one |
| 29 | `CompactionContext` | `test_tool_path_request_shape` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：tool path request shape |
| 30 | `CompactionContext` | `test_tools_are_forwarded` | 工具定义是前缀的一部分：摘要请求必须带上同一份。 |
| 31 | `CompactionContext` | `test_user_path_drops_mode` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：user path drops mode |
| 32 | `CompactionContext` | `test_user_path_drops_new_input` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：user path drops new input |
| 33 | `CompactionContext` | `test_user_path_request_shape` | 覆盖「压缩上下文：剔除本回合新输入与执行模式，末尾接 system 指令」：user path request shape |
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
| 48 | `CompactionLoop` | `test_second_compaction_appends_second_summary` | 第二次压缩产出的摘要追加在已有摘要之后，不合并、不替换。 |
| 49 | `CompactionLoop` | `test_summary_appended_with_bridge` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：summary appended with bridge |
| 50 | `CompactionLoop` | `test_summary_messages_are_system` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：summary messages are system |
| 51 | `CompactionLoop` | `test_summary_text_comes_from_model` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：summary text comes from model |
| 52 | `CompactionLoop` | `test_summary_text_excludes_bridge` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：summary text excludes bridge |
| 53 | `CompactionLoop` | `test_view_messages_drops_covered` | 覆盖「覆盖点推进、摘要累积、重拼后的请求」：view messages drops covered |
| 54 | `Invariants` | `test_every_request_ends_with_instruction` | 覆盖「任何一条压缩请求都必须满足的硬约束」：every request ends with instruction |
| 55 | `Invariants` | `test_every_request_has_all_kb` | 覆盖「任何一条压缩请求都必须满足的硬约束」：every request has all kb |
| 56 | `Invariants` | `test_every_request_has_all_skills` | 覆盖「任何一条压缩请求都必须满足的硬约束」：every request has all skills |
| 57 | `Invariants` | `test_every_request_has_system_prompt` | 覆盖「任何一条压缩请求都必须满足的硬约束」：every request has system prompt |
| 58 | `Invariants` | `test_head_prefix_is_identical_across_requests` | 覆盖「任何一条压缩请求都必须满足的硬约束」：head prefix is identical across requests |
| 59 | `Invariants` | `test_instruction_text_is_stable` | 覆盖「任何一条压缩请求都必须满足的硬约束」：instruction text is stable |
| 60 | `Invariants` | `test_no_request_has_mode` | 覆盖「任何一条压缩请求都必须满足的硬约束」：no request has mode |
| 61 | `Invariants` | `test_summaries_survive_every_request` | 覆盖「任何一条压缩请求都必须满足的硬约束」：summaries survive every request |
| 62 | `LayoutFromMessages` | `test_dialogue_starts_at_the_first_user` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：dialogue starts at the first user |
| 63 | `LayoutFromMessages` | `test_empty_input` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：empty input |
| 64 | `LayoutFromMessages` | `test_given_system_text_is_used_and_not_double_counted` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：given system text is used and not double counted |
| 65 | `LayoutFromMessages` | `test_head_first_message_is_the_system_prompt` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：head first message is the system prompt |
| 66 | `LayoutFromMessages` | `test_last_head_message_is_the_summary` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：last head message is the summary |
| 67 | `LayoutFromMessages` | `test_mode_is_split_out` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：mode is split out |
| 68 | `LayoutFromMessages` | `test_mode_not_counted_as_dialogue` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：mode not counted as dialogue |
| 69 | `LayoutFromMessages` | `test_no_mode_means_no_mode_segment` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：no mode means no mode segment |
| 70 | `LayoutFromMessages` | `test_remaining_is_last` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：remaining is last |
| 71 | `LayoutFromMessages` | `test_total_equals_segments_sum` | 覆盖「兜底口径：没有装配快照的旧会话也分层（按位置切段）」：total equals segments sum |
| 72 | `LayoutPayload` | `test_budget_never_below_used` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：budget never below used |
| 73 | `LayoutPayload` | `test_last_segment_is_remaining` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：last segment is remaining |
| 74 | `LayoutPayload` | `test_no_tail_means_no_mode_segment` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：no tail means no mode segment |
| 75 | `LayoutPayload` | `test_payload_shape` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：payload shape |
| 76 | `LayoutPayload` | `test_pct_sums_to_100` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：pct sums to 100 |
| 77 | `LayoutPayload` | `test_tail_becomes_mode_segment` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：tail becomes mode segment |
| 78 | `LayoutPayload` | `test_total_matches_segments_minus_remaining` | 覆盖「快照载荷：段 + 剩余容量 + 预算」：total matches segments minus remaining |
| 79 | `LayoutWithHead` | `test_dialogue_does_not_include_head` | 覆盖「兜底带装配出来的头部：能分清 Skills / 知识库 / 摘要」：dialogue does not include head |
| 80 | `LayoutWithHead` | `test_mode_splits_from_dialogue` | 覆盖「兜底带装配出来的头部：能分清 Skills / 知识库 / 摘要」：mode splits from dialogue |
| 81 | `LayoutWithHead` | `test_plugin_segments_are_one_row_each` | 同一插件两段各成一行，段名与数量都按描述来。 |
| 82 | `LayoutWithHead` | `test_same_key_and_label_are_merged_in_layout` | 同一插件同一段名的多条消息只显示一行；count 取来源自报总数。 |
| 83 | `LayoutWithHead` | `test_total_equals_sum_without_remaining` | 覆盖「兜底带装配出来的头部：能分清 Skills / 知识库 / 摘要」：total equals sum without remaining |
| 84 | `LayoutWithHead` | `test_without_head_falls_back_to_position` | 不传 head：只能按位置猜，插件段落一律归到摘要之后的那一堆。 |
| 85 | `MaskIsHard` | `test_excerpt_never_touches_the_masked_tail` | 覆盖「遮盖的轮一律原样保留；压缩只在它前面发生」：excerpt never touches the masked tail |
| 86 | `MaskIsHard` | `test_excerpt_starts_at_zero` | 覆盖「遮盖的轮一律原样保留；压缩只在它前面发生」：excerpt starts at zero |
| 87 | `MaskIsHard` | `test_region_excludes_every_system_message` | 压缩区域落在对话段里，一条 system 都不含。 |
| 88 | `MaskIsHard` | `test_region_tool_chain_closed` | 覆盖「遮盖的轮一律原样保留；压缩只在它前面发生」：region tool chain closed |
| 89 | `MaskIsHard` | `test_single_turn_is_compressed_when_nothing_else_can_be` | 只有 1 轮：遮盖前面没东西可压 → 连它一起压（压到 0 轮）。 |
| 90 | `MaskSurvivesOverflow` | `test_mask_invariant_over_random_shapes` | 随机形态：任何一次压缩之后，被遮盖的轮数必须 ≥ 配置值。 |
| 91 | `MaskSurvivesOverflow` | `test_masked_last_turn_stays_when_it_is_huge` | 核心：末尾那一回合自己就吃满预算，仍然不许压它。 |
| 92 | `MaskSurvivesOverflow` | `test_only_masked_turns_still_get_compressed` | 只有被遮盖的轮 → 连它一起压（压不动就是超上限失败）。 |
| 93 | `MaskSurvivesOverflow` | `test_reserve_two_keeps_two_turns` | 覆盖「内层管线：超阈值时遮盖仍然不被压」：reserve two keeps two turns |
| 94 | `MaskSurvivesOverflow` | `test_reserve_zero_means_no_mask` | 覆盖「内层管线：超阈值时遮盖仍然不被压」：reserve zero means no mask |
| 95 | `OrdinaryRequestNeverRewritesHistory` | `test_adding_a_turn_does_not_touch_earlier_messages` | 加一轮 → 前缀逐字节不变（只有末尾多出来）。 |
| 96 | `OrdinaryRequestNeverRewritesHistory` | `test_compression_only_drops_a_prefix` | 压缩之后对话段 = 原序列的一个后缀（不是被改写过的版本）。 |
| 97 | `OrdinaryRequestNeverRewritesHistory` | `test_tool_traffic_survives_set_dialogue` | 覆盖「普通请求只做追加：已发过的消息逐字节不变（改中间一条 = 缓存从那里起全废）」：tool traffic survives set dialogue |
| 98 | `PluginSegmentCountAlignmentTest` | `test_collect_segments_counts_match_items` | 覆盖「段与自报数量必须逐条对齐：错位是静默的，只在浮层上显示成离谱的数字」：collect segments counts match items |
| 99 | `PluginSegmentCountAlignmentTest` | `test_missing_reported_count_falls_back_to_one` | 覆盖「段与自报数量必须逐条对齐：错位是静默的，只在浮层上显示成离谱的数字」：missing reported count falls back to one |
| 100 | `PluginSegmentCountAlignmentTest` | `test_short_count_table_does_not_borrow_neighbours` | 数量表比来源表短时，多出来的段按自身条数算，不拿别的段的数字。 |
| 101 | `PluginSegmentsImmutableTest` | `test_assignment_is_rejected` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：assignment is rejected |
| 102 | `PluginSegmentsImmutableTest` | `test_containers_are_tuples` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：containers are tuples |
| 103 | `PluginSegmentsImmutableTest` | `test_source_lists_are_copied` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：source lists are copied |
| 104 | `PluginSegmentsImmutableTest` | `test_tuple_containers_reject_mutation` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：tuple containers reject mutation |
| 105 | `PluginSegmentsImmutableTest` | `test_wrong_arity_is_rejected_loudly` | 覆盖「B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不…」：wrong arity is rejected loudly |
| 106 | `RandomShapeInvariants` | `test_compaction_range_never_splits_a_turn` | ① 压缩区间首尾都必须落在用户轮边界上。 |
| 107 | `RandomShapeInvariants` | `test_compaction_range_tool_chain_always_closed` | ② 压缩区间内的工具链必须闭合（否则切出残链）。 |
| 108 | `ReasoningReplayBudgetTest` | `test_config_default_matches_constant` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：config default matches constant |
| 109 | `ReasoningReplayBudgetTest` | `test_dialogue_segment_uses_the_budget` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：dialogue segment uses the budget |
| 110 | `ReasoningReplayBudgetTest` | `test_messages_clip_does_not_mutate_input` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：messages clip does not mutate input |
| 111 | `ReasoningReplayBudgetTest` | `test_negative_keeps_everything` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：negative keeps everything |
| 112 | `ReasoningReplayBudgetTest` | `test_positive_keeps_both_ends_and_marks_the_gap` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：positive keeps both ends and marks the gap |
| 113 | `ReasoningReplayBudgetTest` | `test_short_text_untouched` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：short text untouched |
| 114 | `ReasoningReplayBudgetTest` | `test_zero_drops_everything` | 覆盖「思维链回传预算：三种取值的行为与统计口径」：zero drops everything |
| 115 | `RemainingCapacityTest` | `test_budget_zero_would_make_remaining_zero` | 不传预算（= 老装配点的行为）剩余容量就是 0 —— 这条守着别再退回去。 |
| 116 | `RemainingCapacityTest` | `test_old_snapshot_is_rescaled_on_read` | 事件里那份 `budget=已用` 的旧快照，渲染时按当前预算补正。 |
| 117 | `RemainingCapacityTest` | `test_overlay_merges_same_key_and_label` | 刷新时的插件段重算也要按 key+label 合并，不能绕过管线再拆成两行。 |
| 118 | `RemainingCapacityTest` | `test_rescale_falls_back_when_budget_unknown` | 拿不到预算时按"已用"归一（不再更差），段序与字段不变。 |
| 119 | `RemainingCapacityTest` | `test_snapshot_carries_the_budget` | 覆盖「「剩余容量」按压缩阈值算，不是按"已用"算 —— 否则界面那条永远是 0%」：snapshot carries the budget |
| 120 | `SegmentCountSemantics` | `test_dialogue_counts_user_turns_not_messages` | 覆盖「`count` 的计「个」口径按段定：头部按 system 条数，对话按用户轮数」：dialogue counts user turns not messages |
| 121 | `SegmentCountSemantics` | `test_layout_from_messages_counts_turns_too` | 覆盖「`count` 的计「个」口径按段定：头部按 system 条数，对话按用户轮数」：layout from messages counts turns too |
| 122 | `SegmentCountSemantics` | `test_system_prompt_counts_messages` | 覆盖「`count` 的计「个」口径按段定：头部按 system 条数，对话按用户轮数」：system prompt counts messages |
| 123 | `SegmentFieldParity` | `test_both_paths_expose_the_same_fields` | 覆盖「分段快照（内核事件）与兜底重算（适配层）必须给同一套字段」：both paths expose the same fields |
| 124 | `SegmentFieldParity` | `test_layout_event_forwards_every_field` | 适配层转发分段事件时不筛字段（白名单漏一个 = 前端少一样东西）。 |
| 125 | `SegmentKeysAndCounts` | `test_keys_and_labels` | 覆盖「段 key 与数量口径：插件段一律 `plugin:<插件名>`」：keys and labels |
| 126 | `SegmentKeysAndCounts` | `test_plugin_may_declare_more_than_one_segment` | 同一插件两段：数量按位置对上，不会互相覆盖。 |
| 127 | `SegmentOrderMatchesAssembly` | `test_header_order_is_system_plugins_summary` | 覆盖「分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画」：header order is system plugins summary |
| 128 | `SegmentOrderMatchesAssembly` | `test_layout_payload_keeps_the_same_order` | 覆盖「分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画」：layout payload keeps the same order |
| 129 | `SegmentOrderMatchesAssembly` | `test_segment_order_matches_header_order` | 覆盖「分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画」：segment order matches header order |
| 130 | `SegmentOrderMatchesAssembly` | `test_summary_sits_before_dialogue` | 覆盖「分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画」：summary sits before dialogue |
| 131 | `SegmentTokens` | `test_dialogue_split_into_two_segments` | 覆盖「逐段统计与段名」：dialogue split into two segments |
| 132 | `SegmentTokens` | `test_segments_sum_equals_assembled_total` | 关键一致性：分段之和 == 装配出来的消息总量（同估算器）。 |
| 133 | `SegmentTokens` | `test_summary_segment_counts_both_summaries` | 覆盖「逐段统计与段名」：summary segment counts both summaries |
| 134 | `SegmentTokens` | `test_system_segment_matches_its_message` | 覆盖「逐段统计与段名」：system segment matches its message |
| 135 | `SkillInjectionIntoRequest` | `test_empty_segments_leave_head_empty` | 覆盖「Skills 作为插件段落注入：顺序、压缩请求同源、整体重建」：empty segments leave head empty |
| 136 | `SkillInjectionIntoRequest` | `test_plugin_segments_are_not_duplicated_across_passes` | `set_plugin_segments` 是整体重建：多跑几趟不会累积。 |
| 137 | `SkillInjectionIntoRequest` | `test_plugin_segments_sit_after_system_prompt` | 覆盖「Skills 作为插件段落注入：顺序、压缩请求同源、整体重建」：plugin segments sit after system prompt |
| 138 | `SkillInjectionIntoRequest` | `test_plugin_segments_used_by_compaction_request` | 插件段落属头部：压缩请求必须带上同一份。 |
| 139 | `SkillInjectionIntoRequest` | `test_segment_stats_follow_the_plugin` | 分段统计里两段都挂在插件名下，段名与数量由插件给。 |
| 140 | `SkillInjectionIntoRequest` | `test_summary_sits_after_plugin_segments` | 覆盖「Skills 作为插件段落注入：顺序、压缩请求同源、整体重建」：summary sits after plugin segments |
| 141 | `SkillProgressiveDisclosure` | `test_auto_load_empty_when_no_auto_load_dir` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：auto load empty when no auto load dir |
| 142 | `SkillProgressiveDisclosure` | `test_auto_load_excludes_normal_skills` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：auto load excludes normal skills |
| 143 | `SkillProgressiveDisclosure` | `test_auto_load_messages_carry_bodies` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：auto load messages carry bodies |
| 144 | `SkillProgressiveDisclosure` | `test_registry_excludes_auto_load_skill` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：registry excludes auto load skill |
| 145 | `SkillProgressiveDisclosure` | `test_registry_excludes_skill_bodies` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：registry excludes skill bodies |
| 146 | `SkillProgressiveDisclosure` | `test_registry_is_absent_when_no_skills` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：registry is absent when no skills |
| 147 | `SkillProgressiveDisclosure` | `test_registry_lists_names_and_descriptions` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：registry lists names and descriptions |
| 148 | `SkillProgressiveDisclosure` | `test_skillsr_lists_normal_skills_only` | 覆盖「清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文」：skillsr lists normal skills only |
| 149 | `SourceOrderDeclaration` | `test_kernel_pipeline_follows_the_same_order` | 真管线：Skills 两段 → 知识库 → 摘要 → 对话。 |
| 150 | `SourceOrderDeclaration` | `test_no_rank_sorts_last` | 没有位次的（应用级来源，不属于任何插件）排在插件段之后。 |
| 151 | `SourceOrderDeclaration` | `test_rank_beats_registration` | 先注册知识库（位次 1）、后注册 Skills（位次 0），组装仍是 Skills 在前。 |
| 152 | `SourceOrderDeclaration` | `test_same_rank_keeps_registration_order` | 覆盖「注入源的组装顺序：插件段按插件清单位次排，注册先后不影响结果」：same rank keeps registration order |
| 153 | `StripRules` | `test_empty` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：empty |
| 154 | `StripRules` | `test_empty_mode_note_and_no_marker` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：empty mode note and no marker |
| 155 | `StripRules` | `test_kb_never_stripped` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：kb never stripped |
| 156 | `StripRules` | `test_mode_in_the_middle_untouched` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：mode in the middle untouched |
| 157 | `StripRules` | `test_mode_removed_by_exact_text` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：mode removed by exact text |
| 158 | `StripRules` | `test_mode_removed_by_marker_fallback` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：mode removed by marker fallback |
| 159 | `StripRules` | `test_new_input_removed_before_mode` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：new input removed before mode |
| 160 | `StripRules` | `test_new_input_removed_when_last` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：new input removed when last |
| 161 | `StripRules` | `test_non_dict_entry` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：non dict entry |
| 162 | `StripRules` | `test_only_last_user_removed` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：only last user removed |
| 163 | `StripRules` | `test_previous_reply_is_kept` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：previous reply is kept |
| 164 | `StripRules` | `test_summary_never_stripped` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：summary never stripped |
| 165 | `StripRules` | `test_system_prompt_never_stripped` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：system prompt never stripped |
| 166 | `StripRules` | `test_tool_result_is_kept` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：tool result is kept |
| 167 | `StripRules` | `test_two_trailing_systems_both_stripped` | 覆盖「`_context_without_new_input` / _strip_mode_tail…」：two trailing systems both stripped |
| 168 | `TailShape` | `test_mode_is_last` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：mode is last |
| 169 | `TailShape` | `test_mode_is_system_role` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：mode is system role |
| 170 | `TailShape` | `test_mode_swap_changes_only_the_last_entry` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：mode swap changes only the last entry |
| 171 | `TailShape` | `test_mode_text_is_exact` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：mode text is exact |
| 172 | `TailShape` | `test_neither` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：neither |
| 173 | `TailShape` | `test_new_input_is_user_role` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：new input is user role |
| 174 | `TailShape` | `test_no_mode_means_input_is_last` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：no mode means input is last |
| 175 | `TailShape` | `test_no_new_input_means_mode_follows_dialogue` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：no new input means mode follows dialogue |
| 176 | `TailShape` | `test_plan_mode_text_is_exact` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：plan mode text is exact |
| 177 | `TailShape` | `test_tool_result_tail` | 覆盖「尾部 = 本回合新输入 + 执行模式（模式永远最后）」：tool result tail |
| 178 | `TurnAtomicity` | `test_floor_before_first_user` | 覆盖「轮边界的定位与向下取整」：floor before first user |
| 179 | `TurnAtomicity` | `test_floor_beyond_end` | 覆盖「轮边界的定位与向下取整」：floor beyond end |
| 180 | `TurnAtomicity` | `test_floor_inside_turn_goes_back` | 覆盖「轮边界的定位与向下取整」：floor inside turn goes back |
| 181 | `TurnAtomicity` | `test_floor_on_boundary_is_identity` | 覆盖「轮边界的定位与向下取整」：floor on boundary is identity |
| 182 | `TurnAtomicity` | `test_is_boundary` | 覆盖「轮边界的定位与向下取整」：is boundary |
| 183 | `TurnAtomicity` | `test_tool_chain_balanced_missing_result` | 覆盖「轮边界的定位与向下取整」：tool chain balanced missing result |
| 184 | `TurnAtomicity` | `test_tool_chain_balanced_ok` | 覆盖「轮边界的定位与向下取整」：tool chain balanced ok |
| 185 | `TurnAtomicity` | `test_tool_chain_balanced_orphan_result` | 覆盖「轮边界的定位与向下取整」：tool chain balanced orphan result |
| 186 | `TurnAtomicity` | `test_turn_spans` | 覆盖「轮边界的定位与向下取整」：turn spans |
| 187 | `TurnAtomicity` | `test_turn_starts` | 覆盖「轮边界的定位与向下取整」：turn starts |

## test_context_config_wiring.py

共 3 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextFactoryCarriesEveryContextSettingTest` | `test_factory_passes_every_pipeline_setting` | 覆盖「`_default_context_factory` 必须把 [context] 的每一项都传给…」：factory passes every pipeline setting |
| 2 | `ContextFactoryCarriesEveryContextSettingTest` | `test_pipeline_gets_the_configured_values` | 覆盖「`_default_context_factory` 必须把 [context] 的每一项都传给…」：pipeline gets the configured values |
| 3 | `SegmentEventCarriesTheWindowTest` | `test_event_has_window_and_budget` | 覆盖「分段快照必须带上模型窗口：界面按它算占用率」：event has window and budget |

## test_context_dump.py

共 3 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextDumpTest` | `test_missing_conversation_is_an_error` | 覆盖「A class whose instances are single test cases」：missing conversation is an error |
| 2 | `ContextDumpTest` | `test_snapshot_reports_todo_progress_when_list_exists` | 覆盖「A class whose instances are single test cases」：snapshot reports todo progress when list exists |
| 3 | `ContextDumpTest` | `test_snapshot_uses_real_assembly_and_does_not_call_model` | 覆盖「A class whose instances are single test cases」：snapshot uses real assembly and does not call model |

## test_context_dump_skill.py

共 1 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextDumpSkillTest` | `test_skill_is_listed_and_readable` | 覆盖「A class whose instances are single test cases」：skill is listed and readable |

## test_context_hooks.py

共 3 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextAssemblyHooksTest` | `test_hook_receives_full_context_and_can_replace_it` | 覆盖「A class whose instances are single test cases」：hook receives full context and can replace it |
| 2 | `ContextAssemblyHooksTest` | `test_hooks_run_in_order` | 覆盖「A class whose instances are single test cases」：hooks run in order |
| 3 | `ContextAssemblyHooksTest` | `test_invalid_result_is_ignored` | 覆盖「A class whose instances are single test cases」：invalid result is ignored |

## test_context_pipeline.py

共 18 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChunksAndFlattenTest` | `test_flat_messages_to_user_rounds` | 覆盖「数据模型与展平」：flat messages to user rounds |
| 2 | `ChunksAndFlattenTest` | `test_round_and_chunk_append_semantics` | 覆盖「数据模型与展平」：round and chunk append semantics |
| 3 | `ChunksAndFlattenTest` | `test_seven_chunks_order_and_add` | 覆盖「数据模型与展平」：seven chunks order and add |
| 4 | `DefaultConfigValues` | `test_compactor_signature_matches_config` | 覆盖「配置默认值与机制层常量必须一致（三处口径：config.py / 管线常量 / 压缩器签名）」：compactor signature matches config |
| 5 | `DefaultConfigValues` | `test_other_context_defaults` | 覆盖「配置默认值与机制层常量必须一致（三处口径：config.py / 管线常量 / 压缩器签名）」：other context defaults |
| 6 | `DefaultConfigValues` | `test_summary_token_threshold_default` | 覆盖「配置默认值与机制层常量必须一致（三处口径：config.py / 管线常量 / 压缩器签名）」：summary token threshold default |
| 7 | `ExcerptTest` | `test_adjust_back_extends_over_tool_chain` | 覆盖「摘要取段与工具链完整性」：adjust back extends over tool chain |
| 8 | `ExcerptTest` | `test_adjust_extends_end_for_open_results` | 覆盖「摘要取段与工具链完整性」：adjust extends end for open results |
| 9 | `MaxPassesConfigTest` | `test_app_carries_the_value` | 覆盖「`[agent] max_passes`：一回合的操作次数上限，可配」：app carries the value |
| 10 | `MaxPassesConfigTest` | `test_bad_value_falls_back` | 写错不该让回合跑不起来：非法值回落默认，0/负数按 1。 |
| 11 | `MaxPassesConfigTest` | `test_config_value_wins` | 覆盖「`[agent] max_passes`：一回合的操作次数上限，可配」：config value wins |
| 12 | `MaxPassesConfigTest` | `test_default_is_64` | 覆盖「`[agent] max_passes`：一回合的操作次数上限，可配」：default is 64 |
| 13 | `MaxPassesConfigTest` | `test_engine_carries_the_value` | 覆盖「`[agent] max_passes`：一回合的操作次数上限，可配」：engine carries the value |
| 14 | `MemoryAndEstimateTest` | `test_append_new_msg_and_append_msg` | 覆盖「待并摘要 / 估算 / 统计 / 追加」：append new msg and append msg |
| 15 | `MemoryAndEstimateTest` | `test_pending_mem_flow` | 覆盖「待并摘要 / 估算 / 统计 / 追加」：pending mem flow |
| 16 | `MemoryAndEstimateTest` | `test_round_count` | 覆盖「待并摘要 / 估算 / 统计 / 追加」：round count |
| 17 | `MemoryAndEstimateTest` | `test_token_estimates` | 覆盖「待并摘要 / 估算 / 统计 / 追加」：token estimates |
| 18 | `RebuildTest` | `test_rebuild_from_messages` | 覆盖「时序重建（走 MVP 路径）」：rebuild from messages |

## test_context_plumbing.py

共 5 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextPlumbingTest` | `test_context_does_not_leak_outside_the_call` | 调用结束即还原：工具往返上下文不跨调用泄漏。 |
| 2 | `ContextPlumbingTest` | `test_missing_contexts_degrade_instead_of_failing` | 没有 app/session（脚本直建引擎）时仍能跑，只是相关字段为空。 |
| 3 | `ContextPlumbingTest` | `test_service_lookup_from_tool_round` | 全局能力经上下文解析（不必在构造期注入）。 |
| 4 | `ContextPlumbingTest` | `test_session_state_reachable_from_tool_round` | 会话态（门控 / 实时状态 / 待确认）直接从会话上下文取。 |
| 5 | `ContextPlumbingTest` | `test_tool_sees_all_three_contexts` | 覆盖「三级上下文在工具往返内可用」：tool sees all three contexts |

## test_context_splice.py

共 9 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AwaitingFactTest` | `test_pending_call_is_discoverable_from_facts` | 覆盖「挂起信息落盘与"待解决"判定（宿主靠它知道有调用等人）」：pending call is discoverable from facts |
| 2 | `AwaitingFactTest` | `test_pending_state_is_readable_from_facts_not_from_session_context` | 挂起状态从事实源可读 —— 判定"有待解决的调用"只凭事实就够。 |
| 3 | `ContextSpliceTest` | `test_no_staging_table_is_needed` | ② 恢复路径上不需要外部结果暂存表之类的东西：事实源里只有工具结果。 |
| 4 | `ContextSpliceTest` | `test_no_user_message_is_inserted_on_resume` | 恢复回合没有用户输入：绝不能凭空多一条 user 消息——那会让请求序列非法。 |
| 5 | `ContextSpliceTest` | `test_real_store_carries_the_splice` | ③ 用现有真实存储：确认那一刻写下结果事实就完成了拼接。 |
| 6 | `ContextSpliceTest` | `test_repeated_terminal_folds_to_one_tool_message` | 同一 `call_id` 的终态写两次时，派生对话里只有一条 tool 消息。 |
| 7 | `ContextSpliceTest` | `test_spliced_result_lands_exactly_after_the_tool_call` | ① 拼接后 `tool` 紧跟带 `tool_calls` 的 `assistant`——不插任何用户消息。 |
| 8 | `ContextSpliceTest` | `test_stale_empty_input_in_old_records_is_tolerated` | 第二道防线：会话记录里存着空的 `input_claimed` 时，派生仍必须给出合法序列。 |
| 9 | `ResumeSpliceNamingTest` | `test_written_fact_name_is_the_one_kernel_consumes` | 覆盖「`_splice_resume` 必须写内核当前认的结果事实名」：written fact name is the one kernel consumes |

## test_conversation_queue.py

共 6 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ConversationQueueTest` | `test_claimed_cannot_be_recalled_or_cancelled` | 覆盖「A class whose instances are single test cases」：claimed cannot be recalled or cancelled |
| 2 | `ConversationQueueTest` | `test_draft_resubmit_preserves_agent_origin` | 覆盖「A class whose instances are single test cases」：draft resubmit preserves agent origin |
| 3 | `ConversationQueueTest` | `test_fifo_and_state` | 覆盖「A class whose instances are single test cases」：fifo and state |
| 4 | `ConversationQueueTest` | `test_image_roundtrip_and_recall` | 覆盖「A class whose instances are single test cases」：image roundtrip and recall |
| 5 | `ConversationQueueTest` | `test_persistence_and_claimed_recovery` | 覆盖「A class whose instances are single test cases」：persistence and claimed recovery |
| 6 | `ConversationQueueTest` | `test_system_item_hidden_but_claimable` | 覆盖「A class whose instances are single test cases」：system item hidden but claimable |

## test_core.py

共 58 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ArchitectureTest` | `test_abandoned_consumer_is_reported` | 消费者中途放弃迭代时，宿主给出 `abandoned` 而不是留一个 None 结论。 |
| 2 | `ArchitectureTest` | `test_data_never_rides_on_the_return_value` | 数据只走事件：一趟跑完后事实与事件一一对应。 |
| 3 | `ArchitectureTest` | `test_events_stream_out_incrementally` | 流式：事件在产出那一刻就让出去，不是等回合跑完再一次性返回。 |
| 4 | `ArchitectureTest` | `test_every_module_returns_an_outcome_on_every_path` | 每个模块的每条路径都必须 return `Outcome`。 |
| 5 | `ArchitectureTest` | `test_halt_stops_the_chain_immediately` | 覆盖「内核自身的架构约束（判据在真实模块上重验）」：halt stops the chain immediately |
| 6 | `ArchitectureTest` | `test_host_knows_nothing_about_module_semantics` | 宿主只遍历与读四态：一条完全陌生的链也照跑。 |
| 7 | `ArchitectureTest` | `test_ports_expose_no_writable_public_fields` | 覆盖「内核自身的架构约束（判据在真实模块上重验）」：ports expose no writable public fields |
| 8 | `ArchitectureTest` | `test_runaway_chain_hits_the_guard` | 永远要求续行的模块撞护栏而不是死循环（那是模块 bug，不该拖死宿主）。 |
| 9 | `ArchitectureTest` | `test_swap_a_module_without_touching_others` | 换掉模型模块的实现，其余模块与宿主零改动。 |
| 10 | `ArchitectureTest` | `test_unknown_module_return_is_a_loud_error` | 覆盖「内核自身的架构约束（判据在真实模块上重验）」：unknown module return is a loud error |
| 11 | `BasicTurnTest` | `test_failed_tool_result_reaches_the_model_as_error` | 工具失败与成功同形：`{"ok":false,"error":…}`（来自结果事实）。 |
| 12 | `BasicTurnTest` | `test_failed_tool_with_data_keeps_envelope` | 失败附带 data 时仍是顶层 ok/error/data。 |
| 13 | `BasicTurnTest` | `test_message_sequence_is_valid_for_the_model` | 覆盖「纯文本回合：输入 → 模型 → 收尾」：message sequence is valid for the model |
| 14 | `BasicTurnTest` | `test_model_sees_the_real_tool_result_not_null` | 模型必须看到工具的真实结果——不能是 `null`。 |
| 15 | `BasicTurnTest` | `test_no_input_means_no_user_message` | 无新输入时不发 `input_claimed`（恢复回合的前提）。 |
| 16 | `BasicTurnTest` | `test_simple_answer_completes_in_one_pass` | 覆盖「纯文本回合：输入 → 模型 → 收尾」：simple answer completes in one pass |
| 17 | `BasicTurnTest` | `test_usage_is_emitted_when_provided` | 覆盖「纯文本回合：输入 → 模型 → 收尾」：usage is emitted when provided |
| 18 | `CancelTest` | `test_cancel_check_error_propagates` | 停止检查自己出错必须把异常抛出去，不得装成「未取消」。 |
| 19 | `CancelTest` | `test_canceled_batch_keeps_the_model_history_valid` | 补占位的根本理由：`assistant(tool_calls)` 必须配齐 tool 响应，否则下一回合请求被 API 拒。 |
| 20 | `CancelTest` | `test_no_cancel_check_means_no_stop` | 不传停止检查（脚本直建）时行为不变。 |
| 21 | `CancelTest` | `test_stop_before_any_tool_marks_all_as_canceled` | 入口检查点就被叫停：连模型都不叫，工具一个都不启动。 |
| 22 | `CancelTest` | `test_stop_is_recorded_as_stopped_not_paused` | `stopped` ≠ `paused` ≠ `halted`：三者语义不同，观察面靠它分辨。 |
| 23 | `CancelTest` | `test_stop_mid_batch_pads_the_remaining` | 跑到第 2 个调用前被叫停：第 1 个已完成，剩余全部补终态。 |
| 24 | `ContextSegmentsEventTest` | `test_dialogue_segment_grows_with_the_turn` | 对话段按真实内容估：把输入加大，近期记忆段必须变大。 |
| 25 | `ContextSegmentsEventTest` | `test_event_is_emitted_once_per_model_call` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：event is emitted once per model call |
| 26 | `ContextSegmentsEventTest` | `test_every_segment_has_label_and_pct` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：every segment has label and pct |
| 27 | `ContextSegmentsEventTest` | `test_last_segment_is_remaining` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：last segment is remaining |
| 28 | `ContextSegmentsEventTest` | `test_payload_has_segments_and_total` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：payload has segments and total |
| 29 | `ContextSegmentsEventTest` | `test_tool_round_emits_a_fresh_snapshot` | 工具往返会再装配一次 → 再发一条快照（分段随之变化）。 |
| 30 | `ContextSegmentsEventTest` | `test_total_is_the_sum_of_segments_without_remaining` | 覆盖「分段快照事件：每次装配完请求发一条，载荷与真实请求一致」：total is the sum of segments without remaining |
| 31 | `DedupOnFailureTest` | `test_failure_then_success_keeps_each_fact_once` | 真实装配路径：连续失败 K=1..3 → 每个事实仍只落一行。 |
| 32 | `DedupOnFailureTest` | `test_pending_queue_deduplicates_by_seq` | `_put_pending` 收到"已经排队过"的事件时不重复入队。 |
| 33 | `DedupOnFailureTest` | `test_retry_after_failure_never_duplicates_rows` | 同一事件 重复投递多次 → 磁盘上仍只有一份。 |
| 34 | `DurableRetryTest` | `test_failed_flush_survives_new_engine_each_turn` | 连续两次落盘失败 + 每回合新引擎 → 三回合的发言都要在磁盘上。 |
| 35 | `DurableRetryTest` | `test_no_failure_path_stays_clean` | 不失败时行为不变（防止"为了重试"污染正常路径）。 |
| 36 | `DurableRetryTest` | `test_retry_does_not_duplicate_rows_or_coordinates` | 重试不能造副本：`turn_started` 次数 = 回合数，坐标无重复。 |
| 37 | `InfrastructureTest` | `test_events_carry_a_storage_coordinate` | 事实必须带全局存储坐标 `_seq` —— 否则浏览器收不到 `id:`。 |
| 38 | `InfrastructureTest` | `test_facts_are_flushed_incrementally_not_only_at_turn_end` | 事实按趟增量落盘：不能攒到回合末尾（那会丢掉整回合）。 |
| 39 | `InfrastructureTest` | `test_ports_log_is_readonly` | `ports.log` 必须是只读视图 —— 否则模块能绕过 `emit` 写秘密事实。 |
| 40 | `InfrastructureTest` | `test_seq_does_not_stick_after_a_replay` | 适配层的存储坐标每事件独立 —— 回放一次不能让之后所有帧粘住旧坐标。 |
| 41 | `InfrastructureTest` | `test_suspend_emits_exactly_one_tool_end` | 挂起时同一 `tool_call_id` 只能有一帧 `tool_end`。 |
| 42 | `PortConflictTest` | `test_second_bind_on_same_port_raises` | 覆盖「端口被占时 `create_server` 必须抛错」：second bind on same port raises |
| 43 | `SessionLogViewIsolationTest` | `test_events_are_deep_copies` | 覆盖「只读视图不得让调用方穿过元素改到事实源」：events are deep copies |
| 44 | `StoreIntegrationTest` | `test_facts_persist_and_reload` | 覆盖「写入的事实能落进现有 `SessionStore`，且重启后能重建」：facts persist and reload |
| 45 | `SuspendBatchTest` | `test_placeholder_says_why_not_just_null` | 占位内容要说明原因，不能是空串或 `null`。 |
| 46 | `SuspendBatchTest` | `test_request_sequence_stays_valid_when_user_talks_instead_of_answering` | 挂起后用户不答确认、直接发新消息 → 请求序列仍必须合法。 |
| 47 | `SuspendBatchTest` | `test_suspend_mid_batch_gives_the_rest_a_terminal_fact` | 一条消息要求 [ask_user(c1), echo(c2)]，c1 挂起时 c2 必须有终态事实。 |
| 48 | `SuspendResumeTest` | `test_real_user_confirm_records_pending_confirm` | 覆盖「工具需要外部输入 → 挂起（终态）；用户作答 → 拼接结果 → 新回合」：real user confirm records pending confirm |
| 49 | `SuspendResumeTest` | `test_resume_needs_no_memory_state` | 恢复不依赖任何内存游标：丢掉宿主与模块，仅凭事实重建即可。 |
| 50 | `SuspendResumeTest` | `test_resume_splices_result_and_model_continues` | 覆盖「工具需要外部输入 → 挂起（终态）；用户作答 → 拼接结果 → 新回合」：resume splices result and model continues |
| 51 | `SuspendResumeTest` | `test_second_splice_would_duplicate_so_delivery_is_once` | 拼接没有幂等性：同一 `call_id` 交两次即非法。宿主须写前查重。 |
| 52 | `SuspendResumeTest` | `test_suspend_is_terminal_and_writes_no_tool_result` | 覆盖「工具需要外部输入 → 挂起（终态）；用户作答 → 拼接结果 → 新回合」：suspend is terminal and writes no tool result |
| 53 | `SuspendResumeTest` | `test_suspended_call_is_not_retried_within_the_turn` | 覆盖「工具需要外部输入 → 挂起（终态）；用户作答 → 拼接结果 → 新回合」：suspended call is not retried within the turn |
| 54 | `ToolLoopTest` | `test_tool_call_then_model_continues` | 覆盖「工具调用驱动多趟：续行由事实末端表达，不需要谁发续行信号」：tool call then model continues |
| 55 | `ToolLoopTest` | `test_tool_is_not_executed_twice` | 覆盖「工具调用驱动多趟：续行由事实末端表达，不需要谁发续行信号」：tool is not executed twice |
| 56 | `ToolLoopTest` | `test_two_round_trips` | 覆盖「工具调用驱动多趟：续行由事实末端表达，不需要谁发续行信号」：two round trips |
| 57 | `WiringTest` | `test_factory_receives_every_dependency_it_is_given` | `build_engine` 收到的依赖必须真的传进引擎（防"收了不用"）。 |
| 58 | `WiringTest` | `test_live_events_carry_a_storage_coordinate_through_app_session` | 经 `App.session` 跑一个回合，总线上的事件必须带 `_seq`。 |

## test_coverage_gaps.py

共 10 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `HostEventHelperTest` | `test_cancel_and_max_pass_events` | 覆盖「A class whose instances are single test cases」：cancel and max pass events |
| 2 | `HostEventHelperTest` | `test_terminal_event_covers_all_three_states` | 覆盖「A class whose instances are single test cases」：terminal event covers all three states |
| 3 | `ImageHelperTest` | `test_positions_select_and_strip` | 覆盖「A class whose instances are single test cases」：positions select and strip |
| 4 | `ImageHelperTest` | `test_strip_old_images_negative_limits` | 覆盖「A class whose instances are single test cases」：strip old images negative limits |
| 5 | `ModelHelperTest` | `test_build_request_without_context` | 覆盖「A class whose instances are single test cases」：build request without context |
| 6 | `ModelHelperTest` | `test_stream_cancel_returns_stopped` | 覆盖「A class whose instances are single test cases」：stream cancel returns stopped |
| 7 | `ModelHelperTest` | `test_stream_failure_returns_state` | 覆盖「A class whose instances are single test cases」：stream failure returns state |
| 8 | `ModelHelperTest` | `test_stream_parts_usage_and_tool_calls` | 覆盖「A class whose instances are single test cases」：stream parts usage and tool calls |
| 9 | `ToolHelperTest` | `test_cancel_rest_emits_pair_for_every_call` | 覆盖「A class whose instances are single test cases」：cancel rest emits pair for every call |
| 10 | `ToolHelperTest` | `test_result_events_cover_success_and_failure` | 覆盖「A class whose instances are single test cases」：result events cover success and failure |

## test_edited_files.py

共 1 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `EditedFilesPageTest` | `test_list_is_assembled_on_the_live_stream_only` | 覆盖「A class whose instances are single test cases」：list is assembled on the live stream only |

## test_entry_layer.py

共 19 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `BuildShellAppTest` | `test_default_data_root_is_used_when_omitted` | 覆盖「`build_shell_app`：默认交给多模型插件；显式 provider 原样使用」：default data root is used when omitted |
| 2 | `BuildShellAppTest` | `test_default_starts_without_model` | 覆盖「`build_shell_app`：默认交给多模型插件；显式 provider 原样使用」：default starts without model |
| 3 | `BuildShellAppTest` | `test_given_provider_and_store_are_used` | 覆盖「`build_shell_app`：默认交给多模型插件；显式 provider 原样使用」：given provider and store are used |
| 4 | `BuildShellAppTest` | `test_repository_config_has_no_model_section` | 覆盖「`build_shell_app`：默认交给多模型插件；显式 provider 原样使用」：repository config has no model section |
| 5 | `CliEntryTest` | `test_main_delegates_to_chat_main` | 覆盖「`agent.entry.cli`：配置检查在入口做，`chat.main` 只拿到 app 工…」：main delegates to chat main |
| 6 | `CliEntryTest` | `test_no_models_returns_none` | 覆盖「`agent.entry.cli`：配置检查在入口做，`chat.main` 只拿到 app 工…」：no models returns none |
| 7 | `HeadlessEntryTest` | `test_default_factory_wires_session_store` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：default factory wires session store |
| 8 | `HeadlessEntryTest` | `test_main_defaults_to_smoke_text` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：main defaults to smoke text |
| 9 | `HeadlessEntryTest` | `test_main_fails_when_model_is_missing` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：main fails when model is missing |
| 10 | `HeadlessEntryTest` | `test_main_passes_first_argument_and_uses_factory` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：main passes first argument and uses factory |
| 11 | `HeadlessEntryTest` | `test_real_app_uses_full_prompt_and_dynamic_mode_note` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：real app uses full prompt and dynamic mode note |
| 12 | `HeadlessEntryTest` | `test_run_prints_one_line_per_event` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：run prints one line per event |
| 13 | `HeadlessEntryTest` | `test_run_session_maps_terminal_states` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：run session maps terminal states |
| 14 | `HeadlessEntryTest` | `test_run_session_returns_generated_cid` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：run session returns generated cid |
| 15 | `HeadlessEntryTest` | `test_run_session_timeout_cancels` | 覆盖「`agent.entry.headless`：装配在入口，壳只负责跑一个回合并打印」：run session timeout cancels |
| 16 | `WebMainTest` | `test_args_are_forwarded_to_shell_serve` | 覆盖「`agent.entry.web.main`：解析参数 → 装配 → 交给壳；真正的装配故障返回…」：args are forwarded to shell serve |
| 17 | `WebMainTest` | `test_empty_fs_root_passes_none` | 覆盖「`agent.entry.web.main`：解析参数 → 装配 → 交给壳；真正的装配故障返回…」：empty fs root passes none |
| 18 | `WebMainTest` | `test_open_flag_uses_main_page_without_model` | 覆盖「`agent.entry.web.main`：解析参数 → 装配 → 交给壳；真正的装配故障返回…」：open flag uses main page without model |
| 19 | `WebMainTest` | `test_unexpected_build_error_returns_2` | 覆盖「`agent.entry.web.main`：解析参数 → 装配 → 交给壳；真正的装配故障返回…」：unexpected build error returns 2 |

## test_environment_info.py

共 1 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `EnvironmentSectionTest` | `test_section_is_after_resource_and_before_coding` | 覆盖「A class whose instances are single test cases」：section is after resource and before coding |

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
| 1 | `ClassicToolResultTest` | `test_await_user_intermediate_result_does_not_reach_the_model` | 标了 `await_user` 的中间结果不交给模型（按定义还没返回）。 |
| 2 | `ClassicToolResultTest` | `test_cancel_without_a_closing_terminal_still_reaches_the_model` | 取消只写下 tool_failed、没有第二条终态时，模型仍要看到取消，而不是被请去重问。 |
| 3 | `ClassicToolResultTest` | `test_new_format_result_is_not_duplicated` | 新格式（`tool_done` + `tool_ended`）下不得因为认 `tool_result` 而多一条。 |
| 4 | `ClassicToolResultTest` | `test_user_answer_survives_in_the_tool_message` | 覆盖「历史记录里的 `tool_result` 结果事实必须仍被消费」：user answer survives in the tool message |

## test_file_safety.py

共 24 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `LayoutTest` | `test_broken_metadata_only_affects_its_own_version` | 覆盖「结构：<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：broken metadata only affects its own version |
| 2 | `LayoutTest` | `test_create_returns_none_for_missing_file` | 覆盖「结构：<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：create returns none for missing file |
| 3 | `LayoutTest` | `test_directory_names_carry_no_filename` | 目录名一律是短码 + 时间戳 —— 不塞文件名，也就不出现一串 `_`。 |
| 4 | `LayoutTest` | `test_files_are_grouped_by_path_hash` | 同一文件的所有版本在同一个哈希目录下。 |
| 5 | `LayoutTest` | `test_list_for_is_newest_first` | 覆盖「结构：<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：list for is newest first |
| 6 | `LayoutTest` | `test_long_diff_is_clipped_and_marked` | 超长 diff 截断后要标明截断了 —— 静默截断会被读成"改动就这么点"。 |
| 7 | `LayoutTest` | `test_read_returns_the_bytes_that_were_backed_up` | 覆盖「结构：<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：read returns the bytes that were backed up |
| 8 | `LayoutTest` | `test_same_second_versions_keep_chronological_order` | 同一秒内的多次改动必须能排出先后 —— 时间戳要精确到毫秒。 |
| 9 | `LayoutTest` | `test_two_different_files_never_share_a_group` | 中文名不同的两个文件必须各自一组（净化方案下会互相分不开）。 |
| 10 | `LayoutTest` | `test_unknown_mod_id_is_none` | 覆盖「结构：<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：unknown mod id is none |
| 11 | `LayoutTest` | `test_versions_are_self_describing` | 覆盖「结构：<root>/<路径哈希>/<版本目录>/{original,metadata.json…」：versions are self describing |
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

共 9 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChangePayloadTest` | `test_new_file_flag_for_empty_old` | 旧内容为空表示新文件；这一判定不依赖被删掉的字段。 |
| 2 | `ChangePayloadTest` | `test_payload_has_only_diff_not_full_text` | 字段集合固定：有 diff 与统计，没有 old_text/new_text。 |
| 3 | `FourStepGateTest` | `test_happy_path_four_steps` | 四步全流程：预览 → 确认 → 提交（真实写入）→ 重读。 |
| 4 | `FourStepGateTest` | `test_no_preview_denied` | 无预览的直接提交被拒。 |
| 5 | `FourStepGateTest` | `test_pending_cap_evicts_oldest` | 未提交预览满额时，新登记挤掉最旧的一条。 |
| 6 | `FourStepGateTest` | `test_reread_required_for_next_edit` | 写后未重读前，再次提交被拒；read 后放行。 |
| 7 | `FourStepGateTest` | `test_same_path_keeps_only_latest_preview` | 同一写目标再次预览时，旧 confirm_id 被挤掉。 |
| 8 | `FourStepGateTest` | `test_snapshot_binding_and_single_use` | 提交内容以快照为准；confirm_id 一次性。 |
| 9 | `FourStepGateTest` | `test_unconfirmed_preview_denied` | 协议顺序：预览后未确认即提交，被拒。 |

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

## test_frozen_data_root.py

共 3 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `FrozenDataRootTest` | `test_env_override_wins_over_frozen` | 覆盖「A class whose instances are single test cases」：env override wins over frozen |
| 2 | `FrozenDataRootTest` | `test_frozen_uses_user_data_root` | 覆盖「A class whose instances are single test cases」：frozen uses user data root |
| 3 | `FrozenDataRootTest` | `test_windows_user_data_root` | 覆盖「A class whose instances are single test cases」：windows user data root |

## test_gate_negative.py

共 67 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AcceptanceSkipGateTest` | `test_duplicates_do_not_count_twice` | 覆盖「验收 skip：预算上限与白名单都必须能触发」：duplicates do not count twice |
| 2 | `AcceptanceSkipGateTest` | `test_non_whitelisted_fails` | 覆盖「验收 skip：预算上限与白名单都必须能触发」：non whitelisted fails |
| 3 | `AcceptanceSkipGateTest` | `test_over_budget_fails` | 覆盖「验收 skip：预算上限与白名单都必须能触发」：over budget fails |
| 4 | `AcceptanceSkipGateTest` | `test_whitelisted_within_budget_passes` | 覆盖「验收 skip：预算上限与白名单都必须能触发」：whitelisted within budget passes |
| 5 | `ApplicabilityGateTest` | `test_counts_and_ratio_visible` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则、缺表」：counts and ratio visible |
| 6 | `ApplicabilityGateTest` | `test_english_header_and_value_pass` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则、缺表」：english header and value pass |
| 7 | `ApplicabilityGateTest` | `test_missing_table_fails` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则、缺表」：missing table fails |
| 8 | `ApplicabilityGateTest` | `test_rule_ids_are_wellformed` | 编号格式错会让整张表无法申报；分节标题混进来会稀释占比。 |
| 9 | `ApplicabilityGateTest` | `test_short_reason_fails` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则、缺表」：short reason fails |
| 10 | `ApplicabilityGateTest` | `test_stale_id_fails_through_main` | 端到端：拿真实编号集合比对一条不存在的编号，门禁必须退出 1。 |
| 11 | `ApplicabilityGateTest` | `test_unknown_rule_id_fails` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则、缺表」：unknown rule id fails |
| 12 | `ApplicabilityGateTest` | `test_well_formed_row_passes` | 覆盖「例外申报表：列数、准则编号、原因长度、未知准则、缺表」：well formed row passes |
| 13 | `ArchitectureHygieneGateTest` | `test_cross_layer_private_import_fails` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：cross layer private import fails |
| 14 | `ArchitectureHygieneGateTest` | `test_plugin_name_in_core_fails` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：plugin name in core fails |
| 15 | `ArchitectureHygieneGateTest` | `test_quality_gate_real_module_passes` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：quality gate real module passes |
| 16 | `ArchitectureHygieneGateTest` | `test_quality_gate_shim_import_fails` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：quality gate shim import fails |
| 17 | `ArchitectureHygieneGateTest` | `test_same_layer_private_import_passes` | 覆盖「跨层私有导入 / 内核插件名 / quality_gate 回流」：same layer private import passes |
| 18 | `CommentStyleGateTest` | `test_clean_comment_passes` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：clean comment passes |
| 19 | `CommentStyleGateTest` | `test_code_unpacking_is_not_emphasis` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：code unpacking is not emphasis |
| 20 | `CommentStyleGateTest` | `test_command_to_reader_fails` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：command to reader fails |
| 21 | `CommentStyleGateTest` | `test_markdown_emphasis_across_lines_fails` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：markdown emphasis across lines fails |
| 22 | `CommentStyleGateTest` | `test_markdown_emphasis_comment_fails` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：markdown emphasis comment fails |
| 23 | `CommentStyleGateTest` | `test_string_literal_is_not_comment` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：string literal is not comment |
| 24 | `CommentStyleGateTest` | `test_todo_comment_fails` | 覆盖「注释文案：只吃注释/文档串，代码里的同名词不误伤」：todo comment fails |
| 25 | `ComplexityGateTest` | `test_big_file_fails_without_registry` | 覆盖「复杂度：任何超阈值文件/函数都必须失败，没有豁免表」：big file fails without registry |
| 26 | `ComplexityGateTest` | `test_generated_doc_drift_is_reported` | 覆盖「复杂度：任何超阈值文件/函数都必须失败，没有豁免表」：generated doc drift is reported |
| 27 | `ConfigDriftGateTest` | `test_model_plugin_rejects_unknown_key` | 覆盖「配置漂移：真实文件只允许使用 schema 登记的键」：model plugin rejects unknown key |
| 28 | `ConfigDriftGateTest` | `test_real_file_extra_key_reports_line_number` | 覆盖「配置漂移：真实文件只允许使用 schema 登记的键」：real file extra key reports line number |
| 29 | `ConfigDriftGateTest` | `test_real_file_subset_passes` | 覆盖「配置漂移：真实文件只允许使用 schema 登记的键」：real file subset passes |
| 30 | `ConfigDriftGateTest` | `test_unknown_section_fails` | 覆盖「配置漂移：真实文件只允许使用 schema 登记的键」：unknown section fails |
| 31 | `ConfigModelExampleGateTest` | `test_compare_model_example_detects_changed_section` | 覆盖「A class whose instances are single test cases」：compare model example detects changed section |
| 32 | `ConfigModelExampleGateTest` | `test_compare_model_example_detects_extra_key` | 覆盖「A class whose instances are single test cases」：compare model example detects extra key |
| 33 | `ConfigModelExampleGateTest` | `test_compare_model_example_positive` | 覆盖「A class whose instances are single test cases」：compare model example positive |
| 34 | `ConfigModelExampleGateTest` | `test_compare_model_example_requires_keys` | 覆盖「A class whose instances are single test cases」：compare model example requires keys |
| 35 | `ConfirmWordingGateTest` | `test_compliant_wording_passes` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：compliant wording passes |
| 36 | `ConfirmWordingGateTest` | `test_explanatory_wording_fails` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：explanatory wording fails |
| 37 | `ConfirmWordingGateTest` | `test_gate_without_next_step_fails` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：gate without next step fails |
| 38 | `ConfirmWordingGateTest` | `test_missing_unlock_tool_fails` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：missing unlock tool fails |
| 39 | `ConfirmWordingGateTest` | `test_vague_wording_fails` | 覆盖「写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败」：vague wording fails |
| 40 | `CoverageGateTest` | `test_at_or_above_floor_passes` | 覆盖「覆盖率：低于下限、缺数据都要失败」：at or above floor passes |
| 41 | `CoverageGateTest` | `test_below_floor_fails` | 覆盖「覆盖率：低于下限、缺数据都要失败」：below floor fails |
| 42 | `CoverageGateTest` | `test_missing_group_fails` | 覆盖「覆盖率：低于下限、缺数据都要失败」：missing group fails |
| 43 | `GeneratedArtifactDriftTest` | `test_ci_workflow_byte_drift_fails` | 覆盖「生成物门禁：直接改动 CI / 单测清单必须被 --check 抓到」：ci workflow byte drift fails |
| 44 | `GeneratedArtifactDriftTest` | `test_ci_workflow_current_is_clean` | 覆盖「生成物门禁：直接改动 CI / 单测清单必须被 --check 抓到」：ci workflow current is clean |
| 45 | `GeneratedArtifactDriftTest` | `test_render_contains_every_gate_and_acceptance` | 覆盖「生成物门禁：直接改动 CI / 单测清单必须被 --check 抓到」：render contains every gate and acceptance |
| 46 | `GeneratedArtifactDriftTest` | `test_unit_tests_md_drift_fails` | 覆盖「生成物门禁：直接改动 CI / 单测清单必须被 --check 抓到」：unit tests md drift fails |
| 47 | `GeneratedComplexityDocGateTest` | `test_check_accepts_generated_text` | 覆盖「A class whose instances are single test cases」：check accepts generated text |
| 48 | `GeneratedComplexityDocGateTest` | `test_check_detects_drift` | 覆盖「A class whose instances are single test cases」：check detects drift |
| 49 | `GeneratedComplexityDocGateTest` | `test_check_detects_extra_content` | 覆盖「A class whose instances are single test cases」：check detects extra content |
| 50 | `GeneratedComplexityDocGateTest` | `test_check_detects_missing_file` | 覆盖「A class whose instances are single test cases」：check detects missing file |
| 51 | `ImportDirectionGateTest` | `test_composition_root_import_fails` | 覆盖「A2：向上导入与反向依赖装配根都必须被抓到」：composition root import fails |
| 52 | `ImportDirectionGateTest` | `test_downward_import_passes` | 覆盖「A2：向上导入与反向依赖装配根都必须被抓到」：downward import passes |
| 53 | `ImportDirectionGateTest` | `test_type_checking_annotation_is_allowed` | 覆盖「A2：向上导入与反向依赖装配根都必须被抓到」：type checking annotation is allowed |
| 54 | `ImportDirectionGateTest` | `test_upward_import_fails` | 覆盖「A2：向上导入与反向依赖装配根都必须被抓到」：upward import fails |
| 55 | `PythonFloorGateTest` | `test_ordinary_function_passes` | 覆盖「3.11 / 3.12 语法必须在 3.10 下限门禁里报出来」：ordinary function passes |
| 56 | `PythonFloorGateTest` | `test_pep695_generic_fails` | 覆盖「3.11 / 3.12 语法必须在 3.10 下限门禁里报出来」：pep695 generic fails |
| 57 | `ReadmeGateTest` | `test_acceptance_count_drift_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：acceptance count drift fails |
| 58 | `ReadmeGateTest` | `test_consistent_readme_passes` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：consistent readme passes |
| 59 | `ReadmeGateTest` | `test_gate_count_drift_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：gate count drift fails |
| 60 | `ReadmeGateTest` | `test_missing_marker_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：missing marker fails |
| 61 | `ReadmeGateTest` | `test_step_count_drift_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：step count drift fails |
| 62 | `ReadmeGateTest` | `test_test_count_drift_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：test count drift fails |
| 63 | `ReadmeGateTest` | `test_unknown_data_dir_fails` | 覆盖「README 事实：步数、门禁数、用例数写错或标记缺失都必须失败」：unknown data dir fails |
| 64 | `UiJsGateTest` | `test_defined_helper_passes` | 覆盖「UI JS：调用未定义的辅助函数必须被抓到」：defined helper passes |
| 65 | `UiJsGateTest` | `test_model_id_literal_is_rejected` | 覆盖「UI JS：调用未定义的辅助函数必须被抓到」：model id literal is rejected |
| 66 | `UiJsGateTest` | `test_plain_words_are_not_model_ids` | 覆盖「UI JS：调用未定义的辅助函数必须被抓到」：plain words are not model ids |
| 67 | `UiJsGateTest` | `test_undefined_helper_call_fails` | 覆盖「UI JS：调用未定义的辅助函数必须被抓到」：undefined helper call fails |

## test_goal_runner.py

共 6 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CancelTest` | `test_auto_rounds_are_capped` | 目标写歪时不能无限烧下去。 |
| 2 | `CancelTest` | `test_cancel_stops_goal_continuation` | 取消后必须停 —— 不判取消位就是死循环。 |
| 3 | `CancelTest` | `test_goal_rounds_counter_advances` | 界面要显示"已自动推进 N 回合"，计数必须真的在涨。 |
| 4 | `ContinuationTextTest` | `test_active_goal_wins_over_hardcoded_prompt` | 覆盖「`_next_continuation_text` 的判定表（不启线程，直接问）」：active goal wins over hardcoded prompt |
| 5 | `ContinuationTextTest` | `test_goal_absent_falls_back_to_autonomy_switch` | 覆盖「`_next_continuation_text` 的判定表（不启线程，直接问）」：goal absent falls back to autonomy switch |
| 6 | `ContinuationTextTest` | `test_paused_and_done_stop_even_when_autonomy_on` | 目标说了算：暂停/达成后不能再被自主开关顶回去。 |

## test_gui_launcher.py

共 8 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `GuiLauncherTest` | `test_activate_window_uses_windows_api` | 覆盖「A class whose instances are single test cases」：activate window uses windows api |
| 2 | `GuiLauncherTest` | `test_activate_window_without_handle` | 覆盖「A class whose instances are single test cases」：activate window without handle |
| 3 | `GuiLauncherTest` | `test_failed_window_still_stops_child` | 覆盖「A class whose instances are single test cases」：failed window still stops child |
| 4 | `GuiLauncherTest` | `test_launch_owns_child_and_stops_it` | 覆盖「A class whose instances are single test cases」：launch owns child and stops it |
| 5 | `GuiLauncherTest` | `test_missing_entry_returns_nonzero` | 覆盖「A class whose instances are single test cases」：missing entry returns nonzero |
| 6 | `GuiLauncherTest` | `test_occupied_explicit_port_does_not_spawn` | 覆盖「A class whose instances are single test cases」：occupied explicit port does not spawn |
| 7 | `GuiLauncherTest` | `test_open_window_enables_text_selection` | 覆盖「A class whose instances are single test cases」：open window enables text selection |
| 8 | `GuiLauncherTest` | `test_pick_port_and_storage_path` | 覆盖「A class whose instances are single test cases」：pick port and storage path |

## test_history_page.py

共 16 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `FoldRoundsTest` | `test_chars_equal_sum_items` | 覆盖「A class whose instances are single test cases」：chars equal sum items |
| 2 | `FoldRoundsTest` | `test_empty` | 覆盖「A class whose instances are single test cases」：empty |
| 3 | `FoldRoundsTest` | `test_residual_events_before_first_input` | 覆盖「A class whose instances are single test cases」：residual events before first input |
| 4 | `FoldRoundsTest` | `test_round_anchor_and_order` | 覆盖「A class whose instances are single test cases」：round anchor and order |
| 5 | `FoldRoundsTest` | `test_tool_lifecycle_stays_in_round` | 覆盖「A class whose instances are single test cases」：tool lifecycle stays in round |
| 6 | `ItemCostTest` | `test_tool_uses_script_args_preview_and_images` | 覆盖「A class whose instances are single test cases」：tool uses script args preview and images |
| 7 | `ItemCostTest` | `test_user_and_attachments` | 覆盖「A class whose instances are single test cases」：user and attachments |
| 8 | `SelectPageTest` | `test_before_is_exclusive` | 覆盖「A class whose instances are single test cases」：before is exclusive |
| 9 | `SelectPageTest` | `test_before_older_than_everything_returns_empty` | 覆盖「A class whose instances are single test cases」：before older than everything returns empty |
| 10 | `SelectPageTest` | `test_budget_constant` | 覆盖「A class whose instances are single test cases」：budget constant |
| 11 | `SelectPageTest` | `test_budget_reaches_threshold_and_includes_whole_round` | 覆盖「A class whose instances are single test cases」：budget reaches threshold and includes whole round |
| 12 | `SelectPageTest` | `test_exact_before_does_not_return_that_round` | 覆盖「A class whose instances are single test cases」：exact before does not return that round |
| 13 | `SelectPageTest` | `test_full_traversal_has_no_missing_or_duplicate_rounds` | 覆盖「A class whose instances are single test cases」：full traversal has no missing or duplicate rounds |
| 14 | `SelectPageTest` | `test_next_before_only_when_has_more` | 覆盖「A class whose instances are single test cases」：next before only when has more |
| 15 | `SelectPageTest` | `test_page_values_are_copies` | 覆盖「A class whose instances are single test cases」：page values are copies |
| 16 | `SelectPageTest` | `test_single_round_over_budget_is_returned_whole` | 覆盖「A class whose instances are single test cases」：single round over budget is returned whole |

## test_image_embed.py

共 10 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `DerivedMessageShrinksTest` | `test_derived_message_carries_a_shrunk_image` | 端到端：进事实的是原图，派生给模型的是缩过的。 |
| 2 | `DerivedMessageShrinksTest` | `test_derived_message_keeps_plain_text_shape_when_no_attachment` | 覆盖「A class whose instances are single test cases」：derived message keeps plain text shape when no attachment |
| 3 | `EmbedBudgetTest` | `test_broken_base64_is_skipped` | 覆盖「A class whose instances are single test cases」：broken base64 is skipped |
| 4 | `EmbedBudgetTest` | `test_over_budget_becomes_skipped_not_dropped` | 超预算必须可察觉：进 skipped，由调用方转占位。 |
| 5 | `EmbedBudgetTest` | `test_within_budget_is_embedded` | 覆盖「A class whose instances are single test cases」：within budget is embedded |
| 6 | `ShrinkImageTest` | `test_extreme_aspect_ratio_survives` | 横幅截图（本仓的真实用例：492×42 的工具条）不该被搞坏。 |
| 7 | `ShrinkImageTest` | `test_garbage_bytes_are_returned_as_is` | 判据：缩放是优化，解不开就原样发，不能让图片发不出去。 |
| 8 | `ShrinkImageTest` | `test_large_image_is_shrunk_to_max_side` | 覆盖「A class whose instances are single test cases」：large image is shrunk to max side |
| 9 | `ShrinkImageTest` | `test_mime_is_detected_from_content` | 网关以文件实际内容判格式，本模块同样按内容判。 |
| 10 | `ShrinkImageTest` | `test_small_image_is_left_alone` | 本来就小的图不该被重编码 —— 白白损失质量。 |

## test_image_tool.py

共 28 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AttachmentReferenceTest` | `test_placeholder_has_attachment_reference_and_request_cleans_it` | 覆盖「A class whose instances are single test cases」：placeholder has attachment reference and request cleans it |
| 2 | `AttachmentReferenceTest` | `test_read_image_accepts_attachment_id_from_current_store` | 覆盖「A class whose instances are single test cases」：read image accepts attachment id from current store |
| 3 | `AttachmentReferenceTest` | `test_read_image_rejects_repeated_attachment_in_same_turn` | 覆盖「A class whose instances are single test cases」：read image rejects repeated attachment in same turn |
| 4 | `BuildToolPartsTest` | `test_over_budget_reports_note` | 超预算不能静默丢 —— 工具得能告诉模型"有图但没带上"。 |
| 5 | `BuildToolPartsTest` | `test_parts_and_no_note_within_budget` | 覆盖「工具附件 → 块 + 超限说明（工具侧的正文不该被占位文字污染）」：parts and no note within budget |
| 6 | `DescribeImageTest` | `test_gif_size` | 覆盖「尺寸解析不依赖 Pillow —— 它是可选依赖，报尺寸是基本功能」：gif size |
| 7 | `DescribeImageTest` | `test_png_size` | 覆盖「尺寸解析不依赖 Pillow —— 它是可选依赖，报尺寸是基本功能」：png size |
| 8 | `DescribeImageTest` | `test_unknown_bytes_report_no_mime` | 非图片内容：报空 mime、尺寸 0，不抛。 |
| 9 | `PipelineCarriesAttachmentsTest` | `test_attachments_survive_pipeline` | 覆盖「管道把返回值上的附件搬进结果信封，工具不必自己知道 call_id」：attachments survive pipeline |
| 10 | `PipelineCarriesAttachmentsTest` | `test_plain_return_has_no_attachments` | 普通返回值（dict / 字符串）不该凭空多出附件字段。 |
| 11 | `ReadImageToolTest` | `test_default_keeps_original_size` | 默认不缩放：按图定位坐标的场景不能悄悄改尺寸。 |
| 12 | `ReadImageToolTest` | `test_empty_file_raises` | 覆盖「工具本体：成功给附件，失败给结构化错误」：empty file raises |
| 13 | `ReadImageToolTest` | `test_empty_path_raises` | 覆盖「工具本体：成功给附件，失败给结构化错误」：empty path raises |
| 14 | `ReadImageToolTest` | `test_explicit_max_side_reports_scale` | 显式缩放时必须回报换算比例 —— 否则模型按图上像素操作会全错。 |
| 15 | `ReadImageToolTest` | `test_missing_file_raises` | 覆盖「工具本体：成功给附件，失败给结构化错误」：missing file raises |
| 16 | `ReadImageToolTest` | `test_non_image_raises` | 按内容判定：改了扩展名的文本文件不该被当成图片发出去。 |
| 17 | `ReadImageToolTest` | `test_projection_keeps_tool_chosen_size` | 进模型的那一份不再二次缩放：摘要里的实发尺寸就是模型看到的尺寸。 |
| 18 | `ReadImageToolTest` | `test_reads_png_and_summarizes` | 覆盖「工具本体：成功给附件，失败给结构化错误」：reads png and summarizes |
| 19 | `StripProtectsToolImagesTest` | `test_excess_tool_image_is_stripped` | 超出总量闸的老工具图要被剥掉：不限量会随会话线性膨胀。 |
| 20 | `StripProtectsToolImagesTest` | `test_fifo_keeps_new_tool_image_and_drops_oldest_user_image` | 9 张用户图 + 刚读的工具图：最新的工具图保留，最老的用户图被剥。 |
| 21 | `StripProtectsToolImagesTest` | `test_newest_tool_image_wins_over_older_user_image` | 较新的工具图同样按先进先出保留，不因是工具图就被压低优先级。 |
| 22 | `StripProtectsToolImagesTest` | `test_newest_user_image_wins_over_older_tool_image` | 配额只够一张时按时间先进先出，较新的用户图保留。 |
| 23 | `StripProtectsToolImagesTest` | `test_old_tool_image_survives_turn_window` | 轮次窗口不剥工具图：老工具图不是"重复内联的老用户图"， 它只由总量闸管。窗口只影响用户图。 |
| 24 | `StripProtectsToolImagesTest` | `test_tool_image_counts_toward_max` | 工具图占总量配额：不限量会让请求体随会话线性膨胀。 |
| 25 | `StripProtectsToolImagesTest` | `test_tool_image_with_no_user_images_survives` | 纯工具图（用户没发图）必须留着 —— 否则模型永远看不到工具读的图。 |
| 26 | `ToolContentTest` | `test_empty_text_with_image_gets_placeholder` | 空正文 + 有图：补一句说明，而不是发一个只有图片的 content。 |
| 27 | `ToolContentTest` | `test_no_attachments_keeps_string` | 没图时保持字符串：多模态数组会让请求体无谓变大，也改变既有形态。 |
| 28 | `ToolContentTest` | `test_with_image_becomes_array` | 覆盖「工具消息 content 的三态：无图 / 有图 / 只有图」：with image becomes array |

## test_image_turns.py

共 23 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ConfigWiringTest` | `test_app_carries_the_value` | 覆盖「配置项 `[context] image_turns` / `image_max` 一路到模型模…」：app carries the value |
| 2 | `ConfigWiringTest` | `test_default_config_value` | 覆盖「配置项 `[context] image_turns` / `image_max` 一路到模型模…」：default config value |
| 3 | `ConfigWiringTest` | `test_module_receives_the_value` | 覆盖「配置项 `[context] image_turns` / `image_max` 一路到模型模…」：module receives the value |
| 4 | `DefaultBoundedTest` | `test_default_is_bounded` | 覆盖「默认带图窗口有界：不传参数也会剥掉旧图，避免请求体膨胀」：default is bounded |
| 5 | `DefaultBoundedTest` | `test_narrow_window_strips` | 配小 image_turns 即按用户轮剥图。 |
| 6 | `StripByTotalCapTest` | `test_cap_and_turns_apply_together` | 轮数先裁掉窗口外，窗口内再按总量裁。 |
| 7 | `StripByTotalCapTest` | `test_cap_keeps_the_most_recent_turn_first` | 五张的额度：最近一轮三张全保，剩两张给倒数第二轮，最老的一轮全舍。 |
| 8 | `StripByTotalCapTest` | `test_default_call_applies_bounded_defaults` | 默认保留最近 1 轮；20 张里只留最新回合的 4 张。 |
| 9 | `StripByTotalCapTest` | `test_default_cap_is_eight` | 覆盖「轮数之外的第二道闸：总数上限，按时间先进先出」：default cap is eight |
| 10 | `StripByTotalCapTest` | `test_negative_cap_means_no_limit` | 覆盖「轮数之外的第二道闸：总数上限，按时间先进先出」：negative cap means no limit |
| 11 | `StripByTotalCapTest` | `test_oldest_turn_is_dropped_whole_before_touching_newer` | 覆盖「轮数之外的第二道闸：总数上限，按时间先进先出」：oldest turn is dropped whole before touching newer |
| 12 | `StripByTotalCapTest` | `test_one_turn_over_the_cap_keeps_the_tail_of_that_turn` | 一轮本身就超上限：留靠后的那几张（同一轮内后发的更可能是"这张图"）。 |
| 13 | `StripByTotalCapTest` | `test_placeholder_counts_the_dropped_blocks` | 覆盖「轮数之外的第二道闸：总数上限，按时间先进先出」：placeholder counts the dropped blocks |
| 14 | `StripByTotalCapTest` | `test_within_cap_touches_nothing` | 覆盖「轮数之外的第二道闸：总数上限，按时间先进先出」：within cap touches nothing |
| 15 | `StripByTotalCapTest` | `test_zero_cap_drops_everything` | 覆盖「轮数之外的第二道闸：总数上限，按时间先进先出」：zero cap drops everything |
| 16 | `StripByTurnTest` | `test_defaults_are_bounded` | 模块默认值有界：最近 1 轮、最多 8 张。 |
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

共 29 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `BatchERegistrationTest` | `test_archive_declares_write_path_keys` | 覆盖「工具注册链路（六个来源共 12 件）+ 门控预览名单一致性」：archive declares write path keys |
| 2 | `BatchERegistrationTest` | `test_batch_e_plugins_register` | 覆盖「工具注册链路（六个来源共 12 件）+ 门控预览名单一致性」：batch e plugins register |
| 3 | `FileSearchTest` | `test_blank_pattern_raises` | 空 pattern 报错，不要静默把每个位置都当成命中。 |
| 4 | `FileSearchTest` | `test_context_and_gitignore` | 覆盖「大目录内容搜索」：context and gitignore |
| 5 | `FileSearchTest` | `test_limit` | 覆盖「大目录内容搜索」：limit |
| 6 | `FindInFileTest` | `test_blank_pattern_says_what_to_fix` | 字面模式 pattern 为空：只说 pattern 本身该怎么改。 |
| 7 | `FindInFileTest` | `test_literal_or_and_occurrence` | 覆盖「单文件定位」：literal or and occurrence |
| 8 | `FindInFileTest` | `test_missing_file_is_not_reported_as_dir` | 文件不存在与传了目录必须分开说 —— 旧版两者都报「不是已存在文件」。 |
| 9 | `FindInFileTest` | `test_not_found_and_out_of_range` | 覆盖「单文件定位」：not found and out of range |
| 10 | `FindInFileTest` | `test_path_is_dir_points_to_directory_tools` | path 传了目录：说清本工具只处理单文件，并指向能搜目录的工具。 |
| 11 | `FindInFileTest` | `test_regex_invalid` | 覆盖「单文件定位」：regex invalid |
| 12 | `FindInFileTest` | `test_region_and_rowcols` | 覆盖「单文件定位」：region and rowcols |
| 13 | `OcrAndArchiveTest` | `test_archive_list_create_extract` | 覆盖「image_ocr / archive」：archive list create extract |
| 14 | `OcrAndArchiveTest` | `test_archive_unknown_format` | 覆盖「image_ocr / archive」：archive unknown format |
| 15 | `OcrAndArchiveTest` | `test_ocr_region_validation_and_dependency` | 覆盖「image_ocr / archive」：ocr region validation and dependency |
| 16 | `RegexLocateTest` | `test_blank_pattern_raises` | 空 pattern 报错：空正则会命中每个位置。 |
| 17 | `RegexLocateTest` | `test_directory_recursive_and_glob` | 覆盖「单文件/目录正则定位」：directory recursive and glob |
| 18 | `RegexLocateTest` | `test_invalid_regex_and_limit` | 覆盖「单文件/目录正则定位」：invalid regex and limit |
| 19 | `RegexLocateTest` | `test_limit_truncation` | 覆盖「单文件/目录正则定位」：limit truncation |
| 20 | `SystemToolsTest` | `test_env_probe_shape` | 覆盖「env_probe / unified_diagnose / git_workspace」：env probe shape |
| 21 | `SystemToolsTest` | `test_git_workspace_modes` | 覆盖「env_probe / unified_diagnose / git_workspace」：git workspace modes |
| 22 | `SystemToolsTest` | `test_unified_diagnose_red_green` | 覆盖「env_probe / unified_diagnose / git_workspace」：unified diagnose red green |
| 23 | `TextDataToolsTest` | `test_data_table_csv_actions` | 覆盖「text_diff / data_table」：data table csv actions |
| 24 | `TextDataToolsTest` | `test_data_table_xlsx_dependency_path` | 覆盖「text_diff / data_table」：data table xlsx dependency path |
| 25 | `TextDataToolsTest` | `test_text_diff_file_vs_text` | 覆盖「text_diff / data_table」：text diff file vs text |
| 26 | `WebToolsTest` | `test_fetch_acceptance_failure_keeps_data` | 覆盖「web_fetch / web_fetch_render」：fetch acceptance failure keeps data |
| 27 | `WebToolsTest` | `test_fetch_invalid_scheme` | 覆盖「web_fetch / web_fetch_render」：fetch invalid scheme |
| 28 | `WebToolsTest` | `test_fetch_ok_and_checks` | 覆盖「web_fetch / web_fetch_render」：fetch ok and checks |
| 29 | `WebToolsTest` | `test_render_dependency_path` | 覆盖「web_fetch / web_fetch_render」：render dependency path |

## test_kb_plugin.py

共 51 个用例。

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
| 23 | `KBRuntimeTest` | `test_resource_directory_lines_configured` | 覆盖「A class whose instances are single test cases」：resource directory lines configured |
| 24 | `KBRuntimeTest` | `test_resource_directory_lines_unconfigured` | 覆盖「A class whose instances are single test cases」：resource directory lines unconfigured |
| 25 | `KBRuntimeTest` | `test_safe_resolve_boundaries` | 覆盖「A class whose instances are single test cases」：safe resolve boundaries |
| 26 | `KBRuntimeTest` | `test_set_checked_replace_filter_clear` | 覆盖「A class whose instances are single test cases」：set checked replace filter clear |
| 27 | `KnowledgeExtraSuffixesTest` | `test_config_key_is_read_and_used` | 覆盖「配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名」：config key is read and used |
| 28 | `KnowledgeExtraSuffixesTest` | `test_extra_extends_the_whitelist` | 覆盖「配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名」：extra extends the whitelist |
| 29 | `KnowledgeExtraSuffixesTest` | `test_missing_key_keeps_default_whitelist` | 覆盖「配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名」：missing key keeps default whitelist |
| 30 | `KnowledgeExtraSuffixesTest` | `test_parse_forms` | 覆盖「配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名」：parse forms |
| 31 | `KnowledgeTextOnlyTest` | `test_binary_is_neither_listed_nor_selectable` | 覆盖「知识库只收文本类文件：非文本不列、不可勾（读出来是替换字符与 NUL，只占预算）」：binary is neither listed nor selectable |
| 32 | `KnowledgeTextOnlyTest` | `test_runtime_rejects_binary_check` | 覆盖「知识库只收文本类文件：非文本不列、不可勾（读出来是替换字符与 NUL，只占预算）」：runtime rejects binary check |
| 33 | `KnowledgeTextOnlyTest` | `test_text_suffix_rules` | 覆盖「知识库只收文本类文件：非文本不列、不可勾（读出来是替换字符与 NUL，只占预算）」：text suffix rules |
| 34 | `PluginConfigIsolationTest` | `test_each_plugin_reads_its_own_config_file` | 覆盖「内核 `config.ini` 只含内核设置；插件设置在插件自己目录下的 plugin-conf…」：each plugin reads its own config file |
| 35 | `PluginConfigIsolationTest` | `test_kernel_templates_have_no_plugin_section` | 覆盖「内核 `config.ini` 只含内核设置；插件设置在插件自己目录下的 plugin-conf…」：kernel templates have no plugin section |
| 36 | `PluginConfigIsolationTest` | `test_skills_dir_comes_from_its_own_config` | 覆盖「内核 `config.ini` 只含内核设置；插件设置在插件自己目录下的 plugin-conf…」：skills dir comes from its own config |
| 37 | `PluginPanelRenderContractTest` | `test_knowledge_panel_matches_composite_dom_id` | 壳层广播的 panel 是 `knowledge__kb`，不能只认逻辑 id `kb`。 |
| 38 | `PluginPanelRenderContractTest` | `test_open_pane_broadcasts_panel_opened` | 覆盖「插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动」：open pane broadcasts panel opened |
| 39 | `PluginPanelRenderContractTest` | `test_open_plugin_panel_passes_its_plugin_name` | 覆盖「插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动」：open plugin panel passes its plugin name |
| 40 | `PluginPanelRenderContractTest` | `test_panel_has_a_refresh_button_on_the_subtitle` | 小标题右侧一个刷新：知识库目录是外部目录，不重开面板也要能取到新文件。 |
| 41 | `PluginPanelRenderContractTest` | `test_panels_render_on_the_event` | 覆盖「插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动」：panels render on the event |
| 42 | `PluginPanelRenderContractTest` | `test_refresh_handler_re_renders` | 覆盖「插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动」：refresh handler re renders |
| 43 | `PluginSourceContractTest` | `test_disposer_removes_the_source` | 覆盖「插件注入源的契约：注册进「知识库」段、每回合刷新、disposer 后消失」：disposer removes the source |
| 44 | `PluginSourceContractTest` | `test_plugin_sources_do_not_touch_the_kernel` | 插件来源只经注册表进出；内核不持有插件对象。 |
| 45 | `PluginSourceContractTest` | `test_segments_carry_their_own_name_and_prefix` | 段名与注入前缀由来源声明：内核不解释正文是什么。 |
| 46 | `PluginSourceContractTest` | `test_source_is_refreshed_every_turn` | 注入源每回合都重读：第 2 回合改内容，请求里立刻反映。 |
| 47 | `PluginSourceContractTest` | `test_source_text_lands_in_the_knowledge_block` | 覆盖「插件注入源的契约：注册进「知识库」段、每回合刷新、disposer 后消失」：source text lands in the knowledge block |
| 48 | `PluginSourceContractTest` | `test_two_sources_of_one_plugin_stay_separate` | 同一插件可以贡献多段：数量按位置对，不互相覆盖。 |
| 49 | `SkillsConfigSourceTest` | `test_plugin_dir_has_no_own_config` | 覆盖「Skills 设置只有工程 config.ini 一处来源（插件目录下没有同名配置）」：plugin dir has no own config |
| 50 | `SkillsConfigSourceTest` | `test_reader_reads_the_project_config` | 覆盖「Skills 设置只有工程 config.ini 一处来源（插件目录下没有同名配置）」：reader reads the project config |
| 51 | `SkillsConfigSourceTest` | `test_reader_takes_a_given_ini` | 覆盖「Skills 设置只有工程 config.ini 一处来源（插件目录下没有同名配置）」：reader takes a given ini |

## test_layout_min_width.py

共 2 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ChatMinWidthTest` | `test_chat_allows_narrow_layout` | 覆盖「对话区可随窗口缩窄，控件通过换行避免越界」：chat allows narrow layout |
| 2 | `ChatMinWidthTest` | `test_composer_footer_wraps` | 覆盖「对话区可随窗口缩窄，控件通过换行避免越界」：composer footer wraps |

## test_mode_note.py

共 13 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ModeIsNotPersistedTest` | `test_mode_note_is_system_role` | 模式说明不是用户发言：控制台里它不该被当成用户消息。 |
| 2 | `ModeIsNotPersistedTest` | `test_no_event_carries_the_mode_note` | 覆盖「模式说明只存在于发给模型的那一份：不落记录、不发事件」：no event carries the mode note |
| 3 | `ModeTailShapeTest` | `test_empty_note_changes_nothing` | 覆盖「模式说明是请求的最后一条，且不改动别处」：empty note changes nothing |
| 4 | `ModeTailShapeTest` | `test_existing_runtime_tail_is_replaced_not_duplicated` | 同一上下文再次装配时，旧临时尾条要被替换，不能叠成两条。 |
| 5 | `ModeTailShapeTest` | `test_input_list_is_not_mutated` | 覆盖「模式说明是请求的最后一条，且不改动别处」：input list is not mutated |
| 6 | `ModeTailShapeTest` | `test_note_is_appended_last` | 覆盖「模式说明是请求的最后一条，且不改动别处」：note is appended last |
| 7 | `ModeTailShapeTest` | `test_note_works_after_multimodal_tail` | 最后一条是多模态数组时也必须能附加（不能拼坏它的结构）。 |
| 8 | `ModeTailShapeTest` | `test_switching_mode_changes_only_the_tail` | 覆盖「模式说明是请求的最后一条，且不改动别处」：switching mode changes only the tail |
| 9 | `SystemPromptHasNoModeTest` | `test_explicit_system_prompt_gets_no_note` | 调用方自己给的系统提示：模式怎么表达由他决定，不另加。 |
| 10 | `SystemPromptHasNoModeTest` | `test_mode_note_still_differs_per_mode` | 覆盖「模式段必须从系统提示词里出去」：mode note still differs per mode |
| 11 | `SystemPromptHasNoModeTest` | `test_resolved_system_prompt_has_no_mode` | 覆盖「模式段必须从系统提示词里出去」：resolved system prompt has no mode |
| 12 | `SystemPromptHasNoModeTest` | `test_split_helper_drops_the_mode_section` | 覆盖「模式段必须从系统提示词里出去」：split helper drops the mode section |
| 13 | `SystemPromptHasNoModeTest` | `test_switching_mode_keeps_system_prompt_byte_identical` | 覆盖「模式段必须从系统提示词里出去」：switching mode keeps system prompt byte identical |

## test_model_catalog.py

共 23 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ModelCatalogTest` | `test_default_prefers_flag_then_first` | 覆盖「A class whose instances are single test cases」：default prefers flag then first |
| 2 | `ModelCatalogTest` | `test_disposer_is_scoped_to_its_own_registration` | 覆盖「A class whose instances are single test cases」：disposer is scoped to its own registration |
| 3 | `ModelCatalogTest` | `test_duplicate_ids_reject_the_whole_batch` | 覆盖「A class whose instances are single test cases」：duplicate ids reject the whole batch |
| 4 | `ModelCatalogTest` | `test_empty_replacement_flips_authoritative` | 覆盖「A class whose instances are single test cases」：empty replacement flips authoritative |
| 5 | `ModelCatalogTest` | `test_hot_read_duplicate_ids_fall_back_to_last_good` | 覆盖「A class whose instances are single test cases」：hot read duplicate ids fall back to last good |
| 6 | `ModelCatalogTest` | `test_hot_read_failure_keeps_last_good_entries` | 覆盖「A class whose instances are single test cases」：hot read failure keeps last good entries |
| 7 | `ModelCatalogTest` | `test_hot_read_is_re_evaluated_each_snapshot` | 覆盖「A class whose instances are single test cases」：hot read is re evaluated each snapshot |
| 8 | `ModelCatalogTest` | `test_replacing_source_drops_removed_models` | 覆盖「A class whose instances are single test cases」：replacing source drops removed models |
| 9 | `ModelCatalogTest` | `test_second_distinct_source_is_rejected_without_clobbering` | 覆盖「A class whose instances are single test cases」：second distinct source is rejected without clobbering |
| 10 | `ModelCatalogTest` | `test_unconfigured_catalog_is_empty_and_not_authoritative` | 覆盖「A class whose instances are single test cases」：unconfigured catalog is empty and not authoritative |
| 11 | `ModelCatalogTest` | `test_unknown_provider_only_means_not_authoritative` | 覆盖「A class whose instances are single test cases」：unknown provider only means not authoritative |
| 12 | `ModelCatalogTest` | `test_unknown_provider_skips_only_that_entry` | 覆盖「A class whose instances are single test cases」：unknown provider skips only that entry |
| 13 | `ModelEntryTest` | `test_bad_options_json_degrades_to_empty` | 覆盖「A class whose instances are single test cases」：bad options json degrades to empty |
| 14 | `ModelEntryTest` | `test_options_are_canonical_and_isolated` | 覆盖「A class whose instances are single test cases」：options are canonical and isolated |
| 15 | `PluginContextCatalogTest` | `test_disposer_removes_only_its_own_source` | 覆盖「插件注册口：来源名取插件名、冲突不抛、disposer 随 ctx 回收」：disposer removes only its own source |
| 16 | `PluginContextCatalogTest` | `test_hot_read_callback_is_accepted` | 覆盖「插件注册口：来源名取插件名、冲突不抛、disposer 随 ctx 回收」：hot read callback is accepted |
| 17 | `PluginContextCatalogTest` | `test_missing_catalog_is_a_wiring_error` | 覆盖「插件注册口：来源名取插件名、冲突不抛、disposer 随 ctx 回收」：missing catalog is a wiring error |
| 18 | `PluginContextCatalogTest` | `test_plugin_name_becomes_the_catalog_source` | 覆盖「插件注册口：来源名取插件名、冲突不抛、disposer 随 ctx 回收」：plugin name becomes the catalog source |
| 19 | `PluginContextCatalogTest` | `test_second_plugin_source_is_reported_not_raised` | 覆盖「插件注册口：来源名取插件名、冲突不抛、disposer 随 ctx 回收」：second plugin source is reported not raised |
| 20 | `ProviderCacheTest` | `test_option_change_invalidates_the_cached_provider` | 覆盖「A class whose instances are single test cases」：option change invalidates the cached provider |
| 21 | `ProviderCacheTest` | `test_provider_is_built_once_per_entry` | 覆盖「A class whose instances are single test cases」：provider is built once per entry |
| 22 | `ProviderCacheTest` | `test_unknown_model_id_returns_none` | 覆盖「A class whose instances are single test cases」：unknown model id returns none |
| 23 | `SnapshotShapeTest` | `test_entry_lookup_ignores_surrounding_whitespace` | 覆盖「A class whose instances are single test cases」：entry lookup ignores surrounding whitespace |

## test_model_provider.py

共 41 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AppModelConfigTest` | `test_catalog_snapshot_failure_is_non_authoritative` | 覆盖「装配层的模型来源状态：目录接管、回落与清空」：catalog snapshot failure is non authoritative |
| 2 | `AppModelConfigTest` | `test_known_session_model_is_kept` | 覆盖「装配层的模型来源状态：目录接管、回落与清空」：known session model is kept |
| 3 | `AppModelConfigTest` | `test_model_catalog_is_optional` | 覆盖「装配层的模型来源状态：目录接管、回落与清空」：model catalog is optional |
| 4 | `AppModelConfigTest` | `test_model_config_reports_source_and_degrade` | 覆盖「装配层的模型来源状态：目录接管、回落与清空」：model config reports source and degrade |
| 5 | `AppModelConfigTest` | `test_refresh_switches_catalog_on_and_off` | 插件装卸必须重算权威：目录接管时刷新路由，注销后回退且清空清单。 |
| 6 | `AppModelConfigTest` | `test_reload_is_ignored_when_catalog_is_authoritative` | 覆盖「装配层的模型来源状态：目录接管、回落与清空」：reload is ignored when catalog is authoritative |
| 7 | `AppModelConfigTest` | `test_reload_without_catalog_returns_plugin_managed_note` | 覆盖「装配层的模型来源状态：目录接管、回落与清空」：reload without catalog returns plugin managed note |
| 8 | `AppModelConfigTest` | `test_unknown_session_model_falls_back_to_default` | 旧标签页拿着已删除的模型 id 时，读取点收敛到默认值并写回。 |
| 9 | `AvailableModelsWireTest` | `test_current_model_is_always_in_the_list` | `model` 必须在清单里，否则 UI 的白名单校验会丢弃它（顶栏永远"加载中"）。 |
| 10 | `AvailableModelsWireTest` | `test_health_does_not_invent_a_model_in_degraded_state` | `none` 时不能拿 provider 的占位模型充数：那个 id 实际选不了。 |
| 11 | `AvailableModelsWireTest` | `test_health_lists_all_configured_models` | 覆盖「`/health` 的 `allowed_models` 必须给出完整清单」：health lists all configured models |
| 12 | `AvailableModelsWireTest` | `test_shell_health_also_lists_all_models` | 覆盖「`/health` 的 `allowed_models` 必须给出完整清单」：shell health also lists all models |
| 13 | `CatalogAuthorityAtAssemblyTest` | `test_catalog_entries_become_the_model_list` | 覆盖「插件目录一旦权威，装配末尾就把模型清单与路由策略换成目录的」：catalog entries become the model list |
| 14 | `ImagesAlwaysReachTheWireTest` | `test_image_block_survives_into_the_payload` | 覆盖「图片一律原样发给模型 —— 不按模型名猜能力、不做降级剥图」：image block survives into the payload |
| 15 | `ImagesAlwaysReachTheWireTest` | `test_plain_text_message_is_untouched` | 覆盖「图片一律原样发给模型 —— 不按模型名猜能力、不做降级剥图」：plain text message is untouched |
| 16 | `ProviderStreamTimeoutTest` | `test_openai_stream_timeout_is_bounded` | 覆盖「A class whose instances are single test cases」：openai stream timeout is bounded |
| 17 | `ReasonNotReplayedTest` | `test_cut_clears_the_content_but_keeps_the_key_for_tool_messages` | 覆盖「历史推理不回传内容：它必然未命中缓存，回传等于每回合多算几万 token」：cut clears the content but keeps the key for tool messages |
| 18 | `ReasonNotReplayedTest` | `test_cut_none_keeps_everything` | 覆盖「历史推理不回传内容：它必然未命中缓存，回传等于每回合多算几万 token」：cut none keeps everything |
| 19 | `ReasonNotReplayedTest` | `test_original_messages_are_not_mutated` | 覆盖「历史推理不回传内容：它必然未命中缓存，回传等于每回合多算几万 token」：original messages are not mutated |
| 20 | `ReasonNotReplayedTest` | `test_plain_assistant_before_the_cut_drops_the_key` | 覆盖「历史推理不回传内容：它必然未命中缓存，回传等于每回合多算几万 token」：plain assistant before the cut drops the key |
| 21 | `ReasonNotReplayedTest` | `test_provider_passes_the_boundary_and_defaults_to_stripping` | 覆盖「历史推理不回传内容：它必然未命中缓存，回传等于每回合多算几万 token」：provider passes the boundary and defaults to stripping |
| 22 | `ReasonNotReplayedTest` | `test_tool_calls_survive_the_cut` | 覆盖「历史推理不回传内容：它必然未命中缓存，回传等于每回合多算几万 token」：tool calls survive the cut |
| 23 | `ReasonNotReplayedTest` | `test_tool_message_without_reasoning_gets_an_empty_key` | 没有思维链记录的工具消息也要补空串：缺键与空串在 API 侧不等价。 |
| 24 | `RequestLevelModelTest` | `test_effort_still_reaches_the_wire` | 推理档位照常透传到请求载荷。 |
| 25 | `RequestLevelModelTest` | `test_empty_request_model_falls_back_to_instance_default` | 空串 = 不指定 ⇒ 用实例默认模型，既有调用方行为不变。 |
| 26 | `RequestLevelModelTest` | `test_local_model_check_is_per_requested_model` | 本地模型的判定同理：默认是云端、本次选本地时不能照旧下发推理档位。 |
| 27 | `RequestLevelModelTest` | `test_request_model_wins_over_instance_default` | 覆盖「A class whose instances are single test cases」：request model wins over instance default |
| 28 | `RequestLevelModelTest` | `test_whitespace_is_treated_as_unspecified` | 覆盖「A class whose instances are single test cases」：whitespace is treated as unspecified |
| 29 | `SessionModelSelectionTest` | `test_choice_survives_a_new_process` | 换一个 LiveState 实例（= 换进程）后选择仍在 —— 靠落盘，不靠内存。 |
| 30 | `SessionModelSelectionTest` | `test_empty_clears_the_choice` | 覆盖「会话级模型选择：选中即生效、可读回、跨进程仍在」：empty clears the choice |
| 31 | `SessionModelSelectionTest` | `test_read_only_is_never_used` | 只读会话（`is_read_only` 的 cid）不落盘 —— 同 todo 的白名单纪律。 |
| 32 | `SessionModelSelectionTest` | `test_select_then_read_back` | 覆盖「会话级模型选择：选中即生效、可读回、跨进程仍在」：select then read back |
| 33 | `SessionStateFileTest` | `test_closing_todo_does_not_wipe_the_model` | `close` 只清清单：写盘前必须读回其余分量，否则会覆盖模型。 |
| 34 | `SessionStateFileTest` | `test_every_component_survives_a_new_process` | 覆盖「会话状态文件：模型 / 模式 / 档位 / 清单同住一份，可跨进程读回」：every component survives a new process |
| 35 | `SessionStateFileTest` | `test_file_nests_todo_and_keeps_state_flat` | 覆盖「会话状态文件：模型 / 模式 / 档位 / 清单同住一份，可跨进程读回」：file nests todo and keeps state flat |
| 36 | `SessionStateFileTest` | `test_stale_flat_file_is_ignored` | 只认嵌套结构：平铺把清单字段写在顶层的文件不算会话状态。 |
| 37 | `TurnStartAssemblyTest` | `test_model_module_marks_turn_start` | 覆盖「装配时把"本回合起点"标出来，provider 才有裁的依据」：model module marks turn start |
| 38 | `TurnStartAssemblyTest` | `test_port_default_keeps_everything` | 覆盖「装配时把"本回合起点"标出来，provider 才有裁的依据」：port default keeps everything |
| 39 | `UserFacingTextTest` | `test_500_and_503_name_the_model_server` | 覆盖「用户可见的文案不得混入内部术语」：500 and 503 name the model server |
| 40 | `UserFacingTextTest` | `test_deepseek_official_error_codes_are_mapped` | 与 https://api-docs.deepseek.com/quick_start/error_codes 七码对齐。 |
| 41 | `UserFacingTextTest` | `test_http_hints_are_user_facing_and_history_free` | 覆盖「用户可见的文案不得混入内部术语」：http hints are user facing and history free |

## test_model_window.py

共 14 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CompressionThresholdTest` | `test_bad_percent_uses_70` | 覆盖「A class whose instances are single test cases」：bad percent uses 70 |
| 2 | `CompressionThresholdTest` | `test_missing_window_uses_fallback` | 覆盖「A class whose instances are single test cases」：missing window uses fallback |
| 3 | `CompressionThresholdTest` | `test_window_percent` | 覆盖「A class whose instances are single test cases」：window percent |
| 4 | `EntryWindowTest` | `test_bad_metadata_is_zero_not_an_exception` | 覆盖「A class whose instances are single test cases」：bad metadata is zero not an exception |
| 5 | `EntryWindowTest` | `test_compression_percent_defaults_and_clamps` | 覆盖「A class whose instances are single test cases」：compression percent defaults and clamps |
| 6 | `EntryWindowTest` | `test_entry_exposes_the_window` | 覆盖「A class whose instances are single test cases」：entry exposes the window |
| 7 | `_AppWindowTest` | `test_catalog_entry_window_wins` | 覆盖「A class whose instances are single test cases」：catalog entry window wins |
| 8 | `_AppWindowTest` | `test_compression_percent_comes_from_the_current_model` | 覆盖「A class whose instances are single test cases」：compression percent comes from the current model |
| 9 | `_AppWindowTest` | `test_compression_percent_defaults_to_70` | 覆盖「A class whose instances are single test cases」：compression percent defaults to 70 |
| 10 | `_AppWindowTest` | `test_compression_threshold_falls_back_without_a_window` | 覆盖「A class whose instances are single test cases」：compression threshold falls back without a window |
| 11 | `_AppWindowTest` | `test_compression_threshold_uses_the_model_percent` | 覆盖「A class whose instances are single test cases」：compression threshold uses the model percent |
| 12 | `_AppWindowTest` | `test_context_layout_budget_uses_the_model_threshold` | 覆盖「A class whose instances are single test cases」：context layout budget uses the model threshold |
| 13 | `_AppWindowTest` | `test_entry_without_window_uses_the_shared_default` | 覆盖「A class whose instances are single test cases」：entry without window uses the shared default |
| 14 | `_AppWindowTest` | `test_stale_model_converges_to_the_default_window` | 会话还拿着已删除的模型 id：先收敛回默认，窗口跟着默认走。 |

## test_multi_model_plugin.py

共 30 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CatalogPayloadTest` | `test_invalid_entries_are_exposed_for_ops` | 覆盖「A class whose instances are single test cases」：invalid entries are exposed for ops |
| 2 | `CatalogPayloadTest` | `test_payload_carries_no_credentials` | 覆盖「A class whose instances are single test cases」：payload carries no credentials |
| 3 | `ParseTest` | `test_anthropic_options_are_ignored_for_openai` | 覆盖「A class whose instances are single test cases」：anthropic options are ignored for openai |
| 4 | `ParseTest` | `test_anthropic_options_are_typed` | 覆盖「A class whose instances are single test cases」：anthropic options are typed |
| 5 | `ParseTest` | `test_bad_context_window_invalidates_the_entry` | 覆盖「A class whose instances are single test cases」：bad context window invalidates the entry |
| 6 | `ParseTest` | `test_bad_default_flag_keeps_entry_non_default` | 覆盖「A class whose instances are single test cases」：bad default flag keeps entry non default |
| 7 | `ParseTest` | `test_bad_entry_does_not_hide_good_ones` | 覆盖「A class whose instances are single test cases」：bad entry does not hide good ones |
| 8 | `ParseTest` | `test_bad_numbers_invalidate_the_entry` | 覆盖「A class whose instances are single test cases」：bad numbers invalidate the entry |
| 9 | `ParseTest` | `test_bad_thinking_flag_invalidates_the_entry` | 覆盖「A class whose instances are single test cases」：bad thinking flag invalidates the entry |
| 10 | `ParseTest` | `test_compression_percent_defaults_to_70` | 覆盖「A class whose instances are single test cases」：compression percent defaults to 70 |
| 11 | `ParseTest` | `test_compression_percent_rejects_out_of_range` | 覆盖「A class whose instances are single test cases」：compression percent rejects out of range |
| 12 | `ParseTest` | `test_context_window_is_carried_as_entry_metadata` | 覆盖「A class whose instances are single test cases」：context window is carried as entry metadata |
| 13 | `ParseTest` | `test_diagnostic_points_at_file_section_and_key` | 覆盖「A class whose instances are single test cases」：diagnostic points at file section and key |
| 14 | `ParseTest` | `test_duplicate_section_is_a_file_level_error` | INI 不允许同名节：重复 id 会让整份文件解析失败，所以只能用不同 id。 |
| 15 | `ParseTest` | `test_malformed_file_is_reported_not_raised` | 覆盖「A class whose instances are single test cases」：malformed file is reported not raised |
| 16 | `ParseTest` | `test_missing_context_window_invalidates_the_entry` | 覆盖「A class whose instances are single test cases」：missing context window invalidates the entry |
| 17 | `ParseTest` | `test_missing_credentials_invalidates_only_that_entry` | 覆盖「A class whose instances are single test cases」：missing credentials invalidates only that entry |
| 18 | `ParseTest` | `test_missing_file_is_empty_not_an_error` | 覆盖「A class whose instances are single test cases」：missing file is empty not an error |
| 19 | `ParseTest` | `test_multiple_defaults_keep_the_first` | 覆盖「A class whose instances are single test cases」：multiple defaults keep the first |
| 20 | `ParseTest` | `test_no_default_marks_the_first_entry` | 覆盖「A class whose instances are single test cases」：no default marks the first entry |
| 21 | `ParseTest` | `test_openai_defaults_and_first_entry_is_default` | 覆盖「A class whose instances are single test cases」：openai defaults and first entry is default |
| 22 | `ParseTest` | `test_placeholder_keys_are_rejected` | 照抄示例留下的占位符不算已配置，插件继续走回落路径。 |
| 23 | `ParseTest` | `test_same_vendor_twice_with_distinct_ids` | 同一家厂商同时走两套协议：id 必须唯一，`provider` 决定各走哪套。 |
| 24 | `ParseTest` | `test_utf8_bom_is_accepted` | 覆盖「A class whose instances are single test cases」：utf8 bom is accepted |
| 25 | `PickerStyleTest` | `test_button_has_no_width_cap` | 覆盖「模型名是唯一辨识依据：下拉与按钮都不许截断它」：button has no width cap |
| 26 | `PickerStyleTest` | `test_menu_grows_with_its_items` | 覆盖「模型名是唯一辨识依据：下拉与按钮都不许截断它」：menu grows with its items |
| 27 | `PickerStyleTest` | `test_names_and_ids_are_not_ellipsized` | 覆盖「模型名是唯一辨识依据：下拉与按钮都不许截断它」：names and ids are not ellipsized |
| 28 | `RegisterTest` | `test_catalog_callback_hot_reads_the_file` | 覆盖「A class whose instances are single test cases」：catalog callback hot reads the file |
| 29 | `RegisterTest` | `test_register_contributes_catalog_route_and_boot_script` | 覆盖「A class whose instances are single test cases」：register contributes catalog route and boot script |
| 30 | `RegisterTest` | `test_reregister_does_not_duplicate_defaults` | 覆盖「A class whose instances are single test cases」：reregister does not duplicate defaults |

## test_plugin_contributions.py

共 32 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContributionRegistryTest` | `test_action_click_contract_and_placement` | 覆盖「A class whose instances are single test cases」：action click contract and placement |
| 2 | `ContributionRegistryTest` | `test_action_click_url_must_stay_in_plugin_namespace` | 覆盖「A class whose instances are single test cases」：action click url must stay in plugin namespace |
| 3 | `ContributionRegistryTest` | `test_action_explicit_panel` | 覆盖「A class whose instances are single test cases」：action explicit panel |
| 4 | `ContributionRegistryTest` | `test_action_register_and_dispose` | 覆盖「A class whose instances are single test cases」：action register and dispose |
| 5 | `ContributionRegistryTest` | `test_boot_script_register_and_dispose` | 覆盖「A class whose instances are single test cases」：boot script register and dispose |
| 6 | `ContributionRegistryTest` | `test_boot_script_rejects_escape` | 覆盖「A class whose instances are single test cases」：boot script rejects escape |
| 7 | `ContributionRegistryTest` | `test_ctx_segment_style_register_and_dispose` | 覆盖「A class whose instances are single test cases」：ctx segment style register and dispose |
| 8 | `ContributionRegistryTest` | `test_drop_plugin_removes_every_kind` | 覆盖「A class whose instances are single test cases」：drop plugin removes every kind |
| 9 | `ContributionRegistryTest` | `test_panel_duplicate_rejected` | 覆盖「A class whose instances are single test cases」：panel duplicate rejected |
| 10 | `ContributionRegistryTest` | `test_panel_explicit_script_wins` | 覆盖「A class whose instances are single test cases」：panel explicit script wins |
| 11 | `ContributionRegistryTest` | `test_panel_register_and_dispose` | 覆盖「A class whose instances are single test cases」：panel register and dispose |
| 12 | `ContributionRegistryTest` | `test_panel_script_file_builds_asset_url` | 覆盖「A class whose instances are single test cases」：panel script file builds asset url |
| 13 | `ContributionRegistryTest` | `test_panel_script_file_rejects_escape` | 覆盖「A class whose instances are single test cases」：panel script file rejects escape |
| 14 | `ContributionRegistryTest` | `test_route_duplicate_rejected` | 覆盖「A class whose instances are single test cases」：route duplicate rejected |
| 15 | `ContributionRegistryTest` | `test_route_exact_match` | 覆盖「A class whose instances are single test cases」：route exact match |
| 16 | `ContributionRegistryTest` | `test_route_exact_wins_over_parameter` | 同时声明 `tasks` 与 `tasks/:sid` 时，`tasks` 不能被参数路由抢走。 |
| 17 | `ContributionRegistryTest` | `test_route_methods_supported` | 覆盖「A class whose instances are single test cases」：route methods supported |
| 18 | `ContributionRegistryTest` | `test_route_multi_segment_parameter` | 覆盖「A class whose instances are single test cases」：route multi segment parameter |
| 19 | `ContributionRegistryTest` | `test_route_path_parameter` | 覆盖「A class whose instances are single test cases」：route path parameter |
| 20 | `ContributionRegistryTest` | `test_route_rejects_bad_parameter_name` | 覆盖「A class whose instances are single test cases」：route rejects bad parameter name |
| 21 | `ContributionRegistryTest` | `test_route_rejects_bad_paths` | 覆盖「A class whose instances are single test cases」：route rejects bad paths |
| 22 | `ContributionRegistryTest` | `test_route_rejects_bad_plugin_and_method` | 覆盖「A class whose instances are single test cases」：route rejects bad plugin and method |
| 23 | `ContributionRegistryTest` | `test_route_segment_count_must_match` | 覆盖「A class whose instances are single test cases」：route segment count must match |
| 24 | `ExternalPluginRootAssetTest` | `test_plugin_asset_uses_tracked_root` | 覆盖「外部 path= 插件：资产根走 plugin_root，而不是 plugins_dir/<na…」：plugin asset uses tracked root |
| 25 | `PluginAssetUrlTest` | `test_asset_rel_parsing` | 覆盖「面板脚本资产路径的解析（壳层按它取文件）」：asset rel parsing |
| 26 | `PluginContextContributionTest` | `test_ctx_add_context_source_returns_disposer` | 覆盖「A class whose instances are single test cases」：ctx add context source returns disposer |
| 27 | `PluginContextContributionTest` | `test_ctx_namespaces_contributions_by_plugin` | 覆盖「A class whose instances are single test cases」：ctx namespaces contributions by plugin |
| 28 | `PluginContextContributionTest` | `test_data_dir_is_per_plugin_and_created` | 覆盖「A class whose instances are single test cases」：data dir is per plugin and created |
| 29 | `PluginContextContributionTest` | `test_data_dir_none_without_host_root` | 覆盖「A class whose instances are single test cases」：data dir none without host root |
| 30 | `PluginContextContributionTest` | `test_data_dir_path_is_absolute` | 覆盖「A class whose instances are single test cases」：data dir path is absolute |
| 31 | `PluginContextContributionTest` | `test_data_dir_sanitizes_plugin_name` | 覆盖「A class whose instances are single test cases」：data dir sanitizes plugin name |
| 32 | `PluginContextContributionTest` | `test_register_fail_after_add_panel_rolls_back` | register 在 add_panel 之后抛错 → 面板不得留在贡献表。 |

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
| 17 | `PluginHttpTest` | `test_shell_public_stylesheet_does_not_carry_plugin_styles` | 壳层的公共样式表里不该出现插件专属的样式规则。 |
| 18 | `PluginHttpTest` | `test_unknown_path_and_plugin_are_404` | 覆盖「真服务 + 夹具插件；整类共用一个实例」：unknown path and plugin are 404 |

## test_plugins.py

共 29 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AppWiringTest` | `test_build_app_empty_whitelist_noop` | 覆盖「A class whose instances are single test cases」：build app empty whitelist noop |
| 2 | `AppWiringTest` | `test_build_app_loads_whitelisted_plugin` | 覆盖「A class whose instances are single test cases」：build app loads whitelisted plugin |
| 3 | `ConfigParseTest` | `test_get_plugins_parse` | 清单解析只做解析：`[plugin:<名字>]` 节，节里没有字段也合法。 |
| 4 | `ConfigParseTest` | `test_load_logs_source_integrity` | 装载时 stderr 须留下入口文件来源与完整性摘要。 |
| 5 | `ConfigParseTest` | `test_load_manifest_resolves_paths_and_reports_errors` | 装载方把 `path` 落到自己的插件根，并把配置错误变成报告。 |
| 6 | `ConfigParseTest` | `test_profile_overlay_overrides_named_fields` | profile 只覆盖显式字段，未声明项继承基底。 |
| 7 | `ConfigParseTest` | `test_tree_only_rejects_external_path` | plugin_tree_only 打开时，清单里的树外 path 不得装载。 |
| 8 | `PluginGateTest` | `test_gate_rollback_on_register_error` | 覆盖「插件门控接缝：注册期可加检查扩展点（pre-gate）」：gate rollback on register error |
| 9 | `PluginGateTest` | `test_missing_pipeline_guards_and_post_observer` | 覆盖「插件门控接缝：注册期可加检查扩展点（pre-gate）」：missing pipeline guards and post observer |
| 10 | `PluginGateTest` | `test_pre_gate_blocks_then_unload_releases` | 覆盖「插件门控接缝：注册期可加检查扩展点（pre-gate）」：pre gate blocks then unload releases |
| 11 | `PluginHostTest` | `test_broken_import_isolated` | 覆盖「加载器行为（临时目录造插件）」：broken import isolated |
| 12 | `PluginHostTest` | `test_discover_filters` | 覆盖「加载器行为（临时目录造插件）」：discover filters |
| 13 | `PluginHostTest` | `test_discover_missing_dir` | 覆盖「加载器行为（临时目录造插件）」：discover missing dir |
| 14 | `PluginHostTest` | `test_load_enabled_filters_by_whitelist` | 覆盖「加载器行为（临时目录造插件）」：load enabled filters by whitelist |
| 15 | `PluginHostTest` | `test_missing_register_reports_error` | 覆盖「加载器行为（临时目录造插件）」：missing register reports error |
| 16 | `PluginHostTest` | `test_module_namespace_and_unload` | 覆盖「加载器行为（临时目录造插件）」：module namespace and unload |
| 17 | `PluginHostTest` | `test_plugin_tool_runs_via_pipeline` | 覆盖「加载器行为（临时目录造插件）」：plugin tool runs via pipeline |
| 18 | `PluginHostTest` | `test_register_raises_rolls_back` | 覆盖「加载器行为（临时目录造插件）」：register raises rolls back |
| 19 | `PluginHostTest` | `test_register_via_ctx_returns_none` | 覆盖「加载器行为（临时目录造插件）」：register via ctx returns none |
| 20 | `PluginHostTest` | `test_relative_submodule_import` | 覆盖「加载器行为（临时目录造插件）」：relative submodule import |
| 21 | `PluginHostTest` | `test_reload_skips_loaded` | 覆盖「加载器行为（临时目录造插件）」：reload skips loaded |
| 22 | `PluginHostTest` | `test_reports_accumulate` | 覆盖「加载器行为（临时目录造插件）」：reports accumulate |
| 23 | `PluginHostTest` | `test_returned_disposer_list_reverse_order` | 覆盖「加载器行为（临时目录造插件）」：returned disposer list reverse order |
| 24 | `PluginHostTest` | `test_unknown_name_reports_error` | 覆盖「加载器行为（临时目录造插件）」：unknown name reports error |
| 25 | `PluginHostTest` | `test_unload_all_idempotent` | 覆盖「加载器行为（临时目录造插件）」：unload all idempotent |
| 26 | `PluginIdentityFallbackTest` | `test_identity_ignores_plugin_config` | 覆盖「插件身份只来自 `plugin-meta.json`：列表里所有插件走同一条规则」：identity ignores plugin config |
| 27 | `PluginIdentityFallbackTest` | `test_list_plugins_shows_declared_name_without_a_config` | 卡片标题取 `name` 而不是目录名 —— 不能只有配过的插件才显示中文名。 |
| 28 | `PluginIdentityFallbackTest` | `test_meta_supplies_identity_when_config_is_absent` | 覆盖「插件身份只来自 `plugin-meta.json`：列表里所有插件走同一条规则」：meta supplies identity when config is absent |
| 29 | `PluginIdentityFallbackTest` | `test_no_files_falls_back_to_folder_name` | 覆盖「插件身份只来自 `plugin-meta.json`：列表里所有插件走同一条规则」：no files falls back to folder name |

## test_present_tool.py

共 2 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `PresentToolTest` | `test_rejects_missing_and_empty_lists` | 覆盖「A class whose instances are single test cases」：rejects missing and empty lists |
| 2 | `PresentToolTest` | `test_returns_metadata_without_reading_content` | 覆盖「A class whose instances are single test cases」：returns metadata without reading content |

## test_prompt_sections.py

共 2 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `PromptSectionsTest` | `test_extra_sections_sit_inside_the_system_prompt` | 覆盖「同名章节合并与系统提示词注入位置」：extra sections sit inside the system prompt |
| 2 | `PromptSectionsTest` | `test_same_heading_is_merged_once` | 覆盖「同名章节合并与系统提示词注入位置」：same heading is merged once |

## test_prompt_tail.py

共 5 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `PromptTailTest` | `test_empty_source_does_not_add_separator` | 覆盖「A class whose instances are single test cases」：empty source does not add separator |
| 2 | `PromptTailTest` | `test_failing_source_does_not_block_other_sources` | 覆盖「A class whose instances are single test cases」：failing source does not block other sources |
| 3 | `PromptTailTest` | `test_non_callable_source_is_rejected` | 覆盖「A class whose instances are single test cases」：non callable source is rejected |
| 4 | `PromptTailTest` | `test_renders_in_registration_order_and_disposes_idempotently` | 覆盖「A class whose instances are single test cases」：renders in registration order and disposes idempotently |
| 5 | `PromptTailTest` | `test_subagent_hidden_source_is_not_rendered` | 覆盖「A class whose instances are single test cases」：subagent hidden source is not rendered |

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

## test_provider_meta.py

共 8 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `DeriveMessagesMetaTest` | `test_old_logs_without_the_key_still_derive` | 覆盖「A class whose instances are single test cases」：old logs without the key still derive |
| 2 | `DeriveMessagesMetaTest` | `test_provider_meta_survives_replay` | 覆盖「A class whose instances are single test cases」：provider meta survives replay |
| 3 | `DeriveMessagesMetaTest` | `test_unknown_subkeys_are_carried_not_validated` | 覆盖「A class whose instances are single test cases」：unknown subkeys are carried not validated |
| 4 | `LlmEventModelTest` | `test_done_reports_request_model` | 覆盖「模型生命周期事件必须报告本次请求的模型，而不是 provider 默认值」：done reports request model |
| 5 | `ModelMessageMetaTest` | `test_later_meta_wins_on_shared_keys` | 覆盖「A class whose instances are single test cases」：later meta wins on shared keys |
| 6 | `ModelMessageMetaTest` | `test_meta_delta_is_collected_verbatim` | 覆盖「A class whose instances are single test cases」：meta delta is collected verbatim |
| 7 | `ModelMessageMetaTest` | `test_no_meta_delta_leaves_the_key_absent` | 覆盖「A class whose instances are single test cases」：no meta delta leaves the key absent |
| 8 | `OpenAiWireNeverSeesMetaTest` | `test_wire_messages_strip_provider_meta` | 覆盖「A class whose instances are single test cases」：wire messages strip provider meta |

## test_provider_router.py

共 14 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `RoutedStreamTest` | `test_allowed_models_is_an_immutable_record` | 覆盖「A class whose instances are single test cases」：allowed models is an immutable record |
| 2 | `RoutedStreamTest` | `test_catalog_id_is_rewritten_to_the_provider_model_name` | 覆盖「A class whose instances are single test cases」：catalog id is rewritten to the provider model name |
| 3 | `RoutedStreamTest` | `test_empty_model_falls_back_to_default_id_resolution` | 覆盖「A class whose instances are single test cases」：empty model falls back to default id resolution |
| 4 | `RoutedStreamTest` | `test_fallback_applies_only_to_allowed_ids` | 覆盖「A class whose instances are single test cases」：fallback applies only to allowed ids |
| 5 | `RoutedStreamTest` | `test_fallback_is_off_by_default` | 覆盖「A class whose instances are single test cases」：fallback is off by default |
| 6 | `RoutedStreamTest` | `test_model_property_prefers_default_id` | 覆盖「A class whose instances are single test cases」：model property prefers default id |
| 7 | `RoutedStreamTest` | `test_provider_without_model_name_gets_the_request_unchanged` | 覆盖「A class whose instances are single test cases」：provider without model name gets the request unchanged |
| 8 | `RoutedStreamTest` | `test_reload_default_is_visible_through_default_provider` | 覆盖「A class whose instances are single test cases」：reload default is visible through default provider |
| 9 | `RoutedStreamTest` | `test_reload_default_takes_effect_on_the_next_request` | 覆盖「A class whose instances are single test cases」：reload default takes effect on the next request |
| 10 | `RoutedStreamTest` | `test_reload_policy_can_disable_fallback` | 覆盖「A class whose instances are single test cases」：reload policy can disable fallback |
| 11 | `RoutedStreamTest` | `test_reload_policy_updates_model_and_allowed_models` | 覆盖「A class whose instances are single test cases」：reload policy updates model and allowed models |
| 12 | `RoutedStreamTest` | `test_router_without_default_id_uses_default_instance` | 覆盖「A class whose instances are single test cases」：router without default id uses default instance |
| 13 | `RoutedStreamTest` | `test_routes_to_the_requested_model` | 覆盖「A class whose instances are single test cases」：routes to the requested model |
| 14 | `RoutedStreamTest` | `test_unknown_model_raises_instead_of_silently_using_default` | 覆盖「A class whose instances are single test cases」：unknown model raises instead of silently using default |

## test_quality_pipeline.py

共 18 个用例。

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
| 13 | `RereadAnchorTest` | `test_anchor_follows_file_not_stale_number` | 文件前面插入一行后，同一个 old_text 的锚点行号跟着变。 |
| 14 | `RereadAnchorTest` | `test_anchor_for_whole_file_write` | 整体覆盖类：给当前行数与字节数，供对照自己预期覆盖的内容。 |
| 15 | `RereadAnchorTest` | `test_anchor_reports_missing_old_text` | old_text 已被上次写入改掉：如实说找不到，不给假行号。 |
| 16 | `RereadAnchorTest` | `test_anchor_reports_stale_line_range` | 行区间超出当前文件：直接说行号过期。 |
| 17 | `RereadAnchorTest` | `test_anchor_when_file_missing` | 目标文件读不到：如实说明，不编造锚点。 |
| 18 | `RereadAnchorTest` | `test_literal_anchor_shows_current_line` | 字面替换：给出 old_text 在当前文件里的行号与那一行内容。 |

## test_queue_runner.py

共 3 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `PausedQueueTest` | `test_host_paused_flag_keeps_queue` | 覆盖「A class whose instances are single test cases」：host paused flag keeps queue |
| 2 | `PausedQueueTest` | `test_new_input_cancels_pending_confirm` | 覆盖「A class whose instances are single test cases」：new input cancels pending confirm |
| 3 | `PausedQueueTest` | `test_paused_turn_keeps_queue` | 覆盖「A class whose instances are single test cases」：paused turn keeps queue |

## test_queued_input.py

共 4 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `QueuedInputModuleTest` | `test_batch_contains_system_agent_and_user_inserts_only` | 覆盖「A class whose instances are single test cases」：batch contains system agent and user inserts only |
| 2 | `QueuedInputModuleTest` | `test_batch_emits_each_input_as_a_separate_fact` | 覆盖「A class whose instances are single test cases」：batch emits each input as a separate fact |
| 3 | `QueuedInputModuleTest` | `test_claims_one_insert_item_and_emits_input_fact` | 覆盖「A class whose instances are single test cases」：claims one insert item and emits input fact |
| 4 | `QueuedInputModuleTest` | `test_no_insert_item_is_noop` | 覆盖「A class whose instances are single test cases」：no insert item is noop |

## test_readonly_tools.py

共 33 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `GlobFilesToolTest` | `test_derived_dirs_skipped_and_reported` | 默认剪 .git / __pycache__；回执报数；include_derived 可显式放开。 |
| 2 | `GlobFilesToolTest` | `test_entry_type_dir` | 目录过滤。 |
| 3 | `GlobFilesToolTest` | `test_invalid_entry_type_raises` | 非法 entry_type 抛 ValueError。 |
| 4 | `GlobFilesToolTest` | `test_limit_truncation` | limit 截断并标记。 |
| 5 | `GlobFilesToolTest` | `test_non_recursive` | 非递归仅当前层。 |
| 6 | `GlobFilesToolTest` | `test_path_not_dir_raises` | path 指向文件而非目录时抛 ValueError。 |
| 7 | `GlobFilesToolTest` | `test_recursive_default` | 默认递归；**/ 前缀剥除。 |
| 8 | `GrepFilesToolTest` | `test_binary_file_skipped` | 含 NUL 字节的文件被跳过（二进制嗅探）。 |
| 9 | `GrepFilesToolTest` | `test_blank_pattern_says_what_to_fix` | 字面模式 \| 分隔后无有效段：只说 pattern 与 regex 两个真正相关的处置。 |
| 10 | `GrepFilesToolTest` | `test_limit_truncation` | limit 截断并标记。 |
| 11 | `GrepFilesToolTest` | `test_literal_hits` | 字面命中（含子目录；相对路径输出）。 |
| 12 | `GrepFilesToolTest` | `test_missing_path_is_not_reported_as_wrong_type` | 路径不存在与类型不对必须分开说：两者处置完全不同。 |
| 13 | `GrepFilesToolTest` | `test_missing_pattern_raises` | 缺少 pattern 抛 ValueError。 |
| 14 | `GrepFilesToolTest` | `test_no_match` | 无命中：空结果不截断。 |
| 15 | `GrepFilesToolTest` | `test_or_separator` | 字面模式 \| 为 OR 分隔。 |
| 16 | `GrepFilesToolTest` | `test_path_not_dir_raises` | path 指向文件：说清本工具只搜目录，并给出真能吃下单文件的工具。 |
| 17 | `GrepFilesToolTest` | `test_regex_and_ignore_case` | 正则 + 忽略大小写（三个文件行首均命中：alpha / Alpha / alpha deep）。 |
| 18 | `ReadFileToolTest` | `test_empty_file` | 空文件：返回空内容与 0 行，不报错。 |
| 19 | `ReadFileToolTest` | `test_invalid_range_raises` | start 超出总行数时抛 ValueError。 |
| 20 | `ReadFileToolTest` | `test_max_chars_truncation` | max_chars 截断并标记。 |
| 21 | `ReadFileToolTest` | `test_missing_file_raises` | 文件不存在抛 FileNotFoundError（管道回灌）。 |
| 22 | `ReadFileToolTest` | `test_missing_path_raises` | 缺少 path 抛 ValueError。 |
| 23 | `ReadFileToolTest` | `test_range_clamped_to_end` | line_end 超界时 clamp 到文件尾。 |
| 24 | `ReadFileToolTest` | `test_read_full_text` | 全文读取。 |
| 25 | `ReadFileToolTest` | `test_read_line_range` | 行区间切片（1-based 闭区间）。 |
| 26 | `RegistryPipelineIntegrationTest` | `test_register_and_execute_via_pipeline` | 三工具注册进 ToolRegistry；经 ToolPipeline.execute 驱动 read_file。 |
| 27 | `RegistryPipelineIntegrationTest` | `test_tool_error_structured` | 工具异常：管道捕获为 ok=False 回灌。 |
| 28 | `RegistryPipelineIntegrationTest` | `test_unknown_tool_via_pipeline` | 未注册工具名：管道结构化回灌（不抛异常）。 |
| 29 | `ScopeTest` | `test_data_is_searched_by_default` | data 不是通用产物目录名，默认就该被搜到。 |
| 30 | `ScopeTest` | `test_default_only_prunes_git_and_bytecode` | 默认名单只含 .git 与 __pycache__，跳过数如实报出。 |
| 31 | `ScopeTest` | `test_exclude_echoes_what_was_asked` | 回执原样回显调用方传的排除名单，便于自查是否漏传。 |
| 32 | `ScopeTest` | `test_exclude_names_are_honoured` | 点名排除的目录两个工具都不再搜。 |
| 33 | `ScopeTest` | `test_include_derived_does_not_undo_exclude` | include_derived 只放开默认名单，点名排除的仍排除。 |

## test_resume_bridge.py

共 6 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ResumeBridgeTest` | `test_host_holds_no_suspend_state` | 宿主不保存挂起游标：它的实例字段里没有"停在哪"这类信息。 |
| 2 | `ResumeBridgeTest` | `test_model_sees_the_result_on_the_next_pass` | 回灌后工具模块返回 `next`，宿主再跑一趟 → 模型才看得到结果。 |
| 3 | `ResumeBridgeTest` | `test_recovers_after_restart` | ③ 重启后仍能恢复：丢掉宿主与全部模块对象，只从事实重建。 |
| 4 | `ResumeBridgeTest` | `test_result_is_not_delivered_twice` | 回灌不会重复：`tool_result` 已存在就不再发（同一调用只交一次）。 |
| 5 | `ResumeBridgeTest` | `test_resume_delivers_the_result_as_an_ordinary_tool_result` | ② 回灌就是一次普通的 tool_result，没有特殊规则。 |
| 6 | `ResumeBridgeTest` | `test_suspend_is_terminal_and_resume_is_a_new_run` | ① 挂起即终态；恢复是新回合宿主循环，不是回到旧循环。 |

## test_rules_plugin.py

共 12 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `RulesRegisterTest` | `test_dispose_removes_injection` | 覆盖「A class whose instances are single test cases」：dispose removes injection |
| 2 | `RulesRegisterTest` | `test_resource_section_lines` | 覆盖「A class whose instances are single test cases」：resource section lines |
| 3 | `RulesRegisterTest` | `test_resource_section_marks_missing_dir` | 覆盖「A class whose instances are single test cases」：resource section marks missing dir |
| 4 | `RulesRegisterTest` | `test_segment_key_label_and_count` | 覆盖「A class whose instances are single test cases」：segment key label and count |
| 5 | `RulesRegisterTest` | `test_segment_style_registered` | 覆盖「A class whose instances are single test cases」：segment style registered |
| 6 | `RulesRuntimeTest` | `test_cache_reuses_content_until_file_changes` | 覆盖「A class whose instances are single test cases」：cache reuses content until file changes |
| 7 | `RulesRuntimeTest` | `test_count_matches_messages` | 覆盖「A class whose instances are single test cases」：count matches messages |
| 8 | `RulesRuntimeTest` | `test_missing_dir_stays_quiet` | 覆盖「A class whose instances are single test cases」：missing dir stays quiet |
| 9 | `RulesRuntimeTest` | `test_missing_file_read_returns_empty` | 覆盖「A class whose instances are single test cases」：missing file read returns empty |
| 10 | `RulesRuntimeTest` | `test_one_message_per_file_with_prefix` | 覆盖「A class whose instances are single test cases」：one message per file with prefix |
| 11 | `RulesRuntimeTest` | `test_only_markdown_recursive_and_skips_hidden` | 覆盖「A class whose instances are single test cases」：only markdown recursive and skips hidden |
| 12 | `RulesRuntimeTest` | `test_oversized_file_is_skipped` | 覆盖「A class whose instances are single test cases」：oversized file is skipped |

## test_run_registry.py

共 13 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `DrainWindowTest` | `test_end_run_releases_when_idle` | 覆盖「续占必须全程不露出空闲窗口」：end run releases when idle |
| 2 | `DrainWindowTest` | `test_renew_never_exposes_idle_window` | 覆盖「续占必须全程不露出空闲窗口」：renew never exposes idle window |
| 3 | `FileRunRegistryTest` | `test_broken_file_is_treated_as_not_running` | 坏文件不能让读取方崩，也不能把垃圾当成"在跑"。 |
| 4 | `FileRunRegistryTest` | `test_build_switches_implementation_by_directory` | 覆盖「落盘实现：跨实例可见 + 崩溃自愈」：build switches implementation by directory |
| 5 | `FileRunRegistryTest` | `test_stale_entry_self_heals` | 崩溃残留（进程被 kill，心跳停）：超过存活期后应被判为过期并清掉。 |
| 6 | `FileRunRegistryTest` | `test_state_is_visible_across_instances` | 核心诉求：另一个实例（另一个 registry 对象）能看到"在跑"。 |
| 7 | `FileRunRegistryTest` | `test_touch_keeps_long_run_alive` | 长任务靠续心跳保活（否则 120 秒的 ping 会被误判成已结束）。 |
| 8 | `InMemoryRunRegistryTest` | `test_claim_release_renew` | 覆盖「纯内存实现：单实例语义」：claim release renew |
| 9 | `InMemoryRunRegistryTest` | `test_running_cids_snapshot` | 覆盖「纯内存实现：单实例语义」：running cids snapshot |
| 10 | `PidAliveTest` | `test_claim_then_running_is_true_in_this_process` | `claim()` 之后 `running()` 必须为 True（记录里写的是本进程 pid）。 |
| 11 | `PidAliveTest` | `test_invalid_pid_forms_are_dead` | 非法形态不抛异常，一律判死（None / 0 / 负数 / 非数字）。 |
| 12 | `PidAliveTest` | `test_live_pid_is_alive` | 当前进程的 pid 必须判活 —— 这是最直接的判据。 |
| 13 | `PidAliveTest` | `test_nonexistent_pid_is_dead` | 不存在的 pid 必须判死，否则过期记录永远不回收。 |

## test_scan_js_events.py

共 54 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ArrowAnonymousTest` | `test_arrow_callback_is_anonymous` | 覆盖「第 2 条：箭头回调也算匿名，否则全局监听的泄漏会被降级」：arrow callback is anonymous |
| 2 | `ArrowAnonymousTest` | `test_arrow_global_listener_in_render_fn_is_leak_risk` | 覆盖「第 2 条：箭头回调也算匿名，否则全局监听的泄漏会被降级」：arrow global listener in render fn is leak risk |
| 3 | `ArrowAnonymousTest` | `test_async_arrow_callback_is_anonymous` | 覆盖「第 2 条：箭头回调也算匿名，否则全局监听的泄漏会被降级」：async arrow callback is anonymous |
| 4 | `ArrowAnonymousTest` | `test_named_handler_reference_is_not_anonymous` | 负向：具名函数引用可以摘除，不算匿名。 |
| 5 | `ArrowAnonymousTest` | `test_paren_arrow_callback_is_anonymous` | 覆盖「第 2 条：箭头回调也算匿名，否则全局监听的泄漏会被降级」：paren arrow callback is anonymous |
| 6 | `ArrowRenderFnTest` | `test_arrow_assigned_non_render_fn_is_not_render` | 负向：非渲染名的箭头函数不该被当成渲染路径。 |
| 7 | `ArrowRenderFnTest` | `test_arrow_assigned_render_fn_is_named` | 覆盖「第 3 条：箭头函数赋值也要认成具名函数」：arrow assigned render fn is named |
| 8 | `ArrowRenderFnTest` | `test_expression_body_arrow_has_no_span` | 负向：表达式体箭头没有块体，不该吞掉后面的代码。 |
| 9 | `CollectTest` | `test_collects_add_listener_property_and_delegation` | 覆盖「A class whose instances are single test cases」：collects add listener property and delegation |
| 10 | `CollectTest` | `test_collects_inline_html_and_renders_report` | 覆盖「A class whose instances are single test cases」：collects inline html and renders report |
| 11 | `CollectTest` | `test_property_assignment_matches_camel_case` | `onMouseDown` 这类大写事件名也要认，不能只匹配 `on[a-z]+`。 |
| 12 | `CommentTest` | `test_bindings_inside_comments_are_ignored` | 注释里的示例代码不是绑定——块注释与行内 `//` 都不算。 |
| 13 | `CommentTest` | `test_double_slash_inside_string_is_not_a_comment` | URL 里的 `//` 不得把后面的代码当成注释吞掉。 |
| 14 | `DelegateScopeTest` | `test_current_target_contains_is_delegation` | 覆盖「第 5 条：contains 只在事件对象上才算委托」：current target contains is delegation |
| 15 | `DelegateScopeTest` | `test_event_target_closest_is_delegation` | 覆盖「第 5 条：contains 只在事件对象上才算委托」：event target closest is delegation |
| 16 | `DelegateScopeTest` | `test_unrelated_contains_is_not_delegation` | 覆盖「第 5 条：contains 只在事件对象上才算委托」：unrelated contains is not delegation |
| 17 | `EphemeralTest` | `test_bare_assignment_is_recognised` | 模块级申明、函数内懒赋值（无 var 前缀）也要认出来。 |
| 18 | `EphemeralTest` | `test_create_element_and_factory_count_as_new_node` | `createElement` 与本项目 `el()` 工厂都算新建节点。 |
| 19 | `EphemeralTest` | `test_lookup_wins_over_create` | 取节点的函数优先：`getXxx()` 指向已有容器，内部用 createElement 也不算新节点。 |
| 20 | `EphemeralTest` | `test_new_node_binding_is_excluded_as_ephemeral` | 覆盖「A class whose instances are single test cases」：new node binding is excluded as ephemeral |
| 21 | `GuardTest` | `test_container_delegation_in_render_fn_is_not_render_path` | 容器根委托写在渲染函数里也是正确写法，不该报可能累积。 |
| 22 | `GuardTest` | `test_existing_guard_marker_is_recognised` | 项目既有的 `_xxxDelegated` 惯例要被认出来，不能与可疑项同形。 |
| 23 | `LeakRiskTest` | `test_anonymous_callback_is_not_paired` | 覆盖「A class whose instances are single test cases」：anonymous callback is not paired |
| 24 | `LeakRiskTest` | `test_anonymous_global_listener_in_render_fn_is_leak_risk` | 覆盖「A class whose instances are single test cases」：anonymous global listener in render fn is leak risk |
| 25 | `LeakRiskTest` | `test_capture_mismatch_is_not_paired` | 覆盖「A class whose instances are single test cases」：capture mismatch is not paired |
| 26 | `LeakRiskTest` | `test_different_callback_is_not_paired` | 覆盖「A class whose instances are single test cases」：different callback is not paired |
| 27 | `LeakRiskTest` | `test_module_level_global_listener_is_not_leak_risk` | 模块级只绑一次，不是泄漏——负向用例，防止判准退回旧版。 |
| 28 | `LeakRiskTest` | `test_paired_remove_clears_leak_risk` | 同文件、同目标、同事件、同回调、同 capture 才清除泄漏。 |
| 29 | `LoopBodyTest` | `test_binding_after_for_header_is_not_loop` | 负向：循环体结束之后的绑定不算循环内。 |
| 30 | `LoopBodyTest` | `test_create_element_inside_for_is_per_item` | 目标随节点新建也不能顶掉循环内这个结论。 |
| 31 | `LoopBodyTest` | `test_for_in_body_counts_as_loop` | 覆盖「第 1、4 条：语句式循环的循环体必须进 span，光配平头部括号不够」：for in body counts as loop |
| 32 | `LoopBodyTest` | `test_for_loop_body_counts_as_loop` | 覆盖「第 1、4 条：语句式循环的循环体必须进 span，光配平头部括号不够」：for loop body counts as loop |
| 33 | `LoopBodyTest` | `test_for_of_body_counts_as_loop` | 覆盖「第 1、4 条：语句式循环的循环体必须进 span，光配平头部括号不够」：for of body counts as loop |
| 34 | `LoopBodyTest` | `test_while_loop_body_counts_as_loop` | 覆盖「第 1、4 条：语句式循环的循环体必须进 span，光配平头部括号不够」：while loop body counts as loop |
| 35 | `LoopVerdictTest` | `test_binding_after_loop_is_not_per_item` | 循环结束后的绑定不算逐项绑——按花括号配平判，不按缩进或行序。 |
| 36 | `LoopVerdictTest` | `test_binding_inside_loop_is_per_item` | 覆盖「A class whose instances are single test cases」：binding inside loop is per item |
| 37 | `NamedGlobalListenerTest` | `test_named_global_listener_at_module_level_is_global_once` | 负向：模块级只绑一次，具名与否都不算泄漏。 |
| 38 | `NamedGlobalListenerTest` | `test_named_global_listener_in_render_fn_is_leak_risk` | 覆盖「具名回调只代表「能摘除」，不代表「已摘除」」：named global listener in render fn is leak risk |
| 39 | `NamedGlobalListenerTest` | `test_named_global_listener_with_remove_is_global_once` | 负向：真摘了就不算泄漏。 |
| 40 | `NestedRenderContextTest` | `test_binding_in_nested_fn_inside_render_is_render_path` | 覆盖「渲染上下文看整条函数链：绑定写在内层小函数里，外层重建一样会反复安装」：binding in nested fn inside render is render path |
| 41 | `NestedRenderContextTest` | `test_binding_in_nested_fn_outside_render_is_not_render_path` | 负向：外层不叫渲染名时，不能因为嵌套就报渲染路径。 |
| 42 | `ObjectMethodRenderTest` | `test_control_flow_header_is_not_a_method` | 负向：`if(...){` 这类语句头不能被当成对象方法。 |
| 43 | `ObjectMethodRenderTest` | `test_function_valued_object_method_is_named` | 覆盖「对象方法两种写法都要认成具名函数」：function valued object method is named |
| 44 | `ObjectMethodRenderTest` | `test_shorthand_object_method_is_named` | 覆盖「对象方法两种写法都要认成具名函数」：shorthand object method is named |
| 45 | `PairedRemoveTest` | `test_different_event_remove_keeps_leak_risk` | 负向：同目标但事件名不同，不算配对。 |
| 46 | `PairedRemoveTest` | `test_other_element_remove_keeps_leak_risk` | 覆盖「第 6 条：摘除要同目标同事件，别的元素摘同名事件不解绑这一个」：other element remove keeps leak risk |
| 47 | `PairedRemoveTest` | `test_same_target_remove_clears_leak_risk` | 覆盖「第 6 条：摘除要同目标同事件，别的元素摘同名事件不解绑这一个」：same target remove clears leak risk |
| 48 | `ReadGuideTest` | `test_read_guide_counts_match_constants` | 覆盖「第 10 条：文案里的类别数要和常量一致，不靠手写」：read guide counts match constants |
| 49 | `RenderOutputTest` | `test_clean_input_reports_nothing_to_review` | 覆盖「A class whose instances are single test cases」：clean input reports nothing to review |
| 50 | `RenderOutputTest` | `test_report_states_intent_and_read_guide` | 输出本身要写明初衷与读法，换一个会话说不用翻文档也懂。 |
| 51 | `ScopeVerdictTest` | `test_global_container_element_are_distinguished` | 绑全局 / 容器根+closest / 元素自身，是三种不同结论。 |
| 52 | `StringBracketTest` | `test_string_with_paren_does_not_truncate_callback` | 覆盖「第 7 条：配平要跳过字符串，否则回调会被提前截断」：string with paren does not truncate callback |
| 53 | `StringBracketTest` | `test_string_with_paren_keeps_handler_detection` | 负向对照：字符串里的括号不得让具名回调被误判成匿名。 |
| 54 | `StringBracketTest` | `test_template_literal_with_braces_is_skipped` | 覆盖「第 7 条：配平要跳过字符串，否则回调会被提前截断」：template literal with braces is skipped |

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
| 19 | `SharedContainerTest` | `test_gate_factory_required` | 覆盖「live 为装配级共享容器」：gate factory required |
| 20 | `SharedContainerTest` | `test_live_shared_by_reference` | 覆盖「live 为装配级共享容器」：live shared by reference |
| 21 | `SharedContainerTest` | `test_shared_live_is_still_partitioned_by_cid` | 覆盖「live 为装配级共享容器」：shared live is still partitioned by cid |
| 22 | `ThreadSafetyTest` | `test_concurrent_first_use_yields_single_context` | 覆盖「线程安全」：concurrent first use yields single context |

## test_session_seq.py

共 23 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `SeqAssignmentTest` | `test_blank_lines_do_not_shift_positions` | 空行不占号：否则"下一个序号"会随空白漂移。 |
| 2 | `SeqAssignmentTest` | `test_conversation_id_is_not_persisted` | 会话 ID 由文件名承载，落盘行里不存；读回时按会话补进载荷。 |
| 3 | `SeqAssignmentTest` | `test_line_count_matches_next_seq` | `line_count` 就是"下一个可用序号"——`App._seq_next` 靠它播种。 |
| 4 | `SeqAssignmentTest` | `test_load_still_returns_plain_events` | `load()` 的返回形状不变（既有调用方与测试都按纯事件列表用）。 |
| 5 | `SeqAssignmentTest` | `test_seq_continues_across_appends` | 跨批连续：第二批接着第一批的号，不从头开始（约 500 行一批的 flush 依赖此）。 |
| 6 | `SeqAssignmentTest` | `test_seq_is_written_to_each_line` | 覆盖「写入即定位：序号按会话日志位置连续编」：seq is written to each line |
| 7 | `SeqAssignmentTest` | `test_seq_lives_in_payload_and_top_level_only` | 坐标在落盘行里只占顶层 `seq` 一处；业务字段不被污染。 |
| 8 | `SeqEmptyAndErrorTest` | `test_allocate_seq_survives_restart_without_collision` | 重启后重新构造 store 也不能从 0 重发号（否则与磁盘上的坐标撞号）。 |
| 9 | `SeqEmptyAndErrorTest` | `test_append_after_external_edit_does_not_collide` | 外部插入行后追加，新事件不与既有坐标撞号（全局分配器在存储层，不受文件行数影响）。 |
| 10 | `SeqEmptyAndErrorTest` | `test_append_empty_batch_writes_nothing` | 覆盖「A class whose instances are single test cases」：append empty batch writes nothing |
| 11 | `SeqEmptyAndErrorTest` | `test_coordinates_are_global_across_conversations` | 坐标跨会话单调：这是续传游标能只用一条流一个光标的前提。 |
| 12 | `SeqEmptyAndErrorTest` | `test_encrypted_mode_round_trips_seq` | 加密模式下 seq 也必须能读回（它写在明文里，再整体加密）。 |
| 13 | `SeqEmptyAndErrorTest` | `test_non_object_json_lines_do_not_produce_events` | 合法但非对象的行（`"foo"` / `123`）不产生事件，也不影响已有事件的坐标。 |
| 14 | `SeqEmptyAndErrorTest` | `test_tail_across_uses_one_cursor_for_all_conversations` | `tail_across`：一个游标跨会话续传，按坐标升序。 |
| 15 | `SeqEmptyAndErrorTest` | `test_unparseable_line_is_skipped` | 坏行跳过不渲染；已有事件仍保留各自的落盘坐标（坐标来自字段，不靠数位置）。 |
| 16 | `SeqMissingTest` | `test_appended_rows_use_global_seq` | 继续追加时新行用全局坐标，必然大于同文件里的补号。 |
| 17 | `SeqMissingTest` | `test_coordinates_stay_unique_and_monotonic` | 覆盖「缺坐标的行按行位置补号 —— 手写或外部工具产生的日志也要能读」：coordinates stay unique and monotonic |
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
| 5 | `MeshCoreTest` | `test_agents_persistence_roundtrip` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：agents persistence roundtrip |
| 6 | `MeshCoreTest` | `test_queue_fifo_and_size` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：queue fifo and size |
| 7 | `MeshCoreTest` | `test_renew_run_keeps_claim` | 覆盖「公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）」：renew run keeps claim |
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

共 21 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ApplyHostTest` | `test_apply_updates_limits` | 覆盖「A class whose instances are single test cases」：apply updates limits |
| 2 | `IniEditTest` | `test_append_does_not_duplicate_a_section` | 覆盖「A class whose instances are single test cases」：append does not duplicate a section |
| 3 | `IniEditTest` | `test_remove_section_leaves_commented_header` | 覆盖「A class whose instances are single test cases」：remove section leaves commented header |
| 4 | `IniEditTest` | `test_update_keeps_comments_and_other_sections` | 覆盖「A class whose instances are single test cases」：update keeps comments and other sections |
| 5 | `PluginSettingsTest` | `test_enable_and_disable_edit_the_manifest` | 覆盖「A class whose instances are single test cases」：enable and disable edit the manifest |
| 6 | `PluginSettingsTest` | `test_fields_schema_creates_real_config_from_form` | 覆盖「A class whose instances are single test cases」：fields schema creates real config from form |
| 7 | `PluginSettingsTest` | `test_kernel_model_tab_is_absent` | 覆盖「A class whose instances are single test cases」：kernel model tab is absent |
| 8 | `PluginSettingsTest` | `test_missing_plugin_config_returns_empty_editor` | 没有真实配置时返回空编辑器；不伪造示例、不落盘。 |
| 9 | `PluginSettingsTest` | `test_missing_plugin_is_not_enabled` | 覆盖「A class whose instances are single test cases」：missing plugin is not enabled |
| 10 | `PluginSettingsTest` | `test_plugin_config_roundtrip_rejects_a_bad_name` | 覆盖「A class whose instances are single test cases」：plugin config roundtrip rejects a bad name |
| 11 | `PluginSettingsTest` | `test_unknown_route` | 覆盖「A class whose instances are single test cases」：unknown route |
| 12 | `SaveHostTest` | `test_invalid_number_does_not_write` | 覆盖「A class whose instances are single test cases」：invalid number does not write |
| 13 | `SaveHostTest` | `test_save_rewrites_the_key_and_keeps_the_comment` | 覆盖「A class whose instances are single test cases」：save rewrites the key and keeps the comment |
| 14 | `SettingsBroadcastTest` | `test_invalid_save_does_not_broadcast` | 覆盖「A class whose instances are single test cases」：invalid save does not broadcast |
| 15 | `SettingsBroadcastTest` | `test_success_broadcasts_applied_settings` | 覆盖「A class whose instances are single test cases」：success broadcasts applied settings |
| 16 | `SettingsPageAssetsTest` | `test_gear_and_settings_script_are_inlined` | 覆盖「A class whose instances are single test cases」：gear and settings script are inlined |
| 17 | `StructuredPluginConfigTest` | `test_new_model_group_gets_a_generated_id` | 覆盖「声明了 `settings-schema.json` 的插件：按组编辑，密钥不出接口」：new model group gets a generated id |
| 18 | `StructuredPluginConfigTest` | `test_read_masks_the_secret` | 覆盖「声明了 `settings-schema.json` 的插件：按组编辑，密钥不出接口」：read masks the secret |
| 19 | `StructuredPluginConfigTest` | `test_required_field_rejects_an_empty_value` | 覆盖「声明了 `settings-schema.json` 的插件：按组编辑，密钥不出接口」：required field rejects an empty value |
| 20 | `StructuredPluginConfigTest` | `test_save_keeps_other_sections_and_an_untouched_secret` | 覆盖「声明了 `settings-schema.json` 的插件：按组编辑，密钥不出接口」：save keeps other sections and an untouched secret |
| 21 | `StructuredPluginConfigTest` | `test_save_rejects_an_unknown_key` | 覆盖「声明了 `settings-schema.json` 的插件：按组编辑，密钥不出接口」：save rejects an unknown key |

## test_silent_except_gate.py

共 10 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `SilentExceptGateRunTest` | `test_main_fails_on_broad_pass` | 覆盖「A class whose instances are single test cases」：main fails on broad pass |
| 2 | `SilentExceptGateRunTest` | `test_main_passes_on_narrow_fallback` | 覆盖「A class whose instances are single test cases」：main passes on narrow fallback |
| 3 | `SilentExceptStructureTest` | `test_arbitrary_call_is_not_a_transform` | 覆盖「A class whose instances are single test cases」：arbitrary call is not a transform |
| 4 | `SilentExceptStructureTest` | `test_broad_pass_is_rejected` | 覆盖「A class whose instances are single test cases」：broad pass is rejected |
| 5 | `SilentExceptStructureTest` | `test_explicit_result_is_recognized` | 覆盖「A class whose instances are single test cases」：explicit result is recognized |
| 6 | `SilentExceptStructureTest` | `test_narrow_return_is_allowed` | 覆盖「A class whose instances are single test cases」：narrow return is allowed |
| 7 | `SilentExceptStructureTest` | `test_pass_in_multi_statement_is_rejected` | 覆盖「A class whose instances are single test cases」：pass in multi statement is rejected |
| 8 | `SilentExceptStructureTest` | `test_report_error_is_recognized` | 覆盖「A class whose instances are single test cases」：report error is recognized |
| 9 | `SilentExceptStructureTest` | `test_report_error_needs_payload` | 覆盖「A class whose instances are single test cases」：report error needs payload |
| 10 | `SilentExceptStructureTest` | `test_suppress_exception_is_rejected` | 覆盖「A class whose instances are single test cases」：suppress exception is rejected |

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

## test_subagent.py

共 17 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `BatchStoreTest` | `test_batch_file_is_capped_and_isolated_by_parent` | 覆盖「A class whose instances are single test cases」：batch file is capped and isolated by parent |
| 2 | `ManagerTest` | `test_child_can_send_to_parent_with_source` | 覆盖「A class whose instances are single test cases」：child can send to parent with source |
| 3 | `ManagerTest` | `test_child_turn_end_notifies_parent` | 覆盖「A class whose instances are single test cases」：child turn end notifies parent |
| 4 | `ManagerTest` | `test_create_starts_turn_and_uses_child_store` | 覆盖「A class whose instances are single test cases」：create starts turn and uses child store |
| 5 | `ManagerTest` | `test_insert_send_marks_queue_item` | 覆盖「A class whose instances are single test cases」：insert send marks queue item |
| 6 | `ManagerTest` | `test_label_required_and_batch_scope` | 覆盖「A class whose instances are single test cases」：label required and batch scope |
| 7 | `ManagerTest` | `test_parent_send_and_permissions` | 覆盖「A class whose instances are single test cases」：parent send and permissions |
| 8 | `ManagerTest` | `test_restart_restores_idle_children` | 覆盖「A class whose instances are single test cases」：restart restores idle children |
| 9 | `ManagerTest` | `test_system_prompt_uses_role_tool_view` | 覆盖「A class whose instances are single test cases」：system prompt uses role tool view |
| 10 | `ManagerTest` | `test_tool_schema_and_list` | 覆盖「A class whose instances are single test cases」：tool schema and list |
| 11 | `RegistryVisibilityTest` | `test_plugin_can_hide_tool_from_subagent` | 覆盖「A class whose instances are single test cases」：plugin can hide tool from subagent |
| 12 | `RepositoryBoundaryTest` | `test_batch_files_reject_invalid_ids_and_corrupt_entries` | 覆盖「A class whose instances are single test cases」：batch files reject invalid ids and corrupt entries |
| 13 | `RepositoryBoundaryTest` | `test_explicit_batch_history_and_invalid_boundaries` | 覆盖「A class whose instances are single test cases」：explicit batch history and invalid boundaries |
| 14 | `RepositoryBoundaryTest` | `test_failed_seed_removes_new_empty_batch` | 覆盖「A class whose instances are single test cases」：failed seed removes new empty batch |
| 15 | `SeedTest` | `test_fork_keeps_only_completed_turn` | 覆盖「A class whose instances are single test cases」：fork keeps only completed turn |
| 16 | `SeedTest` | `test_fresh_seed_has_only_created_marker` | 覆盖「A class whose instances are single test cases」：fresh seed has only created marker |
| 17 | `SessionStorePathTest` | `test_child_store_shares_sequence_and_separate_path` | 覆盖「A class whose instances are single test cases」：child store shares sequence and separate path |

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
| 13 | `TaskGoalTest` | `test_goal_shapes` | 目标工具：建 / 查 / 改 / 暂停 / 恢复 / 达成 / 删，以及触发文案的语义。 |
| 14 | `TaskGoalTest` | `test_resume_creates_missing_goal_from_text` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：resume creates missing goal from text |
| 15 | `TaskGoalTest` | `test_resume_replaces_existing_goal_text` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：resume replaces existing goal text |
| 16 | `TodoListTest` | `test_add_remove_replace` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：add remove replace |
| 17 | `TodoListTest` | `test_check_uncheck_and_bounds` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：check uncheck and bounds |
| 18 | `TodoListTest` | `test_create_and_shape` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：create and shape |
| 19 | `TodoListTest` | `test_create_replaces_and_validates` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：create replaces and validates |
| 20 | `TodoListTest` | `test_no_list_unknown_and_query_close` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：no list unknown and query close |
| 21 | `TodoListTest` | `test_persistence_reload` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：persistence reload |
| 22 | `TodoListTest` | `test_persistence_tolerance_and_cid_defense` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：persistence tolerance and cid defense |
| 23 | `UserConfirmTest` | `test_confirm_backfill_is_not_a_tool_parameter` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：confirm backfill is not a tool parameter |
| 24 | `UserConfirmTest` | `test_envelope_still_works_without_tty` | 无 TTY 时不给 interactive，必须照常返回待确认信封（宿主 UI 负责交互）。 |
| 25 | `UserConfirmTest` | `test_interactive_flag_is_rejected` | interactive 不是公开工具参数，不得静默穿透到工具实现。 |
| 26 | `UserConfirmTest` | `test_pending_envelope` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：pending envelope |
| 27 | `UserConfirmTest` | `test_validations` | 覆盖「公共夹具：临时目录 + 独立 LiveState + 装配 app；经管道唯一入口调用」：validations |

## test_todo_context_prompt.py

共 21 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ContextLayoutTest` | `test_budget_is_used_for_pct` | 给了预算就按预算算百分比——这样上下文条才反映"还剩多少空间"。 |
| 2 | `ContextLayoutTest` | `test_budget_never_below_used` | 预算小于已用时按已用算——各段之和不得超过 100%。 |
| 3 | `ContextLayoutTest` | `test_chunks_plus_remainder` | 覆盖「上下文分段」：chunks plus remainder |
| 4 | `ContextLayoutTest` | `test_counts_present` | 覆盖「上下文分段」：counts present |
| 5 | `ContextLayoutTest` | `test_labels_are_chinese_names` | 覆盖「上下文分段」：labels are chinese names |
| 6 | `ContextLayoutTest` | `test_pct_sums_to_100` | 覆盖「上下文分段」：pct sums to 100 |
| 7 | `RuntimeTailTodoProgressTest` | `test_mode_note_contains_latest_progress` | 覆盖「运行态尾部每次求值都读最新 Todo 进度」：mode note contains latest progress |
| 8 | `RuntimeTailTodoProgressTest` | `test_no_todo_omits_todo_note` | 覆盖「运行态尾部每次求值都读最新 Todo 进度」：no todo omits todo note |
| 9 | `SystemPromptTest` | `test_blank_explicit_falls_back` | 覆盖「基础系统提示词」：blank explicit falls back |
| 10 | `SystemPromptTest` | `test_coding_and_tooling_disciplines_present` | 系统提示必须含「改前必读」/「大文件局部读」/「失败处理」等纪律条目。 |
| 11 | `SystemPromptTest` | `test_explicit_prompt_wins` | 覆盖「基础系统提示词」：explicit prompt wins |
| 12 | `SystemPromptTest` | `test_mode_section_differs` | 覆盖「基础系统提示词」：mode section differs |
| 13 | `SystemPromptTest` | `test_non_empty_by_default` | 系统提示不得为空——空提示让模型只凭 schema 猜纪律。 |
| 14 | `SystemPromptTest` | `test_preview_write_tools_line_tracks_registry` | 预览写类名单随 registry 增减，不手写固定串。 |
| 15 | `SystemPromptTest` | `test_tool_summary_propagates_registry_errors` | 覆盖「基础系统提示词」：tool summary propagates registry errors |
| 16 | `SystemPromptTest` | `test_tool_summary_shape` | 覆盖「基础系统提示词」：tool summary shape |
| 17 | `SystemPromptTest` | `test_unknown_mode_falls_back_to_auto` | 覆盖「基础系统提示词」：unknown mode falls back to auto |
| 18 | `TodoProgressTest` | `test_check_then_all_done` | 覆盖「清单进度字段」：check then all done |
| 19 | `TodoProgressTest` | `test_close_has_no_items` | 关闭清单只回 `{close: True}`——前端据此隐藏并清未读。 |
| 20 | `TodoProgressTest` | `test_create_reports_progress` | 覆盖「清单进度字段」：create reports progress |
| 21 | `TodoProgressTest` | `test_uncheck_revokes_all_done` | 覆盖「清单进度字段」：uncheck revokes all done |

## test_tool_arguments.py

共 4 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ToolArgumentContractTest` | `test_declared_arguments_still_work` | 覆盖「A class whose instances are single test cases」：declared arguments still work |
| 2 | `ToolArgumentContractTest` | `test_empty_schema_rejects_every_argument` | 覆盖「A class whose instances are single test cases」：empty schema rejects every argument |
| 3 | `ToolArgumentContractTest` | `test_session_create_has_one_name_parameter` | 覆盖「A class whose instances are single test cases」：session create has one name parameter |
| 4 | `ToolArgumentContractTest` | `test_unknown_aliases_are_rejected_before_execution` | 覆盖「A class whose instances are single test cases」：unknown aliases are rejected before execution |

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

## test_tool_resume.py

共 3 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ToolResumeTest` | `test_rejects_missing_or_mismatched_pending` | 覆盖「A class whose instances are single test cases」：rejects missing or mismatched pending |
| 2 | `ToolResumeTest` | `test_submit_failure_restores_pending` | 覆盖「A class whose instances are single test cases」：submit failure restores pending |
| 3 | `ToolResumeTest` | `test_submits_resume_and_clears_pending` | 覆盖「A class whose instances are single test cases」：submits resume and clears pending |

## test_tool_session_gate.py

共 1 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ToolSessionGateTest` | `test_execute_fills_session_gate` | 覆盖「经 ToolPort 执行时，工具所见 gate 与会话注册表一致」：execute fills session gate |

## test_top_level_services.py

共 2 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `AppServicesTest` | `test_missing_service_reports_assembly_hint` | 覆盖「A class whose instances are single test cases」：missing service reports assembly hint |
| 2 | `ConfigSchemaTest` | `test_unknown_section_is_empty` | 覆盖「A class whose instances are single test cases」：unknown section is empty |

## test_update.py

共 25 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ControllerTest` | `test_apply_without_state` | 覆盖「A class whose instances are single test cases」：apply without state |
| 2 | `ControllerTest` | `test_controller_disabled_and_guards` | 覆盖「A class whose instances are single test cases」：controller disabled and guards |
| 3 | `ControllerTest` | `test_controller_uses_root_version` | 覆盖「A class whose instances are single test cases」：controller uses root version |
| 4 | `ControllerTest` | `test_dev_checkout_disables_update` | 覆盖「A class whose instances are single test cases」：dev checkout disables update |
| 5 | `CoverageRootTest` | `test_apply_success_and_failure` | 覆盖「A class whose instances are single test cases」：apply success and failure |
| 6 | `CoverageRootTest` | `test_install_helpers` | 覆盖「A class whose instances are single test cases」：install helpers |
| 7 | `FileHashTest` | `test_sha256_file` | 覆盖「A class whose instances are single test cases」：sha256 file |
| 8 | `InstallLayoutTest` | `test_apply_staged_updates_root_and_keeps_backup` | 覆盖「A class whose instances are single test cases」：apply staged updates root and keeps backup |
| 9 | `InstallLayoutTest` | `test_locked_launcher_is_archived_then_replaced` | 覆盖「A class whose instances are single test cases」：locked launcher is archived then replaced |
| 10 | `InstallLayoutTest` | `test_merge_removes_deleted_key` | 覆盖「A class whose instances are single test cases」：merge removes deleted key |
| 11 | `InstallLayoutTest` | `test_nested_runtime_named_dir_is_backed_up` | 覆盖「A class whose instances are single test cases」：nested runtime named dir is backed up |
| 12 | `InstallLayoutTest` | `test_restore_backup` | 覆盖「A class whose instances are single test cases」：restore backup |
| 13 | `ManifestTest` | `test_bad_schema` | 覆盖「A class whose instances are single test cases」：bad schema |
| 14 | `ManifestTest` | `test_check_disabled_without_url` | 覆盖「A class whose instances are single test cases」：check disabled without url |
| 15 | `ManifestTest` | `test_parse_and_digest` | 覆盖「A class whose instances are single test cases」：parse and digest |
| 16 | `ManifestTest` | `test_stage_package_from_local_asset` | 覆盖「A class whose instances are single test cases」：stage package from local asset |
| 17 | `ManifestTest` | `test_zip_paths` | 覆盖「A class whose instances are single test cases」：zip paths |
| 18 | `PackagingBlacklistTest` | `test_blacklist_keeps_nested_plugin_data_but_drops_root_runtime` | 覆盖「A class whose instances are single test cases」：blacklist keeps nested plugin data but drops root runtime |
| 19 | `PluginConfigTest` | `test_local_secret_filter` | 覆盖「A class whose instances are single test cases」：local secret filter |
| 20 | `PluginConfigTest` | `test_recover_rolls_back_unhealthy_target` | 覆盖「A class whose instances are single test cases」：recover rolls back unhealthy target |
| 21 | `PluginConfigTest` | `test_sensitive_config_is_not_default_distribution` | 覆盖「A class whose instances are single test cases」：sensitive config is not default distribution |
| 22 | `PluginConfigTest` | `test_state_read_write` | 覆盖「A class whose instances are single test cases」：state read write |
| 23 | `PluginConfigTest` | `test_update_log_tail` | 覆盖「A class whose instances are single test cases」：update log tail |
| 24 | `VersionTest` | `test_invalid_version` | 覆盖「A class whose instances are single test cases」：invalid version |
| 25 | `VersionTest` | `test_semver_compare` | 覆盖「A class whose instances are single test cases」：semver compare |

## test_update_processes.py

共 2 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ProcessStopTest` | `test_removes_old_launcher_archives` | 覆盖「A class whose instances are single test cases」：removes old launcher archives |
| 2 | `ProcessStopTest` | `test_stops_matching_running_executable` | 覆盖「A class whose instances are single test cases」：stops matching running executable |

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
| 2 | `VersionStampTest` | `test_frontend_regex_matches_backend_directory_names` | 后端现造的版本目录名必须被前端正则命中，且取到的是时间那一段。 |
| 3 | `VersionStampTest` | `test_node_agrees_with_python` | 把 JS 那段真跑一遍，结果与 Python 侧一致（防止只改了注释没改代码）。 |
| 4 | `VersionStampTest` | `test_unparseable_ids_are_empty` | 覆盖「A class whose instances are single test cases」：unparseable ids are empty |

## test_visual_app_integration.py

共 1 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `VisualAppAssemblyTest` | `test_visual_plugin_is_loaded_with_kernel_hooks` | 覆盖「A class whose instances are single test cases」：visual plugin is loaded with kernel hooks |

## test_visual_context_integration.py

共 2 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ModelHookIntegrationTest` | `test_engine_keeps_plugin_request_id_in_pending` | 覆盖「A class whose instances are single test cases」：engine keeps plugin request id in pending |
| 2 | `ModelHookIntegrationTest` | `test_hook_output_enters_request_messages` | 覆盖「A class whose instances are single test cases」：hook output enters request messages |

## test_visual_operator.py

共 160 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ActToolTest` | `test_batch_find_and_click` | 覆盖「A class whose instances are single test cases」：batch find and click |
| 2 | `ActToolTest` | `test_batch_rejects_destructive_target` | 覆盖「A class whose instances are single test cases」：batch rejects destructive target |
| 3 | `ActToolTest` | `test_batch_resolves_prior_step_fields` | 覆盖「A class whose instances are single test cases」：batch resolves prior step fields |
| 4 | `ActToolTest` | `test_changed_expectation_uses_action_evidence` | 覆盖「A class whose instances are single test cases」：changed expectation uses action evidence |
| 5 | `ActToolTest` | `test_continue_requires_read_only_steps` | 覆盖「A class whose instances are single test cases」：continue requires read only steps |
| 6 | `AmbiguityNoteTest` | `test_hover_on_a_background_window_asks_for_activation` | 覆盖「同名窗口：回执必须说清选了谁、还有谁」：hover on a background window asks for activation |
| 7 | `AmbiguityNoteTest` | `test_matched_windows_are_spelled_out` | 覆盖「同名窗口：回执必须说清选了谁、还有谁」：matched windows are spelled out |
| 8 | `AmbiguityNoteTest` | `test_single_window_has_no_ambiguity_note` | 覆盖「同名窗口：回执必须说清选了谁、还有谁」：single window has no ambiguity note |
| 9 | `CanvasTest` | `test_bad_png_raises` | 覆盖「A class whose instances are single test cases」：bad png raises |
| 10 | `CanvasTest` | `test_blank_and_tiny_images` | 覆盖「A class whose instances are single test cases」：blank and tiny images |
| 11 | `CanvasTest` | `test_cursor_center_pixel_stays_visible` | 覆盖「A class whose instances are single test cases」：cursor center pixel stays visible |
| 12 | `CanvasTest` | `test_cursor_crosshair_is_wide_and_labelled` | 覆盖「A class whose instances are single test cases」：cursor crosshair is wide and labelled |
| 13 | `CanvasTest` | `test_cursor_font_screen_size_is_scale_consistent` | 覆盖「A class whose instances are single test cases」：cursor font screen size is scale consistent |
| 14 | `CanvasTest` | `test_cursor_mark_follows_screen_extent` | 覆盖「A class whose instances are single test cases」：cursor mark follows screen extent |
| 15 | `CanvasTest` | `test_grid_and_cursor_change_pixels` | 覆盖「A class whose instances are single test cases」：grid and cursor change pixels |
| 16 | `CanvasTest` | `test_offset_maps_screen_units_to_sent_pixels` | 覆盖「A class whose instances are single test cases」：offset maps screen units to sent pixels |
| 17 | `CanvasTest` | `test_scales_and_reports` | 覆盖「A class whose instances are single test cases」：scales and reports |
| 18 | `CanvasTest` | `test_tiny_area_hides_cursor_label` | 覆盖「A class whose instances are single test cases」：tiny area hides cursor label |
| 19 | `CaptureStoreTest` | `test_image_coordinates_map_with_origin_and_scale` | 覆盖「A class whose instances are single test cases」：image coordinates map with origin and scale |
| 20 | `CaptureStoreTest` | `test_out_of_image_and_wrong_session_are_rejected` | 覆盖「A class whose instances are single test cases」：out of image and wrong session are rejected |
| 21 | `CaptureStoreTest` | `test_ttl_and_capacity_evict_old_entries` | 覆盖「A class whose instances are single test cases」：ttl and capacity evict old entries |
| 22 | `ClickEvidenceTest` | `test_changed_is_not_measured_for_move` | 覆盖「点击回执要能自证：打中了什么、界面动没动」：changed is not measured for move |
| 23 | `ClickEvidenceTest` | `test_changed_is_zero_when_nothing_moves` | 覆盖「点击回执要能自证：打中了什么、界面动没动」：changed is zero when nothing moves |
| 24 | `ClickEvidenceTest` | `test_hit_is_omitted_without_a_hit_port` | 覆盖「点击回执要能自证：打中了什么、界面动没动」：hit is omitted without a hit port |
| 25 | `ClickEvidenceTest` | `test_hit_report_is_included` | 覆盖「点击回执要能自证：打中了什么、界面动没动」：hit report is included |
| 26 | `ClickEvidenceTest` | `test_local_still_is_resampled_once` | 覆盖「点击回执要能自证：打中了什么、界面动没动」：local still is resampled once |
| 27 | `ClickEvidenceTest` | `test_navigation_is_reported_when_local_pixels_do_not_move` | 点卡片跳详情页：落点 200×200 没变，但顶层窗口换了，不能读成没点中。 |
| 28 | `ClickEvidenceTest` | `test_shot_follows_the_landed_window_not_the_title` | 点击落在播放器窗口时，回图必须拍播放器，而不是标题命中的详情页。 |
| 29 | `ConfigTest` | `test_bad_values_fall_back` | 覆盖「A class whose instances are single test cases」：bad values fall back |
| 30 | `ConfigTest` | `test_missing_file_uses_defaults` | 覆盖「A class whose instances are single test cases」：missing file uses defaults |
| 31 | `ConfigTest` | `test_values_are_read_and_clamped` | 覆盖「A class whose instances are single test cases」：values are read and clamped |
| 32 | `CoordsTest` | `test_geometry_reports_ratio` | 覆盖「A class whose instances are single test cases」：geometry reports ratio |
| 33 | `CoordsTest` | `test_rect_bounds_and_intersection` | 覆盖「A class whose instances are single test cases」：rect bounds and intersection |
| 34 | `CoordsTest` | `test_rect_rejects_empty` | 覆盖「A class whose instances are single test cases」：rect rejects empty |
| 35 | `DiffTest` | `test_different_image_changes` | 覆盖「A class whose instances are single test cases」：different image changes |
| 36 | `DiffTest` | `test_probe_region_follows_the_point_and_clips` | 覆盖「A class whose instances are single test cases」：probe region follows the point and clips |
| 37 | `DiffTest` | `test_same_image_has_no_change` | 覆盖「A class whose instances are single test cases」：same image has no change |
| 38 | `EyeToolTest` | `test_annotate_both_returns_annotated_then_raw` | 覆盖「A class whose instances are single test cases」：annotate both returns annotated then raw |
| 39 | `EyeToolTest` | `test_annotate_raw_skips_grid_and_overlay` | 覆盖「A class whose instances are single test cases」：annotate raw skips grid and overlay |
| 40 | `EyeToolTest` | `test_annotate_unknown_value_is_rejected` | 覆盖「A class whose instances are single test cases」：annotate unknown value is rejected |
| 41 | `EyeToolTest` | `test_capture_id_and_image_mapping_are_returned` | 覆盖「A class whose instances are single test cases」：capture id and image mapping are returned |
| 42 | `EyeToolTest` | `test_description_names_the_guide_lines` | 覆盖「A class whose instances are single test cases」：description names the guide lines |
| 43 | `EyeToolTest` | `test_grid_switch_is_reported` | 覆盖「A class whose instances are single test cases」：grid switch is reported |
| 44 | `EyeToolTest` | `test_note_reports_mixed_scale` | 覆盖「A class whose instances are single test cases」：note reports mixed scale |
| 45 | `EyeToolTest` | `test_notes_report_shrinking_and_blank` | 覆盖「A class whose instances are single test cases」：notes report shrinking and blank |
| 46 | `EyeToolTest` | `test_oversized_region_rejected` | 覆盖「A class whose instances are single test cases」：oversized region rejected |
| 47 | `EyeToolTest` | `test_region_is_clipped_to_screen` | 覆盖「A class whose instances are single test cases」：region is clipped to screen |
| 48 | `EyeToolTest` | `test_region_needs_four_numbers` | 覆盖「A class whose instances are single test cases」：region needs four numbers |
| 49 | `EyeToolTest` | `test_returns_image_attachment` | 覆盖「A class whose instances are single test cases」：returns image attachment |
| 50 | `EyeToolTest` | `test_unknown_argument_rejected` | 覆盖「A class whose instances are single test cases」：unknown argument rejected |
| 51 | `HoverCaptureTest` | `test_grid_step_can_be_tightened_for_small_targets` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：grid step can be tightened for small targets |
| 52 | `HoverCaptureTest` | `test_hover_is_blocked_in_plan_mode` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover is blocked in plan mode |
| 53 | `HoverCaptureTest` | `test_hover_moves_cursor_before_capture` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover moves cursor before capture |
| 54 | `HoverCaptureTest` | `test_hover_outside_the_screen_is_rejected` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover outside the screen is rejected |
| 55 | `HoverCaptureTest` | `test_hover_path_is_walked_before_the_endpoint` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover path is walked before the endpoint |
| 56 | `HoverCaptureTest` | `test_hover_path_length_is_limited` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover path length is limited |
| 57 | `HoverCaptureTest` | `test_hover_path_requires_hover` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover path requires hover |
| 58 | `HoverCaptureTest` | `test_hover_requires_two_integers` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover requires two integers |
| 59 | `HoverCaptureTest` | `test_hover_settle_is_reported_and_clamped` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover settle is reported and clamped |
| 60 | `HoverCaptureTest` | `test_hover_wiggle_moves_around_and_returns` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover wiggle moves around and returns |
| 61 | `HoverCaptureTest` | `test_hover_wiggle_recovers_if_target_warps_cursor` | 覆盖「悬停取图：移光标与截图必须在同一次调用内完成」：hover wiggle recovers if target warps cursor |
| 62 | `IsolationTest` | `test_input_guard_is_reentrant_in_one_thread` | 覆盖「A class whose instances are single test cases」：input guard is reentrant in one thread |
| 63 | `IsolationTest` | `test_input_lock_times_out_for_another_thread` | 覆盖「A class whose instances are single test cases」：input lock times out for another thread |
| 64 | `IsolationTest` | `test_unavailable_backend_reports` | 覆盖「A class whose instances are single test cases」：unavailable backend reports |
| 65 | `KeyboardToolTest` | `test_bad_parameters` | 覆盖「A class whose instances are single test cases」：bad parameters |
| 66 | `KeyboardToolTest` | `test_plan_gate_blocks` | 覆盖「A class whose instances are single test cases」：plan gate blocks |
| 67 | `KeyboardToolTest` | `test_type_key_and_hotkey` | 覆盖「A class whose instances are single test cases」：type key and hotkey |
| 68 | `KeysTest` | `test_aliases_normalize` | 覆盖「A class whose instances are single test cases」：aliases normalize |
| 69 | `KeysTest` | `test_canonical_set_is_coverable` | 覆盖「A class whose instances are single test cases」：canonical set is coverable |
| 70 | `KeysTest` | `test_hotkey_forms` | 覆盖「A class whose instances are single test cases」：hotkey forms |
| 71 | `KeysTest` | `test_hotkey_rejects_bad_shapes` | 覆盖「A class whose instances are single test cases」：hotkey rejects bad shapes |
| 72 | `KeysTest` | `test_unknown_key_names_hint` | 覆盖「A class whose instances are single test cases」：unknown key names hint |
| 73 | `LocatorToolsTest` | `test_click_region_clicks_the_rectangle_center` | 覆盖「A class whose instances are single test cases」：click region clicks the rectangle center |
| 74 | `LocatorToolsTest` | `test_click_region_maps_image_rect_to_screen` | 覆盖「A class whose instances are single test cases」：click region maps image rect to screen |
| 75 | `LocatorToolsTest` | `test_click_text_uses_clickable_point` | 覆盖「A class whose instances are single test cases」：click text uses clickable point |
| 76 | `LocatorToolsTest` | `test_find_empty_result_tells_model_not_to_repeat` | 覆盖「A class whose instances are single test cases」：find empty result tells model not to repeat |
| 77 | `LocatorToolsTest` | `test_find_returns_uia_matches` | 覆盖「A class whose instances are single test cases」：find returns uia matches |
| 78 | `LocatorToolsTest` | `test_find_without_locator_reports_unavailable` | 覆盖「A class whose instances are single test cases」：find without locator reports unavailable |
| 79 | `LocatorToolsTest` | `test_keyboard_type_reports_focused_control` | 覆盖「A class whose instances are single test cases」：keyboard type reports focused control |
| 80 | `LocatorToolsTest` | `test_type_into_accepts_a_visual_rect_without_uia` | 覆盖「A class whose instances are single test cases」：type into accepts a visual rect without uia |
| 81 | `LocatorToolsTest` | `test_type_into_clears_types_and_submits` | 覆盖「A class whose instances are single test cases」：type into clears types and submits |
| 82 | `LocatorToolsTest` | `test_uia_locator_parses_powershell_json` | 覆盖「A class whose instances are single test cases」：uia locator parses powershell json |
| 83 | `MacOSTableTest` | `test_keycodes_cover_canonical_names` | 覆盖「不启动系统库，只校验键码表与结构体拼装」：keycodes cover canonical names |
| 84 | `MacOSTableTest` | `test_point_and_unknown_key` | 覆盖「不启动系统库，只校验键码表与结构体拼装」：point and unknown key |
| 85 | `MacOSTableTest` | `test_scroll_delta_matches_contract` | 覆盖「不启动系统库，只校验键码表与结构体拼装」：scroll delta matches contract |
| 86 | `MouseToolTest` | `test_drag_scroll_and_cursor` | 覆盖「A class whose instances are single test cases」：drag scroll and cursor |
| 87 | `MouseToolTest` | `test_image_coordinates_are_converted_by_the_tool` | 覆盖「A class whose instances are single test cases」：image coordinates are converted by the tool |
| 88 | `MouseToolTest` | `test_image_coordinates_need_a_valid_capture` | 覆盖「A class whose instances are single test cases」：image coordinates need a valid capture |
| 89 | `MouseToolTest` | `test_move_and_click` | 覆盖「A class whose instances are single test cases」：move and click |
| 90 | `MouseToolTest` | `test_out_of_screen_point_rejected` | 覆盖「A class whose instances are single test cases」：out of screen point rejected |
| 91 | `MouseToolTest` | `test_parameter_matrix` | 覆盖「A class whose instances are single test cases」：parameter matrix |
| 92 | `MouseToolTest` | `test_plan_gate` | 覆盖「A class whose instances are single test cases」：plan gate |
| 93 | `PipelineTest` | `test_destructive_and_read_only_checks` | 覆盖「A class whose instances are single test cases」：destructive and read only checks |
| 94 | `PipelineTest` | `test_run_enforces_total_timeout_after_a_step` | 覆盖「A class whose instances are single test cases」：run enforces total timeout after a step |
| 95 | `PipelineTest` | `test_run_honours_expect_failure` | 覆盖「A class whose instances are single test cases」：run honours expect failure |
| 96 | `PipelineTest` | `test_run_stops_on_failure_and_logs_steps` | 覆盖「A class whose instances are single test cases」：run stops on failure and logs steps |
| 97 | `PipelineTest` | `test_scalar_app_and_step_limits` | 覆盖「A class whose instances are single test cases」：scalar app and step limits |
| 98 | `PipelineTest` | `test_window_string_and_wait_ms_are_accepted` | 覆盖「A class whose instances are single test cases」：window string and wait ms are accepted |
| 99 | `PluginTest` | `test_build_tools_honours_switches` | 覆盖「A class whose instances are single test cases」：build tools honours switches |
| 100 | `PluginTest` | `test_register_returns_disposers` | 覆盖「A class whose instances are single test cases」：register returns disposers |
| 101 | `ScaleHintTest` | `test_shrunk_image_reports_the_multiplier` | 覆盖「缩图必须给出换算示例，避免每次心算比例」：shrunk image reports the multiplier |
| 102 | `ShotTest` | `test_keyboard_shot_returns_image` | 覆盖「动作自带回图：点完/打完就在同一次调用里返回图片」：keyboard shot returns image |
| 103 | `ShotTest` | `test_mouse_shot_returns_image_and_receipt` | 覆盖「动作自带回图：点完/打完就在同一次调用里返回图片」：mouse shot returns image and receipt |
| 104 | `ShotTest` | `test_mouse_without_shot_returns_plain_dict` | 覆盖「动作自带回图：点完/打完就在同一次调用里返回图片」：mouse without shot returns plain dict |
| 105 | `ShotTest` | `test_shot_region_is_clipped` | 覆盖「动作自带回图：点完/打完就在同一次调用里返回图片」：shot region is clipped |
| 106 | `ShotTest` | `test_shot_region_shape_is_validated` | 覆盖「动作自带回图：点完/打完就在同一次调用里返回图片」：shot region shape is validated |
| 107 | `ShotTest` | `test_shot_rejected_for_cursor_query` | 覆盖「动作自带回图：点完/打完就在同一次调用里返回图片」：shot rejected for cursor query |
| 108 | `WaitToolTest` | `test_bad_parameters` | 覆盖「A class whose instances are single test cases」：bad parameters |
| 109 | `WaitToolTest` | `test_change_on_a_minimized_window_is_rejected` | 覆盖「A class whose instances are single test cases」：change on a minimized window is rejected |
| 110 | `WaitToolTest` | `test_change_satisfies_immediately` | 覆盖「A class whose instances are single test cases」：change satisfies immediately |
| 111 | `WaitToolTest` | `test_change_times_out_without_raising` | 覆盖「A class whose instances are single test cases」：change times out without raising |
| 112 | `WaitToolTest` | `test_title_change_satisfies_change_without_pixel_motion` | 覆盖「A class whose instances are single test cases」：title change satisfies change without pixel motion |
| 113 | `WaitToolTest` | `test_unknown_argument_rejected` | 覆盖「A class whose instances are single test cases」：unknown argument rejected |
| 114 | `WaitToolTest` | `test_window_appears` | 覆盖「A class whose instances are single test cases」：window appears |
| 115 | `WaitToolTest` | `test_window_condition_needs_a_title` | 覆盖「A class whose instances are single test cases」：window condition needs a title |
| 116 | `WaitToolTest` | `test_window_disappeared_before_waiting_is_flagged_as_already` | 覆盖「A class whose instances are single test cases」：window disappeared before waiting is flagged as already |
| 117 | `WaitToolTest` | `test_window_disappears_times_out` | 覆盖「A class whose instances are single test cases」：window disappears times out |
| 118 | `WaitToolTest` | `test_window_that_already_exists_is_flagged_as_already` | 覆盖「A class whose instances are single test cases」：window that already exists is flagged as already |
| 119 | `Win32TableTest` | `test_activate_uses_foreground_path` | 覆盖「A class whose instances are single test cases」：activate uses foreground path |
| 120 | `Win32TableTest` | `test_crop_bgra_uses_top_down_rows` | 覆盖「A class whose instances are single test cases」：crop bgra uses top down rows |
| 121 | `Win32TableTest` | `test_find_prefers_foreground_then_z_order` | 同名窗口：前台优先，其次 Z 序，最后才是面积。 |
| 122 | `Win32TableTest` | `test_find_without_foreground_falls_back_to_z_order` | 覆盖「A class whose instances are single test cases」：find without foreground falls back to z order |
| 123 | `Win32TableTest` | `test_hit_probe_reports_class_and_root_title` | 覆盖「A class whose instances are single test cases」：hit probe reports class and root title |
| 124 | `Win32TableTest` | `test_hit_probe_returns_empty_when_nothing_is_there` | 覆盖「A class whose instances are single test cases」：hit probe returns empty when nothing is there |
| 125 | `Win32TableTest` | `test_key_table_covers_canonical_names` | 覆盖「A class whose instances are single test cases」：key table covers canonical names |
| 126 | `Win32TableTest` | `test_minimized_capture_restores_without_stealing_focus` | 覆盖「A class whose instances are single test cases」：minimized capture restores without stealing focus |
| 127 | `Win32TableTest` | `test_scroll_delta_matches_contract` | 覆盖「A class whose instances are single test cases」：scroll delta matches contract |
| 128 | `Win32TableTest` | `test_uniform_detection_catches_black_frames` | 覆盖「A class whose instances are single test cases」：uniform detection catches black frames |
| 129 | `Win32TableTest` | `test_utf16_units_and_unknown_key` | 覆盖「A class whose instances are single test cases」：utf16 units and unknown key |
| 130 | `Win32TableTest` | `test_visible_window_activates_only_when_asked` | 覆盖「A class whose instances are single test cases」：visible window activates only when asked |
| 131 | `Win32TableTest` | `test_visible_window_is_left_alone` | 覆盖「A class whose instances are single test cases」：visible window is left alone |
| 132 | `Win32TableTest` | `test_window_capture_does_not_touch_screen_grab` | 覆盖「A class whose instances are single test cases」：window capture does not touch screen grab |
| 133 | `WindowActivationTest` | `test_activation_reports_matched_when_titles_collide` | 覆盖「手部动作可以带 window / hwnd：先置前，再落点」：activation reports matched when titles collide |
| 134 | `WindowActivationTest` | `test_cursor_query_does_not_activate` | 覆盖「手部动作可以带 window / hwnd：先置前，再落点」：cursor query does not activate |
| 135 | `WindowActivationTest` | `test_failed_activation_blocks_input` | 覆盖「手部动作可以带 window / hwnd：先置前，再落点」：failed activation blocks input |
| 136 | `WindowActivationTest` | `test_keyboard_activates_before_typing` | 覆盖「手部动作可以带 window / hwnd：先置前，再落点」：keyboard activates before typing |
| 137 | `WindowActivationTest` | `test_mouse_activates_before_click` | 覆盖「手部动作可以带 window / hwnd：先置前，再落点」：mouse activates before click |
| 138 | `WindowAppOpenTest` | `test_app_launches_and_returns_hwnd` | 覆盖「A class whose instances are single test cases」：app launches and returns hwnd |
| 139 | `WindowAppOpenTest` | `test_app_name_resolves_start_menu_shortcut` | 覆盖「A class whose instances are single test cases」：app name resolves start menu shortcut |
| 140 | `WindowAppOpenTest` | `test_open_binds_a_new_window_instead_of_stale_title_match` | 覆盖「A class whose instances are single test cases」：open binds a new window instead of stale title match |
| 141 | `WindowAppOpenTest` | `test_open_url_uses_default_handler` | 覆盖「A class whose instances are single test cases」：open url uses default handler |
| 142 | `WindowAppOpenTest` | `test_title_matching_ignores_invisible_format_chars` | 覆盖「A class whose instances are single test cases」：title matching ignores invisible format chars |
| 143 | `WindowAppOpenTest` | `test_window_list_and_activate` | 覆盖「A class whose instances are single test cases」：window list and activate |
| 144 | `WindowAppOpenTest` | `test_window_waits_until_visible` | 覆盖「A class whose instances are single test cases」：window waits until visible |
| 145 | `WindowCaptureTest` | `test_activate_failure_is_reported` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：activate failure is reported |
| 146 | `WindowCaptureTest` | `test_activate_rejected_for_plain_screen` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：activate rejected for plain screen |
| 147 | `WindowCaptureTest` | `test_activate_requested_reports_success` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：activate requested reports success |
| 148 | `WindowCaptureTest` | `test_hwnd_skips_title_lookup` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：hwnd skips title lookup |
| 149 | `WindowCaptureTest` | `test_missing_window_port_reports_clearly` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：missing window port reports clearly |
| 150 | `WindowCaptureTest` | `test_no_matching_window` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：no matching window |
| 151 | `WindowCaptureTest` | `test_region_is_passed_through` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：region is passed through |
| 152 | `WindowCaptureTest` | `test_restore_only_does_not_steal_foreground` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：restore only does not steal foreground |
| 153 | `WindowCaptureTest` | `test_screen_fallback_is_reported` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：screen fallback is reported |
| 154 | `WindowCaptureTest` | `test_window_and_hwnd_are_exclusive` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：window and hwnd are exclusive |
| 155 | `WindowCaptureTest` | `test_window_content_has_no_fallback_note` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：window content has no fallback note |
| 156 | `WindowCaptureTest` | `test_window_title_routes_to_window_port` | 覆盖「按窗口取图：走 windows 端口，而不是屏幕端口」：window title routes to window port |
| 157 | `WindowHoverTest` | `test_cursor_layer_different_from_capture_window_is_reported` | 播放器画面是独立顶层窗口：取图窗口与光标那层不同时必须点明。 |
| 158 | `WindowHoverTest` | `test_hover_runs_after_activation_and_before_capture` | 覆盖「窗口悬停：先恢复/置前，再移光标，最后取图」：hover runs after activation and before capture |
| 159 | `WindowHoverTest` | `test_hover_without_window_captures_the_cursor_layer` | 没给窗口时按光标落点取那一层，避免整屏缩放后看不清控件文字。 |
| 160 | `WindowHoverTest` | `test_plain_window_capture_does_not_pass_a_prepare_hook` | 覆盖「窗口悬停：先恢复/置前，再移光标，最后取图」：plain window capture does not pass a prepare hook |

## test_visual_operator_2.py

共 21 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `VisionRuntimeTest` | `test_actions_use_fake_backend_and_wake_on_change` | 覆盖「A class whose instances are single test cases」：actions use fake backend and wake on change |
| 2 | `VisionRuntimeTest` | `test_click_sequence_uses_same_point_conversion` | 覆盖「A class whose instances are single test cases」：click sequence uses same point conversion |
| 3 | `VisionRuntimeTest` | `test_click_tools_and_sequence_contract` | 覆盖「A class whose instances are single test cases」：click tools and sequence contract |
| 4 | `VisionRuntimeTest` | `test_confirm_route_resumes_pending_call` | 覆盖「A class whose instances are single test cases」：confirm route resumes pending call |
| 5 | `VisionRuntimeTest` | `test_consent_owner_and_observation` | 覆盖「A class whose instances are single test cases」：consent owner and observation |
| 6 | `VisionRuntimeTest` | `test_context_hook_appends_two_images` | 覆盖「A class whose instances are single test cases」：context hook appends two images |
| 7 | `VisionRuntimeTest` | `test_context_hook_publishes_exact_model_frame` | 覆盖「A class whose instances are single test cases」：context hook publishes exact model frame |
| 8 | `VisionRuntimeTest` | `test_focus_clips_at_screen_edge` | 覆盖「A class whose instances are single test cases」：focus clips at screen edge |
| 9 | `VisionRuntimeTest` | `test_focus_forces_fresh_center_frame` | 覆盖「A class whose instances are single test cases」：focus forces fresh center frame |
| 10 | `VisionRuntimeTest` | `test_input_monitor_fires_once_in_worker` | 覆盖「A class whose instances are single test cases」：input monitor fires once in worker |
| 11 | `VisionRuntimeTest` | `test_model_point_matches_user_example` | 覆盖「A class whose instances are single test cases」：model point matches user example |
| 12 | `VisionRuntimeTest` | `test_model_point_uses_both_image_sizes` | 覆盖「A class whose instances are single test cases」：model point uses both image sizes |
| 13 | `VisionRuntimeTest` | `test_move_focus_uses_focus_origin` | 覆盖「A class whose instances are single test cases」：move focus uses focus origin |
| 14 | `VisionRuntimeTest` | `test_native_full_image_is_screen_identity` | 覆盖「A class whose instances are single test cases」：native full image is screen identity |
| 15 | `VisionRuntimeTest` | `test_reject_does_not_open` | 覆盖「A class whose instances are single test cases」：reject does not open |
| 16 | `VisionRuntimeTest` | `test_single_click_count_and_interval` | 覆盖「A class whose instances are single test cases」：single click count and interval |
| 17 | `VisionRuntimeTest` | `test_tools_require_consent_and_close_cleanly` | 覆盖「A class whose instances are single test cases」：tools require consent and close cleanly |
| 18 | `VisionRuntimeTest` | `test_trajectory_duration_and_same_point_skip` | 覆盖「A class whose instances are single test cases」：trajectory duration and same point skip |
| 19 | `VisionRuntimeTest` | `test_user_takeover_closes_eyes_and_blocks_actions` | 覆盖「A class whose instances are single test cases」：user takeover closes eyes and blocks actions |
| 20 | `VisionRuntimeTest` | `test_visual_skill_is_registered` | 覆盖「A class whose instances are single test cases」：visual skill is registered |
| 21 | `VisionRuntimeTest` | `test_zero_move_is_not_reported_as_moved` | 覆盖「A class whose instances are single test cases」：zero move is not reported as moved |

## test_wake_scheduler.py

共 16 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `QueueDedupeTest` | `test_dedupe_key_does_not_create_second_item` | 覆盖「A class whose instances are single test cases」：dedupe key does not create second item |
| 2 | `RealMeshDispatcherTest` | `test_busy_target_is_queued_with_dedupe_key` | 覆盖「A class whose instances are single test cases」：busy target is queued with dedupe key |
| 3 | `RealMeshDispatcherTest` | `test_idle_dispatch_goes_through_mesh_activator` | 覆盖「A class whose instances are single test cases」：idle dispatch goes through mesh activator |
| 4 | `RealMeshDispatcherTest` | `test_process_lock_allows_one_scheduler` | 覆盖「A class whose instances are single test cases」：process lock allows one scheduler |
| 5 | `RealMeshDispatcherTest` | `test_terminal_jobs_are_pruned` | 覆盖「A class whose instances are single test cases」：terminal jobs are pruned |
| 6 | `WakeSchedulerTest` | `test_cancel_prevents_delivery` | 覆盖「A class whose instances are single test cases」：cancel prevents delivery |
| 7 | `WakeSchedulerTest` | `test_invalid_schedules_are_rejected` | 覆盖「A class whose instances are single test cases」：invalid schedules are rejected |
| 8 | `WakeSchedulerTest` | `test_list_filters_by_target_and_owner` | 覆盖「A class whose instances are single test cases」：list filters by target and owner |
| 9 | `WakeSchedulerTest` | `test_parse_due_at_normalizes_z` | 覆盖「A class whose instances are single test cases」：parse due at normalizes z |
| 10 | `WakeSchedulerTest` | `test_restart_does_not_repeat_delivered_job` | 覆盖「A class whose instances are single test cases」：restart does not repeat delivered job |
| 11 | `WakeSchedulerTest` | `test_restart_recovers_pending_job` | 覆盖「A class whose instances are single test cases」：restart recovers pending job |
| 12 | `WakeSchedulerTest` | `test_sleep_registers_and_delivers_once` | 覆盖「A class whose instances are single test cases」：sleep registers and delivers once |
| 13 | `WakeSchedulerTest` | `test_target_must_exist_for_other_session` | 覆盖「A class whose instances are single test cases」：target must exist for other session |
| 14 | `WakeToolTest` | `test_app_wake_state_helpers` | 覆盖「A class whose instances are single test cases」：app wake state helpers |
| 15 | `WakeToolTest` | `test_schedule_rejects_past` | 覆盖「A class whose instances are single test cases」：schedule rejects past |
| 16 | `WakeToolTest` | `test_sleep_list_cancel` | 覆盖「A class whose instances are single test cases」：sleep list cancel |

## test_web_auth.py

共 26 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CreateServerAuthTest` | `test_required_mode_has_no_embedded_bypass` | 覆盖「A class whose instances are single test cases」：required mode has no embedded bypass |
| 2 | `CredentialTest` | `test_store_and_verify` | 覆盖「A class whose instances are single test cases」：store and verify |
| 3 | `DesktopBootstrapTest` | `test_one_time_loopback_bootstrap_session` | 覆盖「A class whose instances are single test cases」：one time loopback bootstrap session |
| 4 | `GuiAutoProvisionTest` | `test_gui_startup_creates_initial_password` | 覆盖「A class whose instances are single test cases」：gui startup creates initial password |
| 5 | `PasswordTest` | `test_hash_roundtrip_and_wrong_password` | 覆盖「A class whose instances are single test cases」：hash roundtrip and wrong password |
| 6 | `PolicyTest` | `test_public_and_scope` | 覆盖「A class whose instances are single test cases」：public and scope |
| 7 | `ProviderExtensionTest` | `test_provider_module_can_supply_principal` | 覆盖「A class whose instances are single test cases」：provider module can supply principal |
| 8 | `RequestBoundaryTest` | `test_trusted_proxy_and_host` | 覆盖「A class whose instances are single test cases」：trusted proxy and host |
| 9 | `RuntimeTest` | `test_config_reads_auth_section` | 覆盖「A class whose instances are single test cases」：config reads auth section |
| 10 | `RuntimeTest` | `test_login_issues_session_and_csrf` | 覆盖「A class whose instances are single test cases」：login issues session and csrf |
| 11 | `RuntimeTest` | `test_public_without_password_is_blocked` | 覆盖「A class whose instances are single test cases」：public without password is blocked |
| 12 | `RuntimeTest` | `test_unusable_auth_dir_falls_back` | 覆盖「A class whose instances are single test cases」：unusable auth dir falls back |
| 13 | `SchemaDefaultTest` | `test_schema_uses_copy_not_alias` | 覆盖「A class whose instances are single test cases」：schema uses copy not alias |
| 14 | `SessionTest` | `test_create_validate_and_revoke` | 覆盖「A class whose instances are single test cases」：create validate and revoke |
| 15 | `SessionTest` | `test_expiry` | 覆盖「A class whose instances are single test cases」：expiry |
| 16 | `StreamSessionTest` | `test_stream_drops_revoked_session` | 覆盖「A class whose instances are single test cases」：stream drops revoked session |
| 17 | `TlsGuardTest` | `test_tls_wraps_socket_and_reports_failure` | 覆盖「A class whose instances are single test cases」：tls wraps socket and reports failure |
| 18 | `TokenCliTest` | `test_lock_failure_is_reported_without_traceback` | 覆盖「A class whose instances are single test cases」：lock failure is reported without traceback |
| 19 | `TokenTest` | `test_cross_process_issue_keeps_all_tokens` | 覆盖「A class whose instances are single test cases」：cross process issue keeps all tokens |
| 20 | `TokenTest` | `test_duplicate_token_name_is_rejected` | 覆盖「A class whose instances are single test cases」：duplicate token name is rejected |
| 21 | `TokenTest` | `test_issue_does_not_resurrect_revoked` | 覆盖「A class whose instances are single test cases」：issue does not resurrect revoked |
| 22 | `TokenTest` | `test_issue_verify_and_revoke` | 覆盖「A class whose instances are single test cases」：issue verify and revoke |
| 23 | `TokenTest` | `test_threaded_issue_keeps_all_tokens` | 覆盖「A class whose instances are single test cases」：threaded issue keeps all tokens |
| 24 | `WebAuthHttpTest` | `test_guard_login_csrf_and_logout` | 覆盖「A class whose instances are single test cases」：guard login csrf and logout |
| 25 | `WebAuthHttpTest` | `test_healthz_reports_fallback_target` | 覆盖「A class whose instances are single test cases」：healthz reports fallback target |
| 26 | `WebAuthHttpTest` | `test_login_page_has_window_close` | 覆盖「A class whose instances are single test cases」：login page has window close |

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

共 52 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `ConcurrencyTest` | `test_concurrent_send_queues` | 覆盖「同会话并发发送进入待发送队列；停止请求可下发」：concurrent send queues |
| 2 | `ConcurrencyTest` | `test_stop_cancels_a_running_turn` | 停止是真取消：经 SessionRunner 的停止检查，让内核在检查点停下。 |
| 3 | `ConcurrencyTest` | `test_stop_endpoint_shape` | 覆盖「同会话并发发送进入待发送队列；停止请求可下发」：stop endpoint shape |
| 4 | `DateGroupTest` | `test_groups_by_natural_day` | 覆盖「会话日期分组」：groups by natural day |
| 5 | `DateGroupTest` | `test_older_is_grouped_by_date` | 覆盖「会话日期分组」：older is grouped by date |
| 6 | `DirBrowseDriveRootTest` | `test_drive_root_parent_is_drives_layer` | 覆盖「可见根是盘根时（默认情形），相对路径不能被钉死在盘根」：drive root parent is drives layer |
| 7 | `DirBrowseDriveRootTest` | `test_relative_path_prefers_concrete_workspace_root` | 覆盖「可见根是盘根时（默认情形），相对路径不能被钉死在盘根」：relative path prefers concrete workspace root |
| 8 | `DirBrowseQueryTest` | `test_dir_browse_single_char_path_not_truncated` | `_query()` 必须返回整串：路由若用 `[0]` 取首字符，值会被截断。 |
| 9 | `DirBrowseQueryTest` | `test_ui_state_roundtrip` | 覆盖「路径查询串按整串解析，不按首字符」：ui state roundtrip |
| 10 | `EndpointTest` | `test_health_endpoint` | 覆盖「端点清单可达性与显著错误码」：health endpoint |
| 11 | `EndpointTest` | `test_media_endpoint_guards_root` | 覆盖「端点清单可达性与显著错误码」：media endpoint guards root |
| 12 | `EndpointTest` | `test_media_missing_file_404` | 覆盖「端点清单可达性与显著错误码」：media missing file 404 |
| 13 | `EndpointTest` | `test_pages_and_assets_served` | 覆盖「端点清单可达性与显著错误码」：pages and assets served |
| 14 | `EndpointTest` | `test_send_rejects_bad_input` | 覆盖「端点清单可达性与显著错误码」：send rejects bad input |
| 15 | `EndpointTest` | `test_setup_route_is_removed` | 覆盖「端点清单可达性与显著错误码」：setup route is removed |
| 16 | `EndpointTest` | `test_unknown_path_404` | 覆盖「端点清单可达性与显著错误码」：unknown path 404 |
| 17 | `FileViewerContractTest` | `test_absolute_path_inside_root_is_accepted` | 工具参数常给绝对路径；落在 fs_root 内必须能直接打开。 |
| 18 | `FileViewerContractTest` | `test_absolute_path_outside_root_is_forbidden` | 覆盖「文件读取端点的路径解析与越界边界」：absolute path outside root is forbidden |
| 19 | `FileViewerContractTest` | `test_binary_is_reported_not_dumped` | 覆盖「文件读取端点的路径解析与越界边界」：binary is reported not dumped |
| 20 | `FileViewerContractTest` | `test_list_absolute_path_inside_root` | 覆盖「文件读取端点的路径解析与越界边界」：list absolute path inside root |
| 21 | `FileViewerContractTest` | `test_list_outside_root_is_forbidden` | 覆盖「文件读取端点的路径解析与越界边界」：list outside root is forbidden |
| 22 | `FileViewerContractTest` | `test_list_returns_entries_with_rel_and_type` | 覆盖「文件读取端点的路径解析与越界边界」：list returns entries with rel and type |
| 23 | `FileViewerContractTest` | `test_max_chars_zero_returns_full_file` | 文件查看器显式传 0：不截断；默认调用仍保留 400000 字符保护。 |
| 24 | `FileViewerContractTest` | `test_missing_file_inside_root_is_404_not_403` | 不存在的文件与越界必须分开报告：预览期未落盘的文件是 404，不是越权。 |
| 25 | `FileViewerContractTest` | `test_relative_path_reads_text` | 覆盖「文件读取端点的路径解析与越界边界」：relative path reads text |
| 26 | `FileViewerContractTest` | `test_traversal_cannot_escape_roots` | 穿越语义：不允许逃出可见根（不是"禁止 `..`"）。 |
| 27 | `MultiRootFileViewerTest` | `test_absolute_path_in_first_root` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：absolute path in first root |
| 28 | `MultiRootFileViewerTest` | `test_absolute_path_in_second_root` | 第二个根同样可达——单根实现会把它判成越界。 |
| 29 | `MultiRootFileViewerTest` | `test_list_reports_rel_against_matched_root` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：list reports rel against matched root |
| 30 | `MultiRootFileViewerTest` | `test_missing_in_a_root_is_404_not_403` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：missing in a root is 404 not 403 |
| 31 | `MultiRootFileViewerTest` | `test_outside_all_roots_is_forbidden` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：outside all roots is forbidden |
| 32 | `MultiRootFileViewerTest` | `test_relative_path_resolves_against_each_root` | 相对路径逐个根试：命中哪个根就用哪个。 |
| 33 | `MultiRootFileViewerTest` | `test_roots_are_resolved_and_deduplicated_by_normalize` | 覆盖「多可见根——agent 能写多盘，查看器必须看得见它们写的文件」：roots are resolved and deduplicated by normalize |
| 34 | `SseContractTest` | `test_derived_title_truncates_and_flattens` | 覆盖「/ ：单流多路复用与事件信封」：derived title truncates and flattens |
| 35 | `SseContractTest` | `test_dir_browse_drives_layer` | `path=_drives_` 返回「计算机」层。 |
| 36 | `SseContractTest` | `test_dir_browse_item_shape_and_ordering` | 条目形状 {name,type,ext,path}；目录排前。 |
| 37 | `SseContractTest` | `test_dir_browse_missing_path_falls_back` | 访问不到的路径回落（不报错）——补全不能因为一个坏路径卡死。 |
| 38 | `SseContractTest` | `test_dir_browse_relative_path_uses_workspace_base` | 相对路径应基于可见根解析，且不得落到盘根。 |
| 39 | `SseContractTest` | `test_dir_browse_root_parent_is_drives` | 盘符根的 parent 是 `_drives_`，可从盘根回到计算机层。 |
| 40 | `SseContractTest` | `test_every_frame_carries_conversation_id` | 覆盖「/ ：单流多路复用与事件信封」：every frame carries conversation id |
| 41 | `SseContractTest` | `test_health_reports_model_for_header` | `/health` 须给出 model / allowed_models / 全局默认档位（顶栏与模型菜单）。 |
| 42 | `SseContractTest` | `test_history_and_sessions_endpoints` | 覆盖「/ ：单流多路复用与事件信封」：history and sessions endpoints |
| 43 | `SseContractTest` | `test_reasoning_effort_is_per_conversation` | 会话级档位不串会话：改一个不影响另一个（另一个回全局默认）。 |
| 44 | `SseContractTest` | `test_reasoning_effort_rejects_invalid` | 非法档位拒设且保留原值；缺 cid 报错。 |
| 45 | `SseContractTest` | `test_reasoning_effort_roundtrip` | 推理档位 GET/PUT 往返。 |
| 46 | `SseContractTest` | `test_sessions_carry_date_group` | 会话名录须带 date_group（会话菜单按它插分组标题）。 |
| 47 | `SseContractTest` | `test_sessions_carry_derived_title_not_raw_id` | 会话名录须带派生标题（首条用户输入），否则侧栏只能显示裸 UUID。 |
| 48 | `SseContractTest` | `test_sessions_sorted_by_recent_activity` | 覆盖「/ ：单流多路复用与事件信封」：sessions sorted by recent activity |
| 49 | `SseContractTest` | `test_turn_events_reach_the_stream` | 覆盖「/ ：单流多路复用与事件信封」：turn events reach the stream |
| 50 | `SseContractTest` | `test_two_sessions_do_not_cross` | 覆盖「/ ：单流多路复用与事件信封」：two sessions do not cross |
| 51 | `WriteGateOverWebTest` | `test_confirm_is_session_scoped` | 覆盖「写盘门控闭环经 Web 层 —— 三步写盘（预览 → review 解锁 → 提交落盘）」：confirm is session scoped |
| 52 | `WriteGateOverWebTest` | `test_unconfirmed_commit_rejected_then_review_unlocks` | 覆盖「写盘门控闭环经 Web 层 —— 三步写盘（预览 → review 解锁 → 提交落盘）」：unconfirmed commit rejected then review unlocks |

## test_web_ui_config.py

共 24 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `CompactionUiContractTest` | `test_card_contract_has_count_tokens_and_clean_summary` | 覆盖「压缩卡片必须走现成工具壳，并在实时、历史和来源会话三条路可见」：card contract has count tokens and clean summary |
| 2 | `CompactionUiContractTest` | `test_compaction_pane_can_show_the_full_summary` | 覆盖「压缩卡片必须走现成工具壳，并在实时、历史和来源会话三条路可见」：compaction pane can show the full summary |
| 3 | `CompactionUiContractTest` | `test_module_is_bundled_and_uses_tool_shell` | 覆盖「压缩卡片必须走现成工具壳，并在实时、历史和来源会话三条路可见」：module is bundled and uses tool shell |
| 4 | `ImageLightboxDefaultModeTest` | `test_css_does_not_pin_pixel_mode_to_a_corner` | 覆盖「预览默认以 1:1 打开并双向居中」：css does not pin pixel mode to a corner |
| 5 | `ImageLightboxDefaultModeTest` | `test_default_mode_is_pixel_not_fit` | 覆盖「预览默认以 1:1 打开并双向居中」：default mode is pixel not fit |
| 6 | `ImageLightboxDefaultModeTest` | `test_pixel_mode_centers_both_axes` | 覆盖「预览默认以 1:1 打开并双向居中」：pixel mode centers both axes |
| 7 | `ImageLightboxDefaultModeTest` | `test_pixel_padding_is_small_enough_to_still_center` | 1:1 的内边距不能大：图+内边距超过视口时，margin:auto 失效、图贴顶。 |
| 8 | `ImageLightboxDefaultModeTest` | `test_stage_scroll_is_centered_not_left_top` | 覆盖「预览默认以 1:1 打开并双向居中」：stage scroll is centered not left top |
| 9 | `ToolDetailLayoutTest` | `test_desktop_shot_reuses_the_read_image_meta_block` | 覆盖「工具详情只有两种形态，不能混着来」：desktop shot reuses the read image meta block |
| 10 | `ToolDetailLayoutTest` | `test_desktop_views_do_not_mount_raw_panels` | 覆盖「工具详情只有两种形态，不能混着来」：desktop views do not mount raw panels |
| 11 | `ToolShotPreviewClickTest` | `test_both_image_views_are_clickable` | 覆盖「工具壳详情里的图片点开同一个预览」：both image views are clickable |
| 12 | `ToolShotPreviewClickTest` | `test_click_delegates_to_the_shared_lightbox` | 覆盖「工具壳详情里的图片点开同一个预览」：click delegates to the shared lightbox |
| 13 | `ToolShotPreviewClickTest` | `test_missing_aia_degrades_without_breaking_the_card` | 预览是附加能力：拿不到 `AIA` 就不该把工具卡弄坏。 |
| 14 | `WaitTitleFormatTest` | `test_countdown_says_timeout_once_the_deadline_passes` | 覆盖「`desktop_wait` 等待中倒计时，结束后在标题末尾带上实际等待时长」：countdown says timeout once the deadline passes |
| 15 | `WaitTitleFormatTest` | `test_countdown_uses_the_timeout_as_its_duration` | 覆盖「`desktop_wait` 等待中倒计时，结束后在标题末尾带上实际等待时长」：countdown uses the timeout as its duration |
| 16 | `WaitTitleFormatTest` | `test_long_durations_are_written_in_units` | 覆盖「`desktop_wait` 等待中倒计时，结束后在标题末尾带上实际等待时长」：long durations are written in units |
| 17 | `WaitTitleFormatTest` | `test_nothing_is_reported_from_the_server_while_waiting` | 覆盖「`desktop_wait` 等待中倒计时，结束后在标题末尾带上实际等待时长」：nothing is reported from the server while waiting |
| 18 | `WaitTitleFormatTest` | `test_short_durations_keep_one_decimal_of_seconds` | 覆盖「`desktop_wait` 等待中倒计时，结束后在标题末尾带上实际等待时长」：short durations keep one decimal of seconds |
| 19 | `WaitTitleFormatTest` | `test_ticker_keeps_counting_overtime_until_the_result_arrives` | 覆盖「`desktop_wait` 等待中倒计时，结束后在标题末尾带上实际等待时长」：ticker keeps counting overtime until the result arrives |
| 20 | `WaitTitleFormatTest` | `test_wait_title_prints_the_waited_time` | 覆盖「`desktop_wait` 等待中倒计时，结束后在标题末尾带上实际等待时长」：wait title prints the waited time |
| 21 | `WebUiConfigTest` | `test_blank_value_keeps_the_default` | 覆盖「A class whose instances are single test cases」：blank value keeps the default |
| 22 | `WebUiConfigTest` | `test_classic_page_wires_the_placeholder` | 配置注入与工具卡拆分：占位符、开关属性、工具视图脚本进包。 |
| 23 | `WebUiConfigTest` | `test_missing_file_defaults_items_on_steps_off` | 覆盖「A class whose instances are single test cases」：missing file defaults items on steps off |
| 24 | `WebUiConfigTest` | `test_only_digit_one_turns_a_flag_on` | 覆盖「A class whose instances are single test cases」：only digit one turns a flag on |

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
| 1 | `WritePathKeysLifecycleTest` | `test_drop_plugin_removes_skills_from_registry` | 覆盖「A class whose instances are single test cases」：drop plugin removes skills from registry |
| 2 | `WritePathKeysLifecycleTest` | `test_gate_lookup_tracks_registry` | 覆盖「A class whose instances are single test cases」：gate lookup tracks registry |
| 3 | `WritePathKeysLifecycleTest` | `test_plugin_context_rollback_drops_tool_from_registry` | 覆盖「A class whose instances are single test cases」：plugin context rollback drops tool from registry |
| 4 | `WritePathKeysLifecycleTest` | `test_resolve_uses_declared_keys_not_default_path` | 覆盖「A class whose instances are single test cases」：resolve uses declared keys not default path |

## test_write_path_tools.py

共 36 个用例。

| # | 类 | 方法 | 测试目标 |
|---:|---|---|---|
| 1 | `WritePathToolsTest` | `test_backup_mode_reflects_the_replace_mode` | `replace_in_file` 的 mode 要区分字面替换与行区间替换，不能一律写成工具名。 |
| 2 | `WritePathToolsTest` | `test_backup_of_a_patch_records_the_patch_diff` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：backup of a patch records the patch diff |
| 3 | `WritePathToolsTest` | `test_backup_records_what_the_write_changed` | 写盘触发的备份要记下「这一版改了什么」。 |
| 4 | `WritePathToolsTest` | `test_cross_file_review_block` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：cross file review block |
| 5 | `WritePathToolsTest` | `test_delete_file_dir_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：delete file dir rejected |
| 6 | `WritePathToolsTest` | `test_delete_file_missing_is_already_absent` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：delete file missing is already absent |
| 7 | `WritePathToolsTest` | `test_delete_file_to_recycle` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：delete file to recycle |
| 8 | `WritePathToolsTest` | `test_edits_applies_all_in_order` | 批量字面替换：按顺序一次改完多处。 |
| 9 | `WritePathToolsTest` | `test_edits_are_sequential_not_parallel` | 后一条看得见前一条的结果：先 A→B 再把 B→C，最终应为 C。 |
| 10 | `WritePathToolsTest` | `test_edits_empty_list_rejected` | 空数组不是有效批量：拒绝而不是静默当成无事发生。 |
| 11 | `WritePathToolsTest` | `test_edits_rejects_mixing_with_literal_or_line_params` | edits 与 old_text / 行区间互斥，避免两套语义同时生效。 |
| 12 | `WritePathToolsTest` | `test_edits_rejects_top_level_replace_all` | 顶层 replace_all 在批量模式下不生效，必须拒绝而不是静默忽略。 |
| 13 | `WritePathToolsTest` | `test_edits_rejects_whole_batch_when_one_misses` | 任一条未命中整批拒绝，并指明是第几条；文件一个字节都不动。 |
| 14 | `WritePathToolsTest` | `test_file_ops_copy_and_overwrite_refused` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：file ops copy and overwrite refused |
| 15 | `WritePathToolsTest` | `test_file_ops_source_missing_is_not_already_applied` | copy/move/rename：源不在一律 source_missing（ok=false），不得因目标已在改判。 |
| 16 | `WritePathToolsTest` | `test_file_undo_requires_path` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：file undo requires path |
| 17 | `WritePathToolsTest` | `test_file_undo_restore_and_list` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：file undo restore and list |
| 18 | `WritePathToolsTest` | `test_patch_commit_applies` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch commit applies |
| 19 | `WritePathToolsTest` | `test_patch_context_mismatch_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch context mismatch rejected |
| 20 | `WritePathToolsTest` | `test_patch_missing_target_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch missing target rejected |
| 21 | `WritePathToolsTest` | `test_patch_outside_root_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch outside root rejected |
| 22 | `WritePathToolsTest` | `test_patch_preview_stats_no_write` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch preview stats no write |
| 23 | `WritePathToolsTest` | `test_patch_second_needs_review` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：patch second needs review |
| 24 | `WritePathToolsTest` | `test_read_write_slice_and_backup` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：read write slice and backup |
| 25 | `WritePathToolsTest` | `test_replace_commit_applies` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace commit applies |
| 26 | `WritePathToolsTest` | `test_replace_expected_mismatch_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace expected mismatch rejected |
| 27 | `WritePathToolsTest` | `test_replace_line_mode` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace line mode |
| 28 | `WritePathToolsTest` | `test_replace_old_absent_never_already_applied` | old 字面未命中一律 old_text_not_found；不得因 new 已在或删除语义改判。 |
| 29 | `WritePathToolsTest` | `test_replace_old_text_not_found` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace old text not found |
| 30 | `WritePathToolsTest` | `test_replace_preview_no_write` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace preview no write |
| 31 | `WritePathToolsTest` | `test_replace_same_text_already_applied` | 同值替换不得发空 diff 的 confirm_id。 |
| 32 | `WritePathToolsTest` | `test_replace_stale_file_rejected` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：replace stale file rejected |
| 33 | `WritePathToolsTest` | `test_reread_block_before_second_write` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：reread block before second write |
| 34 | `WritePathToolsTest` | `test_undo_backup_records_what_the_rollback_undid` | 回滚前的留档也要记 diff —— 否则"回滚"这一动作本身无迹可查。 |
| 35 | `WritePathToolsTest` | `test_write_file_same_content_already_applied` | 覆盖「六工具：正向提交 / 违规拒绝 / 门控联动」：write file same content already applied |
| 36 | `WritePathToolsTest` | `test_write_file_trailing_newline_only_shows_diff` | 仅差结尾换行时预览不得空 diff（splitlines 曾吃掉 \n）。 |

