from __future__ import annotations
import asyncio
import ctypes
import json
import sys
from datetime import datetime
from html import escape

import quota
import kimi
import service_providers
import settings
import newapi
import diagnostics
import sub2api
import vault
from ui_actions import VaultActions

XAML = r'''<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Background="{ThemeResource ApplicationPageBackgroundThemeBrush}" Padding="28,24,28,28" RowSpacing="22">
  <Grid.RowDefinitions>
    <RowDefinition Height="Auto" />
    <RowDefinition Height="*" />
  </Grid.RowDefinitions>
  <Grid ColumnSpacing="16">
    <Grid.ColumnDefinitions>
      <ColumnDefinition Width="*" />
      <ColumnDefinition Width="Auto" />
    </Grid.ColumnDefinitions>
    <StackPanel Spacing="5">
      <TextBlock Text="订阅额度" FontSize="30" FontWeight="SemiBold" />
      <TextBlock Text="多家 Coding / Token / Agent Plan 与 API 账户余额" Foreground="{ThemeResource TextFillColorSecondaryBrush}" TextWrapping="Wrap" />
    </StackPanel>
    <StackPanel Grid.Column="1" Orientation="Horizontal" Spacing="10" VerticalAlignment="Center">
      <Button x:Name="ImportFile" Content="导入文件" Click="ImportFile_Click" />
      <Button x:Name="SaveFile" Content="保存到文件" Click="SaveFile_Click" />
    </StackPanel>
  </Grid>
  <Grid Grid.Row="1" ColumnSpacing="24">
    <Grid.ColumnDefinitions>
      <ColumnDefinition Width="360" />
      <ColumnDefinition Width="*" />
    </Grid.ColumnDefinitions>
    <ScrollViewer Grid.Column="0" VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled">
      <StackPanel Spacing="16" Padding="0,0,4,8">
        <ComboBox x:Name="Source" Header="查询服务" HorizontalAlignment="Stretch" SelectedIndex="0" SelectionChanged="Source_Changed">
          <ComboBoxItem Content="GLM Coding Plan" />
          <ComboBoxItem Content="GPT / Codex · sub2api" />
          <ComboBoxItem Content="Kimi Coding Plan" />
          <ComboBoxItem Content="Claude Code" />
          <ComboBoxItem Content="阿里百炼 Token Plan" />
          <ComboBoxItem Content="阿里百炼 Coding Plan" />
          <ComboBoxItem Content="方舟 Agent Plan · 个人版" />
          <ComboBoxItem Content="小米 MiMo Token Plan" />
          <ComboBoxItem Content="讯飞星火 Coding Plan" />
          <ComboBoxItem Content="讯飞 Astron Token Plan" />
          <ComboBoxItem Content="DeepSeek API 余额" />
          <ComboBoxItem Content="小米 MiMo API 余额" />
        </ComboBox>
        <Button x:Name="ResetConnection" Content="更换连接（清除本机保存）" Click="ResetConnection_Click" HorizontalAlignment="Stretch" />
        <Border Padding="20" CornerRadius="12" Background="{ThemeResource CardBackgroundFillColorDefaultBrush}" BorderBrush="{ThemeResource CardStrokeColorDefaultBrush}" BorderThickness="1" x:Name="GlmPanel">
          <StackPanel Spacing="14">
            <ComboBox x:Name="Site" Header="服务站点" HorizontalAlignment="Stretch" SelectedIndex="0" SelectionChanged="Site_Changed">
              <ComboBoxItem Content="智谱 BigModel · 国内" />
              <ComboBoxItem Content="Z.ai · 海外" />
            </ComboBox>
            <PasswordBox x:Name="Key" Header="Coding Plan API Key" PlaceholderText="粘贴你的 API Key" PasswordRevealMode="Hidden" MaxLength="2048" />
            <CheckBox x:Name="Remember" Content="记住 Key（Windows 本机加密）" Unchecked="Remember_Unchecked" Visibility="Collapsed" />
            <Grid ColumnSpacing="14">
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="Auto" />
                <ColumnDefinition Width="*" />
              </Grid.ColumnDefinitions>
              <Button x:Name="Query" Content="查询额度" Style="{StaticResource AccentButtonStyle}" Click="Query_Click" MinWidth="130" />
              <StackPanel Grid.Column="1" Orientation="Horizontal" Spacing="10" VerticalAlignment="Center">
                </StackPanel>
            </Grid>
          </StackPanel>
        </Border>
        <Border x:Name="KimiPanel" Visibility="Collapsed" Padding="20" CornerRadius="12" Background="{ThemeResource CardBackgroundFillColorDefaultBrush}" BorderBrush="{ThemeResource CardStrokeColorDefaultBrush}" BorderThickness="1">
          <StackPanel Spacing="14">
            <TextBlock Text="Kimi Coding Plan" FontSize="18" FontWeight="SemiBold" />
            <PasswordBox x:Name="KimiKey" Header="Kimi Coding Plan API Key" PlaceholderText="粘贴 Kimi Coding Plan Key" PasswordRevealMode="Hidden" MaxLength="2048" />
            <TextBlock Text="使用 Kimi Code 套餐 Key，查询周额度和周期额度；开放平台余额 Key 不适用。" FontSize="12" TextWrapping="Wrap" Foreground="{ThemeResource TextFillColorSecondaryBrush}" />
            <Button x:Name="KimiQuery" Content="查询 Kimi 额度" Style="{StaticResource AccentButtonStyle}" Click="KimiQuery_Click" HorizontalAlignment="Stretch" />
          </StackPanel>
        </Border>
        <Border x:Name="ServicePanel" Visibility="Collapsed" Padding="20" CornerRadius="12" Background="{ThemeResource CardBackgroundFillColorDefaultBrush}" BorderBrush="{ThemeResource CardStrokeColorDefaultBrush}" BorderThickness="1">
          <StackPanel Spacing="14">
            <TextBlock x:Name="ServiceLabel" FontSize="18" FontWeight="SemiBold" TextWrapping="Wrap" />
            <TextBlock x:Name="ServiceDescription" FontSize="12" TextWrapping="Wrap" Foreground="{ThemeResource TextFillColorSecondaryBrush}" />
            <PasswordBox x:Name="ServiceKey" Header="访问凭据" PasswordRevealMode="Hidden" MaxLength="32768" />
            <PasswordBox x:Name="ServiceSecret" Header="辅助凭据" PasswordRevealMode="Hidden" MaxLength="32768" Visibility="Collapsed" />
            <PasswordBox x:Name="ServiceSession" Header="会话凭据" PasswordRevealMode="Hidden" MaxLength="32768" Visibility="Collapsed" />
            <Button x:Name="ServiceQuery" Content="查询当前服务" Style="{StaticResource AccentButtonStyle}" Click="ServiceQuery_Click" HorizontalAlignment="Stretch" />
          </StackPanel>
        </Border>
        <Expander x:Name="NewAPIExpander" Header="从 New API 登录并导入（可选）" HorizontalAlignment="Stretch" HorizontalContentAlignment="Stretch">
          <StackPanel Spacing="12">
            <TextBox x:Name="NewURL" Header="New API 地址" PlaceholderText="https://newapi.example.com" />
            <TextBox x:Name="NewUsername" Header="账号（需要超级管理员 root）" PlaceholderText="New API 用户名" />
            <PasswordBox x:Name="NewPassword" Header="密码（仅用于本次登录，不保存）" PasswordRevealMode="Hidden" />
            <PasswordBox x:Name="LoginCode" Header="登录用 2FA 验证码（需要时填写）" PasswordRevealMode="Hidden" MaxLength="128" />
            <Expander Header="登录高级选项" HorizontalAlignment="Stretch" HorizontalContentAlignment="Stretch">
              <TextBox x:Name="Turnstile" Header="Turnstile Token（仅站点启用时）" PlaceholderText="普通站点留空" MaxLength="4096" />
            </Expander>
            <Button x:Name="LoginButton" Content="登录并加载渠道" Click="Login_Click" />
            <TextBlock x:Name="LoginState" Text="尚未登录" TextWrapping="Wrap" Foreground="{ThemeResource TextFillColorSecondaryBrush}" />
            <ComboBox x:Name="Channels" Header="选择渠道（GLM 相关渠道优先）" PlaceholderText="登录后选择渠道" HorizontalAlignment="Stretch" SelectionChanged="Channel_Changed" />
            <PasswordBox x:Name="ReadCode" Header="读取 Key 用 2FA 验证码（登录后填新的码）" PasswordRevealMode="Hidden" MaxLength="128" />
            <Button x:Name="ImportButton" Content="读取渠道 Key" Click="Import_Click" IsEnabled="False" />
            <ComboBox x:Name="ImportedKeys" Header="选择已导入的 Key" HorizontalAlignment="Stretch" Visibility="Collapsed" SelectionChanged="ImportedKey_Changed" />
            <TextBlock Text="导入后点击上方查询额度。New API 登录凭据仅保留在内存中。Passkey 验证请在后台完成后手动粘贴 GLM Key。" FontSize="12" TextWrapping="Wrap" Foreground="{ThemeResource TextFillColorSecondaryBrush}" />
          </StackPanel>
        </Expander>
        <Border x:Name="SubPanel" Visibility="Collapsed" Padding="20" CornerRadius="12" Background="{ThemeResource CardBackgroundFillColorDefaultBrush}" BorderBrush="{ThemeResource CardStrokeColorDefaultBrush}" BorderThickness="1">
          <StackPanel Spacing="12">
            <TextBlock Text="连接 sub2api" FontSize="18" FontWeight="SemiBold" />
            <TextBox x:Name="SubURL" Header="sub2api 站点地址" PlaceholderText="https://sub.example.com" />
            <TextBox x:Name="SubEmail" Header="sub2api 管理员邮箱" PlaceholderText="用于登录 sub2api 后台" />
            <PasswordBox x:Name="SubPassword" Header="sub2api 密码（本机加密保存）" PasswordRevealMode="Hidden" PlaceholderText="首次输入，随后加密保存" />
            <PasswordBox x:Name="SubCode" Header="2FA 验证码（需要时填写）" PasswordRevealMode="Hidden" MaxLength="6" Visibility="Collapsed" />
            <Expander Header="登录高级选项" HorizontalAlignment="Stretch" HorizontalContentAlignment="Stretch">
              <TextBox x:Name="SubCaptcha" Header="Turnstile Token（如启用）" PlaceholderText="普通站点留空" MaxLength="4096" />
            </Expander>
            <Button x:Name="SubLogin" Content="登录并加载 GPT 账号" Click="SubLogin_Click" HorizontalAlignment="Stretch" Visibility="Collapsed" />
            <TextBlock x:Name="SubState" Text="首次填写，成功后本机加密保存；以后直接查询。" TextWrapping="Wrap" FontSize="12" Foreground="{ThemeResource TextFillColorSecondaryBrush}" />
            <ComboBox x:Name="SubAccounts" Header="选择 GPT / OpenAI 账号" PlaceholderText="登录后选择账号" HorizontalAlignment="Stretch" SelectionChanged="SubSelection_Changed" Visibility="Collapsed" />
            <ComboBox x:Name="SubMode" Header="额度来源" SelectedIndex="0" HorizontalAlignment="Stretch" SelectionChanged="SubSelection_Changed">
              <ComboBoxItem Content="实时查询（经 sub2api）" />
              <ComboBoxItem Content="后台快照（兼容旧版本）" />
            </ComboBox>
            <Button x:Name="SubQuery" Content="查询全部 GPT 账号" Style="{StaticResource AccentButtonStyle}" IsEnabled="True" HorizontalAlignment="Stretch" Click="SubQuery_Click" />
            <TextBlock Text="这里填写 sub2api 后台登录信息。GPT 账号需已导入该后台，无需提供 OpenAI API Key。" FontSize="12" TextWrapping="Wrap" Foreground="{ThemeResource TextFillColorSecondaryBrush}" />
          </StackPanel>
        </Border>
      </StackPanel>
    </ScrollViewer>
    <ScrollViewer Grid.Column="1" VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled">
      <StackPanel Spacing="16" Padding="0,0,4,8">
        <Grid ColumnSpacing="12">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*" />
            <ColumnDefinition Width="Auto" />
            <ColumnDefinition Width="Auto" />
          </Grid.ColumnDefinitions>
          <TextBlock Text="GLM Coding Plan 额度" FontSize="20" FontWeight="SemiBold" VerticalAlignment="Center" x:Name="ResultsTitle" TextWrapping="Wrap" />
          <TextBlock x:Name="Updated" Text="手动查询" FontSize="12" Foreground="{ThemeResource TextFillColorSecondaryBrush}" VerticalAlignment="Center" TextWrapping="Wrap" Grid.Column="2" MaxWidth="220" HorizontalAlignment="Right" />
          <ProgressRing x:Name="Loading" IsActive="False" Width="20" Height="20" Visibility="Collapsed" Grid.Column="1" VerticalAlignment="Center" />
        </Grid>
        <InfoBar x:Name="Notice" IsOpen="True" IsClosable="False" Severity="Informational" Title="准备就绪" Message="输入 Key 后点击查询。仅查询套餐用量。" />
        <StackPanel x:Name="Cards" Spacing="12" />
        <Expander x:Name="RawExpander" Header="查看接口原始数据" HorizontalAlignment="Stretch" Visibility="Collapsed" HorizontalContentAlignment="Stretch">
          <TextBox x:Name="Raw" IsReadOnly="True" AcceptsReturn="True" TextWrapping="Wrap" FontFamily="Consolas" FontSize="12" MaxHeight="300" />
        </Expander>
        <TextBlock Text="百分比按接口返回的使用比例展示；未返回具体次数或重置时间时，不做推算。仅勾选记住并成功查询后保存 Key。" FontSize="12" Foreground="{ThemeResource TextFillColorSecondaryBrush}" TextWrapping="Wrap" x:Name="Footnote" />
      </StackPanel>
    </ScrollViewer>
  </Grid>
</Grid>'''


