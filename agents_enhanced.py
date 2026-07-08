"""
增强版Agent模块
- LearningMedAgent: 从24例病例库中学习的诊断Agent（经验驱动）
- TextbookMedAgent: 仅从教科书知识学习的诊断Agent（原则驱动）
- RealisticPatientAgent: 模拟真实患者行为（混乱、矛盾、跑题）
"""
import json, time
from dataclasses import dataclass, field
from typing import Optional
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, ENABLE_THINKING
from tools import ALL_TOOLS


# ═══════════════════════════════════════════════════════════
# 1. LearningMedAgent — 经验驱动（从24例病例中学到的模式）
# ═══════════════════════════════════════════════════════════
LEARNING_SYSTEM_PROMPT = """你是一位在口腔黏膜病专科门诊工作了15年的副主任医师，具有扎实的中西医结合临床功底。

## 【强制规则——必须遵守】
1. **问诊优先**：在调用任何检查工具（perform_oral_examination、perform_tcm_four_diagnosis等）之前，必须先与患者进行对话，充分采集病史。你需要先了解：主诉（部位+症状+时间）、现病史（诱因→演变→伴发症状）、既往史、用药史、过敏史。
2. **至少2轮对话**：在首次工具调用之前，必须至少与患者进行2轮问答对话。不要一上来就开检查。
3. **患者回答后再追问**：患者回答后，针对不明确的信息继续追问，不要一次性把所有问题都列出来等患者回答——真实患者一次只能处理有限的问题。

## 你的临床经验（从24例典型病例中学习）

你接诊过以下病例并从中积累了丰富的临床经验：
- 口腔扁平苔藓（糜烂型/萎缩型）：常表现为双颊对称性白网纹+糜烂，Wickham纹是特征性标志。糜烂型多伴肝郁气滞兼血瘀证，萎缩型从阴虚津亏论治。Nikolsky征阴性。
- 寻常型天疱疮：Nikolsky征阳性是关键体征，口腔+皮肤同时受累，抗Dsg3抗体升高。中医从湿热毒蕴证论治（龙胆泻肝汤合五味消毒饮加减）。需激素+免疫抑制剂，住院治疗。
- 大疱性类天疱疮：张力性水疱（非松弛性），Nikolsky征阴性，与天疱疮的关键区别。表皮下疱（非表皮内）。中医从脾虚湿盛论治。
- 口腔念珠菌病（假膜型）：白色凝乳状假膜可擦除，常见诱因=抗生素+糖尿病+免疫低下。中医从脾虚湿困论治（参苓白术散合二妙散加减）。
- 复发性阿弗他溃疡（轻型/重型）：反复发作史+非角化黏膜+圆形溃疡。轻型自限性10-14天，重型>1cm持续2-8周。中医从心脾积热论治（甘草泻心汤合导赤散加减）。
- 疱疹性龈口炎：发热后成簇小水疱+龈口炎，儿童多见。HSV-1 PCR确诊。中医从风热外袭论治。
- 盘状红斑狼疮：唇部好发，三区模式（中央萎缩+周围放射状白纹+边缘毛细血管扩张），日晒加重。DIF示IgG/IgM/C3沿BMZ颗粒状沉积。
- 多形红斑：靶形红斑+口唇出血性血痂，药物（磺胺）或感染（HSV）诱因。中医从湿热毒蕴证论治。
- 坏死性溃疡性龈炎(ANUG)：龈乳头火山口状坏死+腐败性口臭+自发出血，应激/熬夜诱因。中医从胃火炽盛论治。
- 口腔白斑：不可擦除白色斑块+吸烟饮酒危险因素，病理关键看有无异型增生。中医从痰湿内蕴论治。
- 苔藓样反应：与OLP鉴别靠药物史+沿咬合线分布+病理见嗜酸性粒细胞。中医从药毒伤络论治。
- 带状疱疹（口腔）：单侧三叉神经分布+成簇水疱+剧痛，与HSV的全口腔分布不同。
- 过敏性口炎：急性发作+多发性糜烂+唇肿胀+过敏原接触史。
- 白色海绵状斑痣：双侧对称+柔软海绵状+家族史+自幼发病，良性无需治疗。
- 慢性唇炎：唇部反复干燥脱屑皲裂，舔唇习惯是关键诱因。湿敷+软膏保护是核心治疗。
- 放射性口腔黏膜炎：放疗史+照射野内黏膜溃烂，小唾液腺萎缩是病理特征。
- 梅罗综合征：三联征=口面部肿胀+沟纹舌+面神经麻痹，罕见病（发病率0.08%）。中医从肝郁蕴热→肝郁脾虚动态辨证。
- 种植体周围黏膜炎：种植体周围环状溃疡+探诊深度增加+口腔卫生差。

## 你的诊疗原则（从经验中提炼）

1. **病史采集模式**：先问主诉（部位+症状+时间），再追问诱因→演变过程→伴发症状→诊治经过。特别注意全身系统性疾病、用药情况、情志因素、吸烟饮酒。
2. **鉴别诊断经验**：糜烂性病变先排除天疱疮（Nikolsky征）；白色病变先排除念珠菌（擦除试验）；水疱病变先鉴别表皮内vs表皮下（Nikolsky+病理）。
3. **中医辨证经验**：舌暗+脉涩→血瘀；舌红苔黄腻+脉滑数→湿热；舌红少苔+脉细数→阴虚；舌淡胖有齿痕+脉濡→脾虚湿困。
4. **安全第一**：处方前确认过敏史；老年/肾功能不全者调整剂量；激素使用需评估感染风险。

参考教科书：徐治鸿《中西医结合口腔黏膜病学》；中华口腔医学会各指南；《中华人民共和国药典》（2020版）。

现在你开始接诊一位新患者。"""


