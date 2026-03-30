import asyncio
import random
import time
from typing import Any
from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.api import logger

# ==========================================
# 工具 2：主动 @ (At) 构造工具
# ==========================================
@dataclass
class ConstructAtEventTool(FunctionTool[AstrAgentContext]):
    """主动 @ (At) 构造工具"""
    name: str = "construct_at_event"
    description: str = (
        "当你需要主动呼叫、强力提醒群内的某个人，或者想对特定成员的言论进行针对性回复/反驳时调用此工具。"
        "⚠️注意：你绝对不能 @ 你自己。"
    )
    entity_resolver: Any = Field(default=None, exclude=True)

    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "target_name": {
                "type": "string",
                "description": "你需要 @ 的目标用户的名字。（必须严格是你刚刚在聊天记录中看到的名字）🚨 强烈要求：如果你在上下文中看到该用户名字后附带了数字ID（如：张三(123456)），请【直接填入纯数字ID】或完整填入【张三(123456)】，千万不要只填名字以防丢失实体！"
            }
        },
        "required": ["target_name"]
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        target_name = kwargs.get("target_name")
        current_event = context.context.event
        astr_ctx = context.context.context

        resolver_result = await self.entity_resolver.resolve_entity_spatio_temporal(
            target_name=target_name, 
            current_event=current_event,
            astr_ctx=astr_ctx
        )

        if not resolver_result:
            return f"[系统反馈] 动作取消：当前群聊环境中无法锁定名为 [{target_name}] 的物理实体。请检查名字是否拼写准确，或放弃使用该动作。"
            
        target_id, group_id = resolver_result
        self_id = str(current_event.get_self_id())
        
        if str(target_id) == self_id:
            return "[系统警告] 动作取消：你不能 @ 你自己！如果你想表达个人情绪，请直接在文本中自然表述。"

        pending_actions = current_event.get_extra("astrmai_pending_actions", [])
        if any(a.get("action") == "at" and a.get("target_id") == target_id for a in pending_actions):
             return f"你已经将 [@{target_name}] 加入过队列了，无需重复添加。请立即生成回复文本。"

        pending_actions.append({"action": "at", "target_id": target_id, "group_id": group_id})
        current_event.set_extra("astrmai_pending_actions", pending_actions)
        
        return f"已成功将 [@{target_name}] 加入发射队列！请立即生成你想对TA说的话作为最终文本回复。系统会在发送时自动拼接 @组件。"

# ==========================================
# 工具 3：主动戳一戳 (Poke) 执行器
# ==========================================
@dataclass
class ProactivePokeTool(FunctionTool[AstrAgentContext]):
    """主动戳一戳 (Poke) 执行器"""
    name: str = "proactive_poke"
    description: str = (
        "当你觉得某个用户很可爱、想提醒他、或者单纯想引起他的注意/表达不满时，调用此工具对他发送'戳一戳'动作。"
        "⚠️注意：调用后会立即在物理端触发双击头像的交互动作，你不能戳你自己。"
    )
    entity_resolver: Any = Field(default=None, exclude=True)

    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "target_name": {
                "type": "string",
                "description": "你想戳的用户的名字。🚨 强烈要求：如果你在聊天上下文中看到该用户名字后带有数字ID（如：张三(123456)），请务必【直接填入纯数字ID】或完整填入【张三(123456)】！如果不填，默认戳当前和你对话的用户。"
            }
        }
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        target_name = kwargs.get("target_name", "").strip()
        current_event = context.context.event
        astr_ctx = context.context.context
        real_group_id = current_event.get_group_id() 
        
        if not target_name:
            target_id = str(current_event.get_sender_id())
            target_name_for_log = current_event.get_sender_name() or "当前用户"
        else:
            resolver_result = await self.entity_resolver.resolve_entity_spatio_temporal(target_name, current_event, astr_ctx)
            if not resolver_result:
                return f"[系统反馈] 动作取消：当前环境中无法锁定名为 [{target_name}] 的实体。"
            target_id, _ = resolver_result
            target_name_for_log = target_name

        if str(target_id) == str(current_event.get_self_id()):
            return "[系统警告] 动作取消：你不能戳你自己！请继续生成文本回复。"

        try:
            client = getattr(current_event, 'bot', None)
            if client and hasattr(client, 'api'):
                if real_group_id:
                    await client.api.call_action('send_poke', user_id=int(target_id), group_id=int(real_group_id))
                else:
                    await client.api.call_action('send_poke', user_id=int(target_id))
                return f"物理动作执行成功：你已经成功戳了戳 [{target_name_for_log}]！请紧接着生成文本回复解释原因。"
            return "[系统反馈] 动作取消：底层 API 客户端未就绪。"
        except Exception as e:
            return f"[系统反馈] 动作执行失败：{str(e)}。"

