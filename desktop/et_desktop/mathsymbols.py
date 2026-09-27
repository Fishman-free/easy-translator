# -*- coding: utf-8 -*-
"""数学符号表：希腊字母、数学变体字母（花体/双线体/哥特体/粗斜体）、单字母变量。

论文（尤其概率论/机器学习）里遇到的非英文符号都在这里查：
  α Ω λ        → 字母名 + 音标 + 中文读法 + 常见含义
  ℒ ℱ ℬ ℝ 𝔼 𝒩  → 变体样式 + 基字母 + 常见含义（靠 Unicode 名称自动识别，不硬编码码点）
  F X n b      → 单字母数学变量（图片里大小写常分不清，卡片会把花体大写含义一并给出）

全部内置、不联网。新增符号只动这个文件。
"""
from __future__ import annotations

import unicodedata as _ud


# —— 希腊字母表（论文常见）：字母 → (英文名, 音标, 中文读法, 常见含义) ——
GREEK = {
    "α": ("alpha", "ˈælfə", "阿尔法", "学习率、角度、系数、显著性水平"),
    "β": ("beta", "ˈbiːtə", "贝塔", "回归系数、β 分布、动量"),
    "γ": ("gamma", "ˈɡæmə", "伽马", "折扣因子、正则系数、伽马分布"),
    "δ": ("delta", "ˈdeltə", "德尔塔", "增量、误差项、克罗内克 δ"),
    "ε": ("epsilon", "ˈepsɪlɒn", "艾普西龙", "极小量、探索率（ε-greedy）"),
    "ζ": ("zeta", "ˈziːtə", "泽塔", "阻尼比、ζ 函数"),
    "η": ("eta", "ˈiːtə", "伊塔", "学习率、效率、黏度"),
    "θ": ("theta", "ˈθiːtə", "西塔", "模型参数、夹角"),
    "ι": ("iota", "aɪˈoʊtə", "约塔", "极少用；编程里指 iota（连续整数）"),
    "κ": ("kappa", "ˈkæpə", "卡帕", "条件数、曲率、κ 系数"),
    "λ": ("lambda", "ˈlæmdə", "兰姆达", "正则化系数、特征值、到达率"),
    "μ": ("mu", "mjuː", "缪", "均值、微（10⁻⁶）、动量系数"),
    "ν": ("nu", "njuː", "纽", "自由度、频率、中微子"),
    "ξ": ("xi", "zaɪ", "克西", "随机变量、自变量"),
    "ο": ("omicron", "ˈɒmɪkrɒn", "奥密克戎", "极少用（易与 o 混淆）"),
    "π": ("pi", "paɪ", "派", "圆周率、策略（策略 π）、连乘"),
    "ρ": ("rho", "roʊ", "柔", "相关系数、密度、学习率衰减"),
    "σ": ("sigma", "ˈsɪɡmə", "西格玛", "标准差、Sigmoid、求和、噪声"),
    "τ": ("tau", "taʊ", "陶", "温度/τ 参数、时间常数"),
    "υ": ("upsilon", "ˈjuːpsɪlɒn", "宇普西龙", "极少用"),
    "φ": ("phi", "faɪ", "斐", "映射/特征函数、势函数"),
    "χ": ("chi", "kaɪ", "凯", "卡方分布、χ² 检验"),
    "ψ": ("psi", "saɪ", "普西", "波函数、势"),
    "ω": ("omega", "ˈoʊmɪɡə", "欧米伽", "权重、角频率、非零元素位置"),
}
GREEK_UPPER = set("ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ")

# —— 数学变体字母（论文里的花体/双线体/哥特体/粗斜体）：靠 Unicode 名称自动识别，
#    不硬编码几百个码点。名称形如 "MATHEMATICAL SCRIPT CAPITAL A" / "DOUBLE-STRUCK CAPITAL R"。 ——

