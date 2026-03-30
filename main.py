import time
import json
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.provider import ProviderRequest

# 导入我们刚刚编写的微引擎和工具
from .entity_resolver import EntityResolver
from .action_consumer import ActionConsumer
from .qq_tools import (
    ConstructAtEventTool,
    ProactivePokeTool,
    MemeResonanceTool,
    SpaceTransitionTool,
    RegretAndWithdrawTool,
    MessageReactionTool,
    ProactiveLikeTool
)

@register("astrbot_plugin_qq_interactive_tools", "和泉智宏", "QQ主动互动函数工具集", "1.0.0", "https://github.com/0d00-Ciallo-0721/astrbot_plugin_qq_interactive_tools")
class MaiQQToolsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 1. 初始化实体引擎
        self.entity_resolver = EntityResolver()
        
        # [新增修复]：自己维护一个跨界专用的内存字典，彻底摆脱系统依赖
        self.space_jumps_memory = {}
        
        # 2. 注册 LLM 全局函数工具
        self.context.add_llm_tools(
            ConstructAtEventTool(entity_resolver=self.entity_resolver),
            ProactivePokeTool(entity_resolver=self.entity_resolver),
            MemeResonanceTool(),
            # [修改点]：将我们自己的字典传进去
            SpaceTransitionTool(shared_dict=self.space_jumps_memory),
            RegretAndWithdrawTool(),
            MessageReactionTool(),
            ProactiveLikeTool(entity_resolver=self.entity_resolver)
        )
        logger.info("[Mai QQ Tools] 🚀 7 个专属物理/情绪交互工具已全局挂载！")

    # ==========================================
    # 钩子 1：发送前置拦截 (消费 Pending 队列与覆写复读)
    # ==========================================
    @filter.on_decorating_result()
    async def intercept_and_consume_actions(self, event: AstrMessageEvent):
        """挂接 action_consumer 逻辑"""
        # 如果带有自闭环发出的免疫标记，跳过检测，防止无限递归解析
        if event.get_extra("astrmai_is_self_reply", False):
            return
            
        try:
            ActionConsumer.consume_decorating_result(event)
        except Exception as e:
            logger.error(f"[Mai QQ Tools] Action Consumer 拦截出错: {e}")

    # ==========================================
    # 钩子 2：大模型请求前置拦截 (处理跨界私聊的“信标补偿”)
    # ==========================================
    @filter.on_llm_request()
    async def inject_space_transition_memory(self, event: AstrMessageEvent, req: ProviderRequest):
        """复刻 planner.py 的溯源逻辑：当从群聊转入私聊时，自动提取前置群聊语境"""
        
        # 只在私聊环境下触发溯源
        if not event.get_group_id():
            # [修改点]：直接使用我们插件自己维护的内存字典
            jumps = self.space_jumps_memory
            sender_id = str(event.get_sender_id())
            
            if sender_id in jumps:
                jump_info = jumps[sender_id]
                # 信标有效期校验 (10 分钟内有效)
                if time.time() - jump_info["timestamp"] < 600:
                    source_group_id = jump_info.get("group_id")
                    group_context_str = ""
                    
                    if source_group_id:
                        try:
                            conv_mgr = self.context.conversation_manager
                            uid = f"{event.get_platform_name()}:GroupMessage:{source_group_id}"
                            curr_cid = await conv_mgr.get_curr_conversation_id(uid)
                            conversation = await conv_mgr.get_conversation(uid, curr_cid)
                            
                            history = conversation.history if conversation else []
                            if isinstance(history, str):
                                history = json.loads(history)
                                
                            recent_msgs = []
                            for msg in history[-5:]:
                                role = msg.get("role", "")
                                text_parts = [
                                    item.get("text", "") 
                                    for item in (msg.get("content") or []) 
                                    if isinstance(item, dict) and item.get("type") == "text"
                                ]
                                content = " ".join(text_parts) if text_parts else ""
                                if content:
                                    speaker = "群友" if role == "user" else "你"
                                    recent_msgs.append(f"[{speaker}]: {content}")
                            
                            if recent_msgs:
                                group_context_str = "\n".join(recent_msgs)
                        except Exception as e:
                            logger.error(f"🤫 [Mai QQ Tools] 溯源群聊历史失败: {e}")

                    sys_inject = (
                        f"\n\n>>> [!!! 极其重要的跨界前置记忆 !!!] <<<\n"
                        f"几分钟前，你刚刚在群聊 (群号:{source_group_id}) 中与大家互动，随后跳出来主动给当前用户发了一句私聊：\n"
                        f"【你的悄悄话原文】：{jump_info['private_message']}\n"
                    )
                    
                    if group_context_str:
                        sys_inject += f"\n【跳转前的群聊事件回顾 (参考)】：\n{group_context_str}\n"
                        
                    sys_inject += (
                        f"\n用户现在的回复绝对是对你上述行为的回应！请结合群里的前置话题和你的悄悄话，"
                        f"以私下交流的自然感、亲密感继续往下聊！\n"
                        f">>> [记忆读取完毕] <<<"
                    )
                    
                    req.system_prompt += sys_inject
                    logger.info(f"🤫 [Mai QQ Tools] 已触发跨界语境补偿，成功抓取群聊历史并注入到 {sender_id} 的私聊思考中。")
                
                # 阅后即焚，清理信标
                del jumps[sender_id]