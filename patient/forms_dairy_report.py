
from django.core.exceptions import ValidationError
from django import forms

INPUT_CLASS = 'form-control form-control-sm'
SHORT_INPUT_CLASS = INPUT_CLASS + ' input-size6'


def number_input(pattern="\d*"):
    return forms.NumberInput(attrs={'class': SHORT_INPUT_CLASS, 'pattern': pattern})


def text_input(placeholder="", short=False):
    if short:
        return forms.TextInput(attrs={'class': SHORT_INPUT_CLASS, 'placeholder': placeholder})
    else:
        return forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': placeholder})


def boolean_radio(true_label, false_label):
    return forms.RadioSelect(choices=(('true', true_label), ('false', false_label)))


def select_input(choices):
    return forms.Select(attrs={'class': INPUT_CLASS}, choices=choices)


class BooleanField(forms.NullBooleanField):
    def prepare_value(self, value):
        if value is True:
            return 'true'
        elif value is False:
            return 'false'
        else:
            return str(value)

    def validate(self, value):
        if value is None and self.required:
            raise ValidationError(self.error_messages['required'], code='required')


class DairyReportFormV1(forms.Form):
    r1_1 = forms.IntegerField(label="收縮壓", widget=number_input())
    r1_2 = forms.IntegerField(label="舒張壓", widget=number_input())
    r1_3 = forms.IntegerField(label="脈搏", widget=number_input())
    r1_4 = BooleanField(label="脈搏規律", widget=boolean_radio("規律", "不規律"))
    r1_5 = forms.FloatField(label="體溫", widget=number_input("\d*.\d*"))
    r1_6 = forms.IntegerField(label="呼吸", widget=number_input())
    r1_7 = BooleanField(label="呼吸規則", widget=boolean_radio("規則", "不規則"))

    r3_1 = forms.IntegerField(label="意識情形", widget=select_input(choices=(
        ("0", "清楚"), ("1", "混亂"), ("4", "嗜睡"), ("7", "反應遲鈍"), ("2", "只對痛有些反應"),
        ("5", "無反應"), )))
    r3_2 = forms.IntegerField(label="知覺狀況", widget=select_input(choices=(
        ("0", "正常"), ("1", "幻想"), ("4", "幻聽"), ("7", "錯覺"), ("2", "譫妄"), )))

    r4_1 = forms.IntegerField(label="昨晚睡眠_小時", widget=select_input((((i / 2, i / 2) for i in range(49)))))
    r4_2 = forms.IntegerField(label="午休睡眠_分鐘", widget=select_input((((i, i) for i in range(0, 125, 5)))))
    r4_3 = forms.IntegerField(label="睡眠品質", widget=select_input(choices=(
        ("0", "安穩"), ("3", "普通"), ("1", "不安穩"), ("4", "難入睡"), ("7", "失眠"),
        ("10", "服用鎮定劑"), ("2", "日夜顛倒"), ("5", "無法評估"), )))
    r4_4 = forms.IntegerField(label="行為", widget=select_input(choices=(
        ("0", "無"), ("1", "遊走"), ("4", "作息混亂"), ("2", "語言攻擊"), ("5", "肢體攻擊"),
        ("7", "干擾行為"), ("8", "抗拒照護"), ("10", "妄想"), ("13", "幻覺"), ("16", "恐懼或焦慮"),
        ("19", "憂鬱或負面狀態"), ("11", "自傷行為"), ("22", "重複行為"), ("14", "破壞行為"),
        ("17", "不適當行為"), ("20", "無法評估"), ("-1", "其他"), )))
    r4_4e = forms.CharField(label="行為/其他", widget=text_input(placeholder="行為/其他"), required=False)

    r5_1 = forms.IntegerField(label="情緒", widget=select_input(choices=(
        ("0", "適當"), ("2", "異常欣快"), ("5", "起伏易變"), ("1", "情緒低落"), ("8", "易怒"),
        ("11", "無法評估"), ("-1", "其他"), )))
    r5_1e = forms.CharField(label="情緒/其他", widget=text_input(placeholder="情緒/其他"), required=False)

    r6_1 = forms.MultipleChoiceField(
        label="日常活動", required=False,
        widget=forms.CheckboxSelectMultiple, choices=(
            ("1", "看電視"), ("2", "閱讀"), ("3", "手工藝"), ("4", "室內肢體運動"),
            ("5", "室外肢體運動"), ("6", "靜態認知活動"), ("7", "棋類活動"), ("8", "音樂活動"),
            ("9", "家事參與"), ("10", "與他人聊天外出散步"), ("11", "外出購物"), ("12", "参與社交活動"),
            ("-1", "其他"), ))
    r6_1e = forms.CharField(label="日常活動/其他", widget=text_input(placeholder="情緒/其他"), required=False)
    r6_2 = forms.IntegerField(label="日課表活動/參與狀況", widget=select_input(choices=(
        ("0", "主動"), ("1", "被動"), ("3", "配合"), ("4", "須引導"), ("2", "反覆異常"), ("5", "拒絕"), )))

    r7_1 = forms.IntegerField(label="日課飲食", widget=forms.RadioSelect(choices=(
        ("1", "早餐"), ("2", "中餐"), ("3", "晚餐"), )))
    r7_2 = forms.CharField(label="菜單", widget=text_input(placeholder="菜單"))
    r7_3 = forms.IntegerField(label="食慾", widget=forms.RadioSelect(choices=(
        ("0", "佳"), ("1", "普通"), ("2", "差"), )))
    r7_4 = forms.IntegerField(label="途徑", widget=select_input(choices=(
        ("自行由口進食", (("11", "普通"), ("12", "軟食"), ("13", "細碎"), ("14", "半流質"), ("15", "流質"), )),
        ("需他人餵食", (("21", "普通"), ("22", "軟食"), ("23", "細碎"), ("24", "半流質"), ("25", "流質"), )),
        ("其他", (("31", "鼻胃管"), ("41", "胃造廔"), )),
    )))
    r7_5 = forms.IntegerField(label="小便", widget=select_input(choices=(((i, i) for i in range(30)))))
    r7_6 = forms.IntegerField(label="小便方式", widget=forms.RadioSelect(choices=(
        ("0", "自解"), ("1", "尿布/尿套/尿管"), )))
    r7_7 = forms.IntegerField(label="小便需求", widget=forms.RadioSelect(choices=(
        ("0", "可自行表達"), ("1", "須提醒"), ("2", "無法表達"), )))
    r7_8 = BooleanField(label="小便狀況", widget=boolean_radio("正常", "異常"))
    r7_8e = forms.CharField(label="小便狀況/其他", widget=text_input(placeholder="異常說明"), required=False)

    r7_9 = forms.IntegerField(label="大便", widget=select_input(choices=(((i, i) for i in range(15)))))
    r7_10 = forms.IntegerField(label="大便方式", widget=forms.RadioSelect(choices=(
        ("0", "自解"), ("1", "尿布/灌腸/造口"), )))
    r7_11 = forms.IntegerField(label="大便需求", widget=forms.RadioSelect(choices=(
        ("0", "可自行表達"), ("1", "須提醒"), ("2", "無法表達"), )))
    r7_12 = BooleanField(label="大便狀況", widget=boolean_radio("正常", "異常"))
    r7_12e = forms.CharField(label="大便狀況/其他", widget=text_input(placeholder="異常說明"), required=False)

    r7_13 = forms.IntegerField(label="用藥狀況", widget=select_input(choices=(
        ("0", "無須服藥"), ("3", "配合服藥"), ("1", "逾時服藥"), ("2", "拒絕服藥"), ("5", "服藥後嘔吐 (無法補藥)"), )))

    r8_1 = forms.BooleanField(label="皮膚狀況/正常", required=False)

    r8_2 = forms.BooleanField(label="皮膚狀況/異常", required=False)
    r8_2e = forms.CharField(label="皮膚狀況/異常/部位", widget=text_input(placeholder="異常部位"), required=False)
    r8_2f = forms.IntegerField(label="皮膚狀況/異常/說明", widget=forms.RadioSelect(choices=(
        ("0", "過度乾燥有皮屑"), ("1", "淤青"), ("2", "有疹子"), )), required=False)

    r8_3 = forms.BooleanField(label="皮膚狀況/傷口", required=False)
    r8_3e = forms.CharField(label="皮膚狀況/傷口/部位", widget=text_input(placeholder="傷口部位", short=True), required=False)
    r8_3s = forms.IntegerField(label="皮膚狀況/傷口/大小", widget=number_input(), required=False)
    r8_3l = forms.CharField(label="皮膚狀況/傷口/等級", widget=text_input(placeholder="傷口等級", short=True), required=False)

    r8_4 = forms.IntegerField(label="皮膚/異常狀況處理", widget=forms.RadioSelect(choices=(
        ("0", "傷口消毒上藥"), ("1", "觀察"), ("2", "就診"), )), required=False)

    r8_5 = forms.IntegerField(label="輔具使用", widget=select_input(choices=(
        ("0", "無"), ("1", "甜甜圈墊"), ("2", "氣墊床"), ("-1", "其他"), )))
    r8_5e = forms.CharField(label="輔具使用/其他", widget=text_input(placeholder="說明"), required=False)

    r9_1 = forms.IntegerField(label="異常狀態", widget=select_input(choices=(
        ("0", "無"), ("1", "身體不適"), ("2", "情緒不穩"), ("3", "攻擊行為"), ("4", "拒絕配合"), ("-1", "其他"), )))
    r9_1e = forms.CharField(label="異常狀態/其他", widget=text_input(placeholder="說明"), required=False)
