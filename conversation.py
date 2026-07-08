"""
对话流程引擎
模拟医生-患者对话循环 + 工具调用执行。
基于 MIRA conv.py 的架构。
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
    """
    运行完整的诊断对话

    流程:
    1. MedAgent 接收初始主诉 → 开始问诊
    2. MedAgent ↔ PatientAgent 交替对话 (病史采集)
    3. MedAgent 调用工具 (检查/化验/微生物/病理)
    4. 工具结果返回 → MedAgent 分析
    5. 循环直到 MedAgent 调用 finalize_diagnosis 或达到最大轮次

    返回: 包含完整对话记录的 dict
    """
    conversation_log = []
    t_start = time.time()

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
        """处理 MedAgent 响应中的工具调用（批量执行 + 递归处理后续调用）。
        返回最终的、不含工具末处理的 response，以及使用的 turn 增量。"""
        nonlocal turn
        extra_turns = 0

        if resp.type != "function_call" or not resp.tool_calls:
            return resp, extra_turns

        while resp.type == "function_call" and resp.tool_calls:
            # 第一阶段：批量执行本轮所有工具调用
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

                if med_agent.completed:
                    return tool_response, extra_turns

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

    # 处理首轮的潜在工具调用
    response, _ = _handle_med_response(response)

    if response.type == "terminated" or med_agent.completed:
        return _build_result(conversation_log, med_agent, patient_agent, patient_context, t_start)

    # ── 第 2 步：对话循环 ──
    current_speaker = "patient"  # MedAgent 发言后轮到 Patient

    while turn < max_turns and not med_agent.completed:
        turn += 1

        if current_speaker == "patient":
            # PatientAgent 回复 MedAgent 的问话
            last_msg = response.messages or "请问您有什么不舒服？"
            response = patient_agent.chat(last_msg)
            conversation_log.append({"turn": turn, "role": "PatientAgent", "content": response.messages, "type": "patient_response"})
            if verbose:
                _print_response("PatientAgent", response)
            current_speaker = "doctor"

        else:
            # MedAgent: 可能文本回复、调用工具、或结束
            response = med_agent.chat(response.messages)
            conversation_log.append({"turn": turn, "role": "MedAgent", "content": response.messages, "type": response.type})

            if verbose:
                _print_response("MedAgent", response)

            # 处理工具调用
            response, _ = _handle_med_response(response)

            if response.type == "terminated" or med_agent.completed:
                break

            current_speaker = "patient"

    # ── 第 3 步：达到最大轮次时强制结束 ──
    if turn >= max_turns and not med_agent.completed:
        if verbose:
            print(f"\n  [WARNING] 达到最大对话轮次 ({max_turns})，强制结束...")
        response = med_agent.force_finish(patient_context.hadm_id)
        conversation_log.append({
            "turn": turn + 1,
            "role": "MedAgent(forced)",
            "content": response.messages,
            "type": "terminated",
        })

    return _build_result(conversation_log, med_agent, patient_agent, patient_context, t_start)


def _build_result(
    log: list,
    med_agent: MedAssistant,
    patient_agent: PatientAssistant,
    ctx: PatientContext,
    t_start: float,
) -> dict:
    """构建结果字典"""
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
    }


def save_result(result: dict, hadm_id: str):
    """保存对话结果到 JSON"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{hadm_id}_{timestamp}.json"
    filepath = SAVE_DIR / filename

    # 清理不可序列化的内容
    clean_result = {
        "hadm_id": result["hadm_id"],
        "conversation_log": result["conversation_log"],
        "statistics": result["statistics"],
        "completed": result["completed"],
    }
    # 只保存最后几条消息历史（避免文件过大）
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
        "MedAgent": "\033[94m",       # 蓝色
        "PatientAgent": "\033[92m",   # 绿色
        "Tool": "\033[93m",  # 黄色
    }
    color = color_map.get(speaker, "\033[0m")
    reset = "\033[0m"

    if response.type == "function_call":
        print(f"{color}[{speaker}]{reset} (调用工具中...)")
    elif response.type == "terminated":
        print(f"{color}[{speaker}]{reset} [OK] 诊断完成\n")
    else:
        text = response.messages or ""
        # 截断过长的输出
        if len(text) > 500:
            text = text[:500] + "..."
        print(f"{color}[{speaker}]{reset} {text}\n")
