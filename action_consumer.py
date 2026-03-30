import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger

class ActionConsumer:
    """
    动作消费引擎 (取代原 ReplyEngine / Executor 的文本拦截器)
    通过分析大模型返回的文本以及压入的 pending_actions 队列，组装最终的消息链。
    """
    @staticmethod
    def consume_decorating_result(event: AstrMessageEvent):
        """此方法将在 main.py 的 @filter.on_decorating_result() 钩子中被调用"""
        result = event.get_result()
        if not result or not result.chain:
            return

        pending_actions = event.get_extra("astrmai_pending_actions", [])

        # ==========================================
        # 🟢 1. 处理 [TERMINAL_YIELD] 人类本质复读机覆写
        # ==========================================
        terminal_content = None
        
        # 优先嗅探 LLM 文本中是否包含 [TERMINAL_YIELD]:
        for comp in result.chain:
            if isinstance(comp, Comp.Plain):
                text = comp.text
                if "[TERMINAL_YIELD]:" in text:
                    idx = text.find("[TERMINAL_YIELD]:")
                    terminal_content = text[idx + len("[TERMINAL_YIELD]:"):].strip()
                    break
        
        # 兼容队列标记
        reread_action = next((a for a in pending_actions if a.get("action") == "terminal_reread"), None)
        if reread_action and not terminal_content:
            terminal_content = reread_action.get("content", "")

        # 如果命中复读覆写，直接清空原本的废话，只发送复读内容
        if terminal_content:
            logger.info(f"🎭 [ActionConsumer] 触发复读动作，已覆写原有消息: {terminal_content}")
            result.chain.clear()
            result.chain.append(Comp.Plain(terminal_content))
            return # 退出，复读不需要再进行 @ 拼接

        # ==========================================
        # 🟢 2. 处理主动 @ (At) 挂载
        # ==========================================
        at_targets = [a.get("target_id") for a in pending_actions if a.get("action") == "at"]
        
        if at_targets:
            # 简单去重，避免对同一个人重复 @ 多次
            unique_targets = list(dict.fromkeys(at_targets))
            
            insert_idx = 0
            for target_id in unique_targets:
                try:
                    uid = int(target_id)
                    # 将 @ 组件插到消息的最前面
                    result.chain.insert(insert_idx, Comp.At(qq=uid))
                    insert_idx += 1
                    # 补充空格防止与正文粘连
                    result.chain.insert(insert_idx, Comp.Plain(" "))
                    insert_idx += 1
                except ValueError:
                    logger.warning(f"[ActionConsumer] 无效的 QQ 号格式，跳过 @ 组装: {target_id}")
                    
            logger.info(f"🎯 [ActionConsumer] 成功在最终消息链首部挂载 @ 组件: {unique_targets}")

        # ==========================================
        # 🟢 3. 清洗多余标记与前缀
        # ==========================================
        for comp in result.chain:
            if isinstance(comp, Comp.Plain):
                # 如果 LLM 不听话把 [SYSTEM_WAIT_SIGNAL] 写出来了，则清理掉
                comp.text = comp.text.replace("[SYSTEM_WAIT_SIGNAL]", "")