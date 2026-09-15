"""MIT: adapted from wuZHeBoy/bead-pattern; see licenses/bead-pattern.txt."""
import numpy as np
from PIL import Image

def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """rgb: (..., 3) 取值 0-255 → 返回同形状 (..., 3) 的 Lab。"""
    arr = np.asarray(rgb, dtype=np.float64) / 255.0
    arr = np.where(arr > 0.04045, ((arr + 0.055) / 1.055) ** 2.4, arr / 12.92)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    x /= 0.95047
    z /= 1.08883
    d = 6.0 / 29.0

    def f(t: np.ndarray) -> np.ndarray:
        return np.where(t > d ** 3, np.cbrt(t), t / (3 * d * d) + 4.0 / 29.0)

    fx, fy, fz = f(x), f(y), f(z)
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    bb = 200.0 * (fy - fz)
    return np.stack([L, a, bb], axis=-1)

def ciede2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """成对 CIEDE2000 色差。lab1:(M,3) lab2:(N,3) → (M,N)。"""
    L1 = lab1[:, 0][:, None]; a1 = lab1[:, 1][:, None]; b1 = lab1[:, 2][:, None]
    L2 = lab2[:, 0][None, :]; a2 = lab2[:, 1][None, :]; b2 = lab2[:, 2][None, :]

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2.0
    Cbar7 = Cbar ** 7
    G = 0.5 * (1 - np.sqrt(Cbar7 / (Cbar7 + 25.0 ** 7)))

    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)

    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p

    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dhp = np.where((C1p * C2p) == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2.0)

    Lbarp = (L1 + L2) / 2.0
    Cbarp = (C1p + C2p) / 2.0

    hsum = h1p + h2p
    habs = np.abs(h1p - h2p)
    hbarp = np.where(
        (C1p * C2p) == 0, hsum,
        np.where(habs <= 180, hsum / 2.0,
                 np.where(hsum < 360, (hsum + 360) / 2.0, (hsum - 360) / 2.0)),
    )

    T = (1
         - 0.17 * np.cos(np.radians(hbarp - 30))
         + 0.24 * np.cos(np.radians(2 * hbarp))
         + 0.32 * np.cos(np.radians(3 * hbarp + 6))
         - 0.20 * np.cos(np.radians(4 * hbarp - 63)))

    dtheta = 30 * np.exp(-(((hbarp - 275) / 25.0) ** 2))
    Cbarp7 = Cbarp ** 7
    Rc = 2 * np.sqrt(Cbarp7 / (Cbarp7 + 25.0 ** 7))
    Sl = 1 + (0.015 * (Lbarp - 50) ** 2) / np.sqrt(20 + (Lbarp - 50) ** 2)
    Sc = 1 + 0.045 * Cbarp
    Sh = 1 + 0.015 * Cbarp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc

    dE = np.sqrt(
        (dLp / Sl) ** 2
        + (dCp / Sc) ** 2
        + (dHp / Sh) ** 2
        + Rt * (dCp / Sc) * (dHp / Sh)
    )
    return dE

def to_grid(img: Image.Image, gw: int, gh: int, fit: bool) -> np.ndarray:
    """把图片降采样成 (gh, gw, 4) 的网格 RGBA。

    fit=True:保持比例缩放并居中,空白补透明(适合固定板尺寸)。
    fit=False:直接缩放到 gw×gh(auto 模式已按比例算好网格,不失真)。
    """
    img = img.convert("RGBA")
    if not fit:
        small = img.resize((gw, gh), Image.BOX)  # BOX=区域平均,抗锯齿
        return np.array(small)

    ratio = min(gw / img.width, gh / img.height)
    nw = max(1, round(img.width * ratio))
    nh = max(1, round(img.height * ratio))
    small = img.resize((nw, nh), Image.BOX)
    canvas = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    canvas.paste(small, ((gw - nw) // 2, (gh - nh) // 2))
    return np.array(canvas)
