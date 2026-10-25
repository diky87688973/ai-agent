# -*- coding: utf-8 -*-
"""网络查询族工具：ip_geolocate / open_meteo_weather。

- ip_geolocate：ipwho.is 免费 API 查询 IP 地理（无 Key；内网/回环归一化为出口查询）；
- open_meteo_weather：Open-Meteo 天气（三来源解析：经纬度 ＞ 地名（CN 别名表 + 评分选择）＞ IP 兜底）。
"""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from agent.capabilities.registry import ToolPlugin
from agent.core.error_report import report_error

IP_TIMEOUT_SEC = 12
WEATHER_TIMEOUT_SEC = 15
WEATHER_FORECAST_DAYS = 2

IP_API_URL = "https://ipwho.is"
GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FC_URL = "https://api.open-meteo.com/v1/forecast"

CN_CITY_ALIAS: Dict[str, Tuple[float, float, str, str, str]] = {
    "北京": (39.9042, 116.4074, "北京", "北京市", "中国"),
    "北京市": (39.9042, 116.4074, "北京", "北京市", "中国"),
    "上海": (31.2304, 121.4737, "上海", "上海市", "中国"),
    "上海市": (31.2304, 121.4737, "上海", "上海市", "中国"),
    "广州": (23.1291, 113.2644, "广州", "广东省", "中国"),
    "深圳": (22.5431, 114.0579, "深圳", "广东省", "中国"),
    "杭州": (30.2741, 120.1551, "杭州", "浙江省", "中国"),
    "南京": (32.0603, 118.7969, "南京", "江苏省", "中国"),
    "成都": (30.5728, 104.0668, "成都", "四川省", "中国"),
    "重庆": (29.5630, 106.5516, "重庆", "重庆市", "中国"),
    "天津": (39.3434, 117.3616, "天津", "天津市", "中国"),
    "武汉": (30.5928, 114.3055, "武汉", "湖北省", "中国"),
    "西安": (34.3416, 108.9398, "西安", "陕西省", "中国"),
    "苏州": (31.2989, 120.5853, "苏州", "江苏省", "中国"),
}


class GeoServiceError(RuntimeError):
    """网络查询结构化错误：type / hint / retryable 随 data 透传。"""

    def __init__(self, message: str, *, err_type: str = "GeoServiceError", hint: str = "", retryable: bool = False) -> None:
        super().__init__(message)
        self.data = {"type": err_type, "message": message, "hint": hint, "retryable": retryable}


def _http_json(url: str, timeout_sec: int, user_agent: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _normalize_ip_for_lookup(ip_raw: Any) -> str:
    """内网 / 回环 / 未指定地址归一化为空串（视为未指定，查出口 IP）。"""
    ip = str(ip_raw or "").strip()
    if not ip:
        return ""
    low = ip.lower()
    if low in {"localhost", "0.0.0.0", "127.0.0.1", "::1"}:
        return ""
    try:
        obj = ipaddress.ip_address(ip)
    except ValueError:
        # 非法 IP 字面量：按「未指定」处理，走出口 IP 查询
        return ""
    if obj.is_loopback or obj.is_unspecified or obj.is_private:
        return ""
    return ip


def _resolve_timeout(raw: Any, default: int) -> int:
    try:
        value = int(raw) if raw is not None and str(raw).strip() != "" else default
    except (TypeError, ValueError):
        raise GeoServiceError("timeout_sec 须为整数", hint="检查参数类型")
    return max(5, value)


def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).casefold()


