"""
v0.1.4 对话引擎 — DGIC (Differential-Guided Information Collection)
基于 MeDxAgent (Microsoft Research, 2026) + DocCHA (UIUC, SIGDIAL 2025)

核心改进（vs v0.1.3）：
1. 早期鉴别诊断生成（Turn ~6-8）: 从初步病史+首轮检查生成3-5个候选诊断
2. 鉴别驱动工具选择: 每个工具调用需声明"正在区分X vs Y"
3. 信息充分性动态评估: 工具结果回来→更新候选排序→判断是否收敛
4. 渐进式诊断截止: Turn 15提醒 → Turn 20紧迫 → Turn 25硬截止
5. max_turns=30（vs v0.1.3的40），强制高效
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents import MedAssistant, PatientAssistant, PatientContext, Response
from config import SAVE_DIR


def run_conversation(
    med_agent: MedAssistant,
    patient_agent: PatientAssistant,
    patient_context: PatientContext,
    primary_complaint: str,
    max_turns: int = 30,
    verbose: bool = True,
) -> dict:
    conversation_log = []
    t_start = time.time()
    differential_generated = False
    turn_warning_15 = False
    turn_warning_20 = False
    turn_warning_25 = False

    if verbose:
        print(f"\n{'='*60}")
        print(f"[v0.1.4 DGIC] 病例 {patient_context.hadm_id} | {patient_context.age}岁 {patient_context.gender}")
        print(f"主诉: {primary_complaint}")
        print(f"策略: 鉴别诊断驱动 | max_turns={max_turns}")
        print(f"{'='*60}\n")

    starter = (
        f"现在接诊一位新患者。患者主诉：{primary_complaint}"
        if primary_complaint
        else "现在接诊一位新患者。请先询问患者的症状。"
    )
    if patient_context.age and patient_context.gender:
        starter += f" 患者为{patient_context.age}岁{'女性' if patient_context.gender == 'F' else '男性'}。"

    def _inject_system_nudge(nudge_text: str):
        med_agent.message_history.append({"role": "system", "content": nudge_text})

    def _handle_med_response(resp):
        nonlocal turn, differential_generated, turn_warning_15, turn_warning_20, turn_warning_25
        if resp.type != "function_call" or not resp.tool_calls:
            return resp, 0
        extra_turns = 0
        while resp.type == "function_call" and resp.tool_calls:
            for tc in resp.tool_calls:
                turn += 1
                extra_turns += 1
                if verbose:
                    args_str = json.dumps(tc['arguments'], ensure_ascii=False)[:200]
                    print(f"\n  [TOOL t{turn}] {tc['name']}: {args_str}")
                tool_response = med_agent._execute_single_tool(tc, patient_context.hadm_id)
                conversation_log.append({
                    "turn": turn, "role": f"Tool({tc['name']})",
                    "content": tool_response.messages, "type": tool_response.type,
                    "tool_call": tc,
                })
                if verbose:
                    _print_response("Tool", tool_response)
                if tool_response.type == "diagnosis_submitted":
                    reflection_prompt = (
                        "【自反思核查】在最终确定前，请进行以下4项核查：\n"
                        "1. 诊断依据是否充分？所有关键临床表现是否都有对应解释？\n"
                        "2. 鉴别诊断是否完整？是否排除了临床表现相似的其他疾病？\n"
                        "3. 证据引用是否准确？引用的文献/指南是否支持你的判断？\n"
                        "4. 不确定性是否合理表达？如信息不足，是否明确指出了不确定之处？\n\n"
                        "如有需要修正，请重新调用 finalize_diagnosis。如已完备，回复'诊断确认无误'。"
                    )
                    med_agent.message_history.append({"role": "user", "content": reflection_prompt})
                    resp = med_agent.chat(user_input=None)
                    turn += 1
                    extra_turns += 1
                    conversation_log.append({
                        "turn": turn, "role": "MedAgent(reflection)",
                        "content": resp.messages, "type": resp.type,
                    })
                    if resp.type == "function_call" and resp.tool_calls:
                        for tc2 in resp.tool_calls:
                            if tc2.get('name') == 'finalize_diagnosis':
                                tr = med_agent._execute_single_tool(tc2, patient_context.hadm_id)
                                conversation_log.append({
                                    "turn": turn+1, "role": "Tool(finalize_diagnosis)",
                                    "content": tr.messages, "type": "terminated", "tool_call": tc2,
                                })
                                med_agent.completed = True
                                return Response(assistant="MedAgent", type="terminated",
                                    messages="诊断完成（修正后）"), extra_turns
                    elif resp.messages and any(kw in resp.messages for kw in [
                        '确认无误', '诊断无误', '不需要修正', '诊断已经完备', '确认诊断'
                    ]):
                        med_agent.completed = True
                        return Response(assistant="MedAgent", type="terminated",
                            messages="诊断确认（含自反思核查）"), extra_turns
                    _inject_system_nudge(
                        "你已完成了信息收集但诊断尚不确定。"
                        "请基于目前已获得的全部信息，使用 finalize_diagnosis 给出你的最佳诊断，"
                        "并在 diagnosis_basis_clinical 中明确标注：(1)诊断的置信度等级 "
                        "(2)支持该诊断的关键证据 (3)仍存在的不确定性。不要继续收集信息。"
                    )
                    resp = med_agent.chat(user_input=None)
                    turn += 1
                    extra_turns += 1
                    conversation_log.append({
                        "turn": turn, "role": "MedAgent(uncertain→diagnose)",
                        "content": resp.messages, "type": resp.type,
                    })
                    resp, extra_turns2 = _handle_med_response(resp)
                    extra_turns += extra_turns2
                    if resp.type == "terminated":
                        med_agent.completed = True
                    return resp, extra_turns

            tool_count = med_agent.tool_call_count
            if tool_count >= 2 and not differential_generated:
                _inject_system_nudge(
                    "【DGIC Phase 1→2 切换】你已收集了初步信息。请执行以下步骤：\n"
                    "1. 在你的思考中列出3-5个候选诊断，按可能性排序\n"
                    "2. 对每个候选标注：支持证据 | 待排除证据 | 关键缺失信息\n"
                    "3. 后续每个工具调用前，说明它用于区分哪些候选诊断\n"
                    "4. 工具结果返回后，更新候选排序\n\n"
                    "从此刻起，每次对话回复请以[当前鉴别诊断: X>Y>Z]开头。"
                )
                differential_generated = True

            if turn >= 25 and not turn_warning_25:
                _inject_system_nudge(
                    "【⚠ 诊断截止警告】你仅剩5轮对话。请立即停止收集新信息，"
                    "基于已有全部信息使用 finalize_diagnosis 完成诊断。"
                    "即使信息不完美，也必须给出诊断+置信度说明。"
                )
                turn_warning_25 = True
            elif turn >= 20 and not turn_warning_20:
                _inject_system_nudge(
                    "【⚡ 收敛提示】你已进行多轮信息收集。如果现有信息的鉴别诊断排序"
                    "在最近3轮中已趋于稳定（top候选不变），说明信息已足够。"
                    "请评估是否可以进入诊断阶段。"
                )
                turn_warning_20 = True
            elif turn >= 15 and not turn_warning_15:
                _inject_system_nudge(
                    "【📋 中期检查点】你已收集了较多信息。请思考："
                    "1. 目前的top候选诊断是什么？\n"
                    "2. 还需要哪些关键信息来确认或排除它？\n"
                    "3. 如果没有这些信息，能否给出暂定诊断？\n"
                    "如已有足够信心，可以开始准备 finalize_diagnosis。"
                )
                turn_warning_15 = True

            resp = med_agent.chat(user_input=None)
            turn += 1
            extra_turns += 1
            conversation_log.append({
                "turn": turn, "role": "MedAgent",
                "content": resp.messages, "type": resp.type,
            })
            if verbose:
                _print_response("MedAgent", resp)
        return resp, extra_turns

    if verbose:
        print("── Phase 1: 快速假设生成 ──")

    turn = 0
    response = med_agent.chat(starter)
    conversation_log.append({"turn": turn, "role": "MedAgent", "content": response.messages, "type": response.type})
    if verbose:
        _print_response("MedAgent", response)

    response, _ = _handle_med_response(response)
    if response.type == "terminated" or med_agent.completed:
        return _build_result(conversation_log, med_agent, patient_agent, patient_context, t_start)

    current_speaker = "patient"
    while turn < max_turns and not med_agent.completed:
        turn += 1
        if current_speaker == "patient":
            last_msg = response.messages or "请问您有什么不舒服？"
            response = patient_agent.chat(last_msg)
            conversation_log.append({
                "turn": turn, "role": "PatientAgent",
                "content": response.messages, "type": "patient_response",
            })
            if verbose:
                _print_response("PatientAgent", response)
            current_speaker = "doctor"
        else:
            response = med_agent.chat(response.messages)
            conversation_log.append({
                "turn": turn, "role": "MedAgent",
                "content": response.messages, "type": response.type,
            })
            if verbose:
                _print_response("MedAgent", response)
            response, _ = _handle_med_response(response)
            if response.type == "terminated" or med_agent.completed:
                break
            current_speaker = "patient"

    if turn >= max_turns and not med_agent.completed:
        if verbose:
            print(f"\n  [WARNING] 达到最大轮次 ({max_turns})，强制完成...")
        _inject_system_nudge(
            "你已达到最大对话轮次。请基于目前已获得的所有信息，"
            "立即使用 finalize_diagnosis 给出你的最佳诊断。"
            "明确标注置信度等级和不确定性来源。这是最后机会。"
        )
        response = med_agent.chat(user_input=None)
        conversation_log.append({
            "turn": turn + 1, "role": "MedAgent(forced)",
            "content": response.messages, "type": response.type,
        })
        if response.type == "function_call" and response.tool_calls:
            for tc in response.tool_calls:
                if tc.get('name') == 'finalize_diagnosis':
                    tr = med_agent._execute_single_tool(tc, patient_context.hadm_id)
                    conversation_log.append({
                        "turn": turn + 2, "role": "Tool(finalize_diagnosis)",
                        "content": tr.messages, "type": "terminated", "tool_call": tc,
                    })
                    med_agent.completed = True
                    break

    return _build_result(conversation_log, med_agent, patient_agent, patient_context, t_start)


def _build_result(log, med_agent, patient_agent, ctx, t_start):
    elapsed = time.time() - t_start
    return {
        "hadm_id": ctx.hadm_id,
        "conversation_log": log,
        "statistics": {
            "total_time_seconds": round(elapsed, 1),
            "total_turns": len(log),
            "tool_calls": med_agent.tool_call_count,
            "med_api_time": round(med_agent.total_time, 1),
            "patient_api_time": round(patient_agent.total_time, 1),
        },
        "completed": med_agent.completed,
        "version": "v0.1.4-dgic",
    }


def save_result(result: dict, hadm_id: str, label: str = ""):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    label_part = f"_{label}" if label else ""
    filename = f"{hadm_id}{label_part}_v014_{timestamp}.json"
    filepath = SAVE_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n对话已保存: {filepath}")
    return filepath


def _print_response(speaker: str, response: Response):
    color_map = {"MedAgent": "\033[94m", "PatientAgent": "\033[92m", "Tool": "\033[93m"}
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