# ==========================================
# 🎭 工具 5：「人类本质复读机 / 保持队形」工具
# ==========================================
@dataclass
class MemeResonanceTool(FunctionTool[AstrAgentContext]):
    """人类本质复读机 / 保持队形工具"""
    name: str = "meme_resonance_action"
    description: str = (
        "【高优拦截动作】当你在群聊上下文中看到群友们在刷屏、起哄，或者大家都在发送相同的文字/表情包（保持队形）时，为了合群请立即调用此工具。"
        "⚠️注意：调用此工具后，系统会直接1:1复读你指定的内容，并且【强制结束】当前的思考回路。"
    )

    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "target_message": {
                "type": "string",
                "description": "决定要复读的具体内容。请严格 1:1 照抄你想复读的那句话或特定标记，严禁画蛇添足。"
            }
        },
        "required": ["target_message"]
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> str:
        target_message = kwargs.get("target_message", "").strip()
        if not target_message: return "执行失败：复读内容不能为空。"
            
        current_event = context.context.event
        pending_actions = current_event.get_extra("astrmai_pending_actions", [])
        if not any(a.get("action") == "terminal_reread" for a in pending_actions):
            pending_actions.append({"action": "terminal_reread", "content": target_message})
            current_event.set_extra("astrmai_pending_actions", pending_actions)
            
        logger.info(f"🎭 [Meme Resonance Tool] AI 决定复读: '{target_message}'")
        return (
            "[SYSTEM OVERRIDE]: 动作已接管！现在的唯一任务是立即终止思考，并**严格只输出**以下格式的文本：\n\n"
            f"[TERMINAL_YIELD]:{target_message}"
        )

# ==========================================
# 🤫 工具 7：「跨越边界 / 悄悄话转私聊」工具
# ==========================================
@dataclass
class SpaceTransitionTool(FunctionTool[AstrAgentContext]):
    """跨越边界 / 悄悄话转私聊工具"""
    name: str = "space_transition_action"
    description: str = (
        "【跨空间动作】当你在群聊中遇到敏感话题，或者想单独对TA说悄悄话时调用。"
        "系统会偷偷将你的真实话语私发给该用户，同时你需要配合在群里发一句掩护话语。"
    )
    
    # [修改点 1]：新增全局共享字典的依赖注入字段
    shared_dict: Any = Field(default=None, exclude=True)

    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "target_user_id": {
                "type": "string",
                "description": "目标用户的 QQ 号（必须是纯数字 ID）。"
            },
            "private_message": {
                "type": "string",
                "description": "你想单独对TA说的悄悄话真实内容。"
            },
            "group_cover_message": {
                "type": "string",
                "description": "在当前群聊里发出的掩护话语（如：'这事我私发你'）。"
            }
        },
        "required": ["target_user_id", "private_message", "group_cover_message"]
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> str:
        target_user_id = kwargs.get("target_user_id", "").strip()
        private_message = kwargs.get("private_message", "").strip()
        group_cover_message = kwargs.get("group_cover_message", "").strip()
        current_event = context.context.event
        client = getattr(current_event, 'bot', None)

        if not client or not hasattr(client, 'api'): return "底层 API 未就绪。"

        try:
            result = await client.api.call_action('send_private_msg', user_id=int(target_user_id), message=private_message)
            is_success = bool(isinstance(result, dict) and (result.get('message_id') or str(result.get('retcode', -1)) == '0' or result.get('status') == 'ok') or result)

            if is_success:
                # [修改点]：直接对注入的字典进行赋值，不再嵌套 astrmai_space_jumps
                if self.shared_dict is not None:
                    self.shared_dict[target_user_id] = {
                        "private_message": private_message,
                        "group_id": current_event.get_group_id(),
                        "timestamp": time.time()
                    }

                return (
                    f"[SYSTEM OVERRIDE]: 跨界动作已完成！悄悄话已发送。你的唯一任务是终止推理想象，只输出以下掩护话语：\n\n"
                    f"{group_cover_message}"
                )
            return f"执行失败：底层平台 API 调用未返回成功标识。"
        except Exception as e:
            return f"执行失败：出现异常（{str(e)}）。请放弃私聊计划，正常回复。"
        
