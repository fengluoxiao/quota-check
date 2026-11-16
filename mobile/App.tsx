import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TextInputProps,
  useColorScheme,
  useWindowDimensions,
  View,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as Linking from 'expo-linking';
import Constants from 'expo-constants';
import * as DocumentPicker from 'expo-document-picker';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import * as SecureStore from 'expo-secure-store';
import Native from './modules/quota-vault';
import {
  AccountCard,
  GlmProfile,
  Provider,
  SubProfile,
  VaultData,
  exportOwned,
  freshVault,
  lockImported,
  normalizeURL,
  validateKey,
} from './src/models';
import { NeedsOTP, SubClient, queryAll, queryGLM } from './src/api';
import { clearVault, loadVault, nativeTransport, saveVault } from './src/storage';
import { fileMode, fromBase64, toBase64 } from './src/encoding';

type Colors = {
  background: string;
  card: string;
  ink: string;
  muted: string;
  line: string;
  accent: string;
  soft: string;
  danger: string;
};
function Field({ label, colors, ...props }: TextInputProps & { label: string; colors: Colors }) {
  return (
    <View style={styles.field}>
      <Text style={[styles.fieldLabel, { color: colors.muted }]}>{label}</Text>
      <TextInput
        {...props}
        autoCapitalize="none"
        autoCorrect={false}
        placeholderTextColor={colors.muted}
        style={[
          styles.input,
          { color: colors.ink, borderColor: colors.line, backgroundColor: colors.background },
          props.editable === false && { opacity: 0.6 },
        ]}
      />
    </View>
  );
}
function Button({
  title,
  onPress,
  colors,
  disabled = false,
  secondary = false,
}: {
  title: string;
  onPress: () => void;
  colors: Colors;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        {
          backgroundColor: secondary ? colors.soft : colors.accent,
          opacity: disabled ? 0.4 : pressed ? 0.7 : 1,
        },
      ]}
    >
      <Text style={[styles.buttonText, { color: secondary ? colors.accent : '#fff' }]}>
        {title}
      </Text>
    </Pressable>
  );
}
function WindowCard({ card, colors }: { card: AccountCard; colors: Colors }) {
  return (
    <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.line }]}>
      <Text selectable={false} style={[styles.cardTitle, { color: colors.ink }]}>
        {card.title}
      </Text>
      <Text style={[styles.meta, { color: colors.muted }]}>{card.subtitle}</Text>
      {card.error ? (
        <Text style={{ color: colors.danger }}>{card.error}</Text>
      ) : card.windows.length ? (
        card.windows.map((w, i) => (
          <View key={i} style={styles.window}>
            <Text style={[styles.windowTitle, { color: colors.muted }]}>{w.title}</Text>
            <Text
              style={[
                styles.percentage,
                { color: w.remaining !== null && w.remaining <= 10 ? colors.danger : colors.ink },
              ]}
            >
              {w.remaining === null ? '未提供使用比例' : '剩余 ' + w.remaining.toFixed(1) + '%'}
              <Text style={[styles.used, { color: colors.muted }]}>
                {w.used === null ? '' : '  已用 ' + w.used.toFixed(1) + '%'}
              </Text>
            </Text>
            {w.used !== null && (
              <View
                accessibilityRole="progressbar"
                accessibilityValue={{ min: 0, max: 100, now: Math.min(100, w.used) }}
                style={[styles.track, { backgroundColor: colors.line }]}
              >
                <View
                  style={[
                    styles.fill,
                    { width: Math.min(100, w.used) + '%', backgroundColor: colors.accent },
                  ]}
                />
              </View>
            )}
            {!!w.detail && <Text style={[styles.detail, { color: colors.muted }]}>{w.detail}</Text>}
            {!!w.reset && (
              <Text style={[styles.detail, { color: colors.muted }]}>重置：{w.reset}</Text>
            )}
          </View>
        ))
      ) : (
        <Text style={{ color: colors.muted }}>后台没有返回额度窗口，没有推算可用比例。</Text>
      )}
    </View>
  );
}
function Screen() {
  const dark = useColorScheme() === 'dark';
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const colors: Colors = dark
    ? {
        background: '#101114',
        card: '#1b1d22',
        ink: '#f2f3f7',
        muted: '#a2a8b4',
        line: '#343943',
        accent: '#5195ff',
        soft: '#24364f',
        danger: '#ff8b87',
      }
    : {
        background: '#f3f5f8',
        card: '#ffffff',
        ink: '#152238',
        muted: '#64748b',
        line: '#dce2eb',
        accent: '#1769d5',
        soft: '#e8f0fd',
        danger: '#c63035',
      };
  const [data, setData] = useState<VaultData>(freshVault);
  const dataRef = useRef(data);
  const [loading, setLoading] = useState(true);
  const [blocked, setBlocked] = useState(false);
  const [busy, setBusyState] = useState(false);
  const busyRef = useRef(false);
  function setBusy(value: boolean) {
    busyRef.current = value;
    setBusyState(value);
  }
  const [cards, setCards] = useState<AccountCard[]>([]);
  const [notice, setNotice] = useState('首次添加连接或导入加密文件，然后点击查询。');
  const [settings, setSettings] = useState(false);
  const [needsOTP, setNeedsOTP] = useState(false);
  const [form, setForm] = useState({
    key: '',
    site: 'cn' as 'cn' | 'global',
    url: '',
    email: '',
    password: '',
    otp: '',
    captcha: '',
    cached: false,
  });
  const [fileTask, setFileTask] = useState<
    { kind: 'import'; blob: string } | { kind: 'export' } | null
  >(null);
  const [filePassword, setFilePassword] = useState('');
  const [fileConfirm, setFileConfirm] = useState('');
  const [fileError, setFileError] = useState('');
  const clientRef = useRef<SubClient | null>(null);
  const active = data.source === 1 ? data.profiles.sub2api : data.profiles.glm;
  const sealed = active?.sealed === true;
  async function commit(next: VaultData, replace = false) {
    await saveVault(next, replace);
    dataRef.current = next;
    setData(next);
    setBlocked(false);
  }
  useEffect(() => {
    let live = true;
    loadVault()
      .then((v) => {
        if (live) {
          dataRef.current = v;
          setData(v);
          setNotice(
            Object.keys(v.profiles).length
              ? '连接已加密保存，点击查询即可。'
              : '添加连接后即可开始查询。',
          );
          if (
            Constants.expoConfig?.extra?.nativeSmokeCheck === true &&
            !Object.keys(v.profiles).length
          ) {
            setTimeout(() => void nativeCheck(), 1000);
          }
        }
      })
      .catch(() => {
        if (live) {
          setBlocked(true);
          setNotice('本机连接无法解密，请导入备份或清除本机连接。');
        }
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, []);
  async function prepareImport(uri: string) {
    if (busyRef.current) return;
    setBusy(true);
    try {
      const file = new File(uri);
      if (file.size > 2 * 1024 * 1024) throw new Error('连接文件过大。');
      const bytes = await file.bytes();
      fileMode(bytes);
      setFilePassword('');
      setFileConfirm('');
      setFileError('');
      setFileTask({ kind: 'import', blob: toBase64(bytes) });
    } catch (e) {
      Alert.alert('导入失败', message(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    const sub = Linking.addEventListener('url', (e) => {
      if (e.url === 'quota-check://native-check') void nativeCheck();
      if (e.url.startsWith('file://') || e.url.startsWith('content://')) void prepareImport(e.url);
    });
    void Linking.getInitialURL().then((url) => {
      if (url && (url.startsWith('file://') || url.startsWith('content://')))
        void prepareImport(url);
    });
    return () => sub.remove();
  }, []);
  async function nativeCheck() {
    // Simulator smoke probe. Never opens or removes an existing connection store.
    if (busyRef.current || Object.keys(dataRef.current.profiles).length || Native.readStorage())
      return;
    setBusy(true);
    const report: Record<string, unknown> = { ok: false, stage: 'start' };
    const probe = 'quota-check.native-probe.' + Date.now();
    const options = {
      keychainService: 'com.fengluoxiao.quotacheck.vault',
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    };
    let wroteStore = false;
    try {
      report.stage = 'generate-key';
      const secret = Native.generateKey();
      report.stage = 'keychain-write';
      await SecureStore.setItemAsync(probe, secret, options);
      if ((await SecureStore.getItemAsync(probe, options)) !== secret) throw new Error('keychain');
      report.keychain = true;
      report.stage = 'native-crypto';
      const plain = JSON.stringify(freshVault());
      const device = await Native.seal(plain, 2, secret);
      if ((await Native.open(device, secret)) !== plain) throw new Error('device');
      const portable = await Native.seal(plain, 1, secret);
      if ((await Native.open(portable, secret)) !== plain) throw new Error('portable');
      report.crypto = true;
      report.stage = 'encrypted-storage';
      await Native.writeStorage(device);
      wroteStore = true;
      if (Native.readStorage() !== device) throw new Error('storage');
      report.storage = true;
      report.ok = true;
      report.stage = 'complete';
    } catch {
      report.error = 'native check failed';
    } finally {
      if (wroteStore) await Native.deleteStorage();
      await SecureStore.deleteItemAsync(probe, options).catch(() => undefined);
      const file = new File(Paths.document, 'native-health.json');
      file.create({ overwrite: true });
      file.write(JSON.stringify(report));
      setBusy(false);
    }
  }
  function message(e: unknown) {
    return e instanceof Error ? e.message : '操作失败，请重试。';
  }
  async function switchSource(source: Provider) {
    if (busyRef.current) return;
    const next = { ...dataRef.current, source };
    setCards([]);
    clientRef.current = null;
    dataRef.current = next;
    setData(next);
    setNeedsOTP(false);
    setNotice('点击查询，或在设置中添加连接。');
    if (!blocked)
      try {
        await commit(next);
      } catch {
        setNotice('服务已切换，但本机设置未能保存。');
      }
  }
  async function runQuery(candidate?: VaultData) {
    if (busyRef.current) return false;
    if (blocked) {
      Alert.alert('请先恢复连接', '导入有效备份或清除本机连接后再查询。');
      return false;
    }
    const next: VaultData = JSON.parse(JSON.stringify(candidate ?? dataRef.current)) as VaultData;
    const profile = next.source === 1 ? next.profiles.sub2api : next.profiles.glm;
    if (!profile) {
      setSettings(true);
      return false;
    }
    setBusy(true);
    setCards([]);
    setNotice(
      next.source === 1 ? '正在连接 sub2api，读取全部 GPT 账号……' : '正在查询 GLM Coding Plan……',
    );
    try {
      if (next.source === 0) {
        const result = await queryGLM(next.profiles.glm!, nativeTransport);
        await commit(next);
        setCards(result);
        setNotice('查询成功 · Key 已在本机加密保存。');
      } else {
        const p = next.profiles.sub2api!;
        let client = clientRef.current;
        if (!client || client.url !== p.url || client.profile.email !== p.email) {
          client = new SubClient(p, nativeTransport);
          clientRef.current = client;
        }
        await client.login(form.otp, form.captcha);
        next.profiles.sub2api = { ...client.profile };
        await commit(next);
        setNeedsOTP(false);
        setForm((v) => ({ ...v, key: '', email: '', password: '', otp: '', captcha: '' }));
        let completed = 0;
        const result = await queryAll(client, (card) => {
          completed++;
          setCards((current) => [...current, card]);
          setNotice('正在读取全部账号 · 已完成 ' + completed + ' 个');
        });
        next.profiles.sub2api = { ...client.profile };
        await commit(next);
        const failed = result.filter((c) => c.error).length;
        setNotice(
          result.length
            ? '共 ' +
                result.length +
                ' 个账号 · 成功 ' +
                (result.length - failed) +
                ' 个' +
                (failed ? ' · 失败 ' + failed + ' 个' : '')
            : '后台没有 OpenAI OAuth 账号。',
        );
      }
      setForm((v) => ({ ...v, key: '', email: '', password: '', otp: '', captcha: '' }));
      return true;
    } catch (e) {
      if (e instanceof NeedsOTP) {
        if (clientRef.current) {
          next.profiles.sub2api = { ...clientRef.current.profile };
          await commit(next);
        }
        setNeedsOTP(true);
        setSettings(true);
        setNotice(e.message);
      } else setNotice(message(e));
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function saveForm() {
    try {
      const next: VaultData = JSON.parse(JSON.stringify(dataRef.current)) as VaultData;
      if (next.source === 0) {
        if (!next.profiles.glm)
          next.profiles.glm = { site: form.site, key: validateKey(form.key), sealed: false };
      } else if (!next.profiles.sub2api) {
        if (!form.email.trim() || !form.password)
          throw new Error('请填写 sub2api 管理员邮箱和密码。');
        next.profiles.sub2api = {
          url: normalizeURL(form.url),
          email: form.email.trim(),
          password: form.password,
          cached: form.cached,
          sealed: false,
        };
      }
      if (next.profiles.sub2api)
        next.profiles.sub2api.cached = form.cached || next.profiles.sub2api.cached === true;
      const ok = await runQuery(next);
      if (ok) setSettings(false);
    } catch (e) {
      Alert.alert('连接信息不完整', message(e));
    }
  }
  function reset() {
    Alert.alert('清除当前连接？', '需要重新填写或导入连接。此操作不会显示已保存的凭据。', [
      { text: '取消', style: 'cancel' },
      {
        text: '清除',
        style: 'destructive',
        onPress: () => {
          void (async () => {
            try {
              if (blocked) {
                await clearVault();
                dataRef.current = freshVault();
                setData(dataRef.current);
                setBlocked(false);
              } else {
                const next: VaultData = JSON.parse(JSON.stringify(dataRef.current)) as VaultData;
                if (next.source === 1) delete next.profiles.sub2api;
                else {
                  delete next.profiles.glm;
                  delete next.profiles.newapi;
                }
                await commit(next);
              }
              clientRef.current = null;
              setCards([]);
              setNeedsOTP(false);
              setForm({
                key: '',
                site: 'cn',
                url: '',
                email: '',
                password: '',
                otp: '',
                captcha: '',
                cached: false,
              });
              setNotice('连接已清除，可以重新填写。');
            } catch (e) {
              Alert.alert('清除失败', message(e));
            }
          })();
        },
      },
    ]);
  }
  async function selectFile() {
    if (busyRef.current) return;
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (!result.canceled && result.assets[0]) await prepareImport(result.assets[0].uri);
    } catch (e) {
      Alert.alert('无法选择文件', message(e));
    }
  }
  function beginExport() {
    try {
      if (sealed) throw new Error('导入连接只可查询，不能再次导出。');
      exportOwned(dataRef.current);
      setFilePassword('');
      setFileConfirm('');
      setFileError('');
      setFileTask({ kind: 'export' });
    } catch (e) {
      Alert.alert('无法导出', message(e));
    }
  }
  async function finishFile() {
    if (!fileTask || busyRef.current) return;
    if (Array.from(filePassword).length < 12) {
      setFileError('文件密码至少需要 12 个字符。');
      return;
    }
    if (fileTask.kind === 'export' && filePassword !== fileConfirm) {
      setFileError('两次输入的文件密码不一致。');
      return;
    }
    setBusy(true);
    setFileError('');
    try {
      if (fileTask.kind === 'import') {
        const next = lockImported(
          JSON.parse(await Native.open(fileTask.blob, filePassword)) as unknown,
        );
        const merged: VaultData = {
          version: 1,
          source: next.source,
          profiles: { ...dataRef.current.profiles, ...next.profiles },
        };
        await commit(merged, true);
        clientRef.current = null;
        setCards([]);
        setSettings(false);
        setForm({
          key: '',
          site: 'cn',
          url: '',
          email: '',
          password: '',
          otp: '',
          captcha: '',
          cached: false,
        });
        setNotice('连接已导入并隐藏凭据，点击查询即可。');
      } else {
        const own = exportOwned(dataRef.current);
        const blob = await Native.seal(JSON.stringify(own), 1, filePassword);
        const file = new File(Paths.cache, 'quota-check-connection.sqv');
        file.create({ overwrite: true });
        file.write(fromBase64(blob));
        if (!(await Sharing.isAvailableAsync())) throw new Error('当前设备不支持系统分享。');
        await Sharing.shareAsync(file.uri, {
          mimeType: 'application/octet-stream',
          UTI: 'com.fengluoxiao.quotacheck.connection',
          dialogTitle: '保存加密连接',
        });
        if (Platform.OS === 'ios' && file.exists) file.delete();
        setNotice('已打开系统分享，可选择“存储到文件”。');
      }
      setFileTask(null);
      setFilePassword('');
      setFileConfirm('');
    } catch (e) {
      setFileError(message(e));
    } finally {
      setBusy(false);
    }
  }
  const storedSub = data.profiles.sub2api;
  const storedGlm = data.profiles.glm;
  const formUI = (
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.formContent}>
      <Text style={[styles.sectionTitle, { color: colors.ink }]}>
        {data.source === 1 ? '连接 sub2api' : 'GLM Coding Plan'}
      </Text>
      {!!active && (
        <View style={[styles.saved, { backgroundColor: colors.soft }]}>
          <Text style={{ color: colors.accent }}>
            {sealed ? '导入连接 · 凭据已隐藏' : '登录信息已加密保存 · 可直接查询'}
          </Text>
        </View>
      )}
      {data.source === 0 ? (
        <>
          <View style={styles.segment}>
            {(['cn', 'global'] as const).map((site) => (
              <Pressable
                key={site}
                disabled={busy || !!storedGlm}
                onPress={() => setForm((v) => ({ ...v, site }))}
                style={[
                  styles.segmentItem,
                  {
                    backgroundColor:
                      (storedGlm?.site ?? form.site) === site ? colors.soft : colors.card,
                  },
                ]}
              >
                <Text style={{ color: colors.accent }}>
                  {site === 'cn' ? '智谱国内' : 'Z.ai 海外'}
                </Text>
              </Pressable>
            ))}
          </View>
          <Field
            colors={colors}
            label="Coding Plan Key"
            value={storedGlm ? '' : form.key}
            editable={!storedGlm && !busy}
            secureTextEntry
            textContentType="none"
            placeholder={storedGlm ? 'Key 已保存，不回填明文' : '首次输入，成功后加密保存'}
            onChangeText={(key) => setForm((v) => ({ ...v, key }))}
          />
          {!storedGlm && !!data.profiles.newapi && (
            <Text style={{ color: colors.muted }}>
              此文件仅含 New API 连接。请先在桌面端读取 GLM Key，再导出包含 Key 的跨电脑文件。
            </Text>
          )}
        </>
      ) : (
        <>
          <Field
            colors={colors}
            label="sub2api 站点地址"
            value={storedSub?.url ?? form.url}
            editable={!storedSub && !busy}
            keyboardType="url"
            placeholder="https://sub.example.com"
            onChangeText={(url) => setForm((v) => ({ ...v, url }))}
          />
          <Field
            colors={colors}
            label="后台管理员邮箱"
            value={storedSub ? '' : form.email}
            editable={!storedSub && !busy}
            keyboardType="email-address"
            placeholder={storedSub ? '登录账号已加密保存' : '用于登录 sub2api 后台'}
            onChangeText={(email) => setForm((v) => ({ ...v, email }))}
          />
          <Field
            colors={colors}
            label="后台密码"
            value={storedSub ? '' : form.password}
            editable={!storedSub && !busy}
            secureTextEntry
            textContentType="none"
            placeholder={storedSub ? '密码已加密保存' : '首次输入，成功后加密保存'}
            onChangeText={(password) => setForm((v) => ({ ...v, password }))}
          />
          {needsOTP && (
            <Field
              colors={colors}
              label="2FA 验证码"
              value={form.otp}
              editable={!busy}
              secureTextEntry
              keyboardType="number-pad"
              maxLength={6}
              placeholder="6 位验证码"
              onChangeText={(otp) => setForm((v) => ({ ...v, otp }))}
            />
          )}
          <View style={styles.switchRow}>
            <Text style={{ color: colors.ink, flex: 1 }}>使用后台快照（兼容旧版）</Text>
            <Switch
              value={storedSub?.cached ?? form.cached}
              disabled={busy}
              onValueChange={(cached) => {
                setForm((v) => ({ ...v, cached }));
                if (storedSub) {
                  const next = {
                    ...dataRef.current,
                    profiles: { ...dataRef.current.profiles, sub2api: { ...storedSub, cached } },
                  };
                  void commit(next).catch(() => setNotice('读取方式未能保存。'));
                }
              }}
            />
          </View>
          <Field
            colors={colors}
            label="Turnstile Token（站点要求时）"
            value={form.captcha}
            editable={!busy}
            secureTextEntry
            textContentType="none"
            placeholder="普通站点留空"
            onChangeText={(captcha) => setForm((v) => ({ ...v, captcha }))}
          />
        </>
      )}
      <Button
        title={busy ? '正在查询……' : data.source === 1 ? '查询全部 GPT 账号' : '查询 GLM 额度'}
        onPress={() => {
          void saveForm();
        }}
        colors={colors}
        disabled={busy}
      />
      <Button
        title={active || blocked ? '更换连接（清除本机保存）' : '清除输入'}
        secondary
        onPress={
          active || blocked
            ? reset
            : () =>
                setForm({
                  key: '',
                  site: 'cn',
                  url: '',
                  email: '',
                  password: '',
                  otp: '',
                  captcha: '',
                  cached: false,
                })
        }
        colors={colors}
        disabled={busy}
      />
      <Text style={[styles.helper, { color: colors.muted }]}>
        本地凭据由设备密钥加密保存，导入后不回填账号、密码或 Key。HTTP
        站点会明文传输登录请求，请优先使用 HTTPS。
      </Text>
      <Text style={[styles.helper, { color: colors.muted }]}>
        文件和界面保护不能保证控制运行环境的人也提取不到凭据。若凭据必须始终不下发，需要服务器代查。
      </Text>
    </ScrollView>
  );
  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: colors.background }]}>
      <StatusBar style={dark ? 'light' : 'dark'} />
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.appTitle, { color: colors.ink }]}>额度查询</Text>
          <Text style={{ color: colors.muted }}>GLM · GPT / Codex</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          onPress={() => void selectFile()}
          disabled={busy || loading}
          style={styles.toolbar}
        >
          <Text style={{ color: colors.accent }}>导入</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={beginExport}
          disabled={busy || sealed || loading}
          style={styles.toolbar}
        >
          <Text style={{ color: sealed ? colors.muted : colors.accent }}>保存</Text>
        </Pressable>
        {!wide && (
          <Pressable
            accessibilityRole="button"
            onPress={() => setSettings(true)}
            disabled={busy || loading}
            style={styles.toolbar}
          >
            <Text style={{ color: colors.accent }}>设置</Text>
          </Pressable>
        )}
      </View>
      <View style={[styles.segment, { marginHorizontal: 20, backgroundColor: colors.card }]}>
        {([0, 1] as const).map((source) => (
          <Pressable
            key={source}
            accessibilityRole="button"
            accessibilityState={{ selected: data.source === source }}
            disabled={busy || loading}
            onPress={() => void switchSource(source)}
            style={[
              styles.segmentItem,
              { backgroundColor: data.source === source ? colors.soft : colors.card },
            ]}
          >
            <Text
              style={{
                color: data.source === source ? colors.accent : colors.muted,
                fontWeight: '600',
              }}
            >
              {source === 0 ? 'GLM Coding Plan' : 'GPT · sub2api'}
            </Text>
          </Pressable>
        ))}
      </View>
      <View style={[styles.body, wide && styles.wideBody]}>
        {wide && (
          <View
            style={[styles.sidebar, { backgroundColor: colors.card, borderColor: colors.line }]}
          >
            {formUI}
          </View>
        )}
        <View style={{ flex: 1 }}>
          <View style={[styles.notice, { backgroundColor: colors.card }]}>
            {(busy || loading) && <ActivityIndicator color={colors.accent} />}
            <Text style={{ color: colors.muted, flex: 1 }}>{notice}</Text>
          </View>
          <FlatList
            data={cards}
            keyExtractor={(c) => c.id}
            renderItem={({ item }) => <WindowCard card={item} colors={colors} />}
            contentContainerStyle={styles.list}
            ListEmptyComponent={
              !loading ? (
                <View style={styles.empty}>
                  <Text style={[styles.emptyTitle, { color: colors.ink }]}>查询你的订阅额度</Text>
                  <Text style={[styles.emptyText, { color: colors.muted }]}>
                    添加一次连接后，点击查询即可。GPT 后台有多少账号，就显示多少张卡片。
                  </Text>
                </View>
              ) : undefined
            }
          />
          {!wide && (
            <View style={styles.queryBar}>
              <Button
                title={busy ? '正在读取……' : data.source === 1 ? '查询全部 GPT 账号' : '查询额度'}
                onPress={() => void runQuery()}
                colors={colors}
                disabled={busy || loading}
              />
            </View>
          )}
        </View>
      </View>
      <Modal
        visible={settings && !wide}
        presentationStyle="pageSheet"
        animationType="slide"
        onRequestClose={() => {
          if (!busy) setSettings(false);
        }}
      >
        <SafeAreaView style={[styles.screen, { backgroundColor: colors.card }]}>
          <View style={styles.modalHeader}>
            <Text style={[styles.sectionTitle, { color: colors.ink }]}>连接设置</Text>
            <Pressable disabled={busy} onPress={() => setSettings(false)}>
              <Text style={{ color: colors.accent }}>完成</Text>
            </Pressable>
          </View>
          <KeyboardAvoidingView
            style={{ flex: 1 }}
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          >
            {formUI}
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Modal>
      <Modal
        visible={!!fileTask}
        presentationStyle="pageSheet"
        animationType="slide"
        onRequestClose={() => {
          if (!busy) setFileTask(null);
        }}
      >
        <SafeAreaView style={[styles.screen, { backgroundColor: colors.card }]}>
          <View style={styles.modalHeader}>
            <Text style={[styles.sectionTitle, { color: colors.ink }]}>
              {fileTask?.kind === 'import' ? '导入加密连接' : '保存加密连接'}
            </Text>
            <Pressable
              disabled={busy}
              onPress={() => {
                setFileTask(null);
                setFilePassword('');
                setFileConfirm('');
              }}
            >
              <Text style={{ color: colors.accent }}>取消</Text>
            </Pressable>
          </View>
          <KeyboardAvoidingView
            style={{ flex: 1 }}
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          >
            <ScrollView
              contentContainerStyle={styles.formContent}
              keyboardShouldPersistTaps="handled"
            >
              <Text style={{ color: colors.muted }}>
                使用独立文件密码保护跨电脑文件。桌面端请选择“跨电脑导入”格式，Windows
                本机备份不能在手机解密。
              </Text>
              <Field
                colors={colors}
                label="文件密码（至少 12 个字符）"
                value={filePassword}
                onChangeText={setFilePassword}
                secureTextEntry
                textContentType="none"
                editable={!busy}
              />
              {fileTask?.kind === 'export' && (
                <Field
                  colors={colors}
                  label="再次输入文件密码"
                  value={fileConfirm}
                  onChangeText={setFileConfirm}
                  secureTextEntry
                  textContentType="none"
                  editable={!busy}
                />
              )}
              <Text style={{ color: colors.danger }}>{fileError}</Text>
              <Button
                title={
                  busy
                    ? '正在处理……'
                    : fileTask?.kind === 'import'
                      ? '解密并导入'
                      : '打开系统分享 / 存储到文件'
                }
                onPress={() => void finishFile()}
                colors={colors}
                disabled={busy}
              />
              <Text style={[styles.helper, { color: colors.muted }]}>
                导入后不提供明文查看或再次导出。拥有文件密码或控制运行环境的人仍有提取凭据的条件。
              </Text>
            </ScrollView>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}
