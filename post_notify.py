# -*- coding: utf-8 -*-
import io
import tempfile

from PIL import Image
from win11toast import notify
from winrt.windows.ui.viewmanagement import UISettings
import requests


def _img2hero(img: Image) -> Image:
    """
    364x180 に縮小したイメージを返す
    with Windows 11 UI bug

    https://learn.microsoft.com/en-us/windows/apps/develop/notifications/app-notifications/app-notifications-content?tabs=appsdk#hero-image
    """
    LW, LH = img.size
    HW, HH = (364, 180)

    # アクセシビリティでテキストのサイズを変更しているとイメージの右端が欠ける UI bug のため
    # テキストの拡大率を考慮した値に補正して通知センターのサイズに収める
    try:
        current_factor = UISettings().text_scale_factor
    except Exception:
        current_factor = 1
    delta_m = 80.0 * (current_factor - 1.0)
    w_safe = max(200, HW - delta_m)
    ratio = w_safe / HW
    nw = int(ratio * HW)
    nh = int(ratio * HW / (LW / LH))
    resized_img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    hero_img = Image.new('RGBA', (HW, HH), (0, 0, 0, 0))
    hero_img.paste(resized_img, (0, int((HH - nh) / 2)))

    return hero_img


def post(data: dict) -> None:
    text = data.get('text', '')
    image_url = data.get('image_url')
    title = None
    body = None
    image = None
    group = None
    tag = None

    m = text.split()
    if image_url:
        if image_url.startswith('https://weather-pctr.c.yimg.jp'):
            title = m[2]
            body = f"{' '.join(m[3:8])}\n{' '.join(m[8:])}"
            group = title
            tag = 'point info'
        else:
            title = text
            group = title
            tag = 'epicenter info'

        with requests.get(image_url, timeout=10) as r:
            hero_img = _img2hero(Image.open(io.BytesIO(r.content)))
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as f:
                temp_file_path = f.name
            hero_img.save(temp_file_path)

        image = {
            'src': temp_file_path,
            'placement': 'hero',
        }
    else:
        title = m[3]
        body = ' '.join(m[4:])
        group = title
        tag = 'info'

    notify(
        title,
        body=body,
        image=image,
        group=group,
        tag=tag,
        audio={'silent': 'true'},
    )
