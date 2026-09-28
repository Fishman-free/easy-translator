# -*- coding: utf-8 -*-
"""特称表：全大写缩写／机构名／期刊会议／领域专名（内置，不联网秒出）。

为什么单独一张表：有道词典和 3B 视觉模型对「IEEE」「IBM」这类全大写缩写
经常给不出准确释义，甚至按普通单词乱猜（IEEE → 猜成 name？）；而这类词在
论文／教材里含义是固定的，用表既准又快，还省一次联网／推理。

命中规则（避免误伤普通词）：
  * 全大写缩写（TERMS_UPPER）：**仅当原文就是全大写**才命中 —— 这样
    「it」不会被当成 IT、「cv」不会被当成 CV；「IT」「CV」才会命中。
  * 规范写法（TERMS_EXACT）：大小写严格匹配，用于 arXiv / PyTorch / Adam /
    ReLU / iid 这类有固定拼写的词。

每项 = (中文, 全称, 补充说明)，全称／说明留空则那行不显示。
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# 全大写缩写：只在原文全大写时命中
# --------------------------------------------------------------------------
TERMS_UPPER = {
    # —— 学术组织 / 标准机构 ——
    "IEEE": ("美国电气与电子工程师协会", "Institute of Electrical and Electronics Engineers",
             "全球最大的工程技术学会，主办 TPAMI、TNNLS 等期刊与大量会议"),
    "ACM": ("美国计算机协会", "Association for Computing Machinery",
            "主办 KDD、SIGIR、SIGCOMM 等会议，另有 ACM 数字图书馆"),
    "SIAM": ("美国工业与应用数学学会", "Society for Industrial and Applied Mathematics",
             "数值计算 / 应用数学的期刊与会议主办方"),
    "ISO": ("国际标准化组织", "International Organization for Standardization", ""),
    "IEC": ("国际电工委员会", "International Electrotechnical Commission",
            "常与 ISO 联合发布标准（如 ISO/IEC 27001）"),
    "ITU": ("国际电信联盟", "International Telecommunication Union",
            "联合国机构，负责无线电频谱分配与电信标准"),
    "ANSI": ("美国国家标准学会", "American National Standards Institute", ""),
    "NIST": ("美国国家标准与技术研究院", "National Institute of Standards and Technology",
             "发布测量 / 密码 / 材料标准，论文常引用其数据库"),
    "NSF": ("美国国家科学基金会", "National Science Foundation", "基础研究主要资助机构之一"),
    "DARPA": ("美国国防高级研究计划局", "Defense Advanced Research Projects Agency",
              "互联网、GPS 与 Transformer 早期研究的资助方"),
    "NASA": ("美国国家航空航天局", "National Aeronautics and Space Administration", ""),
    "ESA": ("欧洲空间局", "European Space Agency", ""),
    "CERN": ("欧洲核子研究组织", "Conseil Européen pour la Recherche Nucléaire",
             "欧洲核子研究中心：大型强子对撞机 LHC 与万维网的诞生地"),
    "IUPAC": ("国际纯粹与应用化学联合会", "International Union of Pure and Applied Chemistry",
              "负责化学命名法与原子量标准"),
    "APS": ("美国物理学会", "American Physical Society", "主办 Physical Review 系列期刊"),
    "ACS": ("美国化学会", "American Chemical Society", "主办 JACS 等期刊"),
    "RSC": ("英国皇家化学会", "Royal Society of Chemistry", ""),
    "AAAS": ("美国科学促进会", "American Association for the Advancement of Science",
             "出版《Science》"),
    "NIH": ("美国国立卫生研究院", "National Institutes of Health", "生物医学主要资助机构"),

    # —— 出版社 / 期刊 / 会议 ——
    "DOI": ("数字对象唯一标识符", "Digital Object Identifier", "论文的永久链接编号，形如 10.1109/xxx"),
    "ISBN": ("国际标准书号", "International Standard Book Number", ""),
    "ISSN": ("国际标准连续出版物号", "International Standard Serial Number", "期刊 / 连续出版物的编号"),
    "JMLR": ("机器学习研究杂志", "Journal of Machine Learning Research", "机器学习领域老牌开放获取期刊"),
    "TPAMI": ("IEEE 模式分析与机器智能汇刊", "IEEE Transactions on Pattern Analysis and Machine Intelligence",
              "计算机视觉 / 模式识别最权威期刊之一"),

    "ICML": ("国际机器学习大会", "International Conference on Machine Learning", "机器学习三大顶会之一"),
    "ICLR": ("国际学习表征会议", "International Conference on Learning Representations",
             "机器学习三大顶会之一，开放评审"),
    "CVPR": ("计算机视觉与模式识别大会", "Conference on Computer Vision and Pattern Recognition",
             "计算机视觉顶会（CCF-A）"),
    "ICCV": ("国际计算机视觉大会", "International Conference on Computer Vision", "两年一届的视觉顶会"),
    "ECCV": ("欧洲计算机视觉会议", "European Conference on Computer Vision", "两年一届的视觉顶会"),
    "AAAI": ("国际人工智能联合会议（美国人工智能协会主办）", "Association for the Advancement of Artificial Intelligence", ""),
    "IJCAI": ("国际人工智能联合会议", "International Joint Conference on Artificial Intelligence", ""),
    "ACL": ("国际计算语言学协会年会", "Annual Meeting of the Association for Computational Linguistics",
            "自然语言处理顶会"),
    "EMNLP": ("自然语言处理经验方法会议", "Conference on Empirical Methods in Natural Language Processing", ""),
    "NAACL": ("北美计算语言学协会年会", "North American Chapter of the ACL", ""),
    "KDD": ("知识发现与数据挖掘会议", "ACM SIGKDD Conference on Knowledge Discovery and Data Mining", ""),
    "SIGIR": ("信息检索特别兴趣组会议", "Special Interest Group on Information Retrieval", ""),
    "WWW": ("国际万维网大会", "The Web Conference", "常写作 WWW / TheWebConf"),
    "ICRA": ("国际机器人与自动化会议", "International Conference on Robotics and Automation", ""),
    "MICCAI": ("医学图像计算与计算机辅助介入会议", "Medical Image Computing and Computer Assisted Intervention", ""),

    "SOTA": ("当前最优", "state of the art", "论文里指「目前最好的结果 / 方法」"),

    # —— 公司与机构 ——
    "IBM": ("国际商业机器公司", "International Business Machines Corporation",
            "老牌科技公司；量子计算（Qiskit）、大型机、Watson"),
    "AMD": ("超威半导体", "Advanced Micro Devices", "CPU / GPU 厂商，与 Intel、NVIDIA 竞争"),
    "NVIDIA": ("英伟达", "", "GPU 与 CUDA 生态的厂商，AI 训练硬件主流供应商"),

    "TSMC": ("台积电", "Taiwan Semiconductor Manufacturing Company", "全球最大晶圆代工厂"),
    "ASML": ("阿斯麦", "Advanced Semiconductor Materials Lithography",
             "唯一能造 EUV 光刻机的厂商"),
    "ARM": ("安谋（Arm 架构）", "Advanced RISC Machines",
            "低功耗 CPU 指令集架构，手机与嵌入式主流"),

    # —— 软硬件 / 系统 ——
    "GPU": ("图形处理器", "Graphics Processing Unit", "并行计算主力，深度学习靠它训练"),
    "CPU": ("中央处理器", "Central Processing Unit", ""),
    "TPU": ("张量处理器", "Tensor Processing Unit", "Google 自研的 AI 加速芯片"),
    "NPU": ("神经网络处理器", "Neural Processing Unit", "手机 / 笔记本上的端侧 AI 加速单元"),
    "RAM": ("内存", "Random Access Memory", "与显存 VRAM 区分"),
    "VRAM": ("显存", "Video RAM", "显卡上的内存，决定能跑多大的模型 / 贴图"),
    "SSD": ("固态硬盘", "Solid State Drive", ""),
    "HDD": ("机械硬盘", "Hard Disk Drive", ""),

    "USB": ("通用串行总线", "Universal Serial Bus", ""),
    "HDMI": ("高清多媒体接口", "High-Definition Multimedia Interface", ""),
    "CUDA": ("统一计算设备架构", "Compute Unified Device Architecture", "NVIDIA 的 GPU 通用计算平台"),

    "API": ("应用程序接口", "Application Programming Interface", ""),
    "SDK": ("软件开发工具包", "Software Development Kit", ""),
    "IDE": ("集成开发环境", "Integrated Development Environment", ""),
    "CLI": ("命令行界面", "Command-Line Interface", ""),
    "GUI": ("图形用户界面", "Graphical User Interface", ""),
    "URL": ("统一资源定位符", "Uniform Resource Locator", "网址"),
    "HTTP": ("超文本传输协议", "Hypertext Transfer Protocol", ""),
    "HTTPS": ("HTTP 安全版", "HTTP Secure", ""),
    "JSON": ("JSON 数据格式", "JavaScript Object Notation", "键值对文本格式，接口常用"),
    "CSV": ("逗号分隔值", "Comma-Separated Values", "最简表格文本格式"),
    "SQL": ("结构化查询语言", "Structured Query Language", ""),
    "FLOPS": ("每秒浮点运算次数", "Floating-point Operations Per Second",
              "算力单位；注意 FLOPs（小写 s）指浮点运算总量"),
    "TOPS": ("每秒万亿次运算", "Tera Operations Per Second", "端侧 AI 算力常用单位"),

    # —— AI / 机器学习 ——
    "AI": ("人工智能", "Artificial Intelligence", ""),
    "ML": ("机器学习", "Machine Learning", ""),
    "DL": ("深度学习", "Deep Learning", ""),
    "NLP": ("自然语言处理", "Natural Language Processing", ""),
    "CV": ("① 计算机视觉　② 循环伏安法", "Computer Vision / Cyclic Voltammetry",
           "看领域：AI 论文里是计算机视觉，电化学论文里是循环伏安法"),
    "RL": ("强化学习", "Reinforcement Learning", ""),
    "LLM": ("大语言模型", "Large Language Model", ""),
    "SLM": ("小语言模型", "Small Language Model", "参数量小、可端侧部署的模型"),
    "AGI": ("通用人工智能", "Artificial General Intelligence", ""),
    "GAN": ("生成对抗网络", "Generative Adversarial Network", ""),
    "VAE": ("变分自编码器", "Variational Autoencoder", "损失里的 ELBO 由它而来"),
    "CNN": ("卷积神经网络", "Convolutional Neural Network", ""),
    "RNN": ("循环神经网络", "Recurrent Neural Network", ""),
    "LSTM": ("长短期记忆网络", "Long Short-Term Memory", "RNN 的改进结构，缓解梯度消失"),
    "GRU": ("门控循环单元", "Gated Recurrent Unit", "LSTM 的简化版"),
    "MLP": ("多层感知机", "Multi-Layer Perceptron", "最基础的前馈网络"),
    "FFN": ("前馈网络", "Feed-Forward Network", "Transformer 里注意力之后的子层"),
    "SVM": ("支持向量机", "Support Vector Machine", ""),
    "GP": ("① 高斯过程　② 图形处理器？", "Gaussian Process",
           "统计学习里的高斯过程；显存相关语境另见 GPU"),
    "PCA": ("主成分分析", "Principal Component Analysis", "降维"),
    "SVD": ("奇异值分解", "Singular Value Decomposition", "矩阵分解"),
    "GMM": ("高斯混合模型", "Gaussian Mixture Model", ""),
    "HMM": ("隐马尔可夫模型", "Hidden Markov Model", ""),
    "MCMC": ("马尔可夫链蒙特卡洛", "Markov Chain Monte Carlo", "贝叶斯推断的采样方法"),
    "ELBO": ("证据下界", "Evidence Lower Bound", "变分推断的优化目标"),
    "KL": ("KL 散度", "Kullback-Leibler divergence", "衡量两个分布的差异"),
    "MLE": ("最大似然估计", "Maximum Likelihood Estimation", ""),
    "MAP": ("最大后验估计", "Maximum A Posteriori", "MLE 加先验；也指平均精度均值（mAP）"),
    "SGD": ("随机梯度下降", "Stochastic Gradient Descent", ""),

    "BN": ("批归一化", "Batch Normalization", "也可是氮化硼 BN"),
    "LN": ("层归一化", "Layer Normalization", "Transformer 常用"),
    "RAG": ("检索增强生成", "Retrieval-Augmented Generation", "先检索再让模型生成"),

    "BLEU": ("BLEU 指标", "Bilingual Evaluation Understudy", "机器翻译评测指标"),
    "ROUGE": ("ROUGE 指标", "Recall-Oriented Understudy for Gisting Evaluation", "摘要评测指标"),
    "RMSE": ("均方根误差", "Root Mean Square Error", "回归常用；越小越好，单位同目标量"),
    "MAE": ("平均绝对误差", "Mean Absolute Error", ""),
    "MSE": ("均方误差", "Mean Squared Error", ""),
    "AUC": ("曲线下面积", "Area Under the Curve", "常配 ROC 曲线衡量分类器"),
    "ROC": ("受试者工作特征曲线", "Receiver Operating Characteristic", ""),
    "TPR": ("真阳性率 / 召回率", "True Positive Rate", ""),
    "FPR": ("假阳性率", "False Positive Rate", ""),
    "IID": ("独立同分布", "independent and identically distributed", "也常写作 iid"),
    "ODE": ("常微分方程", "Ordinary Differential Equation", ""),
    "PDE": ("偏微分方程", "Partial Differential Equation", ""),
    "SDE": ("随机微分方程", "Stochastic Differential Equation", "扩散模型的理论基础"),
    "PDF": ("① 概率密度函数　② 便携文档格式", "Probability Density Function / Portable Document Format",
            "数学语境是密度函数，文件语境是 PDF 文档"),

    # —— 电化学 / 电池（论文复现常用）——
    "SEI": ("固体电解质界面膜", "Solid Electrolyte Interphase",
            "电解液在负极表面分解形成的钝化膜，直接影响循环寿命"),
    "CEI": ("阴极电解质界面膜", "Cathode Electrolyte Interphase", "正极侧的对应界面膜"),
    "EIS": ("电化学阻抗谱", "Electrochemical Impedance Spectroscopy", ""),
    "LSV": ("线性扫描伏安法", "Linear Sweep Voltammetry", "常用来测氧化稳定性窗口"),
    "GCD": ("恒流充放电", "Galvanostatic Charge-Discharge", ""),
    "SOC": ("荷电状态", "State of Charge", "剩余电量百分比"),
    "SOH": ("健康状态", "State of Health", "电池老化程度"),
    "DOD": ("放电深度", "Depth of Discharge", ""),
    "NMC": ("镍钴锰三元正极", "Nickel Manganese Cobalt oxide", ""),
    "LFP": ("磷酸铁锂", "Lithium Iron Phosphate", "安全性好、循环长的正极材料"),
    "LCO": ("钴酸锂", "Lithium Cobalt Oxide", ""),
    "LMO": ("锰酸锂", "Lithium Manganese Oxide", ""),
    "NCA": ("镍钴铝正极", "Nickel Cobalt Aluminium oxide", ""),
    "EC": ("碳酸乙烯酯", "Ethylene Carbonate", "常用溶剂（欧洲委员会 European Commission 也简称 EC）"),
    "DMC": ("碳酸二甲酯", "Dimethyl Carbonate", "低黏度溶剂，常与 EC 混用"),
    "EMC": ("碳酸甲乙酯", "Ethyl Methyl Carbonate", ""),
    "DEC": ("碳酸二乙酯", "Diethyl Carbonate", ""),
    "FEC": ("氟代碳酸乙烯酯", "Fluoroethylene Carbonate", "常见成膜添加剂"),
    "VC": ("① 碳酸亚乙烯酯　② 风险投资", "Vinylene Carbonate / Venture Capital",
           "电化学论文里是成膜添加剂，商业语境里是风险投资"),
    "PVDF": ("聚偏氟乙烯", "Polyvinylidene Fluoride", "常用粘结剂"),
    "NMP": ("N-甲基吡咯烷酮", "N-Methyl-2-Pyrrolidone", "电极浆料常用溶剂"),
    "PEO": ("聚环氧乙烷", "Polyethylene Oxide", "聚合物电解质常用基体"),
    "LLZO": ("锂镧锆氧", "Li7La3Zr2O12", "石榴石型固态电解质"),
    "LATP": ("磷酸铝钛锂", "Li1.3Al0.3Ti1.7(PO4)3", "NASICON 型固态电解质"),
    "ASSB": ("全固态电池", "All-Solid-State Battery", ""),
    "LIB": ("锂离子电池", "Lithium-Ion Battery", ""),
    "SIB": ("钠离子电池", "Sodium-Ion Battery", ""),
    "XRD": ("X 射线衍射", "X-Ray Diffraction", "测晶体结构"),
    "XPS": ("X 射线光电子能谱", "X-ray Photoelectron Spectroscopy", "测表面元素与价态"),
    "SEM": ("扫描电子显微镜", "Scanning Electron Microscopy", ""),
    "TEM": ("透射电子显微镜", "Transmission Electron Microscopy", ""),
    "NMR": ("核磁共振", "Nuclear Magnetic Resonance", "测分子结构 / 离子迁移"),
    "DFT": ("密度泛函理论", "Density Functional Theory", "第一性原理计算"),
    "AIMD": ("从头算分子动力学", "Ab Initio Molecular Dynamics", ""),
    "MD": ("分子动力学", "Molecular Dynamics", "也可是 Markdown 文件后缀 / 医学博士"),
    "RDF": ("径向分布函数", "Radial Distribution Function", ""),
    "DOS": ("① 态密度　② 磁盘操作系统", "Density of States / Disk Operating System",
            "材料计算里是态密度，老系统语境里是 DOS"),
    "PBE": ("PBE 泛函", "Perdew-Burke-Ernzerhof", "DFT 常用交换关联泛函"),
    "VASP": ("VASP 计算软件", "Vienna Ab initio Simulation Package", "主流第一性原理计算软件"),

    # —— 计算机体系结构 / 浮点数（IEEE 754 等课程常客）——
    "ULP": ("最小精度单位", "Unit in the Last Place", "衡量浮点误差与舍入误差的尺度"),
    "FPU": ("浮点运算单元", "Floating-Point Unit", "CPU 里专门算浮点的部件"),
    "ALU": ("算术逻辑单元", "Arithmetic Logic Unit", "CPU 的基本运算部件"),
    "FMA": ("融合乘加", "Fused Multiply-Add", "a×b+c 一次算完，只舍入一次"),
    "SIMD": ("单指令多数据", "Single Instruction Multiple Data", "一条指令并行处理多份数据"),
    "MIMD": ("多指令多数据", "Multiple Instruction Multiple Data", "多核并行的体系结构类别"),
}

# --------------------------------------------------------------------------
# 规范写法：大小写严格匹配（这些词有固定拼写，不能按全大写处理）
# --------------------------------------------------------------------------
TERMS_EXACT = {
    "arXiv": ("预印本平台", "arXiv.org", "康奈尔大学运营的开放预印本库，编号形如 arXiv:2401.12345"),
    "PyTorch": ("PyTorch 框架", "", "Meta 开源的深度学习框架，动态图"),
    "TensorFlow": ("TensorFlow 框架", "", "Google 开源的深度学习框架"),
    "JAX": ("JAX 框架", "", "Google 的函数式数值计算 / 自动微分库"),
    "NumPy": ("NumPy 库", "", "Python 数值计算基础库，ndarray"),
    "SciPy": ("SciPy 库", "", "NumPy 之上的科学计算库"),
    "scikit-learn": ("scikit-learn 库", "", "经典机器学习工具库，简写 sklearn"),
    "pandas": ("pandas 库", "", "Python 表格数据处理库"),
    "matplotlib": ("matplotlib 库", "", "Python 绑图库"),
    "Colab": ("Colab 云端 Notebook", "Google Colaboratory", "免费 GPU 的在线 Jupyter 环境"),
    "Adam": ("Adam 优化器", "Adaptive Moment Estimation", "Kingma & Ba 2014；也作人名"),
    "ReLU": ("ReLU 激活函数", "Rectified Linear Unit", "max(0, x)"),
    "GELU": ("GELU 激活函数", "Gaussian Error Linear Unit", "Transformer 常用激活"),
    "Softmax": ("Softmax 函数", "", "把实数向量变成概率分布"),
    "iid": ("独立同分布", "independent and identically distributed", "样本假设；大写写作 IID"),
    "NeurIPS": ("神经信息处理系统大会", "Conference on Neural Information Processing Systems",
                "机器学习三大顶会之一（NIPS）"),
    "Intel": ("英特尔", "", "CPU 厂商"),
    "OpenAI": ("OpenAI", "", "GPT 系列与 ChatGPT 的开发机构"),
    "DeepMind": ("DeepMind", "", "Google 旗下 AI 研究机构，AlphaGo / AlphaFold"),
    "Anthropic": ("Anthropic", "", "Claude 系列模型的开发机构"),
    "HuggingFace": ("Hugging Face", "", "开源模型 / 数据集社区与 Transformers 库"),
    "Kaggle": ("Kaggle", "", "数据科学竞赛平台，后被 Google 收购"),
    "NVMe": ("NVMe 协议", "Non-Volatile Memory Express", "走 PCIe 的高速固态协议"),
    "PCIe": ("PCI Express 总线", "Peripheral Component Interconnect Express", ""),
    "ROCm": ("ROCm", "Radeon Open Compute", "AMD 的 GPU 计算平台，对标 CUDA"),
    "OpenCL": ("开放计算语言", "Open Computing Language", "跨厂商的异构计算标准"),
    "Docker": ("Docker 容器", "", "把环境打包成镜像，论文复现常用"),
    "LoRA": ("低秩适配", "Low-Rank Adaptation", "微调大模型时只训练少量低秩矩阵"),
    "RoPE": ("旋转位置编码", "Rotary Position Embedding", "现代 LLM 常用的位置编码"),
    "Microsoft": ("微软", "", "Windows / Office / Azure / VS Code；论文里常见其研究院 MSRA"),
    "Google": ("谷歌", "", "搜索 / Android / TensorFlow / TPU；论文里常见 Google Brain、Google Research"),
    "Meta": ("Meta（原 Facebook）", "", "PyTorch 与 LLaMA 系列模型的开发方"),
    "Apple": ("苹果", "", "Apple Silicon（M 系列芯片）与端侧模型研究"),
    "Amazon": ("亚马逊", "", "AWS 云计算 / Alexa；论文里常见 Amazon Science"),

    # —— 浮点数（IEEE 754 课程常客；Fraction/Exponent/Bias 属普通词，交给词典，不收进表）——
    "Mantissa": ("尾数（有效数字段）", "mantissa / significand",
                 "IEEE 754 里除符号位与指数位之外的尾数字段；也指对数的尾数"),
    "Significand": ("有效数字段", "significand", "与 mantissa 同义，很多教材更偏好这个词"),
    "Denormal": ("非规格化数", "denormal / denormalized number",
                 "指数位全 0 时的浮动小数，表示比最小规格化数更小的值"),
    "Subnormal": ("次规格化数", "subnormal number", "与 denormal 同义（IEEE 754-2008 起的叫法）"),

    # —— 论文里的规范拼写（不是全大写，必须精确匹配）——
    "NaN": ("非数（NaN）", "Not a Number", "IEEE 754 里表示无效运算结果，如 0/0"),
    "LiTFSI": ("双三氟甲磺酰亚胺锂", "Lithium bis(trifluoromethanesulfonyl)imide", "常用锂盐"),
    "LiFSI": ("双氟磺酰亚胺锂", "Lithium bis(fluorosulfonyl)imide", ""),

}

def lookup_term(s: str):
    """特称 → 卡片结构（与 lookup_greek 同形）；未命中返回 None。"""
    t = (s or "").strip().strip(".,;:()[]{}\"'")
    if not t:
        return None
    hit = TERMS_EXACT.get(t)                    # 规范写法：大小写敏感
    if not hit and t.isupper():                 # 全大写缩写：仅全大写才命中，避免 it→IT
        hit = TERMS_UPPER.get(t) or TERMS_UPPER.get(t.replace("-", ""))
    if not hit:
        return None
    zh, full, note = hit
    poses = []
    if full:
        poses.append({"pos": "全称", "meaning": full})
    if note:
        poses.append({"pos": "说明", "meaning": note})
    if not poses:
        poses.append({"pos": "说明", "meaning": zh})
    # 中文名与词本身相同时（OpenAI、DeepMind 这类）不要重复显示成「OpenAI　OpenAI」
    title = t if zh.strip().lower() == t.lower() else "%s　%s" % (t, zh)
    return {
        "word": title,
        "phonetics": {"uk": "", "us": ""},
        "poses": poses,
        "examples": [],
        "source": "特称表（内置）",
    }

def is_term(s: str) -> bool:
    """是否命中特称表（供 textgrab 判定用）。"""
    return lookup_term(s) is not None
