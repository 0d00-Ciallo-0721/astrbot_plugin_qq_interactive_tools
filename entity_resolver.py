import re
import json
from typing import Optional, Tuple
from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp

class EntityResolver:
    """
    轻量级实体时空解析引擎 (从原 astrmai 数据库模块剥离)
    职责：将自然语言名字或包含 ID 的字符串精准反推为物理 QQ 号。
    """
    def __init__(self):
        pass

    async def resolve_entity_spatio_temporal(
        self, 
        target_name: str, 
        current_event: AstrMessageEvent, 
        astr_ctx=None
    ) -> Optional[Tuple[str, str]]:
        if not target_name or not current_event:
            return None

        # 获取环境群组 ID
        group_id = current_event.get_group_id() or str(current_event.unified_msg_origin)
        group_id = str(group_id)

        # 🟢 1. 预处理：剔除可能携带的 '@' 符号和两端空格
        target_name = target_name.strip().lstrip('@')
        clean_name = target_name

        # 🟢 2. 拦截模式 A：大模型直接传入了纯数字 ID
        if target_name.isdigit():
            return (target_name, group_id)

        # 🟢 3. 拦截模式 B：大模型传入了 "姓名(ID)" 或 "姓名（ID）" 格式
        match = re.search(r'^(.*?)[\(（]([0-9]+)[\)）]$', target_name)
        if match:
            extracted_id = match.group(2).strip()
            return (extracted_id, group_id)
            
        # 🟢 4. 拦截模式 B.5：物理环境兜底检查 (扫描用户当前消息中的 @ 组件)
        if current_event.message_obj and hasattr(current_event.message_obj, 'message'):
            at_targets = []
            self_id = str(current_event.get_self_id())
            for comp in current_event.message_obj.message:
                if isinstance(comp, Comp.At):
                    at_qq = str(comp.qq)
                    if at_qq != self_id:
                        at_targets.append(at_qq)
            
            # 如果用户的消息里只明确 @ 了一个人，直接锁头
            if len(at_targets) == 1:
                return (at_targets[0], group_id)

        # 🟢 5. 拦截模式 C：如果只是单纯的姓名，继续走下方的时空搜索逻辑
        if current_event.get_sender_name() == clean_name:
            return (str(current_event.get_sender_id()), group_id)

        # 检查局部事件窗口
        window_events = current_event.get_extra("astrmai_window_events", [])
        for w_event in reversed(window_events):
            if w_event.get_sender_name() == clean_name:
                return (str(w_event.get_sender_id()), group_id)

        # 🟢 6. 拦截模式 D：跨界溯源 / AstrBot 原生历史记录检索
        if astr_ctx and hasattr(astr_ctx, 'conversation_manager'):
            try:
                conv_mgr = astr_ctx.conversation_manager
                uid = current_event.unified_msg_origin
                curr_cid = await conv_mgr.get_curr_conversation_id(uid)
                conversation = await conv_mgr.get_conversation(uid, curr_cid)
                
                if conversation and hasattr(conversation, "history") and conversation.history:
                    history = conversation.history
                    if isinstance(history, str):
                        history = json.loads(history)
                        
                    for msg_data in reversed(history):
                        sender_name = ""
                        sender_id = ""
                        if isinstance(msg_data, dict):
                            sender_name = msg_data.get("sender", {}).get("nickname", "") or msg_data.get("name", "")
                            sender_id = msg_data.get("sender", {}).get("user_id", "")
                        elif hasattr(msg_data, "sender"):
                            sender_name = getattr(msg_data.sender, "nickname", getattr(msg_data.sender, "name", ""))
                            sender_id = getattr(msg_data.sender, "user_id", "")
                            
                        if sender_name == clean_name and sender_id:
                            return (str(sender_id), group_id)
            except Exception:
                pass

        # 剥离原 SQL 兜底，实现纯净化
        return None