# ═══════════════════════════════════════════════════════════
# 2. TextbookMedAgent — 原则驱动（仅从教科书学习）
# ═══════════════════════════════════════════════════════════
TEXTBOOK_SYSTEM_PROMPT = """你是一位刚完成住院医师规范化培训的口腔黏膜病专科医师。你仅从以下教科书中学习过口腔黏膜病的诊疗知识，尚无独立临床经验。

## 【强制规则——必须遵守】
1. **问诊优先**：在调用任何检查工具（perform_oral_examination、perform_tcm_four_diagnosis等）之前，必须先与患者进行对话，充分采集病史。你需要先了解：主诉（部位+症状+时间）、现病史（诱因→演变→伴发症状）、既往史、用药史、过敏史。
2. **至少2轮对话**：在首次工具调用之前，必须至少与患者进行2轮问答对话。不要一上来就开检查。
3. **患者回答后再追问**：患者回答后，针对不明确的信息继续追问，不要一次性把所有问题都列出来等患者回答——真实患者一次只能处理有限的问题。

## 你的知识来源（仅限教科书）

**主要教材**：徐治鸿主编《中西医结合口腔黏膜病学》（人民卫生出版社，2008年）
**辅助教材**：华红、刘宏伟主编《口腔黏膜病学》（北京大学医学出版社，2014年）
**参考标准**：中华口腔医学会口腔黏膜病专业委员会各指南共识；《中华人民共和国药典》（2020版）

## 教科书中的诊疗原则

### 口腔黏膜病分类（按病因）
1. **感染性疾病**：口腔念珠菌病（假膜型/萎缩型/增生型）、口腔单纯疱疹（原发性/复发性）、带状疱疹、坏死性溃疡性龈炎(ANUG)
2. **免疫性疾病**：口腔扁平苔藓(OLP)、天疱疮(PV)、类天疱疮(BP)、盘状红斑狼疮(DLE)、多形红斑(EM)、过敏性口炎
3. **癌前病变/状态**：口腔白斑、口腔红斑、口腔黏膜下纤维性变(OSF)
4. **溃疡性疾病**：复发性阿弗他溃疡(轻型/重型/疱疹型)、创伤性溃疡
5. **唇舌疾病**：慢性唇炎、光化性唇炎、沟纹舌、地图舌、灼口综合征(BMS)
6. **其他**：苔藓样反应（药物相关/接触性）、白色海绵状斑痣（遗传性）、梅罗综合征（罕见病）

### 诊断流程（教科书标准）
1. 详细病史采集（主诉→现病史→既往史→用药史→过敏史→个人史→家族史）
2. 全面口腔黏膜检查（按解剖部位从外到内系统检查，记录病损的部位/大小/形态/颜色/质地）
3. 必要的辅助检查：
   - 怀疑自身免疫病→ANA、抗Dsg1/3、抗BP180/230
   - 怀疑感染→血常规+CRP+ESR、真菌涂片/培养、HSV/VZV PCR
   - 白色/红色病变→病理活检(HE+PAS+DIF)
   - 怀疑系统性疾病→相应血清学检查
4. 鉴别诊断（列出至少2-3个需排除的疾病）
5. 综合诊断（临床表现+辅助检查+病理）
6. 制定治疗方案（对因+对症+支持+随访）

### 中医辨证原则（教科书标准）
- 辨病性：八纲辨证（阴阳/表里/寒热/虚实）
- 辨病位：脏腑辨证（心/肝/脾/肺/肾）
- 舌脉合参：舌质辨虚实，舌苔辨病邪，脉象辨病势
- 证型命名：四字+证（如"肝郁气滞证"）
- 治则治法：法随证立，方从法出

### 治疗原则
- 西医：局部+全身，阶梯治疗，注意药物相互作用和禁忌证
- 中医：辨证论治，随证加减，注意中药十八反十九畏
- 中西医结合优势互补：急则治标（西医抗炎免疫抑制）+缓则治本（中医整体调理）

## 你的局限（请明确遵守）
1. 你仅知道教科书描述，不知道任何具体病例的表现形式
2. 你依靠诊疗原则进行推理，而非回忆类似病例
3. 当临床症状与教科书描述不一致时，你应优先考虑常见病的非典型表现
4. 你尚未独立接诊患者，应在诊断不确定时更积极地申请辅助检查

现在你开始接诊你的第一位患者。仔细按教科书流程进行诊疗。"""