VARIANT_STYLE = {
    "BOLD SCRIPT": "粗花体",
    "SCRIPT": "花体",
    "BOLD FRAKTUR": "粗哥特体",
    "FRAKTUR": "哥特体",
    "BLACK-LETTER": "哥特体",
    "BOLD DOUBLE-STRUCK": "粗双线体",
    "DOUBLE-STRUCK": "双线体",
    "SANS-SERIF BOLD ITALIC": "无衬线粗斜体",
    "SANS-SERIF BOLD": "无衬线粗体",
    "SANS-SERIF ITALIC": "无衬线斜体",
    "SANS-SERIF": "无衬线",
    "BOLD ITALIC": "粗斜体",
    "BOLD": "粗体",
    "ITALIC": "斜体",
}
GREEK_NAME2CH = {
    "ALPHA": "α", "BETA": "β", "GAMMA": "γ", "DELTA": "δ", "EPSILON": "ε", "ZETA": "ζ",
    "ETA": "η", "THETA": "θ", "IOTA": "ι", "KAPPA": "κ", "LAMDA": "λ", "LAMBDA": "λ",
    "MU": "μ", "NU": "ν", "XI": "ξ", "OMICRON": "ο", "PI": "π", "RHO": "ρ", "SIGMA": "σ",
    "TAU": "τ", "UPSILON": "υ", "PHI": "φ", "CHI": "χ", "PSI": "ψ", "OMEGA": "ω",
}
# 论文里最常见的变体含义（按 基字母 + 样式）
VARIANT_NOTES = {
    ("L", "花体"): "损失函数 Loss（论文里最常出现的花体字母）",
    ("N", "花体"): "正态分布 𝒩(μ, σ²)；也常指神经网络",
    ("D", "花体"): "数据集 Dataset",
    ("X", "花体"): "输入空间 / 样本空间",
    ("Y", "花体"): "输出空间 / 标签空间",
    ("B", "花体"): "博雷尔集 ℬ（Borel σ-代数，概率论里 (ℝ, ℬ) 的那个 ℬ）；也作 Batch 批量、Basis 基",
    ("F", "花体"): "事件域 ℱ（σ-代数，概率论里 (Ω, ℱ, P) 的那个 ℱ）；也指傅里叶变换、函数空间",
    ("R", "双线体"): "实数集 ℝ",
    ("N", "双线体"): "自然数集 ℕ",
    ("Z", "双线体"): "整数集 ℤ",
    ("Q", "双线体"): "有理数集 ℚ",
    ("C", "双线体"): "复数集 ℂ",
    ("E", "双线体"): "期望 𝔼[X]（Expected value）",
    ("P", "双线体"): "概率 ℙ(·)（Probability）",
    ("I", "双线体"): "指示函数 𝟙（Indicator）",
    ("F", "双线体"): "有限域 𝔽、特征",
    ("1", "双线体"): "指示函数 𝟙[条件]（Indicator，条件成立取 1 否则 0）",
    ("0", "双线体"): "零向量 / 全零矩阵",
}


def variant_info(ch):
    """数学变体字母 → (样式中文, 基字母/希腊名, 是否希腊)；不是变体返回 None。"""
    if not isinstance(ch, str) or len(ch) != 1:
        return None
    try:
        name = _ud.name(ch)
    except ValueError:
        return None
    if name.startswith("MATHEMATICAL "):
        rest = name[len("MATHEMATICAL "):]
    elif name.startswith(("SCRIPT ", "DOUBLE-STRUCK ", "BLACK-LETTER ")):
        rest = name
    else:
        return None
    for style in sorted(VARIANT_STYLE, key=len, reverse=True):
        if rest.startswith(style + " "):
            target = rest[len(style) + 1:]
            parts = target.split(" ", 1)
            if len(parts) != 2 or parts[0] not in ("CAPITAL", "SMALL", "DIGIT"):
                return None
            base = parts[1].upper()
            if base in GREEK_NAME2CH:
                return VARIANT_STYLE[style], GREEK_NAME2CH[base], True
            if parts[0] == "DIGIT":
                digit = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4",
                         "FIVE": "5", "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9"}.get(base)
                return (VARIANT_STYLE[style], digit, False) if digit else None
            if len(base) == 1 and base.isalpha():
                return VARIANT_STYLE[style], base, False
            return None
    return None


