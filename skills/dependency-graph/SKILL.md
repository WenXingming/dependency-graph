---
name: dependency-graph
description: 生成并解读代码库的文件级有向依赖关系图。凡是用户要求“依赖关系图”“架构可视化”“文件之间的依赖”“谁依赖谁”“include/import graph”“dependency graph”，或需要从依赖方向判断某个类型、头文件、模块是否应该拆分/合并/移动时，都应使用此技能。适用于 C/C++ include、Python import、JS/TS import 的基础依赖分析。
---

# 文件依赖关系图

使用此技能时，先把代码里的 `include` / `import` 关系转成可检查的有向图，再基于图分析架构。不要只凭文件名或直觉判断模块职责。

图的方向统一为：

```text
使用者文件 -> 被依赖文件
```

例如 `Hasher.h` 包含 `FileInfo.h`，边就是：

```text
Hasher.h -> FileInfo.h
```

这个方向能回答一个关键问题：每个文件为了完成自己的职责，必须知道哪些其他文件？

## 工作流程

1. 确定分析范围。
   - 用户指定目录或模块时，只分析该范围。
   - 用户只说“当前项目”时，优先从 `src/`、`include/`、`lib/`、`app/` 等源码目录开始。
   - 图太大时，缩小到能回答问题的最小模块。

2. 生成依赖图。
   - 优先使用 `scripts/generate_dependency_graph.py`。
   - 同时输出可视化文件和 JSON 边数据，便于人工查看和精确分析。
   - 如果安装了 Graphviz，优先输出 `.svg`；否则输出 `.html`、`.dot` 或 `.mmd`。
   - C/C++ 默认使用 `--cpp-view headers`：同名 `.h` / `.cpp` 同时存在时只展示头文件，让图更接近模块接口视图。需要实现细节时使用 `--cpp-view all`。
   - 默认使用 `--direction TB` 自上而下布局。文件数变多时它通常比自左向右更利于阅读长文件名；用户明确偏好横向图时再用 `--direction LR`。

3. 阅读图，而不是只列边。
   - 看哪些文件 fan-in 高：它们往往是共享模型、稳定接口或高风险改动点。
   - 看哪些文件 fan-out 高：它们往往是协调者、门面，或可能承担了过多职责。
   - 看是否有环：文件级环通常暗示声明放错位置、头文件过重或职责边界不清。
   - 看依赖方向是否自然：底层工具不应反向依赖高层流程。

4. 回答用户的设计问题。
   - 说明生成了哪些图文件。
   - 摘出最关键的边、fan-in/fan-out、循环情况。
   - 把结论落到用户关心的重构、拆分、合并、移动或命名问题上。
   - 说明限制：脚本主要做静态文本级解析，动态 import、宏生成 include、构建系统 include path 可能无法完全还原。

## 脚本用法

在仓库根目录运行：

```bash
python3 .agents/skills/dependency-graph/scripts/generate_dependency_graph.py \
  --root . \
  --scope src/dedup \
  --direction TB \
  --output /tmp/dedup-deps.svg \
  --json /tmp/dedup-deps.json
```

常用参数：

- `--scope PATH`：指定扫描目录或文件，可重复传入。
- `--include GLOB`：额外指定文件 glob，例如 `src/**/*.h`。
- `--exclude GLOB`：排除路径，例如 `build/**`、`third_party/**`。
- `--output PATH`：按扩展名输出 `.svg`、`.html`、`.dot`、`.mmd` 或 `.json`。
- `--json PATH`：额外输出原始图数据。
- `--external`：把未解析到本项目文件的外部依赖也画成灰色节点。
- `--no-tests`：忽略常见测试目录和测试文件。
- `--cpp-view headers|all`：C/C++ 默认 `headers`，同名 `.h` / `.cpp` 同时存在时只展示 `.h`；使用 `all` 可查看全部实现文件。
- `--direction TB|LR|BT|RL`：默认 `TB` 自上而下；`LR` 是自左向右。

推荐组合：

```bash
python3 .agents/skills/dependency-graph/scripts/generate_dependency_graph.py \
  --root . \
  --scope <目标目录> \
  --direction TB \
  --output /tmp/deps.svg \
  --json /tmp/deps.json
```

## 架构判断规则

当用户问“某个结构体/类/头文件该放在哪里”时，按这个顺序判断：

1. 如果多个平级文件都依赖它，它更像模块级共享模型或接口，倾向于保持独立。
2. 如果只有一个文件使用它，并且语义上确实只属于该文件，可以考虑内聚进去。
3. 如果移动后会迫使无关文件 include 更高层的类或流程对象，说明移动会制造语义耦合，应避免。
4. 如果出现环，优先考虑前置声明、拆出小接口、拆出值对象，或把实现依赖从头文件移到源文件。

## 回复格式

保持简洁，优先给图和结论：

```markdown
已生成依赖图：`/tmp/deps.svg`
原始边数据：`/tmp/deps.json`

关键观察：
- `A -> B`：A 直接依赖 B。
- `B` 的 fan-in 最高，更像共享模型/接口。
- 未发现循环依赖。

结论：...
```

如果图直接支撑用户的架构判断，要明确说出“为什么”。例如：`FileInfo.h` 被 `FileWalker.h`、`Hasher.h`、`DuplicateFinder.h` 同时依赖，因此它不是 `FileWalker` 的私有细节，保持独立更合理。
