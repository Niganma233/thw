"""把图源返回的字节解释成图片。

两个纯函数：判定字节是不是图片、以及图源用 JSON 包装时真正的图片地址在哪。
放在单独模块是为了让 services.cache 与 services.downloader 都能用，
又不至于让它们互相依赖。
"""
import io
import json

from PIL import Image

# Pillow 报告的 format 名 -> 文件扩展名；未知格式一律按 .jpg 处理
_FORMAT_EXTENSIONS = {
    "JPEG": ".jpg",
    "JPG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "BMP": ".bmp",
}

# 图源返回 JSON 时，按顺序尝试这些字段取出图片地址
_URL_KEYS = ("url", "image", "image_url", "download_url", "src")


def detect_extension(image_data):
    """校验字节确实是图片，返回对应扩展名；不是图片则抛出 PIL 的异常。"""
    with Image.open(io.BytesIO(image_data)) as image:
        image.verify()
        image_format = (image.format or "JPEG").upper()
    return _FORMAT_EXTENSIONS.get(image_format, ".jpg")


def resolve_json_image_url(data):
    """从图源的 JSON 响应里取出图片地址；不是 JSON 或取不到时返回 None。"""
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception:
        return None
    if isinstance(obj, dict):
        for key in _URL_KEYS:
            value = obj.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
    return None
