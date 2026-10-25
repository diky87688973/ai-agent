# -*- coding: utf-8 -*-
"""顶层服务解析与配置 schema 的边界测试。"""
from __future__ import annotations

import unittest

from agent.app_services import AppServices
from agent.config_schema import schema_keys


class AppServicesTest(unittest.TestCase):
    def test_missing_service_reports_assembly_hint(self) -> None:
        class Context:
            def get(self, name: str):
                raise KeyError(name)

        services = AppServices()
        services.context = Context()
        with self.assertRaisesRegex(KeyError, "服务未注册"):
            _ = services.registry


class ConfigSchemaTest(unittest.TestCase):
    def test_unknown_section_is_empty(self) -> None:
        self.assertEqual(schema_keys("missing-section"), set())


if __name__ == "__main__":
    unittest.main()