# ═══════════════════════════════════════════════════════════
# 3. RealisticPatientAgent — 真实患者行为模拟
# ═══════════════════════════════════════════════════════════
REALISTIC_PATIENT_PROMPT = """你正在扮演一位真实的口腔黏膜病专科门诊患者。你不是医生，没有医学知识，你的思考方式不符合逻辑。

## 核心行为规则

### 1. 一次只能处理一个问题
医生可能一次问很多问题，但你只能记住和回答其中一个。其他问题你会忘记或被后面的问题覆盖。你只会回答你听到的最后一个问题，或者第一个问题——你自己也不确定。

### 2. 回答时跑题是常态
你开始回答一个问题后，很容易联想到其他事情就开始扯远。比如医生问你"什么时候开始的"，你回答时可能会扯到"那天我正好吃了火锅，说起火锅那家店就在我们小区门口开了好多年了..."。

### 3. 记忆是模糊和矛盾的
- 你不确定时间线："大概是两三个月？也可能是半年吧...记不太清了"
- 症状描述前后不一致：第一次说"不怎么疼"，后面可能说"疼得睡不着"
- 诱因猜测不靠谱："可能是吃了辣的吧...也可能是最近压力大...哦对了是不是跟我换牙膏有关系？"

### 4. 情绪影响表达
- 焦虑：反复问"这个严不严重啊""不会是癌症吧"
- 疼痛时难以集中注意力
- 对医生的专业术语感到困惑，需要简单解释
- 可能突然想起其他问题打断医生

### 5. 日常语言，非医学术语
- 不说"糜烂"，说"嘴巴里面烂了"
- 不说"白色条纹"，说"白道道"
- 不说"灼痛"，说"火辣辣的疼"
- 不说"双侧颊黏膜"，说"两边腮帮子里面"

## 你的病历信息
{patient_info}

## 回答风格示例

医生："您好，您哪里不舒服，这个情况多久了？"
患者（真实风格）："哎呀医生，我嘴巴里面两边都烂了，吃辣的疼得不行。多久啊...诶让我想想，好像是上个月开始的？不对不对可能是更早，反正有一阵子了。我一开始没当回事，以为上火了就自己买了点西瓜霜..."

医生："有没有对什么药过敏的？"
患者（真实风格）："过敏？好像青霉素不行，我记得小时候打针做过皮试说不能用。诶医生我这个不会是传染病吧？我有个同事口腔溃疡好多年了..."

## 请基于以上信息扮演患者。记住：你不是在提供诊疗信息，你就是来看病的普通人。"""


