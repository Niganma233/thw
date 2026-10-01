"""收藏夹（星标壁纸）的读写。

路径一律通过 ``core.paths`` 读取（``paths.FAVORITES_DIR``），理由同 services.cache：
按值绑定会让路径隔离出现漏网之鱼。
"""
import os
import shutil
import time
import uuid

from core.constants import IMAGE_EXTENSIONS
from core import paths


def list_favorites():
    """返回收藏目录下的图片文件名，按大小写不敏感的字典序排序。"""
    try:
        files = [f for f in os.listdir(paths.FAVORITES_DIR) if f.lower().endswith(IMAGE_EXTENSIONS)]
    except OSError:
        return []
    return sorted(files, key=str.casefold)


def safe_name(name):
    """把用户输入的收藏名清洗成合法文件名（不含扩展名）。

    公开函数：gui.py 的"收藏当前壁纸"对话框也要用它，之前那里手抄了一份同样的
    清洗逻辑，两边容易改漏。
    """
    cleaned = "".join("_" if c in '<>:"/\\|?*' else c for c in name).strip().rstrip(".")
    return cleaned or f"fav_{time.strftime('%Y%m%d_%H%M%S')}"


def save_favorite(src_path, name):
    """把 ``src_path`` 复制进收藏夹，返回 ``(文件名, 完整路径)``。

    重名时追加时间戳与随机后缀，不会覆盖已有收藏。
    """
    if not src_path or not os.path.isfile(src_path):
        raise FileNotFoundError("当前壁纸文件不存在")
    base = safe_name(name)
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        ext = ".jpg"
    fav_filename = f"{base}{ext}"
    fav_path = os.path.join(paths.FAVORITES_DIR, fav_filename)
    if os.path.exists(fav_path):
        fav_filename = f"{base}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}{ext}"
        fav_path = os.path.join(paths.FAVORITES_DIR, fav_filename)
    shutil.copy2(src_path, fav_path)
    return fav_filename, fav_path


def delete_favorite(filename):
    """删除收藏文件。

    只接受纯文件名：``os.path.basename(filename) != filename`` 时直接拒绝，
    避免 ``../`` 之类跑到收藏目录外面去删文件。
    """
    safe = os.path.basename(filename or "")
    if not safe or safe != filename:
        return False
    path = os.path.join(paths.FAVORITES_DIR, safe)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
