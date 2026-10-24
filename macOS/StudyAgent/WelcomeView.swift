import AppKit
import SwiftUI

struct WelcomeView: View {
    @EnvironmentObject private var model: StudyAgentModel
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let onContinue: () -> Void

    @State private var page = 0

    private static let pageCount = 3

    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 16)

            illustration
                .frame(height: 176)
                .accessibilityHidden(true)

            VStack(spacing: 10) {
                Text(model.text(title))
                    .font(.largeTitle.weight(.semibold))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)

                Text(model.text(subtitle))
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)

                Text(model.text(description))
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: 500)

                if page == 2 {
                    Label(model.text("Для первой установки Ollama и моделей может понадобиться интернет. Загрузка начинается только по вашему выбору."), systemImage: "arrow.down.circle")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: 480, alignment: .leading)
                        .padding(.top, 4)
                }
            }
            .padding(.horizontal, 40)
            .id(page)
            .transition(.opacity.combined(with: reduceMotion ? .identity : .move(edge: .trailing)))

            Spacer(minLength: 16)

            Divider()
            HStack(spacing: 12) {
                Button(model.text("Назад"), systemImage: "chevron.left") {
                    move(to: page - 1)
                }
                .disabled(page == 0)
                .accessibilityLabel(model.text("Назад"))

                Spacer()
                HStack(spacing: 8) {
                    ForEach(0..<Self.pageCount, id: \.self) { index in
                        Circle()
                            .fill(index == page ? Color.accentColor : Color.secondary.opacity(0.35))
                            .frame(width: 7, height: 7)
                            .accessibilityHidden(true)
                    }
                }
                .accessibilityElement()
                .accessibilityLabel(L10n.format("Шаг %d из %d", language: model.language, page + 1, Self.pageCount))

                Spacer()
                Button(model.text("Пропустить знакомство")) { onContinue() }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                    .keyboardShortcut(.cancelAction)

                Button(model.text(page == 2 ? "Настроить Study Agent" : "Продолжить"), systemImage: page == 2 ? "gearshape" : "chevron.right") {
                    if page == Self.pageCount - 1 {
                        onContinue()
                    } else {
                        move(to: page + 1)
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 16)
        }
        .frame(minWidth: 680, idealWidth: 720, minHeight: 500, idealHeight: 540)
        .background(.background)
    }

    @ViewBuilder private var illustration: some View {
        switch page {
        case 0:
            if let appIcon = NSApp.applicationIconImage {
                Image(nsImage: appIcon)
                    .resizable()
                    .scaledToFit()
                    .frame(width: 112, height: 112)
            } else {
                illustrationTile("books.vertical.fill", tint: .blue, size: 112)
            }
        case 1:
            HStack(spacing: 22) {
                illustrationTile("folder.fill", tint: .blue, size: 66)
                Image(systemName: "arrow.right")
                    .font(.title3.weight(.medium))
                    .foregroundStyle(.tertiary)
                illustrationTile("doc.text.fill", tint: .cyan, size: 66)
                Image(systemName: "arrow.right")
                    .font(.title3.weight(.medium))
                    .foregroundStyle(.tertiary)
                illustrationTile("magnifyingglass", tint: .blue, size: 66)
            }
        default:
            HStack(spacing: 20) {
                illustrationTile("desktopcomputer", tint: .blue, size: 76)
                Image(systemName: "arrow.left.arrow.right")
                    .font(.title3.weight(.medium))
                    .foregroundStyle(.tertiary)
                illustrationTile("lock.shield.fill", tint: .green, size: 76)
            }
        }
    }

    private func illustrationTile(_ symbol: String, tint: Color, size: CGFloat) -> some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.43, weight: .regular))
            .foregroundStyle(tint.gradient)
            .frame(width: size, height: size)
            .background(tint.opacity(0.1), in: RoundedRectangle(cornerRadius: size * 0.25, style: .continuous))
    }

    private var title: String {
        ["Добро пожаловать в Study Agent", "Ваши материалы всегда под рукой", "Ваши знания остаются с вами"][page]
    }

    private var subtitle: String {
        [
            "Ваши учебные материалы — в одном удобном пространстве",
            "Находите нужное в выбранных документах",
            "Локальная обработка на вашем компьютере",
        ][page]
    }

    private var description: String {
        [
            "Ищите по лекциям, учебникам и конспектам. Если подключена локальная языковая модель, приложение сможет подготовить ответ по найденным материалам.",
            "Добавляйте папки с лекциями, учебниками и конспектами. Study Agent поможет найти нужную информацию в выбранных документах.",
            "Поиск и обработка выбранных учебных материалов выполняются на вашем компьютере. Для ответов можно использовать локальную языковую модель.",
        ][page]
    }

    private func move(to destination: Int) {
        guard (0..<Self.pageCount).contains(destination) else { return }
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) {
            page = destination
        }
    }
}