def launch(*, test_hook=None):
    # Imports initialize the native WinUI 3 runtime. Keep startup failures visible in the EXE.
    from win32more.Microsoft.UI.Xaml import Window, Visibility
    from win32more.Microsoft.UI.Xaml.Controls import InfoBarSeverity
    from win32more.Microsoft.UI.Xaml.Markup import XamlReader
    from win32more.Microsoft.UI.Xaml.Media import MicaBackdrop
    from win32more.Windows.Graphics import SizeInt32
    from win32more.winui3 import XamlApplication, XamlLoader

    class App(VaultActions, XamlApplication):
        def OnLaunched(self, args):
            self.initializing = True
            self.busy = False
            self.card_busy = False
            self.newapi_client = None
            self.channel_rows = []
            self.imported_keys = []
            self.sub_client = None
            self.sub_accounts = []
            self.initialize_vault(test_mode=test_hook is not None)
            self.win = Window()
            self.win.Title = "订阅额度 · 多服务 · 1.5"
            self.win.SystemBackdrop = MicaBackdrop()
            self.win.Content = XamlLoader.Load(self, XAML)
            self.win.AppWindow.Resize(SizeInt32(Width=1200, Height=880))
            self.Source.SelectedIndex = self.vault_data["source"]
            self.restore_fields()
            self.initializing = False
            self.Source_Changed(None, None)
            if self.vault_load_error:
                self.message("本机连接无法解密", self.vault_load_error, "Warning")
            if test_hook is None:
                self.win.Activate()
            else:
                asyncio.create_task(test_hook(self))

        def message(self, title, text, severity="Informational"):
            self.Notice.Title = title
            self.Notice.Message = text
            self.Notice.Severity = getattr(InfoBarSeverity, severity)
            self.Notice.IsOpen = True

        def clear_results(self):
            self.Cards.Children.Clear()
            self.Raw.Text = ""
            self.RawExpander.Visibility = Visibility.Collapsed
            self.Updated.Text = "手动查询"


        def SubSelection_Changed(self, sender, e):
            if getattr(self, "initializing", True): return
            self.clear_results()
            self.message("准备查询 GPT 额度", "确认读取方式后，点击查询全部 GPT 账号。")




        def Site_Changed(self, sender, e):
            if getattr(self, "initializing", True): return
            self.clear_results()
            self.message("已切换站点", "请使用对应站点的 Coding Plan API Key 查询。")



        async def Login_Click(self, sender, e):
            if self.busy: return
            self.set_busy(True)
            self.LoginState.Text = "正在连接 New API……"
            self.message("正在登录 New API", "正在验证账号并加载渠道列表。")
            self.Channels.Items.Clear()
            self.channel_rows = []
            self.imported_keys = []
            self.ImportedKeys.Items.Clear()
            self.ImportedKeys.Visibility = Visibility.Collapsed
            try:
                url, username, password = self.newapi_values()
                client = self.newapi_client
                if client and client.pending and client.url == url and getattr(client, "login_username", "") == username:
                    user = await asyncio.to_thread(client.complete_login, self.LoginCode.Password)
                else:
                    client = newapi.NewAPIClient(url)
                    client.login_username = username
                    self.newapi_client = client
                    try:
                        user = await asyncio.to_thread(client.login, username, password, turnstile=self.Turnstile.Text)
                    except newapi.LoginCodeRequired:
                        if not self.LoginCode.Password: raise
                        user = await asyncio.to_thread(client.complete_login, self.LoginCode.Password)
                self.NewPassword.Password = ""
                self.LoginCode.Password = ""
                self.Turnstile.Text = ""
                self.LoginButton.Content = "重新登录并加载渠道"
                self.remember_newapi(url, username, password)
                self.LoginState.Text = "登录信息已加密保存"
                self.channel_rows = await asyncio.to_thread(client.list_channels)
                from win32more.Microsoft.UI.Xaml.Controls import ComboBoxItem
                for row in self.channel_rows:
                    option = ComboBoxItem()
                    option.Content = f"#{row['id']} · {row.get('name') or '未命名渠道'}"
                    self.Channels.Items.Append(option)
                if self.channel_rows:
                    self.Channels.SelectedIndex = 0
                    self.message("登录成功", "请选择 GLM 渠道；如需安全验证，填写新的 2FA 验证码后读取 Key。", "Success")
                else:
                    self.message("登录成功", "账号未返回任何渠道。", "Warning")
            except newapi.LoginCodeRequired as exc:
                self.remember_newapi(url, username, password)
                self.NewPassword.Password = ""
                self.LoginButton.Content = "继续登录"
                self.LoginState.Text = "等待登录验证码"
                self.message("需要登录验证", str(exc), "Warning")
            except quota.QueryError as exc:
                self.NewPassword.Password = ""
                self.LoginState.Text = str(exc)
                self.message("New API 操作失败", str(exc), "Error")
            except Exception:
                self.NewPassword.Password = ""
                self.LoginState.Text = "登录失败"
                self.message("New API 操作失败", "无法处理登录响应，请检查站点地址和版本。", "Error")
            finally:
                self.set_busy(False)

        def Channel_Changed(self, sender, e):
            if getattr(self, "initializing", True): return
            self.imported_keys = []
            self.ImportedKeys.Items.Clear()
            self.ImportedKeys.Visibility = Visibility.Collapsed


        async def Import_Click(self, sender, e):
            if self.busy: return
            index = self.Channels.SelectedIndex
            if not self.newapi_client or not (0 <= index < len(self.channel_rows)):
                self.message("请先选择渠道", "登录 New API 后选择需要读取的 GLM 渠道。", "Warning")
                return
            self.set_busy(True)
            self.message("正在读取渠道 Key", "正在请求所选渠道的原始 Key。")
            self.imported_keys = []
            self.ImportedKeys.Items.Clear()
            self.ImportedKeys.Visibility = Visibility.Collapsed
            try:
                if newapi.normalize_url(self.NewURL.Text) != self.newapi_client.url or self.newapi_values()[1] != getattr(self.newapi_client, "login_username", ""):
                    raise newapi.NewAPIError("地址或账号已更改，请重新登录后再读取 Key。")
                row = self.channel_rows[index]
                keys = await asyncio.to_thread(self.newapi_client.channel_keys, row["id"], self.ReadCode.Password)
                self.imported_keys = keys
                from win32more.Microsoft.UI.Xaml.Controls import ComboBoxItem
                for i,key in enumerate(keys):
                    option = ComboBoxItem()
                    option.Content = f"Key {i+1}"
                    self.ImportedKeys.Items.Append(option)
                self.ImportedKeys.Visibility = Visibility.Visible
                self.ImportedKeys.SelectedIndex = 0
                base = str(row.get("base_url") or "").lower()
                if "api.z.ai" in base: self.Site.SelectedIndex = 1
                elif "bigmodel.cn" in base: self.Site.SelectedIndex = 0
                self.clear_results()
                self.NewAPIExpander.IsExpanded = False
                self.message("已导入渠道 Key", f"已读取 {len(keys)} 把 Key。请确认上方站点后点击查询额度；多 Key 可在此切换。", "Success")
            except quota.QueryError as exc:
                self.LoginState.Text = "读取失败：" + str(exc)
                self.message("导入失败", str(exc), "Error")
            except Exception:
                self.message("导入失败", "无法处理渠道 Key 响应，请检查部署版本或手动粘贴。", "Error")
            finally:
                self.ReadCode.Password = ""
                self.set_busy(False)


        def render(self, payload, key=""):
            self.render_cards(quota.quota_cards(payload), payload, key)

        def render_cards(self, cards, payload, key=""):
            self.Cards.Children.Clear()
            for card in cards:
                used = card["used"]
                title = escape(card["title"], quote=True)
                details = escape(card["details"], quote=True).replace("\n", "&#10;")
                if used is None:
                    percentage = "账户余额" if card.get("kind")=="balance" else "接口未提供有效的使用比例"
                    bar = ""
                else:
                    percentage = f"剩余 {card['remaining']:.1f}% · 已用 {used:.1f}%"
                    bar = f'<ProgressBar Minimum="0" Maximum="100" Value="{min(100, used)}" Height="6" />'
                card_xaml = f'''<Border xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    Padding="20" CornerRadius="12" Background="{{ThemeResource CardBackgroundFillColorDefaultBrush}}"
                    BorderBrush="{{ThemeResource CardStrokeColorDefaultBrush}}" BorderThickness="1">
                    <StackPanel Spacing="10">
                    <TextBlock Text="{title}" FontWeight="SemiBold" TextWrapping="Wrap" />
                    <TextBlock Text="{percentage}" FontSize="24" FontWeight="SemiBold" TextWrapping="Wrap" />
                    {bar}
                    <TextBlock Text="{details}" FontSize="12" Foreground="{{ThemeResource TextFillColorSecondaryBrush}}" TextWrapping="Wrap" />
                    </StackPanel></Border>'''
                from win32more.Microsoft.UI.Xaml import UIElement
                self.Cards.Children.Append(XamlReader.Load(card_xaml).as_(UIElement))
            self.publish_raw(payload, key)
            if not cards: self.message("暂无额度记录", "接口返回了空列表，请确认套餐状态。", "Warning")

    XamlApplication.Start(App)


