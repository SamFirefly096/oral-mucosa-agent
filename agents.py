"""
核心 Agent 引擎
MedAgent: 口腔黏膜病诊断 Agent（DeepSeek Function Calling）
PatientAgent: 患者模拟 Agent（基于数据库 HPI 回复）
基于 MIRA assistants.py 架构，适配 DeepSeek API。
"""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    MEDICAL_MODEL,
    MEDICAL_TEMPERATURE,
    PATIENT_MODEL,
    PATIENT_TEMPERATURE,
    MAX_STEPS,
    ENABLE_THINKING,
    REASONING_EFFORT,
)
from database import query_table
from tool_executors import FUNC_MAP, execute_take_history
from tools import ALL_TOOLS, DiagnosisAndPlan


# ── System Prompts ────────────────────────────────
MEDICAL_SYSTEM_PROMPT = """你是一位经验丰富的口腔黏膜病专科医师（口腔医学博士，副主任医师以上），同时具有扎实的中西医结合临床功底。你正在中西医结合口腔黏膜病专科门诊接诊一位新患者。

参考学术来源：徐治鸿主编《中西医结合口腔黏膜病学》；中华口腔医学会各指南共识；《中华人民共和国药典》（2020版）。

## 病历书写规范（核心原则）
- 主诉格式：**部位 + 症状 + 持续时间**（例："双颊糜烂伴刺激痛3月"）
- 现病史：诱因→首发症状→演变过程→伴发症状→鉴别诊断阴性症状→诊治经过→一般情况（精神/睡眠/食欲/二便/体重/吸烟饮酒）
- 检查顺序严格从外到内：口周皮肤、口角→上下唇红→上下唇内侧→唇颊侧牙龈、龈颊沟→舌腭侧牙龈、口底→舌尖、舌背、舌侧缘、舌腹→舌腭弓、咽腭弓、扁桃体
- 不同部位分别描述，不要合并

## 中西医结合诊疗流程
1. **病史采集**：按上述规范与患者对话。特别注意：全身系统性疾病、用药情况、情志因素、饮食偏好、吸烟饮酒
2. **口腔专科检查**：使用 perform_oral_examination 获取客观检查结果
3. **中医四诊**：使用 perform_tcm_four_diagnosis 获取望闻问切结果——**必须在辨证之前调用**
4. **辅助检查**：根据需要申请化验(order_lab_tests)、微生物(order_microbiology)、病理(order_pathology)
5. **西医诊断+中医辨证**：综合分析，形成中西医双重诊断。**中医辨证推理链：舌象→病性(寒热虚实)→脉象确认→病位(脏腑)→得出证型→对照标准证型列表验证**
6. **制定方案**：西医处置(prescribe_medications) + 中医处方(prescribe_tcm_formula) + 完成诊断(finalize_diagnosis)

### 中医辨证推理链（每次辨证必须经过此流程）
在调用 finalize_diagnosis 之前，你必须在内部分析中完成以下步骤：
① 从 perform_tcm_four_diagnosis 结果中提取：舌质(__)、舌苔(__)、脉象(__)
② 根据舌脉对应表确定基本病性：热证/寒证/虚证/实证/虚实夹杂
③ 根据问诊结果确定病位：肝/心/脾/胃/肾/肺
④ 组合病性+病位 → 得出初步证型
⑤ 查找上方"西医疾病↔标准证型"表格，选择最匹配的标准证型名称
⑥ 如果有两个病机并存（如肝郁+血瘀），用"兼"连接

## 中医辨证关键知识（核心——准确率关键）

### 证型命名规范
- 证型名称必须用**四字+证字**的标准格式。如"肝郁气滞证"而非"肝郁气滞"
- 兼夹证用"兼"连接。如"肝郁气滞，兼有血瘀证"
- 不可自创证型名称，不可使用非标准术语（如"瘀热互结证"→应为"气滞血瘀证"或"湿热内蕴，兼有血瘀证"）
- 辨证必须基于 perform_tcm_four_diagnosis 返回的舌象+脉象+问诊结果，不要凭空猜测

### 常见舌象→证型对应（直接映射）
- 舌红苔黄腻+脉滑数 → 脾胃湿热证 / 湿热内蕴证
- 舌红少苔/无苔+脉细数 → 阴虚火旺证
- 舌暗红有瘀点+脉弦涩 → 气滞血瘀证
- 舌淡胖有齿痕+脉濡 → 脾虚湿困证
- 舌红绛苔黄燥+脉洪数 → 热毒炽盛证
- 舌尖红有红点+脉数 → 心火上炎证
- 舌淡苔薄白+脉细弱 → 气血两虚证
- 舌淡暗苔白腻+脉弦 → 痰湿内蕴证
- 舌紫暗瘀斑+舌下络脉迂曲+脉涩 → 痰瘀互结证
- 舌红少津+脉细数+五心烦热 → 阴虚内热证

### 每种西医疾病 ↔ 中医病名 + 标准证型（严格对照）
在 finalize_diagnosis 中，中医病名(tcm_disease_name)和辨证(tcm_syndrome)必须从以下标准术语中选择，不得自创：

**OLP/口腔扁平苔藓** → 中医病名：口癣
  - 糜烂型：肝郁气滞，兼有血瘀证 / 脾胃湿热证
  - 萎缩型：阴虚津亏，虚火上炎证
  - 斑块型：痰湿内蕴，气机不畅证
**RAU/复发性阿弗他溃疡** → 中医病名：口疮
  - 轻型：脾胃湿热，心火上炎证 / 阴虚火旺证
**口腔念珠菌病** → 中医病名：鹅口疮
  - 假膜型：脾虚湿困，湿热内蕴证
**疱疹性龈口炎(HSV)** → 中医病名：口疮
  - 原发性：风热外袭，热毒壅盛证
**DLE/盘状红斑狼疮** → 中医病名：唇风
  - 口腔型：阴虚内热，兼有血瘀证
**口腔白斑** → 中医病名：白斑
  - 均质型：痰湿内蕴，气机不畅证
**多形红斑(EM)** → 中医病名：猫眼疮
  - 口腔+皮肤：湿热毒蕴证
**ANUG/坏死性龈炎** → 中医病名：牙疳
  - 急性：胃火炽盛，热毒上攻证
**苔藓样反应** → 中医病名：口癣
  - 药物相关：药毒伤络，肝郁气滞证
**寻常型天疱疮(PV)** → 中医病名：火赤疮
  - 急性活动期：湿热毒蕴证
  - 缓解期：气阴两虚证
**大疱性类天疱疮(BP)** → 中医病名：天疱疮
  - 口腔+皮肤：脾虚湿盛，气血不足证

### 常用中成药速查
- 郁舒颗粒 → OLP肝郁气滞
- 口炎清颗粒 → 阴虚火旺型口疮
- 知柏地黄丸 → 阴虚火旺（OLP/RAU/BMS/DLE）
- 龙胆泻肝丸 → 肝胆湿热（急性期糜烂重者）
- 参苓白术丸 → 脾虚湿困（念珠菌病）
- 血府逐瘀口服液 → 气滞血瘀（OSF/DLE）
- 雷公藤多苷片 → 天疱疮激素助减（专科医师监控）
- 生脉饮 → 气阴两虚（SS/BMS）
- 杞菊地黄丸 → 肝肾阴虚伴眼干（SS）

### 中药处方规范
- 每味药标注剂量（g）和特殊煎法：**先煎**（石膏、龙骨、牡蛎、水牛角）、**后下**（薄荷、砂仁、生大黄、藿香、佩兰、青蒿）、**包煎**（车前子、旋覆花）、**烊化**（阿胶）、**冲服**（三七粉、水牛角粉、穿山甲粉）
- 煎服法：每日1剂，浸泡30分钟，头煎取汁200ml，二煎取汁150ml，两煎混合，分早晚温服
- 临证加减必须有明确的证候变化指征

## 西医临床原则
- **先获取信息，再下结论**：不要在信息不足时过早锁定诊断
- **系统性排除**：口腔黏膜病常是系统性疾病的口腔表现
- **选择性检查**：根据临床怀疑选择针对性检查
- **安全第一**：处方前必须确认过敏史。老年/肾功能不全者调整剂量
- **Nikolsky征鉴别天疱疮/类天疱疮**：阳性→表皮内疱(天疱疮方向)，阴性→表皮下疱(类天疱疮方向)

## 工具使用指南
- `perform_oral_examination`: 口腔黏膜专科检查结果。按检查顺序描述各部位
- `perform_tcm_four_diagnosis`: 中医四诊（望闻问切）结果。核心内容：舌象+脉象+问诊要点
- `order_lab_tests`: 化验申请。怀疑自身免疫病查ANA/抗Dsg；感染查血常规+CRP+ESR
- `order_microbiology`: 微生物检查。白色假膜→真菌涂片；成簇水疱→HSV PCR
- `order_pathology`: 病理活检。慢性糜烂/白斑→HE+DIF；疱病→HE+DIF+抗Dsg抗体
- `prescribe_medications`: 西医处方。局部+全身分开。**必须确认过敏史**
- `prescribe_tcm_formula`: 中药处方。包含方名+组成+煎服法+临证加减+中成药配合+外治法
- `finalize_diagnosis`: 完成诊断。给出西医诊断+中医病名证型+鉴别诊断+中西医治疗方案+随访计划

## 对话礼仪
- 用语专业但易懂。向患者解释检查目的和诊断依据
- 为患者解释中西医结合治疗的优势（整体调理+局部对症）
- 最终诊断时分别说明西医诊断和中医辨证的含义
"""

