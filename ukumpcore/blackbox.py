
from PIL import Image, ImageDraw, ImageFont
from itertools import chain
import os

NORMAL = 'NORMAL'
WARNING = 'WARNING'
DANGER = 'DANGER'
INVALID = 'INVALID'
STATUS = (NORMAL, WARNING, DANGER)

CATALOG = {
    0: ("生理狀態", ),
    1: ("精神狀況", ),
    2: ("營養排泄", ),
    3: ("活動狀態", )
}

MEDIA_ROOT = os.path.join(os.path.dirname(__file__), "static", "robot")
KEY_MAPPING = {
    '收縮壓': '血壓/收縮壓(mmHg)',
    '舒張壓': '血壓/舒張壓(mmHg)',
    '脈搏': '脈搏(次/分)',
    '脈搏規律': '',
    '呼吸': '呼吸(次/分)',
    '呼吸規則': '呼吸狀態',
    '體溫': '體溫(℃)',

    '意識情形': '意識情形',
    '知覺': '知覺狀況',
    '睡眠': '前晚睡眠情形',
    '行為': '特殊行為',
    '情緒': '個案情緒',

    '食慾/早': '早餐食慾(速度與量)',
    '食慾/午': '午餐食慾(速度與量)',
    '食慾/晚': '晚餐食慾(速度與量)',
    '小便': '小便',
    '用藥': '用藥',

    '活動參與': '參與狀況'
}

VALUE_MAPPING = {
    '呼吸規則': {'正常': True, '不正常': False},
    '意識情形': {
        '清醒': 0,
        '混亂': 1, '嗜睡': 1, '反應遲鈍': 1,
        '只對痛覺有一點反應': 2, '清醒程度反覆': 2, '無反應': 2
    },
    '知覺': {
        '正常': 0,
        '幻想': 1, '幻聽': 1, '錯覺': 1,
        '譫妄': 2
    },
    '睡眠': {
        '安穩': 0, '普通': 0,
        '不安穩': 1, '難入睡': 1,
        '失眠': 1, '服用鎮定劑': 1,
        '日夜顛倒': 2, '無法評估': 2,
    },
    '行為': {
        '無': 0,
        '遊走': 1, '作息混亂': 1, '干擾行為': 1, '妄想': 1, '恐懼或焦慮': 1, '憂鬱或負面狀態': 1,
        '重複行為': 1, '不適當行為': 1,
        '語言攻擊': 2, '肢體攻擊': 2, '抗拒照護': 2, '幻覺': 2, '自傷行為': 2, '破壞行為': 2,
        '無法評估': 2, '其他': 2
    },
    '情緒': {
        '1': 0, '2': 0, '3': 0, '4': 1, '5': 1, '6': 2, '7': 3
    },

    '食慾/早': {'佳': 0, '普通': 1, '差': 2},
    '食慾/午': {'佳': 0, '普通': 1, '差': 2},
    '食慾/晚': {'佳': 0, '普通': 1, '差': 2},
    '小便': {'正常': 0, '頻尿': 1, '次數較少': 2},
    '用藥': {
        '無須服藥': 0, '配合服藥': 0,
        '逾時服藥': 1,
        '拒絕服藥': 2, '服藥後嘔吐(無法補藥)': 2
    },

    '活動參與': {
        '主動': 0, '配合': 0,
        '被動': 1, '須引導': 1,
        '反覆異常': 4, '拒絕': 4,
    }
}


def get_int(report, key):
    realkey = KEY_MAPPING[key]
    try:
        return int(report.get(realkey))
    except (ValueError, TypeError):
        return None


def get_mapping(report, key):
    realkey = KEY_MAPPING[key]
    mapping = VALUE_MAPPING[key]
    value = report.get(realkey)
    return (value, mapping[value]) if value in mapping else (value, None)


def get_mappings(reports, key):
    realkey = KEY_MAPPING[key]
    mapping = VALUE_MAPPING[key]
    return map(lambda d: mapping[d],
               filter(lambda val: val in mapping,
                      map(lambda r: r.report.get(realkey),
                          reports)))


def get_ints(reports, key):
    realkey = KEY_MAPPING[key]
    for r in reports:
        val = r.report.get(realkey)
        if isinstance(val, int):
            yield val
        elif val:
            try:
                yield int(float(val))
            except (ValueError, TypeError):
                pass


