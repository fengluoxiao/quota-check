#if os(iOS)
import Foundation
import Combine
import UniformTypeIdentifiers

struct ConnectionForm {
    var site = "cn"
    var key = ""
    var url = ""
    var email = ""
    var password = ""
    var captcha = ""
    var cached = false
    var otp = ""
    var secret: [String: String] = [:]
}
enum FileTask {
    case importData(Data)
    case exportData
}

extension FileTask: Identifiable {
    var id: String {
        switch self {
        case .importData: return "import"
        case .exportData: return "export"
        }
    }
}

@MainActor
final class AppModel: ObservableObject {
    @Published var vault = freshVault()
    @Published var cards: [AccountCard] = []
    @Published var busy = false
    @Published var busyCard: String?
    @Published var notice = "首次添加连接或导入加密文件，然后点击查询。"
    @Published var blocked = false
    @Published var loading = true
    @Published var settingsOpen = false
    @Published var form = ConnectionForm()
    @Published var needsOTP = false
    @Published var fileTask: FileTask?
    @Published var filePassword = ""
    @Published var fileConfirm = ""
    @Published var fileError = ""

    private var subClient: SubClient?
    private var importURL: URL?
    private var exportData: Data?
    private var initialized = false

    func start() async {
        guard !initialized else { return }
        initialized = true
        do {
            vault = try VaultStore.load()
            notice = vault.profiles.isEmpty ? "首次添加连接或导入加密文件，然后点击查询。" : "点击查询即可读取已保存的连接。"
        } catch {
            blocked = true
            notice = (error as? LocalizedError)?.errorDescription ?? "本机连接无法解密，请导入备份或清除本机连接。"
        }
        loading = false
        if ProcessInfo.processInfo.environment["NATIVE_SMOKE_CHECK"] == "1", vault.profiles.isEmpty {
            await nativeHealthCheck()
        }
    }

    func activeService() -> ServiceSpec? { QuotaCheckCore.service(source: vault.source) }

    func activeProfile() -> Profile? {
        if let service = activeService() { return vault.profiles[service.id] }
        if vault.source == 0 { return vault.profiles["glm"] }
        if vault.source == 1 { return vault.profiles["sub2api"] }
        if vault.source == 2 { return vault.profiles["kimi"] }
        return nil
    }

    func connectionTitle() -> String {
        if let profile = activeProfile() {
            if profile.sealed { return "已保存连接 · 凭据已隐藏" }
            switch profile.kind {
            case "glm": return profile.site == "global" ? "Z.ai 连接" : "智谱 BigModel 连接"
            case "sub2api": return "sub2api · \((profile.url ?? "").replacingOccurrences(of: "https://", with: ""))"
            case "kimi": return "Kimi Coding Plan 连接"
            case "newapi": return "New API 连接"
            default: return activeService()?.label ?? "服务连接"
            }
        }
        return "未添加连接"
    }

    func switchSource(_ source: Int) async {
        guard !busy, source != vault.source else { return }
        vault.source = source
        cards = []
        needsOTP = false
        form = ConnectionForm()
        notice = "点击查询，或在设置中添加连接。"
        do { try VaultStore.save(vault) } catch { notice = "服务已切换，但本机设置未能保存。" }
        objectWillChange.send()
    }

    func updateForm(_ update: (inout ConnectionForm) -> Void) {
        update(&form)
        objectWillChange.send()
    }

    private func preparedProfile() throws -> Profile {
        if let existing = activeProfile(), existing.sealed { return existing }
        switch vault.source {
        case 0:
            var profile = Profile(kind: "glm")
            profile.site = form.site == "global" ? "global" : "cn"
            profile.key = form.key
            return profile
        case 1:
            var profile = Profile(kind: "sub2api")
            profile.url = form.url
            profile.email = form.email
            profile.password = form.password
            profile.cached = form.cached
            return profile
        case 2:
            var profile = Profile(kind: "kimi")
            profile.key = form.key
            return profile
        case let source:
            guard let spec = service(source: source) else { throw QuotaError("不支持的服务。") }
            var profile = Profile(kind: spec.id)
            for field in spec.fields { if let value = form.secret[field.key] { if field.key == "secret" { profile.secret = value } else if field.key == "secret2" { profile.secret2 = value } else { profile.sessionToken = value } } }
            return profile
        }
    }

    func updateStoredProfile(_ profile: Profile?) {
        guard let profile else { return }
        let key = vault.source == 0 ? "glm" : vault.source == 1 ? "sub2api" : vault.source == 2 ? "kimi" : activeService()?.id ?? ""
        guard !key.isEmpty else { return }
        vault.profiles[key] = profile
        try? VaultStore.save(vault)
    }