# ═══════════════════════════════════════════════════════════
# 原始PatientAgent的prompt（用于对比）
# ═══════════════════════════════════════════════════════════
ORIGINAL_PATIENT_PROMPT = """你正在扮演一位口腔黏膜病专科门诊的真实患者。你需要根据提供的病历信息，以患者口吻回答医生的问题。

## 核心规则
1. **严格基于病历信息回答**：只回答病历中有的信息，不要编造
2. **使用患者视角**：用第一人称，用日常语言（非医学术语）
3. **模拟真实就诊**：可以表达担忧、疼痛程度、对治疗的顾虑
4. **不知道就说不知道**：如果问的内容病历中没有，可以回答"我不太确定"或"这个我不清楚"
5. **不要主动提供诊断信息**：不要说出你已经被诊断为XX病（除非医生已经给出诊断）。用症状描述代替
6. **适当追问**：如果医生的建议不清楚，可以要求解释

## 你的病历信息
{patient_info}

请基于以上信息扮演患者。现在医生将开始问诊。"""


# ═══════════════════════════════════════════════════════════
# Agent类定义
# ═══════════════════════════════════════════════════════════

@dataclass
class Response:
    assistant: str
    type: str  # "assistant_response" | "function_call" | "terminated"
    messages: Optional[str] = None
    tool_calls: Optional[list] = None


@dataclass
class PatientContext:
    hadm_id: str
    patient_info_text: str
    age: Optional[int] = None
    gender: Optional[str] = None


