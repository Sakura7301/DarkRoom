import json  
import re
import time
import plugins  
import sqlite3  
import signal  
import sys  
from typing import Optional  
from datetime import datetime, timedelta  
from config import conf  
from bridge.context import ContextType  
from bridge.reply import Reply, ReplyType  
from common.log import logger   
from plugins import *  
import threading  
import os  # 确保导入 os 模块  

@plugins.register(  
    name="DarkRoom",  
    desire_priority=998,  
    hidden=False,  
    desc="小黑屋",  
    version="1.0",  
    author="sakura7301",  
)  
class DarkRoom(Plugin):  
    def __init__(self):  
        # 初始化插件
        super().__init__()  
        # 初始化数据库路径
        self.db_name = "./plugins/DarkRoom/dark_room.db"  
        # 初始化数据库表名
        self.db_table_name = "blacklist"  
        # 保证线程安全
        self.local_storage = threading.local()  
        # 初始化数据库
        self.check_and_read_database()  
        # 初始化配置
        self.config = super().load_config()
        # 加载配置模板
        if not self.config:
            self.config = self._load_config_template()
        # 存储用户消息计数和触发次数  
        self.user_message_tracker = {}  
        # 用于存储用户的最后事件时间(防抖动)
        self.last_event_time = {}  
        # 加载管理员列表
        self.admin_list = self.config.get("admin_list", [])
        self.message_time_frame = self.config.get("message_time_frame")
        self.trigger_count = self.config.get("trigger_count")
        # 注册事件处理程序
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context  
        logger.info("[DarkRoom] 插件初始化完毕")  

    def check_admin_list(self, content):
        # 检查关键词   
        return any(keyword in content for keyword in self.admin_list)  

    def get_db_connection(self):  
        # 检查是否存在本地存储的连接和游标
        if not hasattr(self.local_storage, 'conn'):  
            # 连接到数据库
            self.local_storage.conn = sqlite3.connect(self.db_name)  
            self.local_storage.cursor = self.local_storage.conn.cursor()  
        return self.local_storage.conn, self.local_storage.cursor  

    def close_db_connection_and_cursor(self):  
        # 关闭游标和连接
        if hasattr(self.local_storage, 'cursor'):  
            self.local_storage.cursor.close()  
            del self.local_storage.cursor  
        if hasattr(self.local_storage, 'conn'):  
            self.local_storage.conn.close()  
            del self.local_storage.conn  
        logger.info("[DarkRoom] 数据库连接和游标已关闭")  

    def check_connection_and_cursor(self):  
        try:  
            # 检查连接和光标是否存在
            self.get_db_connection()  
        except sqlite3.Error as e:  
            logger.error(f"[DarkRoom] 检查连接和游标时发生错误: {e}")  

    def check_and_read_database(self):  
        # 检查数据库是否存在
        if not os.path.exists(self.db_name):  
            logger.warn(f"[DarkRoom] 数据库 {self.db_name} 不存在，正在创建数据库...")  
            try:  
                # 连接到数据库
                conn, cursor = self.get_db_connection()  
                # 执行创建表操作
                cursor.execute(f'''  
                CREATE TABLE IF NOT EXISTS {self.db_table_name} (  
                    user_id TEXT PRIMARY KEY,  
                    user_name TEXT NOT NULL,  
                    release_date INTEGER NOT NULL,  
                    notes TEXT  
                )  
                ''')  
                # 提交更改
                conn.commit()  
                logger.info("[DarkRoom] 数据库已创建")  
            except sqlite3.Error as e:  
                logger.error(f"数据库错误: {e}")   
        else:  
            logger.info(f"[DarkRoom] 数据库 {self.db_name} 已存在，正在检查表...")  
            try:  
                # 连接到数据库
                conn, cursor = self.get_db_connection()  
                # 检查表是否存在
                cursor.execute(f'''  
                SELECT name FROM sqlite_master WHERE type='table' AND name='{self.db_table_name}';  
                ''')  
                if not cursor.fetchone():  
                    logger.info(f"[DarkRoom] 表 {self.db_table_name} 不存在，正在创建...")  
                    cursor.execute(f'''  
                    CREATE TABLE {self.db_table_name} (  
                        user_id TEXT PRIMARY KEY,  
                        user_name TEXT NOT NULL,  
                        release_date INTEGER NOT NULL,  
                        notes TEXT  
                    )  
                    ''')  
                    # 提交更改
                    conn.commit()  
                    logger.info(f"[DarkRoom] 表 {self.db_table_name} 已创建。")  
                else:  
                    logger.info(f"[DarkRoom] 表 {self.db_table_name} 已存在。")  
            except sqlite3.Error as e:  
                self.close_db_connection_and_cursor()  
                logger.error(f"[DarkRoom] 数据库错误: {e}")   

    def delete_entry_by_user_name(self, user_name):  
        """  
        根据用户姓名删除黑名单中的指定条目。  

        参数:  
        user_name (str): 要删除的用户姓名。  
        """  
        try:  
            ret_str = ""
            # 获取数据库连接和光标  
            conn, cursor = self.get_db_connection() 
            # 构建删除 SQL 语句  
            cursor.execute(f'DELETE FROM {self.db_table_name} WHERE user_name = ?', (user_name,))  
            # 返回影响的行数  
            deleted_rows = cursor.rowcount  
            if deleted_rows > 0:  
                ret_str = f"[DarkRoom] 用户 [{user_name}] 已被移出小黑屋。"
                logger.info(ret_str)  
            else:  
                ret_str = f"[DarkRoom] 用户 [{user_name}] 不在牢里。"
                logger.warning(ret_str)  

            # 提交更改  
            conn.commit()  
            return ret_str
        except sqlite3.Error as e:  
            ret_str = f"[DarkRoom] 数据库错误: {e}, user_name: {user_name}, type: {type(user_name)}"
            logger.error(ret_str)  
            return ret_str
        finally:  
            # 关闭数据库连接和光标  
            self.close_db_connection_and_cursor()


    def add_entry(self, user_id, user_name, release_date, notes):  
        try:  
            # 检查数据库连接和光标
            self.check_connection_and_cursor()  
            # 获取数据库连接和光标
            conn, cursor = self.get_db_connection()  
            # 执行插入操作
            cursor.execute(f'''  
            INSERT INTO {self.db_table_name} (user_id, user_name, release_date, release_date) VALUES (?, ?, ?, ?)  
            ''', (user_id, user_name, release_date, notes))  
            # 提交更改
            conn.commit()  
            logger.info("[DarkRoom] 新条目已添加。")  
        except sqlite3.IntegrityError:  
            logger.warn("[DarkRoom] 用户 ID 已存在，添加失败。")  
        except sqlite3.Error as e:  
            self.close_db_connection_and_cursor()  
            logger.error(f"[DarkRoom] 数据库错误: {e}")  

    def delete_entry(self, user_id):  
        try:  
            # 检查数据库连接和光标
            self.check_connection_and_cursor()  
            # 获取数据库连接和光标
            conn, cursor = self.get_db_connection()  
            # 执行删除操作
            cursor.execute(f'DELETE FROM {self.db_table_name} WHERE user_id = ?', (user_id,))  
            # 提交更改
            conn.commit()  
            if cursor.rowcount > 0:  
                logger.info(f"[DarkRoom] 用户 ID 为 {user_id} 的条目已删除。")  
            else:  
                logger.warn(f"[DarkRoom] 未找到用户 ID 为 {user_id} 的条目。")  
        except sqlite3.Error as e:  
            self.close_db_connection_and_cursor()  
            logger.error(f"[DarkRoom] 数据库错误: {e}")  

    def update_entry(self, user_id, user_name=None, release_date=None, notes=None):  
        try:  
            # 检查数据库连接和光标
            self.check_connection_and_cursor()  
            # 获取数据库连接和光标
            conn, cursor = self.get_db_connection()  
            query = f"UPDATE {self.db_table_name} SET "  
            updates = []  
            parameters = []  
            if user_name is not None:  
                updates.append("user_name = ?")  
                parameters.append(user_name)  
            if release_date is not None:  
                updates.append("release_date = ?")  
                parameters.append(release_date)  
            if notes is not None:  
                updates.append("notes = ?")  
                parameters.append(notes)  
            if updates:  
                # 构建更新语句
                query += ", ".join(updates) + " WHERE user_id = ?"  
                parameters.append(user_id)  
                # 执行更新语句
                cursor.execute(query, parameters)  
                # 提交更改
                conn.commit()  
                logger.info("[DarkRoom] 条目已更新。")  
            else:  
                logger.warn("[DarkRoom] 未提供更新信息。")  
        except sqlite3.Error as e:  
            self.close_db_connection_and_cursor()  
            logger.error(f"[DarkRoom] 数据库错误: {e}")  

    def get_entry(self, user_id):  
        try:  
            # 检查数据库连接和光标
            self.check_connection_and_cursor()  
            # 获取数据库连接和光标
            conn, cursor = self.get_db_connection()  
            # 执行查询
            cursor.execute(f'SELECT * FROM {self.db_table_name} WHERE user_id = ?', (user_id,))  
            # 提取一条行
            entry = cursor.fetchone()  
            if entry is None:  
                logger.warning(f"没有找到 user_id: {user_id}")  
            return entry   
        except sqlite3.Error as e:  
            self.close_db_connection_and_cursor()  
            logger.error(f"[DarkRoom] 数据库错误: {e}")  
            return None  

    def display_entries(self):  
        try:  
            ret_str = ""  
            # 检查数据库连接和光标  
            self.check_connection_and_cursor()  
            #获取数据库连接和光标
            conn, cursor = self.get_db_connection()  
            # 执行查询
            cursor.execute(f'SELECT user_name, release_date, notes FROM {self.db_table_name}')  
            # 提取所有行
            rows = cursor.fetchall()  
            
            if not rows:  
                # 没有条目  
                ret_str += "[DarkRoom] 牢房里空荡荡的。继续保持喔~😸"  
                logger.warn(ret_str)  
            else:  
                # 打印条目  
                ret_str += "[DarkRoom] 服刑人员名单:"  
                logger.debug(ret_str)  
                for row in rows:  
                    user_name, release_date, notes = row  # 解包选定的字段  
                    ret_str += f"\n[{user_name}] \n    出狱时间: {release_date}\n    入狱原因: {notes}"  
                    logger.debug(f"[DarkRoom] {user_name}, 出狱时间: {release_date}, 入狱原因: {notes}")  

            return ret_str  
        except sqlite3.Error as e:  
            self.close_db_connection_and_cursor()  
            logger.error(f"[DarkRoom] 数据库错误: {e}")  

    def handle_exit(self, signal, frame):  
        """处理退出信号"""  
        # 关闭数据库连接
        logger.info("[DarkRoom] 接收到退出信号，正在关闭数据库连接...")  
        self.close_db_connection_and_cursor()  

    def on_handle_context(self, e_context):  
        """处理上下文事件"""  
        # 检查上下文类型是否为文本  
        if e_context["context"].type not in [ContextType.TEXT]:  
            logger.debug("[DarkRoom] 上下文类型不是文本，无需处理")  
            return  
        # 获取消息内容并去除首尾空格  
        content = e_context["context"].content.strip()   
        # 获取用户信息  
        msg = e_context['context']['msg']  
        user_id = msg.from_user_id  
        user_name = msg.from_user_nickname   
        # 获取时间戳
        current_time = time.time()  
        # 防抖动机制：检查与上一次事件的时间差  
        if user_id in self.last_event_time:  
            if current_time - self.last_event_time[user_id] < 1:
                logger.debug(f"[DarkRoom] 用户 {user_id} 在短时间内重复触发，忽略处理")  
                return  
        # 更新最后事件的时间  
        self.last_event_time[user_id] = current_time  

        # 检查用户的消息跟踪器是否存在  
        if user_id not in self.user_message_tracker:  
            # 初始化消息记录和触发次数  
            self.user_message_tracker[user_id] = {  
                'last_message': None,  # 记录最后一条消息  
                'trigger_count': 0,  # 该用户的触发次数  
                'first_message_time': None  # 记录第一次发消息的时间  
            }  

        # 检查解除命令
        if "~移除" in content:
            # 检查是否有管理员权限
            if self.check_admin_list(user_id):
                #有管理员权限，执行解除操作, 使用正则表达式提取 ~移除 后的内容  
                match = re.search(r'~移除\s*(\S+)', content) 
                release_user_name = match.group(1) if match else ""
                # 创建回复对象
                reply = Reply()
                reply.type = ReplyType.TEXT
                # 执行解除操作
                reply.content = self.delete_entry_by_user_name(release_user_name)
                # 重置计数器
                self.user_message_tracker[user_id]['trigger_count'] = 1  # 重置为1，因为现在是新消息  
                logger.info(f"[DarkRoom] 用户 {user_name} ({user_id}) 已被移出小黑屋，计数器重置。")
                # 回复给用户
                e_context['reply'] = reply
                # 中断事件传递
                e_context.action = EventAction.BREAK_PASS
                return
            else:
                # 创建回复对象
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "你没有管理员权限，无法解除小黑屋。"
                e_context['reply'] = reply
                # 中断事件传递
                e_context.action = EventAction.BREAK_PASS
                return
        elif "~小黑屋" in content:
            # 检查是否有管理员权限
            if self.check_admin_list(user_id):
                # 创建回复对象
                reply = Reply()
                reply.type = ReplyType.TEXT
                # 获取牢房人员名单
                reply.content = self.display_entries()
                # 回复给用户
                e_context['reply'] = reply
                # 中断事件传递
                e_context.action = EventAction.BREAK_PASS
                return
            else:
                # 创建回复对象
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = "你没有管理员权限，无法查看小黑屋。"
                e_context['reply'] = reply
                # 中断事件传递
                e_context.action = EventAction.BREAK_PASS
                return
        else:
            # 检查用户是否在小黑屋中  
            entry = self.get_entry(user_id)  
            if entry:  
                reply = Reply()  
                reply.type = ReplyType.TEXT  
                release_date = entry[2]  
                if release_date < int(datetime.now().timestamp()):  
                    self.delete_entry(user_id)  
                    dark_room_text = "恭喜出狱，欢迎下次再来(bushi"  
                    logger.info(f"[DarkRoom] 用户 {user_name} 已被移除小黑屋。")  
                else:  
                    dark_room_text = f"你已经在牢里了，享受牢饭吧。\n剩余时间: {release_date - int(datetime.now().timestamp())}s"  
                    logger.info(f"[DarkRoom] 用户 {user_name} 已在小黑屋中。")  
                reply.content = dark_room_text  
                e_context['reply'] = reply  
                e_context.action = EventAction.BREAK_PASS   
            else:  
                # 检查消息时间窗内是否有连续相同消息
                current_time = datetime.now()  
                # 检查消息是否与最后一条相同  
                if content == self.user_message_tracker[user_id]['last_message']:  
                    # 如果相同，增加计数  
                    self.user_message_tracker[user_id]['trigger_count'] += 1  
                    logger.info(f"[DarkRoom] 用户 {user_name} ({user_id}) 连续发送相同消息，触发次数: {self.user_message_tracker[user_id]['trigger_count']}")
                else:  
                    # 如果不同，重置计数器  
                    self.user_message_tracker[user_id]['trigger_count'] = 1  # 重置为1，因为现在是新消息  
                    logger.info(f"[DarkRoom] 用户 {user_name} ({user_id}) 连续发送不同消息，重置触发次数。")
                    # 更新最后一条消息和时间  
                    self.user_message_tracker[user_id]['last_message'] = content  
                    self.user_message_tracker[user_id]['first_message_time'] = current_time  
                # 连续相同消息达到3条
                if self.user_message_tracker[user_id]['trigger_count'] >= self.trigger_count:  
                    # 确保用户不在小黑屋中
                    if not self.get_entry(user_id):    
                        # 将用户关进小黑屋 10 分钟  
                        self.add_entry(user_id, user_name, int((current_time + timedelta(minutes=10)).timestamp()), '刷屏')  
                        logger.info(f"[DarkRoom] 用户 {user_name} ({user_id}) 已被关进小黑屋 10 分钟。")  
                        # 回复给用户
                        reply = Reply()  
                        reply.type = ReplyType.TEXT  
                        reply.content = "你在刷屏哦~ 被关进小黑屋10分钟！🙀"  
                        e_context['reply'] = reply  
                        # 中断事件传递
                        e_context.action = EventAction.BREAK_PASS  
                        return  

    def get_help_text(self, **kwargs):  
        """获取帮助文本"""  
        help_text = "违规的人我都要给你关进小黑屋🐾\n"  
        return help_text
