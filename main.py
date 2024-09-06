import os
import discord
import json
import re
import time
import string
import datetime
from discord.abc import GuildChannel
import asyncio
from discord.ui import Modal, Button, View, TextInput  #モーダル関連
from collections import defaultdict, deque

from discord import app_commands
from discord.ext import commands, tasks
from datetime import timedelta

# インテントの生成
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# botの定義
bot = commands.Bot(intents=intents, command_prefix="$", max_messages=10000)
tree = bot.tree

### -----on_ready------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}.")
    await tree.sync()
    print("Synced slash commands.")

    """設定をファイルから読み込む"""
    global config
    global server_timezone

    if os.path.exists(CONFIG_FILE):
        # 初期設定の読み込み
        config = load_config(CONFIG_FILE)
    else:
        config = {}    
    if config.get('server_timezone', "UTC") == "JST":# タイムゾーンを定義
        JST = datetime.timezone(timedelta(hours=+9), 'JST')
        server_timezone = JST
    else:
        UTC = datetime.timezone(timedelta(hours=+0), 'UTC')
        server_timezone = UTC

    # ループ起動
    check_threads_2nd.start()

### スラッシュコマンド
# スレ立て
@tree.command(name="スレ立て", description="指定したチャンネルでスレッドを作成します")
@app_commands.describe(
    親チャンネル="スレッドを作成するチャンネルを選択します",
    画像="スレ立て時に添付する画像を指定できます",
    ロックまでの時間="設定すると、指定時間（分）経過後に書き込みできなくなります（0-1440）",
    削除までの時間="設定すると、ロック後にここで指定した時間（分）経過後にスレッドを削除します（0-1440）"
)
async def make_thread(
    interaction: discord.Interaction,
    親チャンネル: discord.ForumChannel,
    画像: discord.Attachment = None,
    ロックまでの時間: int = 0,
    削除までの時間: int = 0
):
    # 入力チェック
    if not (0 <= ロックまでの時間 <= 1440) or not (0 <= 削除までの時間 <= 1440):
        await interaction.response.send_message("時間は0から1440までで",ephemeral=True)
        return
  
    # モーダルの定義
    class ThreadModal(Modal):
        def __init__(self):
            super().__init__(title="スレッドを作成")

            # モーダルフィールドの設定
            self.add_item(TextInput(label="スレタイ", placeholder="スレッドのタイトルを入力（100文字まで・省略不可）",max_length=150, style=discord.TextStyle.short))
            self.add_item(TextInput(label="本文", placeholder="スレッドの本文を入力", style=discord.TextStyle.paragraph, required=False))
            self.add_item(TextInput(label="管理キー（変更したほうがいいよ）", placeholder="あとで使える管理用パスワードを入力（20文字まで）",max_length=20, style=discord.TextStyle.short, default="0721"))

        async def on_submit(self, interaction: discord.Interaction):
            # モーダル入力内容の取得
            title = self.children[0].value
            content = self.children[1].value
            password = self.children[2].value
            if ロックまでの時間 == 0:
                lock_time = 0
                lock_time_str = "0"
                delete_time = 削除までの時間
                delete_time_str = str(削除までの時間)
            elif 削除までの時間 == 0:
                lock_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=ロックまでの時間)
                lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                delete_time = 0
                delete_time_str = "0"
            else:
                lock_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=ロックまでの時間)
                lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                delete_time = lock_time + datetime.timedelta(minutes=削除までの時間)
                delete_time_str = delete_time.strftime('%Y年%m月%d日%H時%M分')

            # 入力チェック
            if not title:
                await interaction.response.send_message("スレッドのタイトルを入力してください",ephemeral=True)
                return
            if not content:
                content = "ｷﾀ━━━━(ﾟ∀ﾟ)━━━━!!"


            # ロック・削除までの時間を追記
            if lock_time != 0:
                content += f"\n`このスレッドは{lock_time_str}くらいに書き込めなくなります`"
            else:
                content += "\n`※このスレッドは落ちません`"
            if delete_time != 0 and lock_time != 0:
                content += f"\n`このスレッドは{delete_time_str}くらいに消えます`"
            elif delete_time == 0:
                content += "\n`※このスレッドは消えません…たぶんね`"
            else:
                content += f"\n`※このスレッドはまだ消えませんが、スレ落ち後{削除までの時間}分で消えます`"

            # スレッドの作成
            if 画像:
                thread = await 親チャンネル.create_thread(name=title, content=content,file=await 画像.to_file())
            else:
                thread = await 親チャンネル.create_thread(name=title, content=content)

            # スターターメッセージをピン留め
            await thread.message.pin()

            # JSONデータの保存
            data = load_config(CREATED_THREAD_LIST)
            data[thread.thread.id] = {
                "guild": thread.thread.guild.id,
                "lock_time": [ロックまでの時間,lock_time_str],
                "delete_time": [削除までの時間,delete_time_str],
                "password": password
            }
            save_config(data, CREATED_THREAD_LIST)
            await interaction.response.send_message(f"スレッド '{title}' が作成されました。\nリンク→{thread.thread.jump_url}",ephemeral=True)

    # モーダル表示
    await interaction.response.send_modal(ThreadModal())