def is_variant_letter(ch) -> bool:
    """是不是数学变体字母（花体/双线体/哥特体/粗斜体…）。"""
    return variant_info(ch) is not None


def is_letter_like(ch) -> bool:
    """可查的「字母」：普通希腊字母或数学变体字母。"""
    return is_greek_letter(ch) or is_variant_letter(ch)


# —— 单个拉丁字母在数学/论文里的常见含义（图片/PDF 里单字母极常见）——
MATH_LETTER = {
    "F": "函数、力、事件域 ℱ（σ-代数）",
    "L": "损失函数 ℒ、长度、拉格朗日量",
    "N": "样本数、正态分布 𝒩、神经网络",
    "D": "数据集 𝒟、维度、距离",
    "X": "随机变量、输入、设计矩阵",
    "Y": "输出、标签、因变量",
    "Z": "标准化变量、配分函数、整数集 ℤ",
    "R": "半径、实数集 ℝ、奖励",
    "M": "矩阵、模型、均值",
    "P": "概率 P(·)、概率分布 ℙ",
    "Q": "分布 Q、函数 Q(s,a)、有理数集 ℚ",
    "E": "期望 𝔼、误差、能量",
    "V": "方差、体积、价值函数",
    "W": "权重矩阵、参数",
    "A": "矩阵 A、动作空间、面积",
    "B": "矩阵 B、批量大小、偏差",
    "C": "常数、代价、复数集 ℂ",
    "K": "类别数、核函数、K 近邻",
    "S": "集合、状态空间、样本空间",
    "T": "转置 ᵀ、时间步、温度",
    "U": "均匀分布、并集、效用",
    "G": "生成器、图、梯度",
    "H": "熵、隐状态、假设空间 ℋ",
    "I": "单位矩阵、指示函数、信息量",
    "J": "损失 J、雅可比矩阵",
    "O": "复杂度 O(·)、大 O 记号",
    "i": "下标序号、虚数单位",
    "j": "下标序号",
    "k": "下标序号、类别数",
    "n": "样本量、维度",
    "m": "样本量、维数",
    "t": "时间步、迭代次数",
    "x": "自变量、输入、某个元素",
    "y": "因变量、标签、真值",
    "z": "隐变量、中间变量",
    "w": "权重、参数",
    "b": "偏置 bias、截距",
    "d": "维度、距离、微分 d",
    "p": "概率、维度、参数个数",
    "q": "分布、概率",
    "s": "状态、秒",
    "a": "动作、标量、加速度",
    "e": "自然常数 e、误差项 ε 的简写",
    "f": "函数 f(·)、频率",
    "g": "函数 g(·)、梯度 g",
    "h": "步长、隐藏层、假设",
    "l": "层索引、损失 l",
    "r": "奖励、半径、学习率 η 的简写",
    "u": "输入、控制量",
    "v": "向量 v、速度",
}


# 单字母卡片里附带的「花体写法」提示：图片里常分不清大小写，索性都给出来
SCRIPT_MEANING = {
    "B": "博雷尔集 ℬ（Borel σ-代数）",
    "F": "事件域 ℱ（σ-代数）",
    "L": "损失函数 ℒ（Loss）",
    "N": "正态分布 𝒩(μ,σ²)；也指神经网络",
    "D": "数据集 𝒟（Dataset）",
    "X": "输入空间 𝒳",
    "Y": "输出空间 𝒴",
    "P": "幂集 𝒫；概率",
    "E": "期望 𝔼[X]；事件族 ℰ",
    "M": "矩阵集合 ℳ",
    "R": "实数集 ℝ；关系 ℛ",
    "A": "集合族 𝒜",
    "C": "集合族 𝒞",
    "S": "集合族 𝒮",
    "T": "变换 𝒯",
    "H": "假设空间 ℋ",
    "G": "图 𝒢",
    "U": "论域 𝒰",
}