    func runQuery() async {
        guard !busy else { return }
        if blocked { notice = "请先恢复连接：导入有效备份或清除本机连接。"; return }
        busy = true; notice = "正在查询……"; cards = []
        do {
            let profile = try preparedProfile()
            let result: [AccountCard]
            if vault.source == 0 { result = try await glmCards(profile: profile, transport: nativeTransport) }
            else if vault.source == 2 { result = try await queryKimi(profile: profile, transport: nativeTransport) }
            else if vault.source == 1 {
                let client = try SubClient(profile: profile)
                try await client.login(code: form.otp, captcha: form.captcha)
                result = try await queryAll(client: client) { [weak self] card in
                    Task { @MainActor in self?.replaceCard(card) }
                }
                subClient = client
                updateStoredProfile(client.profile)
            }
            else {
                guard let spec = activeService() else { throw QuotaError("不支持的服务。") }
                result = try await queryService(id: spec.id, profile: profile, transport: nativeTransport)
                var saved = profile; saved.sealed = profile.sealed
                updateStoredProfile(saved)
            }
            cards = result
            needsOTP = false
            notice = "查询成功 · 只读取额度，不调用模型。"
        } catch is NeedsOTP {
            needsOTP = true
            settingsOpen = true
            notice = "需要 2FA 验证码，填写后再次查询。"
        } catch {
            notice = (error as? LocalizedError)?.errorDescription ?? "查询失败，请重试。"
        }
        busy = false
    }

    private func replaceCard(_ card: AccountCard) {
        if let index = cards.firstIndex(where: { $0.id == card.id }) { cards[index] = card }
        else { cards.append(card) }
    }

    func subAction(_ action: String, card: AccountCard) async {
        guard !busy, busyCard == nil, vault.source == 1 else { return }
        busyCard = card.id; busy = true
        notice = action == "refresh" ? "正在刷新该账号额度并保存快照……" : "正在读取该账号的\(action == "reset" ? "重置卡次数" : "点数余额")……"
        do {
            let client = try await ensureSubClient()
            let account = Account(id: Int(card.id) ?? 0, name: card.title, platform: nil, type: nil, status: nil)
            var next = card
            if action == "refresh" {
                let usage = try await client.refreshUsage(account: account)
                next.windows = subWindows(usage)
                next.queries = [:]; next.error = nil
            } else {
                let window = action == "reset" ? try await client.queryResetCredits(account: account) : try await client.queryCredits(account: account)
                next.queries[action] = [window]
            }
            replaceCard(next)
            updateStoredProfile(client.profile)
            notice = "账号卡片查询成功 · 只读取接口实际返回的数据。"
        } catch {
            notice = (error as? LocalizedError)?.errorDescription ?? "卡片查询失败。"
        }
        busy = false; busyCard = nil
    }

    private func ensureSubClient() async throws -> SubClient {
        guard let profile = vault.profiles["sub2api"] else { throw QuotaError("请先添加 sub2api 连接。") }
        if let client = subClient, client.url == profile.url, client.profile.email == profile.email { return client }
        let client = try SubClient(profile: profile)
        try await client.login(code: form.otp, captcha: form.captcha)
        subClient = client
        return client
    }

    func clearConnection() async {
        try? VaultStore.clear()
        vault = freshVault(); cards = []; subClient = nil
        blocked = false; needsOTP = false; form = ConnectionForm()
        notice = "连接已清除，可以重新填写。"
    }

    func canExport() -> Bool {
        !vault.profiles.values.contains { $0.sealed }
    }

    func beginExport() {
        guard canExport() else { notice = "导入连接只可查询，不能再次导出。"; return }
        do {
            let own = try exportOwned(vault)
            guard !own.profiles.isEmpty else { throw QuotaError("没有可导出的自有连接。") }
            fileTask = .exportData
        } catch { notice = (error as? LocalizedError)?.errorDescription ?? "无法导出。" }
    }

    func makeExportData() throws -> Data {
        let own = try exportOwned(vault)
        return try NativeVaultCodec.seal(try encodeJSON(own.jsonValue()), mode: 1, secret: filePassword)
    }

    func prepareImport(url: URL) async {
        guard !busy else { return }
        busy = true
        do {
            let gotAccess = url.startAccessingSecurityScopedResource()
            defer { if gotAccess { url.stopAccessingSecurityScopedResource() } }
            let data = try Data(contentsOf: url)
            try validateFileMode(data)
            importURL = url
            filePassword = ""; fileConfirm = ""; fileError = ""
            fileTask = .importData(data)
        } catch {
            notice = (error as? LocalizedError)?.errorDescription ?? "导入失败。"
        }
        busy = false
    }