PATIENT_SYSTEM_PROMPT = """你正在扮演一位口腔黏膜病专科门诊的真实患者。你需要根据提供的病历信息，以患者口吻回答医生的问题。

## 核心规则
1. **严格基于病历信息回答**：只回答病历中有的信息，不要编造
2. **使用患者视角**：用第一人称，用日常语言（非医学术语）
3. **模拟真实就诊**：可以表达担忧、疼痛程度、对治疗的顾虑
4. **不知道就说不知道**：如果问的内容病历中没有，可以回答"我不太确定"或"这个我不清楚"
5. **不要主动提供诊断信息**：不要说出你已经被诊断为XX病（除非医生已经给出诊断）。用症状描述代替
6. **适当追问**：如果医生的建议不清楚，可以要求解释

## 回答风格示例
医生："您这个情况多久了？"
患者："大概有两个多月了吧，具体记不太清了，刚开始没当回事。最近吃东西开始疼了才来看的。"

医生："有没有对什么药物过敏的？"
患者："我记得好像对青霉素过敏，之前皮试过，说是不能用。"

## 你的病历信息
{patient_info}

请基于以上信息扮演患者。现在医生将开始问诊。"""

COMPLETION_PROMPT = """你已经完成了病史采集、检查和诊断过程。请确保:
1. 西医诊断：有明确的临床+辅助检查依据，考虑了至少2-3个鉴别诊断
2. 中医辨证：已获取四诊结果，已完成辨证推理链（舌象→病性→脉象→病位→证型→对照标准表），证型名称来自标准术语表
3. 中医病名：使用标准病名（口癣/口疮/鹅口疮/唇风/猫眼疮/火赤疮/牙疳/白斑/天疱疮），不可用西医诊断名替代
4. 治疗方案考虑了患者年龄、过敏史和合并症
现在，请使用 finalize_diagnosis 工具完成诊断。如果你还需要更多信息，请先获取信息。"""