# スレ管理
@tree.command(name="スレ管理", description="スレッドの管理をする")
@app_commands.describe(
    管理キー="スレッド作成時に設定した管理キーを入力します",
    内容="設定（変更）内容を選んでね"
)
@app_commands.choices(内容=[
    app_commands.Choice(name="スレッドタイトル変更", value="0"),
    app_commands.Choice(name="スレ落ち（自動ロック）時間再設定", value="1"),
    app_commands.Choice(name="スレ削除時間再設定", value="2"),
    app_commands.Choice(name="スレッドのロック（書き込み停止）", value="3"),
    app_commands.Choice(name="スレッドの削除", value="4")
])
async def manage_thread(
    interaction: discord.Interaction,
    管理キー: str,
    内容: str
):
    channel_key = str(interaction.channel_id)
    data = load_config(CREATED_THREAD_LIST)

    # 入力チェック
    if channel_key not in data:
        await interaction.response.send_message("botが作成したスレッドじゃないみたい（終了）",ephemeral=True)
        return
    elif data[channel_key]["password"] != 管理キー:
        await interaction.response.send_message("管理キーが違うみたい（終了）",ephemeral=True)
        return

    # モーダルの定義
    class ThreadManageModal(Modal):
        def __init__(self):
            super().__init__(title="スレッドを管理")

            # モーダルフィールドの設定
            if 内容 == "0": # タイトル変更
                self.add_item(TextInput(label="変更後のスレタイを入力", placeholder="100文字まで",max_length=100, style=discord.TextStyle.short))
            if 内容 == "1": # 自動ロック時間変更
                self.add_item(TextInput(label="スレ落ち（自動ロック）時間（分）※いまから", placeholder="0～1440までの数字を入れる（0ならスレ落ちしない）",max_length=4, style=discord.TextStyle.short))
            elif 内容 == "2": # 自動削除時間変更
                self.add_item(TextInput(label="スレ自動削除時間（分）※スレ落ち後の時間", placeholder="0～1440までの数字を入れる（0なら自動削除しない）",max_length=4, style=discord.TextStyle.short))
            elif 内容 == "3": # スレッドをロック
                self.add_item(TextInput(label="スレッドのロック（最終確認）", placeholder="ここに「1041」を入れて送信する",max_length=4, style=discord.TextStyle.short))
            elif 内容 == "4": # スレッドを削除
                self.add_item(TextInput(label="スレッドの削除（最終確認）", placeholder="ここに「1041」を入れて送信する",max_length=4, style=discord.TextStyle.short))

        async def on_submit(self, interaction: discord.Interaction):
            # jsonを取得して元の管理情報を変換して変数に入れる
            data = load_config(CREATED_THREAD_LIST)
            ロックまでの時間 = data[channel_key]["lock_time"][0]
            削除までの時間 = data[channel_key]["delete_time"][0]
            lock_time_str = "0"
            lock_time = 0
            delete_time_str = "0"
            delete_time = 0
            if ロックまでの時間 == 0:
                if 削除までの時間 == 0: # [自動ロックしない：自動削除しない]の処理
                    pass
                else: # [自動ロックしない：自動削除する]の処理
                    delete_time_str = data[channel_key]["delete_time"][1] #この場合のみ、数値が文字列化されて格納されている
                    delete_time = int(delete_time_str)
            else:
                if 削除までの時間 == 0: # [自動ロックする　：自動削除しない]の処理
                    lock_time_str = data[channel_key]["lock_time"][1]
                    lock_time = datetime.datetime.strptime(lock_time_str, '%Y年%m月%d日%H時%M分')
                else: # [自動ロックする　：自動削除する]の処理
                    lock_time_str = data[channel_key]["lock_time"][1]
                    lock_time = datetime.datetime.strptime(lock_time_str, '%Y年%m月%d日%H時%M分')
                    delete_time_str = data[channel_key]["delete_time"][1]
                    delete_time = datetime.datetime.strptime(delete_time_str, '%Y年%m月%d日%H時%M分')
            # スターターメッセージを取得
            message = await interaction.channel.fetch_message(interaction.channel_id)
            
            # モーダル入力内容の取得
            try:
                modal_value = int(self.children[0].value)
            except Exception:
                await interaction.response.send_message("入力が変",ephemeral=True)
                return

            if 内容 == "0":
                await interaction.channel.edit(name=self.children[0].value)
                await interaction.response.send_message("変更完了",ephemeral=True)
                return
            else: # モーダル入力内容の取得・int化
                try:
                    modal_value = int(self.children[0].value)
                except Exception:
                    await interaction.response.send_message("入力が変",ephemeral=True)
                    return
                    
            if 内容 == "1":
                if not (0 <= modal_value <= 1440):
                    await interaction.response.send_message("時間は0から1440までで",ephemeral=True)
                    return
                ロックまでの時間 = modal_value
                if modal_value != 0: # ロックする場合
                    lock_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=modal_value)
                    lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                    if 削除までの時間 != 0: # 削除設定があった場合は時刻を更新
                        delete_time = lock_time + datetime.timedelta(minutes=削除までの時間)
                else:
                    lock_time = 0 # ロックしない場合
                    if isinstance(delete_time,datetime.datetime): # もともとロックする設定だった場合はdelete_timeにdatetimeではなくint（分）を入れなおす
                        delete_time = 削除までの時間
                        delete_time_str = "0"
            elif 内容 == "2":
                if not (0 <= modal_value <= 1440):
                    await interaction.response.send_message("時間は0から1440までで",ephemeral=True)
                    return
                削除までの時間 = modal_value
                if modal_value != 0: # 自動削除する場合
                    delete_time = message.created_at.astimezone(server_timezone) + datetime.timedelta(minutes=ロックまでの時間) + datetime.timedelta(minutes=modal_value)
                    delete_time_str = delete_time.strftime('%Y年%m月%d日%H時%M分')
                else:
                    delete_time = 0
                    delete_time_str = "0"
            elif 内容 == "3":
                lock_time = datetime.datetime.now(server_timezone)
                lock_time_str = lock_time.strftime('%Y年%m月%d日%H時%M分')
                if not (modal_value == 1041):
                    await interaction.response.send_message("最終確認失敗",ephemeral=True)
                    return
                if delete_time != 0:
                    delete_time = datetime.datetime.now(server_timezone) + datetime.timedelta(minutes=削除までの時間)
                    delete_time_str = delete_time.strftime('%Y年%m月%d日%H時%M分')
            elif 内容 == "4":
                if not (modal_value == 1041):
                    await interaction.response.send_message("最終確認失敗",ephemeral=True)
                    return
                await interaction.response.send_message("done",ephemeral=True)
                await interaction.channel.delete()
                del data[str(interaction.channel_id)]
                save_config(data, CREATED_THREAD_LIST)
                return

            # スレ本文を編集
            matches = [match.start() for match in re.finditer('`', message.content)]
            target_index = matches[-4] -1
            new_content = message.content[:target_index]

            # ロック・削除までの時間を削除して追記
            if ロックまでの時間 == 0 and 内容 != "3":
                new_content += "\n`※このスレッドは落ちません`"
            elif ロックまでの時間 != 0 and 内容 != "3":
                new_content += f"\n`このスレッドは{lock_time_str}くらいに書き込めなくなります`"
            else:
                new_content += "\n`※このスレッドは書き込めなくなりました`"
            if 削除までの時間 == 0:
                new_content += "\n`※このスレッドは消えません…たぶんね`"
            elif 削除までの時間 != 0 and ロックまでの時間 == 0 and 内容 != "3":
                new_content += f"\n`※このスレッドはまだ消えませんが、スレ落ち後{削除までの時間}分で消えます`"
            else:
                new_content += f"\n`このスレッドは{delete_time_str}くらいに消えます`"
            await message.edit(content=new_content)
            
            # jsonに戻す
            data[channel_key]["delete_time"][0] = 削除までの時間
            data[channel_key]["lock_time"][0] = ロックまでの時間
            data[channel_key]["delete_time"][1] = delete_time_str
            data[channel_key]["lock_time"][1] = lock_time_str
            save_config(data, CREATED_THREAD_LIST)

            # 処理内容に応じたメッセージを送信
            if 内容 == "3":
                await interaction.channel.edit(locked=True,archived=True)
                await interaction.response.send_message("スレッドを手動でロックしました。もう書き込みできないねえ")
            else:
                await interaction.response.send_message("スレッドの設定を変更しました")
            
    # モーダル表示
    await interaction.response.send_modal(ThreadManageModal())

