"""图源数据层：负责内置/自定义图源的增删改、排序、启用状态与配置迁移。"""
import copy
import uuid
from urllib.parse import urlparse


BUILTIN_SOURCES = [
    {
        "id": "all",
        "name": "东方随机图（全部）",
        "url": "https://img.paulzzh.com/touhou/random?size={size}&site=all",
        "site": "all",
        "size": "pc",
        "timeout": 15,
        "retries": 3,
        "enabled": True,
        "builtin": True,
    },
    {
        "id": "konachan",
        "name": "东方随机图（Konachan）",
        "url": "https://img.paulzzh.com/touhou/random?size={size}&site=konachan",
        "site": "konachan",
        "size": "pc",
        "timeout": 15,
        "retries": 3,
        "enabled": True,
        "builtin": True,
    },
    {
        "id": "yandere",
        "name": "东方随机图（Yande.re）",
        "url": "https://img.paulzzh.com/touhou/random?size={size}&site=yandere",
        "site": "yandere",
        "size": "pc",
        "timeout": 15,
        "retries": 3,
        "enabled": True,
        "builtin": True,
    },
]


def _new_id():
    return f"custom_{uuid.uuid4().hex[:12]}"


def validate_source_url(url):
    url = (url or "").strip()
    if not url:
        raise ValueError("图源地址不能为空。")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("图源地址必须是 http:// 或 https:// URL。")
    try:
        url.format(size="pc", site="all")
    except (KeyError, ValueError) as exc:
        raise ValueError(f"URL 模板格式错误：{exc}") from exc
    return url


class SourceManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.migrate_legacy()

    def migrate_legacy(self):
        """把 v2 的 custom_sources 转为带独立参数的新 sources，并修复 custom:N 旧选择值。"""
        sources = self.cfg.get("sources")
        if not isinstance(sources, list):
            sources = []

        legacy = self.cfg.get("custom_sources", [])
        known_urls = {s.get("url") for s in sources if isinstance(s, dict)}
        legacy_index_to_id = {}
        for index, item in enumerate(legacy if isinstance(legacy, list) else []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            name = str(item.get("name", "自定义图源")).strip()
            if not url or url in known_urls:
                continue
            data = self._normalize_custom({"name": name, "url": url})
            sources.append(data)
            legacy_index_to_id[index] = data["id"]
            known_urls.add(url)

        normalized = []
        for item in sources:
            if isinstance(item, dict) and item.get("url") and item.get("name"):
                try:
                    normalized.append(self._normalize_custom(item))
                except (ValueError, TypeError):
                    continue
        self.cfg["sources"] = normalized

        old_selected = self.cfg.get("source_id", "all")
        if isinstance(old_selected, str) and old_selected.startswith("custom:"):
            try:
                old_index = int(old_selected.split(":", 1)[1])
                new_id = legacy_index_to_id.get(old_index)
                if new_id:
                    self.cfg["source_id"] = new_id
            except ValueError:
                self.cfg["source_id"] = "all"

    @staticmethod
    def _normalize_custom(item):
        data = {
            "id": item.get("id") or _new_id(),
            "name": str(item.get("name", "自定义图源")).strip() or "自定义图源",
            "url": str(item.get("url", "")).strip(),
            "site": str(item.get("site", "all")),
            "size": str(item.get("size", "pc")),
            "timeout": max(5, min(60, int(item.get("timeout", 15)))),
            "retries": max(1, min(5, int(item.get("retries", 3)))),
            "enabled": bool(item.get("enabled", True)),
            "builtin": False,
        }
        validate_source_url(data["url"])
        return data

    def custom_sources(self):
        return self.cfg["sources"]

    def all_sources(self):
        return copy.deepcopy(BUILTIN_SOURCES) + copy.deepcopy(self.cfg["sources"])

    def get(self, source_id):
        for source in BUILTIN_SOURCES:
            if source["id"] == source_id:
                return copy.deepcopy(source)
        for source in self.cfg["sources"]:
            if source["id"] == source_id:
                return copy.deepcopy(source)
        return None

    def enabled_candidates(self, preferred_id=None):
        custom = [copy.deepcopy(s) for s in self.cfg["sources"] if s.get("enabled", True)]
        builtins = [copy.deepcopy(s) for s in BUILTIN_SOURCES]
        # 当前选择优先，其余已启用自定义图源按照用户拖动后的顺序作为备用。
        ordered = []
        seen = set()
        if preferred_id:
            chosen = self.get(preferred_id)
            if chosen and chosen.get("enabled", True):
                ordered.append(chosen)
                seen.add(chosen["id"])
        for source in custom + builtins:
            if source["id"] not in seen and source.get("enabled", True):
                ordered.append(source)
                seen.add(source["id"])
        return ordered

    def add_or_update(self, source_id, name, url, site, size, timeout, retries, enabled=True):
        data = self._normalize_custom({
            "id": source_id or _new_id(),
            "name": name,
            "url": validate_source_url(url),
            "site": site,
            "size": size,
            "timeout": timeout,
            "retries": retries,
            "enabled": enabled,
        })
        items = self.cfg["sources"]
        for i, old in enumerate(items):
            if old.get("id") == data["id"]:
                items[i] = data
                return data, i
        items.append(data)
        return data, len(items) - 1

    def delete(self, source_id):
        items = self.cfg["sources"]
        for i, source in enumerate(items):
            if source.get("id") == source_id:
                return items.pop(i)
        return None

    def move(self, source_id, new_index):
        items = self.cfg["sources"]
        old_index = next((i for i, x in enumerate(items) if x.get("id") == source_id), None)
        if old_index is None:
            return False
        new_index = max(0, min(len(items) - 1, new_index))
        item = items.pop(old_index)
        items.insert(new_index, item)
        return old_index != new_index

    def set_enabled(self, source_id, enabled):
        for source in self.cfg["sources"]:
            if source.get("id") == source_id:
                source["enabled"] = bool(enabled)
                return True
        return False
