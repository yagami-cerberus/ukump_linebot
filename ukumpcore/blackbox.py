
from PIL import Image, ImageDraw, ImageFont
import os

CATALOG = {
    0: ("生理狀態", ),
    1: ("精神狀況", ),
    2: ("營養排泄", ),
    3: ("活動狀態", )
}

MEDIA_ROOT = os.path.join(os.path.dirname(__file__), "static", "robot")


def _render_baselayout(img, draw, name, title, date, catalog):
    os.path.basename(__file__)

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
            text_color = (255, 255, 255, 0)
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
        else:
            pass
            # _render_catalog(d, "沒有足夠資料", date)
        return img
    return wrapper


@_render_image
def process_card_1(reports):
    status = []

    g1_1 = max(r.report.get("收縮壓", 0) for r in reports)
    g1_2 = max(r.report.get("舒張壓", 0) for r in reports)
    if g1_1 > 140 or g1_2 > 90:
        status.append(("血壓", 3))
    elif g1_1 > 120 or g1_2 > 80:
        status.append(("血壓", 2))
    else:
        status.append(("血壓", 1))

    g2_1 = max(r.report.get("脈搏", 0) for r in reports)
    g2_2 = any(not r.report.get("脈搏規律", True) for r in reports)
    if g2_1 > 100:
        status.append(("脈搏", 3))
    elif g2_1 > 80 or g2_2:
        status.append(("脈搏", 2))
    else:
        status.append(("脈搏", 1))

    g3_1 = max(r.report.get("體溫", 0) for r in reports)
    if g3_1 > 37.5:
        status.append(("體溫", 3))
    elif g2_1 > 36:
        status.append(("體溫", 2))
    else:
        status.append(("體溫", 1))

    g4_1 = max(r.report.get("呼吸", 0) for r in reports)
    g4_2 = any(not r.report.get("呼吸規則", True) for r in reports)
    if g4_1 > 25:
        status.append(("呼吸", 3))
    elif g4_1 > 20 or g4_2:
        status.append(("呼吸", 2))
    else:
        status.append(("呼吸", 1))

    if any(r.report.get('皮膚狀況/傷口') for r in reports):
        status.append(("皮膚", 3))
    elif any(r.report.get('皮膚狀況/異常') and r.report.get('皮膚狀況/異常/說明') in (1, 2) for r in reports):
        # 淤青/有疹子
        status.append(("皮膚", 3))
    elif any(r.report.get('皮膚狀況/異常') and r.report.get('皮膚狀況/異常/說明') == 0 for r in reports):
        status.append(("皮膚", 2))
    else:
        status.append(("皮膚", 1))

    return status
process_card_1.catalog_id = 0


@_render_image
def process_card_2(reports):
    status = []

    g1 = max(r.report.get("意識情形", 0) % 3 for r in reports)
    status.append(("意識情形", g1 + 1))

    g2 = max(r.report.get("知覺狀況", 0) % 3 for r in reports)
    status.append(("知覺", g2 + 1))

    g3 = max(r.report.get("睡眠品質", 0) % 3 for r in reports)
    status.append(("睡眠", g3 + 1))

    g4 = max(r.report.get("行為", 0) % 3 for r in reports)
    status.append(("行為", g4 + 1))

    g5 = max(r.report.get("情緒", 0) % 3 for r in reports)
    status.append(("情緒", g5 + 1))

    return status
process_card_2.catalog_id = 1


@_render_image
def process_card_3(reports):
    status = []

    g1 = max(r.report.get("食慾", 0) % 3 for r in reports)
    status.append(("飲食", g1 + 1))

    g2_lc = min(r.report.get("小便", 6) for r in reports)
    # g2_bc = min(r.report.get("大便", 1) for r in reports)
    g2_er = any(not r.report.get("小便狀況", True) for r in reports) or any(not r.report.get("大便狀況", True) for r in reports)
    if g2_er:
        status.append(("排泄", 3))
    elif g2_lc < 6:
        status.append(("排泄", 2))
    else:
        status.append(("排泄", 1))

    g3 = max(r.report.get("用藥狀況", 0) % 3 for r in reports)
    status.append(("用藥", g3 + 1))

    return status
process_card_3.catalog_id = 2


@_render_image
def process_card_4(reports):
    status = []

    g1 = max(r.report.get("日課表活動/參與狀況", 0) % 3 for r in reports)
    status.append(("活動參與情形", g1 + 1))
    return status
process_card_4.catalog_id = 3


cards = (process_card_1, process_card_2, process_card_3, process_card_4)