### ループ
# スレッドの時限停止処理
@tasks.loop(seconds=300)
async def check_threads_2nd():
    created_thread_list = load_config(CREATED_THREAD_LIST)
    now = datetime.datetime.today().astimezone(server_timezone)
    # リストにあるスレッドのロック時間が経過しているかを確認する
    for thread_id,config in list(created_thread_list.items()):
        # json読み込み
        guild = bot.get_guild(config["guild"])
        thread = guild.get_channel_or_thread(int(thread_id))
        print(thread)
        if not thread: # スレッドが存在しない（取得できない）場合はリストから消す
            del created_thread_list[thread_id]
            save_config(created_thread_list,CREATED_THREAD_LIST)
            continue
        if thread.flags.pinned: # ピン留めされてるスレッドは触らない
            continue
        ロックまでの時間 = config["lock_time"][0]
        削除までの時間 = config["delete_time"][0]
        lock_time_str = config["lock_time"][1]
        delete_time_str = config["delete_time"][1]
        try:
            lock_time = datetime.datetime.strptime(lock_time_str, '%Y年%m月%d日%H時%M分').astimezone(server_timezone)
        except Exception:
            pass
        try:
            delete_time = datetime.datetime.strptime(delete_time_str, '%Y年%m月%d日%H時%M分').astimezone(server_timezone)
        except Exception:
            pass
        now = datetime.datetime.now(server_timezone)
        
        # ロック・クローズ処理　※クローズしたスレッドは取り出すのが面倒なので削除予定がある場合はロックのみ
        if ロックまでの時間 != 0:
            if not thread.locked:
                if now > lock_time:# ロック予定時刻を過ぎてたら
                    if delete_time_str == "0":
                        thread_embed = discord.Embed(
                            title='',
                            description="このスレッドはロックされました。過去ログとして保管されています。",
                            color=0x3498db  # 色を指定 (青色)
                        )
                        await thread.send(embed=thread_embed)
                        await thread.edit(archived=True, locked=True)
                        del created_thread_list[thread_id]
                        save_config(created_thread_list,CREATED_THREAD_LIST)
                    else:
                        thread_embed = discord.Embed(
                            title='',
                            description=f"このスレッドはロックされました。そのうち消えます（削除予定：{delete_time_str}）",
                            color=0x3498db  # 色を指定 (青色)
                        )
                        await thread.send(embed=thread_embed)
                        await thread.edit(locked=True)
                elif now > lock_time - datetime.timedelta(minutes=5): # ロック予定時刻5分前を切ってたら
                    description="このスレッドは古いのでもうすぐ書き込めなくなります（ロック予定：5分後）"
                    thread_embed = discord.Embed(
                        title='',
                        description=description,
                        color=0x3498db  # 色を指定 (青色)
                    )
                    await thread.send(embed=thread_embed)

        # 削除処理
        if 削除までの時間 != 0:
            if now > delete_time:
                await thread.delete()
                del created_thread_list[thread_id]
                save_config(created_thread_list,CREATED_THREAD_LIST)
                print(f"Thread '{thread.name}' deleted.")
    
@check_threads.before_loop
async def before_check_threads_2nd():
    await bot.wait_until_ready()


# クライアントの実行
bot.run(os.environ["TOKEN"])