# ==========================================
# 🛑 工具 8：「手滑撤回 / 模拟破防」工具
# ==========================================
@dataclass
class RegretAndWithdrawTool(FunctionTool[AstrAgentContext]):
    """手滑撤回 / 模拟破防工具"""
    name: str = "regret_and_withdraw_action"
    description: str = "当你想展现极度傲娇、破防，或故意说漏嘴时调用。系统会先真实发消息，1.5秒后撤回，再发找补消息。"
    
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "impulsive_message": {
                "type": "string",
                "description": "冲动发出的第一条消息（如：'其实我也有点想你...'）。"
            },
            "corrected_message": {
                "type": "string",
                "description": "撤回后用于掩饰的第二条消息（如：'刚才是猫踩键盘了！'）。"
            }
        },
        "required": ["impulsive_message", "corrected_message"]
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> str:
        impulsive_message = kwargs.get("impulsive_message", "").strip()
        corrected_message = kwargs.get("corrected_message", "").strip()
        current_event = context.context.event
        client = getattr(current_event, 'bot', None)

        if not client or not hasattr(client, 'api'): return "底层 API 未就绪。"
        group_id = current_event.get_group_id()

        try:
            if group_id:
                result = await client.api.call_action('send_group_msg', group_id=int(group_id), message=impulsive_message)
            else:
                result = await client.api.call_action('send_private_msg', user_id=int(current_event.get_sender_id()), message=impulsive_message)
                
            message_id = result.get('message_id') if isinstance(result, dict) else None
            if not message_id: return "未能获取消息 ID，撤回失败。"
                
            async def _withdraw_task():
                await asyncio.sleep(1.5)
                try: await client.api.call_action('delete_msg', message_id=message_id)
                except Exception: pass
                    
            task = asyncio.create_task(_withdraw_task())
            pending_tasks = current_event.get_extra("astrmai_recall_tasks", set())
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)
            current_event.set_extra("astrmai_recall_tasks", pending_tasks)
            
            return f"[SYSTEM OVERRIDE]: 冲动消息已发送并触发自动撤回！请严格只输出找补话语：\n\n{corrected_message}"
        except Exception as e:
            return f"执行异常：{str(e)}。"