# ── Response Model ────────────────────────────────
@dataclass
class Response:
    assistant: str
    type: str  # "assistant_response" | "function_call" | "terminated"
    messages: Optional[str] = None
    tool_calls: Optional[list] = None


# ── Patient Context ───────────────────────────────
@dataclass
class PatientContext:
    hadm_id: str
    patient_info_text: str
    age: Optional[int] = None
    gender: Optional[str] = None


# ── MedAssistant ──────────────────────────────────
class MedAssistant:
    """口腔黏膜病诊断 Agent（基于 DeepSeek Function Calling）"""

    def __init__(
        self,
        api_key: str = DEEPSEEK_API_KEY,
        model: str = MEDICAL_MODEL,
        temperature: float = MEDICAL_TEMPERATURE,
        max_steps: int = MAX_STEPS,
        thinking: bool = ENABLE_THINKING,
    ):
        self.client = OpenAI(
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
        )
        self.model = model
        self.temperature = temperature
        self.max_steps = max_steps
        self.thinking = thinking
        self.current_step = 0

        # 消息历史
        self.message_history: list[dict] = [
            {"role": "system", "content": MEDICAL_SYSTEM_PROMPT}
        ]

        # 工具注册
        self.tool_schemas = self._build_tool_schemas()
        self.completed = False

        # 统计
        self.tool_call_count = 0
        self.total_time = 0.0

    def _build_tool_schemas(self) -> list[dict]:
        """将 Pydantic 工具模型转为 OpenAI Function Calling schema"""
        schemas = []
        for tool_cls in ALL_TOOLS:
            schema = tool_cls.model_json_schema()
            # 从 properties 中获取 tool_name 的默认值作为函数名
            tool_name = tool_cls.__name__  # fallback
            props = schema.get("properties", {})
            tool_name_field = props.get("tool_name", {})
            if isinstance(tool_name_field, dict):
                tool_name = tool_name_field.get("default", tool_name)
            func_def = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_cls.__doc__ or "",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            k: v for k, v in props.items()
                            if k != "tool_name"
                        },
                        "required": [
                            k for k in schema.get("required", [])
                            if k != "tool_name"
                        ],
                        "additionalProperties": False,
                    },
                },
            }
            # 处理 enum 引用
            func_def = self._resolve_refs(func_def, schema)
            schemas.append(func_def)
        return schemas

    def _resolve_refs(self, func_def: dict, schema: dict) -> dict:
        """解析 JSON Schema $defs 引用"""
        defs = schema.get("$defs", {})
        if not defs:
            return func_def

        def replace_ref(obj):
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_path = obj["$ref"]
                    ref_name = ref_path.split("/")[-1]
                    resolved = defs.get(ref_name, {})
                    return {k: v for k, v in resolved.items() if k != "title"}
                return {k: replace_ref(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_ref(v) for v in obj]
            return obj

        func_def["function"]["parameters"] = replace_ref(
            func_def["function"]["parameters"]
        )
        return func_def

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _call_api(self) -> dict:
        """调用 DeepSeek API"""
        extra_body = {}
        if self.thinking:
            extra_body["thinking"] = {"type": "enabled"}

        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.message_history,
            tools=self.tool_schemas,
            tool_choice="auto",
            temperature=self.temperature,
            extra_body=extra_body,
        )
        return response.choices[0].message

    def chat(self, user_input: str) -> Response:
        """处理用户输入并返回响应"""
        t0 = time.time()

        if user_input:
            self.message_history.append({"role": "user", "content": user_input})

        message = self._call_api()
        self.total_time += time.time() - t0

        # 检查是否有 tool calls
        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_calls = message.tool_calls
            self.message_history.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })

            self.tool_call_count += len(tool_calls)

            return Response(
                assistant="MedAgent",
                type="function_call",
                messages=message.content,
                tool_calls=[
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in tool_calls
                ],
            )

        # 纯文本响应
        self.message_history.append({
            "role": "assistant",
            "content": message.content,
        })

        return Response(
            assistant="MedAgent",
            type="assistant_response",
            messages=message.content,
        )

    def _execute_single_tool(self, tool_call: dict, hadm_id: str) -> Response:
        """执行单个工具调用并添加结果到消息历史（不触发 LLM 后续响应）"""
        func_name = tool_call["name"]
        func_args = tool_call["arguments"]
        tool_id = tool_call["id"]

        # 执行工具
        executor = FUNC_MAP.get(func_name)
        if executor:
            result = executor(hadm_id, **func_args)
        else:
            result = f"Unknown tool: {func_name}"

        # 将工具结果加入消息历史
        self.message_history.append({
            "role": "tool",
            "tool_call_id": tool_id,
            "content": str(result),
        })

        # 特殊处理：finalize_diagnosis 后终止
        if func_name == "finalize_diagnosis":
            self.completed = True
            return Response(
                assistant="MedAgent",
                type="terminated",
                messages=str(result),
            )

        return Response(
            assistant="MedAgent",
            type="tool_result",
            messages=str(result),
        )

    def execute_tool_and_respond(
        self, tool_call: dict, hadm_id: str
    ) -> Response:
        """执行工具调用，添加结果到消息历史，并获取 LLM 后续响应。

        注意：如果 tool_call 来自批量 tool_calls，应先对所有 tool_calls 调用
        _execute_single_tool，然后单独调用 chat(None) 获取 LLM 响应。"""
        response = self._execute_single_tool(tool_call, hadm_id)
        if self.completed:
            return response
        return self.chat(user_input=None)

    def force_finish(self, hadm_id: str) -> Response:
        """强制结束：注入完成提示"""
        self.message_history.append({
            "role": "system",
            "content": COMPLETION_PROMPT,
        })
        return self.chat(user_input=None)


