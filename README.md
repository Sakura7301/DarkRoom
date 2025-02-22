# DarkRoom 插件

## 概述
`DarkRoom` 是为`chatgpt-on-wechat`项目开发的一款用于管理用户行为的插件，主要功能是监控用户消息，检测并处理违规行为。违规用户将被暂时封禁（"关进小黑屋"），以维护良好的交流环境。该插件支持多种配置选项，管理员可以通过简单的命令进行管理。

## 功能特性
- **违规检测**：自动检测并处理用户发送的违规内容，包括触发违禁词或刷屏。
- **用户封禁**：违规用户将被关进小黑屋，限制其在指定时间内的提问权限。
- **管理员管理**：管理员可以通过命令移除用户，查看当前被封禁的用户列表。
- **防抖动机制**：防止用户在短时间内频繁发送相同的消息，同时也防止`chatgpt-on-wechat`多次回调导致频繁处理。
- **日志记录**：记录所有关键操作和异常信息，便于后续审计。

## 安装
- 方法一：
  - 载的插件文件都解压到`plugins`文件夹的一个单独的文件夹，最终插件的代码都位于`plugins/PLUGIN_NAME/*`中。启动程序后，如果插件的目录结构正确，插件会自动被扫描加载。除此以外，注意你还需要安装文件夹中`requirements.txt`中的依赖。

- 方法二(推荐)：
  - 借助`Godcmd`插件，它是预置的管理员插件，能够让程序在运行时就能安装插件，它能够自动安装依赖。
    - 使用 `#installp git@github.com:Sakura7301/DarkRoom.git` 命令自动安装插件
    - 在安装之后，需要执行`#scanp`命令来扫描加载新安装的插件。
    - 创建`config.json`文件定义你需要的内容，可以参照`config.json.template`。
    - 插件扫描成功之后需要手动使用`#enablep DarkRoom`命令来启用插件。


## 配置
在插件的配置文件中，你可以设置以下选项：
- `admin_password`: 管理员密码。
- `message_time_frame`: 设置刷屏的时间窗口（分钟）。
- `trigger_count`: 设置触发刷屏惩罚的最大消息数。
- `interval_to_prevent_shaking`: 设置防抖动机制的时间间隔（秒）。
- `duration_of_ban`: 设置用户被关进小黑屋的持续时间（分钟）。
- `check_prohibited_words`: 启用或禁用违禁词检查。
- `prohibited_words`: 列出需要检测的违禁词。

## 命令示例
- `/auth 您设置的密码` - 管理员用户认证(默认密码为`7301`，见config.json)。
- `/show` - 查看当前所有被关进小黑屋的用户。
- `/release 用户名` - 移除指定的用户出小黑屋。
- `/release @用户名` - 移除指定的用户出小黑屋。
- `/releaseall` - 释放所有被关进小黑屋的用户。

## 日志
所有的行为和事件都将被记录在日志文件中，包括：
- 用户被关进小黑屋的时间和原因。
- 管理员的操作记录。
- 数据库相关的错误，便于排查问题。

## 注意事项
- 确保你有权限操作和查看小黑屋。
- 定期检查和清理被封禁的用户列表。

## 贡献
欢迎任何形式的贡献，包括报告问题、请求新功能或提交代码。你可以通过以下方式与我们联系：

- 提交 issues 到项目的 GitHub 页面。
- 发送邮件至 [sakuraduck@foxmail.com]。

## 赞助
开发不易，我的朋友，如果你想请我喝杯咖啡的话(笑)

<img src="https://github.com/user-attachments/assets/db273642-1787-4195-af52-7b14c8733405" alt="image" width="300"/> 


## 许可
此项目采用 Apache License 版本 2.0，详细信息请查看 [LICENSE](LICENSE)。

---
