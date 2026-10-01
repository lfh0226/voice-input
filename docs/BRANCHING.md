# 分支与发布策略(GitFlow-lite + 语义化版本)

无人值守自迭代流程的核心规则。每个新功能一个分支,验证通过合并,合并即发布。

## 分支模型

| 分支 | 用途 | 生命周期 |
|---|---|---|
| `main` | 稳定发布线,每个 commit 可运行,合并即打 tag `vX.Y.Z` | 永久 |
| `develop` | 集成分支,功能在此汇合联调 | 永久 |
| `feature/vX.Y-描述` | 单功能开发,从 develop 切出 | 合并回 develop 后删除 |
| `release/vX.Y.Z` | 发布固化:从 develop 切出,只修 bug 不加功能,验收后合并 main+develop 并打 tag | 合并后删除 |
| `hotfix/描述` | 生产紧急修复:从 main 切出,修完合并 main+develop 并打 patch tag | 合并后删除 |

## 无人值守发布流水线(每迭代循环)

```
develop 切 feature 分支 → 实现 + 埋点验证(日志断言) → 合并 develop
→ 功能集合齐 → 切 release/vX.Y.Z → CI 绿灯 → 合并 main + 打 tag + push
→ GitHub Actions 自动构建插件产物并附加到 Release → 开启下一迭代
```

## 验证标准(合并前置条件)

1. `pytest`(无音频依赖用例)全绿
2. C++ 插件 cmake 构建零告警零错误
3. 真机冒烟:Alt_R 会话日志出现 "已通过 fcitx5 插件直接上屏"
4. 回退路径验证:杀掉 fcitx5 后语音仍能通过剪贴板粘贴输出

## 版本号(SemVer)

- 主版本:架构破坏性变更(如 IPC 协议重写)
- 次版本:新功能(V2.0 后端抽象、V2.1 常驻监听…)
- 修订号:bug 修复

