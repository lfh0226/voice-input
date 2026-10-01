// fcitx5 Voice Input 插件:接收 voice-input daemon 的流式识别结果,
// 中间结果 → 预编辑(灰字),最终结果 → commitText 直接上屏。
#include <fcitx/addonfactory.h>
#include <fcitx/addonmanager.h>
#include <fcitx/inputcontext.h>
#include <fcitx/inputpanel.h>
#include <fcitx/inputmethodengine.h>
#include <fcitx/inputmethodentry.h>
#include <fcitx/instance.h>
#include <fcitx/text.h>
#include <fcitx-utils/event.h>

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace fcitx {

namespace {

std::string socketPath() {
    const char *runtime = getenv("XDG_RUNTIME_DIR");
    std::string base = runtime ? runtime : "/run/user/1000";
    return base + "/voice-input/im.sock";
}

// 从 {"type":"...","text":"..."} 中提取 text(内容为 UTF-8,不含转义引号)
std::string extractText(const std::string &line) {
    const std::string key = "\"text\":\"";
    auto pos = line.find(key);
    if (pos == std::string::npos)
        return {};
    pos += key.size();
    auto end = line.find('"', pos);
    if (end == std::string::npos)
        return {};
    return line.substr(pos, end - pos);
}

} // namespace

class VoiceEngine : public InputMethodEngine {
public:
    VoiceEngine(Instance *instance) : instance_(instance) {
        startListen();
    }

    ~VoiceEngine() override {
        if (listenFd_ >= 0)
            close(listenFd_);
        if (clientFd_ >= 0)
            close(clientFd_);
    }

    void activate(const InputMethodEntry &, InputContextEvent &) override {}
    void deactivate(const InputMethodEntry &, InputContextEvent &) override {
        clearPreedit();
    }
    void reset(const InputMethodEntry &, InputContextEvent &) override {
        clearPreedit();
    }

    // 普通按键全部透传,不消费
    void keyEvent(const InputMethodEntry &, KeyEvent &) override {}

private:
    InputContext *focusedIC() {
        auto *ic = instance_->mostRecentInputContext();
        return (ic && ic->hasFocus()) ? ic : nullptr;
    }

    void clearPreedit() {
        auto *ic = focusedIC();
        if (!ic)
            return;
        ic->inputPanel().setClientPreedit(Text());
        ic->updateUserInterface(UserInterfaceComponent::InputPanel);
    }

    void startListen() {
        // 确保套接字父目录存在(如 /run/user/1000/voice-input)
        std::string path = socketPath();
        auto slash = path.rfind('/');
        if (slash != std::string::npos) {
            std::string dir = path.substr(0, slash);
            mkdir(dir.c_str(), 0755); // 已存在时忽略 EEXIST
        }
        listenFd_ = socket(AF_UNIX, SOCK_STREAM, 0);
        if (listenFd_ < 0)
            return;
        unlink(path.c_str());
        sockaddr_un addr{};
        addr.sun_family = AF_UNIX;
        strncpy(addr.sun_path, path.c_str(), sizeof(addr.sun_path) - 1);
        if (bind(listenFd_, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) < 0 ||
            listen(listenFd_, 1) < 0) {
            close(listenFd_);
            listenFd_ = -1;
            return;
        }
        listenSource_ = instance_->eventLoop().addIOEvent(
            listenFd_, IOEventFlag::In,
            [this](EventSourceIO *, int, IOEventFlags) -> bool {
                acceptClient();
                return true;
            });
    }

    void acceptClient() {
        int fd = accept(listenFd_, nullptr, nullptr);
        if (fd < 0)
            return;
        if (clientFd_ >= 0)
            close(clientFd_);
        clientFd_ = fd;
        clientSource_ = instance_->eventLoop().addIOEvent(
            clientFd_, IOEventFlag::In,
            [this](EventSourceIO *, int, IOEventFlags) -> bool {
                readClient();
                return true;
            });
    }

    void readClient() {
        char buf[8192];
        ssize_t n = recv(clientFd_, buf, sizeof(buf) - 1, 0);
        if (n <= 0) {
            clientFd_ = -1; // 对端断开,等待重连
            return;
        }
        buf[n] = '\0';
        // TCP 流式粘包处理:按 \n 拆分,残余半行留到下一次
        recvBuffer_.append(buf, n);
        size_t pos;
        while ((pos = recvBuffer_.find('\n')) != std::string::npos) {
            std::string line = recvBuffer_.substr(0, pos);
            recvBuffer_.erase(0, pos + 1);
            if (!line.empty())
                processLine(line);
        }
    }

    void processLine(const std::string &line) {
        std::string text = extractText(line);
        if (line.find("\"type\":\"partial\"") != std::string::npos) {
            auto *ic = focusedIC();
            if (!ic || text.empty())
                return;
            Text preedit;
            preedit.append(text, TextFormatFlag::HighLight);
            preedit.setCursor(text.size());
            ic->inputPanel().setClientPreedit(preedit);
            ic->updateUserInterface(UserInterfaceComponent::InputPanel);
        } else if (line.find("\"type\":\"final\"") != std::string::npos) {
            auto *ic = focusedIC();
            bool committed = false;
            if (ic && !text.empty()) {
                clearPreedit();
                ic->commitString(text);
                committed = true;
            }
            // 必须 ack,否则 daemon 等待超时后会走剪贴板回退造成重复输入
            std::string ack = committed ? "{\"type\":\"ack\",\"committed\":true}\n"
                                        : "{\"type\":\"ack\",\"committed\":false}\n";
            send(clientFd_, ack.c_str(), ack.size(), 0);
        } else if (line.find("\"type\":\"ping\"") != std::string::npos) {
            const char *pong = "{\"type\":\"pong\"}\n";
            send(clientFd_, pong, strlen(pong), 0);
        }
    }

    std::string recvBuffer_;

    Instance *instance_;
    int listenFd_ = -1;
    int clientFd_ = -1;
    std::unique_ptr<EventSourceIO> listenSource_;
    std::unique_ptr<EventSourceIO> clientSource_;
};

class VoiceIMAddonFactory : public AddonFactory {
public:
    AddonInstance *create(AddonManager *manager) override {
        return new VoiceEngine(manager->instance());
    }
};

} // namespace fcitx

FCITX_ADDON_FACTORY(fcitx::VoiceIMAddonFactory)