export default function App() {
  return (
    <SafeAreaProvider>
      <Screen />
    </SafeAreaProvider>
  );
}
const styles = StyleSheet.create({
  screen: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 20,
    gap: 10,
  },
  appTitle: { fontSize: 30, fontWeight: '700', marginBottom: 3 },
  toolbar: { paddingVertical: 10, paddingHorizontal: 5 },
  segment: { flexDirection: 'row', padding: 4, borderRadius: 12, gap: 3 },
  segmentItem: { flex: 1, paddingVertical: 11, borderRadius: 9, alignItems: 'center' },
  body: { flex: 1, marginTop: 12 },
  wideBody: { flexDirection: 'row', paddingHorizontal: 20, gap: 20 },
  sidebar: {
    width: 340,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 18,
    overflow: 'hidden',
    marginBottom: 14,
  },
  list: { paddingHorizontal: 20, paddingTop: 4, paddingBottom: 20, gap: 14 },
  card: { padding: 20, borderRadius: 18, borderWidth: StyleSheet.hairlineWidth },
  cardTitle: { fontSize: 20, fontWeight: '700' },
  meta: { fontSize: 12, marginTop: 5, marginBottom: 6 },
  window: { marginTop: 18, gap: 8 },
  windowTitle: { fontSize: 13, fontWeight: '600' },
  percentage: { fontSize: 25, fontWeight: '700' },
  used: { fontSize: 12, fontWeight: '400' },
  track: { height: 6, borderRadius: 3, overflow: 'hidden' },
  fill: { height: 6, borderRadius: 3 },
  detail: { fontSize: 12 },
  notice: {
    flexDirection: 'row',
    gap: 10,
    padding: 14,
    marginHorizontal: 20,
    marginBottom: 10,
    borderRadius: 12,
  },
  queryBar: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 12 },
  button: { paddingVertical: 14, paddingHorizontal: 18, borderRadius: 12, alignItems: 'center' },
  buttonText: { fontSize: 16, fontWeight: '600' },
  empty: { paddingHorizontal: 22, paddingTop: 46, alignItems: 'center' },
  emptyTitle: { fontSize: 21, fontWeight: '600', marginBottom: 12 },
  emptyText: { fontSize: 14, lineHeight: 22, textAlign: 'center' },
  modalHeader: {
    padding: 20,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sectionTitle: { fontSize: 22, fontWeight: '700' },
  formContent: { padding: 20, gap: 16, paddingBottom: 40 },
  field: { gap: 7 },
  fieldLabel: { fontSize: 13, fontWeight: '500' },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 10,
    paddingHorizontal: 13,
    paddingVertical: 12,
    fontSize: 16,
    minHeight: 46,
  },
  saved: { padding: 12, borderRadius: 10 },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  helper: { fontSize: 12, lineHeight: 19 },
});