    private func validateFileMode(_ data: Data) throws {
        guard data.count >= 62, data.count <= 2 * 1024 * 1024, Array(data.prefix(8)) == [83, 81, 86, 65, 85, 76, 84, 0], data[data.startIndex + 8] == 1 else {
            throw QuotaError("文件格式或版本不受支持。")
        }
        let bytes = [UInt8](data)
        let wrapped = Int(bytes[10]) << 24 | Int(bytes[11]) << 16 | Int(bytes[12]) << 8 | Int(bytes[13])
        let size = Int(bytes[42]) << 24 | Int(bytes[43]) << 16 | Int(bytes[44]) << 8 | Int(bytes[45])
        guard size >= 16, wrapped <= 16384, 46 + wrapped + size == data.count else { throw QuotaError("文件已损坏。") }
        let mode = bytes[9]
        if mode == 0 { throw QuotaError("此文件绑定 Windows 用户，请在桌面端另存为跨电脑文件。") }
        guard mode == 1, wrapped == 0 else { throw QuotaError("请选择跨电脑加密连接文件。") }
    }

    func finishFile() async {
        guard let task = fileTask, !busy else { return }
        if filePassword.count < 12 { fileError = "文件密码至少需要 12 个字符。"; return }
        if case .exportData = task, filePassword != fileConfirm { fileError = "两次输入的文件密码不一致。"; return }
        busy = true; fileError = ""
        do {
            if case .importData = task {
                guard let url = importURL else { throw VaultFailure.invalid }
                let gotAccess = url.startAccessingSecurityScopedResource()
                defer { if gotAccess { url.stopAccessingSecurityScopedResource() } }
                let data = try Data(contentsOf: url)
                let plaintext = try NativeVaultCodec.open(data, secret: filePassword)
                let next = try lockImported(decodeJSON(plaintext))
                var merged = freshVault()
                merged.source = next.source
                merged.profiles = vault.profiles.merging(next.profiles) { _, imported in imported }
                try VaultStore.save(merged, replace: true)
                vault = merged; cards = []; subClient = nil
                settingsOpen = false
                notice = "连接已导入并隐藏凭据，点击查询即可。"
            }
            if case .exportData = task {
                exportData = try makeExportData()
                fileTask = nil
                notice = "在系统保存面板中选择位置即可。"
            }
        } catch {
            fileError = (error as? LocalizedError)?.errorDescription ?? "文件处理失败。"
        }
        busy = false
    }

    func exportedFile() -> Data? { exportData }
    func clearExport() { exportData = nil; filePassword = ""; fileConfirm = "" }

    private func nativeHealthCheck() async {
        var report: JSON = ["ok": false, "stage": "start"]
        let probe = "quota-check.native.probe." + String(Int(Date().timeIntervalSince1970 * 1000))
        do {
            let secret = try VaultStore.generateKey()
            try VaultStore.writeKey(secret, account: probe)
            report["stage"] = "keychain"; report["keychain"] = try VaultStore.readKey(account: probe) == secret
            try VaultStore.deleteKey(account: probe)
            report["signing"] = try NativeHashCodec.sha256("quota-check") == "d80211816271a3ca9c788e8be5c52c0e62c76b85f8eea3564d2860846641a928" && try NativeHashCodec.hmacSHA256("74657374", "quota-check") == "3792c792c75b5f8ca269a1a30c792c850f815b9cb2701a671a46c1401fa732db"
            let plain = try encodeJSON(freshVault().jsonValue())
            let portable = try NativeVaultCodec.seal(plain, mode: 1, secret: secret)
            report["crypto"] = try NativeVaultCodec.open(portable, secret: secret) == plain
            let temporary = try NativeVaultCodec.seal(plain, mode: 2, secret: secret)
            try VaultStore.writeStorage(temporary)
            report["storage"] = try VaultStore.readStorage() == temporary
            try VaultStore.deleteStorage()
            report["providerUI"] = QuotaCheckCore.services.count
            report["ok"] = report["keychain"] as? Bool == true && report["signing"] as? Bool == true && report["crypto"] as? Bool == true && report["storage"] as? Bool == true && QuotaCheckCore.services.count == 9
            report["stage"] = "complete"
        } catch { report["stage"] = "failed" }
        let url = try? FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("native-health.json")
        if let url, let data = try? JSONSerialization.data(withJSONObject: report, options: [.sortedKeys, .prettyPrinted]) {
            try? data.write(to: url)
        }
    }
}
#endif