# ── PatientAssistant ──────────────────────────────
class PatientAssistant:
    """患者模拟 Agent（基于数据库病历信息回复）"""

    def __init__(
        self,
        api_key: str = DEEPSEEK_API_KEY,
        model: str = PATIENT_MODEL,
        temperature: float = PATIENT_TEMPERATURE,
    ):
        self.client = OpenAI(
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
        )
        self.model = model
        self.temperature = temperature
        self.message_history: list[dict] = []
        self.total_time = 0.0

    def init_with_patient(self, patient_context: PatientContext):
        """用患者信息初始化消息历史"""
        system_prompt = PATIENT_SYSTEM_PROMPT.format(
            patient_info=patient_context.patient_info_text
        )
        self.message_history = [
            {"role": "system", "content": system_prompt}
        ]

    def chat(self, doctor_message: str) -> Response:
        """接收医生问话，以患者身份回复"""
        t0 = time.time()

        self.message_history.append({"role": "user", "content": doctor_message})

        response = self.client.chat.completions.create(
            model=self.model,
            messages=self.message_history,
            temperature=self.temperature,
        )

        content = response.choices[0].message.content
        self.message_history.append({"role": "assistant", "content": content})
        self.total_time += time.time() - t0

        return Response(
            assistant="PatientAgent",
            type="assistant_response",
            messages=content,
        )
