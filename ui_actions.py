"""Credential persistence, batch account cards and encrypted file UI actions."""
import asyncio
import copy
from datetime import datetime
from html import escape
import json
from pathlib import Path
import diagnostics
import file_dialogs
import newapi
import quota
import kimi
import service_providers
import provider_extras
import sub2api
import vault

class VaultActions:
    def initialize_vault(self,test_mode=False):
        self.vault_test_mode=test_mode
        self.vault_load_error=""
        self.candidate_key=""
        self.candidate_sealed=False
        self.last_bulk=[]
        self.service_source=None
        try:self.vault_data=vault.fresh() if test_mode else vault.load_local()
        except vault.VaultError as exc:
            self.vault_data=vault.fresh();self.vault_load_error=str(exc)

    def profile(self,name):return self.vault_data["profiles"].get(name,{})
    def private_view(self):
        spec=service_providers.BY_SOURCE.get(self.Source.SelectedIndex)
        if spec:return bool(self.profile(spec["id"]).get("sealed"))
        if self.Source.SelectedIndex==2:return bool(self.profile("kimi").get("sealed"))
        if self.Source.SelectedIndex==1:return bool(self.profile("sub2api").get("sealed"))
        return bool(self.profile("glm").get("sealed") or self.profile("newapi").get("sealed") or self.candidate_sealed)

    def persist(self):
        self.vault_data["source"]=self.Source.SelectedIndex if self.Source.SelectedIndex in range(12) else 0
        if self.vault_load_error:raise vault.VaultError("本机保存的连接无法解密；请导入有效备份或点击更换连接后重新设置。")
        if not self.vault_test_mode:vault.save_local(self.vault_data)

    def restore_fields(self):
        from win32more.Microsoft.UI.Xaml import Visibility
        g=self.profile("glm");s=self.profile("sub2api");n=self.profile("newapi")
        if g and not self.candidate_key:
            self.Key.Password="";self.Key.PlaceholderText="已加密保存 Key，直接查询即可"
            self.Site.SelectedIndex=1 if g["site"]=="global" else 0
        self.Key.IsEnabled=not self.busy and not bool(g or self.candidate_key)
        self.Site.IsEnabled=not self.busy and not bool(g)
        self.Remember.Visibility=Visibility.Collapsed
        if s:
            self.SubURL.Text=s["url"];self.SubURL.IsReadOnly=True
            self.SubEmail.Text="";self.SubEmail.PlaceholderText="登录账号已加密保存"
            self.SubEmail.IsReadOnly=True
            self.SubPassword.Password="";self.SubPassword.PlaceholderText="密码已加密保存"
            self.SubPassword.IsEnabled=False
            self.SubMode.SelectedIndex=1 if s.get("cached") else 0
            self.SubState.Text="已保存登录信息 · 点击一次即可查询全部账号"+("（导入连接）" if s.get("sealed") else "")
        else:
            self.SubURL.IsReadOnly=False;self.SubEmail.IsReadOnly=False;self.SubPassword.IsEnabled=not self.busy
            self.SubEmail.PlaceholderText="用于登录 sub2api 后台";self.SubPassword.PlaceholderText="首次输入，随后本机加密保存"
        if n:
            self.NewURL.Text=n["url"];self.NewURL.IsReadOnly=True
            self.NewUsername.Text="";self.NewUsername.PlaceholderText="账号已加密保存";self.NewUsername.IsReadOnly=True
            self.NewPassword.Password="";self.NewPassword.PlaceholderText="密码已加密保存";self.NewPassword.IsEnabled=False
        else:
            self.NewURL.IsReadOnly=False;self.NewUsername.IsReadOnly=False;self.NewPassword.IsEnabled=not self.busy
        k=self.profile("kimi")
        self.KimiKey.Password="" if k else self.KimiKey.Password
        self.KimiKey.PlaceholderText="Key 已加密保存，直接查询即可" if k else "粘贴 Kimi Coding Plan Key"
        self.KimiKey.IsEnabled=not self.busy and not bool(k)
        self.KimiQuery.IsEnabled=not self.busy
        self.SubQuery.IsEnabled=not self.busy
        spec=service_providers.BY_SOURCE.get(self.Source.SelectedIndex)
        if spec:
            record=self.profile(spec["id"])
            if self.service_source!=self.Source.SelectedIndex:
                for control in (self.ServiceKey,self.ServiceSecret,self.ServiceSession):control.Password=""
            self.service_source=self.Source.SelectedIndex
            self.ServiceLabel.Text=spec["label"];self.ServiceDescription.Text=spec["help"]
            controls={"secret":self.ServiceKey,"secret2":self.ServiceSecret,"session_token":self.ServiceSession}
            for control in controls.values():control.Visibility=Visibility.Collapsed
            for field in spec["fields"]:
                control=controls[field["key"]];control.Header=field["label"];control.Visibility=Visibility.Visible
                control.IsEnabled=not self.busy and not bool(record)
                if record:control.Password=""
                control.PlaceholderText="凭据已加密保存，不回填明文" if record else "首次填写，成功后加密保存"
        self.SaveFile.IsEnabled=not self.busy and not self.private_view()

    def Source_Changed(self,sender,e):
        if getattr(self,"initializing",True):return
        from win32more.Microsoft.UI.Xaml import Visibility
        spec=service_providers.BY_SOURCE.get(self.Source.SelectedIndex)
        if self.service_source!=self.Source.SelectedIndex:
            for control in (self.ServiceKey,self.ServiceSecret,self.ServiceSession):control.Password=""
        self.service_source=self.Source.SelectedIndex
        is_sub=self.Source.SelectedIndex==1
        is_kimi=self.Source.SelectedIndex==2
        self.GlmPanel.Visibility=Visibility.Collapsed if is_sub or is_kimi or spec else Visibility.Visible
        self.ServicePanel.Visibility=Visibility.Visible if spec else Visibility.Collapsed
        self.KimiPanel.Visibility=Visibility.Visible if is_kimi else Visibility.Collapsed
        self.NewAPIExpander.Visibility=Visibility.Collapsed if is_sub or is_kimi or spec else Visibility.Visible
        self.SubPanel.Visibility=Visibility.Visible if is_sub else Visibility.Collapsed
        self.clear_results()
        self.ResultsTitle.Text="Kimi Coding Plan 额度" if is_kimi else ("全部 GPT / Codex 账号" if is_sub else "GLM Coding Plan 额度")
        self.Footnote.Text=("每张卡片对应一个 GPT 账号；数据时间与后台快照会单独标注。" if is_sub else "额度按接口实际返回展示。Key 在本机加密保存，输入框不回填明文。")
        self.restore_fields()
        if spec:self.ResultsTitle.Text=spec["label"];self.Footnote.Text="按真实接口返回展示；余额不换算为套餐百分比。凭据加密保存，不回填明文。"
        self.message("准备就绪","点击查询全部 GPT 账号。" if is_sub and self.profile("sub2api") else ("首次填写 sub2api 登录信息后，点击查询全部账号。" if is_sub else "输入 Key 后查询；保存过的连接可直接查询。"))

    def set_busy(self,busy):
        from win32more.Microsoft.UI.Xaml import Visibility
        self.busy=busy
        for name in ("Query","Site","Key","KimiQuery","KimiKey","ServiceKey","ServiceSecret","ServiceSession","ServiceQuery","NewURL","NewUsername","NewPassword","LoginCode","ReadCode","LoginButton","Channels","ImportedKeys","Turnstile","Source","SubURL","SubEmail","SubPassword","SubCode","SubCaptcha","SubLogin","SubAccounts","SubMode","ImportFile","SaveFile","ResetConnection"):
            getattr(self,name).IsEnabled=not busy
        self.ImportButton.IsEnabled=not busy and bool(self.newapi_client and self.channel_rows)
        self.SubQuery.IsEnabled=not busy
        self.Loading.Visibility=Visibility.Visible if busy else Visibility.Collapsed;self.Loading.IsActive=busy
        if not busy:self.restore_fields()

    def Remember_Unchecked(self,sender,e):pass

    def ResetConnection_Click(self,sender,e):
        if self.busy:return
        spec=service_providers.BY_SOURCE.get(self.Source.SelectedIndex)
        names=(spec["id"],) if spec else ("kimi",) if self.Source.SelectedIndex==2 else (("sub2api",) if self.Source.SelectedIndex==1 else ("glm","newapi"))
        for name in names:self.vault_data["profiles"].pop(name,None)
        self.vault_load_error="";self.sub_client=None;self.newapi_client=None
        self.candidate_key="";self.candidate_sealed=False;self.sub_accounts=[]
        for control in (self.Key,self.KimiKey,self.ServiceKey,self.ServiceSecret,self.ServiceSession,self.SubPassword,self.NewPassword,self.SubCode):control.Password=""
        for control in (self.SubEmail,self.SubURL,self.NewUsername,self.NewURL):control.Text=""
        try:self.persist()
        except (vault.VaultError,OSError):self.message("设置未保存","清除连接设置失败，请检查本机数据目录权限。","Error");return
        self.restore_fields();self.clear_results();self.message("连接已清除","可以填写新的连接信息。")

    def remember_sub(self,record,client=None):
        record=copy.deepcopy(record)
        if client and client.access_token:
            record.update(access_token=client.access_token,refresh_token=client.refresh_token,user=copy.deepcopy(client.user))
        record["cached"]=self.SubMode.SelectedIndex==1
        self.vault_data["profiles"]["sub2api"]=record
        self.persist();self.restore_fields()

    async def ensure_sub_client(self,force=False):
        saved=self.profile("sub2api")
        if saved:
            if self.SubURL.Text.strip()!=saved["url"]:raise vault.VaultError("已保存连接的服务器地址不能直接修改，请先点击更换连接。")
            record=copy.deepcopy(saved)
        else:
            record={"url":sub2api.normalize_url(self.SubURL.Text),"email":self.SubEmail.Text.strip(),"password":self.SubPassword.Password,"sealed":False}
        if not record.get("email") or not (record.get("password") or record.get("refresh_token")):
            raise sub2api.Sub2APIError("请先填写 sub2api 管理员邮箱和密码。")
        client=self.sub_client
        if client and client.url!=record["url"]:client=None
        if client and client.pending:
            user=await asyncio.to_thread(client.complete_login,self.SubCode.Password)
        elif client and client.access_token and not force:
            self.remember_sub(record,client);return client
        elif saved.get("access_token") and saved.get("user") and not force:
            client=sub2api.Sub2APIClient(record["url"]);client.login_email=record["email"]
            client._tokens({"access_token":record["access_token"],"refresh_token":record.get("refresh_token",""),"user":record["user"]})
            self.sub_client=client;return client
        else:
            client=sub2api.Sub2APIClient(record["url"]);self.sub_client=client
            try:
                user=await asyncio.to_thread(client.login,record["email"],record.get("password",""),turnstile=self.SubCaptcha.Text)
            except sub2api.LoginCodeRequired:
                for key in ("access_token","refresh_token","user"):record.pop(key,None)
                self.remember_sub(record)
                if not self.SubCode.Password:raise
                user=await asyncio.to_thread(client.complete_login,self.SubCode.Password)
        self.sub_client=client
        self.remember_sub(record,client)
        self.SubCode.Password="";self.SubCaptcha.Text=""
        from win32more.Microsoft.UI.Xaml import Visibility
        self.SubCode.Visibility=Visibility.Collapsed
        return client

    async def SubLogin_Click(self,sender,e):await self.SubQuery_Click(sender,e)

    async def SubQuery_Click(self,sender,e):
        if self.busy:return
        self.clear_results();self.set_busy(True);self.last_bulk=[]
        self.message("正在查询全部 GPT 账号","正在连接 sub2api 并加载账号列表。")
        try:
            client=await self.ensure_sub_client()
            try:accounts=await asyncio.to_thread(client.list_accounts)
            except sub2api.Sub2APIError as exc:
                if exc.status!=401:raise
                client=await self.ensure_sub_client(force=True)
                accounts=await asyncio.to_thread(client.list_accounts)
            self.sub_accounts=accounts
            if not accounts:
                self.message("未找到 GPT 账号","sub2api 未返回 OpenAI OAuth 账号。","Warning");return
            cached=self.SubMode.SelectedIndex==1
            # Serialize requests for each login session so refresh-token rotation cannot race.
            for index,account in enumerate(accounts):
                self.message("正在查询全部 GPT 账号",f"正在读取 {index+1} / {len(accounts)} 个账号。")
                try:
                    payload=await asyncio.to_thread(client.fetch_usage,account,cached=cached)
                    item={"account":account,"payload":payload}
                except quota.QueryError as exc:item={"account":account,"error":str(exc)}
                except Exception as exc:
                    item={"account":account,"error":"内部处理异常（"+diagnostics.record("sub2api-account",exc)+"）。"}
                self.last_bulk.append(item)
                self.render_bulk(self.last_bulk)
            self.remember_sub(self.profile("sub2api"),client)
            failed=sum("error" in x for x in self.last_bulk)
            self.Updated.Text="查询于 "+datetime.now().strftime("%H:%M:%S")
            self.SubState.Text=f"登录信息已加密保存 · 共 {len(accounts)} 个账号"
            if failed:
                self.message("GPT 额度部分成功" if failed<len(accounts) else "GPT 额度查询失败",f"共 {len(accounts)} 个账号，成功 {len(accounts)-failed} 个，失败 {failed} 个。失败原因在对应卡片中。","Warning" if failed<len(accounts) else "Error")
            elif all(x["payload"].get("source")=="snapshot" for x in self.last_bulk):
                self.message("已读取 GPT 额度快照",f"已读取全部 {len(accounts)} 个账号的后台快照，请以每张卡片的数据时间为准。","Warning")
            else:self.message("GPT 额度查询成功",f"已读取全部 {len(accounts)} 个账号，每个账号一张卡片。","Success")
        except sub2api.LoginCodeRequired as exc:
            from win32more.Microsoft.UI.Xaml import Visibility
            self.SubCode.Visibility=Visibility.Visible;self.SubState.Text=str(exc)
            self.message("需要登录验证码",str(exc),"Warning")
        except (quota.QueryError,vault.VaultError) as exc:self.message("GPT 额度查询失败",str(exc),"Error")
        except Exception as exc:self.message("程序出错","批量查询异常（"+diagnostics.record("sub2api-bulk",exc)+"）。","Error")
        finally:self.set_busy(False)

    def render_bulk(self,items):
        from win32more.Microsoft.UI.Xaml import UIElement
        from win32more.Microsoft.UI.Xaml.Markup import XamlReader
        self.Cards.Children.Clear();self.ResultsTitle.Text=f"全部 GPT / Codex 账号 · {len(items)} 张卡片"
        for item in items:
            account=item["account"]
            label="GPT 账号 #"+str(account["id"]) if self.private_view() else str(account.get("name") or ("GPT 账号 #"+str(account["id"])))
            sections=[];meta=""
            if item.get("error"):
                sections.append('<TextBlock Text="'+escape(item["error"],quote=True)+'" TextWrapping="Wrap" Foreground="{ThemeResource SystemFillColorCriticalBrush}" />')
            else:
                payload=item["payload"];cards=sub2api.usage_cards(payload)
                usage=payload.get("usage",{})
                tier=str(usage.get("plan_type") or usage.get("subscription_tier") or "")
                source="后台快照" if payload.get("source")=="snapshot" else "实时额度"
                timestamp=sub2api.local_time(payload.get("updated_at"))
                meta=" · ".join(x for x in (tier,source,"数据时间："+timestamp if timestamp else "") if x)
                for card in cards:
                    used=card["used"]
                    if used is None:
                        color="TextFillColorSecondaryBrush";percentage="接口未提供使用比例";bar=""
                    else:
                        remaining=card.get("remaining")
                        color="SystemFillColorCriticalBrush" if remaining is not None and remaining<=10 else ("SystemFillColorCautionBrush" if remaining is not None and remaining<=30 else "SystemFillColorSuccessBrush")
                        percentage=f"{card['remaining']:.1f}% 剩余";bar=f'<ProgressBar Value="{min(100,used):.1f}" Maximum="100" Height="5" CornerRadius="3" />'
                    detail=escape(card["details"],quote=True).replace("\n","&#10;")
                    sections.append(f'''<Border Padding="14" CornerRadius="10" Background="{{ThemeResource CardBackgroundFillColorSecondaryBrush}}" BorderBrush="{{ThemeResource CardStrokeColorDefaultBrush}}" BorderThickness="1"><StackPanel Spacing="8"><Grid><Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions><StackPanel Grid.Column="0" Spacing="2"><TextBlock Text="{escape(card["title"],quote=True)}" FontSize="12" Foreground="{{ThemeResource TextFillColorSecondaryBrush}}" TextWrapping="Wrap"/><TextBlock Text="{percentage}" FontSize="22" FontWeight="SemiBold" Foreground="{{ThemeResource {color}}}"/></StackPanel><StackPanel Grid.Column="1" Spacing="2" VerticalAlignment="Bottom"><TextBlock Text="已用 {used:.1f}%" FontSize="12" HorizontalAlignment="Right" Foreground="{{ThemeResource TextFillColorSecondaryBrush}}"/></StackPanel></Grid>{bar}<TextBlock Text="{detail}" FontSize="11" LineHeight="19" TextWrapping="Wrap" Foreground="{{ThemeResource TextFillColorSecondaryBrush}}"/></StackPanel></Border>''')
                if not cards:sections.append('<TextBlock Text="后台未返回额度窗口，没有推算可用比例。" TextWrapping="Wrap"/>')
            queries=item.get("queries",{})
            for kind,label in (("reset","重置卡次数"),("credits","Codex 点数")):
                for card in queries.get(kind,[]):
                    lines=[escape(line,quote=True) for line in card["details"].splitlines() if line.strip()]
                    primary=lines[0].split("：",1)[-1] if "：" in lines[0] else lines[0]
                    extras="".join(f'<TextBlock Text="{line}" FontSize="11" LineHeight="18" TextWrapping="Wrap" Foreground="{{ThemeResource TextFillColorSecondaryBrush}}"/>' for line in lines[1:])
                    sections.append(f'''<Border Padding="12" CornerRadius="10" Background="{{ThemeResource CardBackgroundFillColorSecondaryBrush}}" BorderBrush="{{ThemeResource CardStrokeColorDefaultBrush}}" BorderThickness="1"><StackPanel Spacing="4"><TextBlock Text="{escape(label,quote=True)}" FontSize="11" Foreground="{{ThemeResource TextFillColorSecondaryBrush}}"/><TextBlock Text="{primary}" FontSize="18" FontWeight="SemiBold"/>{extras}</StackPanel></Border>''')
                    if kind=="reset" and card.get("expanded_details"):
                        details="".join(f'<Border Padding="10" CornerRadius="8" Background="{{ThemeResource CardBackgroundFillColorSecondaryBrush}}" BorderBrush="{{ThemeResource CardStrokeColorDefaultBrush}}" BorderThickness="1"><TextBlock Text="{escape(line,quote=True)}" FontSize="12" LineHeight="19" TextWrapping="Wrap"/></Border>' for line in card["expanded_details"])
                        sections.append(f'''<Expander HorizontalAlignment="Stretch" HorizontalContentAlignment="Stretch" IsExpanded="False" Header="查看 {len(card['expanded_details'])} 条重置卡明细"><StackPanel Spacing="6">{details}</StackPanel></Expander>''')
            note='<TextBlock Text="只读取或刷新快照 · 不消耗重置卡" FontSize="11" TextWrapping="Wrap" Foreground="{ThemeResource TextFillColorTertiaryBrush}" />'
            meta_chip=f'<Border Padding="8,4" CornerRadius="8" HorizontalAlignment="Left" Background="{{ThemeResource CardBackgroundFillColorSecondaryBrush}}" BorderBrush="{{ThemeResource CardStrokeColorDefaultBrush}}" BorderThickness="1"><TextBlock Text="{escape(meta,quote=True)}" FontSize="11" Foreground="{{ThemeResource TextFillColorSecondaryBrush}}"/></Border>' if meta else ""
            card=XamlReader.Load(f'''<Border xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Padding="18" CornerRadius="16" Background="{{ThemeResource CardBackgroundFillColorDefaultBrush}}" BorderBrush="{{ThemeResource CardStrokeColorDefaultBrush}}" BorderThickness="1"><StackPanel Spacing="14"><TextBlock Text="{escape(label,quote=True)}" FontSize="18" FontWeight="SemiBold" TextWrapping="Wrap"/>{meta_chip}{''.join(sections)}<StackPanel x:Name="SubCardActions" Orientation="Horizontal" Spacing="8"><Button Content="重置卡" Height="32" MinWidth="86" Padding="14,4" FontSize="12" FontWeight="SemiBold" CornerRadius="8"/><Button Content="点数" Height="32" MinWidth="86" Padding="14,4" FontSize="12" FontWeight="SemiBold" CornerRadius="8"/><Button Content="刷新快照" Height="32" MinWidth="86" Padding="14,4" FontSize="12" FontWeight="SemiBold" CornerRadius="8" Style="{{StaticResource AccentButtonStyle}}"/></StackPanel>{note}</StackPanel></Border>''')
            from win32more.Microsoft.UI.Xaml.Controls import Border, Button, Panel
            content=card.as_(Border).Child.as_(Panel)
            actions=content.Children.GetAt(content.Children.Size-2)
            actions_list=actions.as_(Panel).Children
            for button,(kind,tag) in zip(actions_list, (("reset",f"{account['id']} reset"),("credits",f"{account['id']} credits"),("refresh",f"{account['id']} refresh"))):
                routed_button=button.as_(Button);routed_button.Name="SubCard_"+tag.replace(" ","_");routed_button.Click += self.SubCardQuery_Click
            self.Cards.Children.Append(card.as_(UIElement))
        self.publish_raw({"accounts":items})

    def render_sub(self,payload):self.render_bulk([{"account":payload.get("account",{}),"payload":payload}])

    async def SubCardQuery_Click(self,sender,e):
        if self.busy or self.card_busy:return
        from win32more.Microsoft.UI.Xaml.Controls import Button
        sender=sender.as_(Button)
        tag=sender.Name.removeprefix("SubCard_").strip().split("_")
        if len(tag)!=2 or not tag[0].isdigit() or tag[1] not in ("reset","credits","refresh"):return
        account_id=int(tag[0]);item=next((x for x in self.last_bulk if x.get("account",{}).get("id")==account_id),None)
        if not item:return
        self.card_busy=True;sender.IsEnabled=False;sender.Content="查询中……";self.set_busy(True)
        self.message("正在查询账号卡片", "正在读取该账号的重置卡 / 点数数据。" if tag[1]!="refresh" else "正在刷新额度并保存后台快照。")
        try:
            client=await self.ensure_sub_client();account=item["account"]
            if tag[1]=="refresh":
                item["payload"]=await asyncio.to_thread(client.refresh_usage,account);item["queries"]={}
            else:
                card=await asyncio.to_thread(client.query_reset_credits if tag[1]=="reset" else client.query_credits,account)
                item.setdefault("queries",{})[tag[1]]=[card]
            self.remember_sub(self.profile("sub2api"),client)
            self.render_bulk(self.last_bulk);self.Updated.Text="查询于 "+datetime.now().strftime("%H:%M:%S")
            self.message("账号卡片查询成功","已读取接口实际返回的数据。","Success")
        except (quota.QueryError,vault.VaultError) as exc:self.message("账号卡片查询失败",str(exc),"Error")
        except Exception as exc:self.message("程序出错","卡片查询异常（"+diagnostics.record("sub2api-card",exc)+"）。","Error")
        finally:self.set_busy(False);self.card_busy=False

    def publish_raw(self,payload,key=""):
        from win32more.Microsoft.UI.Xaml import Visibility
        if self.private_view():self.Raw.Text="";self.RawExpander.Visibility=Visibility.Collapsed;return
        self.Raw.Text=json.dumps(quota.redact_payload(payload,key),ensure_ascii=False,indent=2)
        self.RawExpander.Visibility=Visibility.Visible

    def remember_newapi(self,url,username,password):
        previous=self.profile("newapi")
        if not password:password=previous.get("password","")
        self.vault_data["profiles"]["newapi"]={"url":url,"username":username,"password":password,"sealed":bool(previous.get("sealed"))}
        self.persist();self.restore_fields()

    def newapi_values(self):
        saved=self.profile("newapi")
        if saved:
            if self.NewURL.Text.strip()!=saved["url"]:raise vault.VaultError("已保存连接的服务器地址不能直接修改。")
            return saved["url"],saved["username"],saved["password"]
        return newapi.normalize_url(self.NewURL.Text),self.NewUsername.Text.strip(),self.NewPassword.Password

    def ImportedKey_Changed(self,sender,e):
        index=self.ImportedKeys.SelectedIndex
        if 0<=index<len(self.imported_keys):
            self.candidate_key=self.imported_keys[index];self.candidate_sealed=bool(self.profile("newapi").get("sealed"))
            self.Key.Password="";self.Key.PlaceholderText="渠道 Key 已载入，点击查询即可";self.Key.IsEnabled=False
            self.clear_results()

    async def Query_Click(self,sender,e):
        if self.busy:return
        try:
            saved=self.profile("glm")
            site="global" if self.Site.SelectedIndex==1 else "cn"
            key=quota.validate_key(self.Key.Password or self.candidate_key or saved.get("key",""))
            if saved and saved["site"]!=site and not self.Key.Password and not self.candidate_key:
                raise quota.QueryError("已保存 Key 对应另一个站点，请更换连接后输入该站点的 Key。")
        except quota.QueryError as exc:self.message("请输入有效的 Key",str(exc),"Warning");return
        self.clear_results();self.set_busy(True);stage="request"
        try:
            payload=await asyncio.to_thread(quota.fetch_quota,key,site);stage="render"
            self.render_enriched("glm",quota.quota_cards(payload));self.Updated.Text="更新于 "+datetime.now().strftime("%H:%M:%S")
            sealed=bool(saved.get("sealed") or self.candidate_sealed)
            self.vault_data["profiles"]["glm"]={**saved,"site":site,"key":key,"sealed":sealed}
            self.candidate_key="";self.persist();self.restore_fields()
            if quota.quota_cards(payload):self.message("查询成功","已读取当前套餐额度；Key 已在本机加密保存。","Success")
            if sealed:self.publish_raw({})
        except quota.QueryError as exc:self.message("查询失败",str(exc),"Error")
        except vault.VaultError as exc:self.message("连接保存失败",str(exc),"Error")
        except Exception as exc:self.clear_results();self.message("程序出错","内部异常（"+diagnostics.record(stage,exc)+"）。","Error")
        finally:self.set_busy(False)

    async def KimiQuery_Click(self,sender,e):
        if self.busy:return
        saved=self.profile("kimi")
        try:key=quota.validate_key(self.KimiKey.Password or saved.get("key",""))
        except quota.QueryError as exc:self.message("请输入有效的 Kimi Key",str(exc),"Warning");return
        self.clear_results();self.set_busy(True)
        self.message("正在查询 Kimi","正在读取 Coding Plan 周额度和周期额度。")
        try:
            payload=await asyncio.to_thread(kimi.fetch_quota,key)
            self.render_cards(kimi.quota_cards(payload),payload,key)
            self.Updated.Text="更新于 "+datetime.now().strftime("%H:%M:%S")
            self.vault_data["profiles"]["kimi"]={"key":key,"sealed":bool(saved.get("sealed"))}
            self.persist();self.restore_fields()
            self.message("查询成功","已读取 Kimi Coding Plan 额度；Key 已在本机加密保存。","Success")
        except quota.QueryError as exc:self.message("Kimi 查询失败",str(exc),"Error")
        except (vault.VaultError,OSError):self.message("连接保存失败","无法加密保存 Kimi 连接，请检查本机数据目录权限。","Error")
        except Exception as exc:self.clear_results();self.message("程序出错","内部异常（"+diagnostics.record("kimi-query",exc)+"）。","Error")
        finally:self.set_busy(False)

    def service_values(self):
        spec=service_providers.BY_SOURCE.get(self.Source.SelectedIndex)
        if not spec:raise quota.QueryError("请先选择服务。")
        saved=self.profile(spec["id"])
        if saved:return spec,saved
        controls={"secret":self.ServiceKey,"secret2":self.ServiceSecret,"session_token":self.ServiceSession}
        record={field["key"]:controls[field["key"]].Password for field in spec["fields"]}
        record["sealed"]=False
        return spec,service_providers.validate_profile(spec["id"],record)

    async def ServiceQuery_Click(self,sender,e):
        if self.busy:return
        try:spec,record=self.service_values()
        except quota.QueryError as exc:self.message("请检查访问凭据",str(exc),"Warning");return
        self.clear_results();self.set_busy(True);self.message("正在查询",spec["label"]+" · 正在读取真实数据。")
        try:
            payload=await asyncio.to_thread(service_providers.fetch_usage,spec["id"],record)
            cards=payload["cards"]
            if spec["kind"]=="balance":
                for card in cards:card["kind"]="balance"
            self.render_enriched(spec["id"],cards)
            self.Updated.Text="更新于 "+datetime.now().strftime("%H:%M:%S")
            self.vault_data["profiles"][spec["id"]]=copy.deepcopy(record)
            self.persist();self.restore_fields()
            self.message("查询成功",spec["label"]+" · 凭据已加密保存。","Success")
        except quota.QueryError as exc:self.message("查询失败",str(exc),"Error")
        except (vault.VaultError,OSError):self.message("连接保存失败","无法加密保存连接，请检查数据目录权限。","Error")
        except Exception as exc:self.clear_results();self.message("程序出错","内部异常（"+diagnostics.record("service-query",exc)+"）。","Error")
        finally:self.set_busy(False)

    def render_enriched(self,name,cards,results=None):
        from win32more.Microsoft.UI.Xaml import UIElement
        from win32more.Microsoft.UI.Xaml.Controls import Border,Button,StackPanel,Orientation
        self.extra_provider=name;self.extra_base=copy.deepcopy(cards);self.extra_results=results or {}
        combined=cards+[card for values in self.extra_results.values() for card in values]
        self.render_cards(combined,{"cards":combined})
        actions=provider_extras.ACTIONS.get(name,[])
        if not actions:return
        panel=StackPanel();panel.Orientation=Orientation.Horizontal;panel.Spacing=8
        for action,label in actions:
            button=Button();button.Name="Extra_"+action;button.Content=label
            button.Click+=self.ExtraQuery_Click;panel.Children.Append(button)
        if self.Cards.Children.Size:
            last=self.Cards.Children.GetAt(self.Cards.Children.Size-1).as_(Border)
            last.Child.as_(StackPanel).Children.Append(panel.as_(UIElement))

    async def ExtraQuery_Click(self,sender,e):
        if self.busy:return
        from win32more.Microsoft.UI.Xaml.Controls import Button,ContentDialog,ContentDialogResult,PasswordBox,PasswordRevealMode
        action=sender.as_(Button).Name.removeprefix("Extra_")
        name=self.extra_provider;profile=copy.deepcopy(self.profile(name))
        if name=="glm" and not profile.get("console_token"):
            if profile.get("sealed"):
                self.message("需要控制台凭据","导入的 GLM 连接没有控制台凭据，请由连接所有者补充后重新导出。","Warning");return
            password=PasswordBox();password.Header="GLM 网页控制台 Authorization（不是套餐 Key）";password.PasswordRevealMode=PasswordRevealMode.Hidden
            dialog=ContentDialog();dialog.Title="添加 GLM 控制台查询凭据";dialog.Content=password;dialog.PrimaryButtonText="保存并查询";dialog.CloseButtonText="取消";dialog.XamlRoot=self.win.Content.XamlRoot
            if await dialog.ShowAsync()!=ContentDialogResult.Primary:return
            try:profile["console_token"]=service_providers.header_secret(password.Password)
            except quota.QueryError as exc:self.message("凭据无效",str(exc),"Warning");return
        self.set_busy(True);self.message("正在查询附加信息","只读取当前服务的权益或账单。")
        try:
            rows=await asyncio.to_thread(provider_extras.fetch,name,action,profile)
            self.vault_data["profiles"][name]=profile;self.persist()
            results={**self.extra_results,action:rows}
            self.render_enriched(name,self.extra_base,results)
            self.message("附加查询成功","已读取接口实际返回的数据。","Success")
        except (quota.QueryError,vault.VaultError) as exc:self.message("附加查询失败",str(exc),"Error")
        except Exception as exc:self.message("附加查询失败","内部异常（"+diagnostics.record("provider-extra",exc)+"）。","Error")
        finally:self.set_busy(False)

    def collect_owned(self):
        data=copy.deepcopy(self.vault_data)
        if not self.private_view():
            if self.Source.SelectedIndex==0:
                key=self.Key.Password or self.candidate_key
                if key:data["profiles"]["glm"]={**data["profiles"].get("glm",{}),"site":"global" if self.Site.SelectedIndex==1 else "cn","key":quota.validate_key(key),"sealed":False}
            elif self.Source.SelectedIndex==2:
                if self.KimiKey.Password:data["profiles"]["kimi"]={"key":quota.validate_key(self.KimiKey.Password),"sealed":False}
            elif self.Source.SelectedIndex in service_providers.BY_SOURCE:
                spec,record=self.service_values();data["profiles"][spec["id"]]=copy.deepcopy(record)
            elif self.SubEmail.Text.strip() and self.SubPassword.Password:
                data["profiles"]["sub2api"]={"url":sub2api.normalize_url(self.SubURL.Text),"email":self.SubEmail.Text.strip(),"password":self.SubPassword.Password,"sealed":False,"cached":self.SubMode.SelectedIndex==1}
        data["source"]=self.Source.SelectedIndex
        return vault.exportable(data)

    def build_export_dialog(self):
        from win32more.Microsoft.UI.Xaml import FrameworkElement
        from win32more.Microsoft.UI.Xaml.Controls import ContentDialog,ContentDialogResult
        from win32more.Microsoft.UI.Xaml.Markup import XamlReader
        xaml='''<StackPanel xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Spacing="12" Width="420"><TextBlock Text="本机备份绑定当前 Windows 用户；跨电脑文件需要文件密码。文件加密不等于收件人绝对无法提取运行中的凭据。" TextWrapping="Wrap"/><ComboBox x:Name="Mode" Header="文件用途" SelectedIndex="0" HorizontalAlignment="Stretch"><ComboBoxItem Content="仅当前 Windows 用户可导入"/><ComboBoxItem Content="跨电脑导入（文件密码加密）"/></ComboBox><PasswordBox x:Name="Password" Header="跨电脑文件密码（至少 12 个字符）" PasswordRevealMode="Hidden"/><PasswordBox x:Name="Confirm" Header="再次输入文件密码" PasswordRevealMode="Hidden"/><TextBlock x:Name="Error" TextWrapping="Wrap" Foreground="{ThemeResource SystemFillColorCriticalBrush}"/></StackPanel>'''
        content=XamlReader.Load(xaml).as_(FrameworkElement)
        from win32more.winui3 import as_runtime_class
        mode=as_runtime_class(content.FindName("Mode"));password=as_runtime_class(content.FindName("Password"));confirm=as_runtime_class(content.FindName("Confirm"));error=as_runtime_class(content.FindName("Error"))
        dialog=ContentDialog();dialog.Title="保存加密连接文件";dialog.Content=content;dialog.PrimaryButtonText="选择保存位置";dialog.CloseButtonText="取消";dialog.XamlRoot=self.win.Content.XamlRoot
        return dialog,mode,password,confirm,error

    async def export_options(self):
        from win32more.Microsoft.UI.Xaml.Controls import ContentDialogResult
        dialog,mode,password,confirm,error=self.build_export_dialog()
        while await dialog.ShowAsync()==ContentDialogResult.Primary:
            if mode.SelectedIndex==0:return None
            if len(password.Password)<12:error.Text="文件密码至少需要 12 个字符。";continue
            if password.Password!=confirm.Password:error.Text="两次输入的文件密码不一致。";continue
            return password.Password
        return False

    async def import_password(self):
        from win32more.Microsoft.UI.Xaml.Controls import ContentDialog,ContentDialogResult,PasswordBox
        password=PasswordBox();password.Header="请输入加密连接文件的文件密码"
        from win32more.Microsoft.UI.Xaml.Controls import PasswordRevealMode
        password.PasswordRevealMode=PasswordRevealMode.Hidden
        dialog=ContentDialog();dialog.Title="导入跨电脑连接文件";dialog.Content=password;dialog.PrimaryButtonText="解密并导入";dialog.CloseButtonText="取消";dialog.XamlRoot=self.win.Content.XamlRoot
        return password.Password if await dialog.ShowAsync()==ContentDialogResult.Primary else None

    async def SaveFile_Click(self,sender,e):
        if self.busy:return
        self.set_busy(True)
        try:
            if self.private_view():raise vault.VaultError("导入连接只能查询，不支持再次导出。")
            data=self.collect_owned()
            password=await self.export_options()
            if password is False:return
            target=file_dialogs.pick(self.win,save=True)
            if not target:return
            blob=await asyncio.to_thread(vault.encode,data,password=password)
            await asyncio.to_thread(vault.atomic_write,target,blob)
            self.vault_data["profiles"].update(data["profiles"]);self.persist();self.restore_fields()
            self.message("加密文件已保存","已保存为 .sqv 二进制文件。账号、密码和 Key 不会以明文写入。","Success")
        except (vault.VaultError,quota.QueryError) as exc:self.message("保存失败",str(exc),"Error")
        except OSError:self.message("保存失败","无法写入所选文件，请检查目录权限。","Error")
        except Exception as exc:self.message("保存失败","文件处理异常（"+diagnostics.record("vault-export",exc)+"）。","Error")
        finally:self.set_busy(False)

    async def ImportFile_Click(self,sender,e):
        if self.busy:return
        self.set_busy(True)
        try:
            target=file_dialogs.pick(self.win)
            if not target:return
            if Path(target).stat().st_size>vault.MAX_SIZE:raise vault.VaultError("连接文件过大。")
            blob=Path(target).read_bytes();mode=vault.inspect(blob)
            password=await self.import_password() if mode==vault.PORTABLE else None
            if mode==vault.PORTABLE and password is None:return
            data=vault.imported(await asyncio.to_thread(vault.decode,blob,password=password))
            self.vault_load_error="";self.vault_data["profiles"].update(data["profiles"])
            self.vault_data["source"]=data["source"];self.Source.SelectedIndex=data["source"]
            self.sub_client=None;self.newapi_client=None;self.candidate_key="";self.candidate_sealed=False
            self.persist();self.restore_fields();self.Source_Changed(None,None)
            self.message("加密连接已导入","凭据已隐藏并在本机加密保存。直接点击查询；导入连接不提供明文查看或再次导出。","Success")
        except vault.VaultError as exc:self.message("导入失败",str(exc),"Error")
        except OSError:self.message("导入失败","无法读取文件，请检查路径和权限。","Error")
        except Exception as exc:self.message("导入失败","文件处理异常（"+diagnostics.record("vault-import",exc)+"）。","Error")
        finally:self.set_busy(False)
