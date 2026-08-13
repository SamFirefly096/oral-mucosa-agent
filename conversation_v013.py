"""
v0.1.3 增强版对话引擎
在 v0.1.2 自反思循环基础上，新增：
1. 知识库检索锚定：反思时检索教科书知识库验证诊断
2. 改进反思提示词：允许暂定诊断+不确定性说明+置信度分级
3. 多维完成标准：区分"确诊"/"暂定诊断"/"未完成+充分论证"

用法与原 conversation.py 兼容，替换 import 即可。
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents import MedAssistant, PatientAssistant, PatientContext, Response
from config import SAVE_DIR
from kb_retrieval import get_retriever


# ═══════════════════════════════════════════════════════════
# v0.1.3 反思提示词
# ═══════════════════════════════════════════════════════════
REFLECTION_PROMPT_V013 = """【自反思核查 + 知识库锚定】

请对照以下知识库检索结果和核查清单，对你的诊断进行反思：

{retrieval_summary}

──────── 四维核查 ────────
1. 诊断依据是否充分？所有关键临床表现是否都有对应解释？
2. 鉴别诊断是否完整？知识库列出的待排除疾病是否已充分排除？
3. 证据引用是否准确？诊断条目是否符合知识库中的诊断标准？
4. 不确定性是否合理表达？如果信息不足，请明确指出不确定性之处。

──────── 诊断置信度分级（必须选择一个）────────
请在反思后根据你对诊断的确信程度选择以下之一：

[A] 确诊（confidence: high）
   → 所有诊断标准均已满足，鉴别诊断已充分排除
   → 直接回复"诊断确认无误"

[B] 暂定诊断（confidence: medium）
   → 大部分诊断标准满足，但部分信息不足或待排除
   → 使用 finalize_diagnosis 重新提交诊断，并在 prognosis 字段用 "【暂定诊断】" 开头，在 diagnosis_basis_clinical 末尾加上 "|不确定性说明：[简述哪些信息不足]"
   → 必须有至少1条知识库中提到的诊断依据

[C] 证据不足，无法诊断（confidence: low）
   → 关键诊断标准未满足，或信息严重不足
   → 使用 finalize_diagnosis 提交，primary_diagnosis 填写 "诊断未确定"，differential_diagnoses 列出待排除的疾病（按可能性排序），在 diagnosis_basis_clinical 中说明"关键缺失信息：[列出]"
   → 这不算放弃，而是负责任地记录当前判断限度

