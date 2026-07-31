# -*- coding: utf-8 -*-
from win11toast import notify


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
            body = ' '.join(m[3:])
            group = title
        else:
            title = text
            group = 'epicenter'
        image = {'src': image_url, 'placement': 'hero'}
    else:
        title = m[3]
        body = ' '.join(m[4:])
        group = title

    notify(
        title,
        body=body,
        image=image,
        group=group,
        tag=tag,
        audio={'silent': 'true'},
    )
