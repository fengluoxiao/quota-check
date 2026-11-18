#if os(iOS)
import SwiftUI
import UniformTypeIdentifiers
import QuotaCheckCore

@main
struct QuotaCheckApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .task { await model.start() }
        }
    }
}

struct SQVDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.data] }
    var data = Data()

    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws {
        data = configuration.file.regularFileContents ?? Data()
    }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: data)
    }
}

struct RootView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var colorScheme
    @State private var importOpen = false
    @State private var exportOpen = false

    private var cardColor: Color { colorScheme == .dark ? Color(red: 0.106, green: 0.114, blue: 0.133) : .white }
    private var innerColor: Color { colorScheme == .dark ? Color(red: 0.063, green: 0.067, blue: 0.078) : Color(red: 0.953, green: 0.961, blue: 0.973) }
    private var ink: Color { colorScheme == .dark ? Color(red: 0.949, green: 0.953, blue: 0.969) : Color(red: 0.082, green: 0.133, blue: 0.220) }
    private var muted: Color { colorScheme == .dark ? Color(red: 0.635, green: 0.659, blue: 0.706) : Color(red: 0.392, green: 0.455, blue: 0.545) }
    private var tertiary: Color { colorScheme == .dark ? Color(red: 0.451, green: 0.490, blue: 0.549) : Color(red: 0.522, green: 0.573, blue: 0.651) }
    private var line: Color { colorScheme == .dark ? Color(red: 0.204, green: 0.224, blue: 0.263) : Color(red: 0.863, green: 0.886, blue: 0.922) }
    private var accent: Color { colorScheme == .dark ? Color(red: 0.318, green: 0.584, blue: 1) : Color(red: 0.090, green: 0.412, blue: 0.835) }
    private var soft: Color { colorScheme == .dark ? Color(red: 0.141, green: 0.212, blue: 0.310) : Color(red: 0.910, green: 0.941, blue: 0.992) }

    var body: some View {
        NavigationStack {
            Group {
                if model.loading { ProgressView("正在读取加密连接……") }
                else { content }
            }
            .background(colorScheme == .dark ? Color(red: 0.063, green: 0.067, blue: 0.078) : Color(red: 0.953, green: 0.961, blue: 0.973))
            .navigationTitle("额度查询")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { toolbarItems }
            .safeAreaInset(edge: .bottom) { footer }
        }
        .sheet(isPresented: $model.settingsOpen) { settingsSheet }
        .sheet(item: binding(for: \.fileTask)) { _ in filePasswordSheet }
        .fileImporter(isPresented: $importOpen, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            if let url = try? result.get().first { Task { await model.prepareImport(url: url) } }
        }
        .fileExporter(isPresented: $exportOpen, document: model.exportedFile().map(SQVDocument.init(data:)), contentType: .data, defaultFilename: "quota-check-connection") { result in
            model.clearExport()
            if case .success = result { model.notice = "加密连接已保存。" }
            else if case .failure(let error) = result { model.notice = "保存失败：\(error.localizedDescription)" }
        }
    }

    @ViewBuilder private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                sourceMenu
                if !model.cards.isEmpty { ForEach(model.cards) { card in AccountCardView(card: card, model: model, colors: CardColors(card: cardColor, inner: innerColor, ink: ink, muted: muted, tertiary: tertiary, line: line, accent: accent, soft: soft)) } }
                else { emptyCard }
                if !model.notice.isEmpty { Text(model.notice).font(.footnote).foregroundStyle(muted).padding(.horizontal, 3) }
            }
            .padding(.horizontal, 20)
            .padding(.top, 8)
            .padding(.bottom, 16)
        }
    }

    private var sourceMenu: some View {
        Menu {
            Button("GLM Coding Plan") { Task { await model.switchSource(0) } }
            Button("sub2api · GPT / Codex") { Task { await model.switchSource(1) } }
            Button("Kimi Coding Plan") { Task { await model.switchSource(2) } }
            Divider()
            ForEach(services, id: \.id) { item in
                Button(item.label) { Task { await model.switchSource(item.source) } }
            }
        } label: {
            HStack {
                Text("服务 · \(sourceLabel())").font(.headline).foregroundStyle(accent)
                Image(systemName: "chevron.down").font(.caption).foregroundStyle(accent)
                Spacer()
            }
            .padding(16).background(cardColor).clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(line, lineWidth: 0.5))
        }
    }

    private var emptyCard: some View {
        VStack(spacing: 10) {
            Text("查询你的额度与余额").font(.title2.bold()).foregroundStyle(ink)
            Text("添加一次连接后，点击查询即可。sub2api 后台有多少 GPT 账号，就显示多少张卡片。").font(.subheadline).foregroundStyle(muted).multilineTextAlignment(.center)
        }.frame(maxWidth: .infinity).padding(36).background(cardColor).clipShape(RoundedRectangle(cornerRadius: 16)).overlay(RoundedRectangle(cornerRadius: 16).stroke(line, lineWidth: 0.5)).padding(.top, 4)
    }

    @ToolbarContentBuilder private var toolbarItems: some ToolbarContent {
        ToolbarItemGroup(placement: .topBarTrailing) {
            Button("导入") { importOpen = true }
            Button("保存") { if model.canExport() { model.fileTask = .exportData } else { model.notice = "导入连接只可查询，不能再次导出。" } }
            Button("设置") { model.settingsOpen = true }
        }
    }

    private var footer: some View {
        VStack(spacing: 8) {
            Button {
                Task { await model.runQuery() }
            } label: {
                HStack { if model.busy { ProgressView().tint(.white) }; Text(model.busy ? "查询中……" : "查询额度").fontWeight(.semibold) }
                    .frame(maxWidth: .infinity).padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent).disabled(model.busy)
            Text("原生 SwiftUI · 只读取或刷新快照 · 不调用模型").font(.caption2).foregroundStyle(tertiary)
        }.padding(.horizontal, 20).padding(.bottom, 8).background(.ultraThinMaterial)
    }

    private var settingsSheet: some View {
        NavigationStack {
            Form {
                Section("连接") {
                    if model.blocked { Text(model.notice).foregroundStyle(.red).font(.footnote) }
                    Text(model.connectionTitle()).font(.subheadline).foregroundStyle(muted)
                    if let profile = model.activeProfile(), profile.sealed { Label("凭据已隐藏，点击查询即可使用", systemImage: "lock.shield").font(.footnote).foregroundStyle(accent) }
                }
                connectionForm
                Section {
                    Button(role: .destructive) {
                        Task { await model.clearConnection(); model.settingsOpen = false }
                    } label: { Text("清除本机连接") }
                } footer: { Text("清除只影响本机加密连接和 Keychain 密钥。导入连接仍需要原始跨电脑文件。") }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("完成") { model.settingsOpen = false } } }
        }
    }

    @ViewBuilder private var connectionForm: some View {
        if let profile = model.activeProfile(), profile.sealed {
            Section("已导入连接") { Text("已导入凭据只能查询，不能查看或再次导出。").font(.footnote).foregroundStyle(muted) }
            return
        }
        switch model.vault.source {
        case 0:
            Section("GLM 连接") {
                Picker("站点", selection: Binding(get: { model.form.site }, set: { selected in model.updateForm { $0.site = selected } })) { Text("智谱 BigModel").tag("cn"); Text("Z.ai Global").tag("global") }
                SecureField("Coding Plan API Key", text: Binding(get: { model.form.key }, set: { model.updateForm { $0.key = $1 } }))
            }
        case 1:
            Section("sub2api 管理员") {
                TextField("站点地址", text: Binding(get: { model.form.url }, set: { model.updateForm { $0.url = $1 } })).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                TextField("管理员邮箱", text: Binding(get: { model.form.email }, set: { model.updateForm { $0.email = $1 } })).keyboardType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                SecureField("密码", text: Binding(get: { model.form.password }, set: { model.updateForm { $0.password = $1 } }))
                Toggle("优先读取后台快照", isOn: Binding(get: { model.form.cached }, set: { model.updateForm { $0.cached = $1 } }))
                if model.needsOTP { TextField("6 位登录验证码", text: Binding(get: { model.form.otp }, set: { model.updateForm { $0.otp = $1 } })).keyboardType(.numberPad) }
            }
        case 2:
            Section("Kimi 连接") { SecureField("Coding Plan API Key", text: Binding(get: { model.form.key }, set: { model.updateForm { $0.key = $1 } })) }
        default:
            if let spec = model.activeService() {
                Section(spec.label) {
                    ForEach(spec.fields, id: \.key) { field in
                        fieldView(field, value: Binding(get: { model.form.secret[field.key] ?? "" }, set: { model.updateForm { $0.secret[field.key] = $1 } }))
                    }
                }
                Section { Text(spec.help).font(.footnote).foregroundStyle(muted) }
            }
        }
    }

    private func fieldView(_ field: ServiceField, value: Binding<String>) -> some View {
        Group {
            if field.key == "secret2" || field.key == "session_token" { SecureField(field.label, text: value) }
            else { TextField(field.label, text: value).textInputAutocapitalization(.never).autocorrectionDisabled() }
        }
    }

    private var filePasswordSheet: some View {
        NavigationStack {
            Form {
                Section("文件密码") {
                    SecureField("至少 12 个字符", text: $model.filePassword)
                    if case .exportData = model.fileTask { SecureField("再次输入密码", text: $model.fileConfirm) }
                    if !model.fileError.isEmpty { Text(model.fileError).foregroundStyle(.red).font(.footnote) }
                }
                Section {
                    Button(model.isImport ? "解密并导入" : "准备导出") { Task { await model.finishFile(); if model.exportedFile() != nil { model.fileTask = nil; exportOpen = true } } }.disabled(model.busy)
                    Button("取消", role: .cancel) { model.fileTask = nil; model.filePassword = ""; model.fileConfirm = ""; model.fileError = "" }
                } footer: {
                    Text(model.isImport ? "导入后不提供明文查看或再次导出。拥有文件密码或控制运行环境的人仍有提取凭据的条件。" : "导出使用独立文件密码保护跨电脑文件。")
                }
            }
            .navigationTitle(model.isImport ? "导入加密连接" : "保存加密连接")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private var isImport: Bool {
        if case .importData = model.fileTask { return true }
        return false
    }

    private func binding(for keyPath: KeyPath<AppModel, FileTask?>) -> Binding<FileTask?> {
        Binding(get: { model[keyPath: keyPath] }, set: { model.fileTask = $0 })
    }

    private func sourceLabel() -> String {
        if model.vault.source == 0 { return "GLM Coding Plan" }
        if model.vault.source == 1 { return "sub2api · GPT / Codex" }
        if model.vault.source == 2 { return "Kimi Coding Plan" }
        return model.activeService()?.label ?? "服务"
    }
}

struct CardColors {
    var card: Color
    var inner: Color
    var ink: Color
    var muted: Color
    var tertiary: Color
    var line: Color
    var accent: Color
    var soft: Color
}

struct AccountCardView: View {
    let card: AccountCard
    @ObservedObject var model: AppModel
    let colors: CardColors
    @State private var expanded: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(card.title).font(.headline).foregroundStyle(colors.ink)
            Text(card.subtitle).font(.caption).foregroundStyle(colors.muted)
            if let error = card.error { Text(error).font(.footnote).foregroundStyle(.red).padding(12).frame(maxWidth: .infinity, alignment: .leading).background(colors.inner).clipShape(RoundedRectangle(cornerRadius: 10)) }
            ForEach(Array(card.windows.enumerated()), id: \.offset) { _, window in WindowView(window: window, colors: colors) }
            ForEach(Array(["reset", "credits"].filter { card.queries[$0] != nil }.enumerated()), id: \.offset) { _, key in
                ForEach(Array((card.queries[key] ?? []).enumerated()), id: \.offset) { index, query in
                    QueryCardView(title: query.title, detail: query.detail, colors: colors)
                    if let lines = query.expandedLines, !lines.isEmpty {
                        Button {
                            let id = key + String(index); expanded = expanded == id ? nil : id
                        } label: {
                            Text(expanded == key + String(index) ? "收起明细" : query.expandedTitle ?? "展开明细").font(.caption.weight(.semibold)).foregroundStyle(colors.accent).frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 7).padding(.horizontal, 10).background(colors.card).clipShape(RoundedRectangle(cornerRadius: 8)).overlay(RoundedRectangle(cornerRadius: 8).stroke(colors.line, lineWidth: 0.5))
                        }
                        if expanded == key + String(index) {
                            VStack(alignment: .leading, spacing: 6) { ForEach(Array(lines.enumerated()), id: \.offset) { _, line in Text(line).font(.caption).foregroundStyle(colors.ink).padding(8).frame(maxWidth: .infinity, alignment: .leading).background(colors.card).clipShape(RoundedRectangle(cornerRadius: 8)) } }
                        }
                    }
                }
            }
            if card.actions.contains("reset") {
                HStack(spacing: 8) {
                    actionButton("重置卡", action: "reset", card: card)
                    actionButton("点数", action: "credits", card: card)
                    actionButton("刷新快照", action: "refresh", card: card, accent: true)
                }
                Text("只读取或刷新快照 · 不消耗重置卡").font(.caption2).foregroundStyle(colors.tertiary)
            }
        }
        .padding(18).frame(maxWidth: .infinity, alignment: .leading)
        .background(colors.card).clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(colors.line, lineWidth: 0.5))
    }

    private func actionButton(_ title: String, action: String, card: AccountCard, accent: Bool = false) -> some View {
        Button {
            Task { await model.subAction(action, card: card) }
        } label: {
            Text(title).font(.caption.weight(.semibold)).padding(.vertical, 6).padding(.horizontal, 13)
        }
        .buttonStyle(.borderedProminent)
        .tint(accent ? colors.accent : colors.soft)
        .foregroundStyle(accent ? .white : colors.accent)
        .disabled(model.busyCard != nil)
    }
}