def check_ui(input_path, output_path):
    """Run the real query callback against an external test fixture, with no visible window."""
    from pathlib import Path
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    report = {"ok": False}
    async def probe(view):
        previous_fetch, previous_save = quota.fetch_quota, settings.save
        previous_kimi = kimi.fetch_quota
        previous_service = service_providers.fetch_usage
        try:
            live_transport = payload.get("_live_transport") is True
            if not live_transport:
                quota.fetch_quota = lambda key, site: payload.get("quota", payload)
                kimi.fetch_quota = lambda key: payload.get("quota", payload)
                service_providers.fetch_usage = lambda name,record: {"cards":service_providers.parse_usage(name,payload["quota"],sealed=record.get("sealed",False))}
            settings.save = lambda *args, **kwargs: None
            if payload.get("_provider") in service_providers.BY_ID:
                spec=service_providers.BY_ID[payload["_provider"]]
                view.Source.SelectedIndex=spec["source"]
                controls={"secret":view.ServiceKey,"secret2":view.ServiceSecret,"session_token":view.ServiceSession}
                for field in spec["fields"]:controls[field["key"]].Password="diagnostic-only-secret"
                await view.ServiceQuery_Click(None,None)
                passed=view.Notice.Title=="查询成功"
                report["service_controls"]=bool(view.ServicePanel.Visibility==0 and view.GlmPanel.Visibility!=0 and view.KimiPanel.Visibility!=0)
                passed=passed and report["service_controls"]
            elif payload.get("_provider") == "kimi":
                view.Source.SelectedIndex = 2
                view.KimiKey.Password = "diagnostic-only-kimi"
                await view.KimiQuery_Click(None,None)
                passed = view.Notice.Title == ("Kimi 查询失败" if live_transport else "查询成功")
                report["kimi_controls"] = bool(view.KimiPanel.Visibility == 0 and view.GlmPanel.Visibility != 0 and view.SubPanel.Visibility != 0)
                passed = passed and report["kimi_controls"]
            elif payload.get("_provider") == "sub2api":
                view.Source.SelectedIndex = 1
                view.SubURL.Text = payload["url"]
                view.SubEmail.Text = payload["email"]
                view.SubPassword.Password = payload["password"]
                if payload.get("otp"): view.SubCode.Password = payload["otp"]
                view.SubMode.SelectedIndex = 1 if payload.get("cached") else 0
                await view.SubQuery_Click(None, None)
                if not view.sub_accounts:
                    raise RuntimeError("Sub2api diagnostic query did not return accounts")
                passed = view.Notice.Title in ("GPT 额度查询成功", "已读取 GPT 额度快照") or (payload.get("expect_partial") and view.Notice.Title == "GPT 额度部分成功")
                if payload.get("_sub_card_query"):
                    class ProbeButton:
                        def __init__(self):self.Tag="20 reset";self.IsEnabled=True;self.Content="查询重置卡"
                    from win32more.Microsoft.UI.Xaml.Automation.Peers import ButtonAutomationPeer
                    from win32more.Microsoft.UI.Xaml.Controls import Border as ProbeBorder, Button as ProbeButtonClass, Panel as ProbePanel
                    card_element=view.Cards.Children.GetAt(0)
                    content=card_element.as_(ProbeBorder).Child.as_(ProbePanel)
                    actions=content.Children.GetAt(content.Children.Size-2).as_(ProbePanel)
                    native_button=actions.Children.GetAt(0).as_(ProbeButtonClass)
                    ButtonAutomationPeer(native_button).Invoke()
                    for _ in range(20):
                        await asyncio.sleep(0.1)
                        item=next(x for x in view.last_bulk if x.get("account",{}).get("id")==20)
                        if item.get("queries",{}).get("reset"):break
                    item=next(x for x in view.last_bulk if x.get("account",{}).get("id")==20)
                    report["sub_card_button"]=bool(item.get("queries",{}).get("reset"))
                    report["sub_card_notice"]=view.Notice.Title
                    passed=passed and report["sub_card_button"] and view.Notice.Title=="账号卡片查询成功"
            elif payload.get("_provider") == "newapi":
                view.NewURL.Text = payload["url"]
                view.NewUsername.Text = payload["username"]
                view.NewPassword.Password = payload["password"]
                await view.Login_Click(None, None)
                view.ReadCode.Password = payload["read_code"]
                await view.Import_Click(None, None)
                await view.Query_Click(None, None)
                passed = view.Notice.Title == "查询成功" and not view.NewUsername.Text and not view.NewPassword.Password
            else:
                view.Key.Password = "diagnostic-only"
                await view.Query_Click(None, None)
                passed = view.Notice.Title == ("查询失败" if live_transport else "查询成功")
            if payload.get("_vault_check"):
                import file_dialogs
                password = payload.get("file_password")
                target = str(Path(input_path).with_suffix(".roundtrip.sqv"))
                previous_picker = file_dialogs.pick
                previous_export_options = view.export_options
                previous_import_password = view.import_password
                async def export_choice(): return password
                async def import_choice(): return password
                try:
                    file_dialogs.pick = lambda window, save=False: target
                    view.export_options = export_choice
                    view.import_password = import_choice
                    await view.SaveFile_Click(None, None)
                    if view.Notice.Title != "加密文件已保存":
                        raise RuntimeError("Encrypted file export failed")
                    blob = Path(target).read_bytes()
                    vault.decode(blob, password=password)
                    await view.ImportFile_Click(None, None)
                    if view.Notice.Title != "加密连接已导入":
                        raise RuntimeError("Encrypted file import failed")
                    report["file_handlers_verified"] = True
                finally:
                    file_dialogs.pick = previous_picker
                    view.export_options = previous_export_options
                    view.import_password = previous_import_password
                if payload.get("_provider") == "sub2api":
                    await view.SubQuery_Click(None, None)
                    clean_fields = not view.SubEmail.Text and not view.SubPassword.Password
                    read_only = view.SubURL.IsReadOnly and view.SubEmail.IsReadOnly and not view.SubPassword.IsEnabled
                elif payload.get("_provider") in service_providers.BY_ID:
                    await view.ServiceQuery_Click(None,None)
                    clean_fields = not view.ServiceKey.Password and not view.ServiceSecret.Password and not view.ServiceSession.Password
                    read_only = not view.ServiceKey.IsEnabled
                elif payload.get("_provider") == "kimi":
                    await view.KimiQuery_Click(None,None)
                    clean_fields = not view.KimiKey.Password
                    read_only = not view.KimiKey.IsEnabled
                else:
                    await view.Query_Click(None, None)
                    clean_fields = not view.Key.Password
                    read_only = not view.Key.IsEnabled
                try:
                    vault.exportable(view.vault_data)
                    blocked = False
                except vault.VaultError:
                    blocked = True
                dialog = view.build_export_dialog()[0]
                report.update({"vault_restored": True, "credential_fields_empty": bool(clean_fields),
                               "import_read_only": bool(read_only), "reexport_blocked": blocked,
                               "raw_hidden": not bool(view.Raw.Text), "file_buttons_present": bool(view.ImportFile and view.SaveFile),
                               "export_dialog_constructed": bool(dialog)})
                passed = passed and clean_fields and read_only and blocked and not view.Raw.Text and not view.SaveFile.IsEnabled
            if payload.get("expected_cards") is not None:
                passed = passed and view.Cards.Children.Size == payload["expected_cards"]
            report.update({"ok": passed, "title": view.Notice.Title,
                           "message": view.Notice.Message, "cards": view.Cards.Children.Size,
                           "frozen": bool(getattr(sys, "frozen", False))})
        except Exception as exc:
            report["exception"] = diagnostics.record("ui-probe", exc)
        finally:
            quota.fetch_quota, settings.save = previous_fetch, previous_save
            kimi.fetch_quota = previous_kimi
            service_providers.fetch_usage = previous_service
            Path(output_path).write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            view.win.Close()
            view.Exit()
    launch(test_hook=probe)
    return 0 if report["ok"] else 1


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--check-ui":
        return check_ui(sys.argv[2], sys.argv[3])
    if len(sys.argv) == 3 and sys.argv[1] == "--check-runtime":
        # Headless packaging diagnostic. Does not open a window or contact a server.
        from pathlib import Path
        report = {"ok": False}
        try:
            import ssl
            ssl.create_default_context()
            import win32more.appsdk
            from win32more.Microsoft.UI.Xaml import Window
            from win32more.winui3 import XamlLoader
            from cryptography.hazmat.primitives.asymmetric import rsa
            win32more.appsdk.initialize()
            assert Path(sys.modules["win32more.winui3"].__file__).with_name("app.xaml").exists()
            assert settings.crypt(settings.crypt(b"runtime-check"), decrypt=True) == b"runtime-check"
            report = {"ok": True, "winui3": True, "encrypted_storage": True,
                      "password_encryption": True, "https_context": True, "frozen": bool(getattr(sys, "frozen", False))}
        except Exception as exc:
            report["error_type"] = type(exc).__name__
        Path(sys.argv[2]).write_text(json.dumps(report), encoding="utf-8")
        return 0 if report["ok"] else 1
    try:
        launch()
    except Exception as exc:
        # Never put an API response or a credential in crash messages.
        name = type(exc).__name__
        text = "程序启动失败（" + name + "）。\n请确认已安装 Windows App Runtime 2.6（x64）。\n安装地址见随附的使用说明。"
        if "--debug" in sys.argv:
            import traceback
            traceback.print_exc()
        ctypes.windll.user32.MessageBoxW(None, text, "订阅额度", 0x10)
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