SCRIPT_CHARS = {"F": "ℱ", "L": "ℒ", "M": "ℳ", "R": "ℛ", "N": "𝒩", "D": "𝒟", "X": "𝒳",
                "G": "𝒢", "H": "ℋ", "B": "ℬ", "E": "ℰ", "S": "𝒮", "T": "𝒯", "P": "𝒫",
                "A": "𝒜", "C": "𝒞", "U": "𝒰", "Y": "𝒴"}


def lookup_math_var(ch: str):
    """单个拉丁字母 → 数学变量卡片（图片/PDF 里最常见的情形）。"""
    if not isinstance(ch, str):
        return None
    t = ch.strip()
    if len(t) != 1 or not t.isascii() or not t.isalpha():
        return None
    up = t.upper()
    note = MATH_LETTER.get(t) or MATH_LETTER.get(up) or ""
    poses = [{"pos": "字母", "meaning": t}]
    if note:
        poses.append({"pos": "常见", "meaning": note})
    if up in SCRIPT_MEANING:
        # 图片里常分不清大小写：把花体大写的含义一并给出，避免「ℬ 被读成 b 就显示偏置」这类误导
        poses.append({"pos": "花体",
                      "meaning": f"若图上其实是花体大写 {SCRIPT_CHARS.get(up, up)}：{SCRIPT_MEANING[up]}"})
    return {
        "word": f"{t}",
        "phonetics": {"uk": "", "us": ""},
        "poses": poses,
        "examples": [],
        "source": "数学变量（内置）",
    }


def lookup_variant(ch: str):
    """数学变体字母 → 样式 + 基字母读数 + 常见含义（内置，不联网）。"""
    info = variant_info(ch)
    if not info:
        return None
    style, base, is_gr = info
    if is_gr:
        name, ipa, zh, use = GREEK[base]
        return {
            "word": f"{ch}　{style} {name}",
            "phonetics": {"uk": f"/{ipa}/", "us": f"/{ipa}/"},
            "poses": [
                {"pos": "读法", "meaning": f"{zh}（{style} {name}）"},
                {"pos": "常见", "meaning": use},
            ],
            "examples": [],
            "source": f"希腊字母表（内置 · {style}）",
        }
    note = VARIANT_NOTES.get((base, style), "")
    poses = [{"pos": "读法", "meaning": f"{style} {base}（读作 {base}）"}]
    if note:
        poses.append({"pos": "常见", "meaning": note})
    return {
        "word": f"{ch}　{style} {base}",
        "phonetics": {"uk": "", "us": ""},
        "poses": poses,
        "examples": [],
        "source": f"数学符号表（内置 · {style}）",
    }


def is_greek_letter(s) -> bool:
    """是不是单个希腊字母（含大写形式）。"""
    if not isinstance(s, str):
        return False
    t = s.strip()
    return len(t) == 1 and (t.lower() in GREEK)


def lookup_greek(s: str):
    """希腊字母 → 名称/音标/中文读法/论文常见含义（内置，不联网）。"""
    t = (s or "").strip()
    if not is_greek_letter(t):
        return None
    upper = t in GREEK_UPPER
    name, ipa, zh, use = GREEK[t.lower()]
    disp = name.capitalize() if upper else name
    return {
        "word": f"{t}　{disp}",
        "phonetics": {"uk": f"/{ipa}/", "us": f"/{ipa}/"},
        "poses": [
            {"pos": "读法", "meaning": f"{zh}（{'大写 ' if upper else ''}{disp}）"},
            {"pos": "常见", "meaning": use},
        ],
        "examples": [],
        "source": "希腊字母表（内置）",
    }