struct WindowView: View {
    let window: UsageWindow
    let colors: CardColors

    private var stateColor: Color {
        guard let remaining = window.remaining else { return colors.muted }
        return remaining <= 10 ? .red : remaining <= 30 ? .orange : .green
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(window.title).font(.caption.weight(.semibold)).foregroundStyle(colors.muted)
                    Text(window.remaining == nil ? "未提供使用比例" : "剩余 \(String(format: "%.1f", window.remaining!))%").font(.title2.weight(.semibold)).foregroundStyle(stateColor)
                }
                Spacer()
                if let used = window.used { Text("已用 \(String(format: "%.1f", used))%").font(.caption).foregroundStyle(colors.muted) }
            }
            if window.used != nil { ProgressView(value: min(100, window.used!), total: 100).progressViewStyle(.linear).tint(colors.accent) }
            if !window.detail.isEmpty { Text(window.detail).font(.caption).foregroundStyle(colors.muted) }
            if !window.reset.isEmpty { Text("重置：\(window.reset)").font(.caption).foregroundStyle(colors.muted) }
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(colors.inner).clipShape(RoundedRectangle(cornerRadius: 10)).overlay(RoundedRectangle(cornerRadius: 10).stroke(colors.line, lineWidth: 0.5))
    }
}

struct QueryCardView: View {
    let title: String
    let detail: String
    let colors: CardColors

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(colors.muted)
            Text(detail.split(separator: "\n").first.map(String.init) ?? "").font(.title3.weight(.semibold)).foregroundStyle(colors.ink)
            ForEach(Array(detail.split(separator: "\n").dropFirst().enumerated()), id: \.offset) { _, line in
                Text(String(line)).font(.caption).foregroundStyle(colors.muted)
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(colors.inner).clipShape(RoundedRectangle(cornerRadius: 10)).overlay(RoundedRectangle(cornerRadius: 10).stroke(colors.line, lineWidth: 0.5))
    }
}
#endif
