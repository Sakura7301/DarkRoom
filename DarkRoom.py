import os
import time
import plugins
import sqlite3
from datetime import datetime, timedelta
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *
import threading


@plugins.register(
    name="DarkRoom",
    desire_priority=998,
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
        # 存储用户消息计数和触发次数
        self.user_message_tracker = {}
        # 用于存储用户的最后事件时间(防抖动)
        self.last_event_time = {}
        # 加载刷屏限时
        self.message_time_frame = self.config.get("message_time_frame")
        # 加载刷屏最大次数
        self.trigger_count = self.config.get("trigger_count")
        # 加载防抖动间隔
        self.interval_to_prevent_shaking = self.config.get("interval_to_prevent_shaking")
        # 加载封禁时长
        self.duration_of_ban = self.config.get("duration_of_ban")
        # 加载违禁词配置
        self.check_prohibited_words = self.config.get("check_prohibited_words")
        self.prohibited_words = self.config.get("prohibited_words", [])
        # 加载管理员密码
        self.admin_password = self.config.get("admin_password")
        # 初始化管理员列表
        self.admin_list = []
        # 注册事件处理程序
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.info("[DarkRoom] 插件初始化完毕")

    def check_admin_list(self, user_id):
        # 检查关键词
        return any(keyword in user_id for keyword in self.admin_list)

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
        logger.debug("[DarkRoom] 数据库连接和游标已关闭")

    def check_connection_and_cursor(self):
        try:
            # 检查连接和光标是否存在
            self.get_db_connection()
        except sqlite3.Error as e:
            logger.error(f"[DarkRoom] 检查连接和游标时发生错误: {e}")

    def check_and_read_database(self):
        # 检查数据库是否存在
        if not os.path.exists(self.db_name):
            logger.warning(f"[DarkRoom] 数据库 {self.db_name} 不存在，正在创建数据库...")
            try:
                # 连接到数据库
                conn, cursor = self.get_db_connection()
                # 执行创建表操作
                cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {self.db_table_name} (
                    user_id TEXT PRIMARY KEY,
                    user_name TEXT NOT NULL,
                    user_group_name TEXT,
                    release_date INTEGER NOT NULL,
                    notes
                )
                ''')
                # 提交更改
                conn.commit()
                logger.info("[DarkRoom] 数据库已创建")
                logger.info(f"[DarkRoom] 表 {self.db_table_name} 已创建。")
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
                        user_group_name TEXT,
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

    def delete_entry_by_user_id(self, user_name, user_id):
        """
        根据用户ID删除黑名单中的指定条目。

        参数:
        user_id (str): 要删除的用户ID。
        """
        logger.info(f"[DarkRoom] 尝试从小黑屋移除用户 {user_name} {user_id} 。")
        try:
            ret_str = ""
            # 获取数据库连接和光标
            conn, cursor = self.get_db_connection()
            # 构建删除 SQL 语句
            cursor.execute(f'DELETE FROM {self.db_table_name} WHERE user_id = ?', (user_id,))
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
            ret_str = f"[DarkRoom] 数据库错误: {e}, user_id: {user_id}, type: {type(user_id)}"
            logger.error(ret_str)
            return ret_str
        finally:
            # 关闭数据库连接和光标
            self.close_db_connection_and_cursor()

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

    def add_entry(self, user_id, user_name, user_group_name, release_date, notes):
        try:
            # 检查数据库连接和光标
            self.check_connection_and_cursor()
            # 获取数据库连接和光标
            conn, cursor = self.get_db_connection()
            # 执行插入操作
            cursor.execute(f'''
            INSERT INTO {self.db_table_name} (user_id, user_name, user_group_name, release_date, notes) VALUES (?, ?, ?, ?, ?)
            ''', (user_id, user_name, user_group_name, release_date, notes))
            # 提交更改
            conn.commit()
            logger.info(f"[DarkRoom] 新条目已添加: |{user_name}|{user_group_name}|{release_date}|{notes}")
        except sqlite3.IntegrityError:
            logger.warning("[DarkRoom] 用户 ID 已存在，添加失败。")
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
                logger.warning(f"[DarkRoom] 未找到用户 ID 为 {user_id} 的条目。")
        except sqlite3.Error as e:
            self.close_db_connection_and_cursor()
            logger.error(f"[DarkRoom] 数据库错误: {e}")

    def update_entry(self, user_id, user_name=None, user_group_name=None, release_date=None, notes=None):
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
            if user_group_name is not None:
                updates.append("user_group_name =?")
                parameters.append(user_group_name)
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
                logger.warning("[DarkRoom] 未提供更新信息。")
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
                logger.debug(f"没有找到 user_id: {user_id}")
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
            cursor.execute(f'SELECT user_name, user_group_name, release_date, notes FROM {self.db_table_name}')
            # 提取所有行
            rows = cursor.fetchall()

            if not rows:
                # 没有条目
                ret_str += "[DarkRoom] 牢房里空荡荡的。继续保持喔~😸"
                logger.warning(ret_str)
            else:
                # 打印条目
                ret_str += "[DarkRoom] 🐱服刑人员名单:"
                logger.debug(ret_str)
                for row in rows:
                    # 解包选定的字段
                    user_name, user_group_name, release_date, notes = row
                    # 转换时间戳为日期时间对象
                    release_date_dt = datetime.fromtimestamp(int(release_date))
                    # 格式化为 '年月日时'
                    release_date_formatted = release_date_dt.strftime('%Y/%m/%d %H:%M')
                    ret_str += f"\n[{user_name}|{user_group_name}] \n    出狱时间: {release_date_formatted}\n    入狱原因: {notes}"
                    logger.debug(f"[DarkRoom] {user_name}|{user_group_name}, 出狱时间: {release_date}, 入狱原因: {notes}")

            return ret_str
        except sqlite3.Error as e:
            self.close_db_connection_and_cursor()
            logger.error(f"[DarkRoom] 数据库错误: {e}")

    def handle_exit(self, signal, frame):
        """处理退出信号"""
        # 关闭数据库连接
        logger.info("[DarkRoom] 接收到退出信号，正在关闭数据库连接...")
        self.close_db_connection_and_cursor()

    def update_message_tracker(self, content, current_time, user_name, user_id):
        # 检查用户的消息跟踪器是否存在
        if user_id not in self.user_message_tracker:
            # 初始化消息记录和触发次数
            self.user_message_tracker[user_id] = {
                # 记录最后一条消息
                'last_message': content,
                # 该用户的触发次数
                'trigger_count': 1,
                # 记录第一次发消息的时间
                'first_message_time': current_time
            }
        else:
            # 检查消息是否重复
            if (content == self.user_message_tracker[user_id]['last_message']) and (current_time - self.user_message_tracker[user_id]['first_message_time'] <= (self.message_time_frame * 60)):
                    # 如果消息重复，且在5分钟内，增加触发次数
                    self.user_message_tracker[user_id]['trigger_count'] += 1
                    logger.debug(f"[DarkRoom] 用户 {user_name} ({user_id}) 连续发送相同消息，触发次数: {self.user_message_tracker[user_id]['trigger_count']}")
            else:
                # 如果不同，重置计数器为1，因为现在是新消息
                self.user_message_tracker[user_id]['trigger_count'] = 1
                logger.debug(f"[DarkRoom] 用户 {user_name} ({user_id}) 连续发送不同消息，重置触发次数。")
                # 更新最后一条消息和时间
                self.user_message_tracker[user_id]['last_message'] = content
                self.user_message_tracker[user_id]['first_message_time'] = current_time

    def check_user_prohibited_words(self, content, user_name, user_id):
        if self.check_prohibited_words:
            # 检查用户是否触发违禁词
            for word in self.prohibited_words:
                if word in content:
                    logger.info(f"[DarkRoom] 用户 {user_name} ({user_id}) 触发违禁词: {word}")
                    return True  # 触发了违禁词
            return False  # 未触发违禁词
        else:
            # 未开启违禁词检查，不做任何事
            return False

    def check_user_has_violated(self, content, user_name, user_group_name, user_id, e_context):
        # 直接获取当前时间戳并加上10分钟，转换为整数
        new_timestamp = int((datetime.fromtimestamp(time.time()) + timedelta(minutes=self.duration_of_ban)).timestamp())
        logger.debug(f"[DarkRoom] 用户 {user_name} 连续消息数: {self.user_message_tracker[user_id]['trigger_count']}")
        # 连续相同消息达到3条
        if self.user_message_tracker[user_id]['trigger_count'] >= self.trigger_count:
            # 确保用户不在小黑屋中
            if not self.get_entry(user_id):
                # 将用户关进小黑屋 {self.duration_of_ban} 分钟
                self.add_entry(user_id, user_name, user_group_name, new_timestamp, '刷屏')
                logger.info(f"[DarkRoom] 用户 {user_name} 已被关进小黑屋 {self.duration_of_ban} 分钟。")
                # 回复给用户
                reply = Reply()
                reply.type = ReplyType.TEXT
                reply.content = f"你在刷屏哦~ 被关进小黑屋{self.duration_of_ban}分钟！😏"
                e_context['reply'] = reply
                # 中断事件传递
                e_context.action = EventAction.BREAK_PASS
                return
        elif self.check_user_prohibited_words(content, user_name, user_id):
            # 用户违禁
            logger.info(f"[DarkRoom] 用户 {user_name} ({user_id}) 触发违禁词，被关进小黑屋 {self.duration_of_ban} 分钟。😏")
            # 将用户关进小黑屋 {self.duration_of_ban} 分钟
            self.add_entry(user_id, user_name, user_group_name, new_timestamp, '触发违禁词')
            # 回复给用户
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = "违禁词不可以说哦~ 恭喜你被关进小黑屋10分钟！😏\n\n(维持绿色健康沟通环境，人人有责🐾)"
            e_context['reply'] = reply
            # 中断事件传递
            e_context.action = EventAction.BREAK_PASS
            return
        else:
            # 用户未违禁，无需处理
            return

    def display_dark_room(self, user_id):
        # 检查是否有管理员权限
        if self.check_admin_list(user_id):
            # 获取牢房人员名单
            return self.display_entries()
        else:
            # 没有管理员权限，无法查看小黑屋
            return "[DarkRoom] 你没有管理员权限，无法查看小黑屋。😹"

    def authenticate(self, instruct_content, user_id, is_group) -> str:
        if is_group:
            return "[DarkRoom] 请勿在群聊中认证"

        if user_id in self.admin_list:
            return "[DarkRoom] 管理员账号无需认证"

        # 检查密码是否正确
        if instruct_content == self.admin_password:
            # 认证成功，将用户添加到管理员列表中
            self.admin_list.append(user_id)
            return "[DarkRoom] 认证成功"
        else:
            return "[DarkRoom] 认证失败"

    def parse_instruct(self, user_id, msg, content) -> str:
        try:
            # 去除斜杠同时分割指令和参数
            parts = content[1:].split(' ', 1)
            # 获取指令类型和参数
            instruct_type = parts[0]  # 第一个部分是指令类型
            instruct_content = parts[1] if len(parts) > 1 else ''  # 第二部分是指令参数
            logger.info(f"[DarkRoom] 指令类型: {instruct_type}, 指令内容: {instruct_content}")
            # 鉴权
            if instruct_type == "auth":
                # 执行认证操作
                return self.authenticate(instruct_content, user_id, msg.is_group)
            elif instruct_type == "release":
                # 移除小黑屋中的指定用户
                return self.remove_dark_room(instruct_content, user_id)
            elif instruct_type == "show":
                # 查看小黑屋
                return self.display_dark_room(user_id)
            elif instruct_type == "releaseall":
                # 释放所有小黑屋成员
                return self.release_dark_room(user_id)
            else:
                return None
        except Exception as e:
            err_str = f"[DarkRoom] 指令解析错误: {e}"
            logger.error(err_str)
            return err_str

    def get_user_id_by_name_or_group(self, target_name):
        try:
            # 检查数据库连接和光标
            self.check_connection_and_cursor()
            # 获取数据库连接和光标
            conn, cursor = self.get_db_connection()
            # 执行查询，将 user_name 和 user_group_name 同时作为筛选条件
            cursor.execute(f'SELECT user_id FROM {self.db_table_name} WHERE user_name = ? OR user_group_name = ?', (target_name, target_name))
            # 提取一条行
            entry = cursor.fetchone()
            if entry is None:
                logger.debug(f"没有找到与 target_name: {target_name} 匹配的条目")
                return None
            return entry[0]  # 返回找到的第一个条目的 user_id
        except sqlite3.Error as e:
            logger.error(f"[DarkRoom] 数据库错误: {e}")
            return None
        finally:
            # 关闭数据库连接和光标
            self.close_db_connection_and_cursor()

    def remove_dark_room(self, instruct_content, user_id):
        ret_str = None
        target_name = None
        release_user_id = None
        # 检查是否有管理员权限
        if self.check_admin_list(user_id):
            # 获取目标昵称
            if '@' in instruct_content:
                # 获取'@'符号后面的所有内容
                target_name = instruct_content.split('@', 1)[-1]
            else:
                # 直接使用输入值
                target_name = instruct_content
            logger.info(f"[DarkRoom] 需要释放的目标昵称: {target_name}")

            # 根据昵称从数据库查找用户ID
            release_user_id = self.get_user_id_by_name_or_group(target_name)
            if release_user_id is None:
                ret_str = f"[DarkRoom] 找不到与{target_name}匹配的用户。😹"
            else:
                # 根据用户ID移除用户
                ret_str = self.delete_entry_by_user_id(target_name, release_user_id)
                # 重置该用户计数器
                self.user_message_tracker[release_user_id]['trigger_count'] = 1
        else:
            # 没有管理员权限，无法解除小黑屋里的成员
            ret_str = "[DarkRoom] 你没有管理员权限，无法解除小黑屋里的成员。😹"
        return ret_str

    def release_dark_room(self, user_id):
        try:
            # 检查是否有管理员权限
            if self.check_admin_list(user_id):
                # 检查数据库连接和光标
                self.check_connection_and_cursor()
                # 获取数据库连接和光标
                conn, cursor = self.get_db_connection()
                # 执行删除所有操作
                cursor.execute(f'DELETE FROM {self.db_table_name}')
                # 提交更改
                conn.commit()
                logger.info(f"[DarkRoom] 数据表 {self.db_table_name} 中的所有条目已删除。")
                # 重置所有用户的技术
                for user_id in self.user_message_tracker:
                    self.user_message_tracker[user_id]['trigger_count'] = 1
                return "[DarkRoom] 大赦天下！牢房清空辣~😸"
            else:
                return "[DarkRoom] 你没有管理员权限，无法解除小黑屋里的成员。😹"
        except sqlite3.Error as e:
            err_str = f"[DarkRoom] 数据库错误: {e}"
            logger.error(err_str)
            return err_str
        finally:
            # 关闭数据库连接和光标
            self.close_db_connection_and_cursor()

    def check_if_need_remove_user_from_darkroom(self, release_date, user_id, user_name, user_group_name, e_context):
        # 检查是否需要释放用户
        if release_date < int(datetime.now().timestamp()):
            # 释放用户
            self.delete_entry(user_id)
            logger.info(f"[DarkRoom] 用户 {user_name}|{user_group_name} 已被移除小黑屋。")
            return
        else:
            dark_room_text = f"你已经在牢里了，享受牢饭吧。\n剩余时间: {release_date - int(datetime.now().timestamp())}s\n预计出狱时间：{datetime.fromtimestamp(release_date).strftime('%Y/%m/%d %H:%M')}"
            logger.info(f"[DarkRoom] 用户 {user_name}|{user_group_name} 已在小黑屋中。")
            # 回复给用户
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = dark_room_text
            e_context['reply'] = reply
            # 中断事件传递
            e_context.action = EventAction.BREAK_PASS
            return

    def find_user_name_by_user_id(self, msg, user_id):
        """查找指定 UserName 的昵称"""
        user_name = None
        try:
            # 获取成员列表
            members = msg['User']['MemberList']
            # 遍历成员列表
            for member in members:
                # 检查 UserName 是否匹配
                if member['UserName'] == user_id:
                    # 找到昵称
                    user_name =  member['NickName']
        except Exception as e:
            logger.error(f"[DarkRoom] 查找用户昵称失败: {e}")
        return user_name

    def find_user_id_by_nickname(self, msg, user_name):
        """查找指定昵称的 UserID"""
        user_id = None
        try:
            # 获取成员列表
            members = msg['User']['MemberList']

            for member in members:
                # 匹配用户ID
                if member['NickName'] == user_name:
                    # 返回找到的 UserID
                    user_id = member['UserName']
        except Exception as e:
            logger.error(f"[DarkRoom] 查找用户昵称失败: {e}")
        return user_id  # 如果未找到，返回 None

    def on_handle_context(self, e_context):
        """处理上下文事件"""
        # 检查上下文类型是否为文本
        if e_context["context"].type not in [ContextType.TEXT]:
            logger.debug("[DarkRoom] 上下文类型不是文本，无需处理")
            return
        try:
            # 初始化变量
            user_id = None
            user_name = None
            user_group_name = None
            # 获取消息内容并去除首尾空格
            content = e_context["context"].content.strip()
            # 获取用户信息
            msg = e_context['context']['msg']
            # 检查是否为群消息
            if msg.is_group:
                # 群消息，获取真实ID
                user_id = msg._rawmsg['ActualUserName']
            else:
                # 私聊消息，获取用户ID
                user_id = msg.from_user_id
            # 获取秒级时间戳
            current_time = time.time()
            # 防抖动机制：检查与上一次事件的时间差
            if user_id in self.last_event_time:
                if current_time - self.last_event_time[user_id] < self.interval_to_prevent_shaking:
                    logger.debug(f"[DarkRoom] 用户 {user_id} 在短时间内重复触发，忽略处理")
                    return

            # 更新最后事件的时间
            self.last_event_time[user_id] = current_time

            # 检查是否为群消息
            if msg.is_group:
                # 获取真实昵称
                user_name = self.find_user_name_by_user_id(msg._rawmsg, user_id)
                user_group_name = msg.actual_user_nickname
            else:
                user_name = msg.from_user_nickname
            logger.info(f"[DarkRoom] debug[{user_name}|{user_group_name}|{user_id}]的消息")

            # 更新用户消息触发器
            self.update_message_tracker(content, current_time, user_name, user_id)

            # 检查消息类型，是否是命令
            if content.startswith("/"):
                # 获取处理结果
                handle_instruct_result = self.parse_instruct(user_id, msg, content)
                if handle_instruct_result is None:
                    # 无需回复
                    return
                else:
                    # 创建回复对象
                    reply = Reply()
                    reply.type = ReplyType.TEXT
                    reply.content = handle_instruct_result
                    # 回复给用户
                    e_context['reply'] = reply
                    # 中断事件传递
                    e_context.action = EventAction.BREAK_PASS
                    return
            else:
                # 检查用户是否在小黑屋中
                entry = self.get_entry(user_id)
                if entry:
                    # 获取剩余时间
                    release_date = entry[3]
                    # 检查用户是否需要移除小黑屋
                    self.check_if_need_remove_user_from_darkroom(release_date, user_id, user_name, user_group_name, e_context)
                    return
                else:
                    # 管理员不会受到任何限制
                    if self.check_admin_list(user_id) is False:
                        # 检查用户是否有违规行为
                        self.check_user_has_violated(content, user_name, user_group_name, user_id, e_context)
                    return
        except Exception as e:
            logger.error(f"[DarkRoom] 处理上下文事件时出错: {e}")
            return

    def get_help_text(self, **kwargs):
        """获取帮助文本"""
        help_text = "24字核心价值观：\n富强 民主 文明 和谐\n自由 平等 公正 法治\n爱国 敬业 诚信 友善\n\n违规的人会被关进小黑屋哦~🐾\n"
        return help_text