[C] 选项的核心精神：即使不能确定诊断，也要输出你的推理过程和鉴别思路——这本身就是有价值的临床思考记录。永远不要直接放弃输出。"""


def run_conversation(
    med_agent: MedAssistant,
    patient_agent: PatientAssistant,
    patient_context: PatientContext,
    primary_complaint: str,
    max_turns: int = 30,
    verbose: bool = True,
) -> dict:
    """
    运行完整的诊断对话 (v0.1.3)

    v0.1.3 改进:
    - 反思时自动检索教科书知识库锚定验证
    - 改进反思提示词：三级置信度 + 暂定诊断 + 禁止放弃
    - 多维完成标准
    """
    reflection_done = False
    conversation_log = []
    t_start = time.time()
    kb_retriever = get_retriever()

    # ── 第 1 步：初始问诊 ──
    if verbose:
        print(f"\n{'='*60}")
        print(f"病例 {patient_context.hadm_id} | {patient_context.age}岁 {patient_context.gender}")
        print(f"主诉: {primary_complaint}")
        print(f"{'='*60}\n")

    starter = (
        f"现在接诊一位新患者。患者主诉：{primary_complaint}"
        if primary_complaint
        else "现在接诊一位新患者。请先询问患者的症状。"
    )
    if patient_context.age and patient_context.gender:
        starter += f" 患者为{patient_context.age}岁{'女性' if patient_context.gender == 'F' else '男性'}。"

    # ── 辅助函数：处理 MedAgent 的工具调用 ──
    def _handle_med_response(resp):
        nonlocal turn, reflection_done
        extra_turns = 0

        if resp.type != "function_call" or not resp.tool_calls:
            return resp, extra_turns

        while resp.type == "function_call" and resp.tool_calls:
            for tc in resp.tool_calls:
                turn += 1
                extra_turns += 1
                if verbose:
                    print(f"\n  [TOOL] {tc['name']}: {json.dumps(tc['arguments'], ensure_ascii=False, indent=2)[:300]}")

                tool_response = med_agent._execute_single_tool(
                    tc, patient_context.hadm_id
                )
                conversation_log.append({
                    "turn": turn,
                    "role": f"Tool({tc['name']})",
                    "content": tool_response.messages,
                    "type": tool_response.type,
                    "tool_call": tc,
                })

                if verbose:
                    _print_response("Tool", tool_response)

                # 兼容两种Agent: 增强版返回"diagnosis_submitted"，原始版返回"terminated"
                is_diagnosis_submitted = (
                    tool_response.type == "diagnosis_submitted" or
                    (tool_response.type == "terminated" and tc.get("name") == "finalize_diagnosis")
                )
                if is_diagnosis_submitted:
                    if not reflection_done:
                        reflection_done = True
                        # ── v0.1.3 新增：知识库检索 ──
                        diagnosis_text = tc.get("arguments", {}).get("primary_diagnosis", "")
                        dd_list = tc.get("arguments", {}).get("differential_diagnoses", [])

                        # 从对话中收集临床表现文本用于交叉检索
                        clinical_text = " ".join([
                            entry.get("content", "")
                            for entry in conversation_log
                            if isinstance(entry.get("content"), str)
                        ])[:2000]

                        # 检索知识库
                        kb_result = kb_retriever.retrieve_for_reflection(
                            primary_diagnosis=diagnosis_text,
                            differential_diagnoses=dd_list,
                            clinical_findings=clinical_text,
                        )

                        if verbose:
                            print(f"\n  [KB-RETRIEVAL] 锚定: {kb_result['primary_match']['name_cn'] if kb_result['primary_match'] else '未匹配'}")
                            for item in kb_result.get("diagnostic_checklist", [])[:2]:
                                print(f"    {item[:120]}")

                        # 记录知识库检索结果
                        conversation_log.append({
                            "turn": turn,
                            "role": "KB_Retrieval",
                            "content": kb_result["retrieval_summary"],
                            "type": "kb_anchor",
                            "primary_match": kb_result["primary_match"],
                        })

                        # ── v0.1.3 改进版反思提示 ──
                        reflection_prompt = REFLECTION_PROMPT_V013.format(
                            retrieval_summary=kb_result["retrieval_summary"]
                        )
                        med_agent.message_history.append(
                            {"role": "user", "content": reflection_prompt}
                        )

                        # LLM 反思
                        resp = med_agent.chat(user_input=None)
                        turn += 1
                        extra_turns += 1
                        conversation_log.append({
                            "turn": turn,
                            "role": "MedAgent(reflection)",
                            "content": resp.messages,
                            "type": resp.type,
                            "reflection_version": "v0.1.3",
                        })
                        if verbose:
                            print(f"\n  [REFLECTION v0.1.3] {resp.messages[:250] if resp.messages else ''}...")

                        # 处理反思后的工具调用(重新finalize_diagnosis)
                        resp, _ = _handle_med_response(resp)

                    med_agent.completed = True
                    return Response(
                        assistant="MedAgent",
                        type="terminated",
                        messages="诊断完成（v0.1.3 自反思+KB锚定核查）"
                    ), extra_turns

            # 第二阶段：获取 LLM 后续响应
            resp = med_agent.chat(user_input=None)
            turn += 1
            extra_turns += 1
            conversation_log.append({
                "turn": turn,
                "role": "MedAgent",
                "content": resp.messages,
                "type": resp.type,
            })

            if verbose:
                _print_response("MedAgent", resp)

        return resp, extra_turns

    # MedAgent 首轮
    turn = 0
    response = med_agent.chat(starter)
    conversation_log.append({"turn": turn, "role": "MedAgent", "content": response.messages, "type": response.type})

    if verbose:
        _print_response("MedAgent", response)

    response, _ = _handle_med_response(response)

    if response.type == "terminated" or med_agent.completed:
        return _build_result(conversation_log, med_agent, patient_agent, patient_context, t_start)

    # ── 第 2 步：对话循环 ──
    current_speaker = "patient"

    while turn < max_turns and not med_agent.completed:
        turn += 1

        if current_speaker == "patient":
            last_msg = response.messages or "请问您有什么不舒服？"
            response = patient_agent.chat(last_msg)
            conversation_log.append({
                "turn": turn,
                "role": "PatientAgent",
                "content": response.messages,
                "type": "patient_response"
            })
            if verbose:
                _print_response("PatientAgent", response)
            current_speaker = "doctor"

        else:
            response = med_agent.chat(response.messages)
            conversation_log.append({
                "turn": turn,
                "role": "MedAgent",
                "content": response.messages,
                "type": response.type,
            })
            if verbose:
                _print_response("MedAgent", response)

            response, _ = _handle_med_response(response)

            if response.type == "terminated" or med_agent.completed:
                break

            current_speaker = "patient"

    # ── 第 3 步：达到最大轮次时强制结束 ──
    if turn >= max_turns and not med_agent.completed:
        if verbose:
            print(f"\n  [WARNING] 达到最大对话轮次 ({max_turns})，强制执行 v0.1.3 分层完成...")

        # v0.1.3: 强制结束时允许降级输出
        force_prompt = (
            "对话已达到最大轮次。请基于目前已收集的信息完成诊断。\n"
            "- 如果诊断信息充足 → 使用 finalize_diagnosis 提交确诊\n"
            "- 如果诊断信息不足 → 使用 finalize_diagnosis 提交暂定诊断，"
            "primary_diagnosis 前加【暂定诊断】，说明不确定性来源\n"
            "- 如果信息严重不足 → primary_diagnosis 填「诊断未确定」，"
            "differential_diagnoses 列出待排除疾病，diagnosis_basis_clinical 说明关键缺失信息\n\n"
            "永远不要在临床记录中留白——即使不确定，也要记录当前判断和推理过程。"
        )
        med_agent.message_history.append({"role": "system", "content": force_prompt})
        response = med_agent.chat(user_input=None)
        conversation_log.append({
            "turn": turn + 1,
            "role": "MedAgent(v0.1.3 forced)",
            "content": response.messages,
            "type": "terminated",
        })

    return _build_result(conversation_log, med_agent, patient_agent, patient_context, t_start)


def _build_result(log, med_agent, patient_agent, ctx, t_start):
    """构建结果字典 (v0.1.3)"""
    elapsed = time.time() - t_start
    return {
        "hadm_id": ctx.hadm_id,
        "conversation_log": log,
        "med_message_history": med_agent.message_history,
        "patient_message_history": patient_agent.message_history,
        "statistics": {
            "total_time_seconds": round(elapsed, 1),
            "total_turns": len(log),
            "tool_calls": med_agent.tool_call_count,
            "med_api_time": round(med_agent.total_time, 1),
            "patient_api_time": round(patient_agent.total_time, 1),
        },
        "completed": med_agent.completed,
        "version": "v0.1.3",
    }


def save_result(result: dict, hadm_id: str):
    """保存对话结果到 JSON"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{hadm_id}_{timestamp}.json"
    filepath = SAVE_DIR / filename

    clean_result = {
        "hadm_id": result["hadm_id"],
        "conversation_log": result["conversation_log"],
        "statistics": result["statistics"],
        "completed": result["completed"],
        "version": result.get("version", "unknown"),
    }
    clean_result["med_messages_summary"] = [
        {"role": m["role"], "content_preview": str(m.get("content", ""))[:200]}
        for m in result["med_message_history"]
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(clean_result, f, ensure_ascii=False, indent=2)

    print(f"\n对话已保存: {filepath}")
    return filepath


def _print_response(speaker: str, response: Response):
    """格式化打印响应"""
    color_map = {
        "MedAgent": "\033[94m",
        "PatientAgent": "\033[92m",
        "Tool": "\033[93m",
    }
    color = color_map.get(speaker, "\033[0m")
    reset = "\033[0m"

    if response.type == "function_call":
        print(f"{color}[{speaker}]{reset} (调用工具中...)")
    elif response.type == "terminated":
        print(f"{color}[{speaker}]{reset} [OK] 诊断完成\n")
    else:
        text = response.messages or ""
        if len(text) > 500:
            text = text[:500] + "..."
        print(f"{color}[{speaker}]{reset} {text}\n")