def _has_cjk(s: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", str(s or "")) is not None


def _score_geo_result(query: str, hit: Dict[str, Any]) -> float:
    """地理编码候选评分：名称匹配 / 人口 / admin / feature_code 加权。"""
    qn = _normalize_name(query)
    nn = _normalize_name(str(hit.get("name") or ""))
    admin1 = str(hit.get("admin1") or "")
    admin2 = str(hit.get("admin2") or "")
    country = str(hit.get("country") or "")
    cc = str(hit.get("country_code") or "").upper()
    feat = str(hit.get("feature_code") or "").upper()
    pop = float(hit.get("population") or 0)

    score = 0.0
    score += min(pop / 100000.0, 50.0)
    if nn == qn:
        score += 120
    elif qn and qn in nn:
        score += 60
    elif nn and nn in qn:
        score += 35
    joined = _normalize_name(admin1 + admin2 + country)
    if qn and qn in joined:
        score += 25
    if _has_cjk(query):
        if cc == "CN":
            score += 60
        if feat in {"PPLC", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPL"}:
            score += 20
    if qn == "北京" and _normalize_name(admin1) == "北京市":
        score += 180
    return score


def _pick_geo_result(query: str, js: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    results = js.get("results")
    if not isinstance(results, list) or not results:
        return None
    candidates = [x for x in results if isinstance(x, dict)]
    if not candidates:
        return None
    candidates.sort(key=lambda h: _score_geo_result(query, h), reverse=True)
    return candidates[0]


def _lookup_ip_region(ip_for_lookup: str, timeout_sec: int) -> Optional[Dict[str, Any]]:
    tail = ("/" + urllib.parse.quote(ip_for_lookup, safe="")) if ip_for_lookup else ""
    js = _http_json(IP_API_URL + tail, timeout_sec, "open-meteo-weather/1")
    if js.get("success") is False:
        return None
    if js.get("latitude") is None or js.get("longitude") is None:
        return None
    return js


def _wmo_zh(code: Optional[int]) -> str:
    if code is None:
        return "未知"
    m = {
        0: "晴",
        1: "大部晴",
        2: "少云",
        3: "阴天",
        45: "雾",
        48: "雾凇",
        51: "小毛毛雨",
        53: "毛毛雨",
        55: "大毛毛雨",
        61: "小阵雨",
        63: "阵雨",
        65: "大阵雨",
        71: "小雪",
        73: "雪",
        75: "大雪",
        80: "小阵雨",
        81: "阵雨",
        82: "强阵雨",
        95: "雷暴",
        96: "雷暴伴冰雹",
        99: "强雷暴伴冰雹",
    }
    return m.get(int(code), f"天气码{code}")


class IpGeolocateTool(ToolPlugin):
    """IP 地理查询。"""

    name = "ip_geolocate"
    label = "定位公网地区"
    icon = "📍"
    description = "IP 地理查询（ipwho.is 免费 API，无 Key）：国家/城市/经纬度/时区；内网或未指定 IP 自动查出口。"
    parameters = {
        "ip": {"type": "string", "description": "待查询 IP（省略/内网/回环时查当前出口公网 IP）"},
        "timeout_sec": {"type": "integer", "description": "HTTP 超时秒数（默认 12，下限 5）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tsec = _resolve_timeout(arguments.get("timeout_sec"), IP_TIMEOUT_SEC)
        ip_raw = str(arguments.get("ip") or "").strip()
        ip_n = _normalize_ip_for_lookup(ip_raw)
        try:
            q = ""
            if ip_n:
                q = "/" + urllib.parse.quote(ip_n, safe="")
            js = _http_json(IP_API_URL + q, tsec, "ip-geolocate/1")
            if js.get("success") is False:
                raise GeoServiceError(
                    str(js.get("message") or "ipwho.is 查询失败"),
                    err_type="GeoLocateError",
                    hint="检查 IP 是否合法，或稍后重试",
                    retryable=True,
                )
            city = str(js.get("city") or "")
            region = str(js.get("region") or "")
            country = str(js.get("country") or "")
            lat = js.get("latitude")
            lon = js.get("longitude")
            tz = js.get("timezone") or {}
            tz_id = str(tz.get("id") or "") if isinstance(tz, dict) else ""
            ip_used = str(js.get("ip") or ip_n)

            parts = [x for x in (city, region, country) if x]
            display_region = ",".join(parts) if parts else "未知地区"
            summary = f"【IP定位地区】{display_region}"
            if lat is not None and lon is not None:
                summary += f"（{lat},{lon}）"
            if tz_id:
                summary += f"，时区 {tz_id}"

            return {
                "provider": "ipwho.is",
                "ip": ip_used,
                "city": city,
                "region": region,
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "timezone": tz_id,
                "display_region_zh": "【IP定位地区】" + display_region,
                "summary_zh": summary,
                "raw": js,
            }
        except GeoServiceError:
            raise
        except urllib.error.HTTPError as e:
            raise GeoServiceError(str(e), err_type="HTTPError", hint="稍后重试", retryable=True)
        except urllib.error.URLError as e:
            raise GeoServiceError(str(e.reason), err_type="URLError", hint="检查网络或 DNS", retryable=True)
        except Exception as e:
            report_error("agent.capabilities.builtin.geo_weather_tools.IpGeolocateTool.execute", e)
            raise GeoServiceError(str(e), err_type=type(e).__name__)


class OpenMeteoWeatherTool(ToolPlugin):
    """天气查询。"""

    name = "open_meteo_weather"
    label = "查询天气"
    icon = "🌤️"
    description = "天气预报（Open-Meteo 免费 API，无 Key）：支持地名 / 经纬度 / IP 定位三来源；中文摘要输出。"
    parameters = {
        "location": {"type": "string", "description": "城市或地区名（如 北京；先查内置别名表）"},
        "latitude": {"type": "string", "description": "纬度（与 longitude 成对）"},
        "longitude": {"type": "string", "description": "经度（与 latitude 成对）"},
        "ip": {"type": "string", "description": "客户端公网 IP（无 location/经纬度时用于定位）"},
        "forecast_days": {"type": "integer", "description": "预报天数 1-7（默认 2）"},
        "timeout_sec": {"type": "integer", "description": "HTTP 超时秒数（默认 15，下限 5）"},
    }

    def _forecast_days(self, value: Any) -> int:
        try:
            days = int(value) if value else WEATHER_FORECAST_DAYS
        except (TypeError, ValueError):
            raise GeoServiceError("forecast_days 须为整数", hint="检查参数类型")
        return max(1, min(7, days))

    def _resolve_location(self, location: str, latitude: str, longitude: str,
                          ip: str, tsec: int):
        loc_input = str(location or "").strip()
        lat_s = str(latitude or "").strip()
        lon_s = str(longitude or "").strip()
        ip_for_lookup = _normalize_ip_for_lookup(ip)
        name_used, admin1, country, source, note = loc_input, "", "", "location", ""
        if lat_s and lon_s:
            lat, lon = float(lat_s), float(lon_s)
            name_used = f"经纬度 {lat:.4f}°,{lon:.4f}°"
            source = "coordinates"
        elif loc_input:
            alias = CN_CITY_ALIAS.get(loc_input)
            if alias is not None:
                lat, lon, name_used, admin1, country = alias
            else:
                q = urllib.parse.urlencode({
                    "name": loc_input, "count": "10", "language": "zh",
                    "format": "json"})
                geo = _http_json(f"{GEO_URL}?{q}", tsec, "open-meteo-weather/1")
                hit = _pick_geo_result(loc_input, geo)
                if hit is None:
                    raise GeoServiceError(
                        f"未找到地名：{loc_input}", err_type="NotFound",
                        hint="可换 location 或改用 latitude/longitude")
                lat = float(hit.get("latitude"))
                lon = float(hit.get("longitude"))
                name_used = str(hit.get("name") or loc_input)
                admin1 = str(hit.get("admin1") or "")
                country = str(hit.get("country") or "")
        else:
            ip_geo = _lookup_ip_region(ip_for_lookup, tsec)
            if ip_geo is None:
                raise GeoServiceError(
                    "无法获取地区：未提供 location/经纬度，且 IP 定位失败",
                    err_type="RegionUnavailable",
                    hint="请传 location 或 latitude/longitude；也可传 ip（客户端公网 IP）",
                    retryable=True)
            lat = float(ip_geo.get("latitude"))
            lon = float(ip_geo.get("longitude"))
            city = str(ip_geo.get("city") or "")
            region = str(ip_geo.get("region") or "")
            ctry = str(ip_geo.get("country") or "")
            name_used = city or region or ctry or "IP定位结果"
            admin1, country, source = region, ctry, "ip_geolocate"
            note = (f"说明：按指定 IP（{ip_for_lookup}）定位地区后查询天气。"
                    if ip_for_lookup else
                    "说明：未传 location，已按公网出口 IP 自动定位地区后查询天气。")
        return lat, lon, name_used, admin1, country, source, note, loc_input

    @staticmethod
    def _summary(name_used: str, admin1: str, country: str, note: str,
                 lat: float, lon: float, cur: dict, daily: dict,
                 days: int) -> str:
        tail = ""
        if admin1 or country:
            tail = "（" + "，".join([x for x in (admin1, country) if x]) + "）"
        lines = [f"【解析地区】{name_used}{tail}"]
        if note:
            lines.append(note)
        lines.append(f"坐标：{lat:.4f}, {lon:.4f}")
        cur_code = cur.get("weather_code")
        lines.append(
            f"当前：{_wmo_zh(int(cur_code)) if cur_code is not None else '未知'}，"
            f"气温 {cur.get('temperature_2m')}℃，降水 {cur.get('precipitation')}mm，"
            f"湿度 {cur.get('relative_humidity_2m')}%")
        d_time = daily.get("time") or []
        d_rain_p = daily.get("precipitation_probability_max") or []
        d_prec = daily.get("precipitation_sum") or []
        d_wx = daily.get("weather_code") or []
        if d_time and (d_rain_p or d_prec):
            lines.append("未来数日降水概况：")
            for i, day in enumerate(d_time[:days]):
                prob = d_rain_p[i] if i < len(d_rain_p) else None
                prec = d_prec[i] if i < len(d_prec) else None
                wxc = int(d_wx[i]) if i < len(d_wx) and d_wx[i] is not None else None
                prob_s = f"{prob}%" if prob is not None else "-"
                prec_s = f"{prec}mm" if prec is not None else "-"
                lines.append(f"  {day}：降水概率 {prob_s}，降水量 {prec_s}，{_wmo_zh(wxc)}")
        return "\n".join(lines)

    def _run_core(self, *, location: str = "", latitude: str = "",
                  longitude: str = "", ip: str = "", forecast_days: Any = None,
                  timeout_sec: Any = None) -> Dict[str, Any]:
        tsec = _resolve_timeout(timeout_sec, WEATHER_TIMEOUT_SEC)
        days = self._forecast_days(forecast_days)
        lat, lon, name_used, admin1, country, source, note, loc_input = (
            self._resolve_location(location, latitude, longitude, ip, tsec))
        q2 = urllib.parse.urlencode({
            "latitude": str(lat), "longitude": str(lon),
            "timezone": "Asia/Shanghai", "forecast_days": str(days),
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,showers,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
        })
        fc = _http_json(f"{FC_URL}?{q2}", tsec, "open-meteo-weather/1")
        cur = fc.get("current") or {}
        daily = fc.get("daily") or {}
        summary = self._summary(name_used, admin1, country, note, lat, lon,
                                cur, daily, days)
        tail = ("（" + "，".join([x for x in (admin1, country) if x]) + "）"
                if admin1 or country else "")
        display_plain = f"{name_used}{tail}"
        return {
            "provider": "Open-Meteo", "source": source,
            "requested_location": loc_input, "resolved_name": name_used,
            "display_plain": display_plain,
            "display_region_zh": "【解析地区】" + display_plain,
            "latitude": lat, "longitude": lon, "timezone": fc.get("timezone"),
            "current": cur, "daily": daily, "summary_zh": summary,
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._run_core(
                location=str(arguments.get("location") or ""),
                latitude=str(arguments.get("latitude") or ""),
                longitude=str(arguments.get("longitude") or ""),
                ip=str(arguments.get("ip") or ""),
                forecast_days=arguments.get("forecast_days"),
                timeout_sec=arguments.get("timeout_sec"),
            )
        except GeoServiceError:
            raise
        except urllib.error.HTTPError as e:
            raise GeoServiceError(str(e), err_type="HTTPError", hint="稍后重试", retryable=True)
        except urllib.error.URLError as e:
            raise GeoServiceError(str(e.reason), err_type="URLError", hint="检查网络或 DNS", retryable=True)
        except Exception as e:
            report_error("agent.capabilities.builtin.geo_weather_tools.OpenMeteoWeatherTool.execute", e)
            raise GeoServiceError(str(e), err_type=type(e).__name__)


def build_plugins() -> List[ToolPlugin]:
    """构造本组工具（ip_geolocate / open_meteo_weather）。"""
    return [IpGeolocateTool(), OpenMeteoWeatherTool()]
