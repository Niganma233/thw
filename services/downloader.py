"""从图源抓取壁纸：URL 模板、带重试的 HTTP、JSON 包装解包。

只负责"拿到图片字节并落盘"，不关心谁在调用、也不碰界面。
"""
import time
import urllib.request
from urllib.parse import urlparse

from services.cache import write_wallpaper_file
from services.images import detect_extension, resolve_json_image_url

# 默认的网络参数；单个图源可以用自己的 timeout / retries 覆盖
DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2

_USER_AGENT = "TouhouWallpaper/3.0"


def build_source_url(source_url, site="all", size="pc"):
    """把图源模板里的 ``{size}`` / ``{site}`` 占位符替换成实际取值。"""
    url = (source_url or "").strip()
    if not url:
        raise ValueError("图源地址不能为空")
    try:
        return url.format(size=size, site=site)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"图源 URL 模板格式错误：{exc}") from exc


def fetch_with_retry(url, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES, backoff_base=DEFAULT_BACKOFF_BASE):
    """抓取 URL 内容，失败时按 ``backoff_base ** attempt`` 退避重试。

    返回 ``(字节内容, Content-Type)``；全部尝试失败后抛出最后一次的异常。
    非 http(s) 地址直接判为错误（也会走重试，与其它失败一视同仁）。
    """
    last_exc = None
    for attempt in range(max(1, retries)):
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("只支持 http:// 或 https:// 图源地址")
            request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), response.headers.get_content_type()
        except Exception as exc:
            last_exc = exc
            if attempt < max(1, retries) - 1:
                time.sleep(backoff_base ** attempt)
    raise last_exc


def fetch_source_image(url, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES):
    """抓取图源并返回图片字节。

    图源可以三种形式返回：直接是图片、302 跳到图片、或返回
    ``{"url": "图片地址"}`` 的 JSON。JSON 形式会再抓一次真正的图片地址。
    """
    data, _ = fetch_with_retry(url, timeout=timeout, retries=retries)
    try:
        detect_extension(data)
        return data
    except Exception:
        image_url = resolve_json_image_url(data)
        if not image_url:
            raise ValueError("图源没有直接返回图片，也没有找到可用的图片 URL")
        data, _ = fetch_with_retry(image_url, timeout=timeout, retries=retries)
        detect_extension(data)
        return data


def download_wallpaper(source, size_override=None, timeout=None, retries=None):
    """按图源对象下载一张壁纸，返回缓存里的落盘路径。

    size / timeout / retries 都由图源独立控制，显式传入的参数优先。
    """
    site = source.get("site", "all")
    size = size_override or source.get("size", "pc")
    timeout = int(timeout if timeout is not None else source.get("timeout", DEFAULT_TIMEOUT))
    retries = int(retries if retries is not None else source.get("retries", DEFAULT_RETRIES))
    url = build_source_url(source["url"], site=site, size=size)
    image_data = fetch_source_image(url, timeout=timeout, retries=retries)
    return write_wallpaper_file(image_data)