def _render_baselayout(img, draw, name, title, date, catalog):
    if not name:
        name = " "
    if not title:
        title = " "

    bg = Image.open(os.path.join(MEDIA_ROOT, "card-%s.png" % catalog))
    img.paste(bg, (0, img.height - bg.height))

    name_fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', 100)
    name_size = name_fnt.getsize(name)
    while name_size[0] > 300:
        name_fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', name_fnt.size - 10)
        name_size = name_fnt.getsize(name)
    draw.text((10, 130 - name_size[1]), name, font=name_fnt, fill=(0, 0, 0, 0))

    title_fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', name_fnt.size - 10)
    title_size = title_fnt.getsize(title)
    while title_size[0] > 140:
        title_fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', title_fnt.size - 10)
        title_size = title_fnt.getsize(title)
    draw.text((name_size[0] + 30, 130 - title_size[1]), title, font=title_fnt, fill=(0, 0, 0, 0))

    label = CATALOG.get(catalog, ("未分類", ))[0]
    catalog_fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', 60)
    draw.text((20, 190), label, font=catalog_fnt, fill=(0, 0, 0, 0))

    date_fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', 40)
    draw.text((20, 270), str(date), font=date_fnt, fill=(0, 0, 0, 0))


def _render_status(draw, status):
    fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', 40)
    r = 120

    for i, st in enumerate(status):
        x = 768 if i & 1 else 512
        y = (i // 2) * r + 60
        label, warning = st
        fsize = fnt.getsize(label)

        if warning == 3:
            text_color = (255, 255, 255, 0)
            border_color = (150, 150, 150, 0)
            bg_color = (244, 122, 51, 0)
        elif warning == 2:
            text_color = (252, 190, 44)
            border_color = (252, 190, 44, 0)
            bg_color = (255, 255, 255, 0)
        else:
            text_color = (0, 0, 0, 0)
            border_color = (131, 181, 98, 0)
            bg_color = (255, 255, 255, 0)

        draw.chord((x, y, x + r - 50, y + r - 50), 90, 270, bg_color)
        draw.arc((x, y, x + r - 50, y + r - 50), 90, 270, border_color)
        draw.arc((x, y + 1, x + r - 50, y + r - 51), 90, 270, border_color)

        draw.chord((256 + x - r, y, 206 + x, y + r - 50), 270, 90, bg_color)
        draw.arc((256 + x - r, y, 206 + x, y + r - 50), 270, 90, border_color)
        draw.arc((256 + x - r, y + 1, 206 + x, y + r - 51), 270, 90, border_color)

        draw.rectangle((x + r / 4, y + 1, x + 206 - r / 4, y + r - 51), bg_color)
        draw.line((x + r / 4, y, x + 206 - r / 4, y), border_color, width=2)
        draw.line((x + r / 4, y + r - 51, x + 206 - r / 4, y + r - 51), border_color, width=2)

        fsize = fnt.getsize(label)
        draw.text((x + ((200 - fsize[0]) >> 1), y + 3), label, font=fnt, fill=text_color)


def _render_rank(draw, rank):
    pos = (306, 240)
    if rank == 1:
        fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', 50)
        draw.text(pos, "好", font=fnt, fill=(0, 0, 200, 0))
    elif rank == 2:
        fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', 50)
        draw.text(pos, "普通", font=fnt, fill=(200, 200, 0, 0))
    elif rank == 3:
        fnt = ImageFont.truetype('./NotoSansCJKkr-Regular.otf', 50)
        draw.text(pos, "差", font=fnt, fill=(255, 0, 0, 0))


def _render_image(fn):
    def wrapper(patient, date, reports):
        img = Image.new('RGB', (1024, 678), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        _render_baselayout(img, d, patient.name, patient.extend.get("title", ""), date, wrapper.catalog_id)

        if reports:
            status = fn(reports)

            rank = max(j for i, j in status)
            _render_rank(d, rank)
            _render_status(d, status)
        return img
    return wrapper


@_render_image
def process_card_1(reports):
    status = []

    g1_1 = max(get_ints(reports, '收縮壓'), default=0)
    g1_2 = max(get_ints(reports, '舒張壓'), default=0)
    if g1_1 > 140 or g1_2 > 90:
        status.append(('血壓', 3))
    elif g1_1 > 120 or g1_2 > 80:
        status.append(('血壓', 2))
    else:
        status.append(('血壓', 1))

    g2_1 = max(get_ints(reports, '脈搏'), default=0)
    if g2_1 > 100:
        status.append(('脈搏', 3))
    elif g2_1 > 80:
        status.append(('脈搏', 2))
    else:
        status.append(('脈搏', 1))

    g3_1 = max(get_ints(reports, '體溫'), default=0)
    if g3_1 > 37.5:
        status.append(('體溫', 3))
    elif g2_1 > 36:
        status.append(('體溫', 2))
    else:
        status.append(('體溫', 1))

    g4_1 = max(get_ints(reports, '呼吸'), default=0)
    g4_2 = any(not i for i in get_mappings(reports, '呼吸規則'))
    if g4_1 > 25:
        status.append(('呼吸', 3))
    elif g4_1 > 20 or g4_2:
        status.append(('呼吸', 2))
    else:
        status.append(('呼吸', 1))

    # if any(r.report.get('皮膚狀況/傷口') for r in reports):
    #     status.append(("皮膚", 3))
    # elif any(r.report.get('皮膚狀況/異常') and r.report.get('皮膚狀況/異常/說明') in (1, 2) for r in reports):
    #     # 淤青/有疹子
    #     status.append(("皮膚", 3))
    # elif any(r.report.get('皮膚狀況/異常') and r.report.get('皮膚狀況/異常/說明') == 0 for r in reports):
    #     status.append(("皮膚", 2))
    # else:
    #     status.append(("皮膚", 1))
    status.append(("皮膚", 1))

    return status
process_card_1.catalog_id = 0


@_render_image
def process_card_2(reports):
    status = []

    g1 = max((val % 3 for val in get_mappings(reports, '意識情形')), default=0)
    status.append(('意識情形', g1 + 1))

    g2 = max((val % 3 for val in get_mappings(reports, '知覺')), default=0)
    status.append(('知覺', g2 + 1))

    g3 = max((val % 3 for val in get_mappings(reports, '睡眠')), default=0)
    status.append(('睡眠', g3 + 1))

    g4 = max((val % 3 for val in get_mappings(reports, '行為')), default=0)
    status.append(('行為', g4 + 1))

    g5 = max((val % 3 for val in get_mappings(reports, '情緒')), default=0)
    status.append(('情緒', g5 + 1))

    return status
process_card_2.catalog_id = 1


@_render_image
def process_card_3(reports):
    status = []
    g1 = max(chain(*tuple(get_mappings(reports, k) for k in ('食慾/早', '食慾/午', '食慾/晚'))), default=0)
    status.append(('飲食', g1 + 1))

    # g2 = max(get_mappings('小便'))
    # g2_lc = min(r.report.get('小便', 6) for r in reports)
    # # g2_bc = min(r.report.get("大便", 1) for r in reports)
    # g2_er = any(not r.report.get("小便狀況", True) for r in reports) or any(not r.report.get("大便狀況", True) for r in reports)
    # if g2_er:
    #     status.append(("排泄", 3))
    # elif g2_lc < 6:
    #     status.append(("排泄", 2))
    # else:
    #     status.append(("排泄", 1))
    status.append(("排泄", 1))

    g3 = max(get_mappings(reports, '用藥'), default=0)
    status.append(('用藥', g3 + 1))

    return status
process_card_3.catalog_id = 2


@_render_image
def process_card_4(reports):
    status = []

    g1 = max((get_mappings(reports, '活動參與')), default=0)
    status.append(('活動參與', g1 + 1))
    return status
process_card_4.catalog_id = 3


cards = (process_card_1, process_card_2, process_card_3, process_card_4)


def daily_report_processor(report):
    bph = get_int(report, '收縮壓')
    bpl = get_int(report, '舒張壓')
    if not bph or not bpl:
        yield '血壓', {'status': INVALID}
    elif bph > 140 or bpl > 90:
        yield '血壓', {'status': DANGER, 'value': (bpl, bph)}
    elif bph > 120 or bpl > 80:
        yield '血壓', {'status': WARNING, 'value': (bpl, bph)}
    else:
        yield '血壓', {'status': NORMAL, 'value': (bpl, bph)}

    hb = get_int(report, '脈搏')
    if not hb:
        yield '脈搏', {'status': INVALID}
    elif hb > 100 or hb < 40:
        yield '脈搏', {'status': DANGER, 'value': hb}
    elif hb > 80:
        yield '脈搏', {'status': WARNING, 'value': hb}
    else:
        yield '脈搏', {'status': NORMAL, 'value': hb}

    bt = get_int(report, '體溫')
    if not bt:
        yield '體溫', {'status': INVALID}
    elif bt > 100:
        yield '體溫', {'status': DANGER, 'value': bt}
    elif bt > 80:
        yield '體溫', {'status': WARNING, 'value': bt}
    else:
        yield '體溫', {'status': NORMAL, 'value': bt}

    bf = get_int(report, '呼吸')
    if not bf:
        yield '呼吸', {'status': INVALID}
    elif bf > 100 or bf < 10:
        yield '呼吸', {'status': DANGER, 'value': bf}
    elif bf > 80:
        yield '呼吸', {'status': WARNING, 'value': bf}
    else:
        yield '呼吸', {'status': NORMAL, 'value': bf}

    for catalog in ('意識情形', '知覺', '睡眠', '行為', '情緒', '活動參與', '用藥'):
        text, value = get_mapping(report, catalog)
        yield catalog, {'status': INVALID if value is None else STATUS[value % 3], 'text': text}