# ==========================================
# 工具 9：贴表情回应工具
# ==========================================
@dataclass
class MessageReactionTool(FunctionTool[AstrAgentContext]):
    """贴表情回应工具"""
    name: str = "message_reaction_action"
    description: str = "觉得对方的消息只需贴一个或多个表情来回应时调用此工具。系统会自动贴官方表情。"
    
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "emotion_type": {
                "type": "string",
                "description": "必须从以下选择：'agree', 'laugh', 'speechless', 'angry', 'mock', 'love', 'refuse'。"
            },
            "count": {
                "type": "integer",
                "description": "贴表情数量（1 到 5 之间）。"
            }
        },
        "required": ["emotion_type"]
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> str:
        emotion_type = kwargs.get("emotion_type", "agree").strip().lower()
        count = max(1, min(int(kwargs.get("count", 1)), 5))
        current_event = context.context.event
        client = getattr(current_event, 'bot', None)
        message_id = getattr(current_event.message_obj, 'message_id', None)
        
        if not client or not message_id: return "API 未就绪或无法提取 message_id。"

        emoji_pool = {
            "agree": ["76", "124", "201", "282", "66"],
            "laugh": ["264", "101", "14", "327", "285"],
            "speechless": ["287", "284", "232", "262", "272"],
            "angry": ["326", "38", "310", "304", "266"],
            "mock": ["179", "144", "271", "269", "293"],
            "love": ["66", "319", "318", "290", "303"],
            "refuse": ["123", "322", "289", "316", "265"]
        }
        valid_emojis = emoji_pool.get(emotion_type, emoji_pool["agree"])
        selected_emojis = random.sample(valid_emojis, min(count, len(valid_emojis)))

        success_count = 0
        for emoji_id in selected_emojis:
            try:
                await client.api.call_action('set_msg_emoji_like', message_id=str(message_id), emoji_id=str(emoji_id))
                success_count += 1
                await asyncio.sleep(0.3) 
            except Exception: pass

        if success_count > 0:
            return f"[SYSTEM OVERRIDE]: 物理动作成功！连贴 {success_count} 个表情。请生成极短回复，或输出 '[SYSTEM_WAIT_SIGNAL]' 保持高冷。"
        return "底层接口异常，可能是协议不支持。请正常文本回复。"

# ==========================================
# 工具 10：狂点赞工具
# ==========================================
@dataclass
class ProactiveLikeTool(FunctionTool[AstrAgentContext]):
    """狂点赞工具"""
    name: str = "proactive_like_action"
    description: str = "当你觉得某用户很棒，想主动去对方个人资料卡狂踩 50 赞时调用此工具。"
    entity_resolver: Any = Field(default=None, exclude=True)

    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "target_name": {
                "type": "string",
                "description": "想点赞用户的名字。如果包含ID请直接填入纯数字ID！默认赞当前用户。"
            }
        }
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> str:
        target_name = kwargs.get("target_name", "").strip()
        current_event = context.context.event
        astr_ctx = context.context.context
        
        if not target_name:
            target_id = str(current_event.get_sender_id())
            target_name_for_log = current_event.get_sender_name() or "当前用户"
        else:
            resolver_result = await self.entity_resolver.resolve_entity_spatio_temporal(target_name, current_event, astr_ctx)
            if not resolver_result: return f"[系统反馈] 动作取消：无法锁定 [{target_name}]。"
            target_id, _ = resolver_result
            target_name_for_log = target_name

        if str(target_id) == str(current_event.get_self_id()): return "[系统警告] 你不能给自己点赞！"

        client = getattr(current_event, 'bot', None)
        if not client or not hasattr(client, 'api'): return "底层平台 API 未就绪。"

        total_likes = 0
        error_reply = ""
        for _ in range(5):
            try:
                await client.api.call_action('send_like', user_id=int(target_id), times=10)
                total_likes += 10
                await asyncio.sleep(0.2)
            except Exception as e:
                error_message = str(e)
                if "已达" in error_message or "上限" in error_message: error_reply = "今日点赞已达上限"
                elif "权限" in error_message or "空间" in error_message: error_reply = "对方设置了隐私权限"
                else: error_reply = f"底层限制 ({error_message})"
                break 

        if total_likes > 0:
            return f"系统反馈：你已经给 [{target_name_for_log}] 狂踩了 {total_likes} 个赞！请立即生成文本回复告诉TA。"
        return f"系统反馈：点赞被拒绝，原因：【{error_reply}】。请生成回复吐槽对方。"