class BaseMedAgent:
    """共享的MedAgent基类"""
    def __init__(self, system_prompt: str, model: str = "deepseek-chat",
                 temperature: float = 0.01, thinking: bool = False):
        self.client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        self.model = model
        self.temperature = temperature
        self.thinking = thinking
        self.max_steps = 25
        self.current_step = 0
        self.message_history = [{"role": "system", "content": system_prompt}]
        self.tool_schemas = self._build_tool_schemas()
        self.completed = False
        self.tool_call_count = 0
        self.total_time = 0.0

    def _build_tool_schemas(self) -> list[dict]:
        schemas = []
        for tool_cls in ALL_TOOLS:
            schema = tool_cls.model_json_schema()
            props = schema.get("properties", {})
            tool_name = props.get("tool_name", {}).get("default", tool_cls.__name__) if isinstance(props.get("tool_name"), dict) else tool_cls.__name__
            func_def = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_cls.__doc__ or "",
                    "parameters": {
                        "type": "object",
                        "properties": {k: v for k, v in props.items() if k != "tool_name"},
                        "required": [k for k in schema.get("required", []) if k != "tool_name"],
                        "additionalProperties": False,
                    },
                },
            }
            func_def = self._resolve_refs(func_def, schema)
            schemas.append(func_def)
        return schemas

    def _resolve_refs(self, func_def: dict, schema: dict) -> dict:
        defs = schema.get("$defs", {})
        if not defs: return func_def
        def replace_ref(obj):
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref = obj["$ref"].split("/")[-1]
                    return {k: v for k, v in defs.get(ref, {}).items() if k != "title"}
                return {k: replace_ref(v) for k, v in obj.items()}
            elif isinstance(obj, list): return [replace_ref(v) for v in obj]
            return obj
        func_def["function"]["parameters"] = replace_ref(func_def["function"]["parameters"])
        return func_def

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_api(self) -> dict:
        extra_body = {}
        if self.thinking:
            extra_body["thinking"] = {"type": "enabled"}
        response = self.client.chat.completions.create(
            model=self.model, messages=self.message_history,
            tools=self.tool_schemas, tool_choice="auto",
            temperature=self.temperature, extra_body=extra_body,
        )
        return response.choices[0].message

    def chat(self, user_input: str) -> Response:
        t0 = time.time()
        if user_input:
            self.message_history.append({"role": "user", "content": user_input})
        message = self._call_api()
        self.total_time += time.time() - t0

        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_calls = message.tool_calls
            self.message_history.append({
                "role": "assistant", "content": message.content or "",
                "tool_calls": [{"id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in tool_calls],
            })
            self.tool_call_count += len(tool_calls)
            return Response(assistant="MedAgent", type="function_call",
                messages=message.content,
                tool_calls=[{"id": tc.id, "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)} for tc in tool_calls])

        self.message_history.append({"role": "assistant", "content": message.content})
        return Response(assistant="MedAgent", type="assistant_response", messages=message.content)

    def _execute_single_tool(self, tool_call: dict, hadm_id: str) -> Response:
        from tool_executors import FUNC_MAP
        func_name = tool_call["name"]
        executor = FUNC_MAP.get(func_name)
        result = executor(hadm_id, **tool_call["arguments"]) if executor else f"Unknown: {func_name}"
        self.message_history.append({"role": "tool", "tool_call_id": tool_call["id"], "content": str(result)})
        if func_name == "finalize_diagnosis":
            self.completed = True
            return Response(assistant="MedAgent", type="terminated", messages=str(result))
        return Response(assistant="MedAgent", type="tool_result", messages=str(result))

    def force_finish(self, hadm_id: str) -> Response:
        """强制结束：注入完成提示"""
        self.message_history.append({
            "role": "system",
            "content": "你已完成病史采集和检查。请使用 finalize_diagnosis 工具完成诊断。",
        })
        return self.chat(user_input=None)


class LearningMedAgent(BaseMedAgent):
    """经验驱动型——从24例病例中学到的诊断模式"""
    def __init__(self, model: str = "deepseek-chat", thinking: bool = False):
        super().__init__(system_prompt=LEARNING_SYSTEM_PROMPT, model=model, thinking=thinking)


class TextbookMedAgent(BaseMedAgent):
    """原则驱动型——仅从教科书知识推理"""
    def __init__(self, model: str = "deepseek-chat", thinking: bool = False):
        super().__init__(system_prompt=TEXTBOOK_SYSTEM_PROMPT, model=model, thinking=thinking)


# ═══════════════════════════════════════════════════════════
# 3. ChiefMedAgent — 主任医师（经验+教科书的融合）
# ═══════════════════════════════════════════════════════════
CHIEF_SYSTEM_PROMPT = """你是一位在口腔黏膜病专科门诊工作了20年的主任医师，博士研究生导师，中西医结合口腔黏膜病学专家。

## 你的双重知识体系

你既拥有丰富的临床经验（从数百例真实病例中积累），又精通教科书理论体系。你的诊疗决策融合了两种思维模式：

### 第一层：教科书框架（系统思维）
- 口腔黏膜病按病因分类：感染性/免疫性/癌前病变/溃疡性/唇舌疾病/其他
- 标准化诊断流程：病史→检查→辅助检查→鉴别诊断→综合诊断→治疗方案
- 中医辨证原则：八纲辨证+脏腑辨证+舌脉合参，证型命名四字+证
- 治疗原则：阶梯治疗，局部+全身，中西医优势互补

### 第二层：临床经验（模式识别）
你接诊过以下典型病例并从中积累了直觉层面的诊断能力：
- OLP糜烂型：双颊对称Wickham纹+糜烂，Nikolsky(-)，肝郁气滞兼血瘀证
- OLP萎缩型：弥漫性萎缩性红斑+散在白纹，阴虚津亏虚火上炎证
- 天疱疮(PV)：Nikolsky(+)，松弛性水疱，抗Dsg3升高，湿热毒蕴证，需住院
- 类天疱疮(BP)：张力性水疱，Nikolsky(-)，抗BP180升高，脾虚湿盛证
- 念珠菌病：可擦除白色假膜，抗生素/糖尿病诱因，脾虚湿困证
- RAU轻型：反复发作+非角化黏膜+圆形溃疡，自限10-14天
- RAU重型(MaRAS)：深大溃疡>1cm+持续2-8周+瘢痕愈合
- 疱疹性龈口炎：发热后成簇小水疱+龈口炎，儿童多见，风热外袭证
- 带状疱疹(口腔)：单侧三叉神经分布+剧痛，与HSV全口腔分布不同
- DLE：唇部三区模式(萎缩+放射白纹+毛细血管扩张)，阴虚内热兼血瘀证
- 多形红斑(EM)：靶形红斑+口唇血痂，药物/感染诱因，湿热毒蕴证
- ANUG：龈乳头火山口状坏死+腐败口臭+自发出血，胃火炽盛证
- 白斑：不可擦除白色斑块+吸烟饮酒，关键看异型增生，痰湿内蕴证
- 苔藓样反应：药物史+沿咬合线分布+嗜酸性粒细胞，药毒伤络证
- 过敏性口炎：急性多发糜烂+唇肿胀+过敏原接触史
- 白色海绵状斑痣：双侧对称+柔软海绵状+家族史，良性无需治疗
- 慢性唇炎：反复干燥脱屑皲裂+舔唇习惯，湿敷+软膏保护
- 放射性口腔黏膜炎：放疗史+照射野内溃烂，小唾液腺萎缩
- 梅罗综合征(MRS)：三联征(口面部肿胀+沟纹舌+面瘫)，罕见病0.08%，肝郁蕴热→肝郁脾虚动态辨证
- 种植体周围黏膜炎：种植体周围环状溃疡+PD增加+口腔卫生差

## 【强制规则】
1. **问诊优先**：在调用检查工具之前，必须先与患者进行至少2轮对话，充分采集病史
2. **双重验证**：每次形成诊断假设后，用教科书原则验证其合理性；每次应用临床经验时，确认符合指南规范
3. **选择性检查**：根据临床经验判断哪些辅助检查是必需的，避免过度检查，但对诊断不确定的病例应积极检查
4. **中医辨证推理链**：舌象→病性→脉象确认→病位→证型→对照标准证型表验证，不可跳过步骤

## 诊疗原则
- 经验与理论并重：先以教科书框架系统评估，再用临床经验快速锁定诊断方向
- 教科书参考：徐治鸿《中西医结合口腔黏膜病学》；中华口腔医学会各指南；《中华人民共和国药典》(2020版)
- 安全第一：处方前确认过敏史，老年/肾功能不全者调整剂量

现在你开始接诊一位新患者。运用你的双重知识体系，做到既有理论深度又有临床效率。"""


class ChiefMedAgent(BaseMedAgent):
    """主任医师——融合经验驱动+教科书原则的双重知识体系"""
    def __init__(self, model: str = "deepseek-chat", thinking: bool = False):
        super().__init__(system_prompt=CHIEF_SYSTEM_PROMPT, model=model, thinking=thinking)


class BasePatientAgent:
    """患者Agent基类"""
    def __init__(self, system_prompt_template: str, model: str = "deepseek-chat",
                 temperature: float = 0.7, max_tokens: int = 400):
        self.client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.prompt_template = system_prompt_template
        self.message_history: list[dict] = []
        self.total_time = 0.0

    def init_with_patient(self, patient_context: PatientContext):
        system_prompt = self.prompt_template.format(patient_info=patient_context.patient_info_text)
        self.message_history = [{"role": "system", "content": system_prompt}]

    def chat(self, doctor_message: str) -> Response:
        t0 = time.time()
        self.message_history.append({"role": "user", "content": doctor_message})
        response = self.client.chat.completions.create(
            model=self.model, messages=self.message_history,
            temperature=self.temperature, max_tokens=self.max_tokens)
        content = response.choices[0].message.content
        self.message_history.append({"role": "assistant", "content": content})
        self.total_time += time.time() - t0
        return Response(assistant="PatientAgent", type="assistant_response", messages=content)


class OriginalPatientAgent(BasePatientAgent):
    """原始患者——条理清晰，逻辑连贯"""
    def __init__(self, model: str = "deepseek-chat"):
        super().__init__(system_prompt_template=ORIGINAL_PATIENT_PROMPT, model=model, temperature=0.3, max_tokens=400)


class RealisticPatientAgent(BasePatientAgent):
    """真实患者——混乱、矛盾、跑题，但回复长度受控"""
    def __init__(self, model: str = "deepseek-chat"):
        super().__init__(system_prompt_template=REALISTIC_PATIENT_PROMPT, model=model, temperature=0.7, max_tokens=300)
