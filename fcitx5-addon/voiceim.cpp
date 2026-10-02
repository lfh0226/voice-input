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

void debugLog(const std::string &msg) {
    FILE *f = fopen("/tmp/voiceim-debug.log", "a");
    if (f) {
        fprintf(f, "[voiceim %ld] %s\n", (long)time(nullptr), msg.c_str());
        fclose(f);
    }
}

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

    void activate(const InputMethodEntry &, InputContextEvent &) override {
        // 引擎激活时若还有暂存未上屏的最终结果,立即补 commit
        if (!pendingFinal_.empty()) {
            auto *ic = focusedIC();
            if (ic) {
                std::string t = pendingFinal_;
                pendingFinal_.clear();
                retrySource_.reset();
                ic->commitString(t);
                sendAck(true);
                debugLog("activate 补 commit,len=" + std::to_string(t.size()));
            }
        }
    }
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
        ic->inputPanel().setPreedit(Text());
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
            debugLog("bind/listen FAILED: " + std::string(strerror(errno)));
            return;
        }
        debugLog("listening on " + path);
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
        if (clientFd_ >= 0) {
            clientSource_.reset(); // 先移除旧 watcher,避免已关闭 fd 触发事件风暴
            close(clientFd_);
        }
        clientFd_ = fd;
        // 非阻塞:绝不允许 recv 阻塞 fcitx5 事件循环
        int fl = fcntl(fd, F_GETFL, 0);
        fcntl(fd, F_SETFL, fl | O_NONBLOCK);
        debugLog("client connected (non-blocking)");
        clientSource_ = instance_->eventLoop().addIOEvent(
            clientFd_, IOEventFlag::In,
            [this](EventSourceIO *, int, IOEventFlags) -> bool {
                debugLog("watcher fired");
                readClient();
                // 生命周期统一由 clientSource_ 管理(readClient 断开时 reset),
                // 这里恒返回 true,避免与 reset() 双重移除
                return true;
            });
        // 先发 ready 握手(客户端收到后才开始发数据),再手动读一次兜底
        const char *ready = "{\"type\":\"ready\"}\n";
        send(clientFd_, ready, strlen(ready), 0);
        debugLog("ready sent");
        readClient();
    }

    void readClient() {
        char buf[8192];
        errno = 0;
        debugLog("recv enter");
        ssize_t n = recv(clientFd_, buf, sizeof(buf) - 1, 0);
        if (n <= 0) {
            if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
                return; // 暂无数据(非阻塞 fd),继续等待
            debugLog("client disconnected n=" + std::to_string(n) +
                     " errno=" + std::to_string(errno));
            clientSource_.reset(); // 移除 watcher,防止死循环
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
            if (!ic || text.empty()) {
                debugLog("partial skipped: ic=" + std::string(ic ? "yes" : "null") +
                         " text_len=" + std::to_string(text.size()));
                return;
            }
            Text preedit;
            preedit.append(text, TextFormatFlag::HighLight);
            preedit.setCursor(text.size());
            ic->inputPanel().setClientPreedit(preedit);
            ic->inputPanel().setPreedit(preedit); // 悬浮窗显示,应用不支持 client 预编辑时可见
            ic->updateUserInterface(UserInterfaceComponent::InputPanel);
            debugLog("partial preedit set, len=" + std::to_string(text.size()));
        } else if (line.find("\"type\":\"final\"") != std::string::npos) {
            auto *ic = focusedIC();
            bool committed = false;
            debugLog("final: ic=" + std::string(ic ? "yes" : "null") +
                     " text_len=" + std::to_string(text.size()));
            if (ic && !text.empty()) {
                clearPreedit();
                ic->commitString(text);
                committed = true;
            }
            if (committed) {
                sendAck(true);
            } else if (!text.empty()) {
                // 焦点 IC 尚未就绪(切 IM 竞态):暂存并重试,焦点就绪后自动补上屏
                debugLog("final 暂存,等待焦点就绪(最长 3s)");
                pendingFinal_ = text;
                pendingRetries_ = 30;
                armRetry();
            } else {
                sendAck(false);
            }
        } else if (line.find("\"type\":\"ping\"") != std::string::npos) {
            const char *pong = "{\"type\":\"pong\"}\n";
            send(clientFd_, pong, strlen(pong), 0);
        }
    }

    std::string recvBuffer_;
    std::string pendingFinal_;
    int pendingRetries_ = 0;
    std::unique_ptr<EventSourceTime> retrySource_;

    static uint64_t nowUs() {
        timespec ts{};
        clock_gettime(CLOCK_MONOTONIC, &ts);
        return uint64_t(ts.tv_sec) * 1000000 + ts.tv_nsec / 1000;
    }

    void sendAck(bool committed) {
        if (clientFd_ < 0)
            return;
        std::string ack = committed ? "{\"type\":\"ack\",\"committed\":true}\n"
                                    : "{\"type\":\"ack\",\"committed\":false}\n";
        send(clientFd_, ack.c_str(), ack.size(), 0);
    }

    void armRetry() {
        retrySource_ = instance_->eventLoop().addTimeEvent(
            CLOCK_MONOTONIC, nowUs() + 100000, 10000,
            [this](EventSourceTime *, uint64_t) -> bool { return retryCommit(); });
    }

    bool retryCommit() {
        if (pendingFinal_.empty())
            return false; // 已处理,移除定时器
        auto *ic = focusedIC();
        if (!ic) {
            if (--pendingRetries_ > 0) {
                retrySource_->setTime(nowUs() + 100000);
                return true;
            }
            debugLog("重试超时,放弃 commit");
            sendAck(false);
            pendingFinal_.clear();
            retrySource_.reset();
            return false;
        }
        debugLog("焦点就绪,补 commit,len=" + std::to_string(pendingFinal_.size()));
        clearPreedit();
        ic->commitString(pendingFinal_);
        sendAck(true);
        pendingFinal_.clear();
        retrySource_.reset();
        return false;
    }

